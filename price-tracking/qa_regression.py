#!/usr/bin/env python3
"""
Price Q&A 회귀 검증 — **오답은 내가 찾는다. 형님이 찾게 하지 않는다.**

2026-08-31 형님 지적: "오답을 내가 찾아라? 그럼 고쳐준다? 그럼 Q&A가 왜 필요해?"
정당한 지적이다. 단발 테스트로 "작동합니다"라고 보고한 것이 20% 오답을 가렸다.

무엇을 하나:
  질문 세트를 N회씩 돌려
  ① 편차(같은 질문에 다른 답이 나오는가)
  ② 정답 대조(내가 손으로 짠 기대 SQL의 결과와 맞는가)
  를 측정한다. 하나라도 깨지면 exit 1 + 텔레그램.

실패한 유형은 즉시 템플릿(match_template)으로 승격하는 것이 원칙이다.

사용:
  python3 qa_regression.py            # 전체, 각 3회
  python3 qa_regression.py --runs 5   # 반복 횟수 지정
  python3 qa_regression.py --only 모델 # 태그 필터
  python3 qa_regression.py --notify   # 실패 시 텔레그램
"""
import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import price_qa_server as S  # noqa: E402


def truth(sql, params=()):
    """기대값 — 서버를 거치지 않고 DB에서 직접 구한다(자기 자신으로 자기를 검증하지 않기 위해)."""
    con = sqlite3.connect(f"file:{S.DB}?mode=ro", uri=True)
    try:
        return [tuple(r) for r in con.execute(sql, params)]
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────
# 질문 세트 — 형님이 실제로 물으실 법한 것들.
# check(cols, rows) -> (통과여부, 사유)
# ─────────────────────────────────────────────────────────────
def _chans(cols, rows):
    """결과에서 채널 이름 집합을 뽑는다(컬럼명이 무엇이든)."""
    idx = next((i for i, c in enumerate(cols)
                if any(k in str(c) for k in ("채널", "유통", "매장"))), 0)
    return {str(r[idx]) for r in rows if r[idx] is not None}


def chk_model_channels(model):
    """그 모델을 파는 **모든 채널**이 결과에 있어야 한다. 하나라도 빠지면 실패."""
    def f(cols, rows):
        want = {r[0] for r in truth(
            "SELECT DISTINCT ch.name FROM products p JOIN channels ch ON ch.id=p.channel_id "
            "WHERE p.v6_model=?", (model,))}
        got = _chans(cols, rows)
        missing = want - got
        if missing:
            return False, f"채널 누락 {sorted(missing)} (기대 {len(want)}개 / 실제 {len(got)}개)"
        return True, f"채널 {len(want)}개 전부"
    return f


DATE_VAL = __import__("re").compile(r"^\d{4}-\d{2}(-\d{2})?$")


def chk_has_date(cols, rows):
    """'최신가'를 물었으면 **언제 기준인지** 반드시 있어야 한다. 날짜 없는 가격은 오해를 부른다.

    ⚠️ 컬럼명만 보면 '최종수집일'·'월' 같은 정상 컬럼을 놓친다(1차 회귀에서 오탐 2건).
       **실제 값이 YYYY-MM 또는 YYYY-MM-DD 형태인지**로 판정하는 것이 확실하다."""
    if not rows:
        return False, "결과 0건"
    for i in range(len(cols)):
        vals = [r[i] for r in rows[:20] if r[i] is not None]
        if vals and all(DATE_VAL.match(str(v)) for v in vals):
            return True, f"시점 컬럼 '{cols[i]}'"
    return False, f"시점 컬럼 없음 — 언제 값인지 알 수 없다 (컬럼: {list(cols)[:6]})"


def chk_price_sane(cols, rows):
    """가격 컬럼에 **가격이 아닌 값**이 섞이지 않았는가.

    2026-08-31 실제 오답: eXtra `fj`(판매가의 1/20 수준 적립성 금액)를 '멤버십가'로 제시해
    18K 에어컨을 242 SAR로 안내했다. 가격끼리 20배 차이는 물리적으로 불가능하다."""
    pcols = [i for i, c in enumerate(cols)
             if any(k in str(c) for k in ("가", "price", "SAR")) and "율" not in str(c)
             and "일" not in str(c) and "수" not in str(c)]
    vals = [float(r[i]) for i in pcols for r in rows
            if isinstance(r[i], (int, float)) and r[i] and r[i] > 0]
    if len(vals) < 2:
        return True, "가격 표본 부족 — 검사 생략"
    lo, hi = min(vals), max(vals)
    if lo < hi / 8:
        return False, f"가격 컬럼에 비가격 값 의심: 최저 {lo:,.0f} vs 최고 {hi:,.0f} ({hi/lo:.0f}배)"
    return True, f"가격 범위 {lo:,.0f}~{hi:,.0f}"


def chk_fresh_first(max_lag=3):
    """'현재/최신'을 물었으면 **신선한 행이 위에** 있어야 한다.
    지연된 저가가 맨 위에 오면 그게 현재 최저가로 오독된다(형님이 겪은 오답)."""
    def f(cols, rows):
        li = next((i for i, c in enumerate(cols) if "지연" in str(c)), None)
        if li is None or not rows:
            return True, "지연 컬럼 없음 — 검사 생략"
        first = rows[0][li]
        if isinstance(first, (int, float)) and first > max_lag:
            return False, f"최상단이 {first}일 지연된 행 — 현재가로 오독된다"
        return True, f"최상단 지연 {first}일"
    return f


def chk_no_stale_as_current(cols, rows):
    """지연된 행이 **현재가 컬럼**을 채우고 있으면 안 된다.
    형님 지적: Al Khunaizan 7/14 값(48일 전)이 현재 프로모가로 안내됐다."""
    ci = next((i for i, c in enumerate(cols) if "현재" in str(c)), None)
    li = next((i for i, c in enumerate(cols) if "지연" in str(c)), None)
    if ci is None or li is None:
        return True, "현재가/지연 컬럼 없음 — 검사 생략"
    bad = [r for r in rows if isinstance(r[li], (int, float)) and r[li] > 3 and r[ci] is not None]
    if bad:
        return False, f"지연 {bad[0][li]}일 행이 현재가를 채우고 있다"
    return True, "지연 행은 현재가 비어 있음"


def chk_no_stale_stock(cols, rows):
    """지연된 행에 **재고 상태**를 단정하면 안 된다.
    형님 지적: Technobest 8/15 스냅샷의 '재고있음'이 현재처럼 안내됐다."""
    si = next((i for i, c in enumerate(cols) if "상태" in str(c) or "재고" in str(c)), None)
    li = next((i for i, c in enumerate(cols) if "지연" in str(c)), None)
    if si is None or li is None:
        return True, "상태/지연 컬럼 없음 — 검사 생략"
    for r in rows:
        if isinstance(r[li], (int, float)) and r[li] > 3 and r[si] and "재고있음" in str(r[si]):
            return False, f"지연 {r[li]}일 행이 '재고있음'을 단정한다"
    return True, "지연 행은 재고 단정 없음"


def chk_live_only_avg(cols, rows):
    """'현재 평균가'에 이미 리스팅이 내려간 상품이 섞이면 안 된다."""
    def is_price(c):
        return any(k in str(c) for k in ("평균가", "가_SAR")) 
    if not any(is_price(c) for c in cols) or not rows:
        return True, "평균가 컬럼 없음 — 검사 생략"
    con = sqlite3.connect(f"file:{S.DB}?mode=ro", uri=True)
    try:
        live = con.execute("""
          SELECT ROUND(AVG(COALESCE(s.sl,s.sp))) FROM price_snapshots s
          JOIN products p ON p.id=s.product_id JOIN channels ch ON ch.id=p.channel_id
          WHERE ch.name=? AND UPPER(p.brand)='LG'
            AND s.run_date >= date((SELECT MAX(run_date) FROM price_snapshots),'-30 days')
            AND COALESCE(s.sl,s.sp)>0
            AND p.id IN (SELECT product_id FROM price_snapshots GROUP BY product_id
                         HAVING julianday((SELECT MAX(run_date) FROM price_snapshots))
                                - julianday(MAX(run_date)) <= 3)""", (rows[0][0],)).fetchone()[0]
    finally:
        con.close()
    got = rows[0][1]
    if live and isinstance(got, (int, float)) and abs(got - live) > 1:
        return False, f"{rows[0][0]} 평균가 {got:,.0f} ≠ 판매중 기준 {live:,.0f} (사라진 상품 혼입)"
    return True, "판매중 기준과 일치"


def chk_nonempty(minrows=1):
    def f(cols, rows):
        return (len(rows) >= minrows, f"{len(rows)}행")
    return f


def chk_brands_present(*brands):
    def f(cols, rows):
        blob = json.dumps(rows, ensure_ascii=False).upper()
        miss = [b for b in brands if b.upper() not in blob]
        return (not miss, f"누락 브랜드 {miss}" if miss else "브랜드 전부 포함")
    return f


def chk_channel_count(minimum):
    def f(cols, rows):
        n = len(_chans(cols, rows))
        return (n >= minimum, f"채널 {n}개 (최소 {minimum})")
    return f


CASES = [
    # ── 모델 × 채널 (형님이 실제로 틀렸던 유형) ──────────────
    dict(tag="모델", q="NS182C 가장 최근 가격을 유통별로 알려줘",
         checks=[chk_model_channels("NS182C"), chk_has_date, chk_price_sane, chk_fresh_first(), chk_no_stale_as_current, chk_no_stale_stock]),
    dict(tag="모델", q="NS182C 채널별 최신가",
         checks=[chk_model_channels("NS182C"), chk_has_date, chk_price_sane, chk_fresh_first(), chk_no_stale_as_current, chk_no_stale_stock]),
    dict(tag="모델", q="ND182C 유통사별 지금 얼마야?",
         checks=[chk_model_channels("ND182C"), chk_has_date, chk_price_sane, chk_fresh_first(), chk_no_stale_as_current, chk_no_stale_stock]),
    dict(tag="모델", q="NT382C 어디가 제일 싸?",
         checks=[chk_model_channels("NT382C"), chk_has_date, chk_price_sane, chk_fresh_first(), chk_no_stale_as_current, chk_no_stale_stock]),
    dict(tag="모델", q="APNQ55GT3M 채널별 최근 가격 보여줘",
         checks=[chk_model_channels("APNQ55GT3M"), chk_has_date, chk_price_sane, chk_fresh_first(), chk_no_stale_as_current, chk_no_stale_stock]),
    dict(tag="모델", q="NS182C2.NK2 유통별 가격",
         checks=[chk_model_channels("NS182C"), chk_has_date, chk_price_sane, chk_fresh_first(), chk_no_stale_as_current, chk_no_stale_stock]),

    dict(tag="모델", q="ND182C 모델의 현재 프로모션 각 유통 가격은?",
         checks=[chk_model_channels("ND182C"), chk_has_date, chk_price_sane, chk_fresh_first(), chk_no_stale_as_current, chk_no_stale_stock]),

    # ── 브랜드 · 용량 비교 ────────────────────────────────
    dict(tag="브랜드", q="eXtra에서 18000 BTU LG랑 경쟁사 평균가 비교해줘",
         checks=[chk_nonempty(2), chk_brands_present("LG")]),
    dict(tag="브랜드", q="24000 BTU 구간 브랜드별 평균가 알려줘",
         checks=[chk_nonempty(3), chk_brands_present("LG")]),

    # ── 채널 커버리지 ────────────────────────────────────
    dict(tag="채널", q="채널별 데이터 언제까지 수집됐어?",
         checks=[chk_channel_count(10), chk_has_date]),
    dict(tag="채널", q="채널별 LG 평균가 보여줘",
         checks=[chk_channel_count(8), chk_live_only_avg]),

    # ── 변동 · 추이 ──────────────────────────────────────
    dict(tag="변동", q="지난 7일 경쟁사 중 가격 내린 곳",
         checks=[chk_nonempty(1)]),
    dict(tag="추이", q="LG 18000 BTU 월별 평균가 추이",
         checks=[chk_nonempty(4), chk_has_date]),

    # ── 라인업 ──────────────────────────────────────────
    dict(tag="라인업", q="최근 30일 새로 들어온 경쟁사 제품",
         checks=[chk_nonempty(1)]),
]


def run_case(case, runs):
    """한 질문을 runs회 실행. (편차, 검증실패) 를 반환."""
    sigs, fails, routes, elapsed = [], [], set(), []
    for _ in range(runs):
        t0 = time.time()
        try:
            tpl = S.match_template(case["q"])
            if tpl:
                label, sql, params = tpl
                routes.add("verified")
            else:
                sql = S.sanitize(S.llm([{"role": "system", "content": S.SQL_SYS},
                                        {"role": "user", "content": case["q"]}]))
                params = ()
                routes.add("generated")
            cols, rows = S.run_sql(sql, params)
        except Exception as e:
            fails.append(f"실행오류 {type(e).__name__}: {str(e)[:80]}")
            sigs.append("ERR")
            elapsed.append(time.time() - t0)
            continue
        elapsed.append(time.time() - t0)
        sigs.append(hashlib.md5(json.dumps(rows, ensure_ascii=False,
                                           sort_keys=True, default=str).encode()).hexdigest()[:8])
        for chk in case["checks"]:
            ok, why = chk(cols, rows)
            if not ok:
                fails.append(why)
    return {
        "q": case["q"], "tag": case["tag"],
        "route": "/".join(sorted(routes)),
        "stable": len(set(sigs)) == 1,
        "sigs": sigs,
        "fails": sorted(set(fails)),
        "avg_sec": round(sum(elapsed) / len(elapsed), 1) if elapsed else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", default=None, help="태그 부분일치 필터")
    ap.add_argument("--notify", action="store_true")
    a = ap.parse_args()

    cases = [c for c in CASES if not a.only or a.only in c["tag"] or a.only in c["q"]]
    print(f"Price Q&A 회귀 — {len(cases)}개 질문 × {a.runs}회 "
          f"(기준일 {truth('SELECT MAX(run_date) FROM price_snapshots')[0][0]})\n")

    results = [run_case(c, a.runs) for c in cases]

    bad = [r for r in results if not r["stable"] or r["fails"]]
    for r in results:
        mark = "✅" if (r["stable"] and not r["fails"]) else "🔴"
        rt = "검증질의" if r["route"] == "verified" else "AI생성"
        print(f"{mark} [{r['tag']:4s}|{rt:5s}|{str(r['avg_sec']):>5s}s] {r['q'][:44]}")
        if not r["stable"]:
            print(f"     ⚠️ 답이 매번 다름: {r['sigs']}")
        for f in r["fails"]:
            print(f"     ⚠️ {f}")

    n_unstable = sum(1 for r in results if not r["stable"])
    n_wrong = sum(1 for r in results if r["fails"])
    print(f"\n{'─'*60}")
    print(f"질문 {len(results)}개 · 각 {a.runs}회")
    print(f"  불안정(같은 질문에 다른 답): {n_unstable}개")
    print(f"  검증 실패(정답과 불일치)   : {n_wrong}개")
    print(f"  → 판정: {'🔴 실패' if bad else '✅ 전부 통과'}")

    if bad and a.notify:
        lines = ["🔴 *Price Q&A 회귀 실패*", ""]
        for r in bad[:8]:
            lines.append(f"• {r['q'][:40]}")
            if not r["stable"]:
                lines.append("   답이 매번 다름")
            for f in r["fails"][:2]:
                lines.append(f"   {f[:70]}")
        lines += ["", "실패 유형은 검증된 질의 템플릿으로 승격 필요."]
        sys.path.insert(0, "/home/ubuntu/sonolbot")
        from notify import telegram_send
        telegram_send("\n".join(lines))

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
