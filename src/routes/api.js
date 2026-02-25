const express = require('express');
const router = express.Router();

// POST /api/approval - Claude Code Hook에서 호출
router.post('/approval', async (req, res) => {
  const { approvalManager, autoApprover } = req.app.locals;
  const { command, tool, workdir, sessionId } = req.body;

  if (!command && !tool) {
    return res.status(400).json({ error: 'command 또는 tool이 필요합니다' });
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
    const status = await approvalManager.create({ command, tool, workdir, sessionId });
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
  const limit = parseInt(req.query.limit) || 20;
  res.json(approvalManager.getHistory(limit));
});

// GET /api/rules - 자동 승인 규칙
router.get('/rules', (req, res) => {
  const { autoApprover } = req.app.locals;
  res.json(autoApprover.getRules());
});

// PUT /api/rules - 규칙 업데이트
router.put('/rules', (req, res) => {
  const { autoApprover } = req.app.locals;
  const rules = autoApprover.updateRules(req.body);
  res.json(rules);
});

// POST /api/rules/toggle/:index - 규칙 토글
router.post('/rules/toggle/:index', (req, res) => {
  const { autoApprover } = req.app.locals;
  const index = parseInt(req.params.index);
  const { active } = req.body;
  const rules = autoApprover.toggleRule(index, active);
  res.json(rules);
});

// POST /api/rules/add - 규칙 추가
router.post('/rules/add', (req, res) => {
  const { autoApprover } = req.app.locals;
  const rules = autoApprover.addRule(req.body);
  res.json(rules);
});

// DELETE /api/rules/:index - 규칙 삭제
router.delete('/rules/:index', (req, res) => {
  const { autoApprover } = req.app.locals;
  const index = parseInt(req.params.index);
  const rules = autoApprover.removeRule(index);
  res.json(rules);
});

module.exports = router;
