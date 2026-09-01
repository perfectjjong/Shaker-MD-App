#!/bin/bash
# OR 주간 자동요리 — 셀아웃/재고 raw 도착 시 OR 4단 체인 실행.
# Mega·Promoter Shop Mapping·월간(Monthly)은 요리 대상 아님 → 알림만 (월마감 수동 정책).
set -u
D="$(cd "$(dirname "$0")" && pwd)"
LIST="${SYNC_MATCHED_LIST:-}"
[ -f "$LIST" ] || exit 0
HOT=$(grep -vE "/03\. Mega/|/04\. Promoter|/02\. Monthly/|/99\. Inbox/" "$LIST" || true)
if [ -z "$HOT" ]; then
    # 99. Inbox 전용 회차(라우터가 별도 처리·통지)면 조용히 종료 — 중복 알림 금지
    grep -vq "/99\. Inbox/" "$LIST" || exit 0
    n=$(wc -l < "$LIST")
    "$D/tg_notify.sh" "📦 OneDrive→서버: OR raw ${n}건 도착 (Mega/월간 계열 — 자동요리 없음)"
    exit 0
fi
n=$(echo "$HOT" | wc -l)
"$D/tg_notify.sh" "🍳 OR 주간 파일 ${n}건 도착 — OR 체인 자동 실행 시작
$(echo "$HOT" | sed 's/^/ · /' | head -6)"
PY=/home/ubuntu/ai_env/bin/python3
OR="/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/00. OR/01. Python Code"
B2C="/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/02. B2C/01. Python Code"
LOG=/home/ubuntu/onedrive_menu.log
{
  echo "=== $(date '+%F %T') OR chain (${n}건) ==="
  cd "$OR" && "$PY" or_weekly_consolidator.py && "$PY" or_unified_dashboard_generator.py \
    && "$PY" generate_or_channel_from_unified.py \
    && cd "$B2C" && "$PY" b2c_unified_dashboard_generator.py
} >> "$LOG" 2>&1
rc=$?
if [ $rc -eq 0 ]; then
    "$D/tg_notify.sh" "✅ OR 체인 완료 (consolidator→unified→channel→b2c 4/4)"
else
    "$D/tg_notify.sh" "❌ OR 체인 실패 (exit $rc) — onedrive_menu.log 확인 필요"
fi
exit $rc
