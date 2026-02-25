require('dotenv').config();
const http = require('http');
const express = require('express');
const { WebSocketServer } = require('ws');
const path = require('path');
const { ApprovalManager } = require('./services/approval-manager');
const { TelegramNotifier } = require('./services/telegram-notifier');
const { AutoApprover } = require('./services/auto-approver');
const apiRoutes = require('./routes/api');

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

// 서비스 초기화
const approvalManager = new ApprovalManager();
const autoApprover = new AutoApprover();
let telegramNotifier = null;

if (process.env.TELEGRAM_BOT_TOKEN && process.env.TELEGRAM_CHAT_ID) {
  telegramNotifier = new TelegramNotifier(
    process.env.TELEGRAM_BOT_TOKEN,
    process.env.TELEGRAM_CHAT_ID,
    approvalManager
  );
  console.log('[Telegram] 봇 연결됨');
} else {
  console.log('[Telegram] 토큰 미설정 - 웹 대시보드만 사용 가능');
}

// 미들웨어
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// 서비스를 라우터에 주입
app.locals.approvalManager = approvalManager;
app.locals.autoApprover = autoApprover;
app.locals.telegramNotifier = telegramNotifier;

// API 라우트
app.use('/api', apiRoutes);

// SPA 폴백
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// WebSocket 연결 관리
const wsClients = new Set();

wss.on('connection', (ws) => {
  wsClients.add(ws);
  console.log(`[WS] 클라이언트 연결 (총 ${wsClients.size}명)`);

  // 연결 시 대기 중인 승인 목록 전송
  const pending = approvalManager.getPending();
  ws.send(JSON.stringify({ type: 'pending_list', data: pending }));

  ws.on('close', () => {
    wsClients.delete(ws);
    console.log(`[WS] 클라이언트 연결 해제 (총 ${wsClients.size}명)`);
  });

  ws.on('message', (raw) => {
    try {
      const msg = JSON.parse(raw);
      if (msg.type === 'approve') {
        approvalManager.resolve(msg.id, 'approved');
      } else if (msg.type === 'reject') {
        approvalManager.resolve(msg.id, 'rejected');
      }
    } catch (e) {
      console.error('[WS] 메시지 파싱 오류:', e.message);
    }
  });
});

// 승인 이벤트를 WebSocket 클라이언트에 브로드캐스트
approvalManager.on('new', (approval) => {
  broadcast({ type: 'new_approval', data: approval });
});

approvalManager.on('resolved', (approval) => {
  broadcast({ type: 'approval_resolved', data: approval });
});

function broadcast(msg) {
  const payload = JSON.stringify(msg);
  for (const client of wsClients) {
    if (client.readyState === 1) {
      client.send(payload);
    }
  }
}

// 새 승인 요청 시 자동 승인 체크 + 텔레그램 알림
approvalManager.on('new', async (approval) => {
  // 자동 승인 규칙 체크
  if (autoApprover.shouldAutoApprove(approval)) {
    console.log(`[AutoApprove] 자동 승인: ${approval.command}`);
    approvalManager.resolve(approval.id, 'approved');
    return;
  }

  // 텔레그램 알림
  if (telegramNotifier) {
    try {
      await telegramNotifier.sendApprovalRequest(approval);
    } catch (e) {
      console.error('[Telegram] 알림 전송 실패:', e.message);
    }
  }
});

const PORT = process.env.PORT || 3847;
server.listen(PORT, '0.0.0.0', () => {
  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║   Claude Code Mobile Approver v1.0          ║');
  console.log('╠══════════════════════════════════════════════╣');
  console.log(`║   로컬:  http://localhost:${PORT}              ║`);
  console.log(`║   API:   http://localhost:${PORT}/api           ║`);
  console.log('║                                              ║');
  if (telegramNotifier) {
    console.log('║   ✓ Telegram 알림 활성화                     ║');
  } else {
    console.log('║   ✗ Telegram 미설정 (.env 확인)              ║');
  }
  console.log('╚══════════════════════════════════════════════╝');
  console.log('');
});
