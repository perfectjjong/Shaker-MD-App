#!/usr/bin/env python3
"""
Al Khater Store 에어컨 스크래퍼
- Scrape.do API (super+render) 로 Cloudflare 우회
- 아랍어 상품명에서 Brand/Model/Ton/Compressor/Type/Cold_HC 자동 파싱
"""

import re
import sys
import os
import html as html_lib
import time
from datetime import datetime

try:
    import requests
    import pandas as pd
except ImportError as e:
    print(f"Missing: {e}\nRun: pip install requests pandas openpyxl")
    sys.exit(1)

SCRAPE_DO_TOKEN = "c343dc73d57240478ef683487eff358e31c3ca43f43"
BASE_URL        = "https://alkhaterstore.com/product-category/air-conditioning"
MAX_PAGES       = 15
CURRENT_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE     = os.path.join(CURRENT_DIR, "alkhater_ac_prices.xlsx")

# ─── 브랜드 매핑 (모델 prefix → 브랜드명) ───────────────────────────────
MODEL_BRAND_MAP = [
    (r'^(NS|ND|NT|AM|AF|NW|NF|LA|LB|LH|LK|LO|LT|LS|APNQ|APUW|APW)',  'LG'),
    (r'^KSGA',                                                            'Super General'),
    (r'^GWC|^GMV|^GWH',                                                  'Gree'),
    (r'^HSU|^HAS|^HEU',                                                  'Haier'),
    (r'^WDV|^MSTL|^MSKMP|^MSM|^MSTE',                                   'Midea'),
    (r'^WWS|^WWA',                                                        'Westinghouse'),
    (r'^DW\d|^DT\d',                                                      'Crafft'),
    (r'^DSA',                                                             'Dansat'),
    (r'^HW\d|^AS\d',                                                      'Hisense'),
    (r'^UW',                                                              'Ruud'),
    (r'^HQAS',                                                            'Home Queen'),
    (r'^MPC|^MMPC|^MANDO',                                               'Mando'),
    (r'^SAC|^SAS',                                                        'Samsung'),
    (r'^(TAC|CW-T|CWT)',                                                  'TCL'),
    (r'^AUX',                                                             'AUX'),
    (r'^(FT|FW|FM)',                                                      'Frigidaire'),
    (r'^TH-C|^TU-C',                                                      'Tornado'),
    (r'^ZCP|^ZCH',                                                        'Zamil'),
    (r'^GD\d',                                                            'General Dan'),
    (r'^GJC|^GLW',                                                        'General'),
]

# 아랍어 브랜드명 → 영문
ARABIC_BRAND_MAP = {
    'سوبر جنرال':  'Super General',
    'جري':         'Gree',
    'هاير':        'Haier',
    'ميديا':       'Midea',
    'وستنجهاوس':   'Westinghouse',
    'كرفت':        'Crafft',
    'دانسات':      'Dansat',
    'دان سات':     'Dansat',
    'هايسنس':      'Hisense',
    'ال جي':       'LG',
    'الجي':        'LG',
    'سامسونج':     'Samsung',
    'شارب':        'Sharp',
    'اس كي ام':    'SKM',
    'هوم كوين':    'Home Queen',
    'ماندو':       'Mando',
    'روود':        'Ruud',
    'كولن':        'Kolin',
    'فريجو':       'Frigidaire',
    'تي سي ال':   'TCL',
    'تورنيدو':     'Tornado',
    'الزامل':      'Zamil',
    'جنرال دان':   'General Dan',
    'ز.ترست':      'Z.Trust',
    'زامل':        'Zamil',
}

# AC 아닌 제품 필터링 키워드 (아랍어)
NON_AC_ARABIC = ['مروحة', 'ستارة هوائية', 'خدمة حامل', 'ريبون مروحة', 'مكيف مكتب مقاس']

# 표준 톤 단계 (대시보드 TON_ORDER 기준)
TON_ORDER = [0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]


def snap_ton(btu: int | None, ton_direct: float | None) -> float | None:
    """BTU 또는 직접 표기 ton을 표준 단계로 스냅"""
    if ton_direct is not None:
        val = ton_direct
    elif btu is not None:
        val = btu / 12000
    else:
        return None
    # 가장 가까운 표준 단계로 스냅
    return min(TON_ORDER, key=lambda t: abs(t - val))


def parse_arabic_name(name: str) -> dict:
    """아랍어+영문 혼합 상품명에서 스펙 추출"""
    result = {
        'brand':      '',
        'model':      '',
        'ton':        None,
        'compressor': 'Rotary',
        'ac_type':    'Split',   # Split / Window / Free Standing
        'cold_hc':    'Cold',
    }

    # 모델번호 추출 (대문자+숫자 패턴, 최소 5자)
    model_candidates = re.findall(r'\b([A-Z][A-Z0-9\-]{4,})\b', name.upper())
    model_candidates = [m for m in model_candidates
                        if not re.match(r'^(BTU|BTH|WIFI|WLAN|MODEL|TYPE|FOR)$', m)]
    if model_candidates:
        result['model'] = model_candidates[0]

    # 브랜드 (모델 prefix 우선)
    for pattern, brand in MODEL_BRAND_MAP:
        if result['model'] and re.match(pattern, result['model']):
            result['brand'] = brand
            break
    if not result['brand']:
        for arabic, eng in ARABIC_BRAND_MAP.items():
            if arabic in name:
                result['brand'] = eng
                break

    # Ton: "طن" 직접 표기 우선, 없으면 BTU에서 스냅
    ton_direct = None
    btu_val = None
    ton_match = re.search(r'(\d+(?:\.\d+)?)\s*طن', name)
    if ton_match:
        ton_direct = float(ton_match.group(1))
    btu_match = re.search(r'\b(\d{4,6})\s*(?:وحدة|BTU|btu)', name)
    if btu_match:
        btu_val = int(btu_match.group(1))
    result['ton'] = snap_ton(btu_val, ton_direct)

    # Compressor
    if 'انفيرتر' in name or 'انفيرتير' in name or 'inverter' in name.lower():
        result['compressor'] = 'Inverter'

    # AC Type
    if 'شباك' in name or 'window' in name.lower():
        result['ac_type'] = 'Window'
    elif any(w in name for w in ['ستاند', 'أرضي', 'floor', 'standing']):
        result['ac_type'] = 'Free Standing'
    else:
        result['ac_type'] = 'Split'

    # Cold / H&C
    if 'تدفئة' in name or 'تبريد وتدفئة' in name or 'h&c' in name.lower():
        result['cold_hc'] = 'Hot and Cold'

    return result


def fetch_page(page_num: int) -> str | None:
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/page/{page_num}/"
    for attempt in range(3):
        try:
            resp = requests.get(
                "https://api.scrape.do",
                params={"token": SCRAPE_DO_TOKEN, "url": url,
                        "super": "true", "render": "true", "geoCode": "sa"},
                timeout=120,
            )
        except Exception as e:
            print(f"  ⚠️  요청 오류 (시도 {attempt+1}): {e}")
            time.sleep(5)
            continue

        if resp.status_code == 404:
            return None
        if resp.status_code == 502:
            print(f"  ⚠️  502 재시도 ({attempt+1}/3)...")
            time.sleep(8)
            continue
        if resp.status_code != 200:
            print(f"  ⚠️  HTTP {resp.status_code}")
            return None
        if "Just a moment" in resp.text:
            print("  ❌ Cloudflare 차단")
            return None
        return resp.text
    print(f"  ❌ Page {page_num} 3회 실패, 건너뜀")
    return None


def parse_products(html: str, page_num: int) -> list[dict]:
    items = re.findall(
        r'data-product_id="(\d+)"\s+data-product_sku="([^"]+)"\s+aria-label="([^"]+)"',
        html,
    )
    price_spans = re.findall(r'<span class="price">(.*?)</span>', html, re.DOTALL)

    # 상품 URL 추출 (slug 기반)
    prod_urls = re.findall(
        r'href="(https://alkhaterstore\.com/product/[^"]+)"', html
    )
    # 중복 제거 (카드당 2개씩 나올 수 있음)
    seen_urls = {}
    for u in prod_urls:
        slug = u.rstrip('/').split('/')[-1]
        if slug not in seen_urls:
            seen_urls[slug] = u
    url_list = list(seen_urls.values())

    results = []
    for i, (pid, sku, label) in enumerate(items):
        name = html_lib.unescape(label)
        name = re.sub(r'^إضافة إلى عربة التسوق:\s*"', '', name).rstrip('"')

        # AC 아닌 제품 제외 (선풍기, 에어커튼, 브라켓 서비스 등)
        if any(kw in name for kw in NON_AC_ARABIC):
            continue

        specs = parse_arabic_name(name)

        # 가격
        price_sale = price_reg = None
        if i < len(price_spans):
            raw = price_spans[i]
            nums = re.findall(r'[\d,]+', re.sub(r'<[^>]+>', ' ', raw))
            nums_f = [float(n.replace(',', '')) for n in nums if len(n) >= 3]
            if len(nums_f) >= 2:
                price_reg, price_sale = max(nums_f), min(nums_f)
            elif len(nums_f) == 1:
                price_reg = price_sale = nums_f[0]

        prod_url = url_list[i] if i < len(url_list) else ''

        results.append({
            'SKU':               sku,
            'Product_Name':      name,
            'Brand':             specs['brand'],
            'Model':             specs['model'],
            'Ton':               specs['ton'],
            'Compressor':        specs['compressor'],
            'AC_Type':           specs['ac_type'],
            'Cold_HC':           specs['cold_hc'],
            'Price_SAR':         price_sale,
            'Original_Price_SAR': price_reg,
            'Is_On_Sale':        price_sale != price_reg if price_sale else False,
            'URL':               prod_url,
            'Page':              page_num,
            'Scraped_At':        datetime.now().strftime('%Y-%m-%d %H:%M'),
        })
    return results


def has_next_page(html: str, page_num: int) -> bool:
    # 다음 페이지 URL이 존재하면 다음 페이지 있음
    next_url = f'air-conditioning/page/{page_num + 1}/'
    return next_url in html


def scrape_all() -> list[dict]:
    all_products = []
    for page_num in range(1, MAX_PAGES + 1):
        print(f"  [Page {page_num}] 요청 중...")
        html = fetch_page(page_num)
        if html is None:
            break

        products = parse_products(html, page_num)
        if not products:
            print(f"  ✅ 마지막 페이지")
            break

        all_products.extend(products)
        print(f"     → {len(products)}개 수집 (누계 {len(all_products)}개)")

        if not has_next_page(html, page_num):
            print(f"  ✅ 마지막 페이지 (page {page_num})")
            break
        time.sleep(2)

    return all_products


def save(products: list[dict]):
    if not products:
        print("⚠️  수집 상품 없음")
        return
    df = pd.DataFrame(products)
    today = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(OUTPUT_FILE):
        with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl', mode='a', if_sheet_exists='replace') as w:
            df.to_excel(w, sheet_name=today, index=False)
    else:
        with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as w:
            df.to_excel(w, sheet_name=today, index=False)
    print(f"\n💾 저장: {OUTPUT_FILE} (시트: {today}, {len(df)}개)")
    print(df[['SKU', 'Brand', 'Ton', 'Compressor', 'AC_Type', 'Price_SAR']].to_string(index=False))


if __name__ == '__main__':
    print(f"=== Al Khater AC 스크래퍼 — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    products = scrape_all()
    save(products)
    print('\n완료.')
