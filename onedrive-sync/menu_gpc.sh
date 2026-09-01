#!/bin/bash
# GPC 자동요리 — update_gpc_monthly (신규월 없으면 스스로 무변경 종료하는 안전 설계).
set -u
D="$(cd "$(dirname "$0")" && pwd)"
LIST="${SYNC_MATCHED_LIST:-}"
[ -f "$LIST" ] || exit 0
n=$(wc -l < "$LIST")
LOG=/home/ubuntu/onedrive_menu.log
{
  echo "=== $(date '+%F %T') GPC update (${n}건) ==="
  /home/ubuntu/ai_env/bin/python3 "/home/ubuntu/2026/10. Automation/update_gpc_monthly.py"
} >> "$LOG" 2>&1
rc=$?
if [ $rc -eq 0 ]; then "$D/tg_notify.sh" "✅ GPC 파일 ${n}건 도착 → update_gpc_monthly 완료 (신규월 없으면 무변경)"
else "$D/tg_notify.sh" "❌ GPC 업데이트 실패 (exit $rc) — onedrive_menu.log 확인"; fi
exit $rc
