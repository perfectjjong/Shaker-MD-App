'use strict';

const { EventEmitter } = require('events');
const { v4: uuidv4 } = require('uuid');

/**
 * Task 상태 머신:
 * pending_approval → approved → executing → completed
 *                                         → failed
 *                 → rejected
 *                 → timeout
 */
class TaskManager extends EventEmitter {
  /**
   * @param {import('./task-auto-approver').TaskAutoApprover|null} taskAutoApprover
   */
  constructor(taskAutoApprover = null) {
    super();

    this.tasks = new Map();   // id → task (pending + active)
    this.history = [];        // 완료된 작업 (최대 200건)
    this.taskAutoApprover = taskAutoApprover;

    this.approvalTimeoutMs =
      (parseInt(process.env.TASK_APPROVAL_TIMEOUT) || 600) * 1000;
    this.executionTimeoutMs =
      (parseInt(process.env.TASK_EXECUTION_TIMEOUT) || 1800) * 1000;
    this.maxResultSize =
      parseInt(process.env.MAX_RESULT_SIZE) || 1024 * 1024; // 1MB

    // executorId → { lastSeen, capabilities }
    this.executors = new Map();
  }

  // ─── Executor 등록 ─────────────────────────────────────

  registerExecutor(executorId, capabilities = []) {
    this.executors.set(executorId, {
      executorId,
      capabilities,
      lastSeen: new Date().toISOString(),
      registeredAt: this.executors.has(executorId)
        ? this.executors.get(executorId).registeredAt
        : new Date().toISOString(),
    });
    console.log(`[TaskManager] Executor 등록: ${executorId}`);
  }

  heartbeatExecutor(executorId) {
    if (this.executors.has(executorId)) {
      this.executors.get(executorId).lastSeen = new Date().toISOString();
    }
  }

  getExecutors() {
    return Array.from(this.executors.values());
  }

  /**
   * executor 연결 해제 시 호출.
   * 해당 executor가 맡고 있던 executing 작업을 approved로 되돌려 다른 executor가 재시도할 수 있게 함.
   * _execTimer는 approveTask()에서 'approved' || 'executing' 양쪽을 체크하므로 그대로 유지.
   * @param {string} executorId
   * @returns {number} 복구된 작업 수
   */
  markExecutorOffline(executorId) {
    let resetCount = 0;
    for (const entry of this.tasks.values()) {
      if (entry.status === 'executing' && entry.executorId === executorId) {
        entry.status = 'approved';
        entry.executorId = null;
        entry.claimedAt = null;
        resetCount++;
        console.log(`[TaskManager] executor 오프라인으로 작업 복구: ${entry.id.slice(0, 8)}... → approved`);
        this.emit('task:approved', this._publicTask(entry));
      }
    }
    this.executors.delete(executorId);
    return resetCount;
  }

  // ─── Task 생성 ─────────────────────────────────────────

  /**
   * @param {object} opts
   * @param {string} opts.commanderId
   * @param {string} opts.type  'bash' | 'file_read' | 'file_write' | 'file_edit' | 'custom'
   * @param {string} opts.title
   * @param {string} [opts.description]
   * @param {object} opts.payload  { command, cwd, filePath, content, oldStr, newStr, script, ... }
   * @returns {object} task (without internal timers)
   */
  createTask({ commanderId, type, title, description, payload }) {
    if (!commanderId || typeof commanderId !== 'string') {
      throw new Error('commanderId는 필수 문자열입니다');
    }
    const validTypes = ['bash', 'file_read', 'file_write', 'file_edit', 'custom'];
    if (!type || !validTypes.includes(type)) {
      throw new Error(`type은 다음 중 하나여야 합니다: ${validTypes.join(', ')}`);
    }
    if (!title || typeof title !== 'string') {
      throw new Error('title은 필수 문자열입니다');
    }

    const id = uuidv4();
    const now = new Date().toISOString();
    const task = {
      id,
      commanderId,
      executorId: null,
      type,
      title: title.slice(0, 200),
      description: (description || '').slice(0, 2000),
      payload: payload || {},
      status: 'pending_approval',
      autoApproved: false,
      result: null,
      createdAt: now,
      approvedAt: null,
      claimedAt: null,
      completedAt: null,
    };

    console.log(`[TaskManager] 작업 생성: ${id.slice(0, 8)}... | ${title}`);

    // ── 자동 승인 사전 체크 ──────────────────────────────
    if (this.taskAutoApprover) {
      const autoResult = this.taskAutoApprover.shouldAutoApprove(task);
      if (autoResult === 'approve') {
        task.status = 'approved';
        task.approvedAt = now;
        task.autoApproved = true;

        // 실행 타임아웃 설정
        const execTimer = setTimeout(() => {
          if (this.tasks.has(id)) {
            const t = this.tasks.get(id);
            if (t.status === 'approved' || t.status === 'executing') {
              this._finalizeTask(id, 'timeout', { error: '실행 타임아웃' }, 'execTimer');
            }
          }
        }, this.executionTimeoutMs);

        this.tasks.set(id, { ...task, _approvalTimer: null, _execTimer: execTimer });
        console.log(`[TaskManager] 자동 승인: ${id.slice(0, 8)}... (위험도/이력 기반)`);
        this.emit('task:approved', task);
        return task;
      }
    }

    // ── 수동 승인 대기 ───────────────────────────────────
    const approvalTimer = setTimeout(() => {
      if (this.tasks.has(id)) {
        const t = this.tasks.get(id);
        if (t.status === 'pending_approval') {
          this._finalizeTask(id, 'timeout', null, 'approvalTimer');
        }
      }
    }, this.approvalTimeoutMs);

    this.tasks.set(id, { ...task, _approvalTimer: approvalTimer, _execTimer: null });
    this.emit('task:created', task);
    return task;
  }

  // ─── 사용자 승인/거부 ──────────────────────────────────

  approveTask(id) {
    const entry = this.tasks.get(id);
    if (!entry) return null;
    if (entry.status !== 'pending_approval') return null;

    clearTimeout(entry._approvalTimer);
    entry._approvalTimer = null;
    entry.status = 'approved';
    entry.approvedAt = new Date().toISOString();

    // 실행 타임아웃 (claim되지 않을 경우 대비)
    const execTimer = setTimeout(() => {
      if (this.tasks.has(id)) {
        const t = this.tasks.get(id);
        if (t.status === 'approved' || t.status === 'executing') {
          this._finalizeTask(id, 'timeout', { error: '실행 타임아웃' }, 'execTimer');
        }
      }
    }, this.executionTimeoutMs);
    entry._execTimer = execTimer;

    // 수동 승인 → fingerprint 기록 (다음 번 자동 승인에 활용)
    if (this.taskAutoApprover && !entry.autoApproved) {
      this.taskAutoApprover.recordApproval(entry);
    }

    const task = this._publicTask(entry);
    console.log(`[TaskManager] 승인: ${id.slice(0, 8)}...`);
    this.emit('task:approved', task);
    return task;
  }

  rejectTask(id) {
    return this._finalizeTask(id, 'rejected', null, 'reject');
  }

  // ─── Executor claim / complete ─────────────────────────

  claimTask(id, executorId) {
    const entry = this.tasks.get(id);
    if (!entry) return null;
    if (entry.status !== 'approved') return null; // 이미 claiming 됐거나 상태 불일치

    // Node.js 단일스레드 → 동시 claim 경쟁 없음
    entry.status = 'executing';
    entry.executorId = executorId;
    entry.claimedAt = new Date().toISOString();

    const task = this._publicTask(entry);
    console.log(`[TaskManager] claim: ${id.slice(0, 8)}... by ${executorId}`);
    this.emit('task:executing', task);
    return task;
  }

  completeTask(id, executorId, result) {
    const entry = this.tasks.get(id);
    if (!entry) return null;
    if (entry.status !== 'executing') return null;
    if (entry.executorId !== executorId) return null;

    // 결과 크기 제한
    const safeResult = this._sanitizeResult(result);
    const isFailure = safeResult && (safeResult.exitCode !== 0 || safeResult.error);

    return this._finalizeTask(id, isFailure ? 'failed' : 'completed', safeResult, 'complete');
  }

  // ─── Commander 취소 ────────────────────────────────────

  cancelTask(id, commanderId) {
    const entry = this.tasks.get(id);
    if (!entry) return null;
    if (entry.commanderId !== commanderId) return null;
    if (['completed', 'failed', 'rejected', 'timeout'].includes(entry.status)) return null;

    return this._finalizeTask(id, 'rejected', { error: 'Commander에 의해 취소됨' }, 'cancel');
  }

  // ─── 조회 ──────────────────────────────────────────────

  getTask(id) {
    if (this.tasks.has(id)) return this._publicTask(this.tasks.get(id));
    return this.history.find((t) => t.id === id) || null;
  }

  getApprovedTasks() {
    return Array.from(this.tasks.values())
      .filter((t) => t.status === 'approved')
      .map((t) => this._publicTask(t));
  }

  getPendingApprovalTasks() {
    return Array.from(this.tasks.values())
      .filter((t) => t.status === 'pending_approval')
      .map((t) => this._publicTask(t));
  }

  getActiveTasks() {
    return Array.from(this.tasks.values())
      .map((t) => this._publicTask(t));
  }

  getTasksByCommander(commanderId) {
    const active = Array.from(this.tasks.values())
      .filter((t) => t.commanderId === commanderId)
      .map((t) => this._publicTask(t));
    const hist = this.history.filter((t) => t.commanderId === commanderId);
    return [...active, ...hist];
  }

  /**
   * commanderId의 작업 중 since 이후에 업데이트된 것
   */
  getTaskUpdates(commanderId, since) {
    const sinceDate = since ? new Date(since) : new Date(0);
    const check = (t) => {
      const updated = new Date(t.completedAt || t.claimedAt || t.approvedAt || t.createdAt);
      return t.commanderId === commanderId && updated > sinceDate;
    };
    const active = Array.from(this.tasks.values())
      .filter(check)
      .map((t) => this._publicTask(t));
    const hist = this.history.filter(check);
    return [...active, ...hist];
  }

  getTaskHistory(limit = 20) {
    return this.history.slice(0, Math.min(limit, 200));
  }

  // ─── 내부 유틸리티 ─────────────────────────────────────

  _finalizeTask(id, status, result, source) {
    const entry = this.tasks.get(id);
    if (!entry) return null;

    clearTimeout(entry._approvalTimer);
    clearTimeout(entry._execTimer);

    entry.status = status;
    entry.result = result || null;
    entry.completedAt = new Date().toISOString();

    const { _approvalTimer, _execTimer, ...record } = entry;
    this.tasks.delete(id);

    this.history.unshift(record);
    if (this.history.length > 200) this.history.pop();

    console.log(`[TaskManager] ${status} (${source}): ${id.slice(0, 8)}...`);

    const eventName =
      status === 'completed' ? 'task:completed'
      : status === 'failed'   ? 'task:failed'
      : status === 'rejected' ? 'task:rejected'
      :                         'task:timeout';

    this.emit(eventName, record);
    return record;
  }

  _publicTask(entry) {
    const { _approvalTimer, _execTimer, ...rest } = entry;
    return rest;
  }

  _sanitizeResult(result) {
    if (!result || typeof result !== 'object') return result;
    const out = { ...result };
    if (out.stdout && out.stdout.length > this.maxResultSize) {
      out.stdout = out.stdout.slice(0, this.maxResultSize) + '\n[출력 크기 초과로 잘림]';
    }
    if (out.stderr && out.stderr.length > this.maxResultSize) {
      out.stderr = out.stderr.slice(0, this.maxResultSize) + '\n[출력 크기 초과로 잘림]';
    }
    return out;
  }

  // Graceful shutdown: 실행 중 작업을 failed로 처리
  shutdown() {
    for (const [id, entry] of this.tasks) {
      this._finalizeTask(id, 'failed', { error: '서버 종료로 인해 중단됨' }, 'shutdown');
    }
  }
}

module.exports = { TaskManager };
