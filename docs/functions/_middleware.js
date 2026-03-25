// Cloudflare Access JWT verification + section-level email access control

import accessConfig from '../_access-config.json';

function getEmailFromJWT(request) {
  const jwt = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!jwt) return null;

  try {
    const parts = jwt.split('.');
    if (parts.length !== 3) return null;

    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));

    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }

    return payload.email || null;
  } catch (e) {
    return null;
  }
}

function getSectionPath(pathname) {
  // Match /sellout/ or /sellout or /price/ or /price
  if (pathname.startsWith('/sellout')) return '/sellout/';
  if (pathname.startsWith('/price')) return '/price/';
  return '/';
}

function isEmailAllowed(email, sectionPath) {
  const section = accessConfig.sections[sectionPath];
  if (!section) return false;

  // If email list is empty, allow all authenticated users (not yet configured)
  if (section.emails.length === 0) return true;

  return section.emails.includes(email.toLowerCase());
}

export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);

  // Allow Cloudflare internal paths
  if (url.pathname.startsWith('/cdn-cgi/')) {
    return next();
  }

  // Allow static assets
  if (url.pathname.match(/\.(css|js|png|jpg|svg|ico|json)$/)) {
    return next();
  }

  const email = getEmailFromJWT(request);

  // No JWT = not authenticated (Cloudflare Access will handle redirect)
  if (!email) {
    return next();
  }

  const sectionPath = getSectionPath(url.pathname);

  if (!isEmailAllowed(email, sectionPath)) {
    return new Response(
      `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Access Denied</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; background: #0f0f1a; color: #eee; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .box { text-align: center; padding: 40px; background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; max-width: 400px; }
    h1 { color: #e94560; font-size: 20px; margin-bottom: 12px; }
    p { color: #8888aa; font-size: 14px; line-height: 1.6; }
    a { color: #e94560; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="box">
    <h1>Access Denied</h1>
    <p>${email} does not have permission to access this section.</p>
    <p style="margin-top:16px"><a href="/">Back to Home</a> · <a href="/cdn-cgi/access/logout">Logout</a></p>
  </div>
</body>
</html>`,
      {
        status: 403,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      }
    );
  }

  // Allowed - pass through with user info header
  const response = await next();
  const newResponse = new Response(response.body, response);
  newResponse.headers.set('X-Auth-User', email);
  return newResponse;
}
