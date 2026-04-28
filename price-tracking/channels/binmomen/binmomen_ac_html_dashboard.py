#!/usr/bin/env python3
"""
Bin Momen AC Price Tracking - HTML Dashboard
Sections: KPIs, Price Alerts, New/Disc, Category KPI, Brand Compare, Price Trend, Full SKU, Stock
Based on Black Box v2 template, adapted for Bin Momen data structure.
"""
import os, sys, json, math, shutil, subprocess
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Missing: {e}\nRun: pip install pandas openpyxl numpy"); sys.exit(1)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE  = os.path.join(CURRENT_DIR, "Binmomen_AC_Data.xlsx")
OUTPUT_FILE = os.path.join(CURRENT_DIR, "binmomen_ac_dashboard.html")

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
df = pd.read_excel(INPUT_FILE)
print(f"      {len(df):,} rows, columns: {list(df.columns)}")

# Parse Scrape_Date → date_only
df['Scrape_Date'] = pd.to_datetime(df['Scrape_Date'])
df['date_only'] = df['Scrape_Date'].dt.date

# Numeric coercion
for col in ['Tonnage', 'Original_Price', 'Sale_Price', 'Stock_Qty', 'BTU']:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

# Discount rate from string like "10%" → 0.10
df['Discount_Rate'] = df['Discount'].str.replace('%', '').str.strip()
df['Discount_Rate'] = pd.to_numeric(df['Discount_Rate'], errors='coerce') / 100.0

# Fill missing discount rate from prices
missing_dr = df['Discount_Rate'].isna()
valid = missing_dr & df['Original_Price'].notna() & df['Sale_Price'].notna() & (df['Original_Price'] > 0)
df.loc[valid, 'Discount_Rate'] = 1 - df.loc[valid, 'Sale_Price'] / df.loc[valid, 'Original_Price']

# In_Stock boolean
df['_in_stock'] = df['In_Stock'].str.strip().str.lower() == 'yes'

# Use SKU as unique identifier
df['_sku'] = df['SKU'].fillna(df['Product_Name_EN'])

all_dates = sorted(df['date_only'].unique())
latest_date = str(all_dates[-1])
first_date = str(all_dates[0])

# Stock status
STOCK_RULES = [
    {'label': 'Out of Stock', 'min': None, 'max': 0},
    {'label': 'Critical', 'min': 0, 'max': 5},
    {'label': 'Low', 'min': 5, 'max': 15},
    {'label': 'High', 'min': 15, 'max': 50},
    {'label': 'OK', 'min': 50, 'max': None},
]

# ── Serialize ─────────────────────────────────────────────────────────────────
print("[2/3] Serializing data...")
records = []
for _, r in df.iterrows():
    records.append({
        'd': str(r['date_only']) if pd.notna(r.get('Scrape_Date')) else None,
        'b': safe(r.get('Brand')),
        'n': str(r.get('Product_Name_EN',''))[:70] if pd.notna(r.get('Product_Name_EN')) else '',
        'm': str(r.get('SKU','')) if pd.notna(r.get('SKU')) else '',
        's': str(r.get('_sku','')),  # unique key
        'c': safe(r.get('Category')),
        'h': safe(r.get('Cooling_Type')),
        'inv': safe(r.get('Inverter')),
        't': safe(r.get('Tonnage')),
        'cp': safe(r.get('Compressor')),
        'sp': safe(r.get('Original_Price')),
        'sl': safe(r.get('Sale_Price')),
        'dr': safe(r.get('Discount_Rate')),
        'fp': safe(r.get('Sale_Price')),  # "effective" = Sale_Price for Bin Momen
        'ins': bool(r.get('_in_stock')) if pd.notna(r.get('_in_stock')) else False,
        'stk': safe(r.get('Stock_Qty')),
        'url': str(r.get('Product_URL','')) if pd.notna(r.get('Product_URL')) else '',
        'btu': safe(r.get('BTU')),
        'war': str(r.get('Warranty','')) if pd.notna(r.get('Warranty')) else '',
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
cooling_list = sorted(df['Cooling_Type'].dropna().unique().tolist())
inverter_list = sorted(df['Inverter'].dropna().unique().tolist())
ton_list = sorted(df['Tonnage'].dropna().unique().tolist())

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
<title>Bin Momen AC Price Tracker</title>
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
.level-cool td{background:#eff6ff!important;font-weight:600;border-left:4px solid #60a5fa}
.level-inv td{background:#fef9c3!important;font-weight:500;border-left:4px solid #facc15}
.level-ton td{background:#fff!important;color:#475569;border-left:4px solid #d1d5db}
.type-badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.3px}
.type-cat{background:#2563eb;color:#fff}.type-cool{background:#60a5fa;color:#fff}.type-inv{background:#facc15;color:#713f12}.type-ton{background:#e5e7eb;color:#374151}
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
.sec-search{font-size:11px;border:1px solid #d1d5db;border-radius:6px;padding:3px 8px;background:#fff;width:160px}
.sec-search:focus{outline:none;border-color:#2E75B6;box-shadow:0 0 0 2px rgba(46,117,182,.15)}
.stk-badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.3px}
.stk-ok{background:#dcfce7;color:#166534}.stk-high{background:#dbeafe;color:#1e40af}.stk-low{background:#fef9c3;color:#854d0e}.stk-critical{background:#fee2e2;color:#991b1b}.stk-out{background:#fecaca;color:#7f1d1d}
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
  <div class="max-w-[1600px] mx-auto px-4 sm:px-6 py-3 sm:py-4 flex flex-wrap items-center justify-between gap-2 sm:gap-4">
    <div><h1 class="text-base sm:text-xl font-bold tracking-wide">Bin Momen AC Price Tracker</h1>
      <p class="text-xs text-blue-200 mt-1">Saudi Arabia &middot; Air Conditioners &middot; Daily Price Monitoring</p></div>
    <div class="text-right text-xs text-blue-100 space-y-0.5">
      <div><b class="text-white">Last Updated:</b> <span id="metaDate"></span></div>
      <div><b class="text-white">Period:</b> <span id="metaPeriod"></span></div>
      <div><b class="text-white">SKUs:</b> <span id="metaSku"></span></div></div>
  </div>
</header>

<!-- GLOBAL FILTER BAR -->
<div class="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-gray-200 shadow-sm no-print">
  <div class="max-w-[1600px] mx-auto px-3 sm:px-6 py-2 sm:py-2.5 flex flex-wrap items-center gap-2">
    <span class="text-[10px] font-bold text-navy-700 uppercase tracking-wider">Global</span>
    <div id="gf_date"></div>
    <div class="w-px h-5 bg-gray-300"></div>
    <div id="gf_cat"></div><div id="gf_cool"></div><div id="gf_inv"></div><div id="gf_ton"></div><div id="gf_brand"></div>
    <div class="w-px h-5 bg-gray-300"></div>
    <span id="gf_count" class="text-xs text-gray-500 font-medium"></span>
    <button type="button" onclick="resetGlobal()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-600 rounded px-2.5 py-1 font-medium">Reset</button>
    <span id="gf_compare" class="text-[10px] text-gray-400 ml-auto"></span>
  </div>
</div>

<nav class="max-w-[1600px] mx-auto px-3 sm:px-6 pt-2 sm:pt-3 no-print">
  <div class="flex flex-wrap gap-1.5 text-[11px] pb-1">
    <a href="#sec-kpi" class="px-3 py-1 bg-navy-800 text-white rounded-full font-medium">KPIs</a>
    <a href="#sec-alert" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Price Alerts</a>
    <a href="#sec-new" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">New/Disc</a>
    <a href="#sec-catKPI" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Category KPI</a>
    <a href="#sec-brand" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Brand Compare</a>
    <a href="#sec-trend" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Price Trend</a>
    <a href="#sec-sku" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Full SKU</a>
    <a href="#sec-stock" class="px-3 py-1 bg-white text-navy-800 rounded-full border border-gray-200 hover:bg-navy-50">Stock</a>
  </div>
</nav>

<main class="max-w-[1600px] mx-auto px-2 sm:px-6 py-2 sm:py-3 space-y-2 sm:space-y-3">

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

<!-- SEC 4: Category KPI -->
<section id="sec-catKPI" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Category KPI Table</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s4_cat"></div><div id="s4_cool"></div><div id="s4_inv"></div><div id="s4_ton"></div><div id="s4_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s4_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <button type="button" onclick="resetS4()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div class="tbl-wrap" style="max-height:480px;overflow-y:auto"><table id="tblCatKPI"><thead></thead><tbody></tbody></table></div>
</section>

<!-- SEC 5: Brand Compare -->
<section id="sec-brand" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Brand Price Comparison</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s5_cat"></div><div id="s5_cool"></div><div id="s5_inv"></div><div id="s5_ton"></div><div id="s5_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s5_search" placeholder="Search SKU/Model..." class="sec-search"/>
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

<!-- SEC 6: Price Trend -->
<section id="sec-trend" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Price Trend (Time Series)</h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s6_cat"></div><div id="s6_cool"></div><div id="s6_inv"></div><div id="s6_ton"></div><div id="s6_brand"></div>
    <div class="w-px h-5 bg-gray-200"></div>
    <input type="text" id="s6_search" placeholder="Search SKU/Model..." class="sec-search"/>
    <div class="flex rounded-lg overflow-hidden border border-gray-200">
      <button type="button" class="agg-btn active px-3 py-1 text-[10px] font-medium bg-navy-800 text-white" data-agg="avg">Avg</button>
      <button type="button" class="agg-btn px-3 py-1 text-[10px] font-medium bg-gray-50 text-gray-600" data-agg="min">Min</button></div>
    <button type="button" onclick="resetS6()" class="text-[10px] bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0.5">Reset</button>
  </div>
  <div style="height:400px"><canvas id="trendChart"></canvas></div>
</section>

<!-- SEC 7: Full SKU -->
<section id="sec-sku" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Full SKU Table <span id="skuDateLabel" class="text-xs font-normal text-gray-400"></span></h2>
  <div class="flex flex-wrap items-center gap-2 mb-3 pb-2 border-b border-gray-100">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s7_cat"></div><div id="s7_cool"></div><div id="s7_inv"></div><div id="s7_ton"></div><div id="s7_brand"></div>
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
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">Stock Dashboard</h2>
  <div class="filter-bar flex flex-wrap items-center gap-1.5 mb-3">
    <span class="text-[10px] font-bold text-gray-400 uppercase">Filters</span>
    <div id="s8_date"></div>
    <div id="s8_cat"></div><div id="s8_cool"></div><div id="s8_inv"></div><div id="s8_ton"></div><div id="s8_brand"></div>
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

</main>
<footer class="text-center py-3 text-[10px] text-gray-400">Bin Momen AC Price Tracking Dashboard &middot; Generated GENERATED_AT</footer>
"""

HTML_DATA = f"""<script>
const DATA={json.dumps(records,ensure_ascii=False)};
const DATE_META={json.dumps(date_meta)};
const DATES={json.dumps(dates_list)};
const BRANDS={json.dumps(brands_list)};
const CATEGORIES={json.dumps(categories_list)};
const COOLING={json.dumps(cooling_list)};
const INVERTER={json.dumps(inverter_list)};
const TONS={json.dumps([float(t) for t in ton_list])};
const LATEST_DATE={json.dumps(latest_date)};
const FIRST_DATE={json.dumps(first_date)};
const BRAND_COLORS={json.dumps(BRAND_COLORS)};
const STOCK_RULES={json.dumps(STOCK_RULES)};
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
const searchMatch=(r,q)=>!q||((r.b||'')+(r.s||'')+(r.m||'')+(r.n||'')+(r.c||'')+(r.h||'')+(r.inv||'')+(r.t||'')).toLowerCase().includes(q);

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

// ═══ FILTER HELPERS ═════════════════════════════════════════════════════════
function makeFilters(prefix,cb){
  return {
    cat: new MS(document.getElementById(prefix+'_cat'),CATEGORIES,'Category',cb),
    cool: new MS(document.getElementById(prefix+'_cool'),COOLING,'Cooling',cb),
    inv: new MS(document.getElementById(prefix+'_inv'),INVERTER,'Inverter',cb),
    ton: new MS(document.getElementById(prefix+'_ton'),TONS.map(String),'Ton',cb),
    brand: new MS(document.getElementById(prefix+'_brand'),BRANDS,'Brand',cb,colorOf),
  };
}
function applyF(rows,f){
  return rows.filter(r=>{
    if(r.c!=null&&!f.cat.getSelected().has(r.c))return false;
    if(r.h!=null&&!f.cool.getSelected().has(r.h))return false;
    if(r.inv!=null&&!f.inv.getSelected().has(r.inv))return false;
    if(r.t!=null&&!f.ton.getSelected().has(String(r.t)))return false;
    if(r.b!=null&&!f.brand.getSelected().has(r.b))return false;
    return true;
  });
}
function resetF(f){f.cat.reset();f.cool.reset();f.inv.reset();f.ton.reset();f.brand.reset();}
function syncToSection(src,tgt){
  tgt.cat.setSelected([...src.cat.getSelected()]);
  tgt.cool.setSelected([...src.cool.getSelected()]);
  tgt.inv.setSelected([...src.inv.getSelected()]);
  tgt.ton.setSelected([...src.ton.getSelected()]);
  tgt.brand.setSelected([...src.brand.getSelected()]);
}

function cascadeFilters(data,f){
  const dims=[
    {key:'cat',field:'c',ms:f.cat},
    {key:'cool',field:'h',ms:f.cool},
    {key:'inv',field:'inv',ms:f.inv},
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

// ═══ GLOBAL STATE ═══════════════════════════════════════════════════════════
let GF, S4F, S5F, S6F, S7F, S8F;
let gfDate,s8Date;
const ST={alertDir:'all',s4q:'',s5q:'',s6q:'',s7q:'',s8q:'',skuStock:'all',stkDir:'all',s5agg:'avg',s6agg:'avg'};

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
  S7F=makeFilters('s7',renderS7);
  s8Date=new MS(document.getElementById('s8_date'),DATES,'Date',renderStock);
  S8F=makeFilters('s8',renderStock);

  const searchIds=[['s4_search','s4q',renderS4],['s5_search','s5q',renderS5],['s6_search','s6q',renderS6],['s7_search','s7q',renderS7],['s8_search','s8q',renderStock]];
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
    document.querySelectorAll('.s5agg-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');
    ST.s5agg=btn.dataset.agg;renderS5();
  }));
  document.querySelectorAll('.agg-btn').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('.agg-btn').forEach(b=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600')});
    btn.classList.add('active');btn.className=btn.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');
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

// ═══ GLOBAL REFRESH ═════════════════════════════════════════════════════════
function refreshGlobal(){
  const {cur,prev}=getCompareDates();
  const curData=applyF(DATA.filter(r=>r.d===cur),GF);
  const prevData=prev?applyF(DATA.filter(r=>r.d===prev),GF):[];
  document.getElementById('gf_count').textContent=curData.length+' SKUs';
  document.getElementById('gf_compare').textContent='Viewing: '+cur+(prev?' vs '+prev:'');
  document.getElementById('metaSku').textContent=curData.length;

  syncToSection(GF,S4F);syncToSection(GF,S5F);syncToSection(GF,S6F);syncToSection(GF,S7F);
  s8Date.setSelected([...gfDate.getSelected()]);syncToSection(GF,S8F);

  const allCurDate=DATA.filter(r=>gfDate.getSelected().has(r.d));
  cascadeFilters(allCurDate,GF);

  renderKPIs(curData,prevData);renderAlerts();renderNewDisc(curData,prevData);
  renderS4();renderS5();renderS6();renderS7();renderStock();
}

function resetGlobal(){gfDate.reset();resetF(GF);refreshGlobal();}
function resetS4(){resetF(S4F);ST.s4q='';document.getElementById('s4_search').value='';renderS4();}
function resetS5(){resetF(S5F);ST.s5q='';ST.s5agg='avg';document.getElementById('s5_search').value='';
  document.querySelectorAll('.s5agg-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');}});renderS5();}
function resetS6(){resetF(S6F);ST.s6q='';ST.s6agg='avg';document.getElementById('s6_search').value='';
  document.querySelectorAll('.agg-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-navy-800 text-white/g,'bg-gray-50 text-gray-600');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50 text-gray-600/g,'bg-navy-800 text-white');}});renderS6();}
function resetS7(){resetF(S7F);ST.s7q='';ST.skuStock='all';document.getElementById('s7_search').value='';
  document.querySelectorAll('.stock-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');}});renderS7();}
function resetStock(){s8Date.reset();resetF(S8F);ST.s8q='';ST.stkDir='all';document.getElementById('s8_search').value='';
  document.getElementById('s8_from').value=DATES.length>=2?DATES[DATES.length-2]:DATES[0];
  document.getElementById('s8_to').value=LATEST_DATE;
  document.querySelectorAll('.stk-dir-btn').forEach((b,i)=>{b.classList.remove('active');b.className=b.className.replace(/bg-gray-700 text-white/g,'bg-gray-50');if(i===0){b.classList.add('active');b.className=b.className.replace(/bg-gray-50(?!\s)/g,'bg-gray-700 text-white');}});renderStock();}

// ═══ SEC 1: KPIs ═════════════════════════════════════════════════════════════
function renderKPIs(lat,prev){
  const lm={};lat.forEach(r=>lm[r.s]=r.fp);const pm={};prev.forEach(r=>pm[r.s]=r.fp);
  let up=0,dn=0;Object.keys(lm).filter(s=>s in pm).forEach(s=>{const d=(lm[s]||0)-(pm[s]||0);if(d>0)up++;else if(d<0)dn++;});
  const nw=lat.filter(r=>!(r.s in pm)).length,rm=prev.filter(r=>!(r.s in lm)).length;
  const inStk=lat.filter(r=>r.stk!=null&&r.stk>0).length;
  const ad=lat.filter(r=>r.dr!=null);const avgD=ad.length?mean(ad.map(r=>r.dr)):null;
  const af=lat.filter(r=>r.fp!=null);const avgS=af.length?Math.round(mean(af.map(r=>r.fp))):null;
  const cards=[
    {v:lat.length,l:'Total SKUs',c:'border-l-navy-800 bg-navy-50',vc:'text-navy-800'},
    {v:avgD!=null?(avgD*100).toFixed(1)+'%':'-',l:'Avg Discount',c:'border-l-amber-500 bg-amber-50',vc:'text-amber-700'},
    {v:'&#9650; '+up,l:'Price Up',c:'border-l-red-500 bg-red-50',vc:'text-red-600'},
    {v:'&#9660; '+dn,l:'Price Down',c:'border-l-green-500 bg-green-50',vc:'text-green-600'},
    {v:nw,l:'New SKUs',c:'border-l-blue-500 bg-blue-50',vc:'text-blue-600'},
    {v:rm,l:'Removed',c:'border-l-orange-500 bg-orange-50',vc:'text-orange-600'},
    {v:inStk+'/'+lat.length,l:'In Stock',c:'border-l-teal-500 bg-teal-50',vc:'text-teal-600'},
    {v:fmtSAR(avgS),l:'Avg Sale Price',c:'border-l-purple-500 bg-purple-50',vc:'text-purple-700'},
  ];
  document.getElementById('kpiGrid').innerHTML=cards.map(c=>`<div class="rounded-lg border-l-4 ${c.c} p-3"><div class="text-xl font-bold ${c.vc}">${c.v}</div><div class="text-[10px] text-gray-500 mt-1 font-medium">${c.l}</div></div>`).join('');
}

// ═══ SEC 2: ALERTS ══════════════════════════════════════════════════════════
const AC=[{k:'b',l:'Brand'},{k:'s',l:'Product'},{k:'m',l:'SKU'},{k:'c',l:'Category'},{k:'h',l:'Cooling'},{k:'inv',l:'Inverter'},{k:'ton',l:'Ton'},{k:'prev',l:'Prev',f:fmtSAR},{k:'curr',l:'Curr',f:fmtSAR},{k:'chg',l:'Change',f:fmtChg},{k:'chgPct',l:'Chg%',f:fmtPctR}];
function renderAlerts(){
  const {cur,prev}=getCompareDates();
  const latD=applyF(DATA.filter(r=>r.d===cur),GF);
  const prevD=prev?applyF(DATA.filter(r=>r.d===prev),GF):[];
  const lm={};latD.forEach(r=>lm[r.s]=r);const pm={};prevD.forEach(r=>pm[r.s]=r);
  let rows=[];
  Object.keys(lm).filter(s=>s in pm).forEach(s=>{
    const rn=lm[s],ro=pm[s],pn=rn.fp,po=ro.fp;
    if(pn==null||po==null)return;const chg=pn-po;if(Math.abs(chg)<1)return;
    rows.push({b:rn.b,s:rn.n,m:rn.m,c:rn.c,h:rn.h||'-',inv:rn.inv||'-',ton:rn.t!=null?rn.t.toFixed(1)+'T':'-',prev:po,curr:pn,chg,chgPct:po?chg/po*100:0,url:rn.url});
  });
  if(ST.alertDir==='up')rows=rows.filter(r=>r.chg>0);if(ST.alertDir==='down')rows=rows.filter(r=>r.chg<0);
  rows.sort((a,b)=>Math.abs(b.chg)-Math.abs(a.chg));
  const tbl=document.getElementById('tblAlert');
  tbl.querySelector('thead').innerHTML='<tr>'+AC.map((c,i)=>`<th onclick="sortTbl('tblAlert',${i})">${c.l}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=rows.length?rows.map(r=>'<tr>'+AC.map(c=>{let v=c.f?c.f(r[c.k]):(r[c.k]??'-');let cls='';if((c.k==='chg'||c.k==='chgPct')&&r.chg!=null)cls=r.chg>0?'up-cell':'dn-cell';if(c.k==='s'&&r.url)v=`<a href="${r.url}" target="_blank" class="text-blue-600 hover:underline">${v}</a>`;return`<td class="${cls}">${v}</td>`;}).join('')+'</tr>').join(''):'<tr><td colspan="11" class="text-center text-gray-400 py-6">No changes</td></tr>';
}

// ═══ SEC 3: NEW/DISC ════════════════════════════════════════════════════════
function renderNewDisc(lat,prev){
  const ls=new Set(lat.map(r=>r.s)),ps=new Set(prev.map(r=>r.s));
  const nw=lat.filter(r=>!ps.has(r.s)),dc=prev.filter(r=>!ls.has(r.s));
  const card=(r,clr)=>`<div class="border border-${clr}-200 bg-${clr}-50 rounded-lg p-2.5 flex justify-between items-center"><div><span class="text-xs font-bold" style="color:${colorOf(r.b)}">${r.b}</span> <span class="text-[10px] text-gray-400">${r.m||''}</span><div class="text-[11px] mt-0.5 truncate max-w-[280px]">${r.url?`<a href="${r.url}" target="_blank" class="text-blue-600 hover:underline">${r.n}</a>`:r.n}</div><div class="text-[10px] text-gray-400">${r.c||''} &middot; ${r.t?r.t.toFixed(1)+'T':''} &middot; Stock: ${r.stk!=null?r.stk:'N/A'}</div></div><div class="text-sm font-bold text-gray-700">${fmtSAR(r.fp)} SAR</div></div>`;
  document.getElementById('newCards').innerHTML=nw.length?nw.map(r=>card(r,'green')).join(''):'<p class="text-xs text-gray-400 py-3">None</p>';
  document.getElementById('newCount').textContent='('+nw.length+')';
  document.getElementById('discCards').innerHTML=dc.length?dc.map(r=>card(r,'red')).join(''):'<p class="text-xs text-gray-400 py-3">None</p>';
  document.getElementById('discCount').textContent='('+dc.length+')';
}

// ═══ SEC 4: CATEGORY KPI ════════════════════════════════════════════════════
const CK=[{l:'Type',k:'type'},{l:'Segment',k:'label'},{l:'SKUs',k:'cnt'},{l:'Avg Sale',k:'avgP',f:fmtSAR},{l:'Avg Original',k:'avgStd',f:fmtSAR},{l:'Avg Disc %',k:'avgDisc',f:fmtPctR},{l:'In Stock',k:'inStk'},{l:'LG Avg',k:'lgAvg',f:fmtSAR},{l:'LG Gap',k:'lgGap',f:fmtChg},{l:'LG Gap %',k:'lgGapPct',f:fmtPctR}];
const TYPE_BADGE={cat:'<span class="type-badge type-cat">Category</span>',cool:'<span class="type-badge type-cool">Cooling</span>',inv:'<span class="type-badge type-inv">Inverter</span>',ton:'<span class="type-badge type-ton">Ton</span>'};
const CAT_ORDER=['Split AC','Window AC','Floor Standing AC','Portable AC'];
const COOL_ORDER=['Cold Only','Hot & Cold'];
const INV_ORDER=['Yes','No'];

function segKPI(data){
  const cnt=new Set(data.map(r=>r.s)).size;
  const pArr=data.filter(r=>r.fp!=null).map(r=>r.fp);const avgP=pArr.length?Math.round(mean(pArr)):null;
  const sps=data.filter(r=>r.sp!=null).map(r=>r.sp);const avgStd=sps.length?Math.round(mean(sps)):null;
  const drs=data.filter(r=>r.dr!=null).map(r=>r.dr*100);const avgDisc=drs.length?Math.round(mean(drs)*10)/10:null;
  const inStk=data.filter(r=>r.stk!=null&&r.stk>0).length;
  const lgD=data.filter(r=>r.b==='LG'&&r.fp!=null);const lgAvg=lgD.length?Math.round(mean(lgD.map(r=>r.fp))):null;
  const lgGap=(lgAvg!=null&&avgP!=null)?lgAvg-avgP:null;
  const lgGapPct=(lgGap!=null&&lgAvg)?Math.round(lgGap/lgAvg*1000)/10:null;
  return{cnt,avgP,avgStd,avgDisc,inStk,lgAvg,lgGap,lgGapPct};
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
      const invs=INV_ORDER.filter(i=>[...new Set(coolD.map(r=>r.inv))].includes(i));
      invs.forEach(inv=>{
        const invD=coolD.filter(r=>r.inv===inv);if(!invD.length)return;
        rows.push({level:'inv',type:'inv',label:'Inverter: '+inv,...segKPI(invD)});
        const tons=[...new Set(invD.map(r=>r.t))].filter(Boolean).sort((a,b)=>a-b);
        tons.forEach(t=>{
          const tD=invD.filter(r=>r.t===t);if(!tD.length)return;
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
      let cls='';if(c.k==='lgGap'&&r.lgGap!=null)cls=r.lgGap>0?'up-cell':'dn-cell';if(c.k==='lgGapPct'&&r.lgGapPct!=null)cls=r.lgGapPct>0?'up-cell':'dn-cell';
      return`<td class="${cls}">${v}</td>`;
    }).join('')+'</tr>';
  }).join('');
}

// ═══ SEC 5: BRAND COMPARE ══════════════════════════════════════════════════
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
  brandChart=new Chart(ctx,{type:'bar',data:{labels,datasets:[{label:aggLabel5,data:vals,backgroundColor:bg,borderColor:bg,borderWidth:1}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>'SAR '+fmtSAR(c.raw)}},datalabels:{display:true,anchor:'end',align:'right',color:'#1e3a5f',font:{size:10,weight:'bold'},formatter:v=>fmtSAR(v),clip:false}},scales:{x:{ticks:{callback:v=>fmtSAR(v)},grid:{color:'#f0f0f0'},suggestedMax:vals.length?Math.max(...vals)*1.15:undefined},y:{ticks:{font:{size:10}}}}}});
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
        const lgD=tD.filter(r=>r.b==='LG'&&r.fp!=null);row['LG Min']=lgD.length?Math.round(Math.min(...lgD.map(r=>r.fp))):null;
        segs.push(row);
      });});});
  const allC=['seg',...bList,'Mkt','LG Min'],allH=['Segment',...bList,mktLabel5,'LG Min'];
  const tbl=document.getElementById('tblBrandSeg');
  tbl.querySelector('thead').innerHTML='<tr>'+allH.map((h,i)=>`<th onclick="sortTbl('tblBrandSeg',${i})">${h}</th>`).join('')+'</tr>';
  tbl.querySelector('tbody').innerHTML=segs.length?segs.map(r=>'<tr>'+allC.map(k=>`<td>${k==='seg'?r[k]:(r[k]!=null?fmtSAR(r[k]):'-')}</td>`).join('')+'</tr>').join(''):'<tr><td colspan="99" class="text-center text-gray-400 py-4">No data</td></tr>';
}

// ═══ SEC 6: TREND ══════════════════════════════════════════════════════════
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

// ═══ SEC 7: FULL SKU ═══════════════════════════════════════════════════════
const SK=[{k:'b',l:'Brand'},{k:'n',l:'Product'},{k:'m',l:'SKU'},{k:'c',l:'Category'},{k:'h',l:'Cooling'},{k:'inv',l:'Inverter'},{k:'t',l:'Ton',f:v=>v!=null?v.toFixed(1)+'T':'-'},{k:'sp',l:'Original',f:fmtSAR},{k:'fp',l:'Sale',f:fmtSAR},{k:'dr',l:'Disc%',f:fmtPct},{k:'stk',l:'Stock',f:v=>v!=null?v:'-'},{k:'war',l:'Warranty'}];
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
  tbl.querySelector('tbody').innerHTML=lat.length?lat.map(r=>'<tr>'+SK.map(c=>{let v=c.f?c.f(r[c.k]):(r[c.k]??'-');if(c.k==='n'&&r.url)v=`<a href="${r.url}" target="_blank" class="text-blue-600 hover:underline">${v}</a>`;if(c.k==='stk'){const st=stkStatus(r.stk);v=`<span class="stk-badge ${st.cls}">${v}</span>`;}return`<td>${v}</td>`;}).join('')+'</tr>').join(''):'<tr><td colspan="12" class="text-center text-gray-400 py-6">No data</td></tr>';
}

function downloadExcel(){
  const {cur}=getCompareDates();
  let lat=applyF(DATA.filter(r=>r.d===cur),S7F);
  if(ST.s7q)lat=lat.filter(r=>searchMatch(r,ST.s7q));
  if(ST.skuStock==='in')lat=lat.filter(r=>r.stk!=null&&r.stk>0);
  if(ST.skuStock==='out')lat=lat.filter(r=>r.stk==null||r.stk<=0);
  const rows=lat.map(r=>({Brand:r.b,Product:r.n,SKU:r.m,Category:r.c,Cooling:r.h,Inverter:r.inv,Ton:r.t,Original:r.sp,Sale:r.fp,Discount:r.dr!=null?(r.dr*100).toFixed(1)+'%':'',Stock:r.stk,Warranty:r.war,URL:r.url}));
  const ws=XLSX.utils.json_to_sheet(rows);const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'SKUs');
  XLSX.writeFile(wb,'BinMomen_AC_'+cur+'.xlsx');
}

// ═══ SEC 8: STOCK ══════════════════════════════════════════════════════════
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
    {v:total,l:'Total SKUs',c:'border-l-navy-800 bg-navy-50',vc:'text-navy-800'},
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
  stockTrendChart=new Chart(ctx1,{type:'line',data:{labels:DATES,datasets:[{label:'Total Stock',data:trendData,borderColor:'#2E75B6',backgroundColor:'rgba(46,117,182,.1)',borderWidth:2,pointRadius:3,tension:.3,fill:true}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},datalabels:{display:false}},scales:{x:{ticks:{font:{size:10},maxRotation:45}},y:{ticks:{callback:v=>v.toLocaleString()}}}}});

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
  const donutColors=['#2563eb','#f97316','#10b981','#8b5cf6','#f43f5e'];
  const ctx3=document.getElementById('stockCatDonut').getContext('2d');
  if(stockCatDonutChart)stockCatDonutChart.destroy();
  stockCatDonutChart=new Chart(ctx3,{type:'doughnut',data:{labels:cItems.map(x=>x[0]),datasets:[{data:cItems.map(x=>x[1]),backgroundColor:donutColors.slice(0,cItems.length)}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}},datalabels:{display:true,color:'#fff',font:{size:11,weight:'bold'},formatter:(v,ctx)=>{const sum=ctx.dataset.data.reduce((a,b)=>a+b,0);return sum?(v/sum*100).toFixed(0)+'%':'';}}}}});
}

// ═══ BOOT ═══════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded',init);
</script>
"""

# ── Assemble & write ──────────────────────────────────────────────────────────
html = HTML_HEAD + HTML_BODY.replace('GENERATED_AT', generated_at) + HTML_DATA + HTML_LOGIC + "</body></html>"
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(html)
size_kb = os.path.getsize(OUTPUT_FILE) / 1024
print(f"\n✅ Dashboard saved: {OUTPUT_FILE}")
print(f"   Size: {size_kb:.0f} KB")
print(f"   Data: {len(records):,} records, {len(dates_list)} dates, {len(brands_list)} brands")

# ── GitHub Pages Deploy ────────────────────────────────────────────────────────
DEPLOY_DIR = os.path.join(os.path.expanduser("~"), "tmp_deploy_binmomen")
if os.path.isdir(os.path.join(DEPLOY_DIR, ".git")):
    shutil.copy2(OUTPUT_FILE, os.path.join(DEPLOY_DIR, "index.html"))
    subprocess.run(["git", "add", "index.html"], cwd=DEPLOY_DIR)
    subprocess.run(["git", "commit", "-m", f"Update dashboard {generated_at}"], cwd=DEPLOY_DIR)
    result = subprocess.run(["git", "push"], cwd=DEPLOY_DIR)
    if result.returncode != 0:
        subprocess.run(["git", "pull", "--rebase"], cwd=DEPLOY_DIR)
        result = subprocess.run(["git", "push"], cwd=DEPLOY_DIR)
    if result.returncode == 0:
        print("\n🚀 Deployed: https://perfectjjong.github.io/binmomen-ac-dashboard/")
    else:
        print("\n[WARN] Git push failed. Check deploy directory.")
else:
    print(f"\n[SKIP] Deploy dir not found: {DEPLOY_DIR}")

# ── Deploy to Cloudflare (Shaker-MD-App) ──────────────────────
print("\n[Cloudflare] Deploying to Shaker-MD-App...")
SHAKER_DIR = os.path.join(os.path.expanduser("~"), "Shaker-MD-App")
CLOUDFLARE_DEST = os.path.join(SHAKER_DIR, "docs", "dashboards", "binmomen-price")
if os.path.exists(os.path.join(SHAKER_DIR, ".git")):
    os.makedirs(CLOUDFLARE_DEST, exist_ok=True)
    dest = os.path.join(CLOUDFLARE_DEST, "index.html")
    shutil.copy2(OUTPUT_FILE, dest)
    print(f"  📋 Copied to {dest}")
    try:
        subprocess.run(["git", "add", "docs/dashboards/binmomen-price/index.html"],
                       cwd=SHAKER_DIR, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m",
             f"Update Bin Momen Price dashboard ({generated_at})"],
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
