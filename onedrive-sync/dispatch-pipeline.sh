#!/bin/bash
# 동기화된 파일 경로를 보고 해당하는 파이프라인만 실행한다.
#
# sync-onedrive-to-oci.sh의 파이프라인 칸에서 호출된다. 폴더 하나를 통째로
# 매핑했을 때, 이번 회차에 무엇이 들어왔는지에 따라 실행할 작업을 고르는 용도다.
#
# 규칙: pipeline-rules.conf  (pipeline-rules.conf.example 참고)
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RULES="${ONEDRIVE_PIPELINE_RULES:-$SCRIPT_DIR/pipeline-rules.conf}"

log() { printf '[dispatch] %s %s\n' "$(date '+%F %T')" "$*"; }

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

if [ -z "${SYNC_FILE_LIST:-}" ] || [ ! -f "$SYNC_FILE_LIST" ]; then
    log "SYNC_FILE_LIST가 없다 — sync-onedrive-to-oci.sh를 통해 호출되어야 한다"
    exit 1
fi

if [ ! -f "$RULES" ]; then
    log "규칙 파일 없음: $RULES  (pipeline-rules.conf.example을 복사해서 만드십시오)"
    exit 1
fi

failed=0
ran=0

while IFS='|' read -r prefix command || [ -n "$prefix" ]; do
    prefix="$(trim "$prefix")"
    case "$prefix" in ''|\#*) continue ;; esac

    command="$(trim "${command:-}")"
    [ -z "$command" ] && continue

    # 이번 회차 파일 중 이 접두사로 시작하는 것만 추린다
    matched="$(mktemp)"
    awk -v p="$prefix" 'index($0, p) == 1' "$SYNC_FILE_LIST" > "$matched"
    matched_count="$(wc -l < "$matched" | tr -d ' ')"

    if [ "$matched_count" -eq 0 ]; then
        rm -f "$matched"
        continue
    fi

    log "[$prefix] ${matched_count}건 → $command"
    rc=0
    SYNC_MATCHED_LIST="$matched" \
    SYNC_MATCHED_COUNT="$matched_count" \
    SYNC_MATCHED_PREFIX="$prefix" \
        bash -c "$command" </dev/null || rc=$?

    if [ "$rc" -ne 0 ]; then
        log "[$prefix] 실패 (exit $rc)"
        failed=1
    else
        log "[$prefix] 완료"
    fi
    ran=$(( ran + 1 ))
    rm -f "$matched"
done < "$RULES"

[ "$ran" -eq 0 ] && log "일치하는 규칙 없음 — 실행한 파이프라인 없음"
exit "$failed"
