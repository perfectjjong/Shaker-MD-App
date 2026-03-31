"""Fix dark mode readability for all 10 Price Tracking dashboards"""
import os
import re

DASHBOARDS_DIR = os.path.join(os.path.dirname(__file__), 'docs', 'dashboards')

PRICE_DASHBOARDS = [
    'extra-price', 'almanea-price', 'blackbox-price', 'alkhunaizan-price',
    'bh-price', 'binmomen-price', 'sws-price', 'najm-price',
    'technobest-price', 'tamkeen-price'
]

# Comprehensive dark mode CSS for price tracker readability
DARK_MODE_ADDITIONS = """
/* === DARK MODE: KPI card backgrounds (readability fix) === */
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
/* KPI card text colors (bright for dark bg) */
.text-amber-700,.text-amber-600{color:#fbbf24!important}
.text-blue-600{color:#60a5fa!important}
.text-orange-600,.text-orange-700{color:#fb923c!important}
.text-teal-600,.text-teal-700{color:#2dd4bf!important}
.text-purple-700{color:#c4b5fd!important}
.text-cyan-600{color:#22d3ee!important}
/* New/Disc card borders */
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
/* Select dropdowns */
select{background:#0f172a!important;color:#e2e8f0!important;border-color:#475569!important}
/* Reset/filter buttons */
.bg-gray-100{background:#334155!important;color:#e2e8f0!important}
.bg-gray-100:hover,.bg-gray-200{background:#475569!important}
.bg-gray-50{background:#1e293b!important}
.text-gray-600{color:#e2e8f0!important}
"""

# Full dark mode block for dashboards that don't have it at all (like bh-price)
FULL_DARK_MODE = """
/* === DARK MODE OVERRIDE (sell-thru-progress unified) === */
body{background:#0f172a!important;color:#e2e8f0!important}
header{background:linear-gradient(135deg,#1e293b,#334155)!important;border-bottom:2px solid #3b82f6}
.bg-white,.bg-gray-50,.bg-gray-100{background:#1e293b!important}
.bg-white\\/95{background:rgba(30,41,59,.95)!important}
section{background:#1e293b!important;border-color:#334155!important}
.border-gray-100,.border-gray-200,.border-gray-300{border-color:#334155!important}
.text-gray-800,.text-gray-700,.text-gray-600,.text-gray-500{color:#e2e8f0!important}
.text-gray-400{color:#94a3b8!important}
.text-navy-800{color:#60a5fa!important}
.bg-navy-800{background:#3b82f6!important}
.bg-navy-50{background:#1e3a5f!important}
.tbl-wrap td{border-bottom-color:#334155!important;color:#e2e8f0}
.tbl-wrap tr:nth-child(even) td{background:#1e293b!important}
.tbl-wrap tr:nth-child(odd) td{background:#0f172a!important}
.tbl-wrap tr:hover td{background:#334155!important}
.tbl-wrap th{background:#334155!important;color:#ffffff!important}
.tbl-wrap th:hover{background:#475569!important}
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
.shadow-lg{box-shadow:0 8px 24px rgba(0,0,0,.4)!important}
.backdrop-blur{backdrop-filter:blur(8px)}
a[class*="bg-white"]{background:#1e293b!important;color:#94a3b8!important;border-color:#334155!important}
a[class*="bg-white"]:hover{background:#334155!important}
.bg-gray-700{background:#334155!important}
.bg-green-600{background:#10b981!important}
.bg-green-700{background:#059669!important}
.text-green-700,.text-green-600{color:#34d399!important}
.text-red-700,.text-red-600{color:#f87171!important}
.text-purple-600{color:#a78bfa!important}
nav .flex .px-3.py-1{border-color:#334155!important}
.w-px{background:#334155!important}
input[type=checkbox]{accent-color:#3b82f6}
.type-cat{background:#3b82f6!important}.type-comp{background:#60a5fa!important}.type-hc{background:#f59e0b!important;color:#422006!important}.type-ton{background:#475569!important;color:#e2e8f0!important}
.space-y-2>*+*{border-color:#334155}
.text-blue-200{color:#93c5fd!important}
.text-blue-100{color:#bfdbfe!important}
""" + DARK_MODE_ADDITIONS

fixed = []
for dash in PRICE_DASHBOARDS:
    fpath = os.path.join(DASHBOARDS_DIR, dash, 'index.html')
    if not os.path.exists(fpath):
        print(f"SKIP {dash}: file not found")
        continue

    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    has_dark_mode = 'DARK MODE OVERRIDE' in content

    if has_dark_mode:
        # Check if additions already applied
        if 'KPI card backgrounds (readability fix)' in content:
            print(f"SKIP {dash}: already fixed")
            continue
        # Insert additions before </style>
        content = content.replace('</style></head>', DARK_MODE_ADDITIONS + '\n</style></head>')
    else:
        # Insert full dark mode + additions before </style>
        content = content.replace('</style></head>', FULL_DARK_MODE + '\n</style></head>')

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)

    fixed.append(dash)
    print(f"FIXED {dash} ({'added to existing' if has_dark_mode else 'full dark mode added'})")

print(f"\nTotal fixed: {len(fixed)}/{len(PRICE_DASHBOARDS)}")
