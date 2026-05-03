#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tamkeen Auto Runner
순서: 1) tamkeen_final_scraper.py → 2) tamkeen_ac_html_dashboard.py
스케줄러(Task Scheduler) 등록용 — 사용자 입력 없이 자동 실행
"""

import sys
import io
import os
import subprocess
import time
from datetime import datetime

# Windows 콘솔 UTF-8
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRAPER    = os.path.join(SCRIPT_DIR, "tamkeen_final_scraper.py")
DASHBOARD  = os.path.join(SCRIPT_DIR, "tamkeen_ac_html_dashboard.py")
LOG_FILE   = os.path.join(SCRIPT_DIR, "tamkeen_run.log")

def log(msg: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def run_step(label: str, script: str) -> bool:
    log(f"{'='*60}")
    log(f"STEP: {label}")
    log(f"{'='*60}")
    start = time.time()
    result = subprocess.run(
        [sys.executable, script],
        cwd=SCRIPT_DIR,
        # stdout/stderr을 파이프로 받아 실시간 출력
        stdout=None,  # 상속 → 터미널에 직접 출력
        stderr=None,
    )
    elapsed = time.time() - start
    if result.returncode == 0:
        log(f"OK: {label} 완료 ({elapsed:.1f}s)")
        return True
    else:
        log(f"ERROR: {label} 실패 (exit code {result.returncode}, {elapsed:.1f}s)")
        return False

MAX_SCRAPE_RETRY = 3
RETRY_DELAY      = 30  # seconds

def main():
    log("Tamkeen Auto Runner 시작")

    # ── Step 1: 스크래핑 (재시도 포함) ────────────────────────
    ok = False
    for attempt in range(1, MAX_SCRAPE_RETRY + 1):
        success = run_step(f"스크래핑 시도 {attempt}/{MAX_SCRAPE_RETRY} (tamkeen_final_scraper.py)", SCRAPER)
        if success:
            ok = True
            break
        # exit code 2 = 과소 수집 감지 (재시도 가치 있음)
        if attempt < MAX_SCRAPE_RETRY:
            log(f"스크래핑 실패 → {RETRY_DELAY}초 후 재시도 ({attempt}/{MAX_SCRAPE_RETRY})")
            time.sleep(RETRY_DELAY)

    if not ok:
        log(f"스크래핑 {MAX_SCRAPE_RETRY}회 시도 후 실패 → 대시보드 생성 건너뜀 (이전 데이터 유지)")
        sys.exit(1)

    # ── Step 1.5: 파일 기반 품질 검증 (-10%+ 누락 시 telegram 알림) ──
    # Tamkeen은 매일 별도 파일로 저장 + 자체 3회 재시도 내장 → 추가 retry 없이 알림만
    try:
        sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
        from scrape_quality_check import check_scrape_quality_filebased, notify_telegram
        ok_q, msg_q = check_scrape_quality_filebased(
            directory=SCRIPT_DIR,
            pattern='Tamkeen_Complete_*.xlsx',
            sku_col='SKU',
            sheet_name='All Products',
            retry_threshold_pct=10.0,
        )
        log(f"[Quality Check] {msg_q}")
        if not ok_q:
            notify_telegram(f"[Tamkeen Quality 경고] {msg_q}\n자체 3회 재시도 후에도 누락 발생 → 수동 점검 권고")
    except Exception as e:
        log(f"[Quality Check 오류] {e}")

    # ── Step 2: 대시보드 생성 ─────────────────────────────────
    ok = run_step("대시보드 생성 (tamkeen_ac_html_dashboard.py)", DASHBOARD)
    if not ok:
        log("대시보드 생성 실패")
        sys.exit(1)

    log("모든 작업 완료")

if __name__ == '__main__':
    main()
