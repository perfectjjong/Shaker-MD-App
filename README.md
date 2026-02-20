# Claude Code Mobile Approver

Claude Code의 도구 실행 승인 요청을 모바일에서 원격으로 처리할 수 있는 시스템입니다.

## 기능

- **모바일 웹 대시보드**: 폰 브라우저에서 승인/거부 (PWA 지원)
- **Telegram Bot 알림**: 실시간 알림 + 인라인 버튼으로 즉시 승인
- **자동 승인 규칙**: 패턴 기반 자동 승인/거부 (read-only 명령어 자동 허용 등)
- **실시간 WebSocket**: 승인 요청 즉시 알림
- **히스토리**: 과거 승인/거부 기록 확인

## 구조

```
├── src/
│   ├── server.js                 # Express + WebSocket 서버
│   ├── services/
│   │   ├── approval-manager.js   # 승인 요청 관리
│   │   ├── telegram-notifier.js  # Telegram 알림
│   │   └── auto-approver.js      # 자동 승인 규칙
│   ├── routes/
│   │   └── api.js                # REST API
│   └── public/
│       └── index.html            # 모바일 웹 대시보드
├── scripts/
│   ├── claude-code-hook.js       # Claude Code 연동 훅 (Node.js)
│   ├── claude-code-hook.sh       # Claude Code 연동 훅 (Bash)
│   └── install-hook.js           # 훅 자동 설치
└── config/
    └── auto-approve-rules.json   # 자동 승인 규칙 (자동 생성)
```

## 빠른 시작

### 1. 설치

```bash
npm install
```

### 2. 환경 설정

```bash
cp .env.example .env
# .env 파일을 편집하여 설정
```

### 3. 서버 실행

```bash
npm start
```

### 4. Claude Code 훅 설치

```bash
npm run hook:install
```

또는 수동으로 Claude Code `settings.json`에 추가:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "node /절대경로/scripts/claude-code-hook.js"
          }
        ]
      }
    ]
  }
}
```

## Telegram Bot 설정

1. Telegram에서 [@BotFather](https://t.me/BotFather)에게 `/newbot` 명령 전송
2. 봇 이름과 username 설정
3. 받은 토큰을 `.env`의 `TELEGRAM_BOT_TOKEN`에 입력
4. 생성된 봇에게 `/start` 메시지 전송
5. 봇이 응답하는 Chat ID를 `.env`의 `TELEGRAM_CHAT_ID`에 입력

### Telegram 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 시작 및 Chat ID 확인 |
| `/pending` | 대기 중인 승인 목록 |
| `/history` | 최근 처리 내역 |
| `/approveall` | 대기 중인 모든 요청 승인 |
| `/status` | 서버 상태 확인 |

## 모바일 웹 대시보드

서버 실행 후 `http://PC의IP:3847` 접속

- **대기 중**: 현재 대기 중인 승인 요청 목록, 개별/일괄 승인 가능
- **히스토리**: 최근 승인/거부 내역
- **자동 규칙**: 자동 승인/거부 규칙 관리

### PWA로 설치

모바일 브라우저에서 접속 후 "홈 화면에 추가"하면 앱처럼 사용 가능

## 자동 승인 규칙

`.env`에서 `AUTO_APPROVE_ENABLED=true` 설정 또는 웹 대시보드에서 활성화

기본 규칙:
- **Read-only 명령어**: `ls`, `cat`, `git status` 등 자동 승인
- **npm 읽기 명령어**: `npm list`, `yarn info` 등 자동 승인
- **위험 명령어**: `rm -rf /`, `sudo rm` 등 자동 거부

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/approval` | 승인 요청 생성 (훅에서 호출) |
| GET | `/api/pending` | 대기 중 목록 |
| POST | `/api/approve/:id` | 개별 승인 |
| POST | `/api/reject/:id` | 개별 거부 |
| POST | `/api/approve-all` | 모두 승인 |
| GET | `/api/history` | 처리 내역 |
| GET | `/api/rules` | 규칙 조회 |
| PUT | `/api/rules` | 규칙 업데이트 |

## 외부 접속 (ngrok)

로컬 네트워크 외부에서 접속하려면:

```bash
ngrok http 3847
```

ngrok URL을 `.env`의 `EXTERNAL_URL`에 설정하면 Telegram 알림에 대시보드 링크 포함
