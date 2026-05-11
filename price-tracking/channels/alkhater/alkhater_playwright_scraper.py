#!/usr/bin/env python3
"""
Al Khater Store 에어컨 스크래퍼 - Playwright 직접 방식
GitHub Actions(Azure IP)에서 실행 → OCI IP 차단 우회
"""
import re, sys, os, time, html as html_lib
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    import pandas as pd
except ImportError as e:
    print(f"Missing: {e}"); sys.exit(1)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE  = os.path.join(CURRENT_DIR, "alkhater_ac_prices.xlsx")
BASE_URL     = "https://alkhaterstore.com/product-category/air-conditioning"
MAX_PAGES    = 15
PAGE_WAIT    = 8   # Cloudflare 챌린지 대기

# ── 브랜드 매핑 ──────────────────────────────────────────────────────────────
MODEL_BRAND_MAP = [
    (r'^(NS|ND|NT|AM|AF|NW|NF|LA|LB|LH|LK|LO|LT|LS|APNQ|APUW|APW)', 'LG'),
    (r'^KSGA',                                          'Super General'),
    (r'^GWC|^GMV|^GWH',                                'Gree'),
    (r'^HSU|^HAS|^HEU',                                'Haier'),
    (r'^WDV|^MSTL|^MSKMP|^MSM|^MSTE',                 'Midea'),
    (r'^WWS|^WWA',                                      'Westinghouse'),
    (r'^DW\d|^DT\d',                                   'Crafft'),
    (r'^DSA',                                           'Dansat'),
    (r'^HW\d|^AS\d',                                   'Hisense'),
    (r'^UW',                                            'Ruud'),
    (r'^HQAS',                                         'Home Queen'),
    (r'^MPC|^MMPC|^MANDO',                             'Mando'),
    (r'^SAC|^SAS',                                     'Samsung'),
    (r'^(TAC|CW-T|CWT)',                               'TCL'),
    (r'^(FT|FW|FM)\d',                                 'Frigidaire'),
    (r'^TH-C|^TU-C',                                   'Tornado'),
    (r'^ZCP|^ZCH',                                     'Zamil'),
    (r'^GD\d',                                         'General Dan'),
]
ARABIC_BRAND_MAP = {
    'سوبر جنرال': 'Super General', 'جري': 'Gree', 'هاير': 'Haier',
    'ميديا': 'Midea', 'وستنجهاوس': 'Westinghouse', 'كرفت': 'Crafft',
    'دانسات': 'Dansat', 'دان سات': 'Dansat', 'هايسنس': 'Hisense',
    'ال جي': 'LG', 'الجي': 'LG', 'سامسونج': 'Samsung', 'شارب': 'Sharp',
    'اس كي ام': 'SKM', 'هوم كوين': 'Home Queen', 'ماندو': 'Mando',
    'روود': 'Ruud', 'كولن': 'Kolin', 'فريجو': 'Frigidaire',
    'تي سي ال': 'TCL', 'تورنيدو': 'Tornado', 'الزامل': 'Zamil',
    'جنرال دان': 'General Dan', 'ز.ترست': 'Z.Trust',
}
NON_AC_ARABIC = ['مروحة', 'ستارة هوائية', 'خدمة حامل', 'ريبون']
TON_ORDER     = [0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]


def snap_ton(btu, ton_direct):
    val = ton_direct if ton_direct else (btu / 12000 if btu else None)
    if val is None: return None
    return min(TON_ORDER, key=lambda t: abs(t - val))


def parse_name(name: str) -> dict:
    r = {'brand': '', 'model': '', 'ton': None, 'compressor': 'Rotary',
         'ac_type': 'Split', 'cold_hc': 'Cold'}
    models = re.findall(r'\b([A-Z][A-Z0-9\-]{4,})\b', name.upper())
    models = [m for m in models if not re.match(r'^(BTU|WIFI|MODEL|TYPE)$', m)]
    if models: r['model'] = models[0]
    for pat, brand in MODEL_BRAND_MAP:
        if r['model'] and re.match(pat, r['model']): r['brand'] = brand; break
    if not r['brand']:
        for ar, en in ARABIC_BRAND_MAP.items():
            if ar in name: r['brand'] = en; break
    ton_m = re.search(r'(\d+(?:\.\d+)?)\s*طن', name)
    btu_m = re.search(r'\b(\d{4,6})\s*(?:وحدة|BTU)', name)
    r['ton'] = snap_ton(int(btu_m.group(1)) if btu_m else None,
                        float(ton_m.group(1)) if ton_m else None)
    if 'انفيرتر' in name or 'انفيرتير' in name: r['compressor'] = 'Inverter'
    if 'شباك' in name: r['ac_type'] = 'Window'
    elif any(w in name for w in ['ستاند', 'أرضي']): r['ac_type'] = 'Free Standing'
    if 'تدفئة' in name: r['cold_hc'] = 'Hot and Cold'
    return r


def parse_html(html: str, page_num: int) -> list[dict]:
    items = re.findall(
        r'data-product_id="(\d+)"\s+data-product_sku="([^"]+)"\s+aria-label="([^"]+)"', html)
    prices = re.findall(r'<span class="price">(.*?)</span>', html, re.DOTALL)
    urls   = list({u.rstrip('/').split('/')[-1]: u
                   for u in re.findall(r'href="(https://alkhaterstore\.com/product/[^"]+)"', html)
                   }.values())
    results = []
    for i, (pid, sku, label) in enumerate(items):
        name = html_lib.unescape(label)
        name = re.sub(r'^إضافة إلى عربة التسوق:\s*"', '', name).rstrip('"')
        if any(kw in name for kw in NON_AC_ARABIC): continue
        specs = parse_name(name)
        p_sale = p_reg = None
        if i < len(prices):
            nums = [float(n.replace(',','')) for n in re.findall(r'[\d,]+', re.sub(r'<[^>]+>',' ',prices[i])) if len(n)>=3]
            if len(nums)>=2: p_reg, p_sale = max(nums), min(nums)
            elif nums: p_reg = p_sale = nums[0]
        results.append({
            'SKU': sku, 'Product_Name': name,
            'Brand': specs['brand'], 'Model': specs['model'], 'Ton': specs['ton'],
            'Compressor': specs['compressor'], 'AC_Type': specs['ac_type'],
            'Cold_HC': specs['cold_hc'],
            'Price_SAR': p_sale, 'Original_Price_SAR': p_reg,
            'Is_On_Sale': p_sale != p_reg if p_sale else False,
            'URL': urls[i] if i < len(urls) else '',
            'Scraped_At': datetime.now().strftime('%Y-%m-%d %H:%M'),
        })
    return results


def scrape_all() -> list[dict]:
    all_products = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage',
                  '--disable-blink-features=AutomationControlled'])
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800}, locale='en-US')
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.new_page()

        for page_num in range(1, MAX_PAGES + 1):
            url = BASE_URL if page_num == 1 else f"{BASE_URL}/page/{page_num}/"
            print(f"  [Page {page_num}] {url}")
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except PWTimeout:
                print(f"    ⚠️ 타임아웃"); break

            time.sleep(PAGE_WAIT)
            title = page.title()
            if 'Just a moment' in title:
                print(f"    ❌ Cloudflare 차단 (page {page_num})")
                # 추가 대기 후 재시도
                time.sleep(15)
                title = page.title()
                if 'Just a moment' in title:
                    print("    ❌ 재시도 실패 - 중단")
                    break

            html = page.content()
            products = parse_html(html, page_num)
            if not products:
                print(f"    ✅ 마지막 페이지 (page {page_num})")
                break

            all_products.extend(products)
            print(f"    → {len(products)}개 (누계 {len(all_products)}개)")

            next_url = f'air-conditioning/page/{page_num + 1}/'
            if next_url not in html:
                print(f"    ✅ 마지막 페이지 (page {page_num})")
                break
            time.sleep(3)

        browser.close()
    return all_products


def save(products):
    if not products:
        print("⚠️ 수집 없음"); return
    df = pd.DataFrame(products)
    today = datetime.now().strftime('%Y-%m-%d')
    mode = 'a' if os.path.exists(OUTPUT_FILE) else 'w'
    kw   = {'if_sheet_exists': 'replace'} if mode == 'a' else {}
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl', mode=mode, **kw) as w:
        df.to_excel(w, sheet_name=today, index=False)
    print(f"\n💾 {OUTPUT_FILE} | {today} | {len(df)}개")
    ac = df[df['AC_Type']=='Split']
    print(f"Split AC: {len(ac)}개, 브랜드: {df['Brand'].nunique()}개")


if __name__ == '__main__':
    print(f"=== Al Khater Playwright 스크래퍼 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")
    products = scrape_all()
    save(products)
