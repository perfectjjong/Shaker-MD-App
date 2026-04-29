#!/usr/bin/env python3
"""
GTM Price Tracking HTML Generator
===================================
각 채널의 스크래핑 Excel 마스터 파일에서 데이터를 자동 로드하여
Split AC Price Tracking HTML 대시보드를 생성합니다.

Features:
- Cold / Hot&Cool 행 분리
- 동일 (Ton, Compressor, Cold/HC) 내 SKU별 개별 표시
- LG vs 경쟁사 가격 색상 비교 (vs LG Mid)
- 채널별 탭 구조

Usage:
    python3 generate_gtm_price_tracking.py
    python3 generate_gtm_price_tracking.py --channel extra sws
"""

import os, sys, re, argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

PT_ROOT = Path(__file__).parent.resolve()
REPO_ROOT = PT_ROOT.parent
OUT_PATH = REPO_ROOT / "docs" / "gtm" / "price_tracking.html"

# ──────────────────────────────────────────────────────────────────────
# LG Segment 결정
# ──────────────────────────────────────────────────────────────────────
INV_SEG_PATTERNS = [
    ('NF12',            'Small · NF12'),
    ('NS',              'Entry · NS'),
    ('ND',              'Mid · ND'),
    ('AM', 'High · AM/AF/NW'), ('AF', 'High · AM/AF/NW'), ('NW', 'High · AM/AF/NW'),
    ('NT',              'Big · NT'),
]
ROT_SEG_PATTERNS = [
    ('LA', 'Mid · LA'), ('LO', 'Mid · LA'), ('LK', 'Mid · LA'),
]

def get_lg_segment(model: str, compressor: str) -> str:
    if not model or not isinstance(model, str):
        return ''
    m = model.upper().replace(' ', '')
    if compressor == 'Inverter':
        for pat, label in INV_SEG_PATTERNS:
            if pat in m:
                return label
    else:
        for pat, label in ROT_SEG_PATTERNS:
            if pat in m:
                return label
    return ''


# ──────────────────────────────────────────────────────────────────────
# Cold/HC 정규화
# ──────────────────────────────────────────────────────────────────────
def norm_cold_hc(val: str) -> str:
    if not val or not isinstance(val, str):
        return 'Cold'
    v = val.lower()
    if any(x in v for x in ['hot', 'heat', 'h&c', 'h/c', 'hc', 'cold/hot']):
        return 'Hot and Cold'
    return 'Cold'


def norm_compressor(val: str) -> str:
    if not val or not isinstance(val, str):
        return 'Rotary'
    v = val.lower()
    if 'inv' in v:
        return 'Inverter'
    return 'Rotary'


def norm_brand(val: str) -> str:
    if not val or not isinstance(val, str):
        return val
    v = val.strip().upper()
    aliases = {
        'LG': 'LG', 'SAMSUNG': 'SAMSUNG', 'GREE': 'GREE', 'HAIER': 'HAIER',
        'MIDEA': 'MIDEA', 'TCL': 'TCL', 'HISENSE': 'HISENSE', 'AUX': 'AUX',
        'ZAMIL': 'ZAMIL', 'PANASONIC': 'PANASONIC',
        'CLASS PRO': 'CLASS PRO', 'CLASSPRO': 'CLASS PRO',
        'SUPER GENERAL': 'SUPER GENERAL', 'SUPERGENERAL': 'SUPER GENERAL',
        'O GENERAL': 'GENERAL', 'O\'GENERAL': 'GENERAL', 'GENERAL': 'GENERAL',
        'WHITE WESTINGHOUSE': 'WESTINGHOUSE', 'WESTINGHOUSE': 'WESTINGHOUSE',
        'GENERAL ELECTRIC': 'GENERAL ELECTRIC', 'MANDO': 'MANDO',
        'DANSAT': 'DANSAT', 'SHARP': 'SHARP', 'BOSCH': 'BOSCH',
        'CARRIER': 'CARRIER', 'DAIKIN': 'DAIKIN', 'YORK': 'YORK',
        'KELVINATOR': 'KELVINATOR', 'CRAFFT': 'CRAFFT', 'NIKAI': 'NIKAI',
        'BASIC': 'BASIC', 'ADMIRAL': 'ADMIRAL', 'TRANE': 'TRANE',
        'HAAM': 'HAAM', 'BANCOOL': 'BANCOOL', 'UNIX': 'UNIX',
        'TECHNO BEST': 'TECHNO BEST', 'TECHNOBEST': 'TECHNO BEST',
        'WANSA': 'WANSA', 'FRIGIDAIRE': 'FRIGIDAIRE',
    }
    for k, mapped in aliases.items():
        if v == k:
            return mapped
    # 대소문자 정규화: Title Case
    return val.strip().title()


def parse_nominal_ton(val) -> float:
    """'1.5 Ton', '2 Ton', '2.5  Ton' → float"""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    return float(m.group(1)) if m else np.nan


# ──────────────────────────────────────────────────────────────────────
# 채널별 로더 → 표준 DataFrame
# 표준 컬럼: brand, model, ton, compressor, cold_hc, price
# ──────────────────────────────────────────────────────────────────────

def load_extra() -> pd.DataFrame:
    path = PT_ROOT / 'channels' / 'extra' / 'extra_ac_Prices_Tracking_Master.xlsx'
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name='Prices DB')
    latest = df['Scraped_At'].max()
    df = df[df['Scraped_At'] == latest].copy()
    # Split AC only
    df = df[df['Category'].str.contains('Split', na=False)]
    df['brand'] = df['Brand'].apply(norm_brand)
    df['model'] = df['Model_No'].fillna('')
    df['ton'] = pd.to_numeric(df['Cooling_Capacity_Ton'], errors='coerce')
    df['compressor'] = df['Compressor_Type'].apply(norm_compressor)
    df['cold_hc'] = df['Cold_or_HC'].apply(norm_cold_hc)
    df['price'] = pd.to_numeric(df['Sale_Price'], errors='coerce')
    return df[['brand', 'model', 'ton', 'compressor', 'cold_hc', 'price']].dropna(subset=['price', 'ton'])


def load_sws() -> pd.DataFrame:
    path = PT_ROOT / 'channels' / 'sws' / 'SWS_AC_Price_Tracking_Master.xlsx'
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name='Products_DB')
    latest = df['Timestamp'].max()
    df = df[df['Timestamp'] == latest].copy()
    # Split only
    df = df[df['Sub-Category'].str.contains('Wall Mount Split', na=False)]
    df['brand'] = df['Brand'].apply(norm_brand)
    df['model'] = ''
    df['ton'] = pd.to_numeric(df['Capacity (Ton)'], errors='coerce')
    df['compressor'] = df['Compressor'].apply(norm_compressor)
    df['cold_hc'] = df['Mode'].apply(norm_cold_hc)
    df['price'] = pd.to_numeric(df['Final Price (SAR)'], errors='coerce')
    return df[['brand', 'model', 'ton', 'compressor', 'cold_hc', 'price']].dropna(subset=['price', 'ton'])


def load_almanea() -> pd.DataFrame:
    path = PT_ROOT / 'channels' / 'almanea' / 'Almanea_AC_Price_Tracking_Master.xlsx'
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name='Products_DB')
    latest = df['Scraped_At'].max()
    df = df[df['Scraped_At'] == latest].copy()
    df = df[df['Category'] == 'Split AC']
    df['brand'] = df['Brand'].apply(norm_brand)
    df['model'] = df['Model'].fillna('')
    df['ton'] = pd.to_numeric(df['Capacity_Ton'], errors='coerce')
    df['compressor'] = df['Compressor_Type'].apply(norm_compressor)
    df['cold_hc'] = df['Function'].apply(norm_cold_hc)
    df['price'] = pd.to_numeric(df['Final_Promo_Price'].combine_first(df['Promo_Price']), errors='coerce')
    return df[['brand', 'model', 'ton', 'compressor', 'cold_hc', 'price']].dropna(subset=['price', 'ton'])


def load_alkhunaizan() -> pd.DataFrame:
    path = PT_ROOT / 'channels' / 'alkhunaizan' / 'AlKhunaizan_AC_Prices Tracking_Master.xlsx'
    if not path.exists():
        return None
    df = pd.read_excel(path, sheet_name='Products_DB')
    latest = df['Scraped_At'].max()
    df = df[df['Scraped_At'] == latest].copy()
    df = df[df['Category'] == 'Split AC']
    df['brand'] = df['Brand'].apply(norm_brand)
    df['model'] = ''
    df['ton'] = df['Nominal Capacity'].apply(parse_nominal_ton)
    df['compressor'] = df['Compressor Type'].apply(norm_compressor)
    df['cold_hc'] = df['Type'].apply(norm_cold_hc)
    df['price'] = pd.to_numeric(
        df['Only Pay Price (SAR)'].combine_first(df['Promotion Price (SAR)']),
        errors='coerce'
    )
    return df[['brand', 'model', 'ton', 'compressor', 'cold_hc', 'price']].dropna(subset=['price', 'ton'])


def load_binmomen() -> pd.DataFrame:
    path = PT_ROOT / 'channels' / 'binmomen' / 'Binmomen_AC_Data.xlsx'
    if not path.exists():
        return None
    df = pd.read_excel(path)
    latest = df['Scrape_Date'].max()
    df = df[df['Scrape_Date'] == latest].copy()
    # Split only (Category 컬럼 없으면 전체)
    if 'Category' in df.columns:
        df = df[df['Category'].str.contains('Split', na=False)]
    df['brand'] = df['Brand'].apply(norm_brand)
    df['model'] = ''
    df['ton'] = pd.to_numeric(df['Tonnage'], errors='coerce')
    df['compressor'] = df['Inverter'].apply(
        lambda x: 'Inverter' if str(x).strip().lower() in ('yes', '1', 'true') else 'Rotary'
    )
    df['cold_hc'] = df['Cooling_Type'].apply(norm_cold_hc)
    df['price'] = pd.to_numeric(df['Sale_Price'], errors='coerce')
    return df[['brand', 'model', 'ton', 'compressor', 'cold_hc', 'price']].dropna(subset=['price', 'ton'])


# BH, BlackBox, Tamkeen, TechnoBest, StarAppliance는 마스터 파일이 없어
# 스크레이핑 실행 후 생성 → 경로만 정의해두고 없으면 None 반환
def _load_generic(path: Path, sheet, brand_col, ton_col, comp_col,
                  cold_col, price_col, date_col=None,
                  cat_col=None, cat_filter=None,
                  ton_parser=None) -> pd.DataFrame:
    if not path.exists():
        return None
    try:
        df = pd.read_excel(path, sheet_name=sheet)
        if date_col and date_col in df.columns:
            latest = df[date_col].max()
            df = df[df[date_col] == latest]
        if cat_col and cat_filter:
            df = df[df[cat_col].str.contains(cat_filter, na=False)]
        df['brand'] = df[brand_col].apply(norm_brand)
        df['model'] = ''
        if ton_parser:
            df['ton'] = df[ton_col].apply(ton_parser)
        else:
            df['ton'] = pd.to_numeric(df[ton_col], errors='coerce')
        df['compressor'] = df[comp_col].apply(norm_compressor)
        df['cold_hc'] = df[cold_col].apply(norm_cold_hc)
        df['price'] = pd.to_numeric(df[price_col], errors='coerce')
        return df[['brand', 'model', 'ton', 'compressor', 'cold_hc', 'price']].dropna(subset=['price', 'ton'])
    except Exception as e:
        print(f'  [WARN] {path.name}: {e}', file=sys.stderr)
        return None


def load_bh() -> pd.DataFrame:
    return _load_generic(
        PT_ROOT / 'channels' / 'bh' / 'BH_Subdealer_AC_Master.xlsx',
        sheet='Weekly_Price_DB',
        brand_col='Brand', ton_col='Capacity_Ton', comp_col='Compressor',
        cold_col='Cold_or_HC', price_col='Retail_Price', date_col='Date',
        cat_col='Category', cat_filter='Split',
    )


def load_blackbox() -> pd.DataFrame:
    return _load_generic(
        PT_ROOT / 'channels' / 'blackbox' / 'BlackBox_AC_Master.xlsx',
        sheet='Products_DB',
        brand_col='Brand', ton_col='Capacity_Ton', comp_col='Compressor_Type',
        cold_col='Cold_or_HC', price_col='Sale_Price', date_col='Scraped_At',
        cat_col='Category', cat_filter='Split',
    )


def load_tamkeen() -> pd.DataFrame:
    return _load_generic(
        PT_ROOT / 'channels' / 'tamkeen' / 'Tamkeen_AC_Master.xlsx',
        sheet='Products_DB',
        brand_col='Brand', ton_col='Capacity_Ton', comp_col='Compressor_Type',
        cold_col='Cold_or_HC', price_col='Sale_Price', date_col='Scraped_At',
        cat_col='Category', cat_filter='Split',
    )


def load_technobest() -> pd.DataFrame:
    return _load_generic(
        PT_ROOT / 'channels' / 'technobest' / 'TechnoBest_AC_Master.xlsx',
        sheet='Products_DB',
        brand_col='Brand', ton_col='Capacity_Ton', comp_col='Compressor_Type',
        cold_col='Cold_or_HC', price_col='Sale_Price', date_col='Scraped_At',
        cat_col='Category', cat_filter='Split',
    )


def load_star() -> pd.DataFrame:
    return _load_generic(
        PT_ROOT / 'channels' / 'blackbox' / 'Star_AC_Master.xlsx',
        sheet='Products_DB',
        brand_col='Brand', ton_col='Capacity_Ton', comp_col='Compressor_Type',
        cold_col='Cold_or_HC', price_col='Sale_Price', date_col='Scraped_At',
        cat_col='Category', cat_filter='Split',
    )


CHANNELS = [
    # (tab_name, or_ir, loader_fn)
    ('eXtra',        'OR', load_extra),
    ('SWS',          'OR', load_sws),
    ('Al Manea',     'OR', load_almanea),
    ('AlKhunaizan',  'OR', load_alkhunaizan),
    ('BH',           'IR', load_bh),
    ('Bin Momen',    'IR', load_binmomen),
    ('Black Box',    'IR', load_blackbox),
    ('Star Appliance','IR', load_star),
    ('Tamkeen',      'IR', load_tamkeen),
    ('Techno Best',  'IR', load_technobest),
]

TON_ORDER = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
COMP_ORDER = ['Inverter', 'Rotary']
HC_ORDER   = ['Cold', 'Hot and Cold']

# LG Segment 우선순위 (중간값 기준 선택용)
SEG_PRIORITY = {
    'Mid · ND': 0, 'Mid · LA': 0,
    'Entry · NS': 1, 'Big · NT': 1,
    'Small · NF12': 2, 'High · AM/AF/NW': 3, '': 9,
}

# LG 기준 경쟁사 색상 비교
COLOR_CHEAP  = '#ffe0e0'   # LG보다 10%+ 저렴 → 빨강
COLOR_SIMILAR= '#fff8e0'   # ±10% → 노랑
COLOR_PRICEY = '#e0f0e0'   # LG보다 10%+ 비쌈 → 초록
COLOR_NOLG   = '#f8f9fa'   # LG 없는 행 → 회색

def price_color(comp_price: float, lg_ref: float, has_lg: bool) -> str:
    if not has_lg or lg_ref is None or pd.isna(lg_ref) or lg_ref <= 0:
        return COLOR_NOLG
    ratio = comp_price / lg_ref
    if ratio < 0.90:
        return COLOR_CHEAP
    if ratio > 1.10:
        return COLOR_PRICEY
    return COLOR_SIMILAR


def fmt_price(p) -> str:
    if pd.isna(p):
        return '—'
    return f'{int(round(p)):,}'


def lg_ref_price(lg_rows: pd.DataFrame, comp: str) -> float | None:
    """LG Mid 세그먼트 가격을 우선 기준으로, 없으면 전체 중간값."""
    if lg_rows.empty:
        return None
    mid_segs = {'Mid · ND', 'Mid · LA'}
    mid_rows = lg_rows[lg_rows['model'].apply(
        lambda m: get_lg_segment(m, comp) in mid_segs
    )]
    base = mid_rows if not mid_rows.empty else lg_rows
    prices = base['price'].dropna().tolist()
    return float(np.median(prices)) if prices else None


# ──────────────────────────────────────────────────────────────────────
# 테이블 생성
# ──────────────────────────────────────────────────────────────────────

def build_channel_html(ch_name: str, df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return '<p style="color:#888;padding:16px">데이터 없음 — 스크레이핑 후 재생성하세요.</p>'

    html_parts = []

    for comp in COMP_ORDER:
        df_comp = df[df['compressor'] == comp]
        if df_comp.empty:
            continue

        tons_present = sorted(df_comp['ton'].dropna().unique())

        # 경쟁사 브랜드 목록 (LG 제외, SKU 많은 순)
        comp_brands = (
            df_comp[df_comp['brand'] != 'LG']['brand']
            .value_counts()
            .index.tolist()
        )
        comp_brands = [b for b in comp_brands if b and b != 'LG']

        title = '▶ Inverter Split' if comp == 'Inverter' else '▶ Rotary Split'
        html_parts.append(f'<h3 class="sec-title">{title}</h3>')
        html_parts.append('<div class="tbl-wrap"><table>')

        # 헤더: Cap. | Cold/HC | LG (Seg · Model · Price) | [경쟁사들]
        header_html = (
            '<th class="hdr-cap">Cap.</th>'
            '<th class="hdr-hc">Cold/HC</th>'
            '<th class="lg" style="text-align:left;min-width:200px">LG &nbsp;<span style="font-weight:400;font-size:10px">(Seg · Model · Price SAR)</span></th>'
            + ''.join(f'<th>{b}</th>' for b in comp_brands)
        )
        html_parts.append(f'<tr>{header_html}</tr>')

        for ton in TON_ORDER:
            if ton not in tons_present:
                continue
            df_ton = df_comp[df_comp['ton'] == ton]

            for hc in HC_ORDER:
                df_row = df_ton[df_ton['cold_hc'] == hc]
                if df_row.empty:
                    continue

                lg_rows = df_row[df_row['brand'] == 'LG']
                has_lg = not lg_rows.empty
                lg_ref = lg_ref_price(lg_rows, comp)

                # LG 통합 셀: (세그먼트 · 모델 · SAR 가격) 각 SKU 한 줄
                if has_lg:
                    lg_lines = []
                    for _, r in lg_rows.sort_values('price').iterrows():
                        seg = get_lg_segment(r['model'], comp)
                        model_short = (r['model'] or '').split()[0] if r['model'] else ''
                        p = fmt_price(r['price'])
                        seg_tag = f'<span class="seg-tag">{seg}</span>' if seg else ''
                        model_tag = f'<span class="model-tag">{model_short}</span>' if model_short else ''
                        lg_lines.append(f'{seg_tag}{model_tag}<span class="price-tag">{p}</span>')
                    lg_cell = '<br>'.join(lg_lines)
                    lg_td = f'<td class="lg-val lg-combined">{lg_cell}</td>'
                else:
                    lg_td = '<td class="empty no-lg">(No LG)</td>'

                hc_label = 'Cold' if hc == 'Cold' else 'H&amp;C'
                ton_label = f'{ton:g}T'

                row_html = (
                    f'<td class="ton">{ton_label}</td>'
                    f'<td class="hc-cell">{hc_label}</td>'
                    f'{lg_td}'
                )

                # 경쟁사 셀
                for brand in comp_brands:
                    brand_rows = df_row[df_row['brand'] == brand]
                    if brand_rows.empty:
                        row_html += '<td class="empty">—</td>'
                        continue
                    prices = brand_rows['price'].dropna().sort_values().tolist()
                    if not prices:
                        row_html += '<td class="empty">—</td>'
                        continue
                    avg_p = float(np.mean(prices))
                    color = price_color(avg_p, lg_ref, has_lg)
                    price_lines = '<br>'.join(fmt_price(p) for p in prices)
                    row_html += f'<td style="background:{color}">{price_lines}</td>'

                html_parts.append(f'<tr>{row_html}</tr>')

        html_parts.append('</table></div>')

    return '\n'.join(html_parts)


# ──────────────────────────────────────────────────────────────────────
# HTML 조립
# ──────────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', sans-serif; padding: 24px; background: #f4f6f9; margin: 0; }
h2 { color: #1a1a2e; margin-bottom: 4px; }
.subtitle { color: #666; font-size: 13px; margin-bottom: 16px; }
.legend { display: flex; gap: 20px; margin-bottom: 8px; font-size: 12px; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 6px; }
.dot { width: 14px; height: 14px; border-radius: 3px; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 20px; border-bottom: 2px solid #d0d4e8; padding-bottom: 8px; }
.tab-btn {
  padding: 8px 18px; border: 1px solid #d0d4e8; border-radius: 6px 6px 0 0;
  background: #eef0f8; color: #555; cursor: pointer; font-size: 13px; font-weight: 500;
  transition: all 0.2s; border-bottom: none; margin-bottom: -2px;
}
.tab-btn:hover { background: #dce0f0; color: #1a1a2e; }
.tab-btn.active { background: #1a1a2e; color: white; border-color: #1a1a2e; }
.tab-label { font-size: 11px; font-weight: 700; color: #888; letter-spacing: 1px; padding: 0 6px 10px; align-self: flex-end; }
.tab-content { display: none; }
.ch-note { font-size: 12px; color: #888; margin-bottom: 12px; }
.sec-title { color: #1a1a2e; margin: 20px 0 8px; font-size: 15px; }
.tbl-wrap { overflow-x: auto; margin-bottom: 28px; }
table { border-collapse: collapse; min-width: 700px; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); background: white; }
th { background: #1a1a2e; color: white; padding: 8px 10px; text-align: center; white-space: nowrap; }
th.lg { background: #a50034; }
th.seg { background: #2d3561; text-align: left; }
th.hdr-cap { background: #1a1a2e; }
th.hdr-hc { background: #2d4a6e; }
th.hdr-model { background: #2d3561; min-width: 90px; }
td { padding: 6px 10px; border-bottom: 1px solid #e8eaf0; text-align: right; white-space: nowrap; background: white; vertical-align: middle; line-height: 1.6; }
td.seg { background: #f0f2f8; font-weight: 600; color: #1a1a2e; text-align: left; }
td.ton { background: #eef0f8; color: #333; text-align: center; font-size: 12px; font-weight: 700; border-right: 2px solid #d0d4e8; white-space: nowrap; }
td.hc-cell { background: #f5f6fa; color: #555; text-align: center; font-size: 11px; font-weight: 600; border-right: 1px solid #d0d4e8; }
td.model-cell { background: #f5f6fa; color: #555; text-align: left; font-size: 11px; }
td.lg-val { background: #fff0f3; font-weight: 700; color: #a50034; }
td.lg-combined { background: #fff0f3; text-align: left; line-height: 1.8; }
td.no-lg { color: #bbb; background: #f8f9fa !important; text-align: center; font-style: italic; }
td.empty { color: #ccc; background: #f8f9fa !important; text-align: center; }
.seg-tag { display: inline-block; background: #2d3561; color: #c9d4ff; font-size: 10px; border-radius: 3px; padding: 0 5px; margin-right: 4px; font-weight: 600; }
.model-tag { display: inline-block; color: #555; font-size: 11px; margin-right: 4px; }
.price-tag { display: inline-block; color: #a50034; font-weight: 700; font-size: 12px; }
tr:hover td { filter: brightness(0.97); }
"""

JS = """
function switchTab(idx) {
  document.querySelectorAll('.tab-btn').forEach((b,i) => b.classList.toggle('active', i===idx));
  document.querySelectorAll('.tab-content').forEach((c,i) => {
    c.style.display = i===idx ? 'block' : 'none';
  });
}
document.querySelectorAll('.tab-content')[0].style.display = 'block';
"""


def build_html(channel_data: list) -> str:
    now = datetime.now()
    week_num = now.isocalendar()[1]
    year = now.year

    tab_btns = []
    tab_contents = []
    prev_or_ir = None

    for i, (ch_name, or_ir, df) in enumerate(channel_data):
        if or_ir != prev_or_ir:
            tab_btns.append(f'<span class="tab-label">{or_ir}</span>')
            prev_or_ir = or_ir
        active = ' active' if i == 0 else ''
        tab_btns.append(f'<button class="tab-btn{active}" onclick="switchTab({i})">{ch_name}</button>')

        content_html = build_channel_html(ch_name, df)
        display = 'block' if i == 0 else 'none'
        tab_contents.append(
            f'<div class="tab-content" id="tab-{i}" style="display:{display}">'
            f'<div class="ch-note">Channel: {ch_name} | Prices: VAT-incl. SAR | Competitor color: vs. LG median</div>'
            f'{content_html}'
            f'</div>'
        )

    tabs_html = '\n'.join(tab_btns)
    content_html_all = '\n'.join(tab_contents)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Split AC Price Tracking — W{week_num} {year}</title>
<style>{CSS}</style>
</head><body>
<h2>Split AC Price Tracking — W{week_num} {year}</h2>
<div class="subtitle">Prices: VAT-incl. SAR | Source: Online channel scraping | Auto-generated: {now.strftime('%Y-%m-%d %H:%M')}</div>
<div class="legend">
  <div class="legend-item"><div class="dot" style="background:#ffe0e0"></div> Cheaper than LG (&gt;10%)</div>
  <div class="legend-item"><div class="dot" style="background:#fff8e0"></div> Similar to LG (±10%)</div>
  <div class="legend-item"><div class="dot" style="background:#e0f0e0"></div> Pricier than LG (&gt;10%)</div>
  <div class="legend-item"><div class="dot" style="background:#f8f9fa"></div> No LG in segment</div>
</div>
<div class="tabs">
{tabs_html}
</div>
{content_html_all}
<script>{JS}</script>
</body></html>"""


# ──────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--channel', nargs='*', help='특정 채널만 로드 (예: extra sws)')
    args = parser.parse_args()

    filter_channels = [c.lower() for c in args.channel] if args.channel else None

    print(f'[{datetime.now().strftime("%H:%M:%S")}] GTM Price Tracking 생성 시작')

    channel_data = []
    for ch_name, or_ir, loader_fn in CHANNELS:
        if filter_channels and ch_name.lower().replace(' ', '') not in filter_channels:
            continue
        print(f'  [{ch_name}] 로딩 중...')
        try:
            df = loader_fn()
            if df is not None:
                print(f'    → {len(df)}개 SKU (브랜드: {df["brand"].nunique()}개)')
            else:
                print(f'    → 마스터 파일 없음 (데이터 없음으로 표시)')
        except Exception as e:
            print(f'    → 오류: {e}')
            df = None
        channel_data.append((ch_name, or_ir, df))

    html = build_html(channel_data)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding='utf-8')
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f'\n✅ 완료: {OUT_PATH} ({size_kb:.0f} KB)')
    print(f'   채널 {len(channel_data)}개 처리됨')


if __name__ == '__main__':
    main()
