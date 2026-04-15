"""
AC 시뮬레이터 데이터 탐색 스크립트
실행: python explore_ac_data.py
"""
import json, re
from collections import defaultdict

SHAKER_DIR = r"C:\Users\J_park\Shaker-MD-App"
EXTRA_DATA = rf"{SHAKER_DIR}\docs\dashboards\extra-sellout\data.json"
BH_HTML    = rf"{SHAKER_DIR}\docs\dashboards\bh-sellout\index.html"
SELL_THRU  = rf"{SHAKER_DIR}\docs\dashboards\sell-thru-progress\data.json"

AC_SF_NAMES = {
    "FREE STANDING AIR CONDITIONER",
    "MINI SPLIT AIR CONDITIONER",
    "WINDOW AIR CONDITIONER",
    "SEEC WINDOW AIR CONDITIONER",
}

print("=== 1. eXtra data.json ===")
with open(EXTRA_DATA, encoding="utf-8") as f:
    d = json.load(f)

lg_idx    = d["d"]["b"].index("LG")
sf_list   = d["d"]["sf"]
type_list = d["d"]["t"]
size_list = d["d"]["sz"]
year_list = d["d"]["y"]
week_list = d["d"]["w"]
ac_sf_idx = {i for i, s in enumerate(sf_list) if s in AC_SF_NAMES}

print(f"LG brand index: {lg_idx}")
print(f"Year range: {year_list}")
print(f"AC sub_families: {[sf_list[i] for i in sorted(ac_sf_idx)]}")

weekly = defaultdict(lambda: defaultdict(int))
price_samples = defaultdict(list)

for r in d["c"]:
    if r[2] != lg_idx or r[3] not in ac_sf_idx:
        continue
    dm_key = f"{r[0]}-{r[1]}"
    if dm_key not in d["dm"]:
        continue
    week_idx = d["dm"][dm_key][0]
    year     = year_list[r[0]]
    iso_week = f"{year}-{week_list[week_idx]}"
    product  = (sf_list[r[3]], type_list[r[4]], size_list[r[5]])
    weekly[product][iso_week] += r[9]
    if r[11] > 0:
        price_samples[product].append(r[11])

print(f"\nUnique AC product combos: {len(weekly)}")
totals = {k: sum(v.values()) for k, v in weekly.items()}
print("Top 10 by total units:")
for prod, tot in sorted(totals.items(), key=lambda x: -x[1])[:10]:
    sf, typ, sz = prod
    weeks_n = len(weekly[prod])
    avg_fp = round(sum(price_samples[prod]) / len(price_samples[prod])) if price_samples[prod] else 0
    print(f"  {sf} | {sz} | {typ}: {tot} units, {weeks_n} weeks, avg_fp={avg_fp}")

# Show date range for top product
top_prod = max(totals, key=totals.get)
sorted_wks = sorted(weekly[top_prod].items())
print(f"\nTop product ({top_prod[0]} {top_prod[2]}) range: {sorted_wks[0][0]} -> {sorted_wks[-1][0]}, {len(sorted_wks)} points")
print(f"Recent 4 weeks: {sorted_wks[-4:]}")

print("\n=== 2. BH sell-out HTML ===")
with open(BH_HTML, encoding="utf-8") as f:
    bh_content = f.read()

all_data = None
for line in bh_content.split("\n"):
    if "const _ALL" in line:
        m = re.search(r"const _ALL\s*=\s*(\{.+\})\s*;", line)
        if m:
            all_data = json.loads(m.group(1))
            break

if all_data:
    print(f"Years: {all_data['years']}")
    bh_weekly = defaultdict(lambda: defaultdict(int))
    for yr in all_data["years"]:
        for rec in all_data.get("data", {}).get(yr, {}).get("raw", []):
            model = rec.get("model") or rec.get("code", "")
            if model:
                bh_weekly[model][f"{yr}-{rec['w']}"] += rec.get("q", 0)
    print(f"BH unique models: {len(bh_weekly)}")
    bh_totals = {k: sum(v.values()) for k, v in bh_weekly.items()}
    for m, tot in sorted(bh_totals.items(), key=lambda x: -x[1])[:5]:
        print(f"  {m}: {tot} units, {len(bh_weekly[m])} data points")
else:
    print("  ERROR: _ALL not found")

print("\n=== 3. remain.current ===")
with open(SELL_THRU, encoding="utf-8") as f:
    st = json.load(f)
rc = st["remain"]["current"]
print(f"  keys: {list(rc.keys())}")
print(f"  tq={rc.get('tq')}, tv={rc.get('tv')}, date={rc.get('date')}")

print("\n=== 4. extra-price DATA sample ===")
EXTRA_PRICE = rf"{SHAKER_DIR}\docs\dashboards\extra-price\index.html"
with open(EXTRA_PRICE, encoding="utf-8") as f:
    price_content = f.read()

import json as _json
pos = price_content.find("const DATA=")
if pos >= 0:
    decoder = _json.JSONDecoder()
    data, _ = decoder.raw_decode(price_content, pos + len("const DATA="))
    print(f"Price records: {len(data)}")
    # Recent competitor prices for Free Standing AC 3.5 Ton
    from collections import defaultdict as dd
    best = {}
    for rec in data:
        b = rec.get("b","").upper()
        if b not in ["GREE","SAMSUNG","MIDEA","ZAMIL","LG"]:
            continue
        if "Free Standing" not in rec.get("c",""):
            continue
        if abs((rec.get("t") or 0) - 3.5) > 1.0:
            continue
        date = rec.get("d","")
        fp   = rec.get("fp") or rec.get("sp") or 0
        if fp > 0 and (b not in best or date > best[b]["date"]):
            best[b] = {"price": fp, "date": date, "model": rec.get("m","")}
    print("Free Standing ~3.5T latest prices:")
    for brand, info in sorted(best.items()):
        print(f"  {brand}: SAR {info['price']} ({info['date']}) — {info['model'][:50]}")
else:
    print("  const DATA= not found")

print("\nDONE.")
