---
description: Claude Code 원격 승인 시스템 개발 가이드라인. Node.js/Express + WebSocket + Telegram 기반 모바일 승인 시스템의 구조와 패턴을 가이드합니다.
triggers:
  keywords: [approval, 승인, websocket, telegram, hook, executor, commander, auto-approve, push, tunnel]
  file_paths: ["src/**/*.js", "scripts/*.js"]
type: domain
enforcement: suggest
---

# Claude Code Mobile Approver 가이드라인

## 아키텍처

```
Claude Code Hook → WebSocket → Server → Telegram 알림 → 모바일 승인/거부
                                ↓
                        Express API + WebSocket 대시보드
```

## 서비스 구조

| 서비스 | 파일 | 역할 |
|--------|------|------|
| ApprovalManager | `approval-manager.js` | 승인 요청 관리 (생성, 상태 추적) |
| AutoApprover | `auto-approver.js` | 자동 승인 규칙 |
| TaskAutoApprover | `task-auto-approver.js` | 태스크 자동 승인 |
| TaskManager | `task-manager.js` | 태스크 큐 관리 |
| TelegramNotifier | `telegram-notifier.js` | 텔레그램 알림 전송 |
| PushNotifier | `push-notifier.js` | Web Push 알림 |
| TunnelService | `tunnel-service.js` | localtunnel 관리 |
| RiskAssessor | `risk-assessor.js` | 명령어 위험도 평가 |

## WebSocket 경로

| 경로 | 용도 |
|------|------|
| `/ws` | 대시보드 실시간 업데이트 |
| `/ws/executor` | Claude Code executor 연결 |
| `/ws/commander` | Commander 연결 |

## 보안 규칙

1. **봇 토큰, Push VAPID 키는 `.env`에서만 관리**
2. **RiskAssessor로 명령어 위험도 평가 후 자동/수동 승인 결정**
3. **WebSocket 연결 인증 확인**

## 코드 패턴

```javascript
// ✅ 환경변수 로드
require('dotenv').config();
const token = process.env.TELEGRAM_BOT_TOKEN;

// ✅ 서비스 의존성 주입
const taskManager = new TaskManager(taskAutoApprover);

// ✅ WebSocket noServer 모드
const wss = new WebSocketServer({ noServer: true });
server.on('upgrade', (req, socket, head) => {
    // 경로별 라우팅
});
```
