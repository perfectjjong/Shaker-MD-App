#!/bin/bash
# 요리 없는 폴더 공용 알림 — "무엇이 왔는지"만 통지.
set -u
D="$(cd "$(dirname "$0")" && pwd)"
LIST="${SYNC_MATCHED_LIST:-}"
[ -f "$LIST" ] || exit 0
n=$(wc -l < "$LIST")
"$D/tg_notify.sh" "📦 OneDrive→서버: ${SYNC_MATCHED_PREFIX:-?} ${n}건 도착 (자동요리 없음)
$(sed 's/^/ · /' "$LIST" | head -6)"
