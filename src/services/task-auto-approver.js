'use strict';

const fs = require('fs');
const path = require('path');

const APPROVALS_FILE = path.join(__dirname, '../../config/task-approvals.json');

/**
 * Task 자동 승인 엔진
 *
 * 두 가지 기준으로 수동 승인을 건너뜁니다:
 *   1. 위험도 기반: 설정 임계값 이하의 위험도는 자동 승인
 *   2. 이력 기반: 사용자가 한 번 이상 직접 승인한 fingerprint는 자동 승인
 *
 * 환경변수:
 *   TASK_AUTO_APPROVE_RISK   'none'|'low'|'medium' (기본: 'low')
 *   TASK_APPROVAL_HISTORY_TTL  일수 (기본: 30)
 */
class TaskAutoApprover {
  constructor() {
    // 위험도 임계값: 이 수준 이하는 자동 승인
    // 'none' = 위험도 기반 자동승인 끔 / 'low' = low만 / 'medium' = low+medium
    this._riskThreshold = (process.env.TASK_AUTO_APPROVE_RISK || 'low').toLowerCase();
    if (!['none', 'low', 'medium'].includes(this._riskThreshold)) {
      this._riskThreshold = 'low';
    }

    this._ttlMs = (parseInt(process.env.TASK_APPROVAL_HISTORY_TTL) || 30) * 24 * 60 * 60 * 1000;

    // 메모리 캐시: fingerprint → { approvedAt, count }
    this._fingerprints = this._loadFingerprints();
  }

  // ─── 공개 API ───────────────────────────────────────────

  /**
   * 자동 승인 여부 결정
   * @returns {'approve' | null}  null = 수동 승인 필요
   */
  shouldAutoApprove(task) {
    const risk = this.assessRisk(task);

    // ① 위험도 기반 자동 승인
    if (this._riskThreshold !== 'none') {
      if (risk === 'low') return 'approve';
      if (risk === 'medium' && this._riskThreshold === 'medium') return 'approve';
    }

    // ② 이력 기반 자동 승인
    const fp = this._fingerprint(task);
    if (fp && this._isApproved(fp)) return 'approve';

    return null;
  }

  /**
   * 위험도 평가 (Telegram 표시용으로도 사용)
   * @returns {'low' | 'medium' | 'high'}
   */
  assessRisk(task) {
    switch (task.type) {
      case 'file_read':  return 'low';
      case 'file_write': return 'medium';
      case 'file_edit':  return 'medium';
      case 'custom':     return 'medium';
      case 'bash':       return this._assessBashRisk(task.payload?.command || '');
      default:           return 'medium';
    }
  }

  /**
   * 수동 승인 기록 (approveTask 후 호출)
   */
  recordApproval(task) {
    const fp = this._fingerprint(task);
    if (!fp) return;

    const existing = this._fingerprints[fp];
    this._fingerprints[fp] = {
      approvedAt: new Date().toISOString(),
      count: existing ? existing.count + 1 : 1,
    };

    this._saveFingerprints();
    console.log(`[TaskAutoApprover] fingerprint 기록: ${fp.slice(0, 60)}`);
  }

  // ─── 위험도 평가 ──────────────────────────────────────

  _assessBashRisk(command) {
    const high = [
      /rm\s+-rf\s*\/[\s$]/i,          // rm -rf /
      /rm\s+(-[a-z]*r[a-z]*f|-f[a-z]*r)\s/i, // rm -rf or rm -fr
      /\bsudo\b/i,
      /\bmkfs\b/i,
      /\bdd\b.*\bif=/i,
      /:\s*\(\s*\)\s*\{.*:\s*\|.*:.*&/,  // fork bomb
      /\b(shutdown|halt|poweroff|reboot)\b/i,
      /\bkill\s+-9\b/i,
      />\s*\/dev\/(sda|hda|nvme|xvd)/i,
      /\bchmod\s+[0-7]*777\b/i,
      /\buseradd\b|\buserdel\b/i,
      /\bpasswd\b/i,
      /\bcrontab\s+-[re]/i,
    ];

    const medium = [
      /\brm\s+/i,                      // rm (rm -f, rm 파일 등)
      /\bmv\s+/i,
      /\bcp\s+-r/i,
      /\bgit\s+(push|reset|rebase|force)/i,
      /\bnpm\s+(publish|unpublish|install|ci)\b/i,
      /\byarn\s+(publish|add|remove)\b/i,
      /\bdocker\s+(rm|rmi|kill|stop)\b/i,
      /\bchmod\b/i,
      /\bchown\b/i,
      /\bsystemctl\s+(start|stop|restart|enable|disable)/i,
      /\bservice\s+\w+\s+(start|stop|restart)/i,
      /\bpip\s+(install|uninstall)\b/i,
      /\bapt(-get)?\s+(install|remove|purge)\b/i,
      /\bwget\b.*-[Oo]/i,
      /\bcurl\b.*[>|]/i,
    ];

    for (const p of high)   if (p.test(command)) return 'high';
    for (const p of medium) if (p.test(command)) return 'medium';
    return 'low';
  }

  // ─── Fingerprint ────────────────────────────────────

  _fingerprint(task) {
    const p = task.payload || {};
    switch (task.type) {
      case 'bash':
        return p.command ? `bash:${p.command.trim()}` : null;
      case 'file_read':
        return p.filePath ? `file_read:${p.filePath}` : null;
      case 'file_write':
        return p.filePath ? `file_write:${p.filePath}` : null;
      case 'file_edit':
        if (!p.filePath) return null;
        return `file_edit:${p.filePath}:${(p.oldStr || '').slice(0, 100)}`;
      case 'custom':
        return p.script ? `custom:${p.script.trim().slice(0, 200)}` : null;
      default:
        return null;
    }
  }

  _isApproved(fp) {
    const record = this._fingerprints[fp];
    if (!record) return false;
    const age = Date.now() - new Date(record.approvedAt).getTime();
    return age <= this._ttlMs;
  }

  // ─── 파일 persistence ────────────────────────────────

  _loadFingerprints() {
    try {
      if (!fs.existsSync(APPROVALS_FILE)) return {};
      const raw = fs.readFileSync(APPROVALS_FILE, 'utf8');
      const data = JSON.parse(raw);
      return data.fingerprints || {};
    } catch (e) {
      console.warn('[TaskAutoApprover] 이력 파일 로드 실패, 초기화:', e.message);
      return {};
    }
  }

  _saveFingerprints() {
    try {
      // TTL 만료 항목 정리
      const now = Date.now();
      const cleaned = {};
      for (const [fp, record] of Object.entries(this._fingerprints)) {
        const age = now - new Date(record.approvedAt).getTime();
        if (age <= this._ttlMs) cleaned[fp] = record;
      }
      this._fingerprints = cleaned;

      const dir = path.dirname(APPROVALS_FILE);
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(APPROVALS_FILE, JSON.stringify({ fingerprints: cleaned }, null, 2), 'utf8');
    } catch (e) {
      console.error('[TaskAutoApprover] 이력 파일 저장 실패:', e.message);
    }
  }

  // ─── 상태 조회 (진단용) ──────────────────────────────

  getStatus() {
    const now = Date.now();
    const active = Object.entries(this._fingerprints).filter(([, r]) =>
      now - new Date(r.approvedAt).getTime() <= this._ttlMs
    );
    return {
      riskThreshold: this._riskThreshold,
      ttlDays: Math.round(this._ttlMs / 86400000),
      approvedFingerprints: active.length,
    };
  }
}

module.exports = { TaskAutoApprover };
