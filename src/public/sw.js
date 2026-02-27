const CACHE_NAME = 'claude-approver-v1';

// 푸시 알림 수신
self.addEventListener('push', (event) => {
  if (!event.data) return;

  const payload = event.data.json();

  const options = {
    body: payload.body,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    vibrate: [200, 100, 200],
    tag: payload.id || 'default',
    renotify: true,
    requireInteraction: true, // 사용자가 직접 닫을 때까지 유지
    data: payload.data || payload,
  };

  // 승인 요청일 때 액션 버튼 추가
  if (payload.type === 'approval_request') {
    options.actions = [
      { action: 'approve', title: '✅ 승인' },
      { action: 'reject', title: '❌ 거부' },
    ];
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, options)
  );
});

// 알림 클릭 처리
self.addEventListener('notificationclick', (event) => {
  const notification = event.notification;
  const data = notification.data;
  const action = event.action;

  notification.close();

  if (action === 'approve' || action === 'reject') {
    // 액션 버튼 클릭 → API 호출로 바로 처리
    const approvalId = data.id;
    const endpoint = action === 'approve' ? `/api/approve/${approvalId}` : `/api/reject/${approvalId}`;

    event.waitUntil(
      fetch(endpoint, { method: 'POST' })
        .then((res) => res.json())
        .then((result) => {
          const emoji = action === 'approve' ? '✅' : '❌';
          const label = action === 'approve' ? '승인됨' : '거부됨';
          return self.registration.showNotification(`${emoji} ${label}`, {
            body: data.command ? data.command.slice(0, 80) : '',
            icon: '/icon-192.png',
            tag: 'result-' + approvalId,
          });
        })
        .catch(() => {
          // 실패 시 앱 열기
          return clients.openWindow('/');
        })
    );
  } else {
    // 알림 본문 클릭 → 앱 열기
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
        for (const client of windowClients) {
          if (client.url.includes('/') && 'focus' in client) {
            return client.focus();
          }
        }
        return clients.openWindow('/');
      })
    );
  }
});

// 서비스 워커 활성화 시 즉시 제어권 획득
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// 설치
self.addEventListener('install', (event) => {
  self.skipWaiting();
});
