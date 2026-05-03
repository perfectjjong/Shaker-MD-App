#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TechnoBest AC - 순차 실행 스크립트
  1단계: technobest_ac_scraper.py   (스크래핑 + 엑셀 저장)
  2단계: technobest_ac_html_dashboard.py (대시보드 HTML 생성 + 배포)

스케줄러(Windows 작업 스케줄러 등)에 이 파일 하나만 등록하면 됩니다.
"""

import sys
import io
import os
import subprocess
from datetime import datetime

# Windows console UTF-8
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON     = sys.executable  # 현재 가상환경/인터프리터 사용

STEPS = [
    ("Scraper",    os.path.join(SCRIPT_DIR, "technobest_ac_scraper.py")),
    ("Dashboard",  os.path.join(SCRIPT_DIR, "technobest_ac_html_dashboard.py")),
]


def run_step(label: str, script: str) -> bool:
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] STEP: {label}")
    print(f"  Script : {script}")
    print(f"{'='*60}")

    result = subprocess.run(
        [PYTHON, script],
        cwd=SCRIPT_DIR,
        # 자식 프로세스의 stdout/stderr를 그대로 콘솔에 출력
        stdout=None,
        stderr=None,
    )

    if result.returncode != 0:
        print(f"\n[ERROR] {label} failed (exit code {result.returncode})")
        return False

    print(f"\n[OK] {label} completed successfully.")
    return True


def main():
    start = datetime.now()
    print(f"TechnoBest AC Pipeline started at {start.strftime('%Y-%m-%d %H:%M:%S')}")

    for i, (label, script) in enumerate(STEPS):
        if not run_step(label, script):
            print(f"\nPipeline aborted at step: {label}")
            sys.exit(1)
        # Scraper(Step 1) 직후 품질 검증 + 자동 재실행
        if i == 0:
            try:
                sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
                from scrape_quality_check import run_with_retry
                run_with_retry(
                    {'name': 'Techno Best', 'master': os.path.join(SCRIPT_DIR, 'TechnoBest_AC_Master.xlsx'),
                     'sku_col': 'product_id', 'date_col': 'scrape_date'},
                    scraper_runner=lambda: run_step("Scraper Retry", script),
                )
            except Exception as e:
                print(f"[Quality Check 오류] {e}")

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"All steps completed. Total time: {elapsed:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
