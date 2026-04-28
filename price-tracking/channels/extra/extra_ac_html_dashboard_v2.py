#!/usr/bin/env python3
"""
eXtra AC Price Tracking - HTML Dashboard V2.1
All filters multi-select, section-level filters, Excel download.
"""
import os, sys, json, math
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Missing: {e}\nRun: pip install pandas openpyxl numpy"); sys.exit(1)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE  = os.path.join(CURRENT_DIR, "extra_ac_Prices_Tracking_Master.xlsx")
OUTPUT_FILE = os.path.join(CURRENT_DIR, "extra_ac_dashboard_v2.html")

import re

# ── Category Validation (카테고리 검증/교정) ─────────────────────────────────────
# 비AC 제품 패턴 (삭제 대상)
NON_AC_PATTERNS = [
    r'^SM-[A-Z]\d',          # Samsung 폰
    r'^SM[A-Z]\d',           # Samsung 폰 변형
    r'^(iPhone|iPad|Galaxy)', # 모바일 기기
    r'^(WM|WF|WW)\d',       # 세탁기
    r'^(RF|RS|RT|RR)\d',    # 냉장고
]

WINDOW_KEYWORDS = ['WINDOW', 'WDV', 'WINDOW AC', 'WINDOW AIR']
WINDOW_MODEL_PREFIXES = ['WDV', 'GJC', 'H182EH', 'H242EH', 'W18', 'W24']
SPLIT_KEYWORDS = ['SPLIT', 'WALL MOUNT', 'WALL-MOUNT']
SPLIT_MODEL_PREFIXES = ['CLW', 'NS', 'NT', 'ND', 'NF', 'LA']
FREESTANDING_KEYWORDS = ['FLOOR STANDING', 'FREE STANDING', 'FREESTANDING', 'FLOOR-STANDING']
FREESTANDING_MODEL_PREFIXES = ['APW', 'APQ', 'FS']


def is_non_ac_product(product_name, model_no, brand):
    name_upper = (str(product_name) if pd.notna(product_name) else '').upper()
    model_upper = (str(model_no) if pd.notna(model_no) else '').upper()
    for pattern in NON_AC_PATTERNS:
        if re.match(pattern, model_upper):
            return True
    ac_indicators = ['AC', 'AIR CONDITIONER', 'BTU', 'TON', 'SPLIT', 'WINDOW',
                     'INVERTER', 'ROTARY', 'COMPRESSOR', 'COOLING', 'COLD',
                     'FLOOR STANDING', 'FREE STANDING', 'CASSETTE', 'CONCEALED']
    has_ac_keyword = any(kw in name_upper for kw in ac_indicators)
    non_ac_brands = ['APPLE', 'XIAOMI', 'HUAWEI', 'OPPO', 'VIVO', 'REALME', 'HONOR']
    brand_str = (str(brand) if pd.notna(brand) else '').upper()
    if brand_str in non_ac_brands and not has_ac_keyword:
        return True
    return False


def validate_category(category, product_name, model_no):
    name_upper = (str(product_name) if pd.notna(product_name) else '').upper()
    model_upper = (str(model_no) if pd.notna(model_no) else '').upper()
    is_window = any(kw in name_upper for kw in WINDOW_KEYWORDS) or any(model_upper.startswith(pfx) for pfx in WINDOW_MODEL_PREFIXES)
    is_split = any(kw in name_upper for kw in SPLIT_KEYWORDS) or any(model_upper.startswith(pfx) for pfx in SPLIT_MODEL_PREFIXES)
    is_freestanding = any(kw in name_upper for kw in FREESTANDING_KEYWORDS) or any(model_upper.startswith(pfx) for pfx in FREESTANDING_MODEL_PREFIXES)
    if is_window and not is_split and category != 'Window Air Conditioner':
        return 'Window Air Conditioner'
    if is_split and not is_window and not is_freestanding and category != 'Split Air Conditioner':
        return 'Split Air Conditioner'
    if is_freestanding and not is_split and category != 'Free Standing Air Conditioner':
        return 'Free Standing Air Conditioner'
    return category

def safe(v):
    if v is None: return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating,)):
        return None if math.isnan(float(v)) else round(float(v), 2)
    if isinstance(v, (np.bool_,)): return bool(v)
    if isinstance(v, pd.Timestamp): return v.strftime('%Y-%m-%d')
    return v

# ── Load & Process ────────────────────────────────────────────────────────────
print("[1/3] Loading data...")
df = pd.read_excel(INPUT_FILE, sheet_name='Prices DB')
print(f"      {len(df):,} rows, {df['SKU'].nunique()} unique SKUs")

df['Scraped_At'] = pd.to_datetime(df['Scraped_At'])
df['date_only'] = df['Scraped_At'].dt.date
for col in ['Cooling_Capacity_Ton','Standard_Price','Sale_Price','Jood_Gold_Price',
            'Discount_Rate','Final_Sale_Price','Final_Jood_Gold_Price']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

mask = df['Promo_Code'].astype(str).str.strip().str.lower() == 'extra10'
df.loc[mask, 'Final_Sale_Price'] = (df.loc[mask, 'Sale_Price'] * 0.9).round(0)
df.loc[mask, 'Final_Jood_Gold_Price'] = (df.loc[mask, 'Jood_Gold_Price'] * 0.9).round(0)
df.loc[~mask, 'Final_Sale_Price'] = df.loc[~mask, 'Final_Sale_Price'].fillna(df.loc[~mask, 'Sale_Price'])
df.loc[~mask, 'Final_Jood_Gold_Price'] = df.loc[~mask, 'Final_Jood_Gold_Price'].fillna(df.loc[~mask, 'Jood_Gold_Price'])

for col_fill in ['Brand','Product_Name','Model_No','Category','Cold_or_HC','Cooling_Capacity_Ton','Compressor_Type']:
    lk = df.dropna(subset=[col_fill]).drop_duplicates('SKU', keep='last').set_index('SKU')[col_fill]
    m = df[col_fill].isna()
    df.loc[m, col_fill] = df.loc[m, 'SKU'].map(lk)

# ── 카테고리 검증/교정 + 비AC 제품 필터링 ──
print("      Category validation...")
before_count = len(df)
non_ac_mask = df.apply(lambda r: is_non_ac_product(r.get('Product_Name'), r.get('Model_No'), r.get('Brand')), axis=1)
removed = non_ac_mask.sum()
if removed > 0:
    print(f"      🗑️ Removed {removed} non-AC products")
    df = df[~non_ac_mask].copy()

corrected = 0
for idx in df.index:
    cat = df.at[idx, 'Category']
    pname = df.at[idx, 'Product_Name'] if pd.notna(df.at[idx, 'Product_Name']) else ''
    model = df.at[idx, 'Model_No'] if pd.notna(df.at[idx, 'Model_No']) else ''
    new_cat = validate_category(cat, pname, model)
    if new_cat != cat:
        df.at[idx, 'Category'] = new_cat
        corrected += 1
if corrected > 0:
    print(f"      🔄 Corrected {corrected} category misclassifications")
print(f"      ✅ Validation done ({before_count} → {len(df)} rows, {corrected} corrected)")

missing_dr = df['Discount_Rate'].isna()
valid = missing_dr & df['Standard_Price'].notna() & df['Sale_Price'].notna() & (df['Standard_Price'] > 0)
df.loc[valid, 'Discount_Rate'] = 1 - df.loc[valid, 'Sale_Price'] / df.loc[valid, 'Standard_Price']

all_dates = sorted(df['date_only'].unique())
latest_date = str(all_dates[-1])
first_date = str(all_dates[0])

# ── Serialize ─────────────────────────────────────────────────────────────────
print("[2/3] Serializing data...")
records = []
for _, r in df.iterrows():
    records.append({
        'd': str(r['date_only']) if pd.notna(r.get('Scraped_At')) else None,
        'b': safe(r.get('Brand')), 'n': str(r.get('Product_Name',''))[:70] if pd.notna(r.get('Product_Name')) else '',
        'm': str(r.get('Model_No','')) if pd.notna(r.get('Model_No')) else '',
        's': str(r.get('SKU','')), 'c': safe(r.get('Category')),
        'h': safe(r.get('Cold_or_HC')), 't': safe(r.get('Cooling_Capacity_Ton')),
        'cp': safe(r.get('Compressor_Type')),
        'sp': safe(r.get('Standard_Price')), 'sl': safe(r.get('Sale_Price')),
        'jp': safe(r.get('Jood_Gold_Price')), 'dr': safe(r.get('Discount_Rate')),
        'pr': str(r.get('Promo_Code','')) if pd.notna(r.get('Promo_Code')) else '',
        'ex': str(r.get('eXtra_Exclusive','')) if pd.notna(r.get('eXtra_Exclusive')) else 'No',
        'fp': safe(r.get('Final_Sale_Price')), 'fj': safe(r.get('Final_Jood_Gold_Price')),
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
compressors_list = sorted(df['Compressor_Type'].dropna().unique().tolist())
cold_hc_list = sorted(df['Cold_or_HC'].dropna().unique().tolist())
ton_list = sorted(df['Cooling_Capacity_Ton'].dropna().unique().tolist())

BRAND_COLORS = {b: c for b, c in zip(brands_list, [
    '#1F4E79','#2E75B6','#ED7D31','#A9D18E','#FF0000','#70AD47','#FFC000','#4472C4',
    '#9E480E','#7030A0','#00B0F0','#FF7F7F','#92D050','#FF00FF','#00B050','#C00000','#B4C6E7','#F4B183','#808080','#5B9BD5'])}

generated_at = datetime.now().strftime('%Y-%m-%d %H:%M')

# ── Build HTML ────────────────────────────────────────────────────────────────
print("[3/3] Generating HTML...")

HTML_HEAD = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>eXtra AC Price Tracker</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2"></script>
<script src="https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<script>
tailwind.config={theme:{extend:{fontFamily:{sans:['Inter','system-ui','sans-serif']},colors:{navy:{50:'#E8F4FD',100:'#D1E9FB',200:'#A3D3F7',500:'#2E75B6',700:'#1E3A5F',800:'#1F4E79',900:'#0F2A42'}}}}}
</script>
<style>
.sort-asc::after{content:' \\25B2';font-size:9px}.sort-desc::after{content:' \\25BC';font-size:9px}
.tbl-wrap{overflow-x:auto}.tbl-wrap table{width:100%;border-collapse:collapse;font-size:12px}
.tbl-wrap th{background:#1F4E79;color:#fff;padding:7px 10px;text-align:left;position:sticky;top:0;z-index:2;white-space:nowrap;cursor:pointer;user-select:none;font-weight:600;font-size:11px}
.tbl-wrap th:hover{background:#2E75B6}
.tbl-wrap td{padding:5px 10px;border-bottom:1px solid #f0f0f0;white-space:nowrap}
.tbl-wrap tr:nth-child(even) td{background:#f8fafc}.tbl-wrap tr:hover td{background:#e8f0fe}
.up-cell{color:#dc2626;font-weight:600}.dn-cell{color:#16a34a;font-weight:600}
.level-cat td{background:#dbeafe!important;font-weight:700;color:#1e3a8a;border-left:4px solid #2563eb}
.level-comp td{background:#eff6ff!important;font-weight:600;border-left:4px solid #60a5fa}
.level-hc td{background:#fef9c3!important;font-weight:500;border-left:4px solid #facc15}
.level-ton td{background:#fff!important;color:#475569;border-left:4px solid #d1d5db}
.type-badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.3px}
.type-cat{background:#2563eb;color:#fff}.type-comp{background:#60a5fa;color:#fff}.type-hc{background:#facc15;color:#713f12}.type-ton{background:#e5e7eb;color:#374151}
.ms-wrap{position:relative;display:inline-block}
.ms-btn{display:flex;align-items:center;gap:4px;padding:3px 10px;border:1px solid #d1d5db;border-radius:6px;background:#fff;font-size:11px;cursor:pointer;white-space:nowrap;transition:all .15s}
.ms-btn:hover{border-color:#2E75B6;background:#f0f7ff}
.ms-menu{display:none;position:absolute;top:100%;left:0;z-index:50;min-width:180px;max-height:280px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;box-shadow:0 8px 25px rgba(0,0,0,.15);margin-top:2px}
.ms-menu.open{display:block}
.ms-menu .ms-actions{display:flex;gap:6px;padding:6px 10px;border-bottom:1px solid #f0f0f0;font-size:10px}
.ms-menu .ms-actions button{color:#2E75B6;font-weight:600;cursor:pointer;background:none;border:none}
.ms-menu .ms-actions button:hover{text-decoration:underline}
.ms-menu .ms-actions button.ms-none{color:#dc2626}
.ms-menu .ms-list{max-height:230px;overflow-y:auto;padding:4px 0}
.ms-menu label{display:flex;align-items:center;gap:6px;padding:3px 10px;cursor:pointer;font-size:11px;transition:background .1s}
.ms-menu label:hover{background:#f1f5f9}
.ms-menu input[type=checkbox]{width:14px;height:14px;border-radius:3px}
.pt-sel{font-size:11px;border:1px solid #d1d5db;border-radius:6px;padding:3px 8px;background:#fff;cursor:pointer}
.sec-search{font-size:11px;border:1px solid #d1d5db;border-radius:6px;padding:3px 8px;background:#fff;width:160px}
.sec-search:focus{outline:none;border-color:#2E75B6;box-shadow:0 0 0 2px rgba(46,117,182,.15)}
@media print{.no-print{display:none!important}}
/* === DARK MODE (sell-thru-progress unified) === */
body{background:#0f172a!important;color:#e2e8f0!important}
header{background:linear-gradient(135deg,#1e293b,#334155)!important;border-bottom:2px solid #3b82f6}
.bg-white,.bg-gray-50{background:#1e293b!important}
.bg-white\/95{background:rgba(30,41,59,.95)!important}
section{background:#1e293b!important;border-color:#334155!important}
.border-gray-100,.border-gray-200,.border-gray-300{border-color:#334155!important}
.text-gray-800,.text-gray-700,.text-gray-600,.text-gray-500{color:#e2e8f0!important}
.text-gray-400{color:#94a3b8!important}
.text-navy-800{color:#60a5fa!important}
.text-navy-700{color:#93c5fd!important}
.bg-navy-800{background:#3b82f6!important}
.bg-navy-50{background:#1e3a5f!important}
.tbl-wrap td{border-bottom-color:#334155!important;color:#e2e8f0!important}
.tbl-wrap tr:nth-child(even) td{background:#1e293b!important}
.tbl-wrap tr:nth-child(odd) td{background:#0f172a!important}
.tbl-wrap tr:hover td{background:#334155!important}
.tbl-wrap th{background:#334155!important;color:#ffffff!important}
.tbl-wrap th:hover{background:#475569!important}
.tbl-wrap a{color:#60a5fa!important}
a.text-blue-600{color:#60a5fa!important}
.level-cat td{background:#1e3a5f!important;color:#60a5fa!important;border-left-color:#3b82f6!important}
.level-comp td{background:#172554!important;color:#93c5fd!important;border-left-color:#60a5fa!important}
.level-hc td{background:#422006!important;color:#fbbf24!important;border-left-color:#f59e0b!important}
.level-ton td{background:#0f172a!important;color:#94a3b8!important;border-left-color:#475569!important}
/* Filter readability - dark buttons */
.ms-btn{background:#0f172a!important;color:#f1f5f9!important;border-color:#64748b!important;font-size:12px!important;font-weight:500!important}
.ms-btn:hover{border-color:#60a5fa!important;background:#1e293b!important}
.ms-btn b{color:#93c5fd!important}
.ms-menu{background:#1e293b!important;border-color:#475569!important;box-shadow:0 8px 25px rgba(0,0,0,.4)!important}
.ms-menu .ms-actions{border-bottom-color:#334155!important}
.ms-menu .ms-actions button{color:#60a5fa!important}
.ms-menu .ms-actions button.ms-none{color:#f87171!important}
.ms-menu label{color:#e2e8f0!important}
.ms-menu label:hover{background:#334155!important}
.pt-sel,.sec-search{background:#0f172a!important;color:#e2e8f0!important;border-color:#475569!important}
.sec-search:focus{border-color:#3b82f6!important;box-shadow:0 0 0 2px rgba(59,130,246,.15)!important}
.shadow-sm{box-shadow:0 2px 8px rgba(0,0,0,.3)!important}
a[class*="bg-white"]{background:#1e293b!important;color:#94a3b8!important;border-color:#334155!important}
a[class*="bg-white"]:hover{background:#334155!important}
.bg-gray-100{background:#334155!important;color:#e2e8f0!important}
.bg-gray-100:hover,.bg-gray-200{background:#475569!important}
.bg-gray-700{background:#334155!important}
.bg-green-600{background:#10b981!important}
.text-green-700,.text-green-600{color:#34d399!important}
.text-red-700,.text-red-600{color:#f87171!important}
.text-purple-600{color:#a78bfa!important}
nav .flex .px-3.py-1{border-color:#334155!important}
.w-px{background:#334155!important}
input[type=checkbox]{accent-color:#3b82f6}
select{background:#0f172a!important;color:#e2e8f0!important;border-color:#475569!important}
/* KPI card backgrounds */
.bg-amber-50{background:#2d1f05!important}
.bg-red-50{background:#2d0f0f!important}
.bg-green-50{background:#0a2618!important}
.bg-blue-50{background:#0f1d3d!important}
.bg-orange-50{background:#2d1507!important}
.bg-teal-50{background:#0a2625!important}
.bg-purple-50{background:#1f0a3d!important}
.bg-cyan-50{background:#0a2833!important}
.bg-indigo-50{background:#1a1840!important}
.bg-pink-50{background:#2d0a1a!important}
/* KPI card text colors */
.text-amber-700,.text-amber-600{color:#fbbf24!important}
.text-blue-600{color:#60a5fa!important}
.text-orange-600,.text-orange-700{color:#fb923c!important}
.text-teal-600,.text-teal-700{color:#2dd4bf!important}
.text-purple-700{color:#c4b5fd!important}
.text-cyan-600{color:#22d3ee!important}
/* Card borders */
.border-green-200{border-color:#166534!important}
.border-red-200{border-color:#991b1b!important}
.border-amber-200{border-color:#92400e!important}
/* Stock badges */
.stk-ok{background:#052e16!important;color:#4ade80!important}
.stk-high{background:#172554!important;color:#60a5fa!important}
.stk-low{background:#422006!important;color:#fbbf24!important}
.stk-critical{background:#450a0a!important;color:#fca5a5!important}
.stk-out{background:#3b0a0a!important;color:#fca5a5!important}
/* Cashback/Install badges */
.cb-yes{background:#052e16!important;color:#4ade80!important}
.cb-no{background:#334155!important;color:#94a3b8!important}
.fi-yes{background:#172554!important;color:#60a5fa!important}
.fi-riyadh{background:#422006!important;color:#fbbf24!important}
.fi-no{background:#334155!important;color:#94a3b8!important}
/* Up/Down cell contrast */
.up-cell{color:#f87171!important;font-weight:700}
.dn-cell{color:#4ade80!important;font-weight:700}
/* Nav pills */
nav a.rounded-full{color:#94a3b8!important;border-color:#475569!important}
nav a.rounded-full:hover{background:#334155!important;color:#e2e8f0!important}
nav a.bg-navy-800.rounded-full{color:#fff!important}
/* Section filter bars */
.text-\[10px\].font-bold.text-gray-400.uppercase{color:#64748b!important}
/* New/Disc card text */
.bg-green-50 .text-gray-700,.bg-red-50 .text-gray-700{color:#f1f5f9!important}
.bg-green-50 .text-gray-400,.bg-red-50 .text-gray-400{color:#94a3b8!important}
.bg-green-50,.bg-red-50{color:#e2e8f0!important}
.bg-green-50 a,.bg-red-50 a{color:#93c5fd!important}
#newCards span[style*="color"],#discCards span[style*="color"]{color:#e2e8f0!important;text-shadow:none}
/* Section heading */
.border-navy-800{border-color:#3b82f6!important}
.text-sm.font-bold.text-gray-700{color:#f1f5f9!important}
/* Mode buttons */
.dir-btn.active,.s5agg-btn.active,.agg-btn.active{background:#3b82f6!important;color:#fff!important}
.dir-btn:not(.active),.s5agg-btn:not(.active),.agg-btn:not(.active){background:#1e293b!important;color:#94a3b8!important;border-color:#475569!important}
/* Type badges */
.type-cat{background:#3b82f6!important}.type-comp{background:#60a5fa!important}.type-hc{background:#f59e0b!important;color:#422006!important}.type-ton{background:#475569!important;color:#e2e8f0!important}
/* Sticky filter bar */
.sticky.top-0{background:rgba(15,23,42,.95)!important;border-bottom-color:#334155!important}
/* Promo badge */
.promo-badge{background:#422006!important;color:#fbbf24!important}
</style></head>
<body class="bg-gray-50 font-sans text-gray-800 text-sm">
"""

HTML_BODY = """
<header class="bg-gradient-to-r from-navy-900 to-navy-700 text-white shadow-lg">
  <div class="max-w-[1600px] mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-4">
    <div><h1 class="text-xl font-bold tracking-wide">eXtra AC Price Tracker</h1>
      <p class="text-xs text-blue-200 mt-1">Saudi Arabia &middot; Air Conditioners &middot; Daily Price Monitoring</p></div>
    <div class="text-right text-xs text-blue-100 space-y-0.5">
      <div><b class="text-white">Last Updated:</b> <span id="metaDate"></span></div>
      <div><b class="text-white">Period:</b> <span id="metaPeriod"></span></div>
      <div><b class="text-white">SKUs:</b> <span id="metaSku"></span></div></div>
  </div>
</header>

<!-- GLOBAL FILTER BAR -->
<div class="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-gray-200 shadow-sm no-print">
  <div class="max-w-[1600px] mx-auto px-6 py-2.5 flex flex-wrap items-center gap-2">
    <span class="text-[10px] font-bold text-navy-700 uppercase tracking-wider">Global</span>
    <div id="gf_date"></div>
    <div class="w-px h-5 bg-gray-300"></div>
    <div id="gf_cat"></div><div id="gf_comp"></div><div id="gf_hc"></div><div id="gf_ton"></div><div id="gf_brand"></div>
    <div class="w-px h-5 bg-gray-300"></div>
    <span id="gf_count" class="text-xs text-gray-500 font-medium"></span>
    <button type="button" onclick="resetGlobal()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-600 rounded px-2.5 py-1 font-medium">Reset</button>
    <span id="gf_compare" class="text-[10px] text-gray-400 ml-auto"></span>
  </div>
</div>

<nav class="max-w-[1600px] mx-auto px-6 pt-3 no-print">
  <div class="flex flex-wrap gap-1.5 text-[11px]">
    <a href="#sec-kpi" class="px-3 py-1 bg-navy-800 text-white rounded-full font-medium">KPIs</a>
    <a href="#sec-alert" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Price Alerts</a>
    <a href="#sec-new" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">New/Disc</a>
    <a href="#sec-catKPI" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Category KPI</a>
    <a href="#sec-brand" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Brand Compare</a>
    <a href="#sec-trend" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Price Trend</a>
    <a href="#sec-promo" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Promo</a>
    <a href="#sec-sku" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Full SKU</a>
  </div>
</nav>

<main class="max-w-[1600px] mx-auto px-6 py-3 space-y-3">

<!-- SEC 1: KPIs -->
<section id="sec-kpi" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Key Performance Indicators</h2>
  <div id="kpiGrid" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5"></div>
</section>

<!-- SEC 2: Price Alerts -->
<section id="sec-alert" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Price Change Alert <span class="text-xs font-normal text-gray-400">(vs compare date)</span></h2>
  <div class="flex flex-wrap items-center gap-2 mb-2">
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="alert-tab active px-4 py-1 text-xs font-semibold bg-navy-800 text-white" data-tab="sale">Sale Price</button>
      <button type="button" class="alert-tab px-4 py-1 text-xs font-semibold bg-gray-50 text-gray-600" data-tab="jood">Jood Gold</button></div>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="dir-btn active px-3 py-1 text-xs font-medium bg-gray-700 text-white" data-dir="all">All</button>
      <button type="button" class="dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-red-600" data-dir="up">Up</button>
      <button type="button" class="dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-green-600" data-dir="down">Down</button></div>
  </div>
  <div class="tbl-wrap" style="max-height:380px;overflow-y:auto"><table id="tblAlert"><thead></thead><tbody></tbody></table></div>
</section>

<!-- SEC 3: New & Disc -->
<section id="sec-new" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">New & Discontinued SKUs</h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
    <div><h3 class="text-xs font-bold text-green-700 mb-2"><span class="w-2 h-2 bg-green-500 rounded-full inline-block mr-1"></span>New SKUs <span id="newCount" class="text-gray-400 font-normal"></span></h3><div id="newCards" class="space-y-2"></div></div>
    <div><h3 class="text-xs font-bold text-red-700 mb-2"><span class="w-2 h-2 bg-red-500 rounded-full inline-block mr-1"></span>Discontinued <span id="discCount" class="text-gray-400 font-normal"></span></h3><div id="discCards" class="space-y-2"></div></div>
  </div>
</section>

<!-- SEC 4: Category KPI (OWN FILTERS) -->
<section id="sec-catKPI" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Category KPI Table</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s4_cat"></div><div id="s4_comp"></div><div id="s4_hc"></div><div id="s4_ton"></div><div id="s4_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s4_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <select id="s4_pt" class="pt-sel"><option value="fp">Final Sale</option><option value="fj">Jood Gold</option><option value="sp">Standard</option></select>
    <button type="button" onclick="resetS4()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div class="tbl-wrap" style="max-height:480px;overflow-y:auto"><table id="tblCatKPI"><thead></thead><tbody></tbody></table></div>
</section>

<!-- SEC 5: Brand Compare (OWN FILTERS) -->
<section id="sec-brand" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Brand Price Comparison</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s5_cat"></div><div id="s5_comp"></div><div id="s5_hc"></div><div id="s5_ton"></div><div id="s5_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s5_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <select id="s5_pt" class="pt-sel"><option value="fp">Final Sale</option><option value="fj">Jood Gold</option><option value="sp">Standard</option></select>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="s5agg-btn active px-3 py-1 text-[10px] font-medium bg-navy-800 text-white" data-agg="avg">Avg</button>
      <button type="button" class="s5agg-btn px-3 py-1 text-[10px] font-medium bg-gray-50 text-gray-600" data-agg="min">Min</button></div>
    <button type="button" onclick="resetS5()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <div style="height:360px"><canvas id="brandBarChart"></canvas></div>
    <div class="tbl-wrap" style="max-height:360px;overflow-y:auto"><table id="tblBrandSeg"><thead></thead><tbody></tbody></table></div>
  </div>
</section>

<!-- SEC 6: Price Trend (OWN FILTERS) -->
<section id="sec-trend" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Price Trend (Time Series)</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s6_cat"></div><div id="s6_comp"></div><div id="s6_hc"></div><div id="s6_ton"></div><div id="s6_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s6_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <select id="s6_pt" class="pt-sel"><option value="fp">Final Sale</option><option value="fj">Jood Gold</option><option value="sp">Standard</option></select>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="agg-btn active px-3 py-1 text-[10px] font-medium bg-navy-800 text-white" data-agg="avg">Avg</button>
      <button type="button" class="agg-btn px-3 py-1 text-[10px] font-medium bg-gray-50 text-gray-600" data-agg="min">Min</button></div>
    <button type="button" onclick="resetS6()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div style="height:400px"><canvas id="trendChart"></canvas></div>
</section>

<!-- SEC 7: Promo -->
<section id="sec-promo" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Promotion & Offer Analysis</h2>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div style="height:260px"><canvas id="promoDonut"></canvas></div>
    <div style="height:260px"><canvas id="exclBar"></canvas></div>
    <div><h3 class="text-xs font-bold text-gray-600 mb-2">Promo Summary</h3><div class="tbl-wrap" style="max-height:240px;overflow-y:auto"><table id="tblGift"><thead></thead><tbody></tbody></table></div></div>
  </div>
</section>

<!-- SEC 8: Full SKU (OWN FILTERS) -->
<section id="sec-sku" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Full SKU Table <span id="skuDateLabel" class="text-xs font-normal text-gray-400"></span></h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s8_cat"></div><div id="s8_comp"></div><div id="s8_hc"></div><div id="s8_ton"></div><div id="s8_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s8_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <select id="s8_pt" class="pt-sel"><option value="fp">Final Sale</option><option value="fj">Jood Gold</option><option value="sp">Standard</option></select>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="excl-btn active px-2 py-1 text-[10px] font-medium bg-gray-700 text-white" data-val="all">All</button>
      <button type="button" class="excl-btn px-2 py-1 text-[10px] font-medium bg-gray-50 text-purple-600" data-val="yes">Excl</button>
      <button type="button" class="excl-btn px-2 py-1 text-[10px] font-medium bg-gray-50 text-gray-600" data-val="no">Non</button></div>
    <button type="button" onclick="downloadExcel()" class="text-[10px] bg-green-600 hover:bg-green-700 text-white rounded px-3 py-1 font-semibold flex items-center gap-1">
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
      Excel Download</button>
    <button type="button" onclick="resetS8()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
    <span id="skuCount" class="text-xs text-gray-400 ml-auto"></span>
  </div>
  <div class="tbl-wrap" style="max-height:500px;overflow-y:auto"><table id="tblSku"><thead></thead><tbody></tbody></table></div>
</section>

</main>
<footer class="text-center py-3 text-[10px] text-gray-400">eXtra AC Price Tracking Dashboard v2.1 &middot; Generated GENERATED_AT</footer>
"""

HTML_DATA = f"""<script>
const DATA={json.dumps(records,ensure_ascii=False)};
const DATE_META={json.dumps(date_meta)};
const DATES={json.dumps(dates_list)};
const BRANDS={json.dumps(brands_list)};
const CATEGORIES={json.dumps(categories_list)};
const COMPRESSORS={json.dumps(compressors_list)};
const COLD_HC={json.dumps(cold_hc_list)};
const TONS={json.dumps([float(t) for t in ton_list])};
const LATEST_DATE={json.dumps(latest_date)};
const FIRST_DATE={json.dumps(first_date)};
const BRAND_COLORS={json.dumps(BRAND_COLORS)};
</script>
"""

HTML_LOGIC = r"""<script>
// ═══ UTILITIES ═══════════════════════════════════════════════════════════════
Chart.register(ChartDataLabels);
Chart.defaults.plugins.datalabels={display:false};
const fmtSAR=v=>v==null?'-':Number(v).toLocaleString('en-SA',{maximumFractionDigits:0});
const fmtPct=v=>v==null?'-':(v*100).toFixed(1)+'%';
const fmtPctR=v=>v==null?'-':v.toFixed(1)+'%';
const fmtChg=v=>{if(v==null)return'-';return(v>0?'+':'')+Number(v).toLocaleString('en-SA',{maximumFractionDigits:0});};
const colorOf=br=>BRAND_COLORS[br]||'#6b7280';
const alphaC=(hex,a)=>{const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);return`rgba(${r},${g},${b},${a})`;};
const mean=arr=>arr.length?arr.reduce((s,v)=>s+v,0)/arr.length:null;
const searchMatch=(r,q)=>!q||(r.b+r.s+r.m+r.n+r.c+r.cp+r.h+(r.t||'')+r.pr).toLowerCase().includes(q);

// ═══ MULTI-SELECT COMPONENT ═════════════════════════════════════════════════
class MS {
  constructor(el,opts,label,cb,colorFn){
    this.el=el;this.opts=opts;this.label=label;this.cb=cb;this.colorFn=colorFn||null;
    this.sel=new Set(opts.map(String));this._build();
  }
  _build(){
    const w=document.createElement('div');w.className='ms-wrap';
    const btn=document.createElement('button');btn.type='button';btn.className='ms-btn';
    this.btnEl=btn;w.appendChild(btn);
    const menu=document.createElement('div');menu.className='ms-menu';menu.onclick=function(e){e.stopPropagation()};
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
      const txt=this.label==='Ton'?parseFloat(o).toFixed(1)+'T':String(o).replace('Air Conditioner','AC');
      sp.textContent=txt;
      if(this.colorFn)sp.style.cssText=`color:${this.colorFn(o)};font-weight:600`;
      lbl.appendChild(sp);list.appendChild(lbl);
    });
    menu.appendChild(list);w.appendChild(menu);this.menuEl=menu;
    btn.addEventListener('click',e=>{e.stopPropagation();document.querySelectorAll('.ms-menu.open').forEach(m=>{if(m!==menu)m.classList.remove('open')});menu.classList.toggle('open');});
    this.el.appendChild(w);this._upd();
    this.listEl=list;
  }
  _upd(){this.btnEl.innerHTML=`${this.label} <b class="text-navy-700">${this.sel.size}/${this.opts.length}</b> <span class="text-gray-400 text-[9px]">&#9662;</span>`;}
  selectAll(){this.sel=new Set(this.opts.map(String));this.listEl.querySelectorAll('input').forEach(c=>c.checked=true);this._upd();this.cb();}
  selectNone(){this.sel.clear();this.listEl.querySelectorAll('input').forEach(c=>c.checked=false);this._upd();this.cb();}
  reset(){this.selectAll();}
  getSelected(){return this.sel;}
  // Sync: set selections without triggering callback (to avoid loops)
  setSelected(vals){
    this.sel=new Set(vals.map(String));
    this.listEl.querySelectorAll('input').forEach(cb=>{cb.checked=this.sel.has(cb.value);});
    this._upd();
  }
}
document.addEventListener('click',()=>document.querySelectorAll('.ms-menu.open').forEach(m=>m.classList.remove('open')));

// ═══ FILTER HELPERS ═════════════════════════════════════════════════════════
function makeFilters(prefix,cb){
  return {
    cat: new MS(document.getElementById(prefix+'_cat'),CATEGORIES,'Category',cb),
    comp: new MS(document.getElementById(prefix+'_comp'),COMPRESSORS,'Compressor',cb),
    hc: new MS(document.getElementById(prefix+'_hc'),COLD_HC,'Cold/HC',cb),
    ton: new MS(document.getElementById(prefix+'_ton'),TONS.map(String),'Ton',cb),
    brand: new MS(document.getElementById(prefix+'_brand'),BRANDS,'Brand',cb,colorOf),
  };
}
function applyF(rows,f){
  return rows.filter(r=>{
    if(!f.cat.getSelected().has(r.c))return false;
    if(!f.comp.getSelected().has(r.cp))return false;
    if(!f.hc.getSelected().has(r.h))return false;
    if(r.t!=null&&!f.ton.getSelected().has(String(r.t)))return false;
    if(!f.brand.getSelected().has(r.b))return false;
    return true;
  });
}
function resetF(f){f.cat.reset();f.comp.reset();f.hc.reset();f.ton.reset();f.brand.reset();}

// Sync global filters → section filters (without triggering callbacks)
function syncToSection(src,tgt){
  tgt.cat.setSelected([...src.cat.getSelected()]);
  tgt.comp.setSelected([...src.comp.getSelected()]);
  tgt.hc.setSelected([...src.hc.getSelected()]);
  tgt.ton.setSelected([...src.ton.getSelected()]);
  tgt.brand.setSelected([...src.brand.getSelected()]);
}

// ═══ GLOBAL STATE ═══════════════════════════════════════════════════════════
let GF, S4F, S5F, S6F, S8F;
let gfDate;
const ST={alertTab:'sale',alertDir:'all',s4q:'',s5q:'',s6q:'',s8q:'',skuExcl:'all',s5agg:'avg',s6agg:'avg'};

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

// ═══ INIT ════════════════════════════════════════════════════════════════════
function init(){
  gfDate=new MS(document.getElementById('gf_date'),DATES,'Date',refreshGlobal);
  GF=makeFilters('gf',refreshGlobal);
  S4F=makeFilters('s4',renderS4);
  S5F=makeFilters('s5',renderS5);
  S6F=makeFilters('s6',renderS6);
  S8F=makeFilters('s8',renderS8);

  // Price type selectors
  ['s4_pt','s5_pt','s6_pt','s8_pt'].forEach(id=>{
    const el=document.getElementById(id);
    if(el) el.addEventListener('change',()=>{
      if(id==='s4_pt')renderS4();else if(id==='s5_pt')renderS5();else if(id==='s6_pt')renderS6();else renderS8();
    });
  });

  // Search inputs with debounce
  const searchIds=[['s4_search','s4q',renderS4],['s5_search','s5q',renderS5],['s6_search','s6q',renderS6],['s8_search','s8q',renderS8]];
  searchIds.forEach(([id,key,fn])=>{
    let to=null;const el=document.getElementById(id);
    if(el) el.addEventListener('input',e=>{clearTimeout(to);to=setTimeout(()=>{ST[key]=e.target.value.toLowerCase().trim();fn();},150);});
  });

  // Alert tabs
  document.querySelectorAll('.alert-tab').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.alert-tab').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');
    ST.alertTab=btn.dataset.tab;renderAlerts();
  }));
  document.querySelectorAll('.dir-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.dir-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');
    ST.alertDir=btn.dataset.dir;renderAlerts();
  }));

  // Brand Compare agg toggle (Avg/Min)
  document.querySelectorAll('.s5agg-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.s5agg-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');
    ST.s5agg=btn.dataset.agg;renderS5();
  }));

  // Trend agg toggle (Avg/Min)
  document.querySelectorAll('.agg-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.agg-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');
    ST.s6agg=btn.dataset.agg;renderS6();
  }));

  // SKU exclusive buttons
  document.querySelectorAll('.excl-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.excl-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');
    ST.skuExcl=btn.dataset.val;renderS8();
  }));

  // Meta
  document.getElementById('metaDate').textContent=LATEST_DATE;
  document.getElementById('metaPeriod').textContent=FIRST_DATE+' ~ '+LATEST_DATE+' ('+DATES.length+' days)';

  refreshGlobal();
}

// ═══ GLOBAL REFRESH ═════════════════════════════════════════════════════════
function refreshGlobal(){
  const {cur,prev}=getCompareDates();
  const curData=applyF(DATA.filter(r=>r.d===cur),GF);
  const prevData=prev?applyF(DATA.filter(r=>r.d===prev),GF):[];
  document.getElementById('gf_count').textContent=curData.length+' SKUs';
  document.getElementById('gf_compare').textContent='Viewing: '+cur+(prev?' vs '+prev:'');
  document.getElementById('metaSku').textContent=curData.length;

  // Sync global → all sections
  syncToSection(GF,S4F);
  syncToSection(GF,S5F);
  syncToSection(GF,S6F);
  syncToSection(GF,S8F);

  renderKPIs(curData,prevData);
  renderAlerts();
  renderNewDisc(curData,prevData);
  renderS4();
  renderS5();
  renderS6();
  renderPromo(curData);
  renderS8();
}

function resetGlobal(){gfDate.reset();resetF(GF);refreshGlobal();}
function resetS4(){resetF(S4F);ST.s4q='';document.getElementById('s4_search').value='';document.getElementById('s4_pt').value='fp';renderS4();}
function resetS5(){resetF(S5F);ST.s5q='';ST.s5agg='avg';document.getElementById('s5_search').value='';document.getElementById('s5_pt').value='fp';
  document.querySelectorAll('.s5agg-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');}});
  renderS5();}
function resetS6(){resetF(S6F);ST.s6q='';ST.s6agg='avg';document.getElementById('s6_search').value='';document.getElementById('s6_pt').value='fp';
  document.querySelectorAll('.agg-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');}});
  renderS6();}
function resetS8(){resetF(S8F);ST.s8q='';ST.skuExcl='all';document.getElementById('s8_search').value='';document.getElementById('s8_pt').value='fp';
  document.querySelectorAll('.excl-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');}});
  renderS8();}

// ═══ SEC 1: KPIs ═════════════════════════════════════════════════════════════
function renderKPIs(lat,prev){
  const lm={};lat.forEach(r=>lm[r.s]=r.fp);const pm={};prev.forEach(r=>pm[r.s]=r.fp);
  let up=0,dn=0;Object.keys(lm).filter(s=>s in pm).forEach(s=>{const d=(lm[s]||0)-(pm[s]||0);if(d>0)up++;else if(d<0)dn++;});
  const nw=lat.filter(r=>!(r.s in pm)).length,rm=prev.filter(r=>!(r.s in lm)).length;
  const ex=lat.filter(r=>r.ex==='Yes').length;
  const ad=lat.filter(r=>r.dr!=null);const avgD=ad.length?mean(ad.map(r=>r.dr)):null;
  const af=lat.filter(r=>r.fp!=null);const avgS=af.length?Math.round(mean(af.map(r=>r.fp))):null;
  const cards=[
    {v:lat.length,l:'Total SKUs',c:'border-l-navy-800 bg-navy-50',vc:'text-navy-800'},
    {v:avgD!=null?(avgD*100).toFixed(1)+'%':'-',l:'Avg Discount',c:'border-l-amber-500 bg-amber-50',vc:'text-amber-700'},
    {v:'&#9650; '+up,l:'Price Up',c:'border-l-red-500 bg-red-50',vc:'text-red-600'},
    {v:'&#9660; '+dn,l:'Price Down',c:'border-l-green-500 bg-green-50',vc:'text-green-600'},
    {v:nw,l:'New SKUs',c:'border-l-blue-500 bg-blue-50',vc:'text-blue-600'},
    {v:rm,l:'Removed',c:'border-l-orange-500 bg-orange-50',vc:'text-orange-600'},
    {v:ex,l:'eXtra Exclusive',c:'border-l-purple-500 bg-purple-50',vc:'text-purple-600'},
    {v:fmtSAR(avgS),l:'Avg Sale (SAR)',c:'border-l-teal-500 bg-teal-50',vc:'text-teal-700'},
  ];
  document.getElementById('kpiGrid').innerHTML=cards.map(c=>`<div class="rounded-lg border-l-4 ${c.c} p-3"><div class="text-xl font-bold ${c.vc}">${c.v}</div><div class="text-[10px] text-gray-500 mt-1 font-medium">${c.l}</div></div>`).join('');
}

// ═══ SEC 2: ALERTS ═══════════════════════════════════════════════════════════
const AC_SALE=[{k:'b',l:'Brand'},{k:'s',l:'SKU'},{k:'n',l:'Product Name'},{k:'c',l:'Category'},{k:'cp',l:'Compressor'},{k:'h',l:'Cold/HC'},{k:'ton',l:'Ton'},{k:'prev',l:'Prev Sale',f:fmtSAR},{k:'curr',l:'Curr Sale',f:fmtSAR},{k:'final',l:'Final (w/CB)',f:fmtSAR},{k:'chg',l:'Change',f:fmtChg},{k:'chgPct',l:'Chg%',f:fmtPctR}];
const AC_JOOD=[{k:'b',l:'Brand'},{k:'s',l:'SKU'},{k:'n',l:'Product Name'},{k:'c',l:'Category'},{k:'cp',l:'Compressor'},{k:'h',l:'Cold/HC'},{k:'ton',l:'Ton'},{k:'prev',l:'Prev',f:fmtSAR},{k:'curr',l:'Curr',f:fmtSAR},{k:'chg',l:'Change',f:fmtChg},{k:'chgPct',l:'Chg%',f:fmtPctR}];
function renderAlerts(){
  const {cur,prev}=getCompareDates();
  const latD=applyF(DATA.filter(r=>r.d===cur),GF);
  const prevD=prev?applyF(DATA.filter(r=>r.d===prev),GF):[];
  const isSale=ST.alertTab==='sale';
  const pk=isSale?'sl':'fj';
  const AC=isSale?AC_SALE:AC_JOOD;
  const lm={};latD.forEach(r=>lm[r.s]=r);const pm={};prevD.forEach(r=>pm[r.s]=r);
  let rows=[];
  Object.keys(lm).filter(s=>s in pm).forEach(s=>{
    const rn=lm[s],ro=pm[s],pn=rn[pk],po=ro[pk];
    if(pn==null||po==null)return;const chg=pn-po;if(Math.abs(chg)<1)return;
    const base={b:rn.b,s,n:rn.n,c:rn.c,cp:rn.cp,h:rn.h,ton:rn.t!=null?rn.t.toFixed(1)+'T':'-',prev:po,curr:pn,chg,chgPct:po?chg/po*100:0};
    if(isSale)base.final=rn.fp;
    rows.push(base);
  });
  if(ST.alertDir==='up')rows=rows.filter(r=>r.chg>0);if(ST.alertDir==='down')rows=rows.filter(r=>r.chg<0);
  rows.sort((a,b)=>Math.abs(b.chg)-Math.abs(a.chg));
  const tbl=document.getElementById('tblAlert');
  tbl.querySelector('thead').innerHTML='<tr>'+AC.map((c,i)=>`<th onclick="sortTbl('tblAlert',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=rows.length?rows.map(r=>'<tr>'+AC.map(c=>{let v=c.f?c.f(r[c.k]):(r[c.k]??'-');if(c.k==='n')v=`<a href="https://www.extra.com/en-sa/p/${r.s}" target="_blank" class="text-blue-600 hover:underline">${v}</a>`;let cls='';if((c.k==='chg'||c.k==='chgPct')&&r.chg!=null)cls=r.chg>0?'up-cell':'dn-cell';return`<td class="${cls}">${v}</td>`;}).join('')+'</tr>').join(''):`<tr><td colspan="${AC.length}" class="text-center text-gray-400 py-6">No changes</td></tr>`;
}

// ═══ SEC 3: NEW/DISC ═════════════════════════════════════════════════════════
function renderNewDisc(lat,prev){
  const ls=new Set(lat.map(r=>r.s)),ps=new Set(prev.map(r=>r.s));
  const nw=lat.filter(r=>!ps.has(r.s)),dc=prev.filter(r=>!ls.has(r.s));
  const card=(r,clr)=>`<div class="border border-${clr}-200 bg-${clr}-50 rounded-lg p-2.5 flex justify-between items-center"><div><span class="text-xs font-bold" style="color:${colorOf(r.b)}">${r.b}</span> <span class="text-[10px] text-gray-400">${r.s}</span><div class="text-[11px] text-gray-600 mt-0.5 truncate max-w-[280px]"><a href="https://www.extra.com/en-sa/p/${r.s}" target="_blank" class="hover:underline text-blue-600">${r.n}</a></div><div class="text-[10px] text-gray-400">${r.c||''} &middot; ${r.t?r.t.toFixed(1)+'T':''}</div></div><div class="text-sm font-bold text-gray-700">${fmtSAR(r.fp)} SAR</div></div>`;
  document.getElementById('newCards').innerHTML=nw.length?nw.map(r=>card(r,'green')).join(''):'<p class="text-xs text-gray-400 py-3">None</p>';
  document.getElementById('newCount').textContent='('+nw.length+')';
  document.getElementById('discCards').innerHTML=dc.length?dc.map(r=>card(r,'red')).join(''):'<p class="text-xs text-gray-400 py-3">None</p>';
  document.getElementById('discCount').textContent='('+dc.length+')';
}

// ═══ SEC 4: CATEGORY KPI ════════════════════════════════════════════════════
const CK=[{l:'Type',k:'type'},{l:'Segment',k:'label'},{l:'SKUs',k:'cnt'},{l:'Avg Price',k:'avgP',f:fmtSAR},{l:'Avg Std',k:'avgStd',f:fmtSAR},{l:'Avg Disc %',k:'avgDisc',f:fmtPctR},{l:'Exclusive',k:'excl'},{l:'LG Avg',k:'lgAvg',f:fmtSAR},{l:'LG Gap',k:'lgGap',f:fmtChg},{l:'LG Gap %',k:'lgGapPct',f:fmtPctR}];
const TYPE_BADGE={cat:'<span class="type-badge type-cat">Category</span>',comp:'<span class="type-badge type-comp">Compressor</span>',hc:'<span class="type-badge type-hc">Cold/HC</span>',ton:'<span class="type-badge type-ton">Ton</span>'};
const CAT_ORDER=['Free Standing Air Conditioner','Split Air Conditioner','Window Air Conditioner'];
const COMP_ORDER=['Inverter','Rotary'];
const HC_ORDER=['Cold','Hot and Cold'];

function segKPI(data,pk){
  const cnt=new Set(data.map(r=>r.s)).size;
  const pArr=data.filter(r=>r[pk]!=null).map(r=>r[pk]);const avgP=pArr.length?Math.round(mean(pArr)):null;
  const sps=data.filter(r=>r.sp!=null).map(r=>r.sp);const avgStd=sps.length?Math.round(mean(sps)):null;
  const drs=data.filter(r=>r.dr!=null).map(r=>r.dr*100);const avgDisc=drs.length?Math.round(mean(drs)*10)/10:null;
  const excl=data.filter(r=>r.ex==='Yes').length;
  const lgD=data.filter(r=>r.b==='LG'&&r[pk]!=null);const lgAvg=lgD.length?Math.round(mean(lgD.map(r=>r[pk]))):null;
  const lgGap=(lgAvg!=null&&avgP!=null)?lgAvg-avgP:null;
  const lgGapPct=(lgGap!=null&&lgAvg)?Math.round(lgGap/lgAvg*1000)/10:null;
  return{cnt,avgP,avgStd,avgDisc,excl,lgAvg,lgGap,lgGapPct};
}

function renderS4(){
  const {cur}=getCompareDates();
  const pk=document.getElementById('s4_pt').value;
  let lat=applyF(DATA.filter(r=>r.d===cur),S4F);
  if(ST.s4q)lat=lat.filter(r=>searchMatch(r,ST.s4q));
  const ptLabel={fp:'Final Sale',fj:'Jood Gold',sp:'Standard'}[pk]||'Price';
  CK[3].l='Avg '+ptLabel;
  const rows=[];
  const cats=CAT_ORDER.filter(c=>[...new Set(lat.map(r=>r.c))].includes(c));
  cats.forEach(cat=>{
    const catD=lat.filter(r=>r.c===cat);if(!catD.length)return;
    rows.push({level:'cat',type:'cat',label:cat.replace('Air Conditioner','AC'),...segKPI(catD,pk)});
    const comps=COMP_ORDER.filter(c=>[...new Set(catD.map(r=>r.cp))].includes(c));
    comps.forEach(comp=>{
      const compD=catD.filter(r=>r.cp===comp);if(!compD.length)return;
      rows.push({level:'comp',type:'comp',label:comp,...segKPI(compD,pk)});
      const hcs=HC_ORDER.filter(h=>[...new Set(compD.map(r=>r.h))].includes(h));
      hcs.forEach(hc=>{
        const hcD=compD.filter(r=>r.h===hc);if(!hcD.length)return;
        rows.push({level:'hc',type:'hc',label:hc,...segKPI(hcD,pk)});
        const tons=[...new Set(hcD.map(r=>r.t))].filter(Boolean).sort((a,b)=>a-b);
        tons.forEach(t=>{
          const tD=hcD.filter(r=>r.t===t);if(!tD.length)return;
          rows.push({level:'ton',type:'ton',label:t.toFixed(1)+'T',...segKPI(tD,pk)});
        });
      });
    });
  });
  rows.push({level:'cat',type:'cat',label:'TOTAL',...segKPI(lat,pk)});
  const tbl=document.getElementById('tblCatKPI');
  tbl.querySelector('thead').innerHTML='<tr>'+CK.map((c,i)=>`<th onclick="sortTbl('tblCatKPI',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=rows.map(r=>{
    return`<tr class="level-${r.level}">`+CK.map(c=>{
      let v;
      if(c.k==='type')v=TYPE_BADGE[r.type]||'';
      else if(c.k==='label')v=r.label;
      else v=c.f?c.f(r[c.k]):(r[c.k]??'-');
      let cls='';
      if(c.k==='lgGap'&&r.lgGap!=null)cls=r.lgGap>0?'up-cell':'dn-cell';
      if(c.k==='lgGapPct'&&r.lgGapPct!=null)cls=r.lgGapPct>0?'up-cell':'dn-cell';
      return`<td class="${cls}">${v}</td>`;
    }).join('')+'</tr>';
  }).join('');
}

// ═══ SEC 5: BRAND COMPARE ═══════════════════════════════════════════════════
let brandChart=null;
function renderS5(){
  const {cur}=getCompareDates();
  let lat=applyF(DATA.filter(r=>r.d===cur),S5F);
  if(ST.s5q)lat=lat.filter(r=>searchMatch(r,ST.s5q));
  const pk=document.getElementById('s5_pt').value;
  const aggFn=ST.s5agg==='min'?(arr=>Math.round(Math.min(...arr))):(arr=>Math.round(mean(arr)));
  const aggLabel=ST.s5agg==='min'?'Min Price':'Avg Price';
  const bData={};lat.forEach(r=>{if(r[pk]==null)return;if(!bData[r.b])bData[r.b]=[];bData[r.b].push(r[pk]);});
  let items=Object.entries(bData).map(([b,v])=>({b,val:aggFn(v)})).sort((a,b)=>a.val-b.val);
  const labels=items.map(x=>x.b),vals=items.map(x=>x.val),bg=labels.map(b=>colorOf(b));
  const ctx=document.getElementById('brandBarChart').getContext('2d');
  if(brandChart)brandChart.destroy();
  const allMax=vals.length?Math.max(...vals):0;
  brandChart=new Chart(ctx,{type:'bar',data:{labels,datasets:[{label:aggLabel,data:vals,backgroundColor:bg,borderColor:bg,borderWidth:1}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.dataset.label+': SAR '+fmtSAR(c.raw)}},datalabels:{display:true,anchor:'end',align:'right',color:'#1e3a5f',font:{size:9,weight:'bold'},formatter:v=>fmtSAR(v),clip:false}},scales:{x:{ticks:{callback:v=>fmtSAR(v)},grid:{color:'#f0f0f0'},suggestedMax:allMax?allMax*1.18:undefined},y:{ticks:{font:{size:10}}}}}});
  // Segment table
  const segs=[];const bList=[...new Set(lat.map(r=>r.b))].filter(Boolean).sort();
  const cats=[...new Set(lat.map(r=>r.c))].filter(x=>x!=null&&x!=='').sort();
  cats.forEach(cat=>{const cD=lat.filter(r=>r.c===cat);
    [...new Set(cD.map(r=>r.cp))].filter(x=>x!=null&&x!=='').sort().forEach(comp=>{const coD=cD.filter(r=>r.cp===comp);
      [...new Set(coD.map(r=>r.h))].filter(x=>x!=null&&x!=='').sort().forEach(hc=>{const hD=coD.filter(r=>r.h===hc);
        [...new Set(hD.map(r=>r.t))].filter(x=>x!=null&&!isNaN(x)).sort((a,b)=>a-b).forEach(t=>{const tD=hD.filter(r=>r.t===t);if(!tD.length)return;
          const seg=(cat||'').replace('Air Conditioner','AC')+' / '+(comp||'')+' / '+(hc||'')+' / '+Number(t).toFixed(1)+'T';
          const row={seg};const prices=[];
          bList.forEach(b=>{const bD=tD.filter(r=>r.b===b&&r[pk]!=null);const avg=bD.length?Math.round(mean(bD.map(r=>r[pk]))):null;row[b]=avg;if(avg!=null)prices.push(avg);});
          row['Mkt']=prices.length?Math.round(mean(prices)):null;
          const lgD=tD.filter(r=>r.b==='LG'&&r[pk]!=null);row['LG Min']=lgD.length?Math.round(Math.min(...lgD.map(r=>r[pk]))):null;
          segs.push(row);
        });});});});
  const allC=['seg',...bList,'Mkt','LG Min'],allH=['Segment',...bList,'Mkt Avg','LG Min'];
  const tbl=document.getElementById('tblBrandSeg');
  tbl.querySelector('thead').innerHTML='<tr>'+allH.map((h,i)=>`<th onclick="sortTbl('tblBrandSeg',${i})">${h}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=segs.length?segs.map(r=>'<tr>'+allC.map(k=>`<td>${k==='seg'?r[k]:(r[k]!=null?fmtSAR(r[k]):'-')}</td>`).join('')+'</tr>').join(''):'<tr><td colspan="99" class="text-center text-gray-400 py-4">No data</td></tr>';
}

// ═══ SEC 6: TREND ═══════════════════════════════════════════════════════════
let trendChartObj=null;
function renderS6(){
  const pk=document.getElementById('s6_pt').value;
  const q=ST.s6q;
  let datasets=[];
  const aggFn=ST.s6agg==='min'?(arr=>Math.round(Math.min(...arr))):(arr=>Math.round(mean(arr)));
  const aggLabel=ST.s6agg==='min'?'Market Min':'Market Avg';
  const mkt=DATES.map(d=>{let dd=applyF(DATA.filter(r=>r.d===d),S6F);if(q)dd=dd.filter(r=>searchMatch(r,q));dd=dd.filter(r=>r[pk]!=null);return dd.length?aggFn(dd.map(r=>r[pk])):null;});
  datasets.push({label:aggLabel,data:mkt,borderColor:'#6b7280',borderWidth:2,borderDash:[6,3],pointRadius:2,tension:.3,fill:false});
  const bSet=S6F.brand.getSelected();
  [...bSet].forEach(br=>{
    const vals=DATES.map(d=>{let dd=applyF(DATA.filter(r=>r.d===d&&r.b===br),S6F);if(q)dd=dd.filter(r=>searchMatch(r,q));dd=dd.filter(r=>r[pk]!=null);return dd.length?aggFn(dd.map(r=>r[pk])):null;});
    if(vals.every(v=>v===null))return;const c=colorOf(br);
    datasets.push({label:br,data:vals,borderColor:c,backgroundColor:alphaC(c,.08),borderWidth:1.5,pointRadius:2,tension:.3,fill:false,spanGaps:true});
  });
  const ctx=document.getElementById('trendChart').getContext('2d');
  if(trendChartObj)trendChartObj.destroy();
  trendChartObj=new Chart(ctx,{type:'line',data:{labels:DATES,datasets},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},layout:{padding:{right:90}},plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:10}}},tooltip:{callbacks:{label:c=>c.dataset.label+': SAR '+fmtSAR(c.raw)}},datalabels:{display:false}},scales:{x:{ticks:{font:{size:10},maxRotation:45},grid:{color:'#f5f5f5'}},y:{ticks:{callback:v=>fmtSAR(v)},grid:{color:'#f5f5f5'}}}},plugins:[{id:'endLabels',afterDatasetsDraw(chart){const ctx2=chart.ctx;chart.data.datasets.forEach((ds,i)=>{const meta=chart.getDatasetMeta(i);if(!meta.visible)return;for(let j=meta.data.length-1;j>=0;j--){const pt=meta.data[j];if(pt&&ds.data[j]!=null){ctx2.save();ctx2.font='bold 10px Inter,sans-serif';ctx2.fillStyle=ds.borderColor||'#333';ctx2.textBaseline='middle';const lbl=(ds.label.length>14?ds.label.substring(0,14)+'..':ds.label)+' '+fmtSAR(ds.data[j]);ctx2.fillText(lbl,pt.x+6,pt.y);ctx2.restore();break;}}});}}]});
}

// ═══ SEC 7: PROMO ════════════════════════════════════════════════════════════
let promoD=null,exclB=null;
function renderPromo(lat){
  const pc={};lat.forEach(r=>{const p=r.pr||'(none)';pc[p]=(pc[p]||0)+1;});
  const pl=Object.keys(pc),pv=Object.values(pc),pcol=['#1F4E79','#ED7D31','#A9D18E','#FF0000','#70AD47','#FFC000'];
  const c1=document.getElementById('promoDonut').getContext('2d');if(promoD)promoD.destroy();
  promoD=new Chart(c1,{type:'doughnut',data:{labels:pl,datasets:[{data:pv,backgroundColor:pcol.slice(0,pl.length)}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}},title:{display:true,text:'Promo Code Distribution',font:{size:12}}}}});
  const ec={};lat.filter(r=>r.ex==='Yes').forEach(r=>{ec[r.b]=(ec[r.b]||0)+1;});
  const eb=Object.keys(ec).sort((a,b)=>ec[b]-ec[a]),ev=eb.map(b=>ec[b]);
  const c2=document.getElementById('exclBar').getContext('2d');if(exclB)exclB.destroy();
  exclB=new Chart(c2,{type:'bar',data:{labels:eb,datasets:[{label:'Exclusive',data:ev,backgroundColor:eb.map(b=>colorOf(b))}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},title:{display:true,text:'eXtra Exclusive by Brand',font:{size:12}}},scales:{y:{ticks:{stepSize:1}}}}});
  const tbl=document.getElementById('tblGift');
  tbl.querySelector('thead').innerHTML='<tr><th>Promo</th><th>SKUs</th><th>%</th></tr>';
  tbl.querySelector('tbody').innerHTML=pl.map((p,i)=>`<tr><td>${p}</td><td>${pv[i]}</td><td>${(pv[i]/lat.length*100).toFixed(1)}%</td></tr>`).join('');
}

// ═══ SEC 8: FULL SKU ════════════════════════════════════════════════════════
const SC=[{k:'b',l:'Brand'},{k:'s',l:'SKU'},{k:'m',l:'Model No'},{k:'n',l:'Product Name'},{k:'c',l:'Category'},{k:'cp',l:'Compressor'},{k:'h',l:'Cold/HC'},{k:'ton',l:'Ton'},{k:'sp',l:'Std Price',f:fmtSAR},{k:'sl',l:'Sale Price',f:fmtSAR},{k:'jp',l:'Jood Gold',f:fmtSAR},{k:'dr',l:'Disc %',f:fmtPct},{k:'fp',l:'Final Price',f:fmtSAR},{k:'prev',l:'Prev Price',f:fmtSAR},{k:'chg',l:'Change',f:fmtChg},{k:'chgPct',l:'Chg %',f:fmtPctR},{k:'pr',l:'Promo'},{k:'ex',l:'Exclusive'}];
let _skuData=[];

function renderS8(){
  const {cur,prev}=getCompareDates();
  const pk=document.getElementById('s8_pt').value;
  let lat=applyF(DATA.filter(r=>r.d===cur),S8F);
  const prevD=prev?applyF(DATA.filter(r=>r.d===prev),S8F):[];
  const pm={};prevD.forEach(r=>pm[r.s]=r);
  let rows=lat.map(r=>{
    const pr=pm[r.s];const prevP=pr?pr[pk]:null;
    const chg=(r[pk]!=null&&prevP!=null)?r[pk]-prevP:null;
    const chgPct=(chg!=null&&prevP)?Math.round(chg/prevP*1000)/10:null;
    return{...r,ton:r.t!=null?r.t.toFixed(1)+'T':'-',prev:prevP,chg,chgPct};
  });
  if(ST.skuExcl==='yes')rows=rows.filter(r=>r.ex==='Yes');
  if(ST.skuExcl==='no')rows=rows.filter(r=>r.ex!=='Yes');
  if(ST.s8q)rows=rows.filter(r=>searchMatch(r,ST.s8q));
  _skuData=rows;
  document.getElementById('skuDateLabel').textContent='('+cur+')';
  document.getElementById('skuCount').textContent=rows.length+' SKUs';
  const tbl=document.getElementById('tblSku');
  tbl.querySelector('thead').innerHTML='<tr>'+SC.map((c,i)=>`<th onclick="sortTbl('tblSku',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=rows.length?rows.map(r=>'<tr>'+SC.map(c=>{
    let v=c.f?c.f(r[c.k]):(r[c.k]!=null?r[c.k]:'-');let cls='';
    if((c.k==='chg')&&r.chg!=null)cls=r.chg>0?'up-cell':r.chg<0?'dn-cell':'';
    if((c.k==='chgPct')&&r.chgPct!=null)cls=r.chgPct>0?'up-cell':r.chgPct<0?'dn-cell':'';
    if(c.k==='b')v=`<span style="color:${colorOf(r.b)};font-weight:600">${v}</span>`;
    if(c.k==='n')v=`<a href="https://www.extra.com/en-sa/p/${r.s}" target="_blank" class="text-blue-600 hover:underline">${v}</a>`;
    if(c.k==='pr'&&v&&v!=='-'&&v!=='')v=`<span class="inline-block px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded-full text-[10px] font-semibold">${v}</span>`;
    if(c.k==='ex'&&v==='Yes')v=`<span class="inline-block px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded-full text-[10px] font-semibold">Excl</span>`;
    return`<td class="${cls}">${v}</td>`;
  }).join('')+'</tr>').join(''):'<tr><td colspan="18" class="text-center text-gray-400 py-6">No data</td></tr>';
}

function downloadExcel(){
  const rows=_skuData;if(!rows.length){alert('No data to download');return;}
  const {cur}=getCompareDates();
  const xlData=rows.map(r=>({
    Brand:r.b,SKU:r.s,'Model No':r.m,'Product Name':r.n,Category:r.c,Compressor:r.cp,'Cold/HC':r.h,Ton:r.ton,
    'Std Price':r.sp,'Sale Price':r.sl,'Jood Gold':r.jp,'Disc %':r.dr!=null?Math.round(r.dr*1000)/10:null,
    'Final Price':r.fp,'Prev Price':r.prev,'Change':r.chg,'Change %':r.chgPct,Promo:r.pr,Exclusive:r.ex
  }));
  const ws=XLSX.utils.json_to_sheet(xlData);
  const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'SKU Data');
  XLSX.writeFile(wb,'eXtra_AC_SKUs_'+cur+'.xlsx');
}

// ═══ TABLE SORT ══════════════════════════════════════════════════════════════
const _ss={};
function sortTbl(id,col){
  const tbl=document.getElementById(id),tb=tbl.querySelector('tbody'),rows=Array.from(tb.querySelectorAll('tr')),ths=tbl.querySelectorAll('th');
  const p=_ss[id]||{col:-1,asc:true};const asc=p.col===col?!p.asc:true;_ss[id]={col,asc};
  ths.forEach((th,i)=>{th.classList.remove('sort-asc','sort-desc');if(i===col)th.classList.add(asc?'sort-asc':'sort-desc');});
  rows.sort((a,b)=>{const ta=a.cells[col]?.textContent.trim()||'',tb2=b.cells[col]?.textContent.trim()||'';
    const na=parseFloat(ta.replace(/[^0-9.\-+]/g,'')),nb=parseFloat(tb2.replace(/[^0-9.\-+]/g,''));
    if(!isNaN(na)&&!isNaN(nb))return asc?na-nb:nb-na;return asc?ta.localeCompare(tb2):tb2.localeCompare(ta);});
  rows.forEach(r=>tb.appendChild(r));
}

// ═══ BOOT ════════════════════════════════════════════════════════════════════
init();
</script>
"""

html = HTML_HEAD + HTML_BODY.replace('GENERATED_AT', generated_at) + HTML_DATA + HTML_LOGIC + "\n</body>\n</html>"
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(html)
size_kb = os.path.getsize(OUTPUT_FILE) / 1024
print(f"\nDone! {OUTPUT_FILE} ({size_kb:.0f} KB)")
print(f"Open: file:///{OUTPUT_FILE.replace(chr(92), '/')}")

# ── Auto-deploy to GitHub Pages ──────────────────────────────────────────────
import shutil, subprocess

DEPLOY_DIR = os.path.join(os.path.expanduser("~"), "tmp_deploy")
GH_EXE = os.path.join(os.path.expanduser("~"), "gh_cli", "bin", "gh.exe")

if os.path.isdir(os.path.join(DEPLOY_DIR, ".git")):
    shutil.copy2(OUTPUT_FILE, os.path.join(DEPLOY_DIR, "index.html"))
    try:
        subprocess.run(["git", "add", "index.html"], cwd=DEPLOY_DIR, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Update dashboard {generated_at}"],
                       cwd=DEPLOY_DIR, check=True, capture_output=True)
        try:
            subprocess.run(["git", "push"], cwd=DEPLOY_DIR, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            subprocess.run(["git", "pull", "--rebase"], cwd=DEPLOY_DIR, capture_output=True)
            subprocess.run(["git", "push"], cwd=DEPLOY_DIR, check=True, capture_output=True)
        print("\nGitHub Pages updated! https://perfectjjong.github.io/extra-ac-price-tracker/")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ""
        if "nothing to commit" in stderr:
            print("\nGitHub: No changes to deploy (same as last push).")
        else:
            print(f"\nGitHub deploy failed: {stderr}")
else:
    print("\nSkipped GitHub deploy (repo not found at ~/tmp_deploy).")

# ── Auto-deploy to Cloudflare Pages (via Shaker-MD-App repo) ────────────────
SHAKER_REPO = os.path.join(os.path.expanduser("~"), "shaker-md-app")
CF_DASH_PATH = os.path.join(SHAKER_REPO, "docs", "dashboards", "extra-price", "index.html")

if os.path.isdir(os.path.join(SHAKER_REPO, ".git")):
    try:
        subprocess.run(["git", "pull", "--rebase"], cwd=SHAKER_REPO, capture_output=True, timeout=30)
        shutil.copy2(OUTPUT_FILE, CF_DASH_PATH)
        subprocess.run(["git", "add", CF_DASH_PATH], cwd=SHAKER_REPO, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Update extra-price dashboard {generated_at}"],
                       cwd=SHAKER_REPO, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=SHAKER_REPO, check=True, capture_output=True, timeout=30)
        print("\nCloudflare Pages updated! https://shaker-dashboard.pages.dev/dashboards/extra-price/")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ""
        if "nothing to commit" in stderr:
            print("\nCloudflare: No changes to deploy (same as last push).")
        else:
            print(f"\nCloudflare deploy failed: {stderr[:200]}")
    except Exception as e:
        print(f"\nCloudflare deploy error: {e}")
else:
    print("\nSkipped Cloudflare deploy (Shaker-MD-App repo not found at ~/shaker-md-app).")
