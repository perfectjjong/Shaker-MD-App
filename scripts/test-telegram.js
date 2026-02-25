#!/usr/bin/env node
/**
 * Telegram Bot 연결 테스트 + 승인 시뮬레이션
 *
 * 실행: node scripts/test-telegram.js
 *
 * 실행 중인 서버에 가짜 승인 요청을 보내서
 * Telegram 알림이 정상 작동하는지 테스트합니다.
 */

const http = require('http');
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const SERVER_URL = process.env.CLAUDE_APPROVER_URL || `http://localhost:${process.env.PORT || 3847}`;

function post(url, data) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const postData = JSON.stringify(data);
    const req = http.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(postData),
        },
        timeout: 10000,
      },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString()));
          } catch (e) {
            reject(new Error('응답 파싱 실패'));
          }
        });
      }
    );
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('타임아웃')); });
    req.write(postData);
    req.end();
  });
}

async function main() {
  console.log('');
  console.log('=== Telegram 알림 테스트 ===');
  console.log(`서버: ${SERVER_URL}`);
  console.log('');

  // 서버 연결 확인
  console.log('[1/3] 서버 연결 확인...');
  try {
    await new Promise((resolve, reject) => {
      const parsed = new URL(`${SERVER_URL}/api/pending`);
      http.get({ hostname: parsed.hostname, port: parsed.port, path: parsed.pathname, timeout: 5000 }, (res) => {
        res.resume();
        resolve();
      }).on('error', reject);
    });
    console.log('  OK - 서버 연결됨');
  } catch (e) {
    console.log(`  FAIL - 서버에 연결할 수 없습니다: ${e.message}`);
    console.log('  "npm start"로 서버를 먼저 시작하세요.');
    process.exit(1);
  }

  // 테스트 승인 요청 전송
  console.log('');
  console.log('[2/3] 테스트 승인 요청 전송...');
  console.log('  Telegram에서 [승인] 또는 [거부] 버튼을 눌러주세요.');
  console.log('  (30초 타임아웃)');
  console.log('');

  const startTime = Date.now();

  try {
    const result = await Promise.race([
      post(`${SERVER_URL}/api/approval`, {
        command: 'echo "Hello from test!" && ls -la /home/user',
        tool: 'Bash',
        workdir: '/home/user/test-project',
        sessionId: 'test-session',
      }),
      new Promise((_, reject) => setTimeout(() => reject(new Error('30초 타임아웃')), 30000)),
    ]);

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

    console.log(`[3/3] 결과: ${result.status} (${elapsed}초)`);

    if (result.status === 'approved') {
      console.log('  OK - 승인 처리 정상 작동!');
    } else if (result.status === 'rejected') {
      console.log('  OK - 거부 처리 정상 작동!');
    } else if (result.auto) {
      console.log('  INFO - 자동 승인 규칙에 의해 처리됨');
    } else {
      console.log(`  WARN - 예상치 못한 상태: ${result.status}`);
    }
  } catch (e) {
    console.log(`  FAIL - ${e.message}`);
    if (e.message.includes('타임아웃')) {
      console.log('  Telegram 알림을 확인하고 버튼을 눌러주세요.');
    }
  }

  console.log('');
  console.log('테스트 완료!');
}

main().catch((e) => {
  console.error('오류:', e.message);
  process.exit(1);
});
