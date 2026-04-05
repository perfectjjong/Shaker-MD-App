#!/usr/bin/env python3
"""
Al Manea AC Price Tracking - HTML Dashboard V2.1
All filters multi-select, section-level filters, Excel download, Stock dashboard.
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
INPUT_FILE  = os.path.join(CURRENT_DIR, "Almanea_AC_Price_Tracking_Master.xlsx")
OUTPUT_FILE = os.path.join(CURRENT_DIR, "almanea_ac_dashboard_v2.html")

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
df = pd.read_excel(INPUT_FILE, sheet_name='Products_DB')
print(f"      {len(df):,} rows, {df['SKU'].nunique()} unique SKUs")

df['Scraped_At'] = pd.to_datetime(df['Scraped_At'])
df['date_only'] = df['Scraped_At'].dt.date
for col in ['Capacity_Ton','Original_Price','Promo_Price','Final_Promo_Price','AlAhli_Price','Stock']:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# Parse Discount_Pct from string "51%" to float 0.51
df['Discount_Pct_Num'] = pd.to_numeric(
    df['Discount_Pct'].astype(str).str.replace('%','').str.strip(), errors='coerce'
) / 100.0

# Fill missing Final_Promo_Price from Promo_Price
df['Final_Promo_Price'] = df['Final_Promo_Price'].fillna(df['Promo_Price'])

# Backfill nulls from latest known value per SKU
for col_fill in ['Brand','Product_Name','Model','Category','Function','Capacity_Ton','Compressor_Type','URL_Key']:
    if col_fill not in df.columns:
        continue
    lk = df.dropna(subset=[col_fill]).drop_duplicates('SKU', keep='last').set_index('SKU')[col_fill]
    m = df[col_fill].isna()
    df.loc[m, col_fill] = df.loc[m, 'SKU'].map(lk)

# Compute missing discount rate
missing_dr = df['Discount_Pct_Num'].isna()
valid = missing_dr & df['Original_Price'].notna() & df['Promo_Price'].notna() & (df['Original_Price'] > 0)
df.loc[valid, 'Discount_Pct_Num'] = 1 - df.loc[valid, 'Promo_Price'] / df.loc[valid, 'Original_Price']

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
        'm': str(r.get('Model','')) if pd.notna(r.get('Model')) else '',
        's': str(r.get('SKU','')), 'c': safe(r.get('Category')),
        'h': safe(r.get('Function')), 't': safe(r.get('Capacity_Ton')),
        'cp': safe(r.get('Compressor_Type')),
        'sp': safe(r.get('Original_Price')), 'sl': safe(r.get('Promo_Price')),
        'jp': safe(r.get('AlAhli_Price')), 'dr': safe(r.get('Discount_Pct_Num')),
        'fp': safe(r.get('Final_Promo_Price')), 'fj': safe(r.get('AlAhli_Price')),
        'ho': str(r.get('Has_Offer','')) if pd.notna(r.get('Has_Offer')) else 'No',
        'od': str(r.get('Offer_Detail','')) if pd.notna(r.get('Offer_Detail')) else '',
        'fg': str(r.get('Free_Gift','')) if pd.notna(r.get('Free_Gift')) else '',
        'stk': safe(r.get('Stock')),
        'er': str(r.get('Energy_Rating','')) if pd.notna(r.get('Energy_Rating')) else '',
        'btu': safe(r.get('BTU')),
        'u': str(r.get('URL_Key','')) if pd.notna(r.get('URL_Key')) else '',
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
cold_hc_list = sorted(df['Function'].dropna().unique().tolist())
ton_list = sorted(df['Capacity_Ton'].dropna().unique().tolist())

BRAND_COLORS = {b: c for b, c in zip(brands_list, [
    '#1F4E79','#2E75B6','#ED7D31','#A9D18E','#FF0000','#70AD47','#FFC000','#4472C4',
    '#9E480E','#7030A0','#00B0F0','#FF7F7F','#92D050','#FF00FF','#00B050','#C00000',
    '#B4C6E7','#F4B183','#808080','#5B9BD5','#2F4F4F','#D2691E','#4169E1','#228B22'])}

generated_at = datetime.now().strftime('%Y-%m-%d %H:%M')

# ── Build HTML ────────────────────────────────────────────────────────────────
print("[3/3] Generating HTML...")

HTML_HEAD = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Al Manea AC Price Tracker</title>
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
.ms-menu label.ms-disabled{opacity:.35;pointer-events:none}
.ms-menu label.ms-disabled span{text-decoration:line-through}
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
    <div><h1 class="text-xl font-bold tracking-wide">Al Manea AC Price Tracker</h1>
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
    <a href="#sec-promo" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Offer &amp; Gift</a>
    <a href="#sec-sku" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Full SKU</a>
    <a href="#sec-stock" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Stock</a>
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
      <button type="button" class="alert-tab active px-4 py-1 text-xs font-semibold bg-navy-800 text-white" data-tab="sale">Promo Price</button>
      <button type="button" class="alert-tab px-4 py-1 text-xs font-semibold bg-gray-50 text-gray-600" data-tab="jood">Al Ahli</button></div>
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
    <select id="s4_pt" class="pt-sel"><option value="fp">Final Promo</option><option value="fj">Al Ahli</option><option value="sp">Standard</option></select>
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
    <select id="s5_pt" class="pt-sel"><option value="fp">Final Promo</option><option value="fj">Al Ahli</option><option value="sp">Standard</option></select>
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
    <select id="s6_pt" class="pt-sel"><option value="fp">Final Promo</option><option value="fj">Al Ahli</option><option value="sp">Standard</option></select>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="agg-btn active px-3 py-1 text-[10px] font-medium bg-navy-800 text-white" data-agg="avg">Avg</button>
      <button type="button" class="agg-btn px-3 py-1 text-[10px] font-medium bg-gray-50 text-gray-600" data-agg="min">Min</button></div>
    <button type="button" onclick="resetS6()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div style="height:400px"><canvas id="trendChart"></canvas></div>
</section>

<!-- SEC 7: Offer & Gift -->
<section id="sec-promo" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Offer & Gift Analysis</h2>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div style="height:260px"><canvas id="offerDonut"></canvas></div>
    <div style="height:260px"><canvas id="giftBar"></canvas></div>
    <div><h3 class="text-xs font-bold text-gray-600 mb-2">Offer Summary</h3><div class="tbl-wrap" style="max-height:240px;overflow-y:auto"><table id="tblOffer"><thead></thead><tbody></tbody></table></div></div>
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
    <select id="s8_pt" class="pt-sel"><option value="fp">Final Promo</option><option value="fj">Al Ahli</option><option value="sp">Standard</option></select>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="stock-btn active px-2 py-1 text-[10px] font-medium bg-gray-700 text-white" data-val="all">All</button>
      <button type="button" class="stock-btn px-2 py-1 text-[10px] font-medium bg-gray-50 text-green-600" data-val="in">In Stock</button>
      <button type="button" class="stock-btn px-2 py-1 text-[10px] font-medium bg-gray-50 text-red-600" data-val="out">Out</button></div>
    <button type="button" onclick="downloadExcel()" class="text-[10px] bg-green-600 hover:bg-green-700 text-white rounded px-3 py-1 font-semibold flex items-center gap-1">
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
      Excel Download</button>
    <button type="button" onclick="resetS8()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
    <span id="skuCount" class="text-xs text-gray-400 ml-auto"></span>
  </div>
  <div class="tbl-wrap" style="max-height:500px;overflow-y:auto"><table id="tblSku"><thead></thead><tbody></tbody></table></div>
</section>

<!-- SEC 9: Stock Dashboard -->
<section id="sec-stock" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Stock Dashboard</h2>
  <div class="filter-bar flex flex-wrap items-center gap-1.5 mb-3">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s9_date"></div>
    <div id="s9_cat"></div><div id="s9_comp"></div><div id="s9_hc"></div><div id="s9_ton"></div><div id="s9_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s9_search" placeholder="Search SKU/Brand..." class="sec-search"/>
    <button type="button" onclick="resetStock()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
    <span id="s9_compare" class="text-[10px] text-gray-400 ml-auto"></span>
  </div>
  <div id="stockKpiGrid" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2.5 mb-4"></div>
  <h3 class="text-xs font-bold text-gray-500 uppercase mt-2 mb-2">Stock Trend</h3>
  <div style="height:350px" class="mb-4"><canvas id="stockTrendChart"></canvas></div>
  <h3 class="text-xs font-bold text-gray-500 uppercase mt-2 mb-2">Stock Change Comparison</h3>
  <div class="flex flex-wrap items-center gap-2 mb-3">
    <span class="text-[10px] font-bold text-gray-400">Compare</span>
    <select id="s9_from" class="pt-sel"></select>
    <span class="text-xs text-gray-400">&rarr;</span>
    <select id="s9_to" class="pt-sel"></select>
    <div class="w-px h-5 bg-gray-200"></div>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="stk-dir-btn active px-3 py-1 text-xs font-medium bg-gray-700 text-white" data-dir="all">All</button>
      <button type="button" class="stk-dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-green-600" data-dir="inc">Increased</button>
      <button type="button" class="stk-dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-red-600" data-dir="dec">Decreased</button>
      <button type="button" class="stk-dir-btn px-3 py-1 text-xs font-medium bg-gray-50 text-orange-600" data-dir="out">New Stock-out</button></div>
    <span id="s9_chgCount" class="text-[10px] text-gray-400 ml-auto"></span>
  </div>
  <div class="tbl-wrap mb-4" style="max-height:350px;overflow-y:auto"><table id="tblStockAlert"><thead></thead><tbody></tbody></table></div>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div style="height:320px"><canvas id="stockBrandBar"></canvas></div>
    <div style="height:320px"><canvas id="stockCatDonut"></canvas></div>
  </div>
</section>

</main>
<footer class="text-center py-3 text-[10px] text-gray-400">Al Manea AC Price Tracking Dashboard v2.1 &middot; Generated GENERATED_AT</footer>
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
const fmtName=(name,urlKey)=>urlKey?`<a href="https://www.almanea.sa/en/product/${urlKey}" target="_blank" class="text-blue-600 hover:underline">${name}</a>`:name;
const mean=arr=>arr.length?arr.reduce((s,v)=>s+v,0)/arr.length:null;
const searchMatch=(r,q)=>!q||((r.b||'')+(r.s||'')+(r.m||'')+(r.n||'')+(r.c||'')+(r.cp||'')+(r.h||'')+(r.t||'')+(r.od||'')).toLowerCase().includes(q);

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
    menu.appendChild(list);w.appendChild(menu);this.menuEl=menu;
    btn.addEventListener('click',e=>{e.stopPropagation();document.querySelectorAll('.ms-menu.open').forEach(m=>{if(m!==menu)m.classList.remove('open')});menu.classList.toggle('open');});
    this.listEl=list;
    this.el.appendChild(w);this._upd();
  }
  _upd(){const avail=this._availCount();this.btnEl.innerHTML=`${this.label} <b class="text-navy-700">${this.sel.size}/${avail}</b> <span class="text-gray-400 text-[9px]">&#9662;</span>`;}
  _availCount(){let n=0;this.listEl.querySelectorAll('label').forEach(l=>{if(!l.classList.contains('ms-disabled'))n++;});return n||this.opts.length;}
  selectAll(){this.sel=new Set();this.listEl.querySelectorAll('input').forEach(c=>{if(!c.disabled){this.sel.add(c.value);c.checked=true;}else{c.checked=false;}});this._upd();this.cb();}
  selectNone(){this.sel.clear();this.listEl.querySelectorAll('input').forEach(c=>c.checked=false);this._upd();this.cb();}
  reset(){this.selectAll();}
  getSelected(){return this.sel;}
  setSelected(vals){
    this.sel=new Set(vals.map(String));
    this.listEl.querySelectorAll('input').forEach(cb=>{cb.checked=this.sel.has(cb.value);});
    this._upd();
  }
  updateAvailable(availSet){
    this.listEl.querySelectorAll('label').forEach(lbl=>{
      const cb=lbl.querySelector('input');
      const avail=availSet.has(cb.value);
      lbl.classList.toggle('ms-disabled',!avail);
      if(!avail){cb.disabled=true;}else{cb.disabled=false;}
    });
    this._upd();
  }
}
document.addEventListener('click',()=>document.querySelectorAll('.ms-menu.open').forEach(m=>m.classList.remove('open')));

// ═══ FILTER HELPERS ═════════════════════════════════════════════════════════
function makeFilters(prefix,cb){
  return {
    cat: new MS(document.getElementById(prefix+'_cat'),CATEGORIES,'Category',cb),
    comp: new MS(document.getElementById(prefix+'_comp'),COMPRESSORS,'Compressor',cb),
    hc: new MS(document.getElementById(prefix+'_hc'),COLD_HC,'Function',cb),
    ton: new MS(document.getElementById(prefix+'_ton'),TONS.map(String),'Ton',cb),
    brand: new MS(document.getElementById(prefix+'_brand'),BRANDS,'Brand',cb,colorOf),
  };
}
function applyF(rows,f){
  return rows.filter(r=>{
    if(r.c!=null&&!f.cat.getSelected().has(r.c))return false;
    if(r.cp!=null&&!f.comp.getSelected().has(r.cp))return false;
    if(r.h!=null&&!f.hc.getSelected().has(r.h))return false;
    if(r.t!=null&&!f.ton.getSelected().has(String(r.t)))return false;
    if(r.b!=null&&!f.brand.getSelected().has(r.b))return false;
    return true;
  });
}
function resetF(f){f.cat.reset();f.comp.reset();f.hc.reset();f.ton.reset();f.brand.reset();}

function syncToSection(src,tgt){
  tgt.cat.setSelected([...src.cat.getSelected()]);
  tgt.comp.setSelected([...src.comp.getSelected()]);
  tgt.hc.setSelected([...src.hc.getSelected()]);
  tgt.ton.setSelected([...src.ton.getSelected()]);
  tgt.brand.setSelected([...src.brand.getSelected()]);
}

// ═══ CASCADING FILTER ════════════════════════════════════════════════════════
function cascadeFilters(data,f){
  // For each filter dimension, compute available values based on OTHER selected filters
  const dims=[
    {key:'cat',field:'c',ms:f.cat},
    {key:'comp',field:'cp',ms:f.comp},
    {key:'hc',field:'h',ms:f.hc},
    {key:'ton',field:'t',ms:f.ton,toString:true},
    {key:'brand',field:'b',ms:f.brand},
  ];
  dims.forEach(dim=>{
    // Filter data by ALL other dimensions (not this one)
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
    // Collect available values for this dimension
    const avail=new Set();
    filtered.forEach(r=>{
      const v=r[dim.field];
      if(v!=null)avail.add(dim.toString?String(v):String(v));
    });
    dim.ms.updateAvailable(avail);
  });
}

// ═══ GLOBAL STATE ═══════════════════════════════════════════════════════════
let GF, S4F, S5F, S6F, S8F, S9F;
let gfDate,s9Date;
const ST={alertTab:'sale',alertDir:'all',s4q:'',s5q:'',s5agg:'avg',s6q:'',s6agg:'avg',s8q:'',s9q:'',skuStock:'all',stkDir:'all'};

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
  s9Date=new MS(document.getElementById('s9_date'),DATES,'Date',renderStock);
  S9F=makeFilters('s9',renderStock);

  ['s4_pt','s5_pt','s6_pt','s8_pt'].forEach(id=>{
    const el=document.getElementById(id);
    if(el) el.addEventListener('change',()=>{
      if(id==='s4_pt')renderS4();else if(id==='s5_pt')renderS5();else if(id==='s6_pt')renderS6();else renderS8();
    });
  });

  const searchIds=[['s4_search','s4q',renderS4],['s5_search','s5q',renderS5],['s6_search','s6q',renderS6],['s8_search','s8q',renderS8],['s9_search','s9q',renderStock]];
  searchIds.forEach(([id,key,fn])=>{
    let to=null;const el=document.getElementById(id);
    if(el) el.addEventListener('input',e=>{clearTimeout(to);to=setTimeout(()=>{ST[key]=e.target.value.toLowerCase().trim();fn();},150);});
  });

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

  // SKU stock buttons
  document.querySelectorAll('.stock-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.stock-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');
    ST.skuStock=btn.dataset.val;renderS8();
  }));

  // Stock alert direction buttons
  document.querySelectorAll('.stk-dir-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.stk-dir-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');
    ST.stkDir=btn.dataset.dir;renderStock();
  }));

  // Stock From/To date selectors
  const s9From=document.getElementById('s9_from'),s9To=document.getElementById('s9_to');
  DATES.forEach(d=>{s9From.add(new Option(d,d));s9To.add(new Option(d,d));});
  s9From.value=DATES.length>=2?DATES[DATES.length-2]:DATES[0];
  s9To.value=LATEST_DATE;
  s9From.addEventListener('change',renderStock);
  s9To.addEventListener('change',renderStock);

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

  syncToSection(GF,S4F);
  syncToSection(GF,S5F);
  syncToSection(GF,S6F);
  syncToSection(GF,S8F);
  s9Date.setSelected([...gfDate.getSelected()]);
  syncToSection(GF,S9F);

  // Cascade: disable unavailable options based on current date data
  const allCurDate=DATA.filter(r=>gfDate.getSelected().has(r.d));
  cascadeFilters(allCurDate,GF);

  renderKPIs(curData,prevData);
  renderAlerts();
  renderNewDisc(curData,prevData);
  renderS4();
  renderS5();
  renderS6();
  renderPromo(curData);
  renderS8();
  renderStock();
}

function resetGlobal(){gfDate.reset();resetF(GF);refreshGlobal();}
function resetS4(){resetF(S4F);ST.s4q='';document.getElementById('s4_search').value='';document.getElementById('s4_pt').value='fp';renderS4();}
function resetS5(){resetF(S5F);ST.s5q='';ST.s5agg='avg';document.getElementById('s5_search').value='';document.getElementById('s5_pt').value='fp';
  document.querySelectorAll('.s5agg-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');}});
  renderS5();}
function resetS6(){resetF(S6F);ST.s6q='';ST.s6agg='avg';document.getElementById('s6_search').value='';document.getElementById('s6_pt').value='fp';
  document.querySelectorAll('.agg-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');}});
  renderS6();}
function resetS8(){resetF(S8F);ST.s8q='';ST.skuStock='all';document.getElementById('s8_search').value='';document.getElementById('s8_pt').value='fp';
  document.querySelectorAll('.stock-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');}});
  renderS8();}
function resetStock(){s9Date.reset();resetF(S9F);ST.s9q='';ST.stkDir='all';document.getElementById('s9_search').value='';
  document.getElementById('s9_from').value=DATES.length>=2?DATES[DATES.length-2]:DATES[0];
  document.getElementById('s9_to').value=LATEST_DATE;
  document.querySelectorAll('.stk-dir-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');}});
  renderStock();}

// ═══ SEC 1: KPIs ═════════════════════════════════════════════════════════════
function renderKPIs(lat,prev){
  const lm={};lat.forEach(r=>lm[r.s]=r.fp);const pm={};prev.forEach(r=>pm[r.s]=r.fp);
  let up=0,dn=0;Object.keys(lm).filter(s=>s in pm).forEach(s=>{const d=(lm[s]||0)-(pm[s]||0);if(d>0)up++;else if(d<0)dn++;});
  const nw=lat.filter(r=>!(r.s in pm)).length,rm=prev.filter(r=>!(r.s in lm)).length;
  const offers=lat.filter(r=>r.ho==='Yes').length;
  const ad=lat.filter(r=>r.dr!=null);const avgD=ad.length?mean(ad.map(r=>r.dr)):null;
  const af=lat.filter(r=>r.fp!=null);const avgS=af.length?Math.round(mean(af.map(r=>r.fp))):null;
  const cards=[
    {v:lat.length,l:'Total SKUs',c:'border-l-navy-800 bg-navy-50',vc:'text-navy-800'},
    {v:avgD!=null?(avgD*100).toFixed(1)+'%':'-',l:'Avg Discount',c:'border-l-amber-500 bg-amber-50',vc:'text-amber-700'},
    {v:'&#9650; '+up,l:'Price Up',c:'border-l-red-500 bg-red-50',vc:'text-red-600'},
    {v:'&#9660; '+dn,l:'Price Down',c:'border-l-green-500 bg-green-50',vc:'text-green-600'},
    {v:nw,l:'New SKUs',c:'border-l-blue-500 bg-blue-50',vc:'text-blue-600'},
    {v:rm,l:'Removed',c:'border-l-orange-500 bg-orange-50',vc:'text-orange-600'},
    {v:offers,l:'With Offer',c:'border-l-purple-500 bg-purple-50',vc:'text-purple-600'},
    {v:fmtSAR(avgS),l:'Avg Sale (SAR)',c:'border-l-teal-500 bg-teal-50',vc:'text-teal-700'},
  ];
  document.getElementById('kpiGrid').innerHTML=cards.map(c=>`<div class="rounded-lg border-l-4 ${c.c} p-3"><div class="text-xl font-bold ${c.vc}">${c.v}</div><div class="text-[10px] text-gray-500 mt-1 font-medium">${c.l}</div></div>`).join('');
}

// ═══ SEC 2: ALERTS ═══════════════════════════════════════════════════════════
const AC=[{k:'b',l:'Brand'},{k:'s',l:'SKU'},{k:'n',l:'Product Name'},{k:'c',l:'Category'},{k:'cp',l:'Compressor'},{k:'h',l:'Function'},{k:'ton',l:'Ton'},{k:'prev',l:'Prev',f:fmtSAR},{k:'curr',l:'Curr',f:fmtSAR},{k:'chg',l:'Change',f:fmtChg},{k:'chgPct',l:'Chg%',f:fmtPctR}];
function renderAlerts(){
  const {cur,prev}=getCompareDates();
  const latD=applyF(DATA.filter(r=>r.d===cur),GF);
  const prevD=prev?applyF(DATA.filter(r=>r.d===prev),GF):[];
  const pk=ST.alertTab==='sale'?'fp':'fj';
  const lm={};latD.forEach(r=>lm[r.s]=r);const pm={};prevD.forEach(r=>pm[r.s]=r);
  let rows=[];
  Object.keys(lm).filter(s=>s in pm).forEach(s=>{
    const rn=lm[s],ro=pm[s],pn=rn[pk],po=ro[pk];
    if(pn==null||po==null)return;const chg=pn-po;if(Math.abs(chg)<1)return;
    rows.push({b:rn.b,s,n:rn.n,u:rn.u,c:rn.c,cp:rn.cp||'-',h:rn.h||'-',ton:rn.t!=null?rn.t.toFixed(1)+'T':'-',prev:po,curr:pn,chg,chgPct:po?chg/po*100:0});
  });
  if(ST.alertDir==='up')rows=rows.filter(r=>r.chg>0);if(ST.alertDir==='down')rows=rows.filter(r=>r.chg<0);
  rows.sort((a,b)=>Math.abs(b.chg)-Math.abs(a.chg));
  const tbl=document.getElementById('tblAlert');
  tbl.querySelector('thead').innerHTML='<tr>'+AC.map((c,i)=>`<th onclick="sortTbl('tblAlert',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=rows.length?rows.map(r=>'<tr>'+AC.map(c=>{let v=c.f?c.f(r[c.k]):(r[c.k]??'-');let cls='';if((c.k==='chg'||c.k==='chgPct')&&r.chg!=null)cls=r.chg>0?'up-cell':'dn-cell';if(c.k==='n')v=fmtName(r.n,r.u);return`<td class="${cls}">${v}</td>`;}).join('')+'</tr>').join(''):'<tr><td colspan="11" class="text-center text-gray-400 py-6">No changes</td></tr>';
}

// ═══ SEC 3: NEW/DISC ═════════════════════════════════════════════════════════
function renderNewDisc(lat,prev){
  const ls=new Set(lat.map(r=>r.s)),ps=new Set(prev.map(r=>r.s));
  const nw=lat.filter(r=>!ps.has(r.s)),dc=prev.filter(r=>!ls.has(r.s));
  const card=(r,clr)=>`<div class="border border-${clr}-200 bg-${clr}-50 rounded-lg p-2.5 flex justify-between items-center"><div><span class="text-xs font-bold" style="color:${colorOf(r.b)}">${r.b}</span> <span class="text-[10px] text-gray-400">${r.s}</span><div class="text-[11px] text-gray-600 mt-0.5 truncate max-w-[280px]">${fmtName(r.n,r.u)}</div><div class="text-[10px] text-gray-400">${r.c||''} &middot; ${r.t?r.t.toFixed(1)+'T':''}</div></div><div class="text-sm font-bold text-gray-700">${fmtSAR(r.fp)} SAR</div></div>`;
  document.getElementById('newCards').innerHTML=nw.length?nw.map(r=>card(r,'green')).join(''):'<p class="text-xs text-gray-400 py-3">None</p>';
  document.getElementById('newCount').textContent='('+nw.length+')';
  document.getElementById('discCards').innerHTML=dc.length?dc.map(r=>card(r,'red')).join(''):'<p class="text-xs text-gray-400 py-3">None</p>';
  document.getElementById('discCount').textContent='('+dc.length+')';
}

// ═══ SEC 4: CATEGORY KPI ════════════════════════════════════════════════════
const CK=[{l:'Type',k:'type'},{l:'Segment',k:'label'},{l:'SKUs',k:'cnt'},{l:'Avg Price',k:'avgP',f:fmtSAR},{l:'Avg Std',k:'avgStd',f:fmtSAR},{l:'Avg Disc %',k:'avgDisc',f:fmtPctR},{l:'Offers',k:'offerCnt'},{l:'LG Avg',k:'lgAvg',f:fmtSAR},{l:'LG Gap',k:'lgGap',f:fmtChg},{l:'LG Gap %',k:'lgGapPct',f:fmtPctR}];
const TYPE_BADGE={cat:'<span class="type-badge type-cat">Category</span>',comp:'<span class="type-badge type-comp">Compressor</span>',hc:'<span class="type-badge type-hc">Function</span>',ton:'<span class="type-badge type-ton">Ton</span>'};
const CAT_ORDER=['Split AC','Window AC','Floor Standing','Cassette & Ceiling','Portable','Other'];
const COMP_ORDER=['Dual Inverter','Inverter','Fixed Speed','Rotary'];
const HC_ORDER=['Cold Only','Cold/Hot','Cold & Hot'];

function segKPI(data,pk){
  const cnt=new Set(data.map(r=>r.s)).size;
  const pArr=data.filter(r=>r[pk]!=null).map(r=>r[pk]);const avgP=pArr.length?Math.round(mean(pArr)):null;
  const sps=data.filter(r=>r.sp!=null).map(r=>r.sp);const avgStd=sps.length?Math.round(mean(sps)):null;
  const drs=data.filter(r=>r.dr!=null).map(r=>r.dr*100);const avgDisc=drs.length?Math.round(mean(drs)*10)/10:null;
  const offerCnt=data.filter(r=>r.ho==='Yes').length;
  const lgD=data.filter(r=>r.b==='LG'&&r[pk]!=null);const lgAvg=lgD.length?Math.round(mean(lgD.map(r=>r[pk]))):null;
  const lgGap=(lgAvg!=null&&avgP!=null)?lgAvg-avgP:null;
  const lgGapPct=(lgGap!=null&&lgAvg)?Math.round(lgGap/lgAvg*1000)/10:null;
  return{cnt,avgP,avgStd,avgDisc,offerCnt,lgAvg,lgGap,lgGapPct};
}

function renderS4(){
  const {cur}=getCompareDates();
  const pk=document.getElementById('s4_pt').value;
  cascadeFilters(DATA.filter(r=>r.d===cur),S4F);
  let lat=applyF(DATA.filter(r=>r.d===cur),S4F);
  if(ST.s4q)lat=lat.filter(r=>searchMatch(r,ST.s4q));
  const ptLabel={fp:'Final Promo',fj:'Al Ahli',sp:'Standard'}[pk]||'Price';
  CK[3].l='Avg '+ptLabel;
  const rows=[];
  const cats=CAT_ORDER.filter(c=>[...new Set(lat.map(r=>r.c))].includes(c));
  cats.forEach(cat=>{
    const catD=lat.filter(r=>r.c===cat);if(!catD.length)return;
    rows.push({level:'cat',type:'cat',label:cat,...segKPI(catD,pk)});
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
  cascadeFilters(DATA.filter(r=>r.d===cur),S5F);
  let lat=applyF(DATA.filter(r=>r.d===cur),S5F);
  if(ST.s5q)lat=lat.filter(r=>searchMatch(r,ST.s5q));
  const pk=document.getElementById('s5_pt').value;
  const aggFn=ST.s5agg==='min'?(arr=>Math.round(Math.min(...arr))):(arr=>Math.round(mean(arr)));
  const aggLabel=ST.s5agg==='min'?'Min Price':'Avg Price';
  const bAvg={};lat.forEach(r=>{if(r[pk]==null)return;if(!bAvg[r.b])bAvg[r.b]=[];bAvg[r.b].push(r[pk]);});
  let items=Object.entries(bAvg).map(([b,v])=>({b,avg:aggFn(v)})).sort((a,b)=>a.avg-b.avg);
  const labels=items.map(x=>x.b),vals=items.map(x=>x.avg),bg=labels.map(b=>colorOf(b));
  const ctx=document.getElementById('brandBarChart').getContext('2d');
  if(brandChart)brandChart.destroy();
  brandChart=new Chart(ctx,{type:'bar',data:{labels,datasets:[{label:aggLabel,data:vals,backgroundColor:bg,borderColor:bg,borderWidth:1}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>'SAR '+fmtSAR(c.raw)}},datalabels:{display:true,anchor:'end',align:'right',color:'#1e3a5f',font:{size:10,weight:'bold'},formatter:v=>fmtSAR(v),clip:false}},scales:{x:{ticks:{callback:v=>fmtSAR(v)},grid:{color:'#f0f0f0'},suggestedMax:vals.length?Math.max(...vals)*1.15:undefined},y:{ticks:{font:{size:10}}}}}});
  // Segment table
  const segs=[];const bList=[...new Set(lat.map(r=>r.b))].filter(Boolean).sort();
  const cats=[...new Set(lat.map(r=>r.c))].filter(x=>x!=null&&x!=='').sort();
  cats.forEach(cat=>{const cD=lat.filter(r=>r.c===cat);
    [...new Set(cD.map(r=>r.cp))].filter(x=>x!=null&&x!=='').sort().forEach(comp=>{const coD=cD.filter(r=>r.cp===comp);
      [...new Set(coD.map(r=>r.h))].filter(x=>x!=null&&x!=='').sort().forEach(hc=>{const hD=coD.filter(r=>r.h===hc);
        [...new Set(hD.map(r=>r.t))].filter(x=>x!=null&&!isNaN(x)).sort((a,b)=>a-b).forEach(t=>{const tD=hD.filter(r=>r.t===t);if(!tD.length)return;
          const seg=(cat||'')+' / '+(comp||'')+' / '+(hc||'')+' / '+Number(t).toFixed(1)+'T';
          const row={seg};const prices=[];
          bList.forEach(b=>{const bD=tD.filter(r=>r.b===b&&r[pk]!=null);const avg=bD.length?aggFn(bD.map(r=>r[pk])):null;row[b]=avg;if(avg!=null)prices.push(avg);});
          row['Mkt']=prices.length?aggFn(prices):null;
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
  const {cur}=getCompareDates();
  cascadeFilters(DATA.filter(r=>r.d===cur),S6F);
  const pk=document.getElementById('s6_pt').value;
  const q=ST.s6q;
  const aggFn=ST.s6agg==='min'?(arr=>Math.round(Math.min(...arr))):(arr=>Math.round(mean(arr)));
  const aggLabel=ST.s6agg==='min'?'Market Min':'Market Avg';
  let datasets=[];
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
  trendChartObj=new Chart(ctx,{type:'line',data:{labels:DATES,datasets},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},layout:{padding:{right:90}},plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:10}}},tooltip:{callbacks:{label:c=>c.dataset.label+': SAR '+fmtSAR(c.raw)}},datalabels:{display:false}},scales:{x:{ticks:{font:{size:10},maxRotation:45},grid:{color:'#f5f5f5'}},y:{ticks:{callback:v=>fmtSAR(v)},grid:{color:'#f5f5f5'}}}},plugins:[{id:'endLabels',afterDatasetsDraw(chart){const ctx2=chart.ctx;chart.data.datasets.forEach((ds,i)=>{const meta=chart.getDatasetMeta(i);if(!meta.visible)return;for(let j=meta.data.length-1;j>=0;j--){const pt=meta.data[j];if(pt&&ds.data[j]!=null){ctx2.save();ctx2.font='bold 10px Inter,sans-serif';ctx2.fillStyle=ds.borderColor||'#333';ctx2.textBaseline='middle';const lbl=ds.label.length>18?ds.label.substring(0,18)+'..':ds.label;ctx2.fillText(lbl,pt.x+6,pt.y);ctx2.restore();break;}}});}}]});
}

// ═══ SEC 7: OFFER & GIFT ════════════════════════════════════════════════════
let offerD=null,giftB=null;
function renderPromo(lat){
  // Parse offer types from Offer_Detail (pipe-separated)
  const offerCounts={};
  lat.forEach(r=>{
    if(!r.od)return;
    r.od.split('|').map(s=>s.trim()).filter(Boolean).forEach(offer=>{
      const key=offer.length>45?offer.substring(0,45)+'...':offer;
      offerCounts[key]=(offerCounts[key]||0)+1;
    });
  });
  const ol=Object.entries(offerCounts).sort((a,b)=>b[1]-a[1]);
  const topN=ol.slice(0,8);
  const otherSum=ol.slice(8).reduce((s,e)=>s+e[1],0);
  if(otherSum>0)topN.push(['Other',otherSum]);
  const pl=topN.map(x=>x[0]),pv=topN.map(x=>x[1]);
  const pcol=['#1F4E79','#ED7D31','#A9D18E','#FF0000','#70AD47','#FFC000','#4472C4','#9E480E','#7030A0'];
  const c1=document.getElementById('offerDonut').getContext('2d');if(offerD)offerD.destroy();
  offerD=new Chart(c1,{type:'doughnut',data:{labels:pl,datasets:[{data:pv,backgroundColor:pcol.slice(0,pl.length)}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:9}}},title:{display:true,text:'Offer Type Distribution',font:{size:12}}}}});

  // Free Gift by Brand
  const gc={};lat.filter(r=>r.fg&&r.fg.trim()).forEach(r=>{gc[r.b]=(gc[r.b]||0)+1;});
  const gb=Object.keys(gc).sort((a,b)=>gc[b]-gc[a]),gv=gb.map(b=>gc[b]);
  const c2=document.getElementById('giftBar').getContext('2d');if(giftB)giftB.destroy();
  giftB=new Chart(c2,{type:'bar',data:{labels:gb,datasets:[{label:'Free Gift SKUs',data:gv,backgroundColor:gb.map(b=>colorOf(b))}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},title:{display:true,text:'Free Gift by Brand',font:{size:12}}},scales:{y:{ticks:{stepSize:1}}}}});

  // Offer summary table
  const tbl=document.getElementById('tblOffer');
  tbl.querySelector('thead').innerHTML='<tr><th>Offer</th><th>SKUs</th><th>%</th></tr>';
  tbl.querySelector('tbody').innerHTML=ol.length?ol.map(([p,v])=>`<tr><td class="max-w-[200px] truncate" title="${p}">${p}</td><td>${v}</td><td>${(v/lat.length*100).toFixed(1)}%</td></tr>`).join(''):'<tr><td colspan="3" class="text-center text-gray-400 py-4">No offers</td></tr>';
}

// ═══ SEC 8: FULL SKU ════════════════════════════════════════════════════════
const SC=[{k:'b',l:'Brand'},{k:'s',l:'SKU'},{k:'m',l:'Model'},{k:'n',l:'Product Name'},{k:'c',l:'Category'},{k:'cp',l:'Compressor'},{k:'h',l:'Function'},{k:'ton',l:'Ton'},{k:'sp',l:'Std Price',f:fmtSAR},{k:'sl',l:'Promo Price',f:fmtSAR},{k:'jp',l:'Al Ahli',f:fmtSAR},{k:'dr',l:'Disc %',f:fmtPct},{k:'fp',l:'Final Price',f:fmtSAR},{k:'prev',l:'Prev Price',f:fmtSAR},{k:'chg',l:'Change',f:fmtChg},{k:'chgPct',l:'Chg %',f:fmtPctR},{k:'stk',l:'Stock'},{k:'ho',l:'Offer'},{k:'er',l:'Energy'}];
let _skuData=[];

function renderS8(){
  const {cur,prev}=getCompareDates();
  cascadeFilters(DATA.filter(r=>r.d===cur),S8F);
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
  if(ST.skuStock==='in')rows=rows.filter(r=>r.stk!=null&&r.stk>0);
  if(ST.skuStock==='out')rows=rows.filter(r=>r.stk==null||r.stk===0);
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
    if(c.k==='n')v=fmtName(r.n,r.u);
    if(c.k==='ho'&&v==='Yes')v=`<span class="inline-block px-1.5 py-0.5 bg-green-100 text-green-700 rounded-full text-[10px] font-semibold">Offer</span>`;
    if(c.k==='stk'){const sv=r.stk;if(sv!=null&&sv>0)v=`<span class="text-green-600 font-semibold">${sv}</span>`;else if(sv===0||sv==null)v=`<span class="text-red-500 font-semibold">${sv===0?'0':'N/A'}</span>`;}
    return`<td class="${cls}">${v}</td>`;
  }).join('')+'</tr>').join(''):'<tr><td colspan="19" class="text-center text-gray-400 py-6">No data</td></tr>';
}

function downloadExcel(){
  const rows=_skuData;if(!rows.length){alert('No data to download');return;}
  const {cur}=getCompareDates();
  const xlData=rows.map(r=>({
    Brand:r.b,SKU:r.s,Model:r.m,'Product Name':r.n,Category:r.c,Compressor:r.cp,Function:r.h,Ton:r.ton,
    'Std Price':r.sp,'Promo Price':r.sl,'Al Ahli':r.jp,'Disc %':r.dr!=null?Math.round(r.dr*1000)/10:null,
    'Final Price':r.fp,'Prev Price':r.prev,'Change':r.chg,'Change %':r.chgPct,Stock:r.stk,'Has Offer':r.ho,'Energy':r.er
  }));
  const ws=XLSX.utils.json_to_sheet(xlData);
  const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'SKU Data');
  XLSX.writeFile(wb,'Almanea_AC_SKUs_'+cur+'.xlsx');
}

// ═══ SEC 9: STOCK DASHBOARD ═════════════════════════════════════════════════
let stockBrandChartObj=null,stockCatChartObj=null,stockTrendChartObj=null;

function renderStock(){
  // Dates: s9Date controls trend range; From/To controls comparison
  const toDate=document.getElementById('s9_to').value||LATEST_DATE;
  const fromDate=document.getElementById('s9_from').value||(DATES.length>=2?DATES[DATES.length-2]:DATES[0]);
  document.getElementById('s9_compare').textContent='Viewing: '+toDate+' (compare from '+fromDate+')';

  cascadeFilters(DATA.filter(r=>r.d===toDate),S9F);
  let latD=applyF(DATA.filter(r=>r.d===toDate),S9F);
  const prevD=applyF(DATA.filter(r=>r.d===fromDate),S9F);
  if(ST.s9q){latD=latD.filter(r=>searchMatch(r,ST.s9q));}

  // ── 9-1: KPI Cards (based on To date) ─────────────────────────────────────
  const inStock=latD.filter(r=>r.stk!=null&&r.stk>0);
  const outStock=latD.filter(r=>r.stk==null||r.stk===0);
  const totalSkus=latD.length;
  const totalStkQty=inStock.reduce((s,r)=>s+r.stk,0);
  const stockOutRate=totalSkus?(outStock.length/totalSkus*100).toFixed(1)+'%':'0%';
  const brandOut={};outStock.forEach(r=>{brandOut[r.b]=(brandOut[r.b]||0)+1;});
  const topOutBrand=Object.entries(brandOut).sort((a,b)=>b[1]-a[1]);
  const topOutLabel=topOutBrand.length?topOutBrand[0][0]+' ('+topOutBrand[0][1]+')':'-';
  const stkCards=[
    {v:inStock.length,l:'In Stock SKUs',c:'border-l-green-500 bg-green-50',vc:'text-green-600'},
    {v:outStock.length,l:'Out of Stock',c:'border-l-red-500 bg-red-50',vc:'text-red-600'},
    {v:totalStkQty.toLocaleString(),l:'Total Stock Qty',c:'border-l-blue-500 bg-blue-50',vc:'text-blue-600'},
    {v:stockOutRate,l:'Stock-out Rate',c:'border-l-amber-500 bg-amber-50',vc:'text-amber-700'},
    {v:totalSkus,l:'Total SKUs',c:'border-l-navy-800 bg-navy-50',vc:'text-navy-800'},
    {v:topOutLabel,l:'Most Stock-outs',c:'border-l-orange-500 bg-orange-50',vc:'text-orange-600'},
  ];
  document.getElementById('stockKpiGrid').innerHTML=stkCards.map(c=>`<div class="rounded-lg border-l-4 ${c.c} p-3"><div class="text-lg font-bold ${c.vc}">${c.v}</div><div class="text-[10px] text-gray-500 mt-1 font-medium">${c.l}</div></div>`).join('');

  // ── 9-2: Stock Trend Line Chart (all dates) ───────────────────────────────
  const trendDates=[...s9Date.getSelected()].sort();
  const useDates=trendDates.length?trendDates:DATES;
  let stkDS=[];
  // Market total line
  const mktStk=useDates.map(d=>{
    let dd=applyF(DATA.filter(r=>r.d===d),S9F);
    if(ST.s9q)dd=dd.filter(r=>searchMatch(r,ST.s9q));
    return dd.filter(r=>r.stk!=null).reduce((a,r)=>a+r.stk,0);
  });
  stkDS.push({label:'Total',data:mktStk,borderColor:'#6b7280',borderWidth:2,borderDash:[6,3],pointRadius:2,tension:.3,fill:false});
  // Brand lines
  [...S9F.brand.getSelected()].forEach(br=>{
    const vals=useDates.map(d=>{
      let dd=applyF(DATA.filter(r=>r.d===d&&r.b===br),S9F);
      if(ST.s9q)dd=dd.filter(r=>searchMatch(r,ST.s9q));
      const sum=dd.filter(r=>r.stk!=null).reduce((a,r)=>a+r.stk,0);
      return sum||null;
    });
    if(vals.every(v=>v===null||v===0))return;
    const c=colorOf(br);
    stkDS.push({label:br,data:vals,borderColor:c,borderWidth:1.5,pointRadius:2,tension:.3,fill:false,spanGaps:true});
  });
  const tCtx=document.getElementById('stockTrendChart').getContext('2d');
  if(stockTrendChartObj)stockTrendChartObj.destroy();
  stockTrendChartObj=new Chart(tCtx,{type:'line',data:{labels:useDates,datasets:stkDS},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},layout:{padding:{right:90}},plugins:{legend:{position:'bottom',labels:{boxWidth:10,font:{size:10}}},tooltip:{callbacks:{label:c=>c.dataset.label+': '+((c.raw||0).toLocaleString())}},datalabels:{display:false}},scales:{x:{ticks:{font:{size:10},maxRotation:45},grid:{color:'#f5f5f5'}},y:{ticks:{callback:v=>v.toLocaleString()},grid:{color:'#f5f5f5'}}}},plugins:[{id:'stkEndLabels',afterDatasetsDraw(chart){const cx=chart.ctx;chart.data.datasets.forEach((ds,i)=>{const meta=chart.getDatasetMeta(i);if(!meta.visible)return;for(let j=meta.data.length-1;j>=0;j--){const pt=meta.data[j];if(pt&&ds.data[j]!=null){cx.save();cx.font='bold 10px Inter,sans-serif';cx.fillStyle=ds.borderColor||'#333';cx.textBaseline='middle';const lbl=ds.label.length>18?ds.label.substring(0,18)+'..':ds.label;cx.fillText(lbl,pt.x+6,pt.y);cx.restore();break;}}});}}]});

  // ── 9-3: Stock Change Comparison (From vs To) ─────────────────────────────
  const lm={};latD.forEach(r=>lm[r.s]=r);
  const pm={};const prevF=ST.s9q?prevD.filter(r=>searchMatch(r,ST.s9q)):prevD;prevF.forEach(r=>pm[r.s]=r);
  let stkRows=[];
  const allSkus=new Set([...Object.keys(lm),...Object.keys(pm)]);
  allSkus.forEach(s=>{
    const rn=lm[s];const ro=pm[s];
    const curStk=rn?(rn.stk!=null?rn.stk:0):0;
    const prevStk=ro?(ro.stk!=null?ro.stk:0):0;
    if(!rn&&!ro)return;
    const chg=curStk-prevStk;
    if(chg===0)return;
    const ref=rn||ro;
    const isNewOut=curStk===0&&prevStk>0;
    const chgPct=prevStk!==0?((chg/prevStk)*100).toFixed(1)+'%':(curStk>0?'New':'');
    stkRows.push({b:ref.b,s,n:ref.n,u:ref.u,c:ref.c||'-',ton:ref.t!=null?ref.t.toFixed(1)+'T':'-',prevStk,curStk,chg,chgPct,isNewOut});
  });
  if(ST.stkDir==='inc')stkRows=stkRows.filter(r=>r.chg>0);
  if(ST.stkDir==='dec')stkRows=stkRows.filter(r=>r.chg<0);
  if(ST.stkDir==='out')stkRows=stkRows.filter(r=>r.isNewOut);
  stkRows.sort((a,b)=>Math.abs(b.chg)-Math.abs(a.chg));
  document.getElementById('s9_chgCount').textContent=stkRows.length+' changes';

  const saCols=[{k:'b',l:'Brand'},{k:'s',l:'SKU'},{k:'n',l:'Product Name'},{k:'c',l:'Category'},{k:'ton',l:'Ton'},{k:'prevStk',l:fromDate},{k:'curStk',l:toDate},{k:'chg',l:'Change'},{k:'chgPct',l:'Chg%'}];
  const stbl=document.getElementById('tblStockAlert');
  stbl.querySelector('thead').innerHTML='<tr>'+saCols.map((c,i)=>`<th onclick="sortTbl('tblStockAlert',${i})">${c.l}</th>`).join('')+'</tr>';
  stbl.querySelector('tbody').innerHTML=stkRows.length?stkRows.map(r=>'<tr>'+saCols.map(c=>{
    let v=r[c.k]!=null?r[c.k]:'-';let cls='';
    if(c.k==='chg')cls=r.chg>0?'dn-cell':'up-cell';
    if(c.k==='chgPct')cls=r.chg>0?'dn-cell':'up-cell';
    if(c.k==='curStk'&&r.curStk===0)cls='up-cell';
    if(c.k==='b')v=`<span style="color:${colorOf(r.b)};font-weight:600">${v}</span>`;
    if(c.k==='n')v=fmtName(r.n,r.u);
    if(c.k==='chg')v=(r.chg>0?'+':'')+r.chg;
    if(c.k==='prevStk'||c.k==='curStk')v=Number(v).toLocaleString();
    return`<td class="${cls}">${v}</td>`;
  }).join('')+'</tr>').join(''):'<tr><td colspan="9" class="text-center text-gray-400 py-6">No stock changes between selected dates</td></tr>';

  // ── 9-4: Stock Distribution Charts (based on To date) ─────────────────────
  // Brand total stock bar
  const bStk={};latD.filter(r=>r.stk!=null).forEach(r=>{bStk[r.b]=(bStk[r.b]||0)+r.stk;});
  const bStkItems=Object.entries(bStk).map(([b,total])=>({b,total})).sort((a,b)=>b.total-a.total);
  const bLabels=bStkItems.map(x=>x.b),bVals=bStkItems.map(x=>x.total);
  const ctx1=document.getElementById('stockBrandBar').getContext('2d');
  if(stockBrandChartObj)stockBrandChartObj.destroy();
  stockBrandChartObj=new Chart(ctx1,{type:'bar',data:{labels:bLabels,datasets:[{label:'Total Stock',data:bVals,backgroundColor:bLabels.map(b=>colorOf(b))}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},title:{display:true,text:'Total Stock Quantity by Brand ('+toDate+')',font:{size:12}},datalabels:{display:true,anchor:'end',align:'right',color:'#1e3a5f',font:{size:10,weight:'bold'},formatter:v=>v.toLocaleString(),clip:false}},scales:{x:{grid:{color:'#f0f0f0'}},y:{ticks:{font:{size:10}}}}}});
  // Category total stock donut
  const catStk={};latD.filter(r=>r.stk!=null).forEach(r=>{const c=r.c||'Other';catStk[c]=(catStk[c]||0)+r.stk;});
  const cl=Object.keys(catStk),cv=Object.values(catStk);
  const catCols=['#1F4E79','#ED7D31','#A9D18E','#FF0000','#70AD47','#FFC000','#4472C4','#9E480E'];
  const ctx2=document.getElementById('stockCatDonut').getContext('2d');
  if(stockCatChartObj)stockCatChartObj.destroy();
  stockCatChartObj=new Chart(ctx2,{type:'doughnut',data:{labels:cl,datasets:[{data:cv,backgroundColor:catCols.slice(0,cl.length)}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}},title:{display:true,text:'Stock Quantity by Category ('+toDate+')',font:{size:12}},datalabels:{display:true,color:'#fff',font:{size:11,weight:'bold'},formatter:(v,ctx2b)=>{const t=ctx2b.dataset.data.reduce((a,b)=>a+b,0);return t?(v/t*100).toFixed(1)+'%':'';}}}}});
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

DEPLOY_DIR = os.path.join(os.path.expanduser("~"), "tmp_deploy_almanea")
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
        print("\nGitHub Pages updated! https://perfectjjong.github.io/almanea-ac-price-tracker/")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ""
        if "nothing to commit" in stderr:
            print("\nGitHub: No changes to deploy (same as last push).")
        else:
            print(f"\nGitHub deploy failed: {stderr}")
else:
    print("\nSkipped GitHub deploy (repo not found at ~/tmp_deploy_almanea).")

# ── Deploy to Cloudflare (Shaker-MD-App) ──────────────────────
print("\n[Cloudflare] Deploying to Shaker-MD-App...")
SHAKER_DIR = os.path.join(os.path.expanduser("~"), "Shaker-MD-App")
CLOUDFLARE_DEST = os.path.join(SHAKER_DIR, "docs", "dashboards", "almanea-price")
if os.path.exists(os.path.join(SHAKER_DIR, ".git")):
    os.makedirs(CLOUDFLARE_DEST, exist_ok=True)
    dest = os.path.join(CLOUDFLARE_DEST, "index.html")
    shutil.copy2(OUTPUT_FILE, dest)
    print(f"  📋 Copied to {dest}")
    try:
        subprocess.run(["git", "add", "docs/dashboards/almanea-price/index.html"],
                       cwd=SHAKER_DIR, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m",
             f"Update Al Manea Price dashboard ({generated_at})"],
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
