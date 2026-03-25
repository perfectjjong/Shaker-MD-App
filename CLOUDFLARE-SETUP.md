# Cloudflare Pages + Access 설정 가이드

## 1. Cloudflare Pages 프로젝트 생성

### GitHub Secrets 설정
GitHub 리포지토리의 Settings > Secrets and variables > Actions에 추가:
- `CLOUDFLARE_API_TOKEN`: Cloudflare API 토큰 (Pages 배포 권한 필요)
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare 계정 ID

### API 토큰 생성
1. [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens) 접속
2. **Create Token** > **Custom token**
3. 권한 설정:
   - `Account / Cloudflare Pages / Edit`
   - `Account / Account Settings / Read`
4. 토큰 생성 후 GitHub Secret에 저장

### 수동 배포 (첫 배포)
```bash
npx wrangler pages project create shaker-md-dashboard --production-branch=main
npx wrangler pages deploy docs --project-name=shaker-md-dashboard
```

배포 후 `https://shaker-md-dashboard.pages.dev`에서 접근 가능합니다.

---

## 2. 커스텀 도메인 연결 (선택사항)

1. Cloudflare Dashboard > Pages > 프로젝트 선택
2. **Custom domains** 탭 > **Set up a custom domain**
3. 도메인 입력 (예: `dashboard.yourdomain.com`)
4. DNS 레코드 자동 추가 확인

---

## 3. Cloudflare Access 설정 (접속 권한 관리)

### Zero Trust 대시보드 접속
1. [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) 접속
2. 왼쪽 메뉴 **Access** > **Applications**

### Application 생성
1. **Add an application** 클릭
2. **Self-hosted** 선택
3. 설정:
   - **Application name**: `Dashboard Hub`
   - **Session Duration**: 24시간 (권장)
   - **Application domain**: `shaker-md-dashboard.pages.dev` (또는 커스텀 도메인)

### Access Policy 설정
허용할 사용자를 정의합니다:

#### 이메일 기반 접근 제어
- **Policy name**: `Allowed Users`
- **Action**: Allow
- **Include rule**: Emails
  - 허용할 이메일 주소 추가 (예: `user@company.com`)

#### 이메일 도메인 기반 접근 제어
- **Include rule**: Emails ending in
  - 회사 도메인 입력 (예: `@company.com`)

#### One-time PIN (OTP) 인증
- **Authentication** 탭에서 **One-time PIN** 활성화
- 사용자가 이메일로 받은 PIN을 입력하여 로그인

### 인증 방법 옵션
- **One-time PIN**: 이메일 인증 (가장 간단)
- **Google**: Google 계정 로그인
- **GitHub**: GitHub 계정 로그인
- **SAML/OIDC**: 기업 SSO 연동

---

## 4. 배포 구조

```
docs/
├── index.html          # 메인 대시보드 (Cloudflare Access 연동 UI 포함)
├── _headers            # 보안 헤더
├── _redirects          # URL 리다이렉트 규칙
└── functions/
    └── _middleware.js   # Access JWT 검증 미들웨어
```

### 동작 방식
1. 사용자가 대시보드 URL에 접속
2. Cloudflare Access가 인증 여부 확인
3. 미인증 시 → Cloudflare 로그인 페이지로 리다이렉트
4. 인증 완료 → `CF_Authorization` JWT 쿠키 발급
5. 대시보드 로드 시 JWT에서 이메일 추출하여 상단에 표시
6. 로그아웃: `/cdn-cgi/access/logout` 경로로 세션 종료

---

## 5. GitHub Actions 자동 배포

`main` 브랜치의 `docs/` 디렉토리가 변경되면 자동 배포됩니다.
수동 배포는 GitHub Actions 탭에서 **Run workflow** 버튼으로 실행 가능합니다.

---

## 요약

| 항목 | 설명 |
|------|------|
| 호스팅 | Cloudflare Pages (`shaker-md-dashboard.pages.dev`) |
| 인증 | Cloudflare Access (Zero Trust) |
| 배포 | GitHub Actions → Wrangler CLI |
| 접근 제어 | 이메일/도메인/SSO 기반 정책 |
| 로그아웃 | `/cdn-cgi/access/logout` |
