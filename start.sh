#!/bin/bash
# Claude Code Mobile Approver - Linux/macOS 시작 스크립트

set -e

echo "========================================"
echo "  Claude Code Mobile Approver"
echo "========================================"
echo ""

# Node.js 확인
if ! command -v node &>/dev/null; then
  echo "[ERROR] Node.js가 설치되어 있지 않습니다."
  echo "  설치: https://nodejs.org"
  exit 1
fi

echo "[OK] Node.js $(node -v)"

# 프로젝트 디렉토리로 이동
cd "$(dirname "$0")"

# npm 패키지 설치 (없을 경우)
if [ ! -d "node_modules" ]; then
  echo "[SETUP] npm 패키지 설치 중..."
  npm install
  echo ""
fi

# 접속 URL 표시
echo ""
echo "[INFO] 모바일에서 접속:"
echo ""

# IP 주소 감지
if command -v ip &>/dev/null; then
  ip -4 addr show | grep -oP '(?<=inet\s)\d+\.\d+\.\d+\.\d+' | grep -v '127.0.0.1' | while read -r ip; do
    echo "  http://${ip}:3847"
  done
elif command -v ifconfig &>/dev/null; then
  ifconfig | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | sed 's/addr://' | while read -r ip; do
    echo "  http://${ip}:3847"
  done
fi

echo "  http://localhost:3847"
echo ""
echo "[INFO] Ctrl+C로 서버를 종료합니다."
echo "========================================"
echo ""

# 서버 시작
exec node src/server.js
