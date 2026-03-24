/**
 * 명령어 위험도 평가 (공통 모듈)
 * telegram-notifier와 push-notifier에서 공유
 */

const HIGH_RISK = /(rm\s+-rf|sudo|chmod\s+777|mkfs|dd\s+if|>\s*\/dev\/|shutdown|reboot|kill\s+-9)/i;
const MED_RISK = /(rm\s|mv\s|cp\s+-r|git\s+(push|reset|rebase)|npm\s+(publish|unpublish)|docker\s+rm)/i;

/**
 * @param {string} command
 * @returns {'high' | 'medium' | 'low'}
 */
function assessRisk(command) {
  if (HIGH_RISK.test(command)) return 'high';
  if (MED_RISK.test(command)) return 'medium';
  return 'low';
}

module.exports = { assessRisk };
