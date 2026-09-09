// Cloudflare Access JWT 검증 + 대시보드 단위 접근 제어
//
// 자원 키 규칙 (scripts/build_access_groups.py 의 resource_of() 와 동일 — 바꾸면 양쪽 같이 고칠 것)
//   /dashboards/<key>/...  -> "dash:<key>"
//   /gtm-weekly|/gtm|/psi|/mega-promo|/reports/... -> "sec:<name>"
//   그 외(허브·전역 자산)  -> null (인증만 통과하면 열람)

import cfg from './access-config.json';
import cards from './cards.json';

const SECTIONS = ['gtm-weekly', 'gtm', 'psi', 'mega-promo', 'reports'];

// 서브 허브 페이지 — 카드가 비어도 페이지 제목으로 존재가 드러나므로 그룹 보유자만 연다
const HUB_ACL = { '/ir/': 'ir', '/or/': 'or', '/price/': 'price' };

function decodeJWT(jwt) {
  try {
    const parts = jwt.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload.email || null;
  } catch (e) {
    return null;
  }
}

// Access 토큰은 헤더로 오기도, CF_Authorization 쿠키로 오기도 한다.
// 헤더만 보면 못 받는 경우가 있고, 그러면 email 이 null 이라 접근 제어가 통째로 무력화된다.
function getEmail(request) {
  const hdr = request.headers.get('Cf-Access-Jwt-Assertion');
  if (hdr) {
    const e = decodeJWT(hdr);
    if (e) return { email: e, via: 'header' };
  }
  const cookie = request.headers.get('Cookie') || '';
  const m = cookie.match(/(?:^|;\s*)CF_Authorization=([^;]+)/);
  if (m) {
    const e = decodeJWT(m[1]);
    if (e) return { email: e, via: 'cookie' };
  }
  return { email: null, via: null };
}

export function resourceOf(pathname) {
  if (pathname.startsWith('/dashboards/')) {
    const key = pathname.split('/')[2];
    return key ? 'dash:' + key : null;
  }
  for (const s of SECTIONS) {
    if (pathname === '/' + s || pathname.startsWith('/' + s + '/')) return 'sec:' + s;
  }
  return null;
}

// 사용자가 가진 권한 그룹 이름 Set ('*' = superuser)
export function groupsFor(email) {
  const e = (email || '').toLowerCase();
  if ((cfg.superusers || []).some((s) => s.toLowerCase() === e)) return '*';
  const u = (cfg.users || {})[e] || cfg.default || { groups: [] };
  return new Set(u.groups || []);
}

// '*' = 전체 허용(superuser), 그 외에는 허용 자원 Set
export function allowedFor(email) {
  const e = (email || '').toLowerCase();
  if ((cfg.superusers || []).some((s) => s.toLowerCase() === e)) return '*';
  const u = (cfg.users || {})[e] || cfg.default || { groups: [], resources: [] };
  const set = new Set(u.resources || []);
  for (const g of u.groups || []) for (const r of (cfg.groups || {})[g] || []) set.add(r);
  return set;
}

function denyPage(email, pathname) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Access Denied</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; background: #0f0f1a; color: #eee; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .box { text-align: center; padding: 40px; background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; max-width: 420px; }
    h1 { color: #e94560; font-size: 20px; margin-bottom: 12px; }
    p { color: #8888aa; font-size: 14px; line-height: 1.6; }
    code { color: #aaa; font-size: 12px; }
    a { color: #e94560; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="box">
    <h1>Access Denied</h1>
    <p>${email} does not have permission to view this dashboard.</p>
    <p><code>${pathname}</code></p>
    <p style="margin-top:16px"><a href="/">Back to Home</a> &middot; <a href="/cdn-cgi/access/logout">Logout</a></p>
  </div>
</body>
</html>`;
}

export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);

  if (url.pathname.startsWith('/cdn-cgi/')) return next();

  // 설정·카드 정의 보호. Pages 는 functions/ 를 정적 자산으로 올리지 않지만,
  // 그 전제가 깨지면 권한 매트릭스와 전체 카드 목록이 통째로 노출된다.
  if (url.pathname === '/functions' || url.pathname.startsWith('/functions/')) {
    return new Response('Not found', { status: 404 });
  }

  const { email, via } = getEmail(request);

  // API 는 미인증이어도 정적 404 로 흘리지 않는다 — 조용히 실패하면 원인을 못 찾는다
  if (!email && (url.pathname === '/api/cards' || url.pathname === '/api/me')) {
    return new Response(
      JSON.stringify({ error: 'unauthenticated', detail: 'Access token not found in header or cookie' }),
      { status: 401, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } }
    );
  }
  if (!email) return next(); // 미인증 — Cloudflare Access 가 리다이렉트 처리

  // 보호 대상이 아닌 경로(허브·전역 자산)는 통과.
  // 자산 확장자 일괄 통과는 두지 않는다 — data_ir.js 같은 데이터 파일이 그대로 새어나감.
  const allowed = allowedFor(email);

  // 허브 카드 — 권한에 맞는 것만 만들어 내려보낸다.
  // 카드 정의를 HTML 에 두면 권한 없는 항목도 소스 보기로 노출되므로 서버에서 걸러야 한다.
  if (url.pathname === '/api/cards') {
    const hub = url.searchParams.get('hub') || 'main';
    const myGroups = groupsFor(email);
    const visible = ((cards.hubs || {})[hub] || [])
      // 카드 묶음의 노출 여부는 '그룹 보유'로 판단한다.
      // 자원 기준으로 보면 그룹끼리 겹쳐(price ⊆ or∪ir) 안 줘야 할 묶음이 되살아난다.
      .filter((g) => myGroups === '*' || myGroups.has(g.acl))
      .map((g) => ({
        ...g,
        children: g.children.filter((c) => {
          if (allowed === '*') return true;
          // 여기까지 온 카드는 보유 그룹 소속. 외부 링크는 URL 로 통제 불가하므로 그대로 노출
          if (!c.url.startsWith('/')) return true;
          const r = resourceOf(c.url);
          return r === null || allowed.has(r);
        }),
      }))
      .filter((g) => g.children.length > 0);
    // 내비도 같이 내려보낸다 — HTML 에 두면 권한 없는 메뉴명이 소스에 남는다
    const nav = (cards.nav || []).filter(
      (n) => n.acl === null || myGroups === '*' || myGroups.has(n.acl)
    );
    return new Response(JSON.stringify({ nav, groups: visible }), {
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    });
  }

  // 허브 카드 필터링용 — 자기 권한 조회
  if (url.pathname === '/api/me') {
    return new Response(
      JSON.stringify({
        email,
        via,
        superuser: allowed === '*',
        resources: allowed === '*' ? '*' : [...allowed].sort(),
      }),
      { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } }
    );
  }

  const hubAcl = HUB_ACL[url.pathname] || HUB_ACL[url.pathname + '/'];
  if (hubAcl && allowed !== '*' && !groupsFor(email).has(hubAcl)) {
    return new Response(denyPage(email, url.pathname), {
      status: 403,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }

  const resource = resourceOf(url.pathname);
  if (resource !== null && allowed !== '*' && !allowed.has(resource)) {
    return new Response(denyPage(email, url.pathname), {
      status: 403,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }

  const response = await next();
  const newResponse = new Response(response.body, response);
  newResponse.headers.set('X-Auth-User', email);
  return newResponse;
}
