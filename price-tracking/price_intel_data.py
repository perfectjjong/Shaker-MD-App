#!/usr/bin/env python3
"""
Price Intelligence — 검증된 경영 질문 카드용 데이터 산출.

자유 질의(text-to-SQL)가 아니라 **고정·검증된 질문 세트**만 계산한다.
숫자가 항상 같은 경로로 나오는 것이 이 파일의 존재 이유다.

원칙:
- 결손은 None. 거짓 0을 만들지 않는다.
- 브랜드는 항상 UPPER() 비교 (원본에 Gree/GREE 혼재).
- 기준일은 date('now')가 아니라 DB의 MAX(run_date) — 수집 결손일이 있다.
- 추세 비교는 **동일 SKU**로 한정해 라인업 변화(믹스) 착시를 제거한다.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("/home/ubuntu/2026/06. Price Tracking/price_data.db")

# 경쟁 우선순위 5사 (CLAUDE.md 도메인) + 우리
FOCUS_BRANDS = ["SAMSUNG", "GREE", "MIDEA", "HISENSE", "TCL"]

# BTU 급 — 사우디 AC 시장 통용 구간
BTU_BANDS = [
    ("9~10K", 8500, 10500),
    ("12K", 11000, 13000),
    ("18K", 17000, 19000),
    ("21~24K", 20500, 24500),
    ("30K", 29000, 31000),
    ("36K+", 35000, 100000),
]


def _conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


def _px(alias="s"):
    """기준가. 채널별 alert_basis가 다르지만 sl(프로모가)이 표준이고 결측 시 sp 폴백.
    Black Box는 fp가 기준이나 sl도 채워져 있어 비교 일관성을 위해 sl 통일."""
    return f"COALESCE({alias}.sl, {alias}.sp)"


def anchor_date(c):
    return c.execute("SELECT MAX(run_date) FROM price_snapshots").fetchone()[0]


# ─────────────────────────────────────────────────────────────
# 카드 0 — 데이터 신선도 (모든 숫자의 신뢰 근거)
# ─────────────────────────────────────────────────────────────
def freshness(c):
    anchor = anchor_date(c)
    rows = []
    for r in c.execute("""
        SELECT ch.code, ch.name, MAX(s.run_date) last_date,
               COUNT(*) snaps, COUNT(DISTINCT p.id) skus
        FROM price_snapshots s
        JOIN products p ON p.id = s.product_id
        JOIN channels ch ON ch.id = p.channel_id
        GROUP BY ch.code ORDER BY last_date DESC, ch.name"""):
        lag = (
            (__import__("datetime").date.fromisoformat(anchor)
             - __import__("datetime").date.fromisoformat(r["last_date"])).days
        )
        rows.append({
            "code": r["code"], "name": r["name"], "last_date": r["last_date"],
            "lag_days": lag, "snaps": r["snaps"], "skus": r["skus"],
            "stale": lag > 2,
        })
    return {"anchor": anchor, "channels": rows,
            "stale_count": sum(1 for x in rows if x["stale"])}


# ─────────────────────────────────────────────────────────────
# 카드 1 — LG vs 경쟁 가격 갭 추이 (동일 SKU, 믹스 제거)
# ─────────────────────────────────────────────────────────────
MIN_MONTH_DAYS = 15  # 수집일이 이보다 적은 달은 월평균을 대표하지 못한다


def gap_trend(c, band=("18K", 17000, 19000)):
    """월별 LG·경쟁 평균가. 전 구간에 걸쳐 살아있는 SKU만 써서 라인업 변화 착시를 제거.

    ⚠️ 수집 부실월(2026-01=1일, 2026-02=11일)을 기준월로 쓰면 균형패널이 붕괴한다
    (그 달에 없던 SKU가 전부 탈락 → LG 0건). 수집일 기준으로 먼저 걸러낸다."""
    label, lo, hi = band
    cov = [(r[0], r[1]) for r in c.execute(
        """SELECT substr(run_date,1,7) m, COUNT(DISTINCT run_date) d
           FROM price_snapshots GROUP BY m ORDER BY m""")]
    months = [m for m, d in cov if d >= MIN_MONTH_DAYS]
    dropped = [{"month": m, "days": d} for m, d in cov if d < MIN_MONTH_DAYS]
    if len(months) < 2:
        return None
    first, last = months[0], months[-1]

    # 기준월·최종월 모두에 존재하는 SKU만 (균형 패널)
    keep = [r[0] for r in c.execute(f"""
        SELECT p.id FROM price_snapshots s JOIN products p ON p.id = s.product_id
        WHERE p.btu BETWEEN ? AND ? AND {_px()} > 0
        GROUP BY p.id
        HAVING SUM(substr(s.run_date,1,7) = ?) > 0
           AND SUM(substr(s.run_date,1,7) = ?) > 0""", (lo, hi, first, last))]
    if not keep:
        return None
    ph = ",".join("?" * len(keep))
    mph = ",".join("?" * len(months))

    series = []
    for r in c.execute(f"""
        SELECT substr(s.run_date,1,7) m,
               AVG(CASE WHEN UPPER(p.brand)='LG'  THEN {_px()} END) lg,
               AVG(CASE WHEN UPPER(p.brand)<>'LG' THEN {_px()} END) comp,
               COUNT(DISTINCT CASE WHEN UPPER(p.brand)='LG'  THEN p.id END) lg_n,
               COUNT(DISTINCT CASE WHEN UPPER(p.brand)<>'LG' THEN p.id END) comp_n
        FROM price_snapshots s JOIN products p ON p.id = s.product_id
        WHERE p.id IN ({ph}) AND {_px()} > 0 AND substr(s.run_date,1,7) IN ({mph})
        GROUP BY m ORDER BY m""", (*keep, *months)):
        lg, comp = r["lg"], r["comp"]
        series.append({
            "month": r["m"],
            "lg": round(lg) if lg else None,
            "comp": round(comp) if comp else None,
            "gap_pct": round((lg - comp) / comp * 100, 1) if (lg and comp) else None,
            "lg_n": r["lg_n"], "comp_n": r["comp_n"],
        })
    lg_ns = {s["lg_n"] for s in series}
    comp_ns = {s["comp_n"] for s in series}
    return {"band": label, "sku_count": len(keep), "series": series,
            "base_month": first, "dropped_months": dropped,
            # 균형패널이면 전 월 표본수가 같아야 한다 — 아니면 화면에 경고
            "balanced": len(lg_ns) == 1 and len(comp_ns) == 1}


# ─────────────────────────────────────────────────────────────
# 카드 2 — 채널별 LG 가격 포지션 (최근 30일)
# ─────────────────────────────────────────────────────────────
def channel_position(c, band=("18K", 17000, 19000), days=30):
    label, lo, hi = band
    anchor = anchor_date(c)
    rows = []
    for r in c.execute(f"""
        SELECT ch.name,
               AVG(CASE WHEN UPPER(p.brand)='LG'  THEN {_px()} END) lg,
               AVG(CASE WHEN UPPER(p.brand)<>'LG' THEN {_px()} END) comp,
               COUNT(DISTINCT CASE WHEN UPPER(p.brand)='LG'  THEN p.id END) lg_n,
               COUNT(DISTINCT CASE WHEN UPPER(p.brand)<>'LG' THEN p.id END) comp_n
        FROM price_snapshots s
        JOIN products p ON p.id = s.product_id
        JOIN channels ch ON ch.id = p.channel_id
        WHERE s.run_date >= date(?, ?) AND p.btu BETWEEN ? AND ? AND {_px()} > 0
        GROUP BY ch.name""", (anchor, f"-{days} days", lo, hi)):
        if not r["lg"] or not r["comp"]:
            continue
        rows.append({
            "channel": r["name"], "lg": round(r["lg"]), "comp": round(r["comp"]),
            "gap_pct": round((r["lg"] - r["comp"]) / r["comp"] * 100, 1),
            "lg_n": r["lg_n"], "comp_n": r["comp_n"],
            # SKU 표본이 3개 미만이면 해석 금지 표시
            "thin": r["lg_n"] < 3,
        })
    rows.sort(key=lambda x: -x["lg"])
    solid = [x for x in rows if not x["thin"]]
    spread = None
    if len(solid) >= 2:
        lo_p, hi_p = min(x["lg"] for x in solid), max(x["lg"] for x in solid)
        spread = {"lo": lo_p, "hi": hi_p, "pct": round((hi_p - lo_p) / lo_p * 100, 1)}
    return {"band": label, "days": days, "rows": rows, "spread": spread}


# ─────────────────────────────────────────────────────────────
# 카드 3 — 최근 7일 경쟁사 가격 변동
# ─────────────────────────────────────────────────────────────
def recent_moves(c, days=7, limit=25):
    """최근 변동 순위.

    🔴 스크래핑 결함 가드 2종. 둘 다 '실제 가격 변동'이 아닌데 변동폭이 커서
    순위 상위를 독점한다 → 순위에서 제외하되 **몇 건을 왜 뺐는지 화면에 남긴다.**

    ① 하루짜리 스파이크/딥 — 값이 튀었다가 **다음 관측에서 원래 자리로 복귀**.
       프로모가를 하루 못 잡은 날이다. 소매가 하루 +75%였다가 되돌아오는 일은 없다.
       (Al Manea 8/25: 3,549→6,210→3,549 · Black Box 8/30: 6,149→11,009→6,149)
    ② 할인율 모순 — 할인율은 기록됐는데 판매가(sl)=표준가(sp).
       ①이 대부분 잡지만 원인을 설명해 주므로 함께 둔다.

    ⚠️ ②만으로는 부족하다: Al Manea 건은 discount_pct까지 0으로 기록돼 ②를 빠져나갔다.
    복귀 판정(①)이 채널·포맷 무관하게 동작하는 유일한 방법이다."""
    anchor = anchor_date(c)
    out, excluded = [], 0
    for r in c.execute(f"""
        WITH d AS (
          SELECT s.product_id, s.run_date, {_px()} px, s.sp, s.sl, s.discount_pct dp,
                 LAG({_px()})  OVER w prev,
                 LEAD({_px()}) OVER w next,
                 LAG(s.sp) OVER w prev_sp, LAG(s.sl) OVER w prev_sl,
                 LAG(s.discount_pct) OVER w prev_dp,
                 LAG({_px()}, 2) OVER w prev2
          FROM price_snapshots s
          WHERE s.run_date >= date(?, ?)
          WINDOW w AS (PARTITION BY s.product_id ORDER BY s.run_date)
        )
        SELECT ch.name channel, UPPER(p.brand) brand, p.name_en, p.sku, p.btu,
               d.prev, d.px, d.run_date,
               -- ① 현재 점이 1회성 스파이크: 앞뒤와 15%+ 차이 & 앞뒤끼리는 3% 이내
               (d.next IS NOT NULL AND d.prev > 0 AND d.next > 0
                AND ABS(d.px - d.prev) / d.prev > 0.15
                AND ABS(d.px - d.next) / d.next > 0.15
                AND ABS(d.prev - d.next) / d.prev < 0.03) cur_spike,
               -- ① 직전 점이 1회성 스파이크였다면 그 복귀 이동도 가짜다
               (d.prev2 IS NOT NULL AND d.prev2 > 0 AND d.px > 0 AND d.prev > 0
                AND ABS(d.prev - d.prev2) / d.prev2 > 0.15
                AND ABS(d.prev - d.px) / d.px > 0.15
                AND ABS(d.prev2 - d.px) / d.px < 0.03) prev_spike,
               -- ② 할인율 모순
               (d.dp > 1 AND d.sp > 0 AND d.sl >= d.sp * 0.995) cur_bad,
               (d.prev_dp > 1 AND d.prev_sp > 0 AND d.prev_sl >= d.prev_sp * 0.995) prev_bad
        FROM d JOIN products p ON p.id = d.product_id
               JOIN channels ch ON ch.id = p.channel_id
        WHERE d.prev IS NOT NULL AND d.px IS NOT NULL AND d.px <> d.prev AND d.prev > 0
        ORDER BY ABS((d.px - d.prev) / d.prev) DESC LIMIT ?""",
                       (anchor, f"-{days} days", limit * 8)):
        if r["cur_spike"] or r["prev_spike"] or r["cur_bad"] or r["prev_bad"]:
            excluded += 1
            continue
        chg = (r["px"] - r["prev"]) / r["prev"] * 100
        out.append({
            "channel": r["channel"], "brand": r["brand"], "sku": r["sku"],
            "name": (r["name_en"] or "")[:60], "btu": r["btu"],
            "prev": round(r["prev"]), "curr": round(r["px"]),
            "chg_pct": round(chg, 1), "date": r["run_date"],
            "is_lg": r["brand"] == "LG",
        })
    return {"days": days, "anchor": anchor, "excluded": excluded,
            "up": [x for x in out if x["chg_pct"] > 0][:limit],
            "down": [x for x in out if x["chg_pct"] < 0][:limit]}


# ─────────────────────────────────────────────────────────────
# 카드 4 — 브랜드별 평균가 추이 (경쟁 5사 + LG)
# ─────────────────────────────────────────────────────────────
def brand_trend(c, band=("18K", 17000, 19000)):
    """Q1과 **같은 월 집합**을 쓴다. 수집 1일뿐인 달을 한 점으로 찍으면
    브랜드가 그 달에 급등/급락한 것처럼 보인다(2026-01)."""
    label, lo, hi = band
    brands = ["LG"] + FOCUS_BRANDS
    ph = ",".join("?" * len(brands))
    months_ok = [r[0] for r in c.execute(
        """SELECT substr(run_date,1,7) m FROM price_snapshots
           GROUP BY m HAVING COUNT(DISTINCT run_date) >= ?""", (MIN_MONTH_DAYS,))]
    mph = ",".join("?" * len(months_ok))
    data = {}
    for r in c.execute(f"""
        SELECT substr(s.run_date,1,7) m, UPPER(p.brand) b,
               AVG({_px()}) px, COUNT(DISTINCT p.id) n
        FROM price_snapshots s JOIN products p ON p.id = s.product_id
        WHERE p.btu BETWEEN ? AND ? AND {_px()} > 0 AND UPPER(p.brand) IN ({ph})
          AND substr(s.run_date,1,7) IN ({mph})
        GROUP BY m, b ORDER BY m""", (lo, hi, *brands, *months_ok)):
        # 표본 2개 미만인 달은 신뢰 못 함 → None
        data.setdefault(r["b"], {})[r["m"]] = round(r["px"]) if r["n"] >= 2 else None
    months = sorted({m for v in data.values() for m in v})
    return {"band": label, "months": months,
            "brands": {b: [data.get(b, {}).get(m) for m in months]
                       for b in brands if b in data}}


# ─────────────────────────────────────────────────────────────
# 카드 5 — 경쟁사 라인업 변화 (신규 / 단종)
# ─────────────────────────────────────────────────────────────
def lineup_changes(c, days=30):
    anchor = anchor_date(c)
    new, gone = [], []
    for r in c.execute("""
        SELECT ch.name channel, UPPER(p.brand) brand, p.name_en, p.btu,
               e.status, e.event_date
        FROM sku_status_events e
        JOIN products p ON p.id = e.product_id
        JOIN channels ch ON ch.id = p.channel_id
        WHERE e.event_date >= date(?, ?) AND e.status IN ('new','discontinued')
        ORDER BY e.event_date DESC""", (anchor, f"-{days} days")):
        item = {"channel": r["channel"], "brand": r["brand"],
                "name": (r["name_en"] or "")[:60], "btu": r["btu"],
                "date": r["event_date"], "is_lg": r["brand"] == "LG"}
        (new if r["status"] == "new" else gone).append(item)
    return {"days": days, "new": new[:30], "gone": gone[:30],
            "new_total": len(new), "gone_total": len(gone)}


# ─────────────────────────────────────────────────────────────
# 카드 6 — BTU 급별 LG 프리미엄 한눈에
# ─────────────────────────────────────────────────────────────
def premium_by_band(c, days=30):
    anchor = anchor_date(c)
    out = []
    for label, lo, hi in BTU_BANDS:
        r = c.execute(f"""
            SELECT AVG(CASE WHEN UPPER(p.brand)='LG'  THEN {_px()} END) lg,
                   AVG(CASE WHEN UPPER(p.brand)<>'LG' THEN {_px()} END) comp,
                   COUNT(DISTINCT CASE WHEN UPPER(p.brand)='LG'  THEN p.id END) lg_n,
                   COUNT(DISTINCT CASE WHEN UPPER(p.brand)<>'LG' THEN p.id END) comp_n
            FROM price_snapshots s JOIN products p ON p.id = s.product_id
            WHERE s.run_date >= date(?, ?) AND p.btu BETWEEN ? AND ? AND {_px()} > 0""",
                      (anchor, f"-{days} days", lo, hi)).fetchone()
        if not r["lg"] or not r["comp"] or r["lg_n"] < 3:
            out.append({"band": label, "lg": None, "comp": None, "gap_pct": None,
                        "lg_n": r["lg_n"] or 0, "comp_n": r["comp_n"] or 0})
            continue
        out.append({"band": label, "lg": round(r["lg"]), "comp": round(r["comp"]),
                    "gap_pct": round((r["lg"] - r["comp"]) / r["comp"] * 100, 1),
                    "lg_n": r["lg_n"], "comp_n": r["comp_n"]})
    return out


def build_all():
    with _conn() as c:
        return {
            "freshness": freshness(c),
            "gap_trend": gap_trend(c),
            "channel_position": channel_position(c),
            "recent_moves": recent_moves(c),
            "brand_trend": brand_trend(c),
            "lineup": lineup_changes(c),
            "premium_band": premium_by_band(c),
        }


if __name__ == "__main__":
    import json
    print(json.dumps(build_all(), ensure_ascii=False, indent=1)[:4000])
