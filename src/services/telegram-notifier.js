const TelegramBot = require('node-telegram-bot-api');
const https = require('https');
const http = require('http');
const { URL } = require('url');
const { assessRisk } = require('./risk-assessor');

class TelegramNotifier {
  constructor(token, chatId, approvalManager, options = {}) {
    this.chatId = chatId;
    this.approvalManager = approvalManager;
    this.messageMap = new Map(); // approvalId -> { messageId, approval }
    this.stats = { approved: 0, rejected: 0, timeout: 0 };
    this.connected = false;
    this._token = token;
    this._options = options;
    this._consecutiveErrors = 0;
    this._maxConsecutiveErrors = 5;
  }

  /**
   * Telegram API 서버 연결 가능 여부를 사전 검사
   */
  static async checkConnectivity(token, proxyUrl) {
    const testUrl = `https://api.telegram.org/bot${token}/getMe`;

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        resolve({ ok: false, error: '연결 타임아웃 (5초)' });
      }, 5000);

      try {
        const urlObj = new URL(testUrl);

        const requestOptions = {
          hostname: urlObj.hostname,
          path: urlObj.pathname,
          method: 'GET',
          timeout: 5000,
        };

        // 프록시 설정이 있으면 프록시를 통해 연결
        if (proxyUrl) {
          const proxy = new URL(proxyUrl);
          requestOptions.hostname = proxy.hostname;
          requestOptions.port = proxy.port;
          requestOptions.path = testUrl;
          requestOptions.headers = {
            Host: urlObj.hostname,
          };
          if (proxy.username) {
            requestOptions.headers['Proxy-Authorization'] =
              'Basic ' + Buffer.from(`${proxy.username}:${proxy.password}`).toString('base64');
          }

          const req = http.request(requestOptions, (res) => {
            let data = '';
            res.on('data', (chunk) => (data += chunk));
            res.on('end', () => {
              clearTimeout(timeout);
              try {
                const json = JSON.parse(data);
                if (json.ok) {
                  resolve({ ok: true, botName: json.result.username });
                } else {
                  resolve({ ok: false, error: `Telegram API 오류: ${json.description}` });
                }
              } catch {
                resolve({ ok: false, error: `응답 파싱 실패 (HTTP ${res.statusCode})` });
              }
            });
          });

          req.on('error', (err) => {
            clearTimeout(timeout);
            resolve({ ok: false, error: `프록시 연결 실패: ${err.message}` });
          });

          req.on('timeout', () => {
            req.destroy();
            clearTimeout(timeout);
            resolve({ ok: false, error: '프록시 연결 타임아웃' });
          });

          req.end();
        } else {
          // 직접 연결
          const req = https.get(testUrl, { timeout: 5000 }, (res) => {
            let data = '';
            res.on('data', (chunk) => (data += chunk));
            res.on('end', () => {
              clearTimeout(timeout);
              try {
                const json = JSON.parse(data);
                if (json.ok) {
                  resolve({ ok: true, botName: json.result.username });
                } else {
                  resolve({ ok: false, error: `Telegram API 오류: ${json.description}` });
                }
              } catch {
                resolve({ ok: false, error: `응답 파싱 실패 (HTTP ${res.statusCode})` });
              }
            });
          });

          req.on('error', (err) => {
            clearTimeout(timeout);
            const msg = err.message || String(err);
            if (msg.includes('403') || msg.includes('tunneling')) {
              resolve({
                ok: false,
                error: '네트워크 프록시가 api.telegram.org 연결을 차단 중 (403)',
                blocked: true,
              });
            } else if (msg.includes('EAI_AGAIN') || msg.includes('ENOTFOUND') || msg.includes('getaddrinfo')) {
              resolve({
                ok: false,
                error: 'api.telegram.org DNS 조회 실패 (네트워크 차단 또는 DNS 미설정)',
                blocked: true,
              });
            } else {
              resolve({ ok: false, error: `연결 실패: ${msg}` });
            }
          });

          req.on('timeout', () => {
            req.destroy();
            clearTimeout(timeout);
            resolve({ ok: false, error: '연결 타임아웃' });
          });
        }
      } catch (err) {
        clearTimeout(timeout);
        resolve({ ok: false, error: `검사 중 오류: ${err.message}` });
      }
    });
  }

  /**
   * 봇 시작 (연결 검사 후)
   */
  async start() {
    // 프록시 설정 구성 + callback_query 명시적 수신 설정
    const botOptions = {
      polling: {
        params: {
          allowed_updates: ['message', 'callback_query'],
        },
      },
    };

    if (this._options.proxy) {
      botOptions.request = {
        proxy: this._options.proxy,
      };
      console.log(`[Telegram] 프록시 사용: ${this._options.proxy}`);
    }

    this.bot = new TelegramBot(this._token, botOptions);

    this.bot.on('polling_error', (err) => {
      this._consecutiveErrors++;

      // 연속 에러 횟수에 따라 로그 레벨 조절
      if (this._consecutiveErrors <= 3) {
        console.warn(`[Telegram] 폴링 오류 (${this._consecutiveErrors}/${this._maxConsecutiveErrors}):`, err.message);
      }

      // 연속 에러 초과 시 폴링 재시작 (중지하지 않음)
      if (this._consecutiveErrors >= this._maxConsecutiveErrors) {
        console.error(`[Telegram] 연속 ${this._maxConsecutiveErrors}회 실패 - 폴링 재시작 시도...`);
        this._consecutiveErrors = 0;
        this.bot.stopPolling().then(() => {
          setTimeout(() => {
            if (this.connected !== false) {
              this.bot.startPolling({
                params: { allowed_updates: ['message', 'callback_query'] },
              });
              console.log('[Telegram] 폴링 재시작 완료');
            }
          }, 3000);
        }).catch(() => {});
      }
    });

    // 정상 수신 시 에러 카운터 리셋
    this.bot.on('message', () => {
      this._consecutiveErrors = 0;
      this.connected = true;
    });

    this._setupHandlers();

    // 타임아웃 알림 연동
    this.approvalManager.on('resolved', (record) => {
      if (record.status === 'timeout') {
        this._notifyTimeout(record);
        this.stats.timeout++;
      } else if (record.status === 'approved') {
        this.stats.approved++;
      } else if (record.status === 'rejected') {
        this.stats.rejected++;
      }
    });

    this.connected = true;
    console.log('[Telegram] callback_query 수신 활성화 완료');
    return this;
  }

  /**
   * 연결 상태 정보
   */
  getStatus() {
    return {
      connected: this.connected,
      consecutiveErrors: this._consecutiveErrors,
      maxErrors: this._maxConsecutiveErrors,
      stats: { ...this.stats },
      proxy: this._options.proxy || null,
    };
  }

  _setupHandlers() {
    // 콜백 쿼리 (인라인 버튼 클릭)
    this.bot.on('callback_query', async (query) => {
      // 에러 카운터 리셋
      this._consecutiveErrors = 0;
      this.connected = true;

      try {
        const data = query.data || '';
        console.log(`[Telegram] 콜백 수신: ${data}`);

        if (data === 'noop') {
          await this.bot.answerCallbackQuery(query.id).catch(() => {});
          return;
        }

        const colonIdx = data.indexOf(':');
        if (colonIdx === -1) {
          await this.bot.answerCallbackQuery(query.id).catch(() => {});
          return;
        }

        const action = data.slice(0, colonIdx);
        const approvalId = data.slice(colonIdx + 1);

        if (action === 'approve' || action === 'reject') {
          const status = action === 'approve' ? 'approved' : 'rejected';
          const emoji = action === 'approve' ? '✅' : '❌';
          const label = action === 'approve' ? '승인됨' : '거부됨';

          console.log(`[Telegram] ${label} 처리 시도: ${approvalId.slice(0, 8)}...`);

          const success = this.approvalManager.resolve(approvalId, status);

          // 항상 콜백 응답 (사용자에게 즉시 피드백)
          await this.bot.answerCallbackQuery(query.id, {
            text: success ? `${emoji} ${label}` : '⏳ 이미 처리된 요청입니다',
          }).catch((e) => console.error('[Telegram] answerCallbackQuery 실패:', e.message));

          if (success) {
            console.log(`[Telegram] ${label} 성공: ${approvalId.slice(0, 8)}...`);
            await this._updateMessage(approvalId, status);
          } else {
            console.log(`[Telegram] 이미 처리됨: ${approvalId.slice(0, 8)}...`);
            // 이미 처리된 요청이라도 메시지 버튼 비활성화
            await this._disableButtons(query.message, `⏳ 처리 완료`);
          }
        }
      } catch (e) {
        console.error('[Telegram] 콜백 처리 오류:', e.message);
        try {
          await this.bot.answerCallbackQuery(query.id, { text: '⚠️ 처리 중 오류 발생' });
        } catch (_) {}
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
        `• 승인: ${this.stats.approved}건 | 거부: ${this.stats.rejected}건 | 타임아웃: ${this.stats.timeout}건\n` +
        `• 메모리: ${Math.round(process.memoryUsage().rss / 1024 / 1024)}MB`,
        { parse_mode: 'Markdown' }
      );
    });

    // /help - 도움말
    this.bot.onText(/\/help/, (msg) => {
      this.bot.sendMessage(
        msg.chat.id,
        `📖 *명령어 목록*\n\n` +
        `/pending - 대기 중인 승인 목록\n` +
        `/approveall - 모두 승인\n` +
        `/history - 최근 처리 내역\n` +
        `/status - 서버 상태\n` +
        `/help - 이 도움말`,
        { parse_mode: 'Markdown' }
      );
    });
  }

  /**
   * 승인 요청 알림 전송
   */
  async sendApprovalRequest(approval) {
    if (!this.connected) return;

    // 명령어가 길면 잘라서 보여주기
    const cmdDisplay = approval.command.length > 400
      ? approval.command.slice(0, 397) + '...'
      : approval.command;

    // 위험도 태그
    const risk = assessRisk(approval.command);
    const riskLabel = risk === 'high' ? '🔴 위험' : risk === 'medium' ? '🟡 주의' : '🟢 안전';

    const pendingCount = this.approvalManager.getPending().length;
    const queueInfo = pendingCount > 1 ? `\n📬 대기열: ${pendingCount}건` : '';

    const dashboardUrl = process.env.EXTERNAL_URL;
    const dashboardLink = dashboardUrl ? `\n🌐 [대시보드](${dashboardUrl})` : '';

    const text =
      `🔔 *Claude Code 승인 요청*\n\n` +
      `${riskLabel} | 🔧 \`${approval.tool}\`\n` +
      `📂 \`${approval.workdir || 'N/A'}\`${queueInfo}${dashboardLink}\n\n` +
      `\`\`\`\n${cmdDisplay}\n\`\`\`\n\n` +
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

    this.messageMap.set(approval.id, { messageId: msg.message_id, approval });
  }

  /**
   * 타임아웃 알림
   */
  async _notifyTimeout(record) {
    await this._updateMessage(record.id, 'timeout');
    if (!this.connected) return;
    try {
      await this.bot.sendMessage(
        this.chatId,
        `⏳ *타임아웃*\n\n\`${record.command.slice(0, 100)}\`\n\n승인 대기 시간이 초과되었습니다.`,
        { parse_mode: 'Markdown' }
      );
    } catch (e) {
      // 무시
    }
  }

  /**
   * 이미 처리된 요청의 버튼을 비활성화
   */
  async _disableButtons(message, label) {
    if (!message || !message.message_id) return;
    try {
      await this.bot.editMessageReplyMarkup(
        { inline_keyboard: [[{ text: label, callback_data: 'noop' }]] },
        { chat_id: this.chatId, message_id: message.message_id }
      );
    } catch (_) {}
  }

  /**
   * Markdown 특수문자 이스케이프
   */
  _escapeMarkdown(text) {
    return text.replace(/([_*\[\]()~`>#+\-=|{}.!\\])/g, '\\$1');
  }

  /**
   * 처리 완료 시 메시지 업데이트 (텍스트 + 버튼 모두 변경)
   */
  async _updateMessage(approvalId, status) {
    const entry = this.messageMap.get(approvalId);
    if (!entry) return;

    const { messageId, approval } = entry;
    const emoji = status === 'approved' ? '✅' : status === 'rejected' ? '❌' : '⏳';
    const label = status === 'approved' ? '승인됨' : status === 'rejected' ? '거부됨' : '타임아웃';

    const cmdDisplay = approval.command.length > 400
      ? approval.command.slice(0, 397) + '...'
      : approval.command;

    try {
      // HTML 형식 사용 (Markdown보다 특수문자 이슈가 적음)
      const toolEsc = approval.tool.replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));
      const wdEsc = (approval.workdir || 'N/A').replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));
      const cmdEsc = cmdDisplay.replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));

      const risk = assessRisk(approval.command);
      const riskLabel = risk === 'high' ? '🔴 위험' : risk === 'medium' ? '🟡 주의' : '🟢 안전';

      const updatedText =
        `${emoji} <b>${label}</b>\n\n` +
        `${riskLabel} | 🔧 <code>${toolEsc}</code>\n` +
        `📂 <code>${wdEsc}</code>\n\n` +
        `<pre>${cmdEsc}</pre>`;

      await this.bot.editMessageText(updatedText, {
        chat_id: this.chatId,
        message_id: messageId,
        parse_mode: 'HTML',
        reply_markup: {
          inline_keyboard: [[{ text: `${emoji} ${label}`, callback_data: 'noop' }]],
        },
      });
      console.log(`[Telegram] 메시지 업데이트 성공: ${approvalId.slice(0, 8)}...`);
    } catch (e) {
      console.error(`[Telegram] 메시지 업데이트 실패: ${e.message}`);
      // 텍스트 업데이트 실패 시 버튼만이라도 비활성화
      try {
        await this.bot.editMessageReplyMarkup(
          { inline_keyboard: [[{ text: `${emoji} ${label}`, callback_data: 'noop' }]] },
          { chat_id: this.chatId, message_id: messageId }
        );
      } catch (_) {}
    } finally {
      this.messageMap.delete(approvalId);
    }
  }
}

module.exports = { TelegramNotifier };
