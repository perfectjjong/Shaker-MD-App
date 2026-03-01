const express = require('express');
const router = express.Router();

// POST /api/approval - Claude Code Hook에서 호출
router.post('/approval', async (req, res) => {
  const { approvalManager, autoApprover } = req.app.locals;
  const { command, tool, workdir, sessionId } = req.body;

  if (!command && !tool) {
    return res.status(400).json({ error: 'command 또는 tool이 필요합니다' });
  }

  // 입력 타입 검증
  if (command && typeof command !== 'string') {
    return res.status(400).json({ error: 'command는 문자열이어야 합니다' });
  }
  if (tool && typeof tool !== 'string') {
    return res.status(400).json({ error: 'tool은 문자열이어야 합니다' });
  }

  // 자동 승인 사전 체크 (빠른 응답)
  const autoResult = autoApprover.shouldAutoApprove({ command, tool });
  if (autoResult === 'approve') {
    return res.json({ status: 'approved', auto: true });
  }
  if (autoResult === 'reject') {
    return res.json({ status: 'rejected', auto: true, reason: '자동 거부 규칙' });
  }

  // 수동 승인 대기
  try {
    const status = await approvalManager.create({
      command, tool, workdir, sessionId,
      onId: (id) => {
        // 훅 프로세스가 HTTP 연결을 끊으면 (exit(0) 등) 자동 승인 처리
        // 훅은 연결 끊김 시 exit(0)으로 종료해 이미 허용 상태이므로 approved로 정리
        req.on('close', () => {
          if (approvalManager.pending.has(id)) {
            console.log(`[Approval] 훅 연결 끊김 - 자동 승인: ${id.slice(0, 8)}...`);
            approvalManager.resolve(id, 'approved');
          }
        });
      },
    });
    res.json({ status });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// GET /api/pending - 대기 중인 승인 목록
router.get('/pending', (req, res) => {
  const { approvalManager } = req.app.locals;
  res.json(approvalManager.getPending());
});

// POST /api/approve/:id - 승인
router.post('/approve/:id', (req, res) => {
  const { approvalManager } = req.app.locals;
  const success = approvalManager.resolve(req.params.id, 'approved');
  res.json({ success });
});

// POST /api/reject/:id - 거부
router.post('/reject/:id', (req, res) => {
  const { approvalManager } = req.app.locals;
  const success = approvalManager.resolve(req.params.id, 'rejected');
  res.json({ success });
});

// POST /api/approve-all - 모두 승인
router.post('/approve-all', (req, res) => {
  const { approvalManager } = req.app.locals;
  const pending = approvalManager.getPending();
  let count = 0;
  for (const p of pending) {
    if (approvalManager.resolve(p.id, 'approved')) count++;
  }
  res.json({ approved: count });
});

// GET /api/history - 처리 내역
router.get('/history', (req, res) => {
  const { approvalManager } = req.app.locals;
  const limit = Math.min(Math.max(parseInt(req.query.limit) || 20, 1), 100);
  res.json(approvalManager.getHistory(limit));
});

// GET /api/rules - 자동 승인 규칙
router.get('/rules', (req, res) => {
  const { autoApprover } = req.app.locals;
  res.json(autoApprover.getRules());
});

// PUT /api/rules - 마스터 토글 업데이트만 허용
router.put('/rules', (req, res) => {
  const { autoApprover } = req.app.locals;
  const { enabled } = req.body;
  if (typeof enabled !== 'boolean') {
    return res.status(400).json({ error: 'enabled는 boolean이어야 합니다' });
  }
  const rules = autoApprover.updateRules({ enabled });
  res.json(rules);
});

// POST /api/rules/toggle/:index - 규칙 토글
router.post('/rules/toggle/:index', (req, res) => {
  const { autoApprover } = req.app.locals;
  const index = parseInt(req.params.index);
  if (isNaN(index) || index < 0) {
    return res.status(400).json({ error: '유효하지 않은 인덱스입니다' });
  }
  const { active } = req.body;
  if (typeof active !== 'boolean') {
    return res.status(400).json({ error: 'active는 boolean이어야 합니다' });
  }
  const rules = autoApprover.toggleRule(index, active);
  res.json(rules);
});

// POST /api/rules/add - 규칙 추가
router.post('/rules/add', (req, res) => {
  const { autoApprover } = req.app.locals;
  const { name, pattern, tool, action, active } = req.body;

  // 필수 필드 검증
  if (!name || typeof name !== 'string') {
    return res.status(400).json({ error: 'name은 필수 문자열입니다' });
  }
  if (!action || !['approve', 'reject'].includes(action)) {
    return res.status(400).json({ error: "action은 'approve' 또는 'reject'이어야 합니다" });
  }
  if (!pattern && !tool) {
    return res.status(400).json({ error: 'pattern 또는 tool 중 하나는 필수입니다' });
  }
  // 정규식 유효성 검증
  if (pattern) {
    try {
      new RegExp(pattern);
    } catch (e) {
      return res.status(400).json({ error: `유효하지 않은 정규식: ${e.message}` });
    }
  }

  const rules = autoApprover.addRule({ name, pattern, tool, action, active });
  res.json(rules);
});

// DELETE /api/rules/:index - 규칙 삭제
router.delete('/rules/:index', (req, res) => {
  const { autoApprover } = req.app.locals;
  const index = parseInt(req.params.index);
  if (isNaN(index) || index < 0) {
    return res.status(400).json({ error: '유효하지 않은 인덱스입니다' });
  }
  const rules = autoApprover.removeRule(index);
  res.json(rules);
});

// GET /api/push/vapid-key - VAPID 공개키 반환
router.get('/push/vapid-key', (req, res) => {
  const { pushNotifier } = req.app.locals;
  if (pushNotifier && pushNotifier.vapidPublicKey) {
    res.json({ key: pushNotifier.vapidPublicKey });
  } else {
    res.json({ key: null });
  }
});

// POST /api/push/subscribe - 푸시 구독 등록
router.post('/push/subscribe', (req, res) => {
  const { pushNotifier } = req.app.locals;
  if (!pushNotifier || !pushNotifier.enabled) {
    return res.status(400).json({ error: 'Push 알림이 비활성화되어 있습니다' });
  }
  const { endpoint, keys } = req.body;
  if (!endpoint || !keys) {
    return res.status(400).json({ error: 'endpoint와 keys가 필요합니다' });
  }
  pushNotifier.subscribe(req.body);
  res.json({ success: true });
});

// POST /api/push/unsubscribe - 푸시 구독 해제
router.post('/push/unsubscribe', (req, res) => {
  const { pushNotifier } = req.app.locals;
  if (!pushNotifier) {
    return res.status(400).json({ error: 'Push 알림이 비활성화되어 있습니다' });
  }
  const { endpoint } = req.body;
  if (!endpoint) {
    return res.status(400).json({ error: 'endpoint가 필요합니다' });
  }
  pushNotifier.unsubscribe(endpoint);
  res.json({ success: true });
});

// POST /api/push/test - 테스트 푸시 전송
router.post('/push/test', async (req, res) => {
  const { pushNotifier } = req.app.locals;
  if (!pushNotifier || !pushNotifier.enabled) {
    return res.status(400).json({ error: 'Push 알림이 비활성화되어 있습니다' });
  }
  const sent = await pushNotifier.sendToAll({
    type: 'test',
    title: '테스트 알림',
    body: 'Push 알림이 정상 작동합니다!',
  });
  res.json({ sent });
});

// GET /api/health - 서버 및 Telegram 연결 상태
router.get('/health', (req, res) => {
  const { telegramNotifier, pushNotifier } = req.app.locals;
  const telegramStatus = telegramNotifier
    ? telegramNotifier.getStatus()
    : { connected: false, reason: 'not_configured' };
  const pushStatus = pushNotifier
    ? pushNotifier.getStatus()
    : { enabled: false };

  res.json({
    status: 'ok',
    uptime: Math.round(process.uptime()),
    memory: Math.round(process.memoryUsage().rss / 1024 / 1024),
    telegram: telegramStatus,
    push: pushStatus,
  });
});

module.exports = router;
