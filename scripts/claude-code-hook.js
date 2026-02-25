#!/usr/bin/env node
/**
 * Claude Code Hook Script (Node.js 버전)
 *
 * Claude Code의 PreToolUse 훅으로 사용됩니다.
 * stdin으로 JSON을 받아 승인 서버에 요청을 보내고,
 * 승인/거부 결과를 stdout으로 반환합니다.
 *
 * 설치: Claude Code settings.json의 hooks 섹션에 추가
 * {
 *   "hooks": {
 *     "PreToolUse": [
 *       {
 *         "matcher": "",
 *         "hooks": [
 *           {
 *             "type": "command",
 *             "command": "node /path/to/claude-code-hook.js"
 *           }
 *         ]
 *       }
 *     ]
 *   }
 * }
 */

const http = require('http');

const SERVER_URL = process.env.CLAUDE_APPROVER_URL || 'http://localhost:3847';

async function main() {
  // stdin에서 JSON 읽기
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const input = JSON.parse(Buffer.concat(chunks).toString());

  const toolName = input.tool_name || '';
  const toolInput = input.tool_input || {};

  // 명령어 추출
  let command = '';
  if (toolName === 'Bash') {
    command = toolInput.command || '';
  } else if (toolName === 'Edit' || toolName === 'Write') {
    command = `${toolName}: ${toolInput.file_path || ''}`;
  } else {
    command = JSON.stringify(toolInput).slice(0, 200);
  }

  // 서버로 승인 요청
  try {
    const result = await requestApproval({
      command,
      tool: toolName,
      workdir: toolInput.workdir || process.cwd(),
    });

    if (result.status === 'rejected') {
      // 거부: Claude Code에 block 응답
      const response = {
        decision: 'block',
        reason: result.reason || '모바일에서 거부됨',
      };
      process.stdout.write(JSON.stringify(response));
    }
    // 승인 또는 기타: 빈 출력 (진행 허용)
  } catch (err) {
    // 서버 연결 실패 시 기본 허용 (Claude Code 사용에 지장 없도록)
    process.stderr.write(`[Approver] 서버 연결 실패: ${err.message}\n`);
  }
}

function requestApproval(data) {
  return new Promise((resolve, reject) => {
    const url = new URL(`${SERVER_URL}/api/approval`);
    const postData = JSON.stringify(data);

    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
      },
      timeout: 300000, // 5분 타임아웃
    };

    const req = http.request(options, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        try {
          resolve(JSON.parse(Buffer.concat(chunks).toString()));
        } catch (e) {
          reject(new Error('Invalid response'));
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });

    req.write(postData);
    req.end();
  });
}

main().catch((err) => {
  process.stderr.write(`[Approver] Error: ${err.message}\n`);
  process.exit(0); // 에러 시에도 exit 0으로 Claude Code 진행 허용
});
