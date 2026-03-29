#!/usr/bin/env node
/**
 * Claude Code Hook Script (Node.js)
 *
 * Claude Code의 PreToolUse 훅으로 동작합니다.
 * stdin으로 JSON을 받아 승인 서버에 요청을 보내고,
 * 승인/거부 결과를 stdout으로 반환합니다.
 *
 * 서버가 꺼져있으면 자동으로 패스 (Claude Code 사용에 지장 없음)
 *
 * 설치: npm run hook:install
 * 또는 수동으로 Claude Code settings.json에 추가:
 * {
 *   "hooks": {
 *     "PreToolUse": [{
 *       "matcher": "",
 *       "hooks": [{ "type": "command", "command": "node /path/to/claude-code-hook.js" }]
 *     }]
 *   }
 * }
 */

const http = require('http');

const SERVER_URL = process.env.CLAUDE_APPROVER_URL || 'http://localhost:3847';
const API_KEY = process.env.CLAUDE_APPROVER_API_KEY || '';
const CONNECT_TIMEOUT = 3000;  // 서버 연결 타임아웃 (3초)
const APPROVAL_TIMEOUT = 300000; // 승인 대기 타임아웃 (5분)

async function main() {
  // stdin에서 JSON 읽기
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }

  let input;
  try {
    input = JSON.parse(Buffer.concat(chunks).toString());
  } catch (e) {
    // JSON 파싱 실패시 패스
    process.exit(0);
  }

  const toolName = input.tool_name || '';
  const toolInput = input.tool_input || {};

  // 모든 도구 자동 승인 (승인 서버 미사용)
  process.exit(0);

  // 명령어 추출
  let command = '';
  if (toolName === 'Bash') {
    command = toolInput.command || '';
  } else if (toolName === 'Edit') {
    command = `Edit: ${toolInput.file_path || ''} (${(toolInput.old_string || '').slice(0, 50)}→...)`;
  } else if (toolName === 'Write') {
    command = `Write: ${toolInput.file_path || ''}`;
  } else if (toolName === 'NotebookEdit') {
    command = `NotebookEdit: ${toolInput.notebook_path || ''}`;
  } else {
    command = `${toolName}: ${JSON.stringify(toolInput).slice(0, 200)}`;
  }

  // 서버 연결 확인 (빠르게)
  const serverAlive = await checkServer();
  if (!serverAlive) {
    // 서버가 꺼져있으면 그냥 패스
    process.exit(0);
  }

  // 서버로 승인 요청
  try {
    const result = await requestApproval({
      command,
      tool: toolName,
      workdir: process.cwd(),
    });

    if (result.status === 'rejected') {
      process.stdout.write(JSON.stringify({
        decision: 'block',
        reason: result.reason || '모바일에서 거부됨',
      }));
    }
    // approved / auto / timeout → 진행 허용
  } catch (err) {
    process.stderr.write(`[Approver] ${err.message}\n`);
  }
}

function checkServer() {
  return new Promise((resolve) => {
    const url = new URL(`${SERVER_URL}/api/pending`);
    const headers = API_KEY ? { 'x-api-key': API_KEY } : {};
    const req = http.get(
      { hostname: url.hostname, port: url.port, path: url.pathname, timeout: CONNECT_TIMEOUT, headers },
      (res) => { res.resume(); resolve(true); }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

function requestApproval(data) {
  return new Promise((resolve, reject) => {
    const url = new URL(`${SERVER_URL}/api/approval`);
    const postData = JSON.stringify(data);

    const req = http.request(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(postData),
          ...(API_KEY ? { 'x-api-key': API_KEY } : {}),
        },
        timeout: APPROVAL_TIMEOUT,
      },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString()));
          } catch (e) {
            reject(new Error('Invalid response'));
          }
        });
      }
    );

    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Approval timeout')); });
    req.write(postData);
    req.end();
  });
}

main().catch((err) => {
  process.stderr.write(`[Approver] ${err.message}\n`);
  process.exit(0);
});
