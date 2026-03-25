const fs = require('fs');
const path = require('path');

const RULES_FILE = path.join(__dirname, '../../config/auto-approve-rules.json');

const DEFAULT_RULES = {
  enabled: true,
  rules: [
    {
      name: 'Read-only 명령어',
      pattern: '^(ls|cat|head|tail|wc|file|stat|which|echo|pwd|whoami|date|git\\s+(status|log|diff|branch|show))\\b',
      action: 'approve',
      active: true,
    },
    {
      name: 'npm/yarn 읽기 명령어',
      pattern: '^(npm\\s+(list|ls|outdated|audit)|yarn\\s+(list|info|why))\\b',
      action: 'approve',
      active: true,
    },
    {
      name: '위험 명령어 차단',
      pattern: '(rm\\s+-rf\\s+/|sudo\\s+rm|mkfs|dd\\s+if|:(){ :|&};:)',
      action: 'reject',
      active: true,
    },
    {
      name: '파일 편집 도구 허용',
      pattern: null,
      tool: 'Edit',
      action: 'approve',
      active: false,
    },
    {
      name: '파일 쓰기 도구 허용',
      pattern: null,
      tool: 'Write',
      action: 'approve',
      active: false,
    },
  ],
};

class AutoApprover {
  constructor() {
    this.rules = this._loadRules();
  }

  _loadRules() {
    try {
      if (fs.existsSync(RULES_FILE)) {
        const data = fs.readFileSync(RULES_FILE, 'utf-8');
        return JSON.parse(data);
      }
    } catch (e) {
      console.error('[AutoApprove] 규칙 파일 로드 실패:', e.message);
    }
    // 기본 규칙 저장
    this._saveRules(DEFAULT_RULES);
    return DEFAULT_RULES;
  }

  _saveRules(rules) {
    try {
      const dir = path.dirname(RULES_FILE);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(RULES_FILE, JSON.stringify(rules, null, 2));
    } catch (e) {
      console.error('[AutoApprove] 규칙 저장 실패:', e.message);
    }
  }

  /**
   * 자동 승인 여부 판단
   * @returns {'approve' | 'reject' | null}
   */
  shouldAutoApprove(approval) {
    if (!this.rules.enabled && process.env.AUTO_APPROVE_ENABLED !== 'true') {
      return null;
    }

    for (const rule of this.rules.rules) {
      if (!rule.active) continue;

      // 도구 유형 매칭
      if (rule.tool && rule.tool !== approval.tool) continue;

      // 명령어 패턴 매칭
      if (rule.pattern) {
        try {
          const regex = new RegExp(rule.pattern, 'i');
          if (regex.test(approval.command)) {
            console.log(`[AutoApprove] 규칙 매칭: "${rule.name}" → ${rule.action}`);
            return rule.action;
          }
        } catch (e) {
          console.error(`[AutoApprove] 정규식 오류 (${rule.name}):`, e.message);
        }
      } else if (rule.tool) {
        // 패턴 없이 도구만 매칭
        console.log(`[AutoApprove] 도구 매칭: "${rule.name}" → ${rule.action}`);
        return rule.action;
      }
    }

    return null;
  }

  /**
   * 규칙 목록 반환
   */
  getRules() {
    return this.rules;
  }

  /**
   * 규칙 업데이트
   */
  updateRules(newRules) {
    this.rules = { ...this.rules, ...newRules };
    this._saveRules(this.rules);
    return this.rules;
  }

  /**
   * 개별 규칙 토글
   */
  toggleRule(index, active) {
    if (index >= 0 && index < this.rules.rules.length) {
      this.rules.rules[index].active = active;
      this._saveRules(this.rules);
    }
    return this.rules;
  }

  /**
   * 규칙 추가
   */
  addRule({ name, pattern, tool, action, active = true }) {
    this.rules.rules.push({ name, pattern: pattern || null, tool: tool || null, action, active });
    this._saveRules(this.rules);
    return this.rules;
  }

  /**
   * 규칙 삭제
   */
  removeRule(index) {
    if (index >= 0 && index < this.rules.rules.length) {
      this.rules.rules.splice(index, 1);
      this._saveRules(this.rules);
    }
    return this.rules;
  }
}

module.exports = { AutoApprover };
