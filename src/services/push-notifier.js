const webpush = require('web-push');

class PushNotifier {
  constructor(options = {}) {
    this.subscriptions = new Map(); // endpoint -> subscription
    this.vapidPublicKey = options.vapidPublicKey;

    if (options.vapidPublicKey && options.vapidPrivateKey) {
      webpush.setVapidDetails(
        options.vapidEmail || 'mailto:admin@example.com',
        options.vapidPublicKey,
        options.vapidPrivateKey
      );
      this.enabled = true;
      console.log('[Push] Web Push 알림 활성화');
    } else {
      this.enabled = false;
      console.log('[Push] VAPID 키 미설정 - Push 알림 비활성화');
    }
  }

  /**
   * 구독 등록
   */
  subscribe(subscription) {
    this.subscriptions.set(subscription.endpoint, subscription);
    console.log(`[Push] 구독 등록 (총 ${this.subscriptions.size}개)`);
    return true;
  }

  /**
   * 구독 해제
   */
  unsubscribe(endpoint) {
    const deleted = this.subscriptions.delete(endpoint);
    if (deleted) {
      console.log(`[Push] 구독 해제 (총 ${this.subscriptions.size}개)`);
    }
    return deleted;
  }

  /**
   * 모든 구독자에게 푸시 전송
   */
  async sendToAll(payload) {
    if (!this.enabled || this.subscriptions.size === 0) return 0;

    const data = JSON.stringify(payload);
    let sent = 0;
    const expired = [];

    for (const [endpoint, sub] of this.subscriptions) {
      try {
        await webpush.sendNotification(sub, data);
        sent++;
      } catch (err) {
        if (err.statusCode === 410 || err.statusCode === 404) {
          // 구독 만료됨
          expired.push(endpoint);
        } else {
          console.warn(`[Push] 전송 실패: ${err.message}`);
        }
      }
    }

    // 만료된 구독 제거
    for (const ep of expired) {
      this.subscriptions.delete(ep);
    }
    if (expired.length > 0) {
      console.log(`[Push] 만료 구독 ${expired.length}개 제거`);
    }

    return sent;
  }

  /**
   * 승인 요청 알림 전송
   */
  async sendApprovalRequest(approval) {
    const risk = this._assessRisk(approval.command);
    const riskLabel = risk === 'high' ? '🔴 위험' : risk === 'medium' ? '🟡 주의' : '🟢 안전';

    return this.sendToAll({
      type: 'approval_request',
      id: approval.id,
      title: `${riskLabel} Claude Code 승인 요청`,
      body: `${approval.tool}: ${approval.command.slice(0, 100)}`,
      data: {
        id: approval.id,
        command: approval.command,
        tool: approval.tool,
        workdir: approval.workdir,
        risk,
      },
    });
  }

  /**
   * 처리 완료 알림
   */
  async sendResolved(record) {
    const emoji = record.status === 'approved' ? '✅' : record.status === 'rejected' ? '❌' : '⏳';
    const label = record.status === 'approved' ? '승인됨' : record.status === 'rejected' ? '거부됨' : '타임아웃';

    return this.sendToAll({
      type: 'approval_resolved',
      id: record.id,
      title: `${emoji} ${label}`,
      body: `${record.command.slice(0, 80)}`,
    });
  }

  /**
   * 명령어 위험도 평가
   */
  _assessRisk(command) {
    const highRisk = /(rm\s+-rf|sudo|chmod\s+777|mkfs|dd\s+if|>\s*\/dev\/|shutdown|reboot|kill\s+-9)/i;
    const medRisk = /(rm\s|mv\s|cp\s+-r|git\s+(push|reset|rebase)|npm\s+(publish|unpublish)|docker\s+rm)/i;
    if (highRisk.test(command)) return 'high';
    if (medRisk.test(command)) return 'medium';
    return 'low';
  }

  getStatus() {
    return {
      enabled: this.enabled,
      subscriptions: this.subscriptions.size,
    };
  }
}

module.exports = { PushNotifier };
