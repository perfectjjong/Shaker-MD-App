#!/bin/bash
# Price Q&A — 서버 + Cloudflare 터널 기동, 터널 URL을 대시보드에 주입 후 배포.
#
# Quick Tunnel은 재시작할 때마다 URL이 바뀐다(trycloudflare.com).
# 그래서 기동 → URL 확보 → HTML 주입 → 커밋/푸시가 한 묶음이어야 한다.
# (FCST start_tunnel.sh 와 같은 패턴)
set -uo pipefail

PORT=5071
REPO=/home/ubuntu/Shaker-MD-App
HTML="$REPO/docs/dashboards/price-qa/index.html"
SRV="$REPO/price-tracking/price_qa_server.py"
PY=/usr/bin/python3          # flask 가 여기에 설치돼 있다 (ai_env 에는 없음)
LOG=/tmp/price_qa_server.log
TLOG=/tmp/price_qa_tunnel.log

echo "── 기존 프로세스 정리 ──"
# ⚠️ pkill -f 는 **자기 자신의 명령줄**도 패턴에 걸려 스크립트가 자살한다(exit 144 겪음).
#    pgrep 으로 PID를 뽑아 자기 자신($$)과 부모를 제외하고 죽인다.
kill_matching() {
  for pid in $(pgrep -f "$1" 2>/dev/null); do
    [ "$pid" = "$$" ] && continue
    [ "$pid" = "$PPID" ] && continue
    kill "$pid" 2>/dev/null
  done
}
kill_matching "python3 .*price_qa_server\.py"
kill_matching "cloudflared tunnel --url http://127.0.0.1:${PORT}"
sleep 1

echo "── 서버 기동 :${PORT} ──"
nohup "$PY" "$SRV" "$PORT" > "$LOG" 2>&1 &
sleep 3
if ! curl -sf "http://127.0.0.1:${PORT}/health" > /dev/null; then
  echo "❌ 서버 기동 실패"; tail -20 "$LOG"; exit 1
fi
echo "✅ 서버 정상: $(curl -s http://127.0.0.1:${PORT}/health)"

echo "── 터널 기동 ──"
nohup cloudflared tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate > "$TLOG" 2>&1 &
URL=""
for i in $(seq 1 20); do
  URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$TLOG" 2>/dev/null | head -1)
  [ -n "$URL" ] && break
  sleep 2
done
if [ -z "$URL" ]; then echo "❌ 터널 URL 확보 실패"; tail -20 "$TLOG"; exit 1; fi
echo "✅ 터널: $URL"
echo "$URL" > /tmp/price_qa_tunnel_url.txt

# 터널 경유 실제 도달 확인 (로컬만 되고 외부는 안 되는 경우를 잡는다)
for i in $(seq 1 10); do
  curl -sf "$URL/health" > /dev/null && break || sleep 2
done
if ! curl -sf "$URL/health" > /dev/null; then
  echo "⚠️ 터널 URL로 health 도달 실패 — 전파 지연일 수 있음. 계속 진행."
fi

echo "── 대시보드에 API 주소 주입 ──"
"$PY" - "$HTML" "$URL" <<'PYEOF'
import re, sys, pathlib
html, url = pathlib.Path(sys.argv[1]), sys.argv[2]
s = html.read_text(encoding="utf-8")
new = re.sub(r'const API = "[^"]*";', f'const API = "{url}";', s, count=1)
if new == s and '__API_BASE__' not in s:
    print("   (주소 동일 — 변경 없음)")
html.write_text(new, encoding="utf-8")
print(f"   API = {url}")
PYEOF

echo "── 배포 ──"
BRANCH=$(git -C "$REPO" branch --show-current)
if [ "$BRANCH" != "main" ]; then
  echo "❌ 배포 중단 — 현재 브랜치 '$BRANCH' (main 아님). 여기서 push하면 조용히 누락된다."
  exit 1
fi
git -C "$REPO" add docs/dashboards/price-qa/index.html
if git -C "$REPO" diff --cached --quiet; then
  echo "   변경 없음 — 커밋 생략"
else
  git -C "$REPO" -c commit.gpgsign=false commit -q -m "chore(price-qa): 터널 주소 갱신 $(date +%Y-%m-%d\ %H:%M)"
  git -C "$REPO" push -q origin main
  git -C "$REPO" fetch -q origin main
  BEHIND=$(git -C "$REPO" rev-list --count origin/main..main)
  [ "$BEHIND" = "0" ] && echo "✅ 배포 검증: 원격 main 일치" || { echo "❌ push 후에도 미반영 $BEHIND개"; exit 1; }
fi

echo
echo "════════════════════════════════════════"
echo " 대시보드: https://perfectjjong.github.io/Shaker-MD-App/dashboards/price-qa/"
echo " API     : $URL"
echo " 서버로그: $LOG"
echo "════════════════════════════════════════"
