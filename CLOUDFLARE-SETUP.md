# Cloudflare Pages + Access 설정 가이드

## 구조

```
URL: shaker-dashboard.pages.dev
├── /                → Management Dashboard (경영진 이메일만)
├── /sellout/        → Sell out Dashboard (제한된 인원)
├── /price/          → Price Tracking (제한된 인원)
```

접근 제어: Cloudflare Access (인증) + Pages Functions 미들웨어 (섹션별 이메일 체크)

---

## 1단계: GitHub Secrets 설정

GitHub 리포지토리 Settings > Secrets and variables > Actions:
- `CLOUDFLARE_API_TOKEN`: Cloudflare API 토큰
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare 계정 ID

### API 토큰 생성
1. [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens) > Create Token > Custom token
2. 권한: `Account / Cloudflare Pages / Edit`
3. 토큰 복사 후 GitHub Secret에 저장

### Account ID 확인
Cloudflare Dashboard 우측 하단 또는 URL에서 확인 가능

---

## 2단계: 첫 배포

```bash
npx wrangler pages project create shaker-dashboard --production-branch=main
npx wrangler pages deploy docs --project-name=shaker-dashboard
```

배포 후 접속: `https://shaker-dashboard.pages.dev`

---

## 3단계: Cloudflare Access 설정

[Cloudflare Zero Trust](https://one.dash.cloudflare.com/) 접속

### 3-1. 인증 방법 설정
Settings > Authentication > Login methods > **One-time PIN** 활성화

### 3-2. Access Application 생성 (3개)

**Access > Applications > Add an application > Self-hosted**

| Application name | Application domain | Path |
|---|---|---|
| Dashboard - Management | `shaker-dashboard.pages.dev` | `/` |
| Dashboard - Sell out | `shaker-dashboard.pages.dev` | `/sellout` |
| Dashboard - Price Tracking | `shaker-dashboard.pages.dev` | `/price` |

각 Application마다 Policy 추가:
- **Policy name**: Allowed Users
- **Action**: Allow
- **Include**: Emails → 허용할 이메일 주소 입력

---

## 4단계: 이메일 목록 관리

### Cloudflare Access 정책 (1차 방어 - 서버)
Zero Trust 대시보드에서 각 Application의 Policy에 이메일 추가/삭제

### _access-config.json (2차 방어 - 미들웨어)
`docs/_access-config.json` 파일에서 섹션별 이메일 관리:

```json
{
  "sections": {
    "/": {
      "name": "Management Dashboard",
      "emails": ["exec1@company.com", "exec2@company.com"]
    },
    "/sellout/": {
      "name": "Sell out Dashboard",
      "emails": ["user1@company.com", "user2@company.com"]
    },
    "/price/": {
      "name": "Price Tracking",
      "emails": ["user3@company.com", "user4@company.com"]
    }
  }
}
```

> emails가 빈 배열 `[]`이면 인증된 모든 사용자 허용 (초기 상태)

파일 수정 후 `main`에 push하면 자동 배포됩니다.

---

## 동작 흐름

1. 사용자가 `shaker-dashboard.pages.dev/sellout/` 접속
2. Cloudflare Access가 인증 확인 → 미인증 시 이메일 OTP 로그인 페이지
3. 인증 후 `_middleware.js`가 JWT에서 이메일 추출
4. `_access-config.json`의 해당 섹션 이메일 목록과 대조
5. 허용 → 대시보드 표시 / 미허용 → 403 Access Denied 페이지
