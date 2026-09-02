#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""독립 검증: 엑셀 원본 셀 ↔ 생성된 gpc_data.js 의 GPC_OFFICIAL 을 1:1 대조.
빌더 코드를 재사용하지 않고 엑셀을 처음부터 다시 읽는다(같은 버그를 공유하지 않기 위함)."""
import json, re, sys, collections, openpyxl

XL = ("/home/ubuntu/2026/10. Automation/03. Operation/00. GPC/02. 2026/"
      "04. Official GPC/07. GPC official_Jul_2026.xlsx")
JS = "/home/ubuntu/Shaker-MD-App/docs/dashboards/gpc/gpc_data.js"

# 엑셀 라벨 → 정본 (빌더와 독립적으로 손으로 다시 적음)
X2C = {"Window": "Window AC", "Split  (On / Off) ": "Split On/Off",
       "Split - Inverter": "Split Inverter", "Free Standing": "Floor Standing AC",
       "Cassette": "Cassette AC", "Concealed (CAC)": "Concealed Set",
       "Package (CAC)": "Unitary Package", "Convertible (CAC)": "CAC Ducted",
       "Air Purifier": "Accessory/Others", "Multi V": "Multi-V",
       "Others": "Accessory/Others"}
SGN = {"GSV": ("gsv", 1), "YED": ("yed", -1), "ADC": ("adc", -1), "VPD": ("vpd", -1),
       "DSI": ("dsi", -1), "COGS": ("cogs", 1), "INV": ("inv", -1), "VSP": ("vsp", 1),
       "NSV": ("nsv", 1), "GM": ("gm", 1)}

V = list(openpyxl.load_workbook(XL, read_only=True, data_only=True).active.iter_rows(values_only=True))
lab, band = V[2], V[1]
xl = collections.defaultdict(lambda: collections.defaultdict(float))
for r in V[3:279]:
    met = str(r[5])
    if met not in SGN or r[4] is None:
        continue
    cat = X2C[str(r[4])]
    key, sg = SGN[met]
    for j in range(6, 98):
        mo = re.fullmatch(r"(?:\((A|B)\))?(\d{4})(\d{2})", str(lab[j] or ""))
        if not mo or r[j] in (None, ""):
            continue
        b = "B" if mo.group(1) == "B" else ("F" if str(band[j]) == "FCST" else "A")
        xl[(int(mo.group(2)), int(mo.group(3)), b, cat)][key] += float(r[j]) * sg

src = open(JS, encoding="utf-8").read()
rows = json.loads(re.search(r"const GPC_OFFICIAL = (\[.*?\]);", src, re.S).group(1))
js = {(r["y"], r["m"], r["b"], r["cat"]): r for r in rows}

bad = []
for k, xv in xl.items():
    if all(abs(v) < 0.5 for v in xv.values()):
        continue                                   # 전 지표 0 → 의도적으로 미적재
    jv = js.get(k)
    if jv is None:
        bad.append((k, "js 누락", None, None)); continue
    for mk, xval in xv.items():
        if abs(round(xval, 1) - jv[mk]) > 0.11:     # 소수 1자리 반올림 허용
            bad.append((k, mk, xval, jv[mk]))
extra = [k for k in js if k not in xl]

print(f"엑셀 셀그룹 {len(xl)} / js 레코드 {len(js)}")
print(f"불일치 {len(bad)}건 / js 에만 있는 키 {len(extra)}건")
for b in bad[:20]:
    print("  ❌", b)
for e in extra[:10]:
    print("  ❌ js 잉여:", e)
ok = not bad and not extra
print("\n" + ("✅ 엑셀 원본과 완전 일치" if ok else "❌ 불일치 존재"))
sys.exit(0 if ok else 1)
