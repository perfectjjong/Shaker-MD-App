'use strict';

const express = require('express');
const router = express.Router();

// ─── 공통 유틸 ─────────────────────────────────────────

function tm(req) {
  return req.app.locals.taskManager;
}

function validateExecutor(req, res) {
  const secret = process.env.EXECUTOR_SECRET || '';
  if (!secret) return true; // 미설정 시 인증 생략
  const provided =
    req.headers['x-executor-secret'] || req.query.executor_secret;
  if (provided !== secret) {
    res.status(401).json({ error: 'Executor 인증 실패' });
    return false;
  }
  return true;
}

// ─── Commander 엔드포인트 ───────────────────────────────

/**
 * POST /api/tasks
 * 작업 생성
 */
router.post('/', (req, res) => {
  const { commanderId, type, title, description, payload } = req.body;

  if (!commanderId || typeof commanderId !== 'string') {
    return res.status(400).json({ error: 'commanderId는 필수 문자열입니다' });
  }
  if (!title || typeof title !== 'string') {
    return res.status(400).json({ error: 'title은 필수 문자열입니다' });
  }

  try {
    const task = tm(req).createTask({ commanderId, type, title, description, payload });
    res.status(201).json(task);
  } catch (e) {
    res.status(400).json({ error: e.message });
  }
});

/**
 * GET /api/tasks/poll
 * Long-poll: commanderId의 업데이트된 작업 대기 (최대 30초)
 * ?commanderId=x&since=ISO
 */
router.get('/poll', (req, res) => {
  const { commanderId, since } = req.query;
  if (!commanderId) {
    return res.status(400).json({ error: 'commanderId 쿼리 파라미터가 필요합니다' });
  }

  // 즉시 업데이트가 있으면 바로 반환
  const immediate = tm(req).getTaskUpdates(commanderId, since);
  if (immediate.length > 0) {
    return res.json(immediate);
  }

  // 업데이트 대기 (최대 30초)
  let resolved = false;
  const timeout = setTimeout(() => {
    if (!resolved) {
      resolved = true;
      res.json([]);
    }
  }, 30000);

  const handler = (task) => {
    if (task.commanderId === commanderId && !resolved) {
      resolved = true;
      clearTimeout(timeout);
      // 해당 commanderId의 최신 업데이트 전체 반환
      res.json(tm(req).getTaskUpdates(commanderId, since));
    }
  };

  const taskMgr = tm(req);
  taskMgr.on('task:approved', handler);
  taskMgr.on('task:rejected', handler);
  taskMgr.on('task:executing', handler);
  taskMgr.on('task:completed', handler);
  taskMgr.on('task:failed', handler);
  taskMgr.on('task:timeout', handler);

  res.on('close', () => {
    if (!resolved) {
      resolved = true;
      clearTimeout(timeout);
    }
    taskMgr.off('task:approved', handler);
    taskMgr.off('task:rejected', handler);
    taskMgr.off('task:executing', handler);
    taskMgr.off('task:completed', handler);
    taskMgr.off('task:failed', handler);
    taskMgr.off('task:timeout', handler);
  });
});

/**
 * GET /api/tasks/pending-approval
 * 승인 대기 중인 작업 목록 (사용자/대시보드용)
 */
router.get('/pending-approval', (req, res) => {
  res.json(tm(req).getPendingApprovalTasks());
});

/**
 * GET /api/tasks
 * Commander별 작업 목록 또는 전체 활성 목록
 * ?commanderId=x
 */
router.get('/', (req, res) => {
  const { commanderId } = req.query;
  if (commanderId) {
    return res.json(tm(req).getTasksByCommander(commanderId));
  }
  res.json(tm(req).getActiveTasks());
});

/**
 * GET /api/tasks/history
 * 최근 완료 작업 히스토리
 * ?limit=20
 */
router.get('/history', (req, res) => {
  const limit = Math.min(Math.max(parseInt(req.query.limit) || 20, 1), 200);
  res.json(tm(req).getTaskHistory(limit));
});

/**
 * GET /api/tasks/:id
 * 작업 상태/결과 조회
 */
router.get('/:id', (req, res) => {
  const task = tm(req).getTask(req.params.id);
  if (!task) return res.status(404).json({ error: '작업을 찾을 수 없습니다' });
  res.json(task);
});

/**
 * GET /api/tasks/:id/result
 * 결과만 조회 (완료된 경우)
 */
router.get('/:id/result', (req, res) => {
  const task = tm(req).getTask(req.params.id);
  if (!task) return res.status(404).json({ error: '작업을 찾을 수 없습니다' });
  if (!['completed', 'failed'].includes(task.status)) {
    return res.status(202).json({ status: task.status, result: null });
  }
  res.json({ status: task.status, result: task.result });
});

/**
 * DELETE /api/tasks/:id
 * 작업 취소 (Commander만 가능)
 */
router.delete('/:id', (req, res) => {
  const { commanderId } = req.body;
  if (!commanderId) {
    return res.status(400).json({ error: 'commanderId가 필요합니다' });
  }
  const result = tm(req).cancelTask(req.params.id, commanderId);
  if (!result) {
    return res.status(404).json({ error: '취소할 수 없습니다 (없음/권한 없음/이미 완료)' });
  }
  res.json(result);
});

/**
 * POST /api/tasks/:id/approve
 * 사용자 승인
 */
router.post('/:id/approve', (req, res) => {
  const task = tm(req).approveTask(req.params.id);
  if (!task) {
    return res.status(404).json({ error: '승인할 수 없습니다 (없음 또는 이미 처리됨)' });
  }
  res.json(task);
});

/**
 * POST /api/tasks/:id/reject
 * 사용자 거부
 */
router.post('/:id/reject', (req, res) => {
  const task = tm(req).rejectTask(req.params.id);
  if (!task) {
    return res.status(404).json({ error: '거부할 수 없습니다 (없음 또는 이미 처리됨)' });
  }
  res.json(task);
});

// ─── Executor 엔드포인트 ────────────────────────────────

/**
 * POST /api/executor/register
 * Executor 등록
 */
router.post('/executor/register', (req, res) => {
  if (!validateExecutor(req, res)) return;

  const { executorId, capabilities } = req.body;
  if (!executorId || typeof executorId !== 'string') {
    return res.status(400).json({ error: 'executorId는 필수 문자열입니다' });
  }
  tm(req).registerExecutor(executorId, capabilities || []);
  res.json({ success: true, executorId });
});

/**
 * GET /api/executor/tasks
 * 승인된 작업 목록 (Executor polling)
 */
router.get('/executor/tasks', (req, res) => {
  if (!validateExecutor(req, res)) return;

  const { executorId } = req.query;
  if (!executorId) {
    return res.status(400).json({ error: 'executorId 쿼리 파라미터가 필요합니다' });
  }
  tm(req).heartbeatExecutor(executorId);
  res.json(tm(req).getApprovedTasks());
});

/**
 * POST /api/executor/claim/:id
 * 작업 획득 (executing으로 전환)
 */
router.post('/executor/claim/:id', (req, res) => {
  if (!validateExecutor(req, res)) return;

  const { executorId } = req.body;
  if (!executorId) {
    return res.status(400).json({ error: 'executorId가 필요합니다' });
  }

  const task = tm(req).claimTask(req.params.id, executorId);
  if (!task) {
    return res.status(409).json({ error: '작업을 claim할 수 없습니다 (없음/이미 claimed/상태 불일치)' });
  }
  res.json(task);
});

/**
 * POST /api/executor/result/:id
 * 실행 결과 제출
 */
router.post('/executor/result/:id', (req, res) => {
  if (!validateExecutor(req, res)) return;

  const { executorId, result } = req.body;
  if (!executorId) {
    return res.status(400).json({ error: 'executorId가 필요합니다' });
  }

  const task = tm(req).completeTask(req.params.id, executorId, result);
  if (!task) {
    return res.status(404).json({ error: '결과를 제출할 수 없습니다 (없음/권한 없음/상태 불일치)' });
  }
  res.json(task);
});

/**
 * POST /api/executor/heartbeat
 * 생존 신호
 */
router.post('/executor/heartbeat', (req, res) => {
  if (!validateExecutor(req, res)) return;

  const { executorId } = req.body;
  if (!executorId) {
    return res.status(400).json({ error: 'executorId가 필요합니다' });
  }
  tm(req).heartbeatExecutor(executorId);
  res.json({ ok: true, time: new Date().toISOString() });
});

/**
 * GET /api/executor/status
 * 등록된 Executor 목록
 */
router.get('/executor/status', (req, res) => {
  res.json(tm(req).getExecutors());
});

module.exports = router;
