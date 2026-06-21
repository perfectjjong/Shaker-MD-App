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

# 키는 ENV(ZENROWS_KEY)로 교체 가능 — 새 무료 트라이얼 키 발급 시 코드 수정 없이 환경변수만 바꾸면 됨
ZENROWS_KEY = os.environ.get("ZENROWS_KEY", "6cbc4ab3bdafd8be19ef27c3c0e4604ea18fa796")
BASE_URL    = "https://alkhaterstore.com/product-category/air-conditioning"
MAX_PAGES       = 15
CURRENT_DIR     = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE     = os.path.join(CURRENT_DIR, "alkhater_ac_prices.xlsx")

# ─── 절약 정책 (2026-06-21: 유료 크레딧 낭비 재발 방지) ──────────────────────
#  · 주간 스로틀: 마지막 성공 수집 후 MIN_DAYS_BETWEEN일 미만이면 API 호출 자체를 건너뜀
#    (cron은 매일 돌지만 실제 유료 호출은 주 1회 → 약 7배 절감). --force 로 무시 가능.
#  · js_render 기본 OFF: WooCommerce 카테고리는 서버사이드 렌더(제품이 정적 HTML에 포함)라
#    js_render 불필요. 비싼 배수(×5)를 빼고, 정적으로 0건일 때만 폴백으로 1회 켠다.
#  · 재시도 1회: 실패당 추가 유료 호출이므로 3→1.
MIN_DAYS_BETWEEN = 6

# ─── 브랜드 매핑 (모델 prefix → 브랜드명) ───────────────────────────────
MODEL_BRAND_MAP = [
    (r'^(NS|ND|NT|AM|AF|NW|NF|LA|LB|LH|LK|LO|LT|LS|APNQ|APUW|APW)',  'LG'),
    (r'^(KSGA|KSGS)',                                                     'Super General'),
    (r'^GWC|^GMV|^GWH',                                                  'Gree'),
    (r'^HSU|^HAS|^HEU',                                                  'Haier'),
    (r'^WDV|^MSTL|^MSKMP|^MSM|^MSTE',                                   'Midea'),
    (r'^WWS|^WWA',                                                        'Westinghouse'),
    (r'^(DW\d|DT\d|CWACH)',                                               'Crafft'),
    (r'^DSA',                                                             'Dansat'),
    (r'^HW\d|^AS\d',                                                      'Hisense'),
    (r'^UW',                                                              'Ruud'),
    (r'^HQAS',                                                            'Home Queen'),
    (r'^MPC|^MMPC|^MANDO',                                               'Mando'),
    (r'^SAC|^SAS',                                                        'Samsung'),
    (r'^(TAC|CW-T|CWT)',                                                  'TCL'),
    (r'^AUX',                                                             'AUX'),
    (r'^(FT|FW|FM)\d',                                                   'Frigidaire'),
    (r'^(TH-C|TH-X|TU-C)',                                               'Tornado'),
    (r'^ZCP|^ZCH',                                                        'Zamil'),
    (r'^GD\d',                                                            'General Dan'),
    (r'^(GJC|GLW|ASSA)',                                                  'General'),
    (r'^(BSACCA|BSAC)',                                                   'Basic'),
    (r'^YORX',                                                            'Yorksa'),
    (r'^IM\d',                                                            'Impax'),
    (r'^UNST',                                                            'Unistar'),
]

# 아랍어 브랜드명 → 영문
ARABIC_BRAND_MAP = {
    'سوبر جنرال':  'Super General',
    'سوبر جينرال': 'Super General',
    'جري':         'Gree',
    'هاير':        'Haier',
    'ميديا':       'Midea',
    'وستنجهاوس':   'Westinghouse',
    'كرفت':        'Crafft',
    'كرافت':       'Crafft',
    'دانسات':      'Dansat',
    'دان سات':     'Dansat',
    'هايسنس':      'Hisense',
    'ال جي':       'LG',
    'إل جي':       'LG',
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
    'توريندو':     'Tornado',
    'الزامل':      'Zamil',
    'جنرال دان':   'General Dan',
    'جنرال':       'General',
    'ز.ترست':      'Z.Trust',
    'زامل':        'Zamil',
    'بيسك':        'Basic',
    'يونيستار':    'Unistar',
    'امبكس':       'Impax',
    'امبيكس':      'Impax',
    'يوركس':       'Yorksa',
}

# AC 아닌 제품 필터링 키워드 (아랍어)
NON_AC_ARABIC = ['مروحة', 'ستارة هوائية', 'خدمة حامل', 'ريبون مروحة',
                 'خدمة تركيب', 'خدمة فك', 'مبرد هواء', 'مكيف صحراوي',
                 'removal service', 'installation service']

# 표준 톤 단계 (대시보드 TON_ORDER 기준)
TON_ORDER = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]  # 0.75T 제외 (사우디 비표준)


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
        'ac_type':    'Split',   # Split / Window / Portable / Free Standing
        'cold_hc':    'Cooling Only',
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
    # وحدة / وحده (철자 변형) + 쉼표 포함(22,000) + الف(천 단위 표기 12600 الف وحدة) 처리
    btu_match = re.search(r'\b(\d{1,2},\d{3}|\d{4,6})\s*(?:الف\s*)?(?:وحدة|وحده|BTU|btu)', name)
    if btu_match:
        btu_val = int(btu_match.group(1).replace(',', ''))
    result['ton'] = snap_ton(btu_val, ton_direct)

    # Compressor
    if 'انفيرتر' in name or 'انفيرتير' in name or 'inverter' in name.lower():
        result['compressor'] = 'Inverter'

    # AC Type
    if any(w in name for w in ['متنقل', 'Portable', 'portable']):
        result['ac_type'] = 'Portable'
    elif 'شباك' in name or 'window' in name.lower():
        result['ac_type'] = 'Window'
    elif any(w in name for w in ['ستاند', 'أرضي', 'دولابي', 'floor', 'standing']):
        result['ac_type'] = 'Free Standing'
    else:
        result['ac_type'] = 'Split'

    # Cold / H&C (다른 채널 표준값으로 정규화)
    if any(w in name for w in ['تدفئة', 'حار', 'h&c']):
        result['cold_hc'] = 'Heat & Cool'
    else:
        result['cold_hc'] = 'Cooling Only'

    return result


def fetch_page(page_num: int, js_render: bool = False) -> str | None:
    """ZenRows로 1페이지 가져옴. js_render=False가 기본(저비용). premium_proxy는
    데이터센터 IP가 Cloudflare 평판차단 대상이라 유지(신뢰 IP 필요)."""
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/page/{page_num}/"
    params = {"apikey": ZENROWS_KEY, "url": url, "premium_proxy": "true"}
    if js_render:
        params["js_render"] = "true"
        params["wait"] = "5000"
    for attempt in range(2):  # 1 재시도 (실패당 추가 유료 호출이므로 최소화)
        try:
            resp = requests.get("https://api.zenrows.com/v1/", params=params, timeout=120)
        except Exception as e:
            print(f"  ⚠️  요청 오류 (시도 {attempt+1}): {e}")
            time.sleep(5)
            continue

        if resp.status_code == 404:
            return None
        if resp.status_code in (422, 429, 502, 503):
            print(f"  ⚠️  {resp.status_code} 재시도 ({attempt+1}/2)...")
            time.sleep(10)
            continue
        if resp.status_code != 200:
            print(f"  ⚠️  HTTP {resp.status_code}: {resp.text[:120]}")
            return None
        if "Just a moment" in resp.text:
            print("  ❌ Cloudflare 차단")
            return None
        return resp.text
    print(f"  ❌ Page {page_num} 2회 실패, 건너뜀")
    return None


def _extract_price(bdi_html: str) -> float | None:
    """bdi 태그에서 가격 숫자 추출 (SVG 등 비숫자 제거)"""
    text = re.sub(r'<svg[^>]*>.*?</svg>', '', bdi_html, flags=re.DOTALL)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    nums = re.findall(r'[\d,]+', text)
    for n in nums:
        v = float(n.replace(',', ''))
        if v >= 100:  # 가격은 최소 100 SAR 이상
            return v
    return None


def parse_products(html: str, page_num: int) -> list[dict]:
    # data-product_id 기준으로 블록 분리 (add-to-cart 버튼 위치)
    # 각 블록 = 해당 SKU의 카드 하단부 + 이전 카드 정보
    # → SKU와 같은 블록 내에서 역방향으로 가격/재고 탐색
    blocks = re.split(r'(?=data-product_id="\d+")', html)

    results = []
    for block in blocks[1:]:  # 첫 블록은 헤더
        sku_m = re.search(
            r'data-product_id="(\d+)"\s+data-product_sku="([^"]+)"\s+aria-label="([^"]+)"',
            block)
        if not sku_m:
            continue

        pid, sku, label = sku_m.group(1), sku_m.group(2), sku_m.group(3)

        # 이름 정리
        name = html_lib.unescape(label)
        name = re.sub(r'^إضافة إلى عربة التسوق:\s*"', '', name).rstrip('"')
        name = re.sub(r'^إقرأ المزيد عن\s*"?', '', name).rstrip('"')

        if any(kw in name for kw in NON_AC_ARABIC):
            continue

        specs = parse_arabic_name(name)

        # post-{pid} ~ add-to-cart 버튼 사이로 카드 범위 정확히 제한
        # (이전 rfind('instock') 방식은 다음 카드까지 포함해 가격/재고 오파싱)
        sku_pos  = html.find(f'data-product_sku="{sku}"')
        post_pos = html.rfind(f'post-{pid}', 0, sku_pos)
        if post_pos > 0:
            card = html[post_pos: sku_pos + len(sku) + 100]
        else:
            card = html[max(0, sku_pos - 5000): sku_pos + 100]
        # 재고 상태: 카드 시작 class 속성에서만 확인 (단어 경계로 substring 오매칭 방지)
        in_stock = bool(re.search(r'\binstock\b', card[:400])) and not bool(re.search(r'\boutofstock\b', card[:400]))

        # 정가 (del 태그 내 bdi)
        del_m = re.search(r'<del[^>]*>.*?<bdi>(.*?)</bdi>', card, re.DOTALL)
        # 할인가 (ins 태그 내 bdi)
        ins_m = re.search(r'<ins[^>]*>.*?<bdi>(.*?)</bdi>', card, re.DOTALL)
        # 단일 가격 (del/ins 없는 경우 - 첫 번째 bdi)
        bdi_m = re.search(r'<bdi>(.*?)</bdi>', card, re.DOTALL)

        price_reg  = _extract_price(del_m.group(1)) if del_m else None
        price_sale = _extract_price(ins_m.group(1)) if ins_m else None

        # del/ins 없으면 단일 가격
        if price_reg is None and price_sale is None and bdi_m:
            p = _extract_price(bdi_m.group(1))
            price_reg = price_sale = p

        # ins 없이 del만 있는 경우 (정가 = 판매가)
        if price_sale is None and price_reg is not None:
            price_sale = price_reg

        # 할인율 배지로 정가 역산 (del 없고 ins만 있는 경우)
        disc_m = re.search(r'onsale[^>]*>\s*(-\d+)%', card)
        if disc_m and price_sale and price_reg is None:
            pct = abs(int(disc_m.group(1)))
            price_reg = round(price_sale / (1 - pct / 100))

        discount_pct = None
        if price_reg and price_sale and price_reg > price_sale:
            discount_pct = round((1 - price_sale / price_reg) * 100, 1)

        # URL
        url_m = re.search(r'href="(https://alkhaterstore\.com/product/[^"]+)"', card)
        prod_url = url_m.group(1) if url_m else ''

        # removal-service 등 비AC 서비스 제품 URL 필터
        if prod_url and any(kw in prod_url for kw in ('removal-service', 'installation-service')):
            continue

        results.append({
            'SKU':                sku,
            'Product_Name':       name,
            'Brand':              specs['brand'],
            'Model':              specs['model'],
            'Ton':                specs['ton'],
            'Compressor':         specs['compressor'],
            'AC_Type':            specs['ac_type'],
            'Cold_HC':            specs['cold_hc'],
            'Price_SAR':          price_sale,
            'Original_Price_SAR': price_reg,
            'Discount_Pct':       discount_pct,
            'Is_On_Sale':         discount_pct is not None and discount_pct > 0,
            'In_Stock':           in_stock,
            'URL':                prod_url,
            'Page':               page_num,
            'Scraped_At':         datetime.now().strftime('%Y-%m-%d %H:%M'),
        })
    return results


def has_next_page(html: str, page_num: int) -> bool:
    # 다음 페이지 URL이 존재하면 다음 페이지 있음
    next_url = f'air-conditioning/page/{page_num + 1}/'
    return next_url in html


def scrape_all() -> list[dict]:
    all_products = []
    use_js = False  # 저비용 정적 모드로 시작. page1이 0건이면 js_render 폴백으로 전환.
    for page_num in range(1, MAX_PAGES + 1):
        print(f"  [Page {page_num}] 요청 중...{' [js_render]' if use_js else ''}")
        html = fetch_page(page_num, js_render=use_js)
        if html is None:
            break

        products = parse_products(html, page_num)
        # page1이 정적으로 0건이면 = JS 렌더 필요. 1회만 js_render로 폴백 재시도.
        if not products and page_num == 1 and not use_js:
            print("  ↻ 정적 0건 → js_render 폴백 1회")
            use_js = True
            html = fetch_page(1, js_render=True)
            if html:
                products = parse_products(html, 1)
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


def _last_scrape_date():
    """기존 xlsx의 최신 시트(YYYY-MM-DD)를 datetime으로 반환. 없으면 None."""
    if not os.path.exists(OUTPUT_FILE):
        return None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(OUTPUT_FILE, read_only=True)
        dates = []
        for name in wb.sheetnames:
            try:
                dates.append(datetime.strptime(name.strip(), '%Y-%m-%d'))
            except ValueError:
                continue
        wb.close()
        return max(dates) if dates else None
    except Exception:
        return None


if __name__ == '__main__':
    force = '--force' in sys.argv
    print(f"=== Al Khater AC 스크래퍼 — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")

    # 주간 스로틀: 최근 MIN_DAYS_BETWEEN일 내 성공 수집이 있으면 유료 호출 건너뜀
    last = _last_scrape_date()
    if last and not force:
        age_days = (datetime.now() - last).days
        if age_days < MIN_DAYS_BETWEEN:
            print(f"⏭️  최근 수집 {age_days}일 전({last:%Y-%m-%d}) — {MIN_DAYS_BETWEEN}일 미만이라 "
                  f"유료 호출 건너뜀 (강제 실행: --force)")
            print('\n완료(스킵).')
            sys.exit(0)

    products = scrape_all()
    save(products)
    print('\n완료.')
