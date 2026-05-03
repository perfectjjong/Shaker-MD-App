#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SWS AC — 통합 실행 파일 (스케줄러용)
  1단계: 스크래퍼  (swsg_ac_scraper_v12.py)   → Master Excel 누적 저장
  2단계: 대시보드  (sws_ac_html_dashboard.py) → HTML 생성 + GitHub/Cloudflare 배포

스케줄러 등록 예시 (Windows 작업 스케줄러):
  python "C:/Users/J_park/Documents/2026/01. Work/06. Price Tracking/02. SWS/sws_ac_run.py"
"""

import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
SCRAPER    = SCRIPT_DIR / 'swsg_ac_scraper_v12.py'
DASHBOARD  = SCRIPT_DIR / 'sws_ac_html_dashboard.py'
LOG_FILE   = SCRIPT_DIR / 'sws_ac_run.log'

# stdout → UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass


def log(msg: str):
    """콘솔 + 로그 파일에 동시 출력"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def run_step(label: str, script: Path) -> bool:
    log(f"{'='*60}")
    log(f"START: {label}")
    log(f"{'='*60}")

    if not script.exists():
        log(f"[ERROR] Script not found: {script}")
        return False

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(SCRIPT_DIR),
        stdin=subprocess.DEVNULL,  # input() 대기 없이 즉시 EOFError → 자동 통과
    )

    if result.returncode == 0:
        log(f"[OK] {label} completed successfully.")
        return True
    else:
        log(f"[ERROR] {label} failed — returncode={result.returncode}")
        return False


def main():
    started = datetime.now()
    log(f"{'#'*60}")
    log(f"SWS AC Runner started")
    log(f"{'#'*60}")

    # ── Step 1: Scraper ──────────────────────────────────────────
    ok_scraper = run_step("Scraper (swsg_ac_scraper_v12)", SCRAPER)

    # ── Step 1.5: 품질 검증 + 자동 재실행 (-10%+ 누락 시) ──────────
    if ok_scraper:
        try:
            sys.path.insert(0, str(SCRIPT_DIR.parent))
            from scrape_quality_check import run_with_retry
            run_with_retry(
                {'name': 'SWS', 'master': SCRIPT_DIR / 'SWS_AC_Price_Tracking_Master.xlsx',
                 'sku_col': 'Product ID', 'date_col': 'Timestamp', 'sheet_name': 'Products_DB'},
                scraper_runner=lambda: run_step("Scraper Retry", SCRAPER),
                log_func=log,
            )
        except Exception as e:
            log(f"[Quality Check 오류] {e}")

    # ── Step 2: Dashboard (스크래퍼 성공 여부 관계없이 실행) ──────
    #   이미 Excel에 데이터가 쌓여 있다면 대시보드는 항상 최신 기준으로 생성
    ok_dashboard = run_step("Dashboard (sws_ac_html_dashboard)", DASHBOARD)

    # ── 결과 요약 ────────────────────────────────────────────────
    elapsed = (datetime.now() - started).seconds
    log(f"{'#'*60}")
    log(f"DONE — elapsed: {elapsed}s  |  scraper={'OK' if ok_scraper else 'FAIL'}  |  dashboard={'OK' if ok_dashboard else 'FAIL'}")
    log(f"{'#'*60}\n")

    # 둘 다 실패 시 exit code 1 반환 (스케줄러에서 실패 감지용)
    if not ok_scraper and not ok_dashboard:
        sys.exit(1)


if __name__ == '__main__':
    main()
