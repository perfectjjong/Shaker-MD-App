#!/usr/bin/env python3
"""Fix dark mode for all 10 Price Tracking dashboards.
1. Copy original files from source directories
2. Inject dark mode CSS
3. Add Chart.js dark mode defaults
4. Update inline chart grid/label colors
"""
import shutil
import re

# Mapping: Shaker-MD-App dashboard dir -> original source file
DASHBOARDS = {
    "extra-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\00. eXtra\00. Raw\extra_ac_dashboard_v2.html",
    "bh-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\01. BH\bh_ac_dashboard_v2.html",
    "sws-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\02. SWS\sws_ac_dashboard.html",
    "najm-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\03. Najm Store\najm_ac_dashboard.html",
    "alkhunaizan-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\04. Al Khunizan\alkhunaizan_ac_dashboard_v2.html",
    "almanea-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\05. Al Manea\almanea_ac_dashboard_v2.html",
    "tamkeen-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\06. Tamkeen\tamkeen_ac_dashboard.html",
    "binmomen-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\07. Bin Momen\binmomen_ac_dashboard.html",
    "blackbox-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\08. Black Box\blackbox_ac_dashboard_v2.html",
    "technobest-price": r"C:\Users\J_park\Documents\2026\01. Work\06. Price Tracking\09. Techno Best\technobest_ac_dashboard.html",
}

DARK_MODE_CSS = """
/* === DARK MODE (sell-thru-progress unified) === */
body{background:#0f172a!important;color:#e2e8f0!important}
header{background:linear-gradient(135deg,#1e293b,#334155)!important;border-bottom:2px solid #3b82f6}
.bg-white,.bg-gray-50{background:#1e293b!important}
.bg-white\\/95{background:rgba(30,41,59,.95)!important}
section{background:#1e293b!important;border-color:#334155!important}
.border-gray-100,.border-gray-200,.border-gray-300{border-color:#334155!important}
.text-gray-800,.text-gray-700,.text-gray-600,.text-gray-500{color:#e2e8f0!important}
.text-gray-400{color:#94a3b8!important}
.text-navy-800{color:#60a5fa!important}
.bg-navy-800{background:#3b82f6!important}
.bg-navy-50{background:#1e3a5f!important}
.tbl-wrap td{border-bottom-color:#334155!important;color:#e2e8f0!important}
.tbl-wrap tr:nth-child(even) td{background:#1e293b!important}
.tbl-wrap tr:nth-child(odd) td{background:#0f172a!important}
.tbl-wrap tr:hover td{background:#334155!important}
.tbl-wrap th{background:#334155!important;color:#ffffff!important}
.tbl-wrap th:hover{background:#475569!important}
.tbl-wrap a{color:#93c5fd!important}
.level-cat td{background:#1e3a5f!important;color:#60a5fa!important;border-left-color:#3b82f6!important}
.level-comp td{background:#172554!important;color:#93c5fd!important;border-left-color:#60a5fa!important}
.level-hc td{background:#422006!important;color:#fbbf24!important;border-left-color:#f59e0b!important}
.level-ton td{background:#0f172a!important;color:#94a3b8!important;border-left-color:#475569!important}
.ms-btn{background:#0f172a!important;color:#e2e8f0!important;border-color:#475569!important}
.ms-btn:hover{border-color:#60a5fa!important;background:#1e293b!important}
.ms-menu{background:#1e293b!important;border-color:#475569!important;box-shadow:0 8px 25px rgba(0,0,0,.4)!important}
.ms-menu .ms-actions{border-bottom-color:#334155!important}
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
.text-\\[10px\\].font-bold.text-gray-400.uppercase{color:#64748b!important}
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
"""

# Chart.js defaults for dark mode - injected after Chart.register(ChartDataLabels)
CHARTJS_DEFAULTS = """
Chart.defaults.color='#94a3b8';
Chart.defaults.borderColor='#334155';
"""

def apply_dark_mode(src_path, dst_path, dashboard_name):
    """Copy original file and apply dark mode modifications."""
    # Read original
    with open(src_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Inject dark mode CSS before </style>
    content = content.replace('</style>', DARK_MODE_CSS + '\n</style>', 1)

    # 2. Add Chart.js defaults after Chart.register(ChartDataLabels)
    content = content.replace(
        "Chart.register(ChartDataLabels);",
        "Chart.register(ChartDataLabels);\n" + CHARTJS_DEFAULTS
    )
    # Also try alternate pattern
    content = content.replace(
        "Chart.register(ChartDataLabels)\n",
        "Chart.register(ChartDataLabels);\n" + CHARTJS_DEFAULTS
    )

    # 3. Update chart grid colors from light (#f0f0f0, #f5f5f5, #eee) to dark-visible (#334155)
    content = content.replace("grid:{color:'#f0f0f0'}", "grid:{color:'#334155'}")
    content = content.replace("grid:{color:'#f5f5f5'}", "grid:{color:'#334155'}")
    content = content.replace("grid:{color:'#eee'}", "grid:{color:'#334155'}")
    content = content.replace("grid:{color:'#e5e7eb'}", "grid:{color:'#334155'}")
    content = content.replace('grid:{color:"#f0f0f0"}', 'grid:{color:"#334155"}')
    content = content.replace('grid:{color:"#f5f5f5"}', 'grid:{color:"#334155"}')

    # 4. Update datalabel colors from dark (#1e3a5f, #333) to light (#e2e8f0) for bar charts
    content = content.replace("color:'#1e3a5f'", "color:'#e2e8f0'")
    content = content.replace("color:'#333'", "color:'#cbd5e1'")

    # 5. Update end label colors for trend charts (fillStyle for ctx2.fillText)
    content = content.replace("ctx2.fillStyle=ds.borderColor||'#333'", "ctx2.fillStyle=ds.borderColor||'#94a3b8'")

    # Write to destination
    with open(dst_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ {dashboard_name}: dark mode applied")

# Process all dashboards
import os
dest_base = r"C:\Users\J_park\Shaker-MD-App\docs\dashboards"

for name, src in DASHBOARDS.items():
    dst = os.path.join(dest_base, name, "index.html")
    if not os.path.exists(src):
        print(f"❌ {name}: source not found: {src}")
        continue
    apply_dark_mode(src, dst, name)

print("\n🎉 All dashboards updated!")
