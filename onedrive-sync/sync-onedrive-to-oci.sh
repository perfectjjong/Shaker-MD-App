#!/bin/bash
# OneDrive → OCI 서버 단방향 동기화
#
# OneDrive의 지정 폴더를 OCI 서버의 대응 폴더로 내려받고,
# 새로 들어온 파일이 있으면 해당 매핑에 등록된 파이프라인을 실행한다.
#
# 단방향이다. 서버 → OneDrive 방향으로는 아무것도 쓰지 않는다
# (rclone copy는 대상에만 쓰고, 원본은 읽기만 한다).
#
# 중복 처리:
#   - 서버에 이미 있고 내용이 같은 파일(크기·수정시각 일치)은 전송하지 않는다.
#   - 같은 이름의 파일이 양쪽에 있으면 더 최신인 쪽을 남긴다. 서버 파일이
#     더 최신이면 건너뛰므로, 서버가 생성한 산출물이 옛 버전으로 덮이지 않는다.
#
# 용량 보호 (sync-settings.conf에서 조정):
#   1) 확장자 화이트리스트 — 허용된 확장자만 내려받는다
#   2) 단일 파일 크기 상한
#   3) 회차당 총 전송량 상한
#   4) 동기화 전 디스크 여유 공간 점검
#
# 설정: sync-map.conf, sync-settings.conf  (각각 .example 참고)
# 설치: ./install-cron.sh
# 사용법:
#   ./sync-onedrive-to-oci.sh              # 전체 매핑 동기화
#   ./sync-onedrive-to-oci.sh --dry-run    # 실제 복사 없이 대상만 확인
#   ./sync-onedrive-to-oci.sh --only NAME  # 특정 매핑만
#   ./sync-onedrive-to-oci.sh --list       # 매핑 목록과 현재 설정 출력
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

CONF="${ONEDRIVE_SYNC_CONF:-$SCRIPT_DIR/sync-map.conf}"
SETTINGS="${ONEDRIVE_SYNC_SETTINGS:-$SCRIPT_DIR/sync-settings.conf}"
REMOTE="${ONEDRIVE_REMOTE:-onedrive}"
LOCK="${ONEDRIVE_SYNC_LOCK:-/tmp/onedrive-sync.lock}"
RCLONE="${RCLONE_BIN:-rclone}"

# 용량 가드 기본값 — sync-settings.conf가 있으면 그 값이 우선한다
INCLUDE_EXT="xlsx,xls,xlsm,csv,txt,json"
MAX_FILE_SIZE="100M"
MAX_TRANSFER="2G"
MIN_FREE_DISK_MB="5000"
KEEP_NEWER_ON_SERVER="true"
MODIFY_WINDOW="1s"

# shellcheck source=/dev/null
[ -f "$SETTINGS" ] && . "$SETTINGS"

DRY_RUN=0
ONLY=""
LIST_ONLY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --only)    ONLY="${2:-}"; shift ;;
        --list)    LIST_ONLY=1 ;;
        -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
    esac
    shift
done

log() { printf '[onedrive-sync] %s %s\n' "$(date '+%F %T')" "$*"; }

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

# xlsx → [xX][lL][sS][xX]  (rclone 필터는 대소문자를 구분한다)
ci_glob() {
    local s="$1" out="" c lower upper i
    for (( i = 0; i < ${#s}; i++ )); do
        c="${s:i:1}"
        case "$c" in
            [a-zA-Z])
                lower="$(printf '%s' "$c" | tr 'A-Z' 'a-z')"
                upper="$(printf '%s' "$c" | tr 'a-z' 'A-Z')"
                out+="[${lower}${upper}]"
                ;;
            *) out+="$c" ;;
        esac
    done
    printf '%s' "$out"
}

# rclone 필터 규칙을 만든다.
#
# --include와 --exclude를 섞으면 rclone이 평가 순서를 보장하지 않아
# Office 임시파일 ~$보고서.xlsx 가 화이트리스트의 *.xlsx에 먼저 걸릴 수 있다.
# --filter로 순서를 명시한다 — 위에서부터 먼저 일치하는 규칙이 이긴다.
#   1) 제외 규칙 (임시·잠금 파일)
#   2) 확장자 화이트리스트
#   3) 나머지 전부 제외
build_filter_args() {
    filter_args=()
    local ext
    local -a exts

    filter_args+=( --filter '- ~$*' )       # Office 임시파일
    filter_args+=( --filter '- .~lock.*' )  # LibreOffice 잠금파일
    filter_args+=( --filter '- .DS_Store' )
    filter_args+=( --filter '- *.tmp' )

    # 파일 단위 제외 목록 (선택): sync-exclude.conf — 한 줄에 리모트 기준 상대경로 하나.
    # 서버에서 수리·가공한 raw가 OneDrive의 더 최신 타임스탬프 본으로 되돌아가는 것을
    # 개별 파일 단위로 막는 용도 (2026-08-28, 최초 유입 검토에서 덮어쓰기 18건 제외 결정).
    # 화이트리스트보다 먼저 평가되도록 이 위치에 둔다. 경로 선두 '/'는 전송 루트 앵커.
    local exclude_file="$SCRIPT_DIR/sync-exclude.conf"
    if [ -f "$exclude_file" ]; then
        local xline
        while IFS= read -r xline; do
            xline="$(trim "$xline")"
            [ -z "$xline" ] && continue
            case "$xline" in \#*) continue ;; esac
            filter_args+=( --filter "- /$xline" )
        done < "$exclude_file"
    fi

    IFS=',' read -ra exts <<< "$INCLUDE_EXT"
    for ext in "${exts[@]}"; do
        ext="$(trim "$ext")"
        [ -z "$ext" ] && continue
        filter_args+=( --filter "+ *.$(ci_glob "$ext")" )
    done

    filter_args+=( --filter '- *' )
}

# 대상 경로가 속한 파일시스템의 여유 공간(MB)
free_disk_mb() {
    local probe="$1"
    while [ ! -d "$probe" ] && [ "$probe" != "/" ] && [ -n "$probe" ]; do
        probe="$(dirname "$probe")"
    done
    df -Pm "$probe" 2>/dev/null | awk 'NR==2 {print $4}'
}

[ -f "$CONF" ] || { log "설정 파일 없음: $CONF  (sync-map.conf.example을 복사해서 만드십시오)"; exit 1; }
command -v "$RCLONE" >/dev/null 2>&1 || { log "rclone 미설치 — README.md의 설치 절차를 따르십시오"; exit 1; }

build_filter_args

if [ "$LIST_ONLY" -eq 1 ]; then
    echo "설정 (${SETTINGS})"
    echo "  확장자 화이트리스트 : $INCLUDE_EXT"
    echo "  단일 파일 최대       : $MAX_FILE_SIZE"
    echo "  회차당 전송 상한     : $MAX_TRANSFER"
    echo "  최소 여유 디스크     : ${MIN_FREE_DISK_MB} MB"
    echo "  서버 최신본 보존     : $KEEP_NEWER_ON_SERVER (수정시각 허용오차 ${MODIFY_WINDOW})"
    echo
    printf '%-20s %-55s %s\n' "NAME" "ONEDRIVE" "LOCAL"
    while IFS='|' read -r name od local pipeline || [ -n "$name" ]; do
        name="$(trim "$name")"
        case "$name" in ''|\#*) continue ;; esac
        printf '%-20s %-55s %s\n' "$name" "$(trim "$od")" "$(trim "$local")"
    done < "$CONF"
    exit 0
fi

# 동시 실행 방지 — cron 주기보다 동기화가 오래 걸려도 겹치지 않는다
exec 9>"$LOCK"
if ! flock -n 9; then
    log "이전 실행이 아직 진행 중 — 이번 회차 건너뜀"
    exit 0
fi

# rclone이 실제로 전송한(또는 dry-run에서 전송했을) 파일 목록을 JSON 로그에서 추출한다
extract_transferred() {
    python3 - "$1" "$2" <<'PY'
import json, sys
log_path, dry = sys.argv[1], sys.argv[2] == "1"
prefix = "Skipped copy" if dry else "Copied"
with open(log_path, encoding="utf-8", errors="replace") as fh:
    for line in fh:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not str(entry.get("msg", "")).startswith(prefix):
            continue
        obj = entry.get("object")
        if obj:
            print(obj)
PY
}

failed=0
synced_total=0

while IFS='|' read -r name od_path local_path pipeline || [ -n "$name" ]; do
    name="$(trim "$name")"
    case "$name" in ''|\#*) continue ;; esac

    od_path="$(trim "${od_path:-}")"
    local_path="$(trim "${local_path:-}")"
    pipeline="$(trim "${pipeline:-}")"

    [ -n "$ONLY" ] && [ "$ONLY" != "$name" ] && continue

    if [ -z "$od_path" ] || [ -z "$local_path" ]; then
        log "[$name] 설정이 불완전함 (OneDrive/로컬 경로 누락) — 건너뜀"
        failed=1
        continue
    fi

    # 디스크 점검을 복사보다 먼저 — 꽉 찬 뒤에 아는 것은 늦다
    avail="$(free_disk_mb "$local_path")"
    if [ -n "$avail" ] && [ "$avail" -lt "$MIN_FREE_DISK_MB" ]; then
        log "[$name] 디스크 여유 부족: ${avail} MB < 기준 ${MIN_FREE_DISK_MB} MB — 동기화 중단"
        failed=1
        continue
    fi

    mkdir -p "$local_path"

    rclone_log="$(mktemp)"
    rc=0
    "$RCLONE" copy "${REMOTE}:${od_path}" "$local_path" \
        "${filter_args[@]}" \
        --max-size "$MAX_FILE_SIZE" \
        --max-transfer "$MAX_TRANSFER" \
        --modify-window "$MODIFY_WINDOW" \
        $( [ "$KEEP_NEWER_ON_SERVER" = "true" ] && printf '%s' '--update' ) \
        --use-json-log --log-level INFO --log-file "$rclone_log" --stats 0 \
        --transfers 4 --checkers 8 --retries 3 --low-level-retries 10 \
        $( [ "$DRY_RUN" -eq 1 ] && printf '%s' '--dry-run' ) \
        </dev/null || rc=$?

    # 8 = --max-transfer 상한 도달. 실패가 아니라 의도된 제동이므로
    # 받아온 파일은 정상 처리하고 다음 회차에 이어받는다.
    if [ "$rc" -eq 8 ]; then
        log "[$name] 전송 상한(${MAX_TRANSFER}) 도달 — 나머지는 다음 회차에 이어받음"
    elif [ "$rc" -ne 0 ]; then
        log "[$name] rclone 실패 (exit $rc)"
        sed -n '1,20p' "$rclone_log" >&2 || true
        rm -f "$rclone_log"
        failed=1
        continue
    fi

    file_list="$(mktemp)"
    extract_transferred "$rclone_log" "$DRY_RUN" > "$file_list"
    rm -f "$rclone_log"

    count="$(wc -l < "$file_list" | tr -d ' ')"

    if [ "$count" -eq 0 ]; then
        rm -f "$file_list"
        continue
    fi

    synced_total=$(( synced_total + count ))

    if [ "$DRY_RUN" -eq 1 ]; then
        log "[$name] (dry-run) 복사 대상 ${count}건:"
        sed 's/^/    /' "$file_list"
        rm -f "$file_list"
        continue
    fi

    log "[$name] ${count}건 동기화 → $local_path"
    sed 's/^/    /' "$file_list"

    if [ -z "$pipeline" ]; then
        rm -f "$file_list"
        continue
    fi

    log "[$name] 파이프라인 실행: $pipeline"
    prc=0
    SYNC_NAME="$name" \
    SYNC_LOCAL_DIR="$local_path" \
    SYNC_REMOTE_PATH="$od_path" \
    SYNC_FILE_COUNT="$count" \
    SYNC_FILE_LIST="$file_list" \
        bash -c "$pipeline" </dev/null || prc=$?

    if [ "$prc" -ne 0 ]; then
        log "[$name] 파이프라인 실패 (exit $prc)"
        failed=1
    else
        log "[$name] 파이프라인 완료"
    fi

    rm -f "$file_list"
done < "$CONF"

if [ "$synced_total" -eq 0 ]; then
    log "변경 없음"
fi

exit "$failed"
