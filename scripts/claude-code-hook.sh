#!/bin/bash
# Claude Code Hook Script
# Claude Code의 도구 실행 전에 호출되어 승인 서버로 요청을 보냅니다.
#
# 사용법 (Claude Code settings.json에 추가):
# {
#   "hooks": {
#     "PreToolUse": [
#       {
#         "matcher": "",
#         "hooks": [
#           {
#             "type": "command",
#             "command": "/path/to/claude-code-hook.sh"
#           }
#         ]
#       }
#     ]
#   }
# }
#
# Hook은 stdin으로 JSON을 받습니다:
# {
#   "tool_name": "Bash",
#   "tool_input": { "command": "ls -la", "description": "..." }
# }

SERVER_URL="${CLAUDE_APPROVER_URL:-http://localhost:3847}"

# stdin에서 JSON 읽기
INPUT=$(cat)

# 도구 정보 추출
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null)
TOOL_INPUT=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('tool_input',{})))" 2>/dev/null)

# 명령어 추출 (Bash 도구인 경우)
if [ "$TOOL_NAME" = "Bash" ]; then
  COMMAND=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('command',''))" 2>/dev/null)
else
  COMMAND=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)))" 2>/dev/null)
fi

# 서버로 승인 요청
RESPONSE=$(curl -s -m 300 \
  -X POST "${SERVER_URL}/api/approval" \
  -H "Content-Type: application/json" \
  -d "{
    \"command\": $(python3 -c "import json; print(json.dumps('''${COMMAND}'''))" 2>/dev/null || echo "\"${COMMAND}\""),
    \"tool\": \"${TOOL_NAME}\",
    \"workdir\": \"$(pwd)\"
  }" 2>/dev/null)

# 응답 파싱
STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)

if [ "$STATUS" = "approved" ]; then
  # 승인됨 - 정상 진행 (빈 출력 또는 exit 0)
  exit 0
elif [ "$STATUS" = "rejected" ]; then
  # 거부됨 - JSON으로 거부 메시지 출력
  echo '{"decision": "block", "reason": "모바일에서 거부됨"}'
  exit 0
else
  # 서버 연결 실패 또는 타임아웃 - 기본 허용
  exit 0
fi
