#!/bin/bash
# Power Automate 수확분 라우터 — OneDrive 99. Inbox 로 떨어진 메일 첨부(.msg/.xlsx)를
# 해체·스테이징에 넣고 inbox_place 를 즉시 호출한다. (2026-08-28, Graph 차단 우회 B안)
set -u
D="$(cd "$(dirname "$0")" && pwd)"
LIST="${SYNC_MATCHED_LIST:-}"
[ -f "$LIST" ] || exit 0
SRV="/home/ubuntu/2026/10. Automation"
# ⚠️ STAGE 를 OR 수신함으로 고정하면 IR 수신함 첨부가 OR 내용판별기로 흘러가 전량 미분류된다
#    (2026-08-30: PA 플로우 4개 신설로 IR 99. Inbox 가 생겼다). rel 기준으로 잡는다.
n=0
while IFS= read -r rel; do
  src="$SRV/$rel"
  [ -f "$src" ] || continue
  STAGE="/home/ubuntu/inbox/staged/auto/$(dirname "$rel")"
  mkdir -p "$STAGE"
  case "${rel,,}" in
    *.msg)
      # 중첩메일 해체 — 안의 엑셀만 스테이징으로 (재귀 2단, PC v11과 동일 한도)
      /home/ubuntu/ai_env/bin/python3 - "$src" "$STAGE" <<'PY'
import sys, os, extract_msg
def harvest(path, out, depth=0):
    if depth > 2: return 0
    k = 0
    m = extract_msg.openMsg(path)
    for a in (m.attachments or []):
        name = (a.longFilename or a.shortFilename or '')
        data = a.data
        if hasattr(data, 'attachments'):          # 중첩 메일
            tmp = os.path.join(out, f'.n{depth}_{k}.msg')
            data.export(tmp) if hasattr(data,'export') else None
            if os.path.exists(tmp):
                k += harvest(tmp, out, depth+1); os.remove(tmp)
            continue
        if name.lower().endswith(('.xlsx','.xls','.xlsm','.pdf')) and isinstance(data, bytes):
            safe = name.replace('/','_').replace('\\','_')
            open(os.path.join(out, safe), 'wb').write(data); k += 1
    m.close()
    return k
print(harvest(sys.argv[1], sys.argv[2]))
PY
      rm -f "$src"          # 해체 끝난 .msg 원본은 정리 (서버·OneDrive 재동기 방지엔 서버측만)
      n=$((n+1));;
    *.xlsx|*.xls|*.xlsm|*.pdf)
      mv "$src" "$STAGE/"; n=$((n+1));;
  esac
  # ⚠️ OneDrive 원본도 지워야 한다 — 서버 사본만 지우면 다음 회차에 재다운로드되어
  #    1분마다 무한 재수신 루프가 된다(2026-08-28 실측: 시험파일로 60여 회 루프).
  rclone deletefile "onedrive:문서/01. 2026/01. Work/08. Automation/$rel" 2>/dev/null
done < "$LIST"
# 화이트리스트 밖 첨부(서명 이미지 등)는 동기화가 안 내려받아 OneDrive에만 쌓인다 → 원격 청소
for _box in "01. Sell Out Dashboard/00. OR/00. Raw/99. Inbox" \
            "01. Sell Out Dashboard/01. IR/00. Raw/99. Inbox"; do
  timeout 40 rclone lsf "onedrive:문서/01. 2026/01. Work/08. Automation/$_box" 2>/dev/null \
    | grep -viE '\.(xlsx|xls|xlsm|pdf|msg)$' | while IFS= read -r junk; do
      [ -n "$junk" ] && rclone deletefile "onedrive:문서/01. 2026/01. Work/08. Automation/$_box/$junk" 2>/dev/null
    done
done

[ $n -eq 0 ] && exit 0
"$D/tg_notify.sh" "📨 메일 수확분 ${n}건 수신(클라우드 경유) — 서버 분류 시작"
/home/ubuntu/ai_env/bin/python3 /home/ubuntu/scripts/inbox_place.py --apply >> /home/ubuntu/onedrive_menu.log 2>&1
