#!/usr/bin/env python3
"""
가격 DB 정본 뷰 — **품질 판정을 DB 한 곳에서 내린다.**

왜 필요한가 (2026-09-01, 형님 질문 "DB화를 한 본질적인 이유가 무엇일까요?"):
  DB화의 본질은 '흩어진 파일을 모으는 것'이 아니라 **모아서 그 숫자를 믿을 수 있게 만드는 것**이다.
  그런데 나는 DB를 창고로만 쓰고, 품질 판정을 **조회하는 쪽에 흩어놓았다**:
    julianday 11곳 · ROW_NUMBER 7곳 · COALESCE(sl,sp) 31곳 ·
    템플릿 14종 중 '판매중 필터'를 쓰는 건 7종뿐 — 나머지 7종은 빠져 있었다.
  그래서 소비처가 늘 때마다 규칙을 다시 써야 했고, 하나 빠뜨릴 때마다 오답이 나갔다.
  (실제: 모델 템플릿엔 지연 구분을 넣고 평균가 템플릿엔 빠뜨려 형님이 지적하기 전엔 몰랐다)

→ 규칙을 **뷰 하나**에 모은다. 모든 소비처는 이 뷰만 본다.
   새 소비처가 생겨도 규칙이 자동으로 따라간다.

멱등. 스키마 변경 후 다시 돌리면 된다.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db as dbmod  # noqa: E402

STALE_DAYS = 3          # 이보다 오래 안 보이면 '현재'가 아니다
SPIKE_RATIO = 0.15      # 앞뒤와 15% 넘게 차이나면 스파이크 후보
RETURN_RATIO = 0.03     # 앞뒤끼리 3% 이내면 '되돌아옴' = 결함

VIEWS = {

# ── ① 결함 스냅샷을 걸러낸 가격 시계열 ─────────────────────────
# 가격 추이·변동을 보는 모든 질의는 이 뷰를 쓴다.
"v_price_clean": f"""
CREATE VIEW v_price_clean AS
WITH seq AS (
  SELECT s.id, s.product_id, s.run_date,
         COALESCE(s.sl, s.sp) AS px, s.sp, s.sl, s.fp,
         s.discount_pct, s.in_stock, s.stock_qty,
         LAG(COALESCE(s.sl, s.sp))  OVER w AS prev_px,
         LEAD(COALESCE(s.sl, s.sp)) OVER w AS next_px,
         LAG(s.sp) OVER w AS prev_sp, LAG(s.sl) OVER w AS prev_sl,
         LAG(s.discount_pct) OVER w AS prev_dp
  FROM price_snapshots s
  WHERE COALESCE(s.sl, s.sp) > 0
  WINDOW w AS (PARTITION BY s.product_id ORDER BY s.run_date)
)
SELECT id, product_id, run_date, px, sp, sl, fp, discount_pct, in_stock, stock_qty,
       prev_px, next_px,
       -- 결함 ①: 하루 튀었다 원위치 (프로모가를 못 잡은 날)
       CASE WHEN next_px IS NOT NULL AND prev_px > 0 AND next_px > 0
                 AND ABS(px - prev_px)/prev_px > {SPIKE_RATIO}
                 AND ABS(px - next_px)/next_px > {SPIKE_RATIO}
                 AND ABS(prev_px - next_px)/prev_px < {RETURN_RATIO}
            THEN 1 ELSE 0 END AS is_spike,
       -- 결함 ②: 할인율은 있는데 판매가 = 표준가
       CASE WHEN discount_pct > 1 AND sp > 0 AND sl >= sp * 0.995
            THEN 1 ELSE 0 END AS is_incons
FROM seq
""",

# ── ② 상품별 '지금' 상태 — 신선도·판매여부 판정을 여기서 끝낸다 ──
# 현재가를 묻는 모든 질의는 이 뷰를 쓴다. 지연된 값이 현재가로 새어나가지 않는다.
"v_product_current": f"""
CREATE VIEW v_product_current AS
WITH anchor AS (SELECT MAX(run_date) d FROM price_snapshots),
ch_fresh AS (
  SELECT p.channel_id cid, MAX(s.run_date) ch_last
  FROM price_snapshots s JOIN products p ON p.id = s.product_id
  GROUP BY p.channel_id
),
last AS (
  SELECT c.*, ROW_NUMBER() OVER (PARTITION BY c.product_id ORDER BY c.run_date DESC) rn
  FROM v_price_clean c
  WHERE c.is_spike = 0 AND c.is_incons = 0     -- 결함 스냅샷을 '최신'으로 삼지 않는다
)
SELECT p.id AS product_id, p.channel_id, ch.code AS channel_code, ch.name AS channel_name,
       UPPER(p.brand) AS brand, p.v6_model, p.sku, p.name_en, p.btu, p.ton,
       p.compressor, p.ac_type, p.category,
       -- 🔴 냉방타입 정규화: 채널마다 표기가 제각각이다
       --    CO 계열  : 'Cold Only' / 'CO' / 'Cooling Only' / 'Cold' / 'Cold Only, Inverter'
       --    H&C 계열 : 'Hot & Cold' / 'Heat & Cool' / 'Cold and Hot' / 'Cold/Hot' / 'H&C' / 'C&H'
       --    'Cold/Hot' 처럼 슬래시가 든 건 냉난방이므로 **CO 판정보다 먼저** 걸러야 한다.
       CASE
         WHEN p.ac_type IS NULL THEN NULL
         WHEN UPPER(p.ac_type) LIKE '%HOT%' OR UPPER(p.ac_type) LIKE '%HEAT%'
           OR UPPER(p.ac_type) LIKE '%H&C%' OR UPPER(p.ac_type) LIKE '%C&H%'
           OR UPPER(p.ac_type) LIKE '%COLD/HOT%' OR UPPER(p.ac_type) LIKE '%COLD AND HOT%'
           THEN 'H&C'
         WHEN UPPER(p.ac_type) LIKE '%COLD%' OR UPPER(p.ac_type) LIKE '%COOL%'
           OR UPPER(p.ac_type) = 'CO'
           THEN 'CO'
         ELSE NULL
       END AS cool_type,
       -- 🔴 압축기 정규화: 'Dual Inverter'·'Inverter' → Inverter, 'Rotary'·'On/Off'·'On-Off' → On/Off
       --    ⚠️ ac_type 에 압축기가 섞여 들어온 채널이 있다(Al Khunaizan 'Cold Only, Inverter').
       --       compressor 컬럼이 비면 ac_type 문자열도 본다.
       CASE
         WHEN UPPER(COALESCE(p.compressor,'')) LIKE '%INVERTER%'
           OR UPPER(COALESCE(p.ac_type,''))    LIKE '%INVERTER%' THEN 'Inverter'
         WHEN UPPER(COALESCE(p.compressor,'')) LIKE '%ROTARY%'
           OR UPPER(COALESCE(p.compressor,'')) LIKE '%ON/OFF%'
           OR UPPER(COALESCE(p.compressor,'')) LIKE '%ON-OFF%' THEN 'On/Off'
         ELSE NULL
       END AS comp_type,
       l.px, l.sp, l.discount_pct, l.in_stock, l.stock_qty, l.run_date,
       CAST(julianday((SELECT d FROM anchor)) - julianday(l.run_date) AS INT) AS lag_days,
       CASE WHEN julianday((SELECT d FROM anchor)) - julianday(l.run_date) <= {STALE_DAYS}
            THEN 1 ELSE 0 END AS is_live,
       CASE
         WHEN julianday((SELECT d FROM anchor)) - julianday(l.run_date) <= {STALE_DAYS}
           THEN CASE WHEN l.in_stock = 0 THEN '판매중 · 품절'
                     WHEN l.in_stock = 1 THEN '판매중 · 재고있음'
                     ELSE '판매중 · 재고미상' END
         -- 채널은 계속 수집되는데 이 상품만 사라짐 → 리스팅이 내려간 것
         WHEN julianday(cf.ch_last) - julianday(l.run_date) > {STALE_DAYS}
           THEN '미판매 · ' || CAST(julianday((SELECT d FROM anchor))
                - julianday(l.run_date) AS INT) || '일째 리스팅 없음'
         -- 채널 자체가 멈춤 → 우리 수집 문제
         ELSE '수집중단 · 채널 최종수집 ' || cf.ch_last
       END AS status
FROM products p
JOIN channels ch ON ch.id = p.channel_id
JOIN last l ON l.product_id = p.id AND l.rn = 1
JOIN ch_fresh cf ON cf.cid = p.channel_id
""",
}


# 🔴 v_product_current 는 **물리 테이블로 굳힌다**.
#    WINDOW 함수가 든 뷰는 인덱스가 안 먹어 모델 1건을 물어도 전체를 계산한다(실측 2.28초).
#    이 DB는 하루 1회 적재이므로 적재 직후 한 번 굳혀두면 조회가 즉시 끝난다(0.0초대).
#    v_price_clean 은 시계열 전체를 보는 용도라 뷰로 둔다.
MATERIALIZE = "product_current"


def main():
    path = dbmod.resolve_db_path()
    con = sqlite3.connect(str(path))
    try:
        for name, ddl in VIEWS.items():
            con.execute(f"DROP VIEW IF EXISTS {name}")
            con.execute(ddl)
            print(f"  ✅ {name}")

        # 조회 성능용 인덱스 (없으면 생성)
        con.execute("CREATE INDEX IF NOT EXISTS idx_snap_prod_date "
                    "ON price_snapshots(product_id, run_date)")

        # 현재 상태를 물리 테이블로 굳히고 인덱스를 건다
        con.execute(f"DROP TABLE IF EXISTS {MATERIALIZE}")
        con.execute(f"CREATE TABLE {MATERIALIZE} AS SELECT * FROM v_product_current")
        con.execute(f"CREATE INDEX idx_pc_model ON {MATERIALIZE}(v6_model)")
        con.execute(f"CREATE INDEX idx_pc_ch ON {MATERIALIZE}(channel_id, is_live)")
        con.execute(f"CREATE INDEX idx_pc_brand ON {MATERIALIZE}(brand, is_live)")
        con.execute(f"CREATE INDEX idx_pc_btu ON {MATERIALIZE}(btu, is_live)")
        print(f"  ✅ {MATERIALIZE} (물리 테이블 + 인덱스 4종)")
        con.commit()

        print(f"\nDB: {path}")
        cur = con.execute("SELECT COUNT(*) FROM v_product_current")
        tot = cur.fetchone()[0]
        live = con.execute("SELECT COUNT(*) FROM v_product_current WHERE is_live=1").fetchone()[0]
        print(f"  v_product_current : {tot:,}행 (판매중 {live:,} / 미판매·중단 {tot-live:,})")
        c = con.execute("""SELECT COUNT(*), SUM(is_spike), SUM(is_incons)
                           FROM v_price_clean""").fetchone()
        print(f"  v_price_clean     : {c[0]:,}행 "
              f"(스파이크 {c[1]:,} · 할인율모순 {c[2]:,} → 변동 조회에서 제외됨)")
        print("\n  상태 분포:")
        for r in con.execute("""SELECT CASE WHEN is_live=1 THEN '판매중'
                                            WHEN status LIKE '미판매%' THEN '미판매(리스팅 내려감)'
                                            ELSE '수집중단' END k, COUNT(*)
                                FROM v_product_current GROUP BY k ORDER BY 2 DESC"""):
            print(f"    {r[0]:<22} {r[1]:,}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
