#!/bin/bash
# Sell Thru Raw Data 라우터 — RSM FCST 또는 OUD 도착 시 full refresh, 나머지는 알림만.
# ⚠️ 이전 주석("OUD는 새벽 정기 파이프라인이 반영")은 사실이 아니었다. 새벽 03:00 가드는
#    **동결 감지 시에만** refresh 를 돌리므로, OUD 가 새로 와도 STP 는 갱신되지 않는다
#    (2026-08-30 실측: 29-AUG 입고 후에도 대시보드가 22-AUG 에 정지). → OUD 도 요리 대상.
set -u
D="$(cd "$(dirname "$0")" && pwd)"
LIST="${SYNC_MATCHED_LIST:-}"
[ -f "$LIST" ] || exit 0
RSM=$(grep -E "/06\. RSM FCST/" "$LIST" || true)
OUD=$(grep -E "/05\. OUD/" "$LIST" || true)
HOT=$(printf '%s\n%s' "$RSM" "$OUD" | grep -v '^$' || true)
OTHER=$(grep -vE "/06\. RSM FCST/|/05\. OUD/" "$LIST" || true)
if [ -n "$OTHER" ]; then
    "$D/tg_notify.sh" "📦 OneDrive→서버: Sell Thru raw $(echo "$OTHER" | wc -l)건 도착 (알림만)
$(echo "$OTHER" | sed 's/^/ · /' | head -5)"
fi
[ -z "$HOT" ] && exit 0
WHAT=$([ -n "$RSM" ] && echo "RSM FCST" || echo "OUD")
"$D/tg_notify.sh" "🍳 ${WHAT} 도착 — refresh_dashboard full refresh 시작"
LOG=/home/ubuntu/onedrive_menu.log
{
  echo "=== $(date '+%F %T') ${WHAT} full refresh ==="
  cd "/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/01. Python Code" \
    && /home/ubuntu/ai_env/bin/python3 refresh_dashboard.py
} >> "$LOG" 2>&1
rc=$?
if [ $rc -eq 0 ]; then "$D/tg_notify.sh" "✅ ${WHAT} 반영 완료 (full refresh)"
else "$D/tg_notify.sh" "❌ ${WHAT} refresh 실패 (exit $rc) — onedrive_menu.log 확인"; fi
exit $rc
