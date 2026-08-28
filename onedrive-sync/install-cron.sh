#!/bin/bash
# OneDrive → OCI 동기화 cron 등록 (멱등 — 여러 번 실행해도 중복되지 않는다)
#
#   ./install-cron.sh              # 기본: 5분마다
#   ./install-cron.sh "*/2 * * * *"  # 주기 직접 지정
#   ./install-cron.sh --remove     # 등록 해제
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MARKER="# shaker-onedrive-sync"
SYNC="$SCRIPT_DIR/sync-onedrive-to-oci.sh"
LOG="${ONEDRIVE_SYNC_LOG:-/home/ubuntu/onedrive_sync.log}"

current="$(crontab -l 2>/dev/null || true)"
cleaned="$(printf '%s\n' "$current" | grep -vF "$MARKER" || true)"

if [ "${1:-}" = "--remove" ]; then
    printf '%s\n' "$cleaned" | grep -v '^$' | crontab - || crontab -r
    echo "cron 등록 해제됨"
    exit 0
fi

SCHEDULE="${1:-*/5 * * * *}"

[ -x "$SYNC" ] || { echo "실행 권한 없음: $SYNC  (chmod +x 하십시오)" >&2; exit 1; }

{
    printf '%s\n' "$cleaned" | grep -v '^$' || true
    printf '%s %s >> %s 2>&1 %s\n' "$SCHEDULE" "$SYNC" "$LOG" "$MARKER"
} | crontab -

echo "cron 등록 완료: $SCHEDULE"
echo "  스크립트: $SYNC"
echo "  로그:     $LOG"
crontab -l | grep -F "$MARKER"
