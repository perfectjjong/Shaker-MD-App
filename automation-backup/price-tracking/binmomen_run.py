#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bin Momen AC - Full Pipeline Runner
  Step 1: binmomen_ac_scraper.py        (스크래핑)
  Step 2: binmomen_ac_dashboard_builder.py  (엑셀 빌드)
  Step 3: binmomen_ac_html_dashboard.py     (HTML 대시보드 생성)
"""

import sys
import os
import subprocess
from datetime import datetime

# Windows console UTF-8
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

STEPS = [
    ("Step 1/3 — Scraper",           "binmomen_ac_scraper.py"),
    ("Step 2/3 — Dashboard Builder",  "binmomen_ac_dashboard_builder.py"),
    ("Step 3/3 — HTML Dashboard",     "binmomen_ac_html_dashboard.py"),
]


def run_step(label: str, script: str) -> bool:
    path = os.path.join(CURRENT_DIR, script)
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    result = subprocess.run(
        [PYTHON, path],
        cwd=CURRENT_DIR,
        # stdout/stderr are inherited → 실시간 출력
    )

    if result.returncode != 0:
        print(f"\n[ERROR] {label} failed (exit code {result.returncode}). Pipeline stopped.")
        return False

    print(f"\n[OK] {label} completed.")
    return True


def main():
    start = datetime.now()
    print(f"Bin Momen Pipeline started at {start.strftime('%Y-%m-%d %H:%M:%S')}")

    for i, (label, script) in enumerate(STEPS):
        if not run_step(label, script):
            sys.exit(1)
        # Scraper(Step 1) 직후 품질 검증 + 자동 재실행
        if i == 0:
            try:
                sys.path.insert(0, os.path.dirname(CURRENT_DIR))
                from scrape_quality_check import run_with_retry
                run_with_retry(
                    {'name': 'Bin Momen', 'master': os.path.join(CURRENT_DIR, 'Binmomen_AC_Data.xlsx'),
                     'sku_col': 'SKU', 'date_col': 'Scrape_Date'},
                    scraper_runner=lambda: run_step("Scraper Retry", script),
                )
            except Exception as e:
                print(f"[Quality Check 오류] {e}")

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"  All steps completed in {elapsed:.1f}s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
