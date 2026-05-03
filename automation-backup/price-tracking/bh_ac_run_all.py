#!/usr/bin/env python3
"""
BH AC Price Tracker - 통합 실행 스크립트 (Run All)
2개 스크립트를 순차 실행합니다:
  1. consolidate_ac.py        - 스크래핑 + 엑셀 마스터 빌드
  2. bh_ac_html_dashboard_v2.py - HTML 대시보드 생성

에러 발생 시 다음 단계로 넘어가지 않고 중단됩니다.
Author: 핍쫑이
Date: 2026-03-19
"""

import subprocess
import sys
import os
import time
from datetime import datetime

# ============================================================
# 설정
# ============================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 실행할 스크립트 목록 (순서대로)
SCRIPTS = [
    {
        "file": "consolidate_ac.py",
        "name": "스크래핑 + 엑셀 마스터 빌드",
        "icon": "🌐",
    },
    {
        "file": "bh_ac_html_dashboard_v2.py",
        "name": "HTML 대시보드 생성",
        "icon": "🖥️",
    },
]

# Python 실행 명령어 (Windows: py, 기타: python3)
PYTHON_CMD = "py" if sys.platform == "win32" else sys.executable


def run_script(script_info, step, total):
    """단일 스크립트 실행 및 결과 반환"""
    filepath = os.path.join(CURRENT_DIR, script_info["file"])
    name = script_info["name"]
    icon = script_info["icon"]

    print(f"\n{'='*60}")
    print(f"  {icon} [{step}/{total}] {name}")
    print(f"     파일: {script_info['file']}")
    print(f"{'='*60}")

    # 파일 존재 확인
    if not os.path.exists(filepath):
        print(f"  ❌ 파일을 찾을 수 없습니다: {filepath}")
        return False

    start_time = time.time()

    try:
        result = subprocess.run(
            [PYTHON_CMD, filepath],
            cwd=CURRENT_DIR,
            capture_output=False,       # 실시간 출력
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,               # 30분 타임아웃
        )

        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        if result.returncode == 0:
            print(f"\n  ✅ {name} 완료 ({minutes}분 {seconds}초)")
            return True
        else:
            print(f"\n  ❌ {name} 실패 (종료코드: {result.returncode})")
            print(f"     소요시간: {minutes}분 {seconds}초")
            return False

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"\n  ⏱️ {name} 타임아웃 (30분 초과)")
        return False
    except FileNotFoundError:
        print(f"\n  ❌ Python 실행 파일을 찾을 수 없습니다: {PYTHON_CMD}")
        print(f"     Python이 설치되어 있고 PATH에 등록되어 있는지 확인하세요.")
        return False
    except Exception as e:
        print(f"\n  ❌ 예기치 않은 오류: {e}")
        return False


def main():
    # Windows 콘솔 UTF-8 설정
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    total = len(SCRIPTS)
    run_start = datetime.now()

    print("=" * 60)
    print("🚀 BH AC Price Tracker - 통합 실행 (Run All)")
    print(f"   시작: {run_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   실행 순서:")
    for i, s in enumerate(SCRIPTS, 1):
        print(f"     {i}. {s['icon']} {s['name']} ({s['file']})")
    print("=" * 60)

    # 순차 실행
    for i, script_info in enumerate(SCRIPTS, 1):
        success = run_script(script_info, i, total)

        if not success:
            print(f"\n{'='*60}")
            print(f"❌ [{i}/{total}] {script_info['name']} 단계에서 실패!")
            print(f"   이후 단계를 건너뜁니다.")
            print(f"{'='*60}")
            break

        # Scraper(Step 1) 직후 품질 검증 + 자동 재실행 (BH RT만 — Weekly_Price_DB)
        if i == 1:
            try:
                from pathlib import Path as _P
                _SCRIPT_DIR = _P(__file__).parent
                sys.path.insert(0, str(_SCRIPT_DIR.parent))
                from scrape_quality_check import run_with_retry
                run_with_retry(
                    {'name': 'BH', 'master': _SCRIPT_DIR / 'BH_Subdealer_AC_Master.xlsx',
                     'sku_col': 'Model Code', 'date_col': 'Run Timestamp', 'sheet_name': 'Weekly_Price_DB'},
                    scraper_runner=lambda: run_script(script_info, i, total),
                )
            except Exception as e:
                print(f"[Quality Check 오류] {e}")
    else:
        # 모든 스크립트 성공
        run_end = datetime.now()
        elapsed = run_end - run_start
        minutes = int(elapsed.total_seconds() // 60)
        seconds = int(elapsed.total_seconds() % 60)

        print(f"\n{'='*60}")
        print(f"🎉 전체 완료!")
        print(f"   시작: {run_start.strftime('%H:%M:%S')}")
        print(f"   종료: {run_end.strftime('%H:%M:%S')}")
        print(f"   소요: {minutes}분 {seconds}초")
        print(f"{'='*60}")

    # 수동 실행 시에만 대기
    try:
        if sys.stdin.isatty():
            input("\n 엔터를 누르면 종료...")
    except (EOFError, OSError):
        pass


if __name__ == "__main__":
    main()
