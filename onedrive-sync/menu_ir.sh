#!/bin/bash
# IR 주간 자동요리 — run_all ir ×2회 (재고 1주 지연 함정 대응, 확정 절차).
set -u
D="$(cd "$(dirname "$0")" && pwd)"
LIST="${SYNC_MATCHED_LIST:-}"
[ -f "$LIST" ] || exit 0
# 99. Inbox 는 라우터(mail_inbox_router.sh)가 해체·배치까지 책임진다. 여기서 또 요리하면
# 아직 분류도 안 된 상태로 run_all 이 돌고 알림도 중복된다(OR 메뉴와 동일 규칙).
HOT=$(grep -v "/99\. Inbox/" "$LIST" || true)
[ -z "$HOT" ] && exit 0
printf '%s\n' "$HOT" > "$LIST.hot" && LIST="$LIST.hot"
n=$(wc -l < "$LIST")
"$D/tg_notify.sh" "🍳 IR 주간 파일 ${n}건 도착 — run_all ir ×2 자동 실행 시작
$(sed 's/^/ · /' "$LIST" | head -6)"
PY=/home/ubuntu/ai_env/bin/python3
RA="/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/run_all.py"
LOG=/home/ubuntu/onedrive_menu.log
{
  echo "=== $(date '+%F %T') IR run_all x2 (${n}건) ==="
  "$PY" "$RA" ir && "$PY" "$RA" ir
} >> "$LOG" 2>&1
rc=$?
if [ $rc -eq 0 ]; then
    "$D/tg_notify.sh" "✅ IR 파이프라인 완료 (run_all ir 2회 — 재고 반영 포함)"
else
    "$D/tg_notify.sh" "❌ IR 파이프라인 실패 (exit $rc) — onedrive_menu.log 확인 필요"
fi
exit $rc
