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

// API 키 인증 미들웨어
const API_KEY = process.env.API_KEY || '';
function authMiddleware(req, res, next) {
  if (!API_KEY) return next(); // 키 미설정 시 인증 건너뛰기
  const key = req.headers['x-api-key'] || req.query.api_key;
  if (key !== API_KEY) {
    return res.status(401).json({ error: '인증 실패: 유효한 API 키가 필요합니다' });
  }
  next();
}

// 미들웨어
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// 서비스를 라우터에 주입
app.locals.approvalManager = approvalManager;
app.locals.autoApprover = autoApprover;
app.locals.telegramNotifier = telegramNotifier;

// API 라우트 (인증 적용)
app.use('/api', authMiddleware, apiRoutes);

// SPA 폴백
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// WebSocket 연결 관리
const wsClients = new Set();

wss.on('connection', (ws, req) => {
  // WebSocket 인증 (API 키 설정 시)
  if (API_KEY) {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const key = url.searchParams.get('api_key');
    if (key !== API_KEY) {
      ws.close(4001, '인증 실패');
      return;
    }
  }

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
      // 입력 검증: id가 문자열이어야 함
      if (!msg.id || typeof msg.id !== 'string') return;
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

// WebSocket 브로드캐스트
function broadcast(msg) {
  const payload = JSON.stringify(msg);
  for (const client of wsClients) {
    if (client.readyState === 1) {
      client.send(payload);
    }
  }
}

approvalManager.on('resolved', (approval) => {
  broadcast({ type: 'approval_resolved', data: approval });
});

// 새 승인 요청: WebSocket 브로드캐스트 + 텔레그램 알림
// 자동 승인은 api.js에서 사전 체크하므로 여기서는 중복 체크하지 않음
approvalManager.on('new', async (approval) => {
  // WebSocket 클라이언트에 브로드캐스트
  broadcast({ type: 'new_approval', data: approval });

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
  const portStr = String(PORT);
  const localUrl = `http://localhost:${PORT}`;
  const apiUrl = `http://localhost:${PORT}/api`;
  const pad = (str, len) => str + ' '.repeat(Math.max(0, len - str.length));

  console.log('');
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║   Claude Code Mobile Approver v1.0          ║');
  console.log('╠══════════════════════════════════════════════╣');
  console.log(`║   ${pad('로컬:  ' + localUrl, 43)}║`);
  console.log(`║   ${pad('API:   ' + apiUrl, 43)}║`);
  console.log('║                                              ║');
  if (telegramNotifier) {
    console.log('║   ✓ Telegram 알림 활성화                     ║');
  } else {
    console.log('║   ✗ Telegram 미설정 (.env 확인)              ║');
  }
  if (API_KEY) {
    console.log('║   ✓ API 키 인증 활성화                       ║');
  }
  console.log('╚══════════════════════════════════════════════╝');
  console.log('');
});

// Graceful shutdown
function shutdown(signal) {
  console.log(`\n[Server] ${signal} 수신 - 종료 중...`);

  // 대기 중인 승인 요청 전부 타임아웃 처리
  const pending = approvalManager.getPending();
  for (const p of pending) {
    approvalManager.resolve(p.id, 'timeout');
  }

  // WebSocket 연결 종료
  for (const client of wsClients) {
    client.close(1001, '서버 종료');
  }

  // Telegram 폴링 중지
  if (telegramNotifier && telegramNotifier.bot) {
    telegramNotifier.bot.stopPolling();
  }

  server.close(() => {
    console.log('[Server] 정상 종료');
    process.exit(0);
  });

  // 5초 후 강제 종료
  setTimeout(() => {
    console.error('[Server] 강제 종료');
    process.exit(1);
  }, 5000);
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
