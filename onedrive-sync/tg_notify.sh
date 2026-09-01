#!/bin/bash
# 텔레그램 알림 헬퍼 — $1 = 메시지. sonolbot .env의 봇/채팅ID 사용.
MSG="$1"
/home/ubuntu/ai_env/bin/python3 - "$MSG" <<'PY'
import sys, os
sys.path.insert(0, '/home/ubuntu/sonolbot')
from dotenv import load_dotenv; load_dotenv('/home/ubuntu/sonolbot/.env')
chat = os.getenv('TELEGRAM_ALLOWED_USERS','').split(',')[0].strip()
if chat:
    from telegram_sender import send_message_sync
    send_message_sync(int(chat), sys.argv[1])
PY
