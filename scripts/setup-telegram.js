#!/usr/bin/env node
/**
 * Telegram Bot 초기 셋업 위저드
 *
 * 실행: node scripts/setup-telegram.js
 *
 * 단계:
 * 1. Bot Token 입력 안내
 * 2. Token 유효성 검증
 * 3. Chat ID 자동 감지
 * 4. .env 파일 자동 생성
 * 5. 테스트 메시지 전송
 */

const https = require('https');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const ENV_PATH = path.join(__dirname, '..', '.env');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

function ask(question) {
  return new Promise((resolve) => rl.question(question, resolve));
}

function telegramApi(token, method, body) {
  return new Promise((resolve, reject) => {
    const postData = body ? JSON.stringify(body) : '';
    const options = {
      hostname: 'api.telegram.org',
      path: `/bot${token}/${method}`,
      method: body ? 'POST' : 'GET',
      headers: body
        ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) }
        : {},
    };
    const req = https.request(options, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        try {
          resolve(JSON.parse(Buffer.concat(chunks).toString()));
        } catch (e) {
          reject(new Error('응답 파싱 실패'));
        }
      });
    });
    req.on('error', reject);
    if (body) req.write(postData);
    req.end();
  });
}

async function main() {
  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║   Telegram Bot 셋업 위저드                   ║');
  console.log('╚══════════════════════════════════════════════╝');
  console.log('');

  // Step 1: Bot Token
  console.log('[ Step 1 ] Telegram Bot 토큰');
  console.log('');
  console.log('  1. Telegram에서 @BotFather 검색');
  console.log('  2. /newbot 명령어 전송');
  console.log('  3. 봇 이름 입력 (예: Claude Approver)');
  console.log('  4. 봇 username 입력 (예: claude_approver_bot)');
  console.log('  5. 받은 토큰 복사');
  console.log('');

  const token = (await ask('  Bot Token 입력: ')).trim();

  if (!token || !token.includes(':')) {
    console.log('\n  [오류] 유효하지 않은 토큰 형식입니다.');
    console.log('  형식: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz');
    rl.close();
    process.exit(1);
  }

  // Step 2: Token 검증
  console.log('\n  토큰 검증 중...');
  try {
    const me = await telegramApi(token, 'getMe');
    if (!me.ok) {
      console.log('  [오류] 유효하지 않은 토큰입니다.');
      rl.close();
      process.exit(1);
    }
    console.log(`  [확인] 봇 이름: @${me.result.username}`);
  } catch (e) {
    console.log(`  [오류] API 연결 실패: ${e.message}`);
    rl.close();
    process.exit(1);
  }

  // Step 3: Chat ID 감지
  console.log('');
  console.log('[ Step 2 ] Chat ID 설정');
  console.log('');
  console.log('  Telegram에서 방금 만든 봇에게 /start 메시지를 보내세요.');
  console.log('  (보낸 후 Enter를 눌러주세요)');

  await ask('  전송 후 Enter: ');

  console.log('  Chat ID 감지 중...');
  let chatId = null;

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const updates = await telegramApi(token, 'getUpdates');
      if (updates.ok && updates.result.length > 0) {
        // 가장 최근 메시지의 chat id
        const lastMsg = updates.result[updates.result.length - 1];
        chatId = (lastMsg.message && lastMsg.message.chat.id) || null;
        if (chatId) break;
      }
    } catch (e) {
      // 재시도
    }
    if (attempt < 2) {
      console.log('  감지 대기 중... (재시도)');
      await new Promise((r) => setTimeout(r, 2000));
    }
  }

  if (!chatId) {
    console.log('  [주의] 자동 감지 실패. 수동 입력해주세요.');
    const manual = await ask('  Chat ID 입력: ');
    chatId = manual.trim();
  } else {
    console.log(`  [확인] Chat ID: ${chatId}`);
  }

  // Step 4: .env 파일 생성
  console.log('');
  console.log('[ Step 3 ] 설정 파일 저장');

  let envContent = '';
  if (fs.existsSync(ENV_PATH)) {
    envContent = fs.readFileSync(ENV_PATH, 'utf-8');
    // 기존 값 교체
    envContent = envContent.replace(/TELEGRAM_BOT_TOKEN=.*/, `TELEGRAM_BOT_TOKEN=${token}`);
    envContent = envContent.replace(/TELEGRAM_CHAT_ID=.*/, `TELEGRAM_CHAT_ID=${chatId}`);
    if (!envContent.includes('TELEGRAM_BOT_TOKEN')) {
      envContent += `\nTELEGRAM_BOT_TOKEN=${token}`;
    }
    if (!envContent.includes('TELEGRAM_CHAT_ID')) {
      envContent += `\nTELEGRAM_CHAT_ID=${chatId}`;
    }
  } else {
    envContent = [
      `TELEGRAM_BOT_TOKEN=${token}`,
      `TELEGRAM_CHAT_ID=${chatId}`,
      `PORT=3847`,
      `APPROVAL_TIMEOUT=300`,
      `AUTO_APPROVE_ENABLED=false`,
      `EXTERNAL_URL=`,
    ].join('\n');
  }

  fs.writeFileSync(ENV_PATH, envContent);
  console.log(`  [확인] .env 저장 완료`);

  // Step 5: 테스트 메시지
  console.log('');
  console.log('[ Step 4 ] 테스트 메시지 전송');

  try {
    const result = await telegramApi(token, 'sendMessage', {
      chat_id: chatId,
      text:
        '✅ *Claude Code Mobile Approver*\n\n' +
        '봇 연결 성공!\n\n' +
        'Claude Code에서 승인 요청이 오면\n' +
        '이 채팅으로 알림이 옵니다.\n\n' +
        '`npm start` 로 서버를 시작하세요.',
      parse_mode: 'Markdown',
    });

    if (result.ok) {
      console.log('  [확인] 테스트 메시지 전송 성공! Telegram을 확인하세요.');
    } else {
      console.log(`  [주의] 전송 실패: ${result.description}`);
    }
  } catch (e) {
    console.log(`  [주의] 전송 실패: ${e.message}`);
  }

  // 완료
  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║   셋업 완료!                                 ║');
  console.log('╠══════════════════════════════════════════════╣');
  console.log('║                                              ║');
  console.log('║   다음 단계:                                 ║');
  console.log('║   1. npm start        (서버 시작)            ║');
  console.log('║   2. npm run hook:install (훅 설치)          ║');
  console.log('║                                              ║');
  console.log('║   Telegram 명령어:                           ║');
  console.log('║   /pending    - 대기 중인 승인 목록          ║');
  console.log('║   /approveall - 모두 승인                    ║');
  console.log('║   /history    - 처리 내역                    ║');
  console.log('║   /status     - 서버 상태                    ║');
  console.log('╚══════════════════════════════════════════════╝');
  console.log('');

  rl.close();
}

main().catch((e) => {
  console.error('오류:', e.message);
  rl.close();
  process.exit(1);
});
