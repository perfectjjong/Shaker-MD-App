#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPC 대시보드 데이터 빌더: 통합엑셀(2024/2025/2026 시트) -> gpc_data.js
- 카테고리 상세행만 사용, 월 Total행은 검증용(이중계상 방지)
- %지표는 프론트에서 금액 재집계 후 계산 (빌더는 금액만 emit)
"""
import json, re, openpyxl

SRC = "/home/ubuntu/2026/02. Operation Team/01. GPC Management/B2C GPC 2024-2026 통합.xlsx"
OUT = "/home/ubuntu/Shaker-MD-App/docs/dashboards/gpc/gpc_data.js"

# 통합엑셀 헤더(1행) 인덱스 -> 금액 키 (0-indexed)
M = {  # metric col -> key
    5:"gross_sale", 6:"yed", 8:"add_disc", 10:"vp_disc", 12:"dsi",
    14:"net_sales", 15:"cogs", 16:"inventory", 17:"support",
    18:"total_cogs", 19:"gross_margin",
}
METRIC_KEYS = list(M.values())

# 제품 카테고리(정규화 표시명) vs 조정항목
PRODUCT_CATS = ["Window","Split (On/Off)","Split - Inverter","Free Standing",
                "Cassette","Concealed (CAC)","Package (CAC)","Convertible (CAC)",
                "Air Purifier","Multi V"]
ADJ_CATS = ["Accessory/Other","COS adjustment","Inventory Provision","Adjust."]

def norm_cat(s):
    s = re.sub(r"\s+", " ", str(s)).strip()
    low = s.lower()
    if low.startswith("window"): return "Window"
    if low.startswith("split") and ("on" in low or "off" in low): return "Split (On/Off)"
    if low.startswith("split") and "inver" in low: return "Split - Inverter"
    if low.startswith("free"): return "Free Standing"
    if low.startswith("cassette"): return "Cassette"
    if low.startswith("concealed"): return "Concealed (CAC)"
    if low.startswith("package"): return "Package (CAC)"
    if low.startswith("convertible"): return "Convertible (CAC)"
    if low.startswith("air"): return "Air Purifier"
    if low.startswith("multi"): return "Multi V"
    if low.startswith("accessory"): return "Accessory/Other"
    if low.startswith("cos"): return "COS adjustment"
    if low.startswith("inventory pro"): return "Inventory Provision"
    if low.startswith("adjust"): return "Adjust."
    return s

def num(v):
    try: return round(float(v), 4)
    except (TypeError, ValueError): return 0.0

def is_total_row(segment, category):
    seg = str(segment or "").strip().lower()
    cat = str(category or "").strip().lower()
    return seg.endswith("total") or cat.startswith("total")

wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
records = []
validation = {}  # (year,month) -> {'detail_gm':x, 'total_gm':y}

for sheet in ("2024","2025","2026"):
    ws = wb[sheet]
    for row in ws.iter_rows(min_row=2, values_only=True):
        ym = row[2]
        if ym is None: continue
        try: ym = int(re.sub(r"\D","",str(ym)))
        except ValueError: continue
        if ym < 202000: continue
        year, month = ym//100, ym%100
        cat_raw, seg = row[4], row[3]
        if cat_raw in (None,""): continue
        amts = {k: num(row[ci]) for ci,k in M.items()}
        key = (year, month)
        validation.setdefault(key, {"detail_gm":0.0,"total_gm":0.0,"detail_gs":0.0,"total_gs":0.0})
        if is_total_row(seg, cat_raw):
            validation[key]["total_gm"] += amts["gross_margin"]
            validation[key]["total_gs"] += amts["gross_sale"]
            continue
        cat = norm_cat(cat_raw)
        validation[key]["detail_gm"] += amts["gross_margin"]
        validation[key]["detail_gs"] += amts["gross_sale"]
        rec = {"year":year, "month":month, "category":cat,
               "is_product": cat in PRODUCT_CATS}
        rec.update(amts)
        records.append(rec)
wb.close()

# ---- 정합성 검증: 상세 합 == 월 Total행 ----
print("=== 정합성 검증 (상세 GM합 vs 월 Total행 GM) ===")
bad = 0
for (y,m), v in sorted(validation.items()):
    dgm, tgm = v["detail_gm"], v["total_gm"]
    if abs(dgm - tgm) > 0.5:
        print(f"  ❌ {y}-{m:02d}: detail={dgm:,.1f} total={tgm:,.1f} Δ={dgm-tgm:,.2f}")
        bad += 1
print(f"  검증 월 수: {len(validation)} / 불일치: {bad}")

meta = {
    "product_cats": PRODUCT_CATS,
    "adj_cats": ADJ_CATS,
    "metric_keys": METRIC_KEYS,
    "years": [2024,2025,2026],
    "year_months": {str(y): sorted(m for (yy,m) in validation if yy==y) for y in (2024,2025,2026)},
}

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// GPC 대시보드 데이터 (build_gpc_dashboard.py 자동생성 — 직접 수정 금지)\n")
    f.write("const GPC_META = " + json.dumps(meta, ensure_ascii=False) + ";\n")
    f.write("const GPC_DATA = " + json.dumps(records, ensure_ascii=False) + ";\n")

print(f"\n✅ 생성: {OUT}")
print(f"   레코드 {len(records)}건, 제품카테고리 {len(PRODUCT_CATS)}종")
for y in (2024,2025,2026):
    mm = meta["year_months"][str(y)]
    print(f"   {y}: {len(mm)}개월 ({mm[0]}~{mm[-1]})")
