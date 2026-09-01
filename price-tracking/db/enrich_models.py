#!/usr/bin/env python3
"""
가격 DB 상품 → v6 모델코드 부착 (C단계).

왜 필요한가: 채널마다 제품을 제멋대로 부른다.
  eXtra   "LG Spilt AC, 18,000 BTU, Cool, Win, Dual Inverter"   (오타 포함)
  Najm    "ال جي مكيف سبليت جيت كول 24,000 وحدة - بارد - LO242C0"
이름으로는 채널 간 같은 모델을 짝지을 수 없다. v6 정본 코드를 붙여야 열린다.

원칙:
- 정규화는 **`ssot_model_name.canon()` 단일 진입점만** 쓴다.
  자체 규칙을 새로 만들지 않는다 [[project_model_mapping_single_entry]].
- canon 은 v6가 아는 형태만 돌려준다. 모르면 **원문 유지 → 미부착**으로 남긴다.
  추측해서 붙이지 않는다.
- 어디서 건졌는지(`v6_source`)를 함께 저장한다. 근거 없는 값을 남기지 않는다.

멱등. ingest_daily 이후에 돌린다.
사용: python3 enrich_models.py [--brand LG] [--verbose]
"""
import argparse
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
from ssot_model_name import canon, _v6_known  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import db as dbmod  # noqa: E402

# LG 모델코드 토큰: 영문2~5 + 영숫자 + 숫자 포함, 선택적 .접미(ANWGIB 등)
# ⚠️ 접두 영문이 **1자**인 계열이 있다(W181EC/W242EC = Window). {2,5} 로 두면 통째로 누락된다.
#    [[project_w_series_window_sn3]] — 1자를 허용해도 아래 v6 등재 검증이 오탐을 막는다.
TOKEN = re.compile(r"[A-Z]{1,5}[A-Z0-9]{2,}\d[A-Z0-9]*(?:[.\-][A-Z0-9]{2,8})?")


def candidates(model, name, url, sku=None):
    """모델코드 후보를 우선순위대로. 채널마다 코드가 숨은 자리가 다르다.
       model 컬럼(5채널) → SKU(binmomen) → 제품명 꼬리(sws/najm) → URL 슬러그(alkhunaizan/technobest)"""
    out = []
    if model:
        # Al Manea는 'NF122C0.NJ0 NF122C0.UJ0' 처럼 실내/실외 쌍을 한 칸에 넣는다
        out += [t for t in re.split(r"[\s,;]+", model.upper()) if len(t) >= 6]
    # Bin Momen은 SKU 자체가 모델코드다 ('ND182C0NK0' = ND182C0.NK0).
    # 숫자만인 SKU(eXtra/Najm/SWS)는 TOKEN 패턴에 안 걸리므로 섞여 들어오지 않는다.
    if sku and TOKEN.fullmatch(str(sku).upper()):
        out.append(str(sku).upper())
    for src in (name, urllib.parse.unquote(url or "")):
        if not src:
            continue
        u = src.upper()
        out += TOKEN.findall(u)
        out += TOKEN.findall(u.replace("-", ""))   # 슬러그 하이픈 제거본
    if url:
        # …/product/…-p-abnq21gm1t6-anwgib  → ABNQ21GM1T6 / ABNQ21GM1T6.ANWGIB
        tail = urllib.parse.unquote(url).upper().rstrip("/").split("/")[-1]
        parts = [p for p in re.split(r"[-_.]", tail) if re.fullmatch(r"[A-Z0-9]{5,12}", p)]
        for i, p in enumerate(parts):
            if re.match(r"^[A-Z]{2,5}\d", p):
                out.append(p)
                if i + 1 < len(parts) and re.fullmatch(r"[A-Z0-9]{3,7}", parts[i + 1]):
                    out.append(f"{p}.{parts[i+1]}")
    seen = set()
    return [x for x in out if not (x in seen or seen.add(x))]


MAX_CODE_LEN = 16   # v6 최장 코드가 14자. 여유 2자.


def resolve(model, name, url, sku=None):
    """(v6코드, 출처) 또는 (None, None). **v6 마스터가 실제로 아는 코드만** 채택한다.

    🔴 2026-09-01 수정 — 이전 조건 `v != cand or len(cand) >= 8` 이 오염을 만들었다.
       canon()은 모르는 코드를 **원문 그대로** 돌려준다. 그런데 '8자 이상이면 채택'했기 때문에
       상품명에서 하이픈을 뗀 긴 문자열이 그대로 모델코드가 됐다:
         'LGWINDOWAC18000BTUWINDOWROTARYCOOLONLYW181ECSN'
         'BASICAIRCONDITIONERSPLITCOLDONLY31400BTUINVERTER...'
       LG만 돌릴 땐 97%였는데 전 브랜드로 돌리며 **3,076건 중 845건(27.5%)이 오염**됐다.
       → v6 등재 여부(_v6_known)로 판정하고 길이 상한을 둔다. 모르면 붙이지 않는다."""
    for cand in candidates(model, name, url, sku):
        if len(cand) > MAX_CODE_LEN:
            continue
        v = canon(cand)
        if not v or len(v) > MAX_CODE_LEN:
            continue
        if not (_v6_known(v) or _v6_known(v.split(".")[0])):
            continue    # v6가 모르는 코드는 추측이다. 붙이지 않는다.
        if True:
            src = ("model" if model and cand in model.upper()
                   else "sku" if sku and cand == str(sku).upper()
                   else "name" if name and cand.replace(".", "") in name.upper().replace("-", "")
                   else "url")
            return v, src
    return None, None


def ensure_columns(c):
    cols = {r[1] for r in c.execute("PRAGMA table_info(products)")}
    for col in ("v6_model", "v6_source"):
        if col not in cols:
            c.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT")
            print(f"  · products.{col} 컬럼 신설")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default=None, help="특정 브랜드만 (기본: 전 브랜드)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    c = sqlite3.connect(str(dbmod.resolve_db_path()))
    c.row_factory = sqlite3.Row
    ensure_columns(c)

    q = """SELECT p.id, p.model, p.name_en, p.url, p.sku, UPPER(p.brand) brand, ch.code chn
           FROM products p JOIN channels ch ON ch.id = p.channel_id"""
    args = ()
    if a.brand:
        q += " WHERE UPPER(p.brand) = ?"
        args = (a.brand.upper(),)

    stat, unmapped, n = {}, [], 0
    for r in c.execute(q, args).fetchall():
        v6, src = resolve(r["model"], r["name_en"], r["url"], r["sku"])
        c.execute("UPDATE products SET v6_model=?, v6_source=? WHERE id=?", (v6, src, r["id"]))
        n += 1
        d = stat.setdefault(r["chn"], {"hit": 0, "tot": 0})
        d["tot"] += 1
        if v6:
            d["hit"] += 1
        elif r["brand"] == "LG":
            unmapped.append((r["chn"], r["sku"], (r["name_en"] or "")[:46]))
    c.commit()

    print(f"\n대상 {n:,}개 상품 · 채널별 v6 코드 부착률")
    th = tt = 0
    for k, d in sorted(stat.items(), key=lambda x: -x[1]["tot"]):
        th += d["hit"]; tt += d["tot"]
        print(f"  {k:12s} {d['hit']:4d}/{d['tot']:4d}  {d['hit']/d['tot']*100:5.1f}%")
    print(f"  {'합계':12s} {th:4d}/{tt:4d}  {th/tt*100:5.1f}%")

    if unmapped:
        print(f"\n⚠️ LG 미부착 {len(unmapped)}건 — 원본에 모델코드가 없는 상품이다(추측 금지).")
        if a.verbose:
            for u in unmapped:
                print("   ", u)
        else:
            for u in unmapped[:8]:
                print("   ", u)
            if len(unmapped) > 8:
                print(f"    … 외 {len(unmapped)-8}건 (--verbose)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
