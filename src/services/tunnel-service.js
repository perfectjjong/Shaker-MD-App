/**
 * Tunnel Service - 외부 접속용 터널 자동 생성
 * localtunnel을 사용하여 로컬 서버를 인터넷에 공개
 */

class TunnelService {
  constructor(port, options = {}) {
    this.port = port;
    this.subdomain = options.subdomain || null;
    this.tunnel = null;
    this.url = null;
    this.retryCount = 0;
    this.maxRetries = 5;
    this.running = false;
  }

  /**
   * 터널 시작
   * @returns {Promise<string>} 외부 접속 URL
   */
  async start() {
    const localtunnel = require('localtunnel');

    this.running = true;
    const opts = { port: this.port };
    if (this.subdomain) {
      opts.subdomain = this.subdomain;
    }

    try {
      this.tunnel = await localtunnel(opts);
      this.url = this.tunnel.url;
      this.retryCount = 0;

      console.log(`[Tunnel] 외부 접속 URL: ${this.url}`);

      // 터널 닫힘 이벤트 - 자동 재연결
      this.tunnel.on('close', () => {
        console.log('[Tunnel] 터널 연결 종료');
        if (this.running) {
          this._reconnect();
        }
      });

      // 에러 이벤트
      this.tunnel.on('error', (err) => {
        console.error('[Tunnel] 에러:', err.message);
        if (this.running) {
          this._reconnect();
        }
      });

      return this.url;
    } catch (err) {
      console.error('[Tunnel] 시작 실패:', err.message);
      if (this.running && this.retryCount < this.maxRetries) {
        return this._reconnect();
      }
      throw err;
    }
  }

  /**
   * 자동 재연결 (지수 백오프)
   */
  async _reconnect() {
    this.retryCount++;
    if (this.retryCount > this.maxRetries) {
      console.error(`[Tunnel] 최대 재시도 횟수(${this.maxRetries}) 초과 - 터널 비활성화`);
      this.running = false;
      return null;
    }

    const delay = Math.min(2000 * Math.pow(2, this.retryCount - 1), 30000);
    console.log(`[Tunnel] ${delay / 1000}초 후 재연결 시도 (${this.retryCount}/${this.maxRetries})...`);

    await new Promise(resolve => setTimeout(resolve, delay));

    if (!this.running) return null;

    try {
      const url = await this.start();
      return url;
    } catch (err) {
      return null;
    }
  }

  /**
   * 터널 중지
   */
  stop() {
    this.running = false;
    if (this.tunnel) {
      this.tunnel.close();
      this.tunnel = null;
      this.url = null;
      console.log('[Tunnel] 터널 종료');
    }
  }

  /**
   * 현재 URL 반환
   */
  getUrl() {
    return this.url;
  }
}

module.exports = { TunnelService };
