#!/usr/bin/env python3
"""
Tamkeen AC Price Tracking - HTML Dashboard
Sections: KPIs, Price Alerts, New/Disc, Category KPI, Brand Compare, Price Trend, Full SKU, Stock + Delivery
Based on BinMomen template, adapted for Tamkeen snapshot-based data structure.
"""
import os, sys, json, math, glob, re, shutil, subprocess
from datetime import datetime
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Missing: {e}\nRun: pip install pandas openpyxl numpy"); sys.exit(1)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = CURRENT_DIR
OUTPUT_FILE = os.path.join(CURRENT_DIR, "tamkeen_ac_dashboard.html")

def safe(v):
    if v is None: return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating,)):
        return None if math.isnan(float(v)) else round(float(v), 2)
    if isinstance(v, (np.bool_,)): return bool(v)
    if isinstance(v, pd.Timestamp): return v.strftime('%Y-%m-%d')
    return v

# == Load & Merge Snapshots ====================================================
print("[1/4] Loading and merging Tamkeen snapshots...")
pattern = os.path.join(DATA_DIR, "Tamkeen_Complete_*.xlsx")
all_files = sorted(glob.glob(pattern))
# Exclude partial files
all_files = [f for f in all_files if '_partial' not in f]
print(f"      Found {len(all_files)} snapshot files")

# Group by date, keep latest file per date
date_files = {}
for fp in all_files:
    fname = os.path.basename(fp)
    m = re.search(r'(\d{8})_(\d{4})', fname)
    if m:
        d = m.group(1)  # YYYYMMDD
        t = m.group(2)  # HHMM
        if d not in date_files or t > date_files[d][1]:
            date_files[d] = (fp, t)

selected_files = [(d, info[0]) for d, info in sorted(date_files.items())]
print(f"      Using {len(selected_files)} unique dates (latest file per date)")

dfs = []
for date_str, fp in selected_files:
    try:
        tmp = pd.read_excel(fp)
        # Parse date from filename: YYYYMMDD -> YYYY-MM-DD
        tmp['Scrape_Date'] = pd.to_datetime(date_str, format='%Y%m%d')
        dfs.append(tmp)
    except Exception as e:
        print(f"      [WARN] Skipping {os.path.basename(fp)}: {e}")

df = pd.concat(dfs, ignore_index=True)
print(f"      Total: {len(df):,} rows after merge")

# == Process Data ==============================================================
print("[2/4] Processing data...")
df['date_only'] = df['Scrape_Date'].dt.date

# Numeric coercion
for col in ['Tonnage', 'Original Price (SR)', 'Sale Price (SR)', 'Discount (SR)',
            'Stock Qty', 'Capacity (BTU)']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Discount rate from string like "30.6%" -> 0.306
df['Discount_Rate'] = df['Discount (%)'].astype(str).str.replace('%', '').str.strip()
df['Discount_Rate'] = pd.to_numeric(df['Discount_Rate'], errors='coerce') / 100.0

# Fill missing discount rate from prices
missing_dr = df['Discount_Rate'].isna()
valid = missing_dr & df['Original Price (SR)'].notna() & df['Sale Price (SR)'].notna() & (df['Original Price (SR)'] > 0)
df.loc[valid, 'Discount_Rate'] = 1 - df.loc[valid, 'Sale Price (SR)'] / df.loc[valid, 'Original Price (SR)']

# In_Stock boolean
df['_in_stock'] = df['In Stock'].astype(str).str.strip().str.lower() == 'yes'

# Express delivery boolean
df['_express'] = df['Express Delivery'].astype(str).str.strip().str.lower() == 'yes'

# Use SKU as unique identifier
df['_sku'] = df['SKU'].fillna(df['Name'])

all_dates = sorted(df['date_only'].unique())
latest_date = str(all_dates[-1])
first_date = str(all_dates[0])

# Stock status rules
STOCK_RULES = [
    {'label': 'Out of Stock', 'min': None, 'max': 0},
    {'label': 'Critical', 'min': 0, 'max': 5},
    {'label': 'Low', 'min': 5, 'max': 15},
    {'label': 'High', 'min': 15, 'max': 50},
    {'label': 'OK', 'min': 50, 'max': None},
]

# == Serialize =================================================================
print("[3/4] Serializing data...")
records = []
for _, r in df.iterrows():
    records.append({
        'd': str(r['date_only']) if pd.notna(r.get('Scrape_Date')) else None,
        'b': safe(r.get('Brand')),
        'n': str(r.get('Name',''))[:80] if pd.notna(r.get('Name')) else '',
        'm': str(r.get('SKU','')) if pd.notna(r.get('SKU')) else '',
        's': str(r.get('_sku','')),  # unique key
        'c': safe(r.get('Category')),
        'h': safe(r.get('Cooling Type')),
        'cp': safe(r.get('Compressor')),
        't': safe(r.get('Tonnage')),
        'sp': safe(r.get('Original Price (SR)')),
        'sl': safe(r.get('Sale Price (SR)')),
        'dr': safe(r.get('Discount_Rate')),
        'dsr': safe(r.get('Discount (SR)')),  # Discount in SAR
        'fp': safe(r.get('Sale Price (SR)')),  # effective price = Sale Price
        'ins': bool(r.get('_in_stock')) if pd.notna(r.get('_in_stock')) else False,
        'stk': safe(r.get('Stock Qty')),
        'exp': bool(r.get('_express')) if pd.notna(r.get('_express')) else False,
        'ed': str(r.get('Expected Delivery','')) if pd.notna(r.get('Expected Delivery')) else '',
        'url': str(r.get('Product URL','')) if pd.notna(r.get('Product URL')) else '',
        'img': str(r.get('Image URL','')) if pd.notna(r.get('Image URL')) else '',
        'btu': safe(r.get('Capacity (BTU)')),
    })

from datetime import date as dt_date
date_meta = []
for d in all_dates:
    dd = d if isinstance(d, dt_date) else pd.Timestamp(d).date()
    iso = dd.isocalendar()
    date_meta.append({'date':str(dd),'year':dd.year,'month':dd.month,'month_name':dd.strftime('%b'),'week':iso[1]})

dates_list = [str(d) for d in all_dates]
brands_list = sorted(df['Brand'].dropna().unique().tolist())
categories_list = sorted(df['Category'].dropna().unique().tolist())
cooling_list = sorted(df['Cooling Type'].dropna().unique().tolist())
compressor_list = sorted(df['Compressor'].dropna().unique().tolist())
ton_list = sorted(df['Tonnage'].dropna().unique().tolist())

BRAND_COLORS = {b: c for b, c in zip(brands_list, [
    '#1F4E79','#2E75B6','#ED7D31','#A9D18E','#FF0000','#70AD47','#FFC000','#4472C4',
    '#9E480E','#7030A0','#00B0F0','#FF7F7F','#92D050','#FF00FF','#00B050','#C00000',
    '#B4C6E7','#F4B183','#808080','#5B9BD5','#2F4F4F','#D2691E','#4169E1','#228B22'])}


# ── SKU 4-way Status Classification ───────────────────────────────────────────
# New / Reactive / Temp OOS / Discontinued
TEMP_OOS_THRESHOLD = 14
REACTIVE_GAP_MIN   = 2

all_dates_seq = sorted([d for d in df['date_only'].unique() if pd.notna(d)])
latest_d      = all_dates_seq[-1]

sku_date_map  = df.groupby('_sku')['date_only'].apply(lambda s: set(d for d in s if pd.notna(d))).to_dict()

sku_status   = {}
disc_records = []

for sku, dates_set in sku_date_map.items():
    first_d = min(dates_set)
    last_d  = max(dates_set)

    if last_d == latest_d:
        if first_d == latest_d:
            sku_status[sku] = {'st':'new','ab':0,'ls':str(last_d),'fs':str(first_d),'gb':0}
        else:
            idx = all_dates_seq.index(latest_d)
            gap = 0
            for pd_ in reversed(all_dates_seq[:idx]):
                if pd_ not in dates_set: gap += 1
                else: break
            if gap >= REACTIVE_GAP_MIN:
                sku_status[sku] = {'st':'reactive','ab':0,'ls':str(last_d),'fs':str(first_d),'gb':gap}
    else:
        absent_days = sum(1 for d in all_dates_seq if d > last_d)
        st = 'disc' if absent_days >= TEMP_OOS_THRESHOLD else 'temp_disc'
        sku_status[sku] = {'st':st,'ab':absent_days,'ls':str(last_d),'fs':str(first_d),'gb':0}
        row = df[(df['_sku']==sku) & (df['date_only']==last_d)].iloc[0]
        disc_records.append({
            's':str(sku),'st':st,'ab':absent_days,'ls':str(last_d),
            'b':safe(row.get('brand_en') if 'brand_en' in row else (row.get('Brand') if 'Brand' in row else None)),
            'n':next((str(row[k])[:70] for k in ['name_en','Name','Product_Name_EN','Product_Name','Product Name','product_name','name','title','Title','subtitle','Description','description'] if k in row.index and pd.notna(row.get(k)) and str(row.get(k)).strip()), ''),
            'm':str(sku),
            'c':safe(row.get('category_en') if 'category_en' in row else row.get('Category')),
            'h':safe(row.get('ac_type') if 'ac_type' in row else row.get('Cold_or_HC')),
            'cp':safe(row.get('compressor') if 'compressor' in row else row.get('Compressor_Type')),
            't':safe(row.get('ton') if 'ton' in row else row.get('Cooling_Capacity_Ton')),
            'fp':safe(row.get('price') if 'price' in row else row.get('Final_Sale_Price')),
            'url':next((str(row[k]) for k in ['url','URL','Product URL','Product_URL','URL_Key','product_url','link','Link'] if k in row.index and pd.notna(row.get(k)) and str(row.get(k)).strip()), ''),
        })

generated_at = datetime.now().strftime('%Y-%m-%d %H:%M')

# == Build HTML ================================================================
print("[4/4] Generating HTML...")

HTML_HEAD = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Tamkeen AC Price Tracker</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2"></script>
<script src="https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<script>
tailwind.config={theme:{extend:{fontFamily:{sans:['Inter','system-ui','sans-serif']},colors:{navy:{50:'#E8F4FD',100:'#D1E9FB',200:'#A3D3F7',500:'#2E75B6',700:'#1E3A5F',800:'#1F4E79',900:'#0F2A42'},teal:{50:'#f0fdfa',500:'#14b8a6',600:'#0d9488',700:'#0f766e'}}}}}
</script>
<style>
.sort-asc::after{content:' \\25B2';font-size:9px}.sort-desc::after{content:' \\25BC';font-size:9px}
.tbl-wrap{overflow-x:auto}.tbl-wrap table{width:100%;border-collapse:collapse;font-size:12px}
.tbl-wrap th{background:#1a2744;color:#fff;padding:7px 10px;text-align:left;position:sticky;top:0;z-index:2;white-space:nowrap;cursor:pointer;user-select:none;font-weight:600;font-size:11px}
.tbl-wrap th:hover{background:#243460}
.tbl-wrap td{padding:5px 10px;border-bottom:1px solid #f0f0f0;white-space:nowrap}
.tbl-wrap tr:nth-child(even) td{background:#f8fafc}.tbl-wrap tr:hover td{background:#e8f0fe}
.up-cell{color:#dc2626;font-weight:600}.dn-cell{color:#16a34a;font-weight:600}
.level-cat td{background:#ccfbf1!important;font-weight:700;color:#134e4a;border-left:4px solid #0d9488}
.level-cool td{background:#e6fffa!important;font-weight:600;border-left:4px solid #2dd4bf}
.level-cp td{background:#fef9c3!important;font-weight:500;border-left:4px solid #facc15}
.level-ton td{background:#fff!important;color:#475569;border-left:4px solid #d1d5db}
.type-badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.3px}
.type-cat{background:#0d9488;color:#fff}.type-cool{background:#2dd4bf;color:#fff}.type-cp{background:#facc15;color:#713f12}.type-ton{background:#e5e7eb;color:#374151}
.ms-wrap{position:relative;display:inline-block}
.ms-btn{display:flex;align-items:center;gap:4px;padding:3px 10px;border:1px solid #d1d5db;border-radius:6px;background:#fff;font-size:11px;cursor:pointer;white-space:nowrap;transition:all .15s}
.ms-btn:hover{border-color:#0d9488;background:#f0fdfa}
.ms-menu{display:none;position:absolute;top:100%;left:0;z-index:50;min-width:180px;max-height:280px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;box-shadow:0 8px 25px rgba(0,0,0,.15);margin-top:2px}
.ms-menu.open{display:block}
.ms-menu .ms-actions{display:flex;gap:6px;padding:6px 10px;border-bottom:1px solid #f0f0f0;font-size:10px}
.ms-menu .ms-actions button{color:#0d9488;font-weight:600;cursor:pointer;background:none;border:none}
.ms-menu .ms-actions button:hover{text-decoration:underline}
.ms-menu .ms-actions button.ms-none{color:#dc2626}
.ms-menu .ms-list{max-height:230px;overflow-y:auto;padding:4px 0}
.ms-menu label{display:flex;align-items:center;gap:6px;padding:3px 10px;cursor:pointer;font-size:11px;transition:background .1s}
.ms-menu label:hover{background:#f1f5f9}
.ms-menu input[type=checkbox]{width:14px;height:14px;border-radius:3px}
.ms-menu label.ms-disabled{opacity:.35;pointer-events:none}
.ms-menu label.ms-disabled span{text-decoration:line-through}
.sec-search{font-size:11px;border:1px solid #d1d5db;border-radius:6px;padding:3px 8px;background:#fff;width:160px}
.sec-search:focus{outline:none;border-color:#0d9488;box-shadow:0 0 0 2px rgba(13,148,136,.15)}
.stk-badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.3px}
.stk-ok{background:#dcfce7;color:#166534}.stk-high{background:#dbeafe;color:#1e40af}.stk-low{background:#fef9c3;color:#854d0e}.stk-critical{background:#fee2e2;color:#991b1b}.stk-out{background:#fecaca;color:#7f1d1d}
.exp-badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700}
.exp-yes{background:#dcfce7;color:#166534}.exp-no{background:#fee2e2;color:#991b1b}
@media print{.no-print{display:none!important}}
/* ===== MOBILE RESPONSIVE ===== */
@media (max-width:640px){
  header .max-w-\\[1600px\\]{padding:12px 12px;gap:8px}
  header h1{font-size:16px}
  header .text-right{text-align:left;font-size:10px}
  .sticky.top-0 .max-w-\\[1600px\\]{padding:6px 8px}
  nav .flex{flex-wrap:wrap;padding-bottom:4px}
  nav a{flex-shrink:0}
  main{padding:8px!important}
  main section{padding:10px!important}
  .filter-bar{flex-wrap:wrap;gap:6px}
  .tbl-wrap{font-size:11px}
  .tbl-wrap th{padding:5px 6px;font-size:10px}
  .tbl-wrap td{padding:4px 6px;font-size:11px}
  canvas{max-height:250px!important}
  div[style*="height:350px"],div[style*="height:360px"],div[style*="height:400px"],div[style*="height:320px"]{height:220px!important}
  .sec-search{width:120px}
  .grid.grid-cols-1.lg\\:grid-cols-2{grid-template-columns:1fr}
}
@media (max-width:380px){
  header h1{font-size:14px}
  .tbl-wrap{font-size:10px}
  .tbl-wrap th{font-size:9px;padding:4px 4px}
  .tbl-wrap td{font-size:10px;padding:3px 4px}
  div[style*="height:350px"],div[style*="height:360px"],div[style*="height:400px"],div[style*="height:320px"]{height:180px!important}
}
</style></head>
<body class="bg-gray-50 font-sans text-gray-800 text-sm">
"""

HTML_BODY = """
<header style="background:linear-gradient(135deg,#1a2744,#1e3a5f)" class="text-white shadow-lg">
  <div class="max-w-[1600px] mx-auto px-4 sm:px-6 py-3 sm:py-4 flex flex-wrap items-center justify-between gap-2 sm:gap-4">
    <div><h1 class="text-base sm:text-xl font-bold tracking-wide">Tamkeen AC Price Tracker</h1>
      <p class="text-xs mt-1" style="color:#93c5fd">Saudi Arabia &middot; Air Conditioners &middot; Daily Price Monitoring</p></div>
    <div class="text-right text-xs space-y-0.5" style="color:#bfdbfe">
      <div><b class="text-white">Last Updated:</b> <span id="metaDate"></span></div>
      <div><b class="text-white">Period:</b> <span id="metaPeriod"></span></div>
      <div><b class="text-white">SKUs:</b> <span id="metaSku"></span></div></div>
  </div>
</header>

<!-- GLOBAL FILTER BAR -->
<div class="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-gray-200 shadow-sm no-print">
  <div class="max-w-[1600px] mx-auto px-3 sm:px-6 py-2 sm:py-2.5 flex flex-wrap items-center gap-2">
    <span class="text-[10px] font-bold uppercase tracking-wider" style="color:#1a2744">Global</span>
    <div id="gf_date"></div>
    <div class="w-px h-5 bg-gray-300"></div>
    <div id="gf_cat"></div><div id="gf_cool"></div><div id="gf_cp"></div><div id="gf_ton"></div><div id="gf_brand"></div>
    <div class="w-px h-5 bg-gray-300"></div>
    <span id="gf_count" class="text-xs text-gray-500 font-medium"></span>
    <button type="button" onclick="resetGlobal()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-600 rounded px-2.5 py-1 font-medium">Reset</button>
    <span id="gf_compare" class="text-[10px] text-gray-400 ml-auto"></span>
  </div>
</div>

<nav class="max-w-[1600px] mx-auto px-3 sm:px-6 pt-2 sm:pt-3 no-print">
  <div class="flex flex-wrap gap-1.5 text-[11px]">
    <a href="#sec-kpi" class="px-3 py-1 text-white rounded-full font-medium" style="background:#1a2744">KPIs</a>
    <a href="#sec-alert" class="px-3 py-1 bg-white rounded-full border border-gray-200 hover:bg-blue-50" style="color:#1a2744">Price Alerts</a>
    <a href="#sec-new" class="px-3 py-1 bg-white rounded-full border border-gray-200 hover:bg-blue-50" style="color:#1a2744">New/Disc</a>
    <a href="#sec-catKPI" class="px-3 py-1 bg-white rounded-full border border-gray-200 hover:bg-blue-50" style="color:#1a2744">Category KPI</a>
    <a href="#sec-brand" class="px-3 py-1 bg-white rounded-full border border-gray-200 hover:bg-blue-50" style="color:#1a2744">Brand Compare</a>
    <a href="#sec-trend" class="px-3 py-1 bg-white rounded-full border border-gray-200 hover:bg-blue-50" style="color:#1a2744">Price Trend</a>
    <a href="#sec-sku" class="px-3 py-1 bg-white rounded-full border border-gray-200 hover:bg-blue-50" style="color:#1a2744">Full SKU</a>
    <a href="#sec-stock" class="px-3 py-1 bg-white rounded-full border border-gray-200 hover:bg-blue-50" style="color:#1a2744">Stock</a>
    <a href="#sec-delivery" class="px-3 py-1 bg-white rounded-full border border-gray-200 hover:bg-blue-50" style="color:#1a2744">Delivery</a>
  </div>
</nav>

<main class="max-w-[1600px] mx-auto px-2 sm:px-6 py-2 sm:py-3 space-y-2 sm:space-y-3">

<!-- SEC 1: KPIs -->
<section id="sec-kpi" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold border-b-2 pb-2 mb-3" style="color:#1a2744;border-color:#1a2744">Key Performance Indicators</h2>
  <div id="kpiGrid" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5"></div>
</section>

<!-- SEC 2: Price Alerts -->
<section id="sec-alert" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold border-b-2 pb-2 mb-3" style="color:#1a2744;border-color:#1a2744">Price Change Alert <span class="text-xs font-normal text-gray-400">(vs compare date)</span></h2>
  <div class="flex flex-wrap items-center gap-2 mb-2">
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="dir-btn active px-3 py-1 text-xs font-medium bg-gray-700 text-white" data-dir="all">All</button>
      <button type="button" class="dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-red-600" data-dir="up">Up</button>
      <button type="button" class="dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-green-600" data-dir="down">Down</button></div>
  </div>
  <div class="tbl-wrap" style="max-height:380px;overflow-y:auto"><table id="tblAlert"><thead></thead><tbody></tbody></table></div>
</section>

<!-- SEC 3: SKU Status Tracker -->
<section id="sec-new" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">SKU Status Tracker</h2>
  <div class="flex gap-2 mb-3 flex-wrap" id="skuTabBar">
    <button class="sku-tab active" data-tab="new">🟢 New <span id="cntNew" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-green-100 text-green-700"></span></button>
    <button class="sku-tab" data-tab="reactive">🔵 Reactive <span id="cntReactive" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700"></span></button>
    <button class="sku-tab" data-tab="temp_disc">🟡 Temp OOS <span id="cntTempDisc" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700"></span></button>
    <button class="sku-tab" data-tab="disc">🔴 Discontinued <span id="cntDisc" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700"></span></button>
  </div>
  <div id="skuRunWarn"></div>
  <div id="skuTabDesc" class="text-[10px] text-gray-400 mb-2"></div>
  <div id="skuCards" class="space-y-2 max-h-[420px] overflow-y-auto"></div>
</section>

<!-- SEC 4: Category KPI -->
<section id="sec-catKPI" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold border-b-2 pb-2 mb-3" style="color:#1a2744;border-color:#1a2744">Category KPI Table</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s4_cat"></div><div id="s4_cool"></div><div id="s4_cp"></div><div id="s4_ton"></div><div id="s4_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s4_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <button type="button" onclick="resetS4()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div class="tbl-wrap" style="max-height:480px;overflow-y:auto"><table id="tblCatKPI"><thead></thead><tbody></tbody></table></div>
</section>

<!-- SEC 5: Brand Compare -->
<section id="sec-brand" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold border-b-2 pb-2 mb-3" style="color:#1a2744;border-color:#1a2744">Brand Price Comparison</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s5_cat"></div><div id="s5_cool"></div><div id="s5_cp"></div><div id="s5_ton"></div><div id="s5_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s5_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="s5agg-btn active px-3 py-1 text-[10px] font-medium text-white" style="background:#1a2744" data-agg="avg">Avg</button>
      <button type="button" class="s5agg-btn px-3 py-1 text-[10px] font-medium bg-gray-50 text-gray-600" data-agg="min">Min</button></div>
    <button type="button" onclick="resetS5()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <div style="height:360px"><canvas id="brandBarChart"></canvas></div>
    <div class="tbl-wrap" style="max-height:360px;overflow-y:auto"><table id="tblBrandSeg"><thead></thead><tbody></tbody></table></div>
  </div>
</section>

<!-- SEC 6: Price Trend -->
<section id="sec-trend" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold border-b-2 pb-2 mb-3" style="color:#1a2744;border-color:#1a2744">Price Trend (Time Series)</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s6_cat"></div><div id="s6_cool"></div><div id="s6_cp"></div><div id="s6_ton"></div><div id="s6_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s6_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="agg-btn active px-3 py-1 text-[10px] font-medium text-white" style="background:#1a2744" data-agg="avg">Avg</button>
      <button type="button" class="agg-btn px-3 py-1 text-[10px] font-medium bg-gray-50 text-gray-600" data-agg="min">Min</button></div>
    <button type="button" onclick="resetS6()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div style="height:400px"><canvas id="trendChart"></canvas></div>
</section>

<!-- SEC 7: Full SKU -->
<section id="sec-sku" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold border-b-2 pb-2 mb-3" style="color:#1a2744;border-color:#1a2744">Full SKU Table <span id="skuDateLabel" class="text-xs font-normal text-gray-400"></span></h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s7_cat"></div><div id="s7_cool"></div><div id="s7_cp"></div><div id="s7_ton"></div><div id="s7_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s7_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="stock-btn active px-2 py-1 text-[10px] font-medium bg-gray-700 text-white" data-val="all">All</button>
      <button type="button" class="stock-btn px-2 py-1 text-[10px] font-medium bg-gray-50 text-green-600" data-val="in">In Stock</button>
      <button type="button" class="stock-btn px-2 py-1 text-[10px] font-medium bg-gray-50 text-red-600" data-val="out">Out</button></div>
    <button type="button" onclick="downloadExcel()" class="text-[10px] bg-green-600 hover:bg-green-700 text-white rounded px-3 py-1 font-semibold flex items-center gap-1">
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
      Excel</button>
    <button type="button" onclick="resetS7()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
    <span id="skuCount" class="text-xs text-gray-400 ml-auto"></span>
  </div>
  <div class="tbl-wrap" style="max-height:500px;overflow-y:auto"><table id="tblSku"><thead></thead><tbody></tbody></table></div>
</section>

<!-- SEC 8: Stock Dashboard -->
<section id="sec-stock" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold border-b-2 pb-2 mb-3" style="color:#1a2744;border-color:#1a2744">Stock Dashboard</h2>
  <div class="filter-bar flex flex-wrap items-center gap-1.5 mb-3">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s8_date"></div>
    <div id="s8_cat"></div><div id="s8_cool"></div><div id="s8_cp"></div><div id="s8_ton"></div><div id="s8_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s8_search" placeholder="Search SKU/Brand..." class="sec-search"/>
    <button type="button" onclick="resetStock()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
    <span id="s8_compare" class="text-[10px] text-gray-400 ml-auto"></span>
  </div>
  <div id="stockKpiGrid" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2.5 mb-4"></div>
  <h3 class="text-xs font-bold text-gray-500 uppercase mt-2 mb-2">Stock Trend</h3>
  <div style="height:350px" class="mb-4"><canvas id="stockTrendChart"></canvas></div>
  <h3 class="text-xs font-bold text-gray-500 uppercase mt-2 mb-2">Stock Change Comparison</h3>
  <div class="flex flex-wrap items-center gap-2 mb-3">
    <span class="text-[10px] font-bold text-gray-400">Compare</span>
    <select id="s8_from" class="text-xs border rounded px-2 py-1"></select>
    <span class="text-xs text-gray-400">&rarr;</span>
    <select id="s8_to" class="text-xs border rounded px-2 py-1"></select>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="stk-dir-btn active px-3 py-1 text-xs font-medium bg-gray-700 text-white" data-dir="all">All</button>
      <button type="button" class="stk-dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-green-600" data-dir="inc">Increased</button>
      <button type="button" class="stk-dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-red-600" data-dir="dec">Decreased</button>
      <button type="button" class="stk-dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-orange-600" data-dir="out">New Stock-out</button></div>
    <span id="s8_chgCount" class="text-[10px] text-gray-400 ml-auto"></span>
  </div>
  <div class="tbl-wrap mb-4" style="max-height:350px;overflow-y:auto"><table id="tblStockAlert"><thead></thead><tbody></tbody></table></div>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div style="height:320px"><canvas id="stockBrandBar"></canvas></div>
    <div style="height:320px"><canvas id="stockCatDonut"></canvas></div>
  </div>
</section>

<!-- SEC 9: Delivery Analysis -->
<section id="sec-delivery" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold border-b-2 pb-2 mb-3" style="color:#1a2744;border-color:#1a2744">Delivery Analysis</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s9_cat"></div><div id="s9_cool"></div><div id="s9_cp"></div><div id="s9_ton"></div><div id="s9_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s9_search" placeholder="Search SKU/Brand..." class="sec-search"/>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="exp-btn active px-3 py-1 text-[10px] font-medium bg-gray-700 text-white" data-val="all">All</button>
      <button type="button" class="exp-btn px-3 py-1 text-[10px] font-medium bg-gray-50 text-green-600" data-val="yes">Express</button>
      <button type="button" class="exp-btn px-3 py-1 text-[10px] font-medium bg-gray-50 text-red-600" data-val="no">No Express</button></div>
    <button type="button" onclick="resetS9()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
    <span id="s9_count" class="text-[10px] text-gray-400 ml-auto"></span>
  </div>
  <div id="deliveryKpiGrid" class="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4"></div>
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
    <div style="height:320px"><canvas id="deliveryBrandBar"></canvas></div>
    <div style="height:320px"><canvas id="deliveryCatDonut"></canvas></div>
  </div>
  <h3 class="text-xs font-bold text-gray-500 uppercase mt-2 mb-2">Express Delivery SKU List</h3>
  <div class="tbl-wrap" style="max-height:400px;overflow-y:auto"><table id="tblDelivery"><thead></thead><tbody></tbody></table></div>
</section>

</main>
<footer class="text-center py-3 text-[10px] text-gray-400">Tamkeen AC Price Tracking Dashboard &middot; Generated GENERATED_AT</footer>
"""

HTML_DATA = f"""<script>
const DATA={json.dumps(records,ensure_ascii=False)};
const DATE_META={json.dumps(date_meta)};
const DATES={json.dumps(dates_list)};
const BRANDS={json.dumps(brands_list)};
const CATEGORIES={json.dumps(categories_list)};
const COOLING={json.dumps(cooling_list)};
const COMPRESSORS={json.dumps(compressor_list)};
const TONS={json.dumps([float(t) for t in ton_list])};
const LATEST_DATE={json.dumps(latest_date)};
const FIRST_DATE={json.dumps(first_date)};
const BRAND_COLORS={json.dumps(BRAND_COLORS)};
const SKU_STATUS={json.dumps(sku_status,ensure_ascii=False)};
const DISC_RECORDS={json.dumps(disc_records,ensure_ascii=False)};
const STOCK_RULES={json.dumps(STOCK_RULES)};
</script>
"""

HTML_LOGIC = r"""<script>
// === UTILITIES ================================================================
Chart.register(ChartDataLabels);
Chart.defaults.plugins.datalabels={display:false};
const fmtSAR=v=>v==null?'-':Number(v).toLocaleString('en-SA',{maximumFractionDigits:0});
const fmtPct=v=>v==null?'-':(v*100).toFixed(1)+'%';
const fmtPctR=v=>v==null?'-':v.toFixed(1)+'%';
const fmtChg=v=>{if(v==null)return'-';return(v>0?'+':'')+Number(v).toLocaleString('en-SA',{maximumFractionDigits:0});};
const colorOf=br=>BRAND_COLORS[br]||'#6b7280';
const alphaC=(hex,a)=>{const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);return`rgba(${r},${g},${b},${a})`;};
const mean=arr=>arr.length?arr.reduce((s,v)=>s+v,0)/arr.length:null;
const searchMatch=(r,q)=>!q||((r.b||'')+(r.s||'')+(r.m||'')+(r.n||'')+(r.c||'')+(r.h||'')+(r.cp||'')+(r.t||'')).toLowerCase().includes(q);

function stkStatus(qty){
  if(qty==null||qty<=0) return {label:'Out of Stock',cls:'stk-out'};
  if(qty<=5) return {label:'Critical',cls:'stk-critical'};
  if(qty<=15) return {label:'Low',cls:'stk-low'};
  if(qty<=50) return {label:'High',cls:'stk-high'};
  return {label:'OK',cls:'stk-ok'};
}

function sortTbl(id,colIdx){
  const tbl=document.getElementById(id);
  const th=tbl.querySelector('thead tr').children[colIdx];
  const asc=!th.classList.contains('sort-asc');
  tbl.querySelectorAll('th').forEach(t=>{t.classList.remove('sort-asc','sort-desc');});
  th.classList.add(asc?'sort-asc':'sort-desc');
  const rows=[...tbl.querySelector('tbody').rows];
  rows.sort((a,b)=>{
    let va=a.cells[colIdx].textContent.replace(/[,%SAR+\s]/g,''),vb=b.cells[colIdx].textContent.replace(/[,%SAR+\s]/g,'');
    const na=parseFloat(va),nb=parseFloat(vb);
    if(!isNaN(na)&&!isNaN(nb))return asc?na-nb:nb-na;
    return asc?va.localeCompare(vb):vb.localeCompare(va);
  });
  const tbody=tbl.querySelector('tbody');rows.forEach(r=>tbody.appendChild(r));
}

// === MULTI-SELECT COMPONENT ==================================================
class MS {
  constructor(el,opts,label,cb,colorFn){
    this.el=el;this.opts=opts;this.label=label;this.cb=cb;this.colorFn=colorFn||null;
    this.sel=new Set(opts.map(String));this._build();
  }
  _build(){
    const w=document.createElement('div');w.className='ms-wrap';
    const btn=document.createElement('button');btn.type='button';btn.className='ms-btn';
    this.btnEl=btn;w.appendChild(btn);
    const menu=document.createElement('div');menu.className='ms-menu';
    const acts=document.createElement('div');acts.className='ms-actions';
    const aAll=document.createElement('button');aAll.textContent='All';aAll.onclick=()=>this.selectAll();
    const aNone=document.createElement('button');aNone.textContent='None';aNone.className='ms-none';aNone.onclick=()=>this.selectNone();
    acts.appendChild(aAll);acts.appendChild(aNone);menu.appendChild(acts);
    const list=document.createElement('div');list.className='ms-list';
    this.opts.forEach(o=>{
      const lbl=document.createElement('label');
      const cb=document.createElement('input');cb.type='checkbox';cb.checked=true;cb.value=String(o);
      cb.addEventListener('change',()=>{if(cb.checked)this.sel.add(String(o));else this.sel.delete(String(o));this._upd();this.cb();});
      lbl.appendChild(cb);
      const sp=document.createElement('span');
      const txt=this.label==='Ton'?parseFloat(o).toFixed(1)+'T':String(o);
      sp.textContent=txt;
      if(this.colorFn)sp.style.cssText=`color:${this.colorFn(o)};font-weight:600`;
      lbl.appendChild(sp);list.appendChild(lbl);
    });
    menu.appendChild(list);w.appendChild(menu);this.menuEl=menu;menu.addEventListener('click',e=>e.stopPropagation());
    btn.addEventListener('click',e=>{e.stopPropagation();document.querySelectorAll('.ms-menu.open').forEach(m=>{if(m!==menu)m.classList.remove('open')});menu.classList.toggle('open');});
    this.listEl=list;
    this.el.appendChild(w);this._upd();
  }
  _upd(){const avail=this._availCount();this.btnEl.innerHTML=`${this.label} <b style="color:#1a2744">${this.sel.size}/${avail}</b> <span class="text-gray-400 text-[9px]">&#9662;</span>`;}
  _availCount(){let n=0;this.listEl.querySelectorAll('label').forEach(l=>{if(!l.classList.contains('ms-disabled'))n++;});return n||this.opts.length;}
  selectAll(){this.sel=new Set();this.listEl.querySelectorAll('input').forEach(c=>{if(!c.disabled){this.sel.add(c.value);c.checked=true;}else{c.checked=false;}});this._upd();this.cb();}
  selectNone(){this.sel.clear();this.listEl.querySelectorAll('input').forEach(c=>c.checked=false);this._upd();this.cb();}
  reset(){this.selectAll();}
  getSelected(){return this.sel;}
  setSelected(vals){this.sel=new Set(vals.map(String));this.listEl.querySelectorAll('input').forEach(cb=>{cb.checked=this.sel.has(cb.value);});this._upd();}
  updateAvailable(availSet){
    this.listEl.querySelectorAll('label').forEach(lbl=>{
      const cb=lbl.querySelector('input');
      const avail=availSet.has(cb.value);
      lbl.classList.toggle('ms-disabled',!avail);
      cb.disabled=!avail;
    });
    this._upd();
  }
}
document.addEventListener('click',()=>document.querySelectorAll('.ms-menu.open').forEach(m=>m.classList.remove('open')));

// === FILTER HELPERS ==========================================================
function makeFilters(prefix,cb){
  return {
    cat: new MS(document.getElementById(prefix+'_cat'),CATEGORIES,'Category',cb),
    cool: new MS(document.getElementById(prefix+'_cool'),COOLING,'Cooling',cb),
    cp: new MS(document.getElementById(prefix+'_cp'),COMPRESSORS,'Compressor',cb),
    ton: new MS(document.getElementById(prefix+'_ton'),TONS.map(String),'Ton',cb),
    brand: new MS(document.getElementById(prefix+'_brand'),BRANDS,'Brand',cb,colorOf),
  };
}
function applyF(rows,f){
  return rows.filter(r=>{
    if(r.c!=null&&!f.cat.getSelected().has(r.c))return false;
    if(r.h!=null&&!f.cool.getSelected().has(r.h))return false;
    if(r.cp!=null&&!f.cp.getSelected().has(r.cp))return false;
    if(r.t!=null&&!f.ton.getSelected().has(String(r.t)))return false;
    if(r.b!=null&&!f.brand.getSelected().has(r.b))return false;
    return true;
  });
}
function resetF(f){f.cat.reset();f.cool.reset();f.cp.reset();f.ton.reset();f.brand.reset();}
function syncToSection(src,tgt){
  tgt.cat.setSelected([...src.cat.getSelected()]);
  tgt.cool.setSelected([...src.cool.getSelected()]);
  tgt.cp.setSelected([...src.cp.getSelected()]);
  tgt.ton.setSelected([...src.ton.getSelected()]);
  tgt.brand.setSelected([...src.brand.getSelected()]);
}

function cascadeFilters(data,f){
  const dims=[
    {key:'cat',field:'c',ms:f.cat},
    {key:'cool',field:'h',ms:f.cool},
    {key:'cp',field:'cp',ms:f.cp},
    {key:'ton',field:'t',ms:f.ton,toString:true},
    {key:'brand',field:'b',ms:f.brand},
  ];
  dims.forEach(dim=>{
    let filtered=data;
    dims.forEach(other=>{
      if(other.key===dim.key)return;
      const sel=other.ms.getSelected();
      filtered=filtered.filter(r=>{
        const v=r[other.field];
        if(v==null)return true;
        return sel.has(other.toString?String(v):v);
      });
    });
    const avail=new Set();
    filtered.forEach(r=>{const v=r[dim.field];if(v!=null)avail.add(dim.toString?String(v):String(v));});
    dim.ms.updateAvailable(avail);
  });
}

// === GLOBAL STATE ============================================================
let GF, S4F, S5F, S6F, S7F, S8F, S9F;
let gfDate,s8Date;
const ST={alertDir:'all',s4q:'',s5q:'',s6q:'',s7q:'',s8q:'',s9q:'',skuStock:'all',stkDir:'all',s5agg:'avg',s6agg:'avg',expFilter:'all'};

function getCompareDates(){
  const sel=[...gfDate.getSelected()].sort();
  if(!sel.length) return {cur:LATEST_DATE,prev:null};
  const cur=sel[sel.length-1];
  if(sel.length===DATES.length){
    const idx=DATES.indexOf(cur);
    return {cur,prev:idx>0?DATES[idx-1]:null};
  }
  return {cur,prev:sel.length>=2?sel[sel.length-2]:null};
}

// === INIT ====================================================================
function init(){
  gfDate=new MS(document.getElementById('gf_date'),DATES,'Date',refreshGlobal);
  GF=makeFilters('gf',refreshGlobal);
  S4F=makeFilters('s4',renderS4);
  S5F=makeFilters('s5',renderS5);
  S6F=makeFilters('s6',renderS6);
  S7F=makeFilters('s7',renderS7);
  s8Date=new MS(document.getElementById('s8_date'),DATES,'Date',renderStock);
  S8F=makeFilters('s8',renderStock);
  S9F=makeFilters('s9',renderS9);

  const searchIds=[['s4_search','s4q',renderS4],['s5_search','s5q',renderS5],['s6_search','s6q',renderS6],['s7_search','s7q',renderS7],['s8_search','s8q',renderStock],['s9_search','s9q',renderS9]];
  searchIds.forEach(([id,key,fn])=>{
    let to=null;const el=document.getElementById(id);
    if(el) el.addEventListener('input',e=>{clearTimeout(to);to=setTimeout(()=>{ST[key]=e.target.value.toLowerCase().trim();fn();},150);});
  });

  document.querySelectorAll('.dir-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.dir-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');
    ST.alertDir=btn.dataset.dir;renderAlerts();
  }));

  document.querySelectorAll('.s5agg-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.s5agg-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-teal-700 text-white/g,'bg-gray-50 text-gray-600')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50 text-gray-600/g,'bg-teal-700 text-white');
    ST.s5agg=btn.dataset.agg;renderS5();
  }));
  document.querySelectorAll('.agg-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.agg-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-teal-700 text-white/g,'bg-gray-50 text-gray-600')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50 text-gray-600/g,'bg-teal-700 text-white');
    ST.s6agg=btn.dataset.agg;renderS6();
  }));

  document.querySelectorAll('.stock-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.stock-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');
    ST.skuStock=btn.dataset.val;renderS7();
  }));

  document.querySelectorAll('.stk-dir-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.stk-dir-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');
    ST.stkDir=btn.dataset.dir;renderStock();
  }));

  document.querySelectorAll('.exp-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.exp-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');
    ST.expFilter=btn.dataset.val;renderS9();
  }));

  const s8From=document.getElementById('s8_from'),s8To=document.getElementById('s8_to');
  DATES.forEach(d=>{s8From.add(new Option(d,d));s8To.add(new Option(d,d));});
  s8From.value=DATES.length>=2?DATES[DATES.length-2]:DATES[0];
  s8To.value=LATEST_DATE;
  s8From.addEventListener('change',renderStock);
  s8To.addEventListener('change',renderStock);

  document.getElementById('metaDate').textContent=LATEST_DATE;
  document.getElementById('metaPeriod').textContent=FIRST_DATE+' ~ '+LATEST_DATE+' ('+DATES.length+' days)';

  refreshGlobal();
}

// === GLOBAL REFRESH ==========================================================
function refreshGlobal(){
  const {cur,prev}=getCompareDates();
  const curData=applyF(DATA.filter(r=>r.d===cur),GF);
  const prevData=prev?applyF(DATA.filter(r=>r.d===prev),GF):[];
  document.getElementById('gf_count').textContent=curData.length+' SKUs';
  document.getElementById('gf_compare').textContent='Viewing: '+cur+(prev?' vs '+prev:'');
  document.getElementById('metaSku').textContent=curData.length;

  syncToSection(GF,S4F);syncToSection(GF,S5F);syncToSection(GF,S6F);syncToSection(GF,S7F);
  s8Date.setSelected([...gfDate.getSelected()]);syncToSection(GF,S8F);
  syncToSection(GF,S9F);

  const allCurDate=DATA.filter(r=>gfDate.getSelected().has(r.d));
  cascadeFilters(allCurDate,GF);

  renderKPIs(curData,prevData);renderAlerts();renderSkuStatus();
  renderS4();renderS5();renderS6();renderS7();renderStock();renderS9();
}

initSkuTabs();
function resetGlobal(){gfDate.reset();resetF(GF);refreshGlobal();}
function resetS4(){resetF(S4F);ST.s4q='';document.getElementById('s4_search').value='';renderS4();}
function resetS5(){resetF(S5F);ST.s5q='';ST.s5agg='avg';document.getElementById('s5_search').value='';
  document.querySelectorAll('.s5agg-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-teal-700 text-white/g,'bg-gray-50 text-gray-600');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50 text-gray-600/g,'bg-teal-700 text-white');}});renderS5();}
function resetS6(){resetF(S6F);ST.s6q='';ST.s6agg='avg';document.getElementById('s6_search').value='';
  document.querySelectorAll('.agg-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-teal-700 text-white/g,'bg-gray-50 text-gray-600');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50 text-gray-600/g,'bg-teal-700 text-white');}});renderS6();}
function resetS7(){resetF(S7F);ST.s7q='';ST.skuStock='all';document.getElementById('s7_search').value='';
  document.querySelectorAll('.stock-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');}});renderS7();}
function resetStock(){s8Date.reset();resetF(S8F);ST.s8q='';ST.stkDir='all';document.getElementById('s8_search').value='';
  document.getElementById('s8_from').value=DATES.length>=2?DATES[DATES.length-2]:DATES[0];
  document.getElementById('s8_to').value=LATEST_DATE;
  document.querySelectorAll('.stk-dir-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');}});renderStock();}
function resetS9(){resetF(S9F);ST.s9q='';ST.expFilter='all';document.getElementById('s9_search').value='';
  document.querySelectorAll('.exp-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');}});renderS9();}

// === SEC 1: KPIs =============================================================
function renderKPIs(lat,prev){
  const lm={};lat.forEach(r=>lm[r.s]=r.fp);const pm={};prev.forEach(r=>pm[r.s]=r.fp);
  let up=0,dn=0;Object.keys(lm).filter(s=>s in pm).forEach(s=>{const d=(lm[s]||0)-(pm[s]||0);if(d>0)up++;else if(d<0)dn++;});
  const nw=lat.filter(r=>!(r.s in pm)).length,rm=prev.filter(r=>!(r.s in lm)).length;
  const inStk=lat.filter(r=>r.stk!=null&&r.stk>0).length;
  const ad=lat.filter(r=>r.dr!=null);const avgD=ad.length?mean(ad.map(r=>r.dr)):null;
  const af=lat.filter(r=>r.fp!=null);const avgS=af.length?Math.round(mean(af.map(r=>r.fp))):null;
  const expCount=lat.filter(r=>r.exp).length;
  const cards=[
    {v:lat.length,l:'Total SKUs',c:'border-l-teal-700 bg-teal-50',vc:'text-teal-800'},
    {v:avgD!=null?(avgD*100).toFixed(1)+'%':'-',l:'Avg Discount',c:'border-l-amber-500 bg-amber-50',vc:'text-amber-700'},
    {v:'&#9650; '+up,l:'Price Up',c:'border-l-red-500 bg-red-50',vc:'text-red-600'},
    {v:'&#9660; '+dn,l:'Price Down',c:'border-l-green-500 bg-green-50',vc:'text-green-600'},
    {v:nw,l:'New SKUs',c:'border-l-blue-500 bg-blue-50',vc:'text-blue-600'},
    {v:rm,l:'Removed',c:'border-l-orange-500 bg-orange-50',vc:'text-orange-600'},
    {v:inStk+'/'+lat.length,l:'In Stock',c:'border-l-cyan-500 bg-cyan-50',vc:'text-cyan-600'},
    {v:expCount+'/'+lat.length,l:'Express',c:'border-l-purple-500 bg-purple-50',vc:'text-purple-700'},
  ];
  document.getElementById('kpiGrid').innerHTML=cards.map(c=>`<div class="rounded-lg border-l-4 ${c.c} p-3"><div class="text-xl font-bold ${c.vc}">${c.v}</div><div class="text-[10px] text-gray-500 mt-1 font-medium">${c.l}</div></div>`).join('');
}

// === SEC 2: ALERTS ===========================================================
const AC=[{k:'b',l:'Brand'},{k:'s',l:'Product'},{k:'m',l:'SKU'},{k:'c',l:'Category'},{k:'h',l:'Cooling'},{k:'cp',l:'Compressor'},{k:'ton',l:'Ton'},{k:'prev',l:'Prev',f:fmtSAR},{k:'curr',l:'Curr',f:fmtSAR},{k:'chg',l:'Change',f:fmtChg},{k:'chgPct',l:'Chg%',f:fmtPctR}];
function renderAlerts(){
  const {cur,prev}=getCompareDates();
  const latD=applyF(DATA.filter(r=>r.d===cur),GF);
  const prevD=prev?applyF(DATA.filter(r=>r.d===prev),GF):[];
  const lm={};latD.forEach(r=>lm[r.s]=r);const pm={};prevD.forEach(r=>pm[r.s]=r);
  let rows=[];
  Object.keys(lm).filter(s=>s in pm).forEach(s=>{
    const rn=lm[s],ro=pm[s],pn=rn.fp,po=ro.fp;
    if(pn==null||po==null)return;const chg=pn-po;if(Math.abs(chg)<1)return;
    rows.push({b:rn.b,s:rn.n,m:rn.m,c:rn.c,h:rn.h||'-',cp:rn.cp||'-',ton:rn.t!=null?rn.t.toFixed(1)+'T':'-',prev:po,curr:pn,chg,chgPct:po?chg/po*100:0,url:rn.url});
  });
  if(ST.alertDir==='up')rows=rows.filter(r=>r.chg>0);if(ST.alertDir==='down')rows=rows.filter(r=>r.chg<0);
  rows.sort((a,b)=>Math.abs(b.chg)-Math.abs(a.chg));
  const tbl=document.getElementById('tblAlert');
  tbl.querySelector('thead').innerHTML='<tr>'+AC.map((c,i)=>`<th onclick="sortTbl('tblAlert',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=rows.length?rows.map(r=>'<tr>'+AC.map(c=>{let v=c.f?c.f(r[c.k]):(r[c.k]??'-');let cls='';if((c.k==='chg'||c.k==='chgPct')&&r.chg!=null)cls=r.chg>0?'up-cell':'dn-cell';if(c.k==='s'&&r.url)v=`<a href="${r.url}" target="_blank" class="text-blue-600 hover:underline">${v}</a>`;return`<td class="${cls}">${v}</td>`;}).join('')+'</tr>').join(''):'<tr><td colspan="11" class="text-center text-gray-400 py-6">No changes</td></tr>';
}

// ═══ SEC 3: SKU STATUS TRACKER ══════════════════════════════════════════════
// New        : 역대 첫 등장
// Reactive   : 2일+ 부재 후 복귀
// Temp OOS   : 연속 부재 1~13 스크래핑일 (재고 부족 → 영업 챌린지)
// Discontinued: 연속 부재 14+ 스크래핑일 (단종 가능성)

// 날짜별 카테고리 카운트 (런 품질 체크용)
const CAT_COUNT_BY_DATE=(()=>{
  const m={};
  DATA.forEach(r=>{if(!m[r.d])m[r.d]={};m[r.d][r.c]=(m[r.d][r.c]||0)+1;});
  return m;
})();

function checkRunQuality(date){
  const idx=DATES.indexOf(date);
  if(idx<=0)return{ok:true,reasons:[]};
  const baselineDts=DATES.slice(Math.max(0,idx-14),idx);
  const dayCounts=CAT_COUNT_BY_DATE[date]||{};
  const totalToday=Object.values(dayCounts).reduce((a,b)=>a+b,0);
  const reasons=[];
  const baseTotals=baselineDts.map(d=>Object.values(CAT_COUNT_BY_DATE[d]||{}).reduce((a,b)=>a+b,0)).sort((a,b)=>a-b);
  if(baseTotals.length>0){
    const med=baseTotals[Math.floor(baseTotals.length/2)];
    if(med>0&&totalToday/med<0.85)reasons.push(`총 수집량 급감 (${totalToday}/${med}건, ${Math.round(totalToday/med*100)}%)`);
  }
  const knownCats=new Set();
  baselineDts.forEach(d=>Object.keys(CAT_COUNT_BY_DATE[d]||{}).forEach(c=>knownCats.add(c)));
  knownCats.forEach(cat=>{
    const hits=baselineDts.filter(d=>(CAT_COUNT_BY_DATE[d]||{})[cat]>0).length;
    if(hits>=3&&!(dayCounts[cat]>0))reasons.push(`'${cat}' 카테고리 완전 누락`);
  });
  return{ok:reasons.length===0,reasons};
}

// 탭 상태
let ACTIVE_SKU_TAB='new';

// 탭별 설명
const TAB_DESC={
  new:'역대 처음 등장한 신규 SKU',
  reactive:'단종/품절 후 재입고된 SKU — 공급 정상화 확인',
  temp_disc:'최근 1~13일 연속 부재 — 일시 재고 부족 의심 → 영업 챌린지 검토',
  disc:'14일+ 연속 부재 — 단종 가능성 높음 → 대체 모델 파악'
};

// 현재 최신 날짜의 런 품질 (전체 섹션 상단 경고용)
const _latestQ=checkRunQuality(LATEST_DATE);

function renderSkuStatus(){
  // 카운트 업데이트
  const newSkus=Object.entries(SKU_STATUS).filter(([,v])=>v.st==='new');
  const reactiveSkus=Object.entries(SKU_STATUS).filter(([,v])=>v.st==='reactive');
  const tempDiscSkus=DISC_RECORDS.filter(r=>r.st==='temp_disc');
  const discSkus=DISC_RECORDS.filter(r=>r.st==='disc');
  document.getElementById('cntNew').textContent=newSkus.length;
  document.getElementById('cntReactive').textContent=reactiveSkus.length;
  document.getElementById('cntTempDisc').textContent=tempDiscSkus.length;
  document.getElementById('cntDisc').textContent=discSkus.length;

  // 런 품질 경고 (최신 날짜 이상 시)
  const warnEl=document.getElementById('skuRunWarn');
  if(!_latestQ.ok){
    warnEl.innerHTML=`<div class="flex items-start gap-2 bg-amber-50 border border-amber-300 rounded-lg p-2.5 mb-2 text-[10px] text-amber-800"><span class="text-amber-500 text-sm leading-none mt-0.5">⚠</span><div><div class="font-bold mb-0.5">최신 수집 이상 — Temp OOS/Disc 목록 신뢰도 낮음</div>${_latestQ.reasons.map(r=>`<div>${r}</div>`).join('')}</div></div>`;
  } else { warnEl.innerHTML=''; }

  // 탭 설명
  document.getElementById('skuTabDesc').textContent=TAB_DESC[ACTIVE_SKU_TAB]||'';

  // 카드 렌더링
  const latestData=DATA.filter(r=>r.d===LATEST_DATE);
  const latestMap={};latestData.forEach(r=>latestMap[r.s]=r);

  function skuCard(r,cfg){
    const abLabel=r.ab>0?`<span class="text-[9px] font-bold px-1.5 py-0.5 rounded-full ${cfg.badgeCls}">${r.ab}일 부재</span>`:'';
    const gbLabel=r.gb>0?`<span class="text-[9px] text-gray-400">(${r.gb}일 만에 복귀)</span>`:'';
    const nameHtml=r.url?`<a href="${r.url}" target="_blank" class="text-blue-600 hover:underline">${r.n||r.s}</a>`:(r.n||r.s);
    return `<div class="border ${cfg.border} ${cfg.bg} rounded-lg p-2.5 flex justify-between items-start gap-2">
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="text-xs font-bold" style="color:${colorOf(r.b)}">${r.b||'Unknown'}</span>
          <span class="text-[10px] text-gray-400">${r.m||''}</span>
          ${abLabel}${gbLabel}
        </div>
        <div class="text-[11px] mt-0.5 truncate">${nameHtml}</div>
        <div class="text-[10px] text-gray-400 mt-0.5">${r.c||''} &middot; ${r.t?r.t.toFixed(1)+'T':''} &middot; ${r.h||''} &middot; 마지막: ${r.ls||''}</div>
      </div>
      <div class="text-sm font-bold text-gray-700 whitespace-nowrap">${fmtSAR(r.fp)} SAR</div>
    </div>`;
  }

  let html='';
  if(ACTIVE_SKU_TAB==='new'){
    const recs=newSkus.map(([sku])=>latestMap[sku]).filter(Boolean);
    html=recs.length?recs.map(r=>skuCard({...r,ab:0,gb:0,ls:LATEST_DATE},{border:'border-green-200',bg:'bg-green-50',badgeCls:''})).join(''):'<p class="text-xs text-gray-400 py-4 text-center">신규 SKU 없음</p>';
  } else if(ACTIVE_SKU_TAB==='reactive'){
    const recs=reactiveSkus.map(([sku,st])=>{const d=latestMap[sku];return d?{...d,...st}:null;}).filter(Boolean);
    html=recs.length?recs.map(r=>skuCard(r,{border:'border-blue-200',bg:'bg-blue-50',badgeCls:'bg-blue-100 text-blue-700'})).join(''):'<p class="text-xs text-gray-400 py-4 text-center">복귀 SKU 없음</p>';
  } else if(ACTIVE_SKU_TAB==='temp_disc'){
    const sorted=tempDiscSkus.slice().sort((a,b)=>b.ab-a.ab);
    html=sorted.length?sorted.map(r=>skuCard(r,{border:'border-amber-200',bg:'bg-amber-50',badgeCls:'bg-amber-100 text-amber-700'})).join(''):'<p class="text-xs text-gray-400 py-4 text-center">Temp OOS 없음</p>';
  } else {
    const sorted=discSkus.slice().sort((a,b)=>b.ab-a.ab);
    html=sorted.length?sorted.map(r=>skuCard(r,{border:'border-red-200',bg:'bg-red-50',badgeCls:'bg-red-100 text-red-700'})).join(''):'<p class="text-xs text-gray-400 py-4 text-center">Discontinued 없음</p>';
  }
  document.getElementById('skuCards').innerHTML=html;
}

// 탭 클릭 이벤트 (init에서 등록)
function initSkuTabs(){
  document.querySelectorAll('.sku-tab').forEach(btn=>{
    btn.addEventListener('click',()=>{
      document.querySelectorAll('.sku-tab').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      ACTIVE_SKU_TAB=btn.dataset.tab;
      renderSkuStatus();
    });
  });
}

// === SEC 4: CATEGORY KPI =====================================================
const CK=[{l:'Type',k:'type'},{l:'Segment',k:'label'},{l:'SKUs',k:'cnt'},{l:'Avg Sale',k:'avgP',f:fmtSAR},{l:'Avg Original',k:'avgStd',f:fmtSAR},{l:'Avg Disc %',k:'avgDisc',f:fmtPctR},{l:'In Stock',k:'inStk'},{l:'Express',k:'expCnt'},{l:'Avg Disc SR',k:'avgDSR',f:fmtSAR}];
const TYPE_BADGE={cat:'<span class="type-badge type-cat">Category</span>',cool:'<span class="type-badge type-cool">Cooling</span>',cp:'<span class="type-badge type-cp">Compressor</span>',ton:'<span class="type-badge type-ton">Ton</span>'};
const CAT_ORDER=['Split AC','Window AC','Standing AC','Floor Standing AC','Portable AC'];
const COOL_ORDER=['Cold Only','Heat & Cool','Hot & Cold'];
const CP_ORDER=['Inverter','Rotary'];

function segKPI(data){
  const cnt=new Set(data.map(r=>r.s)).size;
  const pArr=data.filter(r=>r.fp!=null).map(r=>r.fp);const avgP=pArr.length?Math.round(mean(pArr)):null;
  const sps=data.filter(r=>r.sp!=null).map(r=>r.sp);const avgStd=sps.length?Math.round(mean(sps)):null;
  const drs=data.filter(r=>r.dr!=null).map(r=>r.dr*100);const avgDisc=drs.length?Math.round(mean(drs)*10)/10:null;
  const inStk=data.filter(r=>r.stk!=null&&r.stk>0).length;
  const expCnt=data.filter(r=>r.exp).length;
  const dsrs=data.filter(r=>r.dsr!=null).map(r=>r.dsr);const avgDSR=dsrs.length?Math.round(mean(dsrs)):null;
  return{cnt,avgP,avgStd,avgDisc,inStk,expCnt,avgDSR};
}

function renderS4(){
  const {cur}=getCompareDates();
  cascadeFilters(DATA.filter(r=>r.d===cur),S4F);
  let lat=applyF(DATA.filter(r=>r.d===cur),S4F);
  if(ST.s4q)lat=lat.filter(r=>searchMatch(r,ST.s4q));
  const rows=[];
  const cats=CAT_ORDER.filter(c=>[...new Set(lat.map(r=>r.c))].includes(c));
  cats.forEach(cat=>{
    const catD=lat.filter(r=>r.c===cat);if(!catD.length)return;
    rows.push({level:'cat',type:'cat',label:cat,...segKPI(catD)});
    const cools=COOL_ORDER.filter(c=>[...new Set(catD.map(r=>r.h))].includes(c));
    cools.forEach(cool=>{
      const coolD=catD.filter(r=>r.h===cool);if(!coolD.length)return;
      rows.push({level:'cool',type:'cool',label:cool,...segKPI(coolD)});
      const cps=CP_ORDER.filter(i=>[...new Set(coolD.map(r=>r.cp))].includes(i));
      cps.forEach(cp=>{
        const cpD=coolD.filter(r=>r.cp===cp);if(!cpD.length)return;
        rows.push({level:'cp',type:'cp',label:cp,...segKPI(cpD)});
        const tons=[...new Set(cpD.map(r=>r.t))].filter(Boolean).sort((a,b)=>a-b);
        tons.forEach(t=>{
          const tD=cpD.filter(r=>r.t===t);if(!tD.length)return;
          rows.push({level:'ton',type:'ton',label:t.toFixed(1)+'T',...segKPI(tD)});
        });
      });
    });
  });
  rows.push({level:'cat',type:'cat',label:'TOTAL',...segKPI(lat)});
  const tbl=document.getElementById('tblCatKPI');
  tbl.querySelector('thead').innerHTML='<tr>'+CK.map((c,i)=>`<th onclick="sortTbl('tblCatKPI',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=rows.map(r=>{
    return`<tr class="level-${r.level}">`+CK.map(c=>{
      let v;if(c.k==='type')v=TYPE_BADGE[r.type]||'';else if(c.k==='label')v=r.label;else v=c.f?c.f(r[c.k]):(r[c.k]??'-');
      return`<td>${v}</td>`;
    }).join('')+'</tr>';
  }).join('');
}

// === SEC 5: BRAND COMPARE ====================================================
let brandChart=null;
function renderS5(){
  const {cur}=getCompareDates();cascadeFilters(DATA.filter(r=>r.d===cur),S5F);
  let lat=applyF(DATA.filter(r=>r.d===cur),S5F);if(ST.s5q)lat=lat.filter(r=>searchMatch(r,ST.s5q));
  const aggFn5=ST.s5agg==='min'?(arr=>Math.round(Math.min(...arr))):(arr=>Math.round(mean(arr)));
  const aggLabel5=ST.s5agg==='min'?'Min Price':'Avg Price';
  const bAvg={};lat.forEach(r=>{if(r.fp==null)return;if(!bAvg[r.b])bAvg[r.b]=[];bAvg[r.b].push(r.fp);});
  let items=Object.entries(bAvg).map(([b,v])=>({b,avg:aggFn5(v)})).sort((a,b)=>a.avg-b.avg);
  const labels=items.map(x=>x.b),vals=items.map(x=>x.avg),bg=labels.map(b=>colorOf(b));
  const ctx=document.getElementById('brandBarChart').getContext('2d');
  if(brandChart)brandChart.destroy();
  brandChart=new Chart(ctx,{type:'bar',data:{labels,datasets:[{label:aggLabel5,data:vals,backgroundColor:bg,borderColor:bg,borderWidth:1}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>'SAR '+fmtSAR(c.raw)}},datalabels:{display:true,anchor:'end',align:'right',color:'#134e4a',font:{size:10,weight:'bold'},formatter:v=>fmtSAR(v),clip:false}},scales:{x:{ticks:{callback:v=>fmtSAR(v)},grid:{color:'#f0f0f0'},suggestedMax:vals.length?Math.max(...vals)*1.15:undefined},y:{ticks:{font:{size:10}}}}}});
  // Segment table
  const segs=[];const bList=[...new Set(lat.map(r=>r.b))].filter(Boolean).sort();
  const cats=[...new Set(lat.map(r=>r.c))].filter(x=>x!=null).sort();
  const mktLabel5=ST.s5agg==='min'?'Mkt Min':'Mkt Avg';
  cats.forEach(cat=>{const cD=lat.filter(r=>r.c===cat);
    [...new Set(cD.map(r=>r.h))].filter(x=>x!=null).sort().forEach(cool=>{const coD=cD.filter(r=>r.h===cool);
      [...new Set(coD.map(r=>r.t))].filter(x=>x!=null&&!isNaN(x)).sort((a,b)=>a-b).forEach(t=>{const tD=coD.filter(r=>r.t===t);if(!tD.length)return;
        const seg=(cat||'')+' / '+(cool||'')+' / '+Number(t).toFixed(1)+'T';
        const row={seg};const prices=[];
        bList.forEach(b=>{const bD=tD.filter(r=>r.b===b&&r.fp!=null);const v=bD.length?aggFn5(bD.map(r=>r.fp)):null;row[b]=v;if(v!=null)prices.push(v);});
        row['Mkt']=prices.length?aggFn5(prices):null;
        segs.push(row);
      });});});
  const allC=['seg',...bList,'Mkt'],allH=['Segment',...bList,mktLabel5];
  const tbl=document.getElementById('tblBrandSeg');
  tbl.querySelector('thead').innerHTML='<tr>'+allH.map((h,i)=>`<th onclick="sortTbl('tblBrandSeg',${i})">${h}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=segs.length?segs.map(r=>'<tr>'+allC.map(k=>`<td>${k==='seg'?r[k]:(r[k]!=null?fmtSAR(r[k]):'-')}</td>`).join('')+'</tr>').join(''):'<tr><td colspan="99" class="text-center text-gray-400 py-4">No data</td></tr>';
}

// === SEC 6: TREND ============================================================
let trendChartObj=null;
function renderS6(){
  const {cur}=getCompareDates();cascadeFilters(DATA.filter(r=>r.d===cur),S6F);
  const q=ST.s6q;
  const aggFn6=ST.s6agg==='min'?(arr=>Math.round(Math.min(...arr))):(arr=>Math.round(mean(arr)));
  const mktLabel6=ST.s6agg==='min'?'Market Min':'Market Avg';
  let datasets=[];
  const mkt=DATES.map(d=>{let dd=applyF(DATA.filter(r=>r.d===d),S6F);if(q)dd=dd.filter(r=>searchMatch(r,q));dd=dd.filter(r=>r.fp!=null);return dd.length?aggFn6(dd.map(r=>r.fp)):null;});
  datasets.push({label:mktLabel6,data:mkt,borderColor:'#6b7280',borderWidth:2,borderDash:[6,3],pointRadius:2,tension:.3,fill:false});
  const bSet=S6F.brand.getSelected();
  [...bSet].forEach(br=>{
    const vals=DATES.map(d=>{let dd=applyF(DATA.filter(r=>r.d===d&&r.b===br),S6F);if(q)dd=dd.filter(r=>searchMatch(r,q));dd=dd.filter(r=>r.fp!=null);return dd.length?aggFn6(dd.map(r=>r.fp)):null;});
    if(vals.every(v=>v===null))return;const c=colorOf(br);
    datasets.push({label:br,data:vals,borderColor:c,backgroundColor:alphaC(c,.08),borderWidth:1.5,pointRadius:2,tension:.3,fill:false,spanGaps:true});
  });
  const ctx=document.getElementById('trendChart').getContext('2d');
  if(trendChartObj)trendChartObj.destroy();
  trendChartObj=new Chart(ctx,{type:'line',data:{labels:DATES,datasets},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},layout:{padding:{right:90}},plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:10}}},tooltip:{callbacks:{label:c=>c.dataset.label+': SAR '+fmtSAR(c.raw)}},datalabels:{display:false}},scales:{x:{ticks:{font:{size:10},maxRotation:45},grid:{color:'#f5f5f5'}},y:{ticks:{callback:v=>fmtSAR(v)},grid:{color:'#f5f5f5'}}}},plugins:[{id:'endLabels',afterDatasetsDraw(chart){const ctx2=chart.ctx;chart.data.datasets.forEach((ds,i)=>{const meta=chart.getDatasetMeta(i);if(!meta.visible)return;for(let j=meta.data.length-1;j>=0;j--){const pt=meta.data[j];if(pt&&ds.data[j]!=null){ctx2.save();ctx2.font='bold 10px Inter,sans-serif';ctx2.fillStyle=ds.borderColor||'#333';ctx2.textBaseline='middle';const lbl=ds.label.length>18?ds.label.substring(0,18)+'..':ds.label;ctx2.fillText(lbl,pt.x+6,pt.y);ctx2.restore();break;}}});}}]});
}

// === SEC 7: FULL SKU =========================================================
const SK=[{k:'b',l:'Brand'},{k:'n',l:'Product'},{k:'m',l:'SKU'},{k:'c',l:'Category'},{k:'h',l:'Cooling'},{k:'cp',l:'Compressor'},{k:'t',l:'Ton',f:v=>v!=null?v.toFixed(1)+'T':'-'},{k:'sp',l:'Original',f:fmtSAR},{k:'fp',l:'Sale',f:fmtSAR},{k:'dsr',l:'Disc SR',f:fmtSAR},{k:'dr',l:'Disc%',f:fmtPct},{k:'stk',l:'Stock',f:v=>v!=null?v:'-'},{k:'exp',l:'Express',f:v=>v?'Yes':'No'}];
function renderS7(){
  const {cur}=getCompareDates();cascadeFilters(DATA.filter(r=>r.d===cur),S7F);
  let lat=applyF(DATA.filter(r=>r.d===cur),S7F);
  if(ST.s7q)lat=lat.filter(r=>searchMatch(r,ST.s7q));
  if(ST.skuStock==='in')lat=lat.filter(r=>r.stk!=null&&r.stk>0);
  if(ST.skuStock==='out')lat=lat.filter(r=>r.stk==null||r.stk<=0);
  document.getElementById('skuDateLabel').textContent='('+cur+')';
  document.getElementById('skuCount').textContent=lat.length+' SKUs';
  const tbl=document.getElementById('tblSku');
  tbl.querySelector('thead').innerHTML='<tr>'+SK.map((c,i)=>`<th onclick="sortTbl('tblSku',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=lat.length?lat.map(r=>'<tr>'+SK.map(c=>{let v=c.f?c.f(r[c.k]):(r[c.k]??'-');if(c.k==='n'&&r.url)v=`<a href="${r.url}" target="_blank" class="text-blue-600 hover:underline">${v}</a>`;if(c.k==='stk'){const st=stkStatus(r.stk);v=`<span class="stk-badge ${st.cls}">${v}</span>`;}if(c.k==='exp')v=r.exp?'<span class="exp-badge exp-yes">Yes</span>':'<span class="exp-badge exp-no">No</span>';return`<td>${v}</td>`;}).join('')+'</tr>').join(''):'<tr><td colspan="13" class="text-center text-gray-400 py-6">No data</td></tr>';
}

function downloadExcel(){
  const {cur}=getCompareDates();
  let lat=applyF(DATA.filter(r=>r.d===cur),S7F);
  if(ST.s7q)lat=lat.filter(r=>searchMatch(r,ST.s7q));
  if(ST.skuStock==='in')lat=lat.filter(r=>r.stk!=null&&r.stk>0);
  if(ST.skuStock==='out')lat=lat.filter(r=>r.stk==null||r.stk<=0);
  const rows=lat.map(r=>({Brand:r.b,Product:r.n,SKU:r.m,Category:r.c,Cooling:r.h,Compressor:r.cp,Ton:r.t,'Original (SR)':r.sp,'Sale (SR)':r.fp,'Discount (SR)':r.dsr,'Discount %':r.dr!=null?(r.dr*100).toFixed(1)+'%':'',Stock:r.stk,Express:r.exp?'Yes':'No',URL:r.url}));
  const ws=XLSX.utils.json_to_sheet(rows);const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'SKUs');
  XLSX.writeFile(wb,'Tamkeen_AC_'+cur+'.xlsx');
}

// === SEC 8: STOCK ============================================================
let stockTrendChart=null,stockBrandBarChart=null,stockCatDonutChart=null;
function renderStock(){
  const selDates=[...s8Date.getSelected()].sort();
  const latDate=selDates.length?selDates[selDates.length-1]:LATEST_DATE;
  cascadeFilters(DATA.filter(r=>s8Date.getSelected().has(r.d)),S8F);
  let lat=applyF(DATA.filter(r=>r.d===latDate),S8F);
  if(ST.s8q)lat=lat.filter(r=>searchMatch(r,ST.s8q));
  document.getElementById('s8_compare').textContent='Stock as of: '+latDate;

  // KPIs
  const total=lat.length;const inStk=lat.filter(r=>r.stk!=null&&r.stk>0).length;
  const outStk=lat.filter(r=>r.stk==null||r.stk<=0).length;
  const totalUnits=lat.reduce((s,r)=>s+(r.stk||0),0);
  const avgStk=total?Math.round(totalUnits/total):0;
  const lowStk=lat.filter(r=>r.stk!=null&&r.stk>0&&r.stk<=15).length;
  const sCards=[
    {v:total,l:'Total SKUs',c:'border-l-teal-700 bg-teal-50',vc:'text-teal-800'},
    {v:inStk,l:'In Stock',c:'border-l-green-500 bg-green-50',vc:'text-green-600'},
    {v:outStk,l:'Out of Stock',c:'border-l-red-500 bg-red-50',vc:'text-red-600'},
    {v:totalUnits.toLocaleString(),l:'Total Units',c:'border-l-blue-500 bg-blue-50',vc:'text-blue-600'},
    {v:avgStk,l:'Avg Stock/SKU',c:'border-l-purple-500 bg-purple-50',vc:'text-purple-600'},
    {v:lowStk,l:'Low Stock',c:'border-l-amber-500 bg-amber-50',vc:'text-amber-600'},
  ];
  document.getElementById('stockKpiGrid').innerHTML=sCards.map(c=>`<div class="rounded-lg border-l-4 ${c.c} p-3"><div class="text-xl font-bold ${c.vc}">${c.v}</div><div class="text-[10px] text-gray-500 mt-1 font-medium">${c.l}</div></div>`).join('');

  // Stock Trend
  const trendData=DATES.map(d=>{const dd=applyF(DATA.filter(r=>r.d===d),S8F);return dd.reduce((s,r)=>s+(r.stk||0),0);});
  const ctx1=document.getElementById('stockTrendChart').getContext('2d');
  if(stockTrendChart)stockTrendChart.destroy();
  stockTrendChart=new Chart(ctx1,{type:'line',data:{labels:DATES,datasets:[{label:'Total Stock',data:trendData,borderColor:'#0d9488',backgroundColor:'rgba(13,148,136,.1)',borderWidth:2,pointRadius:3,tension:.3,fill:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},datalabels:{display:false}},scales:{x:{ticks:{font:{size:10},maxRotation:45}},y:{ticks:{callback:v=>v.toLocaleString()}}}}});

  // Stock Change
  const fromDate=document.getElementById('s8_from').value;
  const toDate=document.getElementById('s8_to').value;
  const fromD=applyF(DATA.filter(r=>r.d===fromDate),S8F);
  const toD=applyF(DATA.filter(r=>r.d===toDate),S8F);
  const fm={};fromD.forEach(r=>fm[r.s]=r);const tm={};toD.forEach(r=>tm[r.s]=r);
  const allSKUs=new Set([...Object.keys(fm),...Object.keys(tm)]);
  let changes=[];
  allSKUs.forEach(s=>{
    const fr=fm[s],tr=tm[s];
    const fStk=fr?fr.stk:null,tStk=tr?tr.stk:null;
    const chg=(tStk||0)-(fStk||0);
    if(chg===0&&fStk===tStk)return;
    const r=tr||fr;
    changes.push({b:r.b,n:r.n,m:r.m,c:r.c,from:fStk!=null?fStk:'-',to:tStk!=null?tStk:'-',chg,newOut:fStk>0&&(tStk==null||tStk<=0)});
  });
  if(ST.stkDir==='inc')changes=changes.filter(r=>r.chg>0);
  if(ST.stkDir==='dec')changes=changes.filter(r=>r.chg<0);
  if(ST.stkDir==='out')changes=changes.filter(r=>r.newOut);
  changes.sort((a,b)=>Math.abs(b.chg)-Math.abs(a.chg));
  document.getElementById('s8_chgCount').textContent=changes.length+' changes';

  const stCols=[{k:'b',l:'Brand'},{k:'n',l:'Product'},{k:'m',l:'SKU'},{k:'c',l:'Category'},{k:'from',l:'From'},{k:'to',l:'To'},{k:'chg',l:'Change'}];
  const stbl=document.getElementById('tblStockAlert');
  stbl.querySelector('thead').innerHTML='<tr>'+stCols.map((c,i)=>`<th onclick="sortTbl('tblStockAlert',${i})">${c.l}</th>`).join('')+'</tr>';
  stbl.querySelector('tbody').innerHTML=changes.length?changes.map(r=>'<tr>'+stCols.map(c=>{
    let v=r[c.k]??'-';let cls='';
    if(c.k==='chg'){v=fmtChg(r.chg);cls=r.chg>0?'dn-cell':'up-cell';}
    return`<td class="${cls}">${v}</td>`;}).join('')+'</tr>').join(''):'<tr><td colspan="7" class="text-center text-gray-400 py-4">No changes</td></tr>';

  // Brand bar chart
  const brandStk={};lat.forEach(r=>{if(!brandStk[r.b])brandStk[r.b]=0;brandStk[r.b]+=(r.stk||0);});
  const bItems=Object.entries(brandStk).sort((a,b)=>b[1]-a[1]);
  const ctx2=document.getElementById('stockBrandBar').getContext('2d');
  if(stockBrandBarChart)stockBrandBarChart.destroy();
  stockBrandBarChart=new Chart(ctx2,{type:'bar',data:{labels:bItems.map(x=>x[0]),datasets:[{label:'Stock Units',data:bItems.map(x=>x[1]),backgroundColor:bItems.map(x=>colorOf(x[0]))}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},datalabels:{display:true,anchor:'end',align:'right',font:{size:10,weight:'bold'},formatter:v=>v.toLocaleString(),clip:false}},scales:{x:{ticks:{callback:v=>v.toLocaleString()}},y:{ticks:{font:{size:10}}}}}});

  // Category donut
  const catStk={};lat.forEach(r=>{if(!catStk[r.c])catStk[r.c]=0;catStk[r.c]+=(r.stk||0);});
  const cItems=Object.entries(catStk).sort((a,b)=>b[1]-a[1]);
  const donutColors=['#0d9488','#f97316','#10b981','#8b5cf6','#f43f5e'];
  const ctx3=document.getElementById('stockCatDonut').getContext('2d');
  if(stockCatDonutChart)stockCatDonutChart.destroy();
  stockCatDonutChart=new Chart(ctx3,{type:'doughnut',data:{labels:cItems.map(x=>x[0]),datasets:[{data:cItems.map(x=>x[1]),backgroundColor:donutColors.slice(0,cItems.length)}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}},datalabels:{display:true,color:'#fff',font:{size:11,weight:'bold'},formatter:(v,ctx)=>{const sum=ctx.dataset.data.reduce((a,b)=>a+b,0);return sum?(v/sum*100).toFixed(0)+'%':'';}}}}});
}

// === SEC 9: DELIVERY =========================================================
let deliveryBrandBarChart=null,deliveryCatDonutChart=null;
function renderS9(){
  const {cur}=getCompareDates();
  cascadeFilters(DATA.filter(r=>r.d===cur),S9F);
  let lat=applyF(DATA.filter(r=>r.d===cur),S9F);
  if(ST.s9q)lat=lat.filter(r=>searchMatch(r,ST.s9q));
  if(ST.expFilter==='yes')lat=lat.filter(r=>r.exp);
  if(ST.expFilter==='no')lat=lat.filter(r=>!r.exp);

  // KPIs
  const total=lat.length;
  const expYes=lat.filter(r=>r.exp).length;
  const expNo=lat.filter(r=>!r.exp).length;
  const expPct=total?(expYes/total*100).toFixed(1)+'%':'0%';
  const dCards=[
    {v:total,l:'Total SKUs',c:'border-l-teal-700 bg-teal-50',vc:'text-teal-800'},
    {v:expYes,l:'Express Available',c:'border-l-green-500 bg-green-50',vc:'text-green-600'},
    {v:expNo,l:'No Express',c:'border-l-red-500 bg-red-50',vc:'text-red-600'},
    {v:expPct,l:'Express Rate',c:'border-l-blue-500 bg-blue-50',vc:'text-blue-600'},
  ];
  document.getElementById('deliveryKpiGrid').innerHTML=dCards.map(c=>`<div class="rounded-lg border-l-4 ${c.c} p-3"><div class="text-xl font-bold ${c.vc}">${c.v}</div><div class="text-[10px] text-gray-500 mt-1 font-medium">${c.l}</div></div>`).join('');
  document.getElementById('s9_count').textContent=lat.length+' SKUs';

  // Brand bar: express count per brand
  const brandExp={};lat.forEach(r=>{if(!brandExp[r.b])brandExp[r.b]={yes:0,no:0};if(r.exp)brandExp[r.b].yes++;else brandExp[r.b].no++;});
  const bItems=Object.entries(brandExp).sort((a,b)=>(b[1].yes+b[1].no)-(a[1].yes+a[1].no));
  const ctx2=document.getElementById('deliveryBrandBar').getContext('2d');
  if(deliveryBrandBarChart)deliveryBrandBarChart.destroy();
  deliveryBrandBarChart=new Chart(ctx2,{type:'bar',data:{labels:bItems.map(x=>x[0]),datasets:[
    {label:'Express',data:bItems.map(x=>x[1].yes),backgroundColor:'#10b981'},
    {label:'No Express',data:bItems.map(x=>x[1].no),backgroundColor:'#f87171'}
  ]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}},datalabels:{display:true,font:{size:9,weight:'bold'},formatter:v=>v||'',clip:false}},scales:{x:{stacked:true,ticks:{stepSize:1}},y:{stacked:true,ticks:{font:{size:10}}}}}});

  // Category donut: express distribution
  const catExp={};lat.filter(r=>r.exp).forEach(r=>{if(!catExp[r.c])catExp[r.c]=0;catExp[r.c]++;});
  const cItems=Object.entries(catExp).sort((a,b)=>b[1]-a[1]);
  const donutColors=['#0d9488','#f97316','#10b981','#8b5cf6','#f43f5e'];
  const ctx3=document.getElementById('deliveryCatDonut').getContext('2d');
  if(deliveryCatDonutChart)deliveryCatDonutChart.destroy();
  deliveryCatDonutChart=new Chart(ctx3,{type:'doughnut',data:{labels:cItems.map(x=>x[0]),datasets:[{data:cItems.map(x=>x[1]),backgroundColor:donutColors.slice(0,cItems.length)}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}},datalabels:{display:true,color:'#fff',font:{size:11,weight:'bold'},formatter:(v,ctx)=>{const sum=ctx.dataset.data.reduce((a,b)=>a+b,0);return sum?(v/sum*100).toFixed(0)+'%':'';}}}}});

  // Delivery table
  const dlCols=[{k:'b',l:'Brand'},{k:'n',l:'Product'},{k:'m',l:'SKU'},{k:'c',l:'Category'},{k:'h',l:'Cooling'},{k:'cp',l:'Compressor'},{k:'t',l:'Ton',f:v=>v!=null?v.toFixed(1)+'T':'-'},{k:'fp',l:'Sale',f:fmtSAR},{k:'stk',l:'Stock',f:v=>v!=null?v:'-'},{k:'exp',l:'Express',f:v=>v?'Yes':'No'}];
  const tbl=document.getElementById('tblDelivery');
  tbl.querySelector('thead').innerHTML='<tr>'+dlCols.map((c,i)=>`<th onclick="sortTbl('tblDelivery',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=lat.length?lat.map(r=>'<tr>'+dlCols.map(c=>{let v=c.f?c.f(r[c.k]):(r[c.k]??'-');if(c.k==='n'&&r.url)v=`<a href="${r.url}" target="_blank" class="text-blue-600 hover:underline">${v}</a>`;if(c.k==='stk'){const st=stkStatus(r.stk);v=`<span class="stk-badge ${st.cls}">${v}</span>`;}if(c.k==='exp')v=r.exp?'<span class="exp-badge exp-yes">Yes</span>':'<span class="exp-badge exp-no">No</span>';return`<td>${v}</td>`;}).join('')+'</tr>').join(''):'<tr><td colspan="10" class="text-center text-gray-400 py-4">No data</td></tr>';
}

// === BOOT ====================================================================
document.addEventListener('DOMContentLoaded',init);
</script>
"""

# == Assemble & Write ==========================================================
html = HTML_HEAD + HTML_BODY.replace('GENERATED_AT', generated_at) + HTML_DATA + HTML_LOGIC + "</body></html>"
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(html)
size_kb = os.path.getsize(OUTPUT_FILE) / 1024
print(f"\n✅ Dashboard saved: {OUTPUT_FILE}")
print(f"   Size: {size_kb:.0f} KB")
print(f"   Data: {len(records):,} records, {len(dates_list)} dates, {len(brands_list)} brands")

# ── GitHub Pages Deploy ────────────────────────────────────────────────────────
DEPLOY_DIR = os.path.join(os.path.expanduser("~"), "tmp_deploy_tamkeen_dashboard")
if os.path.isdir(os.path.join(DEPLOY_DIR, ".git")):
    shutil.copy2(OUTPUT_FILE, os.path.join(DEPLOY_DIR, "index.html"))
    subprocess.run(["git", "add", "index.html"], cwd=DEPLOY_DIR)
    subprocess.run(["git", "commit", "-m", f"Update dashboard {generated_at}"], cwd=DEPLOY_DIR)
    result = subprocess.run(["git", "push"], cwd=DEPLOY_DIR)
    if result.returncode != 0:
        subprocess.run(["git", "pull", "--rebase"], cwd=DEPLOY_DIR)
        result = subprocess.run(["git", "push"], cwd=DEPLOY_DIR)
    if result.returncode == 0:
        print("\n🚀 Deployed: https://perfectjjong.github.io/tamkeen-ac-dashboard/")
    else:
        print("\n[WARN] Git push failed. Check deploy directory.")
else:
    print(f"\n[SKIP] Deploy dir not found: {DEPLOY_DIR}")

# ── Deploy to Cloudflare (Shaker-MD-App) ──────────────────────
print("\n[Cloudflare] Deploying to Shaker-MD-App...")
SHAKER_DIR = os.path.join(os.path.expanduser("~"), "Shaker-MD-App")
CLOUDFLARE_DEST = os.path.join(SHAKER_DIR, "docs", "dashboards", "tamkeen-price")
if os.path.exists(os.path.join(SHAKER_DIR, ".git")):
    os.makedirs(CLOUDFLARE_DEST, exist_ok=True)
    dest = os.path.join(CLOUDFLARE_DEST, "index.html")
    shutil.copy2(OUTPUT_FILE, dest)
    print(f"  📋 Copied to {dest}")
    try:
        subprocess.run(["git", "add", "docs/dashboards/tamkeen-price/index.html"],
                       cwd=SHAKER_DIR, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m",
             f"Update Tamkeen Price dashboard ({generated_at})"],
            cwd=SHAKER_DIR, capture_output=True, text=True
        )
        if result.returncode == 0:
            push = subprocess.run(["git", "push"], cwd=SHAKER_DIR,
                                  capture_output=True, text=True)
            if push.returncode != 0:
                subprocess.run(["git", "pull", "--rebase"], cwd=SHAKER_DIR,
                               capture_output=True)
                subprocess.run(["git", "push"], cwd=SHAKER_DIR,
                               capture_output=True)
            print("  🚀 Pushed to Shaker-MD-App (Cloudflare auto-deploy)")
        else:
            if "nothing to commit" in (result.stdout or "") + (result.stderr or ""):
                print("  ℹ️ No changes to deploy (dashboard unchanged)")
            else:
                print(f"  ⚠️ Git commit failed: {result.stderr}")
    except Exception as e:
        print(f"  ⚠️ Cloudflare deploy error: {e}")
else:
    print(f"  ⚠️ Shaker-MD-App not found at {SHAKER_DIR}")
