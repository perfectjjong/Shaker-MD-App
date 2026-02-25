const TelegramBot = require('node-telegram-bot-api');

class TelegramNotifier {
  constructor(token, chatId, approvalManager) {
    this.chatId = chatId;
    this.approvalManager = approvalManager;
    this.messageMap = new Map(); // approvalId -> telegramMessageId

    this.bot = new TelegramBot(token, { polling: true });
    this._setupHandlers();
  }

  _setupHandlers() {
    // 콜백 쿼리 (인라인 버튼 클릭)
    this.bot.on('callback_query', async (query) => {
      const [action, approvalId] = query.data.split(':');

      if (action === 'approve' || action === 'reject') {
        const status = action === 'approve' ? 'approved' : 'rejected';
        const success = this.approvalManager.resolve(approvalId, status);

        if (success) {
          const emoji = action === 'approve' ? '✅' : '❌';
          const label = action === 'approve' ? '승인됨' : '거부됨';
          await this.bot.answerCallbackQuery(query.id, {
            text: `${emoji} ${label}`,
          });
          await this._updateMessage(approvalId, status);
        } else {
          await this.bot.answerCallbackQuery(query.id, {
            text: '⏳ 이미 처리된 요청입니다',
          });
        }
      }
    });

    // /start 명령어
    this.bot.onText(/\/start/, (msg) => {
      const chatId = msg.chat.id;
      this.bot.sendMessage(
        chatId,
        `🤖 *Claude Code Mobile Approver*\n\n` +
        `Chat ID: \`${chatId}\`\n\n` +
        `이 Chat ID를 \`.env\` 파일의 \`TELEGRAM_CHAT_ID\`에 설정하세요.\n\n` +
        `명령어:\n` +
        `/pending - 대기 중인 승인 목록\n` +
        `/history - 최근 처리 내역\n` +
        `/approveall - 대기 중인 모든 요청 승인\n` +
        `/status - 서버 상태`,
        { parse_mode: 'Markdown' }
      );
    });

    // /pending - 대기 중 목록
    this.bot.onText(/\/pending/, (msg) => {
      const pending = this.approvalManager.getPending();
      if (pending.length === 0) {
        this.bot.sendMessage(msg.chat.id, '✨ 대기 중인 승인 요청이 없습니다.');
        return;
      }
      let text = `📋 *대기 중인 승인 (${pending.length}건)*\n\n`;
      for (const p of pending) {
        const elapsed = Math.round((Date.now() - new Date(p.createdAt)) / 1000);
        text += `• \`${p.command.slice(0, 60)}\`\n  ⏱ ${elapsed}초 전\n\n`;
      }
      this.bot.sendMessage(msg.chat.id, text, { parse_mode: 'Markdown' });
    });

    // /history - 처리 내역
    this.bot.onText(/\/history/, (msg) => {
      const history = this.approvalManager.getHistory(10);
      if (history.length === 0) {
        this.bot.sendMessage(msg.chat.id, '📭 처리 내역이 없습니다.');
        return;
      }
      let text = `📜 *최근 처리 내역*\n\n`;
      for (const h of history) {
        const emoji = h.status === 'approved' ? '✅' : h.status === 'rejected' ? '❌' : '⏳';
        text += `${emoji} \`${h.command.slice(0, 50)}\`\n`;
      }
      this.bot.sendMessage(msg.chat.id, text, { parse_mode: 'Markdown' });
    });

    // /approveall - 모두 승인
    this.bot.onText(/\/approveall/, (msg) => {
      const pending = this.approvalManager.getPending();
      if (pending.length === 0) {
        this.bot.sendMessage(msg.chat.id, '✨ 대기 중인 승인 요청이 없습니다.');
        return;
      }
      let count = 0;
      for (const p of pending) {
        if (this.approvalManager.resolve(p.id, 'approved')) count++;
      }
      this.bot.sendMessage(msg.chat.id, `✅ ${count}건 모두 승인되었습니다.`);
    });

    // /status - 서버 상태
    this.bot.onText(/\/status/, (msg) => {
      const pending = this.approvalManager.getPending();
      const uptime = process.uptime();
      const hours = Math.floor(uptime / 3600);
      const mins = Math.floor((uptime % 3600) / 60);
      this.bot.sendMessage(
        msg.chat.id,
        `🖥 *서버 상태*\n\n` +
        `• 가동 시간: ${hours}시간 ${mins}분\n` +
        `• 대기 중: ${pending.length}건\n` +
        `• 메모리: ${Math.round(process.memoryUsage().rss / 1024 / 1024)}MB`,
        { parse_mode: 'Markdown' }
      );
    });
  }

  /**
   * 승인 요청 알림 전송
   */
  async sendApprovalRequest(approval) {
    const text =
      `🔔 *Claude Code 승인 요청*\n\n` +
      `📂 \`${approval.workdir || 'N/A'}\`\n` +
      `🔧 도구: \`${approval.tool}\`\n\n` +
      `\`\`\`\n${approval.command.slice(0, 500)}\n\`\`\`\n\n` +
      `⏱ 대기 중...`;

    const msg = await this.bot.sendMessage(this.chatId, text, {
      parse_mode: 'Markdown',
      reply_markup: {
        inline_keyboard: [
          [
            { text: '✅ 승인', callback_data: `approve:${approval.id}` },
            { text: '❌ 거부', callback_data: `reject:${approval.id}` },
          ],
        ],
      },
    });

    this.messageMap.set(approval.id, msg.message_id);
  }

  /**
   * 처리 완료 시 메시지 업데이트
   */
  async _updateMessage(approvalId, status) {
    const messageId = this.messageMap.get(approvalId);
    if (!messageId) return;

    const emoji = status === 'approved' ? '✅' : status === 'rejected' ? '❌' : '⏳';
    const label = status === 'approved' ? '승인됨' : status === 'rejected' ? '거부됨' : '타임아웃';

    try {
      await this.bot.editMessageReplyMarkup(
        { inline_keyboard: [[{ text: `${emoji} ${label}`, callback_data: 'noop' }]] },
        { chat_id: this.chatId, message_id: messageId }
      );
    } catch (e) {
      // 메시지가 이미 변경된 경우 무시
    }

    this.messageMap.delete(approvalId);
  }
}

module.exports = { TelegramNotifier };
