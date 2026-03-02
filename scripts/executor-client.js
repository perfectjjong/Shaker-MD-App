#!/usr/bin/env node
/**
 * executor-client.js
 *
 * 소놀봇(커스텀 Telegram 봇)과 함께 실행하는 Executor 프로세스.
 * Shaker-MD-App 서버에 WebSocket으로 연결하여:
 *   1. 승인된 작업(task_available)을 실시간으로 수신
 *   2. 작업을 claim하고 PC에서 실행
 *   3. 결과를 서버에 보고
 *
 * 환경변수:
 *   EXECUTOR_SERVER_URL    ws://localhost:3847/ws/executor  (WS 연결)
 *   EXECUTOR_API_URL       http://localhost:3847            (HTTP API)
 *   EXECUTOR_ID            executor-sonolbot                (식별자)
 *   EXECUTOR_SECRET        (선택) 서버 공유 시크릿
 *   EXECUTOR_ALLOWED_DIRS  (선택) 허용 디렉토리, 콤마 구분
 *   EXECUTOR_MAX_CONCURRENT 1                              (최대 동시 실행)
 *   MAX_OUTPUT_SIZE        1048576                         (stdout 최대 크기)
 *   POLL_INTERVAL_MS       5000                            (HTTP polling 간격)
 *   EXECUTOR_WEBHOOK_URL   (선택) 작업 완료/실패 시 POST 알림을 보낼 URL
 *                          예: http://localhost:8765/executor-webhook
 *                          Payload: { taskId, title, type, status, exitCode,
 *                                     stdout, stderr, error, durationMs, executorId }
 */

'use strict';

require('dotenv').config();
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

// ─── 설정 ─────────────────────────────────────────────────

const EXECUTOR_ID = process.env.EXECUTOR_ID || `executor-${process.pid}`;
const EXECUTOR_SECRET = process.env.EXECUTOR_SECRET || '';
const API_URL = (process.env.EXECUTOR_API_URL || 'http://localhost:3847').replace(/\/$/, '');
const WS_URL = process.env.EXECUTOR_SERVER_URL
  || API_URL.replace(/^http/, 'ws') + `/ws/executor`;
const API_KEY = process.env.API_KEY || '';
const MAX_CONCURRENT = parseInt(process.env.EXECUTOR_MAX_CONCURRENT) || 1;
const MAX_OUTPUT = parseInt(process.env.MAX_OUTPUT_SIZE) || 1024 * 1024;
const POLL_INTERVAL = parseInt(process.env.POLL_INTERVAL_MS) || 5000;
const WEBHOOK_URL = process.env.EXECUTOR_WEBHOOK_URL || '';

const ALLOWED_DIRS = (process.env.EXECUTOR_ALLOWED_DIRS || '')
  .split(',')
  .map((d) => d.trim())
  .filter(Boolean);

// 위험 명령어 블록리스트
const DANGEROUS_PATTERNS = [
  /rm\s+-rf\s+\/(\s|$)/i,
  /mkfs/i,
  /dd\s+if=.*of=\/dev\/(sd|hd|nvme)/i,
  /:\s*\(\s*\)\s*\{.*:\|:&\s*\}/,  // fork bomb
  />\s*\/dev\/(sda|hda|nvme)/i,
  /shutdown\s+(-[rh]\s+)?now/i,
  /halt(\s|$)/i,
];

let runningCount = 0;
let ws = null;
let wsReconnectTimer = null;
let wsReconnectDelay = 2000;
let pollTimer = null;
let usePolling = false; // WS 실패 시 HTTP polling으로 전환

// ─── HTTP 유틸 ────────────────────────────────────────────

function apiHeaders() {
  const h = { 'Content-Type': 'application/json' };
  if (API_KEY) h['x-api-key'] = API_KEY;
  if (EXECUTOR_SECRET) h['x-executor-secret'] = EXECUTOR_SECRET;
  return h;
}

function apiRequest(method, urlPath, body) {
  return new Promise((resolve, reject) => {
    const fullUrl = `${API_URL}${urlPath}`;
    const isHttps = fullUrl.startsWith('https');
    const mod = isHttps ? https : http;
    const urlObj = new URL(fullUrl);

    const bodyStr = body ? JSON.stringify(body) : null;
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || (isHttps ? 443 : 80),
      path: urlObj.pathname + urlObj.search,
      method,
      headers: {
        ...apiHeaders(),
        ...(bodyStr ? { 'Content-Length': Buffer.byteLength(bodyStr) } : {}),
      },
      timeout: 30000,
    };

    const req = mod.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, body: data });
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('API request timeout')); });
    if (bodyStr) req.write(bodyStr);
    req.end();
  });
}

// ─── 보안 검사 ────────────────────────────────────────────

function isSafeCommand(command) {
  for (const pattern of DANGEROUS_PATTERNS) {
    if (pattern.test(command)) {
      return { safe: false, reason: `위험 패턴 차단: ${pattern}` };
    }
  }
  return { safe: true };
}

function isSafePath(filePath) {
  if (!ALLOWED_DIRS.length) return { safe: true };
  const resolved = path.resolve(filePath);
  for (const allowed of ALLOWED_DIRS) {
    if (resolved.startsWith(path.resolve(allowed))) {
      return { safe: true };
    }
  }
  return { safe: false, reason: `허용되지 않은 경로: ${resolved} (허용: ${ALLOWED_DIRS.join(', ')})` };
}

// ─── 작업 실행 ────────────────────────────────────────────

async function executeBash(payload) {
  const { command, cwd } = payload;
  if (!command) throw new Error('command가 없습니다');

  const safeCheck = isSafeCommand(command);
  if (!safeCheck.safe) {
    return { exitCode: -1, stdout: '', stderr: safeCheck.reason, error: '보안 정책에 의해 차단됨' };
  }

  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    const startTime = Date.now();
    const execTimeout = (parseInt(process.env.TASK_EXECUTION_TIMEOUT) || 1800) * 1000;

    const proc = spawn('bash', ['-c', command], {
      cwd: cwd || process.cwd(),
      env: process.env,
      timeout: execTimeout,
    });

    proc.stdout.on('data', (chunk) => {
      stdout += chunk;
      if (stdout.length > MAX_OUTPUT) {
        stdout = stdout.slice(0, MAX_OUTPUT) + '\n[출력 크기 초과로 잘림]';
        proc.kill('SIGTERM');
      }
    });

    proc.stderr.on('data', (chunk) => {
      stderr += chunk;
      if (stderr.length > MAX_OUTPUT) {
        stderr = stderr.slice(0, MAX_OUTPUT) + '\n[출력 크기 초과로 잘림]';
      }
    });

    proc.on('close', (code, signal) => {
      const duration = Date.now() - startTime;
      console.log(`[Executor] bash 완료 (exit=${code}, signal=${signal}, ${duration}ms)`);
      resolve({
        exitCode: code !== null ? code : -1,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        signal: signal || null,
        durationMs: duration,
      });
    });

    proc.on('error', (err) => {
      resolve({ exitCode: -1, stdout: '', stderr: err.message, error: err.message });
    });
  });
}

async function executeFileRead(payload) {
  const { filePath } = payload;
  const pathCheck = isSafePath(filePath);
  if (!pathCheck.safe) {
    return { exitCode: -1, error: pathCheck.reason };
  }
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    return { exitCode: 0, stdout: content };
  } catch (e) {
    return { exitCode: -1, error: e.message };
  }
}

async function executeFileWrite(payload) {
  const { filePath, content } = payload;
  const pathCheck = isSafePath(filePath);
  if (!pathCheck.safe) {
    return { exitCode: -1, error: pathCheck.reason };
  }
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content || '', 'utf8');
    return { exitCode: 0, stdout: `파일 저장 완료: ${filePath}` };
  } catch (e) {
    return { exitCode: -1, error: e.message };
  }
}

async function executeFileEdit(payload) {
  const { filePath, oldStr, newStr } = payload;
  const pathCheck = isSafePath(filePath);
  if (!pathCheck.safe) {
    return { exitCode: -1, error: pathCheck.reason };
  }
  try {
    const original = fs.readFileSync(filePath, 'utf8');
    if (!original.includes(oldStr)) {
      return { exitCode: -1, error: `대상 문자열을 찾을 수 없습니다: "${oldStr.slice(0, 100)}"` };
    }
    const updated = original.replace(oldStr, newStr);
    fs.writeFileSync(filePath, updated, 'utf8');
    return { exitCode: 0, stdout: `파일 수정 완료: ${filePath}` };
  } catch (e) {
    return { exitCode: -1, error: e.message };
  }
}

async function executeCustom(payload) {
  const { script } = payload;
  if (!script) {
    return { exitCode: -1, error: 'script가 없습니다' };
  }
  return executeBash({ command: script, cwd: payload.cwd });
}

async function executeTask(task) {
  console.log(`[Executor] 실행: [${task.type}] ${task.title}`);
  try {
    switch (task.type) {
      case 'bash':       return await executeBash(task.payload);
      case 'file_read':  return await executeFileRead(task.payload);
      case 'file_write': return await executeFileWrite(task.payload);
      case 'file_edit':  return await executeFileEdit(task.payload);
      case 'custom':     return await executeCustom(task.payload);
      default:
        return { exitCode: -1, error: `알 수 없는 작업 유형: ${task.type}` };
    }
  } catch (e) {
    return { exitCode: -1, error: e.message };
  }
}

// ─── Webhook 알림 ────────────────────────────────────────

async function notifyWebhook(task, result) {
  if (!WEBHOOK_URL) return;
  const payload = JSON.stringify({
    taskId: task.id,
    title: task.title,
    type: task.type,
    status: result.exitCode === 0 ? 'completed' : 'failed',
    exitCode: result.exitCode,
    stdout: (result.stdout || '').slice(0, 2000),
    stderr: (result.stderr || '').slice(0, 500),
    error: result.error || null,
    durationMs: result.durationMs || null,
    executorId: EXECUTOR_ID,
  });

  try {
    const urlObj = new URL(WEBHOOK_URL);
    const isHttps = WEBHOOK_URL.startsWith('https');
    const mod = isHttps ? https : http;
    await new Promise((resolve, reject) => {
      const req = mod.request(
        {
          hostname: urlObj.hostname,
          port: urlObj.port || (isHttps ? 443 : 80),
          path: urlObj.pathname + urlObj.search,
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload),
          },
          timeout: 10000,
        },
        (res) => {
          res.resume();
          resolve(res.statusCode);
        }
      );
      req.on('error', reject);
      req.on('timeout', () => { req.destroy(); reject(new Error('webhook timeout')); });
      req.write(payload);
      req.end();
    });
    console.log(`[Executor] Webhook 알림 전송 완료: ${WEBHOOK_URL}`);
  } catch (e) {
    console.warn(`[Executor] Webhook 알림 실패 (무시):`, e.message);
  }
}

// ─── Task 처리 파이프라인 ─────────────────────────────────

async function processTask(task) {
  if (runningCount >= MAX_CONCURRENT) {
    console.log(`[Executor] 동시 실행 제한 초과 (${runningCount}/${MAX_CONCURRENT}), 건너뜀: ${task.id}`);
    return;
  }

  // claim
  let claimedTask;
  try {
    const resp = await apiRequest('POST', `/api/tasks/executor/claim/${task.id}`, {
      executorId: EXECUTOR_ID,
    });
    if (resp.status !== 200) {
      console.log(`[Executor] claim 실패 (status=${resp.status}): ${task.id}`);
      return;
    }
    claimedTask = resp.body;
  } catch (e) {
    console.error(`[Executor] claim 오류:`, e.message);
    return;
  }

  runningCount++;
  console.log(`[Executor] 실행 시작: ${claimedTask.id.slice(0, 8)}... (동시 실행: ${runningCount})`);

  try {
    const result = await executeTask(claimedTask);

    await apiRequest('POST', `/api/tasks/executor/result/${claimedTask.id}`, {
      executorId: EXECUTOR_ID,
      result,
    });
    console.log(`[Executor] 결과 보고 완료: ${claimedTask.id.slice(0, 8)}... (exit=${result.exitCode})`);
    await notifyWebhook(claimedTask, result);
  } catch (e) {
    console.error(`[Executor] 실행/보고 오류:`, e.message);
    // 오류 결과 보고 시도
    try {
      const errResult = { exitCode: -1, error: e.message };
      await apiRequest('POST', `/api/tasks/executor/result/${claimedTask.id}`, {
        executorId: EXECUTOR_ID,
        result: errResult,
      });
      await notifyWebhook(claimedTask, errResult);
    } catch {
      // 무시
    }
  } finally {
    runningCount--;
  }
}

// ─── HTTP polling ─────────────────────────────────────────

async function pollTasks() {
  try {
    const resp = await apiRequest(
      'GET',
      `/api/tasks/executor/tasks?executorId=${encodeURIComponent(EXECUTOR_ID)}`
    );
    if (resp.status === 200 && Array.isArray(resp.body)) {
      for (const task of resp.body) {
        processTask(task).catch((e) => console.error('[Executor] processTask 오류:', e.message));
      }
    }
  } catch (e) {
    console.warn('[Executor] polling 오류:', e.message);
  }
}

function startPolling() {
  if (pollTimer) return;
  console.log(`[Executor] HTTP polling 시작 (interval: ${POLL_INTERVAL}ms)`);
  pollTasks(); // 즉시 첫 poll
  pollTimer = setInterval(pollTasks, POLL_INTERVAL);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ─── WebSocket 연결 ───────────────────────────────────────

function connectWebSocket() {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }

  const { WebSocket } = require('ws');
  const wsUrl = `${WS_URL}?executorId=${encodeURIComponent(EXECUTOR_ID)}&capabilities=bash,file_read,file_write,file_edit,custom${API_KEY ? '&api_key=' + API_KEY : ''}`;

  console.log(`[Executor] WebSocket 연결 시도: ${WS_URL}`);
  ws = new WebSocket(wsUrl);

  ws.on('open', () => {
    console.log(`[Executor] WebSocket 연결 성공`);
    wsReconnectDelay = 2000;
    usePolling = false;
    stopPolling();

    // heartbeat (30초마다)
    const hbInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'heartbeat' }));
      } else {
        clearInterval(hbInterval);
      }
    }, 30000);
  });

  ws.on('message', (raw) => {
    try {
      const msg = JSON.parse(raw);
      if (msg.type === 'task_available' && msg.data) {
        console.log(`[Executor] 새 작업 수신: ${msg.data.id?.slice(0, 8)}...`);
        processTask(msg.data).catch((e) =>
          console.error('[Executor] processTask 오류:', e.message)
        );
      }
    } catch (e) {
      console.error('[Executor] WS 메시지 파싱 오류:', e.message);
    }
  });

  ws.on('close', (code, reason) => {
    console.warn(`[Executor] WebSocket 연결 해제 (code=${code}, reason=${reason})`);
    ws = null;
    scheduleReconnect();
  });

  ws.on('error', (err) => {
    console.error(`[Executor] WebSocket 오류:`, err.message);
    // close 이벤트가 뒤따름
  });
}

function scheduleReconnect() {
  if (wsReconnectTimer) return;

  // 첫 재연결 실패 후 polling으로 폴백
  if (!usePolling) {
    usePolling = true;
    startPolling();
  }

  console.log(`[Executor] ${wsReconnectDelay / 1000}초 후 WebSocket 재연결 시도...`);
  wsReconnectTimer = setTimeout(() => {
    wsReconnectTimer = null;
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 60000);
    connectWebSocket();
  }, wsReconnectDelay);
}

// ─── Executor 등록 ────────────────────────────────────────

async function register() {
  try {
    const resp = await apiRequest('POST', '/api/tasks/executor/register', {
      executorId: EXECUTOR_ID,
      capabilities: ['bash', 'file_read', 'file_write', 'file_edit', 'custom'],
    });
    if (resp.status === 200) {
      console.log(`[Executor] 서버에 등록 완료: ${EXECUTOR_ID}`);
    } else {
      console.warn(`[Executor] 등록 응답 이상 (status=${resp.status}):`, resp.body);
    }
  } catch (e) {
    console.warn(`[Executor] 등록 실패 (서버 미실행?):`, e.message);
  }
}

// ─── 시작 ─────────────────────────────────────────────────

async function main() {
  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║   Shaker-MD-App Executor Client              ║');
  console.log('╠══════════════════════════════════════════════╣');
  console.log(`║   ID:    ${EXECUTOR_ID.padEnd(35)}║`);
  console.log(`║   API:   ${API_URL.padEnd(35)}║`);
  console.log(`║   WS:    ${WS_URL.padEnd(35)}║`);
  if (ALLOWED_DIRS.length) {
    console.log(`║   허용경로: ${ALLOWED_DIRS.join(', ').slice(0, 33)}║`);
  } else {
    console.log('║   허용경로: 제한 없음                         ║');
  }
  if (WEBHOOK_URL) {
    console.log(`║   Webhook: ${WEBHOOK_URL.slice(0, 34)}║`);
  }
  console.log(`║   최대동시실행: ${String(MAX_CONCURRENT).padEnd(28)}║`);
  console.log('╚══════════════════════════════════════════════╝');
  console.log('');

  // 서버에 Executor 등록
  await register();

  // WebSocket 연결 시작
  try {
    connectWebSocket();
  } catch (e) {
    // ws 모듈 없을 경우 polling으로 폴백
    console.warn('[Executor] WebSocket 모듈 오류, polling으로 전환:', e.message);
    usePolling = true;
    startPolling();
  }
}

// ─── Graceful shutdown ────────────────────────────────────

function shutdown(signal) {
  console.log(`\n[Executor] ${signal} - 종료 중...`);
  if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
  stopPolling();
  if (ws) {
    try { ws.close(1001, '정상 종료'); } catch {}
  }
  setTimeout(() => process.exit(0), 1000);
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

// ws 모듈 확인
try {
  require.resolve('ws');
  main().catch((e) => {
    console.error('[Executor] 시작 오류:', e.message);
    process.exit(1);
  });
} catch {
  console.error('[Executor] ws 모듈 없음. npm install ws 실행 후 재시도하거나,');
  console.error('           EXECUTOR_SERVER_URL을 빈 값으로 설정하면 HTTP polling만 사용합니다.');
  // ws 없이 polling으로 시작
  register().then(() => {
    usePolling = true;
    startPolling();
    console.log('[Executor] HTTP polling 모드로 시작됨');
  });
}
