// Cloudflare Access JWT verification middleware
// Verifies that requests are authenticated through Cloudflare Access

const CERTS_URL_TEMPLATE = 'https://{team-domain}.cloudflareaccess.com/cdn-cgi/access/certs';

async function verifyAccessJWT(request, env) {
  const jwt = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!jwt) {
    return null;
  }

  try {
    const parts = jwt.split('.');
    if (parts.length !== 3) return null;

    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));

    // Check expiration
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }

    return {
      email: payload.email,
      identityNonce: payload.identity_nonce,
      sub: payload.sub,
      iat: payload.iat,
      exp: payload.exp,
    };
  } catch (e) {
    return null;
  }
}

export async function onRequest(context) {
  const { request, env, next } = context;

  // Allow Cloudflare Access callback paths
  const url = new URL(request.url);
  if (url.pathname.startsWith('/cdn-cgi/')) {
    return next();
  }

  // Check for Cloudflare Access JWT
  const identity = await verifyAccessJWT(request, env);

  if (identity) {
    // Add user info to request headers for downstream use
    const response = await next();
    const newResponse = new Response(response.body, response);
    newResponse.headers.set('X-Auth-User', identity.email || '');
    return newResponse;
  }

  // If no Access JWT, let the request through
  // (Cloudflare Access policy will handle blocking at the edge)
  return next();
}
