#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Almanea AC Pipeline — 통합 실행 스크립트
실행 순서:
  1. almanea_ac_v3.py          → API 스크래핑 → Master.xlsx 저장
  2. almanea_ac_master_dashboard.py → 엑셀 대시보드 시트 생성
  3. almanea_ac_html_dashboard_v2.py → HTML 대시보드 생성 + GitHub Pages 배포
"""

import os
import sys
import time
import importlib.util

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_module(filename):
    """같은 디렉토리의 .py 파일을 모듈로 로드"""
    path = os.path.join(SCRIPT_DIR, filename)
    if not os.path.exists(path):
        print(f"[ERROR] 파일 없음: {path}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location(filename.replace('.py', ''), path)
    mod = importlib.util.module_from_spec(spec)
    return mod, spec


def main():
    print()
    print("═" * 65)
    print("  Almanea AC Pipeline — 통합 실행")
    print("  1) Scrape → 2) Excel Dashboard → 3) HTML Dashboard + Deploy")
    print("═" * 65)
    t0 = time.time()

    # ── STEP 1: Scraper ──────────────────────────────────────────────────────
    print("\n" + "─" * 65)
    print("  STEP 1/3: API Scraping (almanea_ac_v3.py)")
    print("─" * 65)
    try:
        mod, spec = _load_module('almanea_ac_v3.py')
        # input() 호출을 무시하도록 패치
        import builtins
        _orig_input = builtins.input
        builtins.input = lambda *a, **kw: None
        try:
            spec.loader.exec_module(mod)
            mod.main()
        finally:
            builtins.input = _orig_input
        print("  [STEP 1 완료]")
    except Exception as e:
        print(f"  [ERROR] Scraping 실패: {e}")
        import traceback; traceback.print_exc()
        print("  Master.xlsx가 이미 있으면 STEP 2로 계속 진행합니다.")

    # ── STEP 2: Excel Dashboard ──────────────────────────────────────────────
    print("\n" + "─" * 65)
    print("  STEP 2/3: Excel Dashboard (almanea_ac_master_dashboard.py)")
    print("─" * 65)
    try:
        mod2, spec2 = _load_module('almanea_ac_master_dashboard.py')
        _orig_input2 = builtins.input
        builtins.input = lambda *a, **kw: None
        try:
            spec2.loader.exec_module(mod2)
            mod2.main()
        finally:
            builtins.input = _orig_input2
        print("  [STEP 2 완료]")
    except Exception as e:
        print(f"  [ERROR] Excel Dashboard 실패: {e}")
        import traceback; traceback.print_exc()
        print("  STEP 3으로 계속 진행합니다.")

    # ── STEP 3: HTML Dashboard + Deploy ──────────────────────────────────────
    print("\n" + "─" * 65)
    print("  STEP 3/3: HTML Dashboard + Deploy (almanea_ac_html_dashboard_v2.py)")
    print("─" * 65)
    try:
        # HTML dashboard는 모듈 레벨에서 실행되므로 exec으로 처리
        html_path = os.path.join(SCRIPT_DIR, 'almanea_ac_html_dashboard_v2.py')
        with open(html_path, 'r', encoding='utf-8') as f:
            code = f.read()
        exec(compile(code, html_path, 'exec'), {'__name__': '__html_dashboard__', '__file__': html_path})
        print("  [STEP 3 완료]")
    except Exception as e:
        print(f"  [ERROR] HTML Dashboard 실패: {e}")
        import traceback; traceback.print_exc()

    elapsed = time.time() - t0
    print("\n" + "═" * 65)
    print(f"  Pipeline 완료! (총 {elapsed:.1f}초)")
    print("  https://perfectjjong.github.io/almanea-ac-price-tracker/")
    print("═" * 65)

    try:
        if sys.stdin.isatty():
            input("\n  엔터를 누르면 종료...")
    except (EOFError, OSError):
        pass


if __name__ == '__main__':
    main()
