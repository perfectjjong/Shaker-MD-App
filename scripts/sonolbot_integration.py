"""
sonolbot_integration.py
=======================
소놀봇(Python Telegram 봇)에서 Shaker-MD-App executor-client.js를 통합하는
참고 코드 스니펫입니다.

사용 방법:
1. 이 파일을 소놀봇 프로젝트에 복사하세요.
2. ShakerExecutorBridge를 봇 초기화 시 생성하고 start()를 호출하세요.
3. 환경변수 또는 코드에서 설정값을 조정하세요.

필요 패키지:
    pip install aiohttp python-telegram-bot  # 또는 telebot 등
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

logger = logging.getLogger(__name__)

# ─── 설정 ─────────────────────────────────────────────────

SHAKER_SERVER_URL = os.getenv("SHAKER_SERVER_URL", "http://localhost:3847")
EXECUTOR_NODE_SCRIPT = os.getenv(
    "EXECUTOR_NODE_SCRIPT",
    os.path.join(os.path.dirname(__file__), "executor-client.js"),
)
WEBHOOK_PORT = int(os.getenv("EXECUTOR_WEBHOOK_PORT", "8765"))
WEBHOOK_PATH = os.getenv("EXECUTOR_WEBHOOK_PATH", "/executor-webhook")

# Telegram 알림을 보낼 채팅 ID (소놀봇 주인 ID)
NOTIFY_CHAT_ID = os.getenv("NOTIFY_CHAT_ID", "")

# ─── Webhook 수신 서버 ─────────────────────────────────────


class WebhookHandler(BaseHTTPRequestHandler):
    """executor-client.js가 작업 완료 시 POST하는 webhook 수신기."""

    callback = None  # ShakerExecutorBridge에서 주입

    def do_POST(self):
        if self.path != WEBHOOK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.end_headers()

        try:
            data = json.loads(body)
            if WebhookHandler.callback:
                asyncio.run_coroutine_threadsafe(
                    WebhookHandler.callback(data),
                    WebhookHandler.loop,
                )
        except Exception as e:
            logger.error(f"[Webhook] 파싱 오류: {e}")

    def log_message(self, format, *args):
        pass  # HTTP 접속 로그 숨김


# ─── 통합 브릿지 ───────────────────────────────────────────


class ShakerExecutorBridge:
    """
    소놀봇에서 executor-client.js를 시작하고,
    작업 완료 알림을 Telegram으로 전달하는 브릿지.

    사용 예시 (python-telegram-bot v20+):
    ----------------------------------------
    from sonolbot_integration import ShakerExecutorBridge

    async def main():
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        bridge = ShakerExecutorBridge(bot=application.bot)
        await bridge.start()

        # 봇 실행
        await application.run_polling()

        await bridge.stop()
    ----------------------------------------
    """

    def __init__(self, bot=None, notify_chat_id: str = NOTIFY_CHAT_ID):
        """
        bot: python-telegram-bot의 Bot 객체 (없으면 알림 전송 안 함)
        notify_chat_id: 알림 수신 Telegram chat_id
        """
        self.bot = bot
        self.notify_chat_id = notify_chat_id
        self._executor_proc: subprocess.Popen | None = None
        self._webhook_server: HTTPServer | None = None
        self._webhook_thread: Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self):
        """브릿지 시작: webhook 서버 + executor 프로세스 실행."""
        self._loop = asyncio.get_event_loop()

        # 1. Webhook 수신 서버 시작
        self._start_webhook_server()

        # 2. executor-client.js 시작
        self._start_executor()

        logger.info("[ShakerBridge] 시작 완료")

    async def stop(self):
        """브릿지 종료."""
        if self._executor_proc and self._executor_proc.poll() is None:
            self._executor_proc.terminate()
            try:
                self._executor_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._executor_proc.kill()
            logger.info("[ShakerBridge] executor 프로세스 종료")

        if self._webhook_server:
            self._webhook_server.shutdown()
            logger.info("[ShakerBridge] webhook 서버 종료")

    def _start_webhook_server(self):
        """백그라운드 스레드에서 webhook HTTP 서버 실행."""
        WebhookHandler.callback = self._on_task_event
        WebhookHandler.loop = self._loop

        self._webhook_server = HTTPServer(("127.0.0.1", WEBHOOK_PORT), WebhookHandler)
        self._webhook_thread = Thread(
            target=self._webhook_server.serve_forever, daemon=True
        )
        self._webhook_thread.start()
        logger.info(f"[ShakerBridge] Webhook 서버 시작: 127.0.0.1:{WEBHOOK_PORT}{WEBHOOK_PATH}")

    def _start_executor(self):
        """executor-client.js를 subprocess로 실행."""
        webhook_url = f"http://127.0.0.1:{WEBHOOK_PORT}{WEBHOOK_PATH}"

        env = os.environ.copy()
        env["EXECUTOR_WEBHOOK_URL"] = webhook_url
        env["EXECUTOR_API_URL"] = SHAKER_SERVER_URL
        # 필요 시 추가 환경변수 설정
        # env["EXECUTOR_ID"] = "executor-sonolbot"
        # env["API_KEY"] = "your-api-key"

        node_cmd = "node"
        self._executor_proc = subprocess.Popen(
            [node_cmd, EXECUTOR_NODE_SCRIPT],
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        logger.info(f"[ShakerBridge] executor-client.js 시작 (PID: {self._executor_proc.pid})")

    async def _on_task_event(self, data: dict):
        """작업 완료/실패 webhook 수신 시 호출되는 콜백."""
        task_id = data.get("taskId", "")[:8]
        title = data.get("title", "작업")
        status = data.get("status", "unknown")
        exit_code = data.get("exitCode", -1)
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        error = data.get("error")
        duration_ms = data.get("durationMs")

        logger.info(f"[ShakerBridge] 작업 이벤트: {task_id}... ({status})")

        if self.bot and self.notify_chat_id:
            msg = self._format_telegram_message(
                task_id, title, status, exit_code, stdout, stderr, error, duration_ms
            )
            try:
                await self.bot.send_message(
                    chat_id=self.notify_chat_id,
                    text=msg,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"[ShakerBridge] Telegram 전송 실패: {e}")

    @staticmethod
    def _format_telegram_message(
        task_id, title, status, exit_code, stdout, stderr, error, duration_ms
    ) -> str:
        icon = "✅" if status == "completed" else "❌"
        duration = f"{duration_ms / 1000:.1f}s" if duration_ms else "-"

        lines = [
            f"{icon} <b>{title}</b>",
            f"<code>ID: {task_id}...</code>",
            f"상태: <b>{status}</b>  |  종료코드: <code>{exit_code}</code>  |  소요: {duration}",
        ]

        if stdout:
            preview = stdout[:800] + ("..." if len(stdout) > 800 else "")
            lines.append(f"\n<b>출력:</b>\n<pre>{_escape_html(preview)}</pre>")

        if error:
            lines.append(f"\n<b>오류:</b> {_escape_html(str(error))}")
        elif stderr:
            preview = stderr[:300] + ("..." if len(stderr) > 300 else "")
            lines.append(f"\n<b>stderr:</b>\n<pre>{_escape_html(preview)}</pre>")

        return "\n".join(lines)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─── 단독 실행 테스트 ──────────────────────────────────────

if __name__ == "__main__":
    """
    소놀봇 없이 브릿지만 단독 실행해 테스트합니다.
    executor-client.js의 webhook 콜백을 콘솔에 출력합니다.
    """
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    class _ConsoleBridge(ShakerExecutorBridge):
        async def _on_task_event(self, data):
            print("\n[TEST] Webhook 수신:")
            print(json.dumps(data, ensure_ascii=False, indent=2))

    async def _test():
        bridge = _ConsoleBridge()
        await bridge.start()
        print("Ctrl+C로 종료")
        try:
            while True:
                await asyncio.sleep(1)
                if bridge._executor_proc and bridge._executor_proc.poll() is not None:
                    print("[TEST] executor 프로세스가 종료되었습니다.")
                    break
        except KeyboardInterrupt:
            pass
        finally:
            await bridge.stop()

    asyncio.run(_test())
