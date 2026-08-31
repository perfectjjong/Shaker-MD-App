#!/bin/bash
# eXtra All Brand 자동요리 — `05. All Brand/*.xlsb` 도착 시 eXtra 대시보드 4종 갱신.
#   extra-sellout / extra-ms / extra-ms-value  ← update_sellout_dashboard.py
#   extra-mgmt / extra-ac-business             ← update_stock_dashboard.py
#
# 2026-08-31 신설. 그 전에는 이 원본이 와도 menu_or.sh 의 OR 4단 체인만 돌아
# eXtra 대시보드는 손으로 돌려야 했다(그래서 4개월 정지도 못 봤다).
#
# ⚠️ 재고 생성이 5분 넘게 걸린다. OneDrive cron 은 1분 주기라 겹칠 수 있어 flock 으로 막는다.
#    이미 돌고 있으면 조용히 종료 — 다음 파일 도착분에 어차피 최신 상태로 다시 돈다.
# ⚠️ 두 스크립트 모두 내부에서 git push 까지 한다. 순차 실행이라 서로 충돌하지 않는다.
set -u
D="$(cd "$(dirname "$0")" && pwd)"
PY=/home/ubuntu/ai_env/bin/python3
EX="/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/00. OR/02. eXtra"
LOG=/home/ubuntu/onedrive_menu.log
LOCK=/home/ubuntu/.extra_allbrand.lock

exec 9>"$LOCK"
if ! flock -n 9; then
    echo "[extra_allbrand] 이미 실행 중 — 건너뜀" >> "$LOG"
    exit 0
fi

n="${SYNC_MATCHED_COUNT:-${1:-?}}"
"$D/tg_notify.sh" "🍳 eXtra All Brand 원본 ${n}건 도착 — 대시보드 4종 갱신 시작"

{
  echo "=== $(date '+%F %T') eXtra All Brand chain (${n}건) ==="
  cd "$EX" || exit 1
  echo "--- [1/2] sellout (extra-sellout / extra-ms / extra-ms-value)"
  "$PY" update_sellout_dashboard.py --force
  rc1=$?
  echo "--- [2/2] stock (extra-mgmt / extra-ac-business)"
  "$PY" update_stock_dashboard.py
  rc2=$?
  echo "rc1=$rc1 rc2=$rc2"
  exit $(( rc1 != 0 || rc2 != 0 ))
} >> "$LOG" 2>&1
rc=$?

# 배포 검증 — push 가 rc=0 으로 조용히 통과하는 사고가 있었다. 원격을 직접 조회한다.
# ⚠️ `git fetch origin main` 은 FETCH_HEAD 만 갱신하고 origin/main 추적 ref 는 그대로 둔다.
#    그래서 `git rev-parse origin/main` 이 stale 값을 돌려줘, 멀쩡히 배포된 것을 '미반영'으로
#    오탐했다(2026-08-31 첫 실행에서 실제로 겪음). ls-remote 로 원격 ref 를 직접 읽는다.
L=$(cd /home/ubuntu/Shaker-MD-App && git rev-parse HEAD 2>/dev/null)
R=$(cd /home/ubuntu/Shaker-MD-App && git ls-remote origin main 2>/dev/null | cut -f1)

if [ $rc -eq 0 ] && [ "$L" = "$R" ]; then
    "$D/tg_notify.sh" "✅ eXtra 4종 갱신 완료 (검증: 체인 2/2 · 원격 ref 일치 ${L:0:8})"
elif [ $rc -eq 0 ]; then
    "$D/tg_notify.sh" "⚠️ eXtra 4종 생성은 끝났으나 **원격 미반영** (local ${L:0:8} ≠ remote ${R:0:8}) — 확인 필요"
else
    "$D/tg_notify.sh" "❌ eXtra 체인 실패 (exit $rc) — onedrive_menu.log 확인 필요"
fi
exit $rc
