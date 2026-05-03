#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blackbox AC Pipeline Runner
============================
Runs the three scripts in sequence:
  Step 1. blackbox_ac_scraper.py          — Scrape & accumulate data into Master XLSX
  Step 2. blackbox_ac_dashboard_builder.py — Build Excel dashboard sheets
  Step 3. blackbox_ac_html_dashboard_v2.py — Generate self-contained HTML dashboard

Usage:
  python blackbox_ac_run_all.py
"""

import sys
import os
import subprocess
import time
from pathlib import Path

# ── UTF-8 output ──────────────────────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).parent

STEPS = [
    ("Scraper          (1/3)", "blackbox_ac_scraper.py"),
    ("Excel Dashboard  (2/3)", "blackbox_ac_dashboard_builder.py"),
    ("HTML Dashboard   (3/3)", "blackbox_ac_html_dashboard_v2.py"),
]


def run_step(label: str, script: str) -> bool:
    script_path = SCRIPT_DIR / script
    if not script_path.exists():
        print(f"  [ERROR] Script not found: {script_path}")
        return False

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"  >> {script}")
    print(f"{'=' * 60}")

    start = time.time()
    result = subprocess.run(
        [sys.executable, str(script_path)],
        stdin=subprocess.DEVNULL,   # suppress "Press Enter" prompts
        cwd=str(SCRIPT_DIR),
    )
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n  [FAILED] {script} exited with code {result.returncode}")
        return False

    print(f"\n  [OK] Completed in {elapsed:.1f}s")
    return True


def main():
    print("=" * 60)
    print("  Blackbox AC Pipeline Runner")
    print("=" * 60)
    print(f"  Working dir : {SCRIPT_DIR}")
    print(f"  Python      : {sys.executable}")

    total_start = time.time()

    for i, (label, script) in enumerate(STEPS):
        ok = run_step(label, script)
        if not ok:
            print(f"\n  Pipeline stopped at: {script}")
            print("  Fix the error above and re-run.")
            sys.exit(1)
        # Scraper(Step 1) 직후 품질 검증 + 자동 재실행
        if i == 0:
            try:
                sys.path.insert(0, str(SCRIPT_DIR.parent))
                from scrape_quality_check import run_with_retry
                run_with_retry(
                    {'name': 'Black Box', 'master': SCRIPT_DIR / 'Black Box_AC_Price tracking_Master.xlsx',
                     'sku_col': 'Model Code', 'date_col': 'Scraped At', 'sheet_name': 'Product_DB'},
                    scraper_runner=lambda: run_step("Scraper Retry", script),
                )
            except Exception as e:
                print(f"[Quality Check 오류] {e}")

    total_elapsed = time.time() - total_start
    print(f"\n{'=' * 60}")
    print(f"  All 3 steps completed successfully! ({total_elapsed:.1f}s total)")
    print(f"{'=' * 60}")

    try:
        if sys.stdin.isatty():
            input("\n  Press Enter to exit...")
    except (EOFError, OSError):
        pass


if __name__ == "__main__":
    main()
