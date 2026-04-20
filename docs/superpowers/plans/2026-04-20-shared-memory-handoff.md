# Shared Memory & Handoff System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code와 텔레그램 봇이 프로젝트 수준의 장기 지식을 공유하고, 퇴근/출근 시 작업 컨텍스트를 핸드오프할 수 있는 시스템 구축

**Architecture:** `/home/ubuntu/shared_memory/`를 읽기 전용 공유 저장소로 두고, 양쪽 CLAUDE.md에서 세션 시작 시 자동 로드. 공유 메모리 업데이트는 `shared_memory_writer.py`를 통한 원자적 쓰기로만 허용. 핸드오프는 `handoff.md` 파일을 통해 작업 상태를 명시적으로 전달.

**Tech Stack:** Python (fcntl 파일 잠금, os.replace 원자적 쓰기), Markdown (메모리/핸드오프 파일)

---

## 파일 구조

```
/home/ubuntu/
├── shared_memory/                         # [NEW] 공유 메모리 저장소
│   ├── MEMORY.md                          # [NEW] 공유 메모리 인덱스
│   ├── handoff.md                         # [NEW] 핸드오프 노트 (세션 간 작업 전달)
│   ├── feedback_language.md               # [NEW] 한국어 필수 (양쪽 공통)
│   ├── feedback_server_env.md             # [NEW] 서버 환경 설정 (양쪽 공통)
│   ├── project_domain_knowledge.md        # [NEW] 도메인 지식 (채널 분류, 가격 세그먼트 등)
│   ├── project_data_sources.md            # [NEW] 데이터 소스 합의 (FCST, OR 파이프라인)
│   └── project_dashboard_rules.md        # [NEW] 대시보드 업데이트 정책
├── shared_memory_writer.py                # [NEW] 원자적 쓰기 유틸리티
├── CLAUDE.md                              # [MODIFY] shared_memory 참조 + 핸드오프 지시 추가
└── sonolbot/
    └── CLAUDE.md                          # [MODIFY] shared_memory 참조 + 핸드오프 지시 추가
```

---

## Task 1: shared_memory 디렉토리 및 초기 파일 생성

**Files:**
- Create: `/home/ubuntu/shared_memory/MEMORY.md`
- Create: `/home/ubuntu/shared_memory/handoff.md`
- Create: `/home/ubuntu/shared_memory/feedback_language.md`
- Create: `/home/ubuntu/shared_memory/feedback_server_env.md`
- Create: `/home/ubuntu/shared_memory/project_domain_knowledge.md`
- Create: `/home/ubuntu/shared_memory/project_data_sources.md`
- Create: `/home/ubuntu/shared_memory/project_dashboard_rules.md`

- [ ] **Step 1: shared_memory 디렉토리 생성**

```bash
mkdir -p /home/ubuntu/shared_memory
```

- [ ] **Step 2: MEMORY.md 인덱스 생성**

`/home/ubuntu/shared_memory/MEMORY.md`:
```markdown
# Shared Memory Index
<!-- Claude Code와 텔레그램 봇이 공동으로 읽는 장기 지식 저장소 -->
<!-- 업데이트: shared_memory_writer.py 또는 명시적 명령("shared memory 업데이트해줘")으로만 -->

- [언어 설정](feedback_language.md) — 모든 소통은 한국어로
- [서버 환경 설정](feedback_server_env.md) — bypassPermissions, 기획 모델 Opus 4.7
- [도메인 지식](project_domain_knowledge.md) — 채널 분류, 가격 세그먼트, 대시보드 구조
- [데이터 소스 합의](project_data_sources.md) — FCST/OR 파이프라인, 경로 정보
- [대시보드 업데이트 정책](project_dashboard_rules.md) — eXtra 3개 동시 배포 등 운영 규칙
```

- [ ] **Step 3: feedback_language.md 생성**

`/home/ubuntu/shared_memory/feedback_language.md`:
```markdown
---
name: 언어 설정 — 한국어 필수
type: feedback
last_updated: 2026-04-20
source: claude-code
---
모든 응답은 반드시 한국어로 작성한다.

**Why:** 사용자가 명시적으로 요청 — "무조건 한국어로 합니다"

**How to apply:** 코드 코멘트, 기술 설명, 질문, 요약 등 모든 텍스트를 한국어로.
코드 자체(변수명, 함수명)는 영어 유지 가능.
```

- [ ] **Step 4: feedback_server_env.md 생성**

`/home/ubuntu/shared_memory/feedback_server_env.md`:
```markdown
---
name: 서버 환경 설정
type: feedback
last_updated: 2026-04-20
source: claude-code
---
## Tool 승인
모든 tool 사용을 자동 승인(bypassPermissions)으로 설정.

**Why:** 서버에서 운영 중 — 실시간 승인 불가 환경.

**How to apply:** 파일 수정, bash 실행, 패키지 설치 등 모든 작업을 승인 요청 없이 진행.

## 기획/브레인스토밍 모델
기획 및 브레인스토밍 sub-agent는 반드시 `claude-opus-4-7` 사용.

**Why:** 기획 품질을 위해 Opus 4.7 지정. 메인은 비용 효율을 위해 Sonnet 유지.

**How to apply:**
- brainstorming / writing-plans 스킬 → Agent tool 호출 시 `model: "opus"` 지정
- 코드 작성, 파일 편집 등 실행 작업 → 기본 sonnet/haiku 유지
```

- [ ] **Step 5: project_domain_knowledge.md 생성**

`/home/ubuntu/shared_memory/project_domain_knowledge.md`:
```markdown
---
name: 도메인 지식
type: project
last_updated: 2026-04-20
source: claude-code + bot
---
## 채널 구조

**OR 5채널**: eXtra, Al Manea, SWS, Black Box, Al Khunizan
**IR 8채널**: BH, BM, Tamkeen, Zagzoog, Dhamin, Star Appliance, Al Ghanem, Al Shathri

## 2026년 채널 분류 로직
파일: `/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/01. Python Code/refresh_dashboard.py` (274번째 줄)

2026년은 Account ID 기준으로 OR/IR 재분류:
- OR 5채널 ID: Al Manea(1110000001~3), SWS(1110000004~5), Black Box(1110000006), Al Khunizan(1110000007), eXtra(1120000000, 1110000369)
- IR 8채널 ID: BH(1110000000), BM(1110000009), Tamkeen(1110000010), Zagzoog(1110000299), Dhamin(1110000015), Star(1110000101), AlGhanem(1110000253), AlShathri(1110000065)
- 위 ID 외 계정 → OR_Others / IR_Others

## eXtra AC 가격 세그먼트
Mini Split AC는 반드시 **Inverter / Rotary(On-Off)**로 세분화하여 분석.

- Inverter: 에너지 효율 중시, 프리미엄, 비가격 민감 (2025 평균 2,610 SAR)
- Rotary: 가격 민감, LG 점유율 낮음 (2025 평균 1,959 SAR, LG MS 2.7%)

분석 단위: Mini Split+Inverter+CO/HC, Mini Split+Rotary+CO/HC, Window+Inverter/Rotary, PAC, Cassette

## Apify 도입 정책
반복 에러 채널에 한해 선택적 Apify 도입. apify-client 설치 완료.
```

- [ ] **Step 6: project_data_sources.md 생성**

`/home/ubuntu/shared_memory/project_data_sources.md`:
```markdown
---
name: 데이터 소스 합의
type: project
last_updated: 2026-04-20
source: claude-code
---
## eXtra 2026 Sell-out 데이터

**경로**: `/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/00. OR/00. Raw/00. eXtra/00. Weekly Sell out/week01~weekNN.xlsx`

**Why**: B2C Dealer 파일과 OR 주간 파일은 스케일이 달라 혼용 금지. OR 주간 파일 기준으로 통일.

**How to apply**: FCST DB 적재 시 항상 `or_unified_dashboard_generator.py`의 `read_extra_sellout()` 파이프라인 사용.

## FCST 시스템 경로
- DB: `/home/ubuntu/2026/03. Reporting/01. FCST/data/sellout.db`
- 대시보드: `/home/ubuntu/2026/03. Reporting/01. FCST/dashboard/`
- GitHub Pages: https://perfectjjong.github.io/extra-fcst-dashboard/

## OR 업데이트 파이프라인
실행: `python run_all.py [or|ir|b2c|extra|all]`
위치: `/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/run_all.py`

## Shaker Dashboard
- URL: https://shaker-dashboard.pages.dev
- Repo: /home/ubuntu/Shaker-MD-App
- 배포: git push → Cloudflare Pages 자동 배포
```

- [ ] **Step 7: project_dashboard_rules.md 생성**

`/home/ubuntu/shared_memory/project_dashboard_rules.md`:
```markdown
---
name: 대시보드 업데이트 정책
type: project
last_updated: 2026-04-20
source: claude-code
---
## eXtra Sellout 3개 대시보드 동시 배포

eXtra weekly raw 데이터 업데이트 시 아래 3개 대시보드를 반드시 동시 업데이트:
1. `extra-sellout/` — 통합 포맷 (OR 5채널 통합 뷰)
2. `extra-ms/` — MS Dashboard Qty 기준 (이전 포맷, 7탭)
3. `extra-ms-value/` — MS Dashboard Value 기준 (SAR 기준)

**스크립트**: `/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/00. OR/02. eXtra/update_sellout_dashboard.py`
→ `deploy_to_cloudflare()` 함수가 3곳에 data.json 동시 복사 후 git push

## 대시보드 수정 원칙
- HTML 직접 패치 금지 → generator .py 파일만 수정
- 수정 후 반드시 `python generator.py`로 재생성 검증
- OR/IR 개별 대시보드는 통합 대시보드에서 파생 (`generate_channel_from_unified.py`)

## 네비게이션 순서 (docs/index.html)
Sell Thru Progress → eXtra AC Business → OR 5 Ch. Weekly → MS Qty → MS Value →
eXtra Weekly Sell Out → eXtra AC Business → Al Manea → SWS → Black Box → Al Khunizan
```

- [ ] **Step 8: handoff.md 빈 템플릿 생성**

`/home/ubuntu/shared_memory/handoff.md`:
```markdown
# Handoff Note
<!-- 마지막 업데이트: (날짜/시간 없음 — 아직 핸드오프 없음) -->
<!-- 사용법:
  [Claude Code 종료 시] "봇으로 넘길게, 핸드오프 써줘"
  [봇 시작 시]         "클코에서 하던 거 이어서 해줘"
-->

## 상태
핸드오프 없음 — 초기 상태
```

---

## Task 2: 원자적 쓰기 유틸리티 생성

**Files:**
- Create: `/home/ubuntu/shared_memory_writer.py`

- [ ] **Step 1: shared_memory_writer.py 작성**

`/home/ubuntu/shared_memory_writer.py`:
```python
#!/usr/bin/env python3
"""
shared_memory_writer.py — 공유 메모리 원자적 쓰기 유틸리티

사용법:
  python shared_memory_writer.py update <파일명> <내용>
  python shared_memory_writer.py handoff  # 핸드오프 노트 업데이트 (stdin에서 읽기)

직접 import:
  from shared_memory_writer import write_shared, update_handoff
"""
import fcntl
import os
import sys
import json
from datetime import datetime

SHARED_DIR = os.path.join(os.path.expanduser("~"), "shared_memory")


def write_shared(filename: str, content: str) -> None:
    """공유 메모리 파일을 원자적으로 쓴다 (파일 잠금 + tmp 교체)."""
    filepath = os.path.join(SHARED_DIR, filename)
    lock_path = filepath + ".lock"
    os.makedirs(SHARED_DIR, exist_ok=True)

    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            tmp = filepath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, filepath)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def update_handoff(
    completed: list[str],
    in_progress: list[str],
    next_tasks: list[str],
    open_decisions: list[str] = None,
    related_files: list[str] = None,
    source: str = "unknown",
) -> None:
    """핸드오프 노트를 업데이트한다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Handoff Note",
        f"<!-- 마지막 업데이트: {now} | 출처: {source} -->",
        f"",
        f"## 완료한 작업",
    ]
    for item in completed:
        lines.append(f"- {item}")

    lines += ["", "## 진행 중 (여기서 멈춤)"]
    for item in in_progress:
        lines.append(f"- {item}")

    lines += ["", "## 다음 작업"]
    for i, item in enumerate(next_tasks, 1):
        lines.append(f"{i}. {item}")

    if related_files:
        lines += ["", "## 관련 파일"]
        for f in related_files:
            lines.append(f"- {f}")

    if open_decisions:
        lines += ["", "## 열린 결정사항"]
        for item in open_decisions:
            lines.append(f"- {item}")
    else:
        lines += ["", "## 열린 결정사항", "없음"]

    write_shared("handoff.md", "\n".join(lines) + "\n")
    print(f"[shared_memory] handoff.md 업데이트 완료 ({now})")


def read_handoff() -> str:
    """핸드오프 노트를 읽는다."""
    filepath = os.path.join(SHARED_DIR, "handoff.md")
    if not os.path.exists(filepath):
        return "핸드오프 노트 없음"
    with open(filepath, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python shared_memory_writer.py [read-handoff|test]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "read-handoff":
        print(read_handoff())
    elif cmd == "test":
        update_handoff(
            completed=["테스트 완료 작업"],
            in_progress=["테스트 진행 중 작업"],
            next_tasks=["다음 할 일 1", "다음 할 일 2"],
            source="test",
        )
        print(read_handoff())
    else:
        print(f"알 수 없는 명령: {cmd}")
        sys.exit(1)
```

- [ ] **Step 2: 동작 검증**

```bash
cd /home/ubuntu && python3 shared_memory_writer.py test
```

예상 출력:
```
[shared_memory] handoff.md 업데이트 완료 (2026-04-20 HH:MM)
# Handoff Note
...
```

---

## Task 3: Claude Code CLAUDE.md 업데이트

**Files:**
- Modify: `/home/ubuntu/CLAUDE.md`

- [ ] **Step 1: 현재 CLAUDE.md 끝에 shared_memory 섹션 추가**

`/home/ubuntu/CLAUDE.md` 끝에 아래 내용 추가:

```markdown
---

## Shared Memory (Claude Code ↔ 텔레그램 봇 공유)

세션 시작 시 `/home/ubuntu/shared_memory/MEMORY.md`를 읽고 링크된 파일들을 로드한다.

### 공유 메모리 업데이트 기준
아래 중 하나에 해당하면 `shared_memory/`에 기록 (나머지는 private memory에만):
- 프로젝트 전반에 적용되는 규칙/정책 변경
- 사용자 작업 스타일/선호도
- 비즈니스 도메인 지식 (채널 구조, 데이터 소스 합의 등)
- 대시보드 운영 정책

스팟성 작업(이번 주 데이터 업데이트, 특정 버그 수정 과정 등)은 shared_memory에 기록하지 않는다.

공유 메모리 파일 쓰기는 반드시 `shared_memory_writer.py`를 통해 원자적으로 처리:
```bash
from shared_memory_writer import write_shared
write_shared("파일명.md", 내용)
```

### 핸드오프 (봇으로 넘길 때)
사용자가 "봇으로 넘길게, 핸드오프 써줘" 또는 유사한 말을 하면:

1. 오늘 완료한 작업, 진행 중인 작업, 다음 할 일을 정리한다
2. `shared_memory_writer.update_handoff()`를 호출하여 handoff.md를 업데이트한다
3. 관련 shared_memory도 최신 내용으로 업데이트한다

### 핸드오프 받을 때 (봇에서 온 경우)
세션 시작 시 사용자가 "클코에서 하던 거 이어서 해줘" 또는 유사한 말을 하면:

1. `/home/ubuntu/shared_memory/handoff.md`를 읽는다
2. 진행 중 작업과 다음 할 일을 파악한다
3. 이어서 작업한다
```

---

## Task 4: 텔레그램 봇 CLAUDE.md 업데이트

**Files:**
- Modify: `/home/ubuntu/sonolbot/CLAUDE.md`

- [ ] **Step 1: 봇 CLAUDE.md에 shared_memory 섹션 추가**

`/home/ubuntu/sonolbot/CLAUDE.md` 끝에 아래 내용 추가:

```markdown
---

## Shared Memory (Claude Code ↔ 텔레그램 봇 공유)

세션 시작 시 `/home/ubuntu/shared_memory/MEMORY.md`를 읽고 링크된 파일들을 로드한다.

### 공유 메모리 업데이트 기준
아래 중 하나에 해당하면 `shared_memory/`에 기록 (나머지는 private memory에만):
- 프로젝트 전반에 적용되는 규칙/정책 변경
- 사용자 작업 스타일/선호도
- 비즈니스 도메인 지식

스팟성 작업(데이터 업데이트, 특정 버그 수정 등)은 shared_memory에 기록하지 않는다.

공유 메모리 파일 쓰기:
```bash
cd /home/ubuntu && python3 shared_memory_writer.py
# 또는 Python에서:
import sys; sys.path.insert(0, '/home/ubuntu')
from shared_memory_writer import write_shared, update_handoff
```

### 핸드오프 받을 때 (Claude Code에서 온 경우)
사용자가 "클코에서 하던 거 이어서 해줘" 또는 유사한 말을 하면:

1. `/home/ubuntu/shared_memory/handoff.md`를 읽는다
2. 진행 중 작업과 다음 할 일을 파악한다
3. 이어서 작업한다

### 봇에서 Claude Code로 넘길 때
사용자가 "클코로 넘길게" 또는 유사한 말을 하면:

1. 오늘 완료한 작업, 진행 중인 작업, 다음 할 일을 정리한다
2. `update_handoff()`를 호출하여 handoff.md를 업데이트한다
```

---

## Task 5: 동작 검증

- [ ] **Step 1: shared_memory 파일 구조 확인**

```bash
ls -la /home/ubuntu/shared_memory/
```

예상 출력: `MEMORY.md`, `handoff.md`, `feedback_*.md`, `project_*.md` 파일들

- [ ] **Step 2: CLAUDE.md 참조 확인**

```bash
grep -n "shared_memory" /home/ubuntu/CLAUDE.md | head -5
grep -n "shared_memory" /home/ubuntu/sonolbot/CLAUDE.md | head -5
```

- [ ] **Step 3: shared_memory_writer 동작 확인**

```bash
cd /home/ubuntu && python3 shared_memory_writer.py test
cat /home/ubuntu/shared_memory/handoff.md
```

- [ ] **Step 4: git 커밋**

```bash
cd /home/ubuntu/Shaker-MD-App
git add docs/superpowers/plans/2026-04-20-shared-memory-handoff.md
git commit -m "docs: add shared memory + handoff system implementation plan"
git push origin main
```
