// Reverse proxy for the Netlify-hosted Flooring dashboard.
//
// Why: the Flooring site is protected by HTTP Basic Auth. We want the portal
// link to open with zero manual login, WITHOUT ever exposing the credential in
// public source (this repo + the pages.dev HTML are both public).
//
// How: this Pages Function proxies every request under /flooring/* to the
// upstream Netlify site, injecting the Basic Auth header from an encrypted
// Cloudflare secret. The credential lives ONLY in the Cloudflare dashboard.
//
// Required secret (Cloudflare Pages > Settings > Environment variables, encrypted):
//   FLOORING_AUTH_B64 = base64("<user>:<password>")
//
// All Flooring assets/data use relative paths (style.css, app.js, data/*.json),
// so serving under /flooring/ resolves everything back through this proxy.

const UPSTREAM = 'https://shaker-flooring-dashboard-673.netlify.app';

export async function onRequest(context) {
  const { request, env, params } = context;

  const authB64 = env.FLOORING_AUTH_B64;
  if (!authB64) {
    return new Response(
      'Flooring proxy is not configured yet: set the FLOORING_AUTH_B64 secret in Cloudflare Pages settings.',
      { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } }
    );
  }

  const url = new URL(request.url);

  // /flooring (no trailing slash) -> redirect so relative assets resolve under /flooring/
  if (url.pathname === '/flooring') {
    return Response.redirect(url.origin + '/flooring/', 301);
  }

  // Catch-all segments after /flooring/
  const rest = Array.isArray(params.path) ? params.path.join('/') : (params.path || '');
  const upstreamUrl = UPSTREAM + '/' + rest + url.search;

  const headers = new Headers(request.headers);
  headers.set('Authorization', 'Basic ' + authB64);
  headers.delete('host');
  headers.delete('cf-access-jwt-assertion');

  const upstreamReq = new Request(upstreamUrl, {
    method: request.method,
    headers,
    body: (request.method === 'GET' || request.method === 'HEAD') ? undefined : request.body,
    redirect: 'manual',
  });

  const resp = await fetch(upstreamReq);

  // Clean response headers: drop the auth challenge, upstream CSP, and
  // encoding/length headers that the platform will recompute.
  const outHeaders = new Headers(resp.headers);
  outHeaders.delete('www-authenticate');
  outHeaders.delete('content-security-policy');
  outHeaders.delete('content-encoding');
  outHeaders.delete('content-length');
  outHeaders.delete('transfer-encoding');

  // Rewrite any redirect that points back to the upstream host onto /flooring
  const loc = outHeaders.get('location');
  if (loc && loc.startsWith(UPSTREAM)) {
    outHeaders.set('location', '/flooring' + loc.slice(UPSTREAM.length));
  }

  return new Response(resp.body, {
    status: resp.status,
    statusText: resp.statusText,
    headers: outHeaders,
  });
}
