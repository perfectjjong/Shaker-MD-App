#!/usr/bin/env python3
"""
압축기 정보 보강 — 이미 만들어 둔 채널별 맵을 DB에 넣는다.

🔴 2026-09-02 형님 지적: "비어있는 정보가 있는 모델이 많나?
   규칙에 어긋나있는 예외 DB가 많은 건 DB로의 가치를 많이 훼손하는건데"

실측했더니 압축기 결측 400개(판매중의 20.5%)가 **2개 채널에 몰려** 있었다:
  BH 183개(100% 결측) · Technobest 160개(100% 결측)
그런데 이 둘의 압축기는 **이미 웹검색·교차조회로 만들어 둔 맵 파일에 있었다**
  (`bh_compressor_map.json` 580건 · `technobest_price_compressor_map.json` 362건 등,
   [[project_bh_compressor_axis_mapping]] · shared_compressor_websearch.py 산출물).
  → 데이터가 없는 게 아니라 **DB 적재에 반영이 안 된 것**이었다. 커버율 BH 100% · Technobest 99%.

이 스크립트는 그 맵을 products.compressor 에 채운다. 원본 스크래핑 값이 있으면 건드리지 않는다.
멱등. enrich_models 다음, create_views 앞에 돌린다.
"""
import glob
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db as dbmod  # noqa: E402

MAP_GLOB = "/home/ubuntu/2026/06. Price Tracking/*/*compressor_map.json"
# 맵 파일명 slug → DB channel code
SLUG2CODE = {
    "bh": "bh", "technobest": "technobest", "extra": "extra",
    "sws": "sws", "tamkeen": "tamkeen", "binmomen": "binmomen",
}
VALID = ("Inverter", "Dual Inverter", "Rotary", "On-Off", "On/Off")


def load_maps():
    out = {}
    for f in glob.glob(MAP_GLOB):
        slug = os.path.basename(f).replace("_compressor_map.json", "").replace("_price", "")
        code = SLUG2CODE.get(slug)
        if not code:
            continue
        try:
            out[code] = json.load(open(f))
        except Exception as e:
            print(f"  ⚠️ {slug} 맵 읽기 실패: {e}")
    return out


def lookup(m, sku, name):
    """맵 키가 채널마다 다르다 — SKU / 'SKU SKU' / 제품명 순으로 찾는다."""
    for k in (str(sku), f"{sku} SKU", name):
        if k and k in m:
            v = m[k]
            comp = v.get("compressor") if isinstance(v, dict) else v
            if comp in VALID:
                return comp, (v.get("source") if isinstance(v, dict) else "map")
    return None, None


def main():
    maps = load_maps()
    if not maps:
        print("맵 파일 없음 — 종료")
        return 1
    con = sqlite3.connect(str(dbmod.resolve_db_path()), timeout=20)
    con.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(products)")}
        if "compressor_source" not in cols:
            con.execute("ALTER TABLE products ADD COLUMN compressor_source TEXT")
            print("  · products.compressor_source 컬럼 신설")

        total_filled = 0
        for code, m in sorted(maps.items()):
            rows = con.execute("""
                SELECT p.id, p.sku, p.name_en FROM products p
                JOIN channels ch ON ch.id = p.channel_id
                WHERE ch.code = ?
                  AND (p.compressor IS NULL OR TRIM(p.compressor) = ''
                       OR UPPER(p.compressor) = 'NONE')""", (code,)).fetchall()
            filled = 0
            for r in rows:
                comp, src = lookup(m, r["sku"], r["name_en"])
                if comp:
                    con.execute("UPDATE products SET compressor=?, compressor_source=? WHERE id=?",
                                (comp, f"map:{src}", r["id"]))
                    filled += 1
            total_filled += filled
            if rows:
                print(f"  {code:<12} 결측 {len(rows):>4} → 채움 {filled:>4} "
                      f"({filled/len(rows)*100:5.1f}%)  남음 {len(rows)-filled}")
        con.commit()
        print(f"\n  총 {total_filled:,}건 보강")

        r = con.execute("""
            SELECT COUNT(*), SUM(compressor IS NULL OR UPPER(compressor)='NONE')
            FROM products""").fetchone()
        print(f"  전체 상품 {r[0]:,} 중 압축기 결측 {r[1]:,} ({r[1]/r[0]*100:.1f}%)")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
