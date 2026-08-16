#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Price Tracking 대시보드 야간모드(22:00~06:00) 재적용 — 멱등(idempotent) 후처리기.

배경:
  가격추적 cron(매일 00:00 UTC)이 채널별 생성기로 대시보드 HTML을 통째로 새로
  써버리기 때문에, 배포본에 직접 넣은 야간모드가 매일 밤 사라졌다.
  (2026-08-17 00:12 커밋에서 almanea-price 등 야간모드 92줄 삭제 확인)

해결:
  생성 직후 이 스크립트를 돌려 야간모드를 다시 주입한다.
  이미 적용돼 있으면 아무것도 하지 않는다(멱등).

사용:
  python3 price-tracking/darkmode/apply_night_mode.py            # 전체
  python3 price-tracking/darkmode/apply_night_mode.py bh-price   # 특정 채널
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DASH_DIR = os.path.join(REPO, 'docs', 'dashboards')
BLOCKS_DIR = os.path.join(HERE, 'blocks')          # 대시보드별 고유 블록
BLOCK_FILE = os.path.join(HERE, 'night_mode_block.txt')  # 폴백(공통)

PRICE_DASHBOARDS = [
    'extra-price', 'almanea-price', 'blackbox-price', 'alkhunaizan-price',
    'bh-price', 'binmomen-price', 'sws-price', 'najm-price',
    'technobest-price', 'tamkeen-price', 'alshathri-price',
]

MARKER = 'NIGHT_START'


def load_block(name=None):
    """대시보드 고유 블록 우선, 없으면 공통 폴백.

    대시보드마다 사용하는 CSS 클래스가 달라(예: sws-price 124규칙 vs technobest 79규칙)
    남의 블록을 넣으면 커버되지 않는 영역이 밝게 남는다.
    """
    path = os.path.join(BLOCKS_DIR, f'{name}.txt') if name else None
    if not path or not os.path.exists(path):
        path = BLOCK_FILE
    raw = open(path, encoding='utf-8').read()
    script, css = raw.split('<!--CSS-->')
    return script.strip(), css.strip()


def apply(path, script, css):
    """야간모드 스크립트 + html.dark CSS 주입. 이미 있으면 skip."""
    html = open(path, encoding='utf-8').read()
    if MARKER in html:
        return 'skip'

    # 1) </head> 직전에 스크립트 삽입 (없으면 <body> 앞)
    if '</head>' in html:
        html = html.replace('</head>', script + '\n</head>', 1)
    elif '<body' in html:
        i = html.index('<body')
        html = html[:i] + script + '\n' + html[i:]
    else:
        return 'no-anchor'

    # 2) 마지막 </style> 직전에 CSS 삽입 (없으면 <style> 블록 신설)
    if '</style>' in html:
        i = html.rindex('</style>')
        html = html[:i] + '\n' + css + '\n' + html[i:]
    else:
        html = html.replace('</head>', '<style>\n' + css + '\n</style>\n</head>', 1)

    open(path, 'w', encoding='utf-8').write(html)
    return 'applied'


def main():
    if not os.path.isdir(BLOCKS_DIR) and not os.path.exists(BLOCK_FILE):
        print(f"[ERROR] 야간모드 블록이 없습니다: {BLOCKS_DIR}")
        return 1

    targets = sys.argv[1:] or PRICE_DASHBOARDS
    applied = skipped = missing = 0
    for name in targets:
        path = os.path.join(DASH_DIR, name, 'index.html')
        if not os.path.exists(path):
            print(f"  [MISS] {name}")
            missing += 1
            continue
        script, css = load_block(name)
        r = apply(path, script, css)
        if r == 'applied':
            print(f"  [OK]   {name} — 야간모드 주입")
            applied += 1
        elif r == 'skip':
            print(f"  [SKIP] {name} — 이미 적용됨")
            skipped += 1
        else:
            print(f"  [WARN] {name} — 삽입 지점 없음")
    print(f"\n야간모드: 적용 {applied} / 유지 {skipped} / 누락 {missing}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
