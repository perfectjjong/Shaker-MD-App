#!/bin/bash
# Price Q&A — 서버 + Cloudflare 터널 기동, 터널 URL을 대시보드에 주입 후 배포.
#
# Quick Tunnel은 재시작할 때마다 URL이 바뀐다(trycloudflare.com).
# 그래서 기동 → URL 확보 → HTML 주입 → 커밋/푸시가 한 묶음이어야 한다.
# (FCST start_tunnel.sh 와 같은 패턴)
set -uo pipefail

PORT=5071
REPO=/home/ubuntu/Shaker-MD-App
HTML="$REPO/docs/gtm/price-qa/index.html"
ENDPOINT="$REPO/docs/gtm/price-qa/endpoint.js"
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
# 🔴 이 서버의 로컬 DNS는 새로 만들어진 trycloudflare 호스트를 한동안 해석하지 못한다.
#    그냥 curl 하면 HTTP 000 이 나와 "터널 죽음"으로 오판한다 — 실제로는 형님 브라우저에선 멀쩡하다.
#    그래서 **공개 DNS(1.1.1.1)로 직접 해석**해 그 IP로 도달을 확인한다.
HOSTONLY=${URL#https://}
TUNNEL_OK=0
for i in $(seq 1 12); do
  IP=$(dig +short @1.1.1.1 "$HOSTONLY" 2>/dev/null | grep -E '^[0-9.]+$' | head -1)
  if [ -n "$IP" ] && curl -sf -m 15 --resolve "${HOSTONLY}:443:${IP}" "$URL/health" > /dev/null; then
    TUNNEL_OK=1; echo "✅ 외부 도달 확인 ($IP)"; break
  fi
  sleep 3
done
[ "$TUNNEL_OK" = "1" ] || echo "⚠️ 외부 도달 미확인 — 전파 지연일 수 있음. 계속 진행."

# 🔴 2026-09-03: 주소를 index.html 이 아니라 **한 줄짜리 별도 파일**에 쓴다.
#    quick tunnel 은 재시작마다 주소가 바뀌는데(37시간에 8개), 그때마다 대시보드 본문을
#    통째로 커밋해 main 이력을 더럽히고 다른 배포와 push 경쟁을 일으켰다(remote rejected 5회).
#    ⚠️ 근본 해결은 **고정 주소(named tunnel)** 다. `cloudflared tunnel login` 이 필요해
#       형님 브라우저 승인 없이는 못 만든다 — 그전까지의 차선책이다.
echo "── API 주소 파일 갱신 ──"
echo "window.PRICE_QA_API = \"$URL\";" > "$ENDPOINT"
echo "   API = $URL"

echo "── 배포 ──"
BRANCH=$(git -C "$REPO" branch --show-current)
if [ "$BRANCH" != "main" ]; then
  echo "❌ 배포 중단 — 현재 브랜치 '$BRANCH' (main 아님). 여기서 push하면 조용히 누락된다."
  exit 1
fi
git -C "$REPO" add docs/gtm/price-qa/endpoint.js docs/gtm/price-qa/index.html
if git -C "$REPO" diff --cached --quiet; then
  echo "   변경 없음 — 커밋 생략"
else
  git -C "$REPO" -c commit.gpgsign=false commit -q -m "chore(price-qa): 터널 주소 갱신 $(date +%Y-%m-%d\ %H:%M)"
  # 🔴 다른 배포(가격 대시보드 11채널이 매일 자정 push)와 부딪히면 push 가 거부된다.
  #    거부를 무시하고 "배포 완료"라 보고하던 것을 막는다 — rebase 후 재시도.
  if ! git -C "$REPO" push -q origin main 2>/dev/null; then
    echo "   push 거부 — 원격 변경을 받아 rebase 후 재시도"
    git -C "$REPO" fetch -q origin main && git -C "$REPO" rebase -q origin/main || {
      git -C "$REPO" rebase --abort 2>/dev/null; echo "❌ rebase 실패 — 수동 확인 필요"; exit 1; }
    git -C "$REPO" push -q origin main
  fi
  git -C "$REPO" fetch -q origin main
  BEHIND=$(git -C "$REPO" rev-list --count origin/main..main)
  [ "$BEHIND" = "0" ] && echo "✅ 배포 검증: 원격 main 일치" || { echo "❌ push 후에도 미반영 $BEHIND개"; exit 1; }
fi

echo
echo "════════════════════════════════════════"
echo " 대시보드: https://shaker-dashboard.pages.dev/gtm/price-qa/"
echo " API     : $URL"
echo " 서버로그: $LOG"
echo "════════════════════════════════════════"
