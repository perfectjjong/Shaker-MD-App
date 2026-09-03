#!/usr/bin/env python3
"""
가격 DB 품질 게이트 — 결측·규칙위반을 매일 재고, 악화되면 알린다.

🔴 2026-09-02 형님 지적:
   "비어있는 정보가 있는 모델이 많나? **규칙에 어긋나있는 예외 DB가 많은 건
    DB로의 가치를 많이 훼손하는건데**"

맞는 지적이다. DB의 가치는 '모아둔 양'이 아니라 **믿고 꺼내 쓸 수 있느냐**로 정해진다.
결측이 한 축에 몰리면 그 축으로 묻는 질문이 통째로 답을 못 낸다
(실측: 압축기 결측 400개가 BH·Technobest 두 채널에 몰려 있었고,
 그 탓에 "인버터만 보여줘" 류 질문에서 판매중의 18%가 소리 없이 빠졌다).

그래서 **한 번 고치고 끝내지 않고 매일 잰다.** 악화되면 텔레그램.

사용: python3 quality_gate.py [--notify]
cron: 매일 06:00 (적재→부착→압축기보강→뷰갱신 다음)
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db as dbmod  # noqa: E402

STATE = Path.home() / ".cron_status/price_quality.json"

# 결측 허용선 — 넘으면 경고. '없는 게 정상'인 건 뺐다(비LG의 v6_model 등).
MISSING_LIMITS = {
    "px":         (0.00, "현재가"),
    "brand":      (0.02, "브랜드"),
    "btu":        (0.12, "BTU"),
    "cool_type":  (0.15, "냉방타입"),
    "comp_type":  (0.10, "압축기"),
    # 🔴 판정 기준은 name_en 이 아니라 display_name 이다.
    #    아랍어 이름만 있는 채널(Technobest)도 실제로는 **보여줄 이름이 있다**.
    #    name_en 결측은 별도 '참고'로만 낸다 — 느슨하게 푸는 게 아니라 올바른 지표로 재는 것.
    "display_name": (0.02, "표시명"),
    "sp":         (0.10, "표준가"),
}

RULES = [
    ("가격 0 이하", 0,
     "SELECT COUNT(*) FROM product_current WHERE px<=0"),
    ("프로모가 > 표준가", 5,
     "SELECT COUNT(*) FROM product_current WHERE sp IS NOT NULL AND px>sp*1.001"),
    ("할인율 범위 이탈", 0,
     "SELECT COUNT(*) FROM product_current WHERE discount_pct<0 OR discount_pct>100"),
    ("할인율-실제가 불일치(5%p+)", 20,
     """SELECT COUNT(*) FROM product_current WHERE sp>0 AND discount_pct>1
        AND ABS((1-px/sp)*100 - discount_pct) > 5"""),
    ("BTU 상식 밖", 0,
     "SELECT COUNT(*) FROM product_current WHERE btu IS NOT NULL AND (btu<3000 OR btu>120000)"),
    ("톤 상식 밖", 0,
     "SELECT COUNT(*) FROM product_current WHERE ton IS NOT NULL AND (ton<0.3 OR ton>12)"),
    ("BTU-톤 불일치(30%+)", 10,
     """SELECT COUNT(*) FROM product_current WHERE btu IS NOT NULL AND ton IS NOT NULL
        AND ton>0 AND ABS(btu - ton*12000)/(ton*12000) > 0.3"""),
    ("채널 내 SKU 중복", 0,
     "SELECT COUNT(*) FROM (SELECT channel_id,sku FROM products GROUP BY 1,2 HAVING COUNT(*)>1)"),
    ("모델코드 형식 이상", 0,
     "SELECT COUNT(*) FROM products WHERE v6_model IS NOT NULL AND LENGTH(v6_model)>16"),
    ("브랜드 대소문자 혼재", 0,
     """SELECT COUNT(*) FROM (SELECT UPPER(brand) FROM products WHERE brand IS NOT NULL
        GROUP BY 1 HAVING COUNT(DISTINCT brand)>1)"""),
    ("미래 날짜", 0,
     "SELECT COUNT(*) FROM price_snapshots WHERE run_date > date('now','+1 day')"),
    # 🔴 2026-09-03 신설: 결함으로 최신 스냅샷을 버리고 **과거값을 현재가로 보여주는** 상품 수.
    #    버리는 것 자체는 옳다(할인율만 있고 프로모가를 못 잡은 날). 조용히 하는 게 문제였다.
    #    수가 늘면 스크래퍼가 프로모가를 놓치기 시작했다는 신호다.
    ("최신 스냅샷 결함으로 과거값 표시", 80,
     "SELECT COUNT(*) FROM product_current WHERE is_live=1 AND px_suspect=1"),
    # 냉방타입이 제품명과 모순 — raw ac_type 을 맹신하면 다시 벌어진다
    ("냉방타입-제품명 모순", 10,
     """SELECT COUNT(*) FROM product_current WHERE is_live=1 AND cool_type='H&C'
        AND (UPPER(display_name) LIKE '%COOL ONLY%'
             OR UPPER(display_name) LIKE '%COOLING ONLY%')"""),
]

# 한 축의 결측이 특정 채널에 몰리면 그 축의 질문이 통째로 무너진다
CONCENTRATION_LIMIT = 0.80   # 한 채널의 그 필드 결측률이 이 이상이면 경고


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(f"file:{dbmod.resolve_db_path()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    issues, report = [], []
    try:
        tot = con.execute("SELECT COUNT(*) FROM product_current WHERE is_live=1").fetchone()[0]
        anchor = con.execute("SELECT MAX(run_date) FROM price_snapshots").fetchone()[0]
        report.append(f"판매중 {tot:,}개 · 기준일 {anchor}")

        report.append("\n[결측률]")
        missing = {}
        for f, (limit, ko) in MISSING_LIMITS.items():
            n = con.execute(f"SELECT COUNT(*) FROM product_current "
                            f"WHERE is_live=1 AND {f} IS NULL").fetchone()[0]
            rate = n / tot if tot else 0
            missing[f] = rate
            over = rate > limit
            if over:
                issues.append(f"{ko} 결측 {rate*100:.1f}% (허용 {limit*100:.0f}%)")
            report.append(f"  {'🔴' if over else '✅'} {ko:<10} {n:>5} {rate*100:>6.1f}%"
                          f"  (허용 {limit*100:.0f}%)")

            # 한 채널에 몰렸는가
            for r in con.execute(f"""SELECT channel_name, SUM({f} IS NULL) m, COUNT(*) c
                                     FROM product_current WHERE is_live=1
                                     GROUP BY channel_id HAVING c >= 20"""):
                if r["m"] / r["c"] >= CONCENTRATION_LIMIT:
                    msg = f"{ko} 결측이 {r['channel_name']}에 집중 ({r['m']}/{r['c']})"
                    issues.append(msg)
                    report.append(f"      ↳ 🔴 {msg} — 이 축의 질문에서 통째로 빠진다")

        # 참고 지표 — 게이트 판정에는 넣지 않되 눈에는 보이게
        n_en = con.execute("SELECT COUNT(*) FROM product_current "
                           "WHERE is_live=1 AND name_en IS NULL").fetchone()[0]
        if n_en:
            report.append(f"  ℹ️ 영문명 없음 {n_en} ({n_en/tot*100:.1f}%) — 아랍어명으로 표시 중(참고)")

        report.append("\n[규칙 위반]")
        for ko, limit, q in RULES:
            n = con.execute(q).fetchone()[0]
            over = n > limit
            if over:
                issues.append(f"{ko} {n}건 (허용 {limit})")
            report.append(f"  {'🔴' if over else '✅'} {ko:<26} {n:>5}  (허용 {limit})")

        # 이전 회차 대비 악화 감지
        prev = {}
        if STATE.exists():
            try:
                prev = json.loads(STATE.read_text()).get("missing", {})
            except Exception:
                pass
        worse = [f"{MISSING_LIMITS[f][1]} {prev[f]*100:.1f}%→{missing[f]*100:.1f}%"
                 for f in missing if f in prev and missing[f] > prev[f] + 0.03]
        if worse:
            issues.append("전일 대비 악화: " + ", ".join(worse))
            report.append("\n[전일 대비] 🔴 " + ", ".join(worse))

        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"anchor": anchor, "missing": missing}, ensure_ascii=False))
    finally:
        con.close()

    print("\n".join(report))
    print(f"\n→ 판정: {'🔴 ' + str(len(issues)) + '건' if issues else '✅ 이상 없음'}")

    if issues and a.notify:
        sys.path.insert(0, "/home/ubuntu/sonolbot")
        from notify import telegram_send
        telegram_send("🔴 *가격 DB 품질 게이트*\n\n" + "\n".join(f"• {i}" for i in issues[:10]))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
