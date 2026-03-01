const { EventEmitter } = require('events');
const { v4: uuidv4 } = require('uuid');

class ApprovalManager extends EventEmitter {
  constructor() {
    super();
    this.pending = new Map();   // id -> approval
    this.history = [];          // 최근 100건
    this.timeoutMs = (parseInt(process.env.APPROVAL_TIMEOUT) || 300) * 1000;
  }

  /**
   * 새 승인 요청 생성
   * @param {Function} [onId] - ID 생성 직후 호출되는 콜백 (연결 감시 등에 사용)
   * @returns {Promise<string>} 'approved' | 'rejected' | 'timeout'
   */
  create({ command, tool, workdir, sessionId, onId }) {
    const id = uuidv4();
    const approval = {
      id,
      command: command || '',
      tool: tool || 'Bash',
      workdir: workdir || '',
      sessionId: sessionId || '',
      status: 'pending',
      createdAt: new Date().toISOString(),
      resolvedAt: null,
    };

    return new Promise((resolve) => {
      // 타임아웃 설정
      const timer = setTimeout(() => {
        if (this.pending.has(id)) {
          this.resolve(id, 'timeout');
        }
      }, this.timeoutMs);

      this.pending.set(id, {
        ...approval,
        _resolve: resolve,
        _timer: timer,
      });

      // ID를 호출자에게 콜백으로 노출 (연결 끊김 감지 등에 활용)
      if (onId) onId(id);

      console.log(`[Approval] 새 요청: ${id.slice(0, 8)}... | ${command}`);
      this.emit('new', approval);
    });
  }

  /**
   * 승인/거부 처리
   */
  resolve(id, status) {
    const entry = this.pending.get(id);
    if (!entry) return false;

    clearTimeout(entry._timer);
    entry.status = status;
    entry.resolvedAt = new Date().toISOString();

    const { _resolve, _timer, ...record } = entry;
    this.pending.delete(id);

    // 히스토리에 추가 (최대 100건)
    this.history.unshift(record);
    if (this.history.length > 100) this.history.pop();

    console.log(`[Approval] ${status}: ${id.slice(0, 8)}... | ${entry.command}`);
    this.emit('resolved', record);
    _resolve(status);
    return true;
  }

  /**
   * 대기 중인 승인 목록
   */
  getPending() {
    return Array.from(this.pending.values()).map(
      ({ _resolve, _timer, ...rest }) => rest
    );
  }

  /**
   * 히스토리 조회
   */
  getHistory(limit = 20) {
    return this.history.slice(0, limit);
  }
}

module.exports = { ApprovalManager };
