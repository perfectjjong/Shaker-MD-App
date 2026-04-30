#!/usr/bin/env python3
"""
Extra.com 에어컨 스크래퍼 v4 - Playwright 포팅 (서버 이전용)
- v4 기반 비즈니스 로직 전면 유지
- Selenium + ChromeDriverManager → Playwright 교체
  (ChromeDriverManager 네트워크 장애로 자동화 실패 문제 해결)
- Playwright 번들 Chromium 사용 → 네트워크 의존성 없음
Author: 핍쫑이
"""

import time
import re
import sys
import os
import random

try:
    import pandas as pd
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    from datetime import datetime
except ImportError as e:
    print(f"Missing: {e}\nRun: pip install pandas openpyxl playwright && playwright install chromium")
    sys.exit(1)

# ============================================================
# 설정
# ============================================================
BASE_URL = "https://www.extra.com/en-sa/white-goods/air-conditioner/c/4-402?q=%3Arelevance&page=0&pageSize=96"
APPLY_IN_STOCK_FILTER = True
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) or os.getcwd()
OUTPUT_FILE = os.path.join(CURRENT_DIR, "extra_ac_Prices_Tracking_Master.xlsx")
LOCK_FILE = os.path.join(CURRENT_DIR, "scraper_running.lock")
RUN_TIMESTAMP = datetime.now()

# ============================================================
# Daily 중복 스크래핑 방지
# ============================================================
def check_already_scraped_today():
    """오늘 이미 성공적으로 스크래핑된 데이터가 있으면 True 반환"""
    if not os.path.exists(OUTPUT_FILE):
        return False
    try:
        df = pd.read_excel(OUTPUT_FILE, sheet_name='Prices DB', engine='openpyxl',
                           usecols=['Scraped_At'])
        today = RUN_TIMESTAMP.date()
        df['_date'] = pd.to_datetime(df['Scraped_At'], errors='coerce').dt.date
        today_count = (df['_date'] == today).sum()
        if today_count > 0:
            print(f"⚠️  오늘({today}) 이미 {today_count}개 데이터가 존재합니다.")
            print(f"   Daily 중복 방지: 스크래핑을 건너뜁니다.")
            print(f"   강제 재실행: FORCE_RESCRAPE=1 환경변수 설정 후 실행하세요.")
            return True
        return False
    except Exception as e:
        print(f"⚠️  중복 체크 중 오류 ({e}), 계속 진행합니다.")
        return False


def acquire_lock():
    """락 파일 생성. 이미 실행 중이면 False 반환."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                lock_info = f.read().strip()
            # 락 파일이 2시간 이상 된 경우 스탈(stale)로 판단하고 제거
            lock_time = datetime.fromisoformat(lock_info.split('|')[0].strip())
            age_hours = (datetime.now() - lock_time).total_seconds() / 3600
            if age_hours > 2:
                print(f"⚠️  스탈 락 파일 감지 ({age_hours:.1f}시간 경과). 제거 후 계속 진행합니다.")
                os.remove(LOCK_FILE)
            else:
                print(f"⚠️  스크래퍼가 이미 실행 중입니다. (락 파일: {lock_info})")
                print(f"   중복 실행을 방지합니다. 기존 프로세스 완료 후 재시도하세요.")
                return False
        except Exception:
            os.remove(LOCK_FILE)  # 읽기 오류 시 제거하고 계속
    with open(LOCK_FILE, 'w') as f:
        f.write(f"{datetime.now().isoformat()} | PID:{os.getpid()}")
    return True


def release_lock():
    """락 파일 제거"""
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass

HEADLESS = True
ITEMS_PER_PAGE = 96

SUB_FAMILIES = [
    "Split Air Conditioner",
    "Window Air Conditioner",
    "Free Standing Air Conditioner",
    "Portable Air Conditioner",
]

# ============================================================
# 카테고리 검증/교정
# ============================================================
NON_AC_PATTERNS = [
    r'^SM-[A-Z]\d', r'^SM[A-Z]\d',
    r'^(iPhone|iPad|Galaxy)',
    r'^(WM|WF|WW)\d', r'^WM$',
    r'^(RF|RS|RT|RR)\d',
    r'^HC\d{5}', r'^GIFT\b',
]
WINDOW_KEYWORDS      = ['WINDOW', 'WDV', 'WINDOW AC', 'WINDOW AIR']
WINDOW_MODEL_PREFIXES = ['WDV', 'GJC', 'H182EH', 'H242EH', 'W18', 'W24', 'CLW']
SPLIT_KEYWORDS       = ['SPLIT', 'WALL MOUNT', 'WALL-MOUNT']
SPLIT_MODEL_PREFIXES  = ['NS', 'NT', 'ND', 'NF', 'LA']
FREESTANDING_KEYWORDS = ['FLOOR STANDING', 'FREE STANDING', 'FREESTANDING', 'FLOOR-STANDING']
FREESTANDING_MODEL_PREFIXES = ['APW', 'APQ', 'FS']
PORTABLE_KEYWORDS    = ['PORTABLE', 'PORTABLE AC', 'PORTABLE AIR']
PORTABLE_MODEL_PREFIXES = ['GPH', 'YPH', 'CPH', 'PORT', 'YAS', 'YAE', 'PAC']


def is_non_ac_product(product_name, model_no, brand):
    name_upper  = (product_name or '').upper()
    model_upper = (model_no or '').upper()
    for pattern in NON_AC_PATTERNS:
        if re.match(pattern, model_upper):
            return True
    non_ac_name_kws = ['IPHONE', 'IPAD', 'GALAXY TAB', 'MACBOOK',
                       'WASHING MACHINE', 'REFRIGERATOR', 'DRYER']
    if any(kw in name_upper for kw in non_ac_name_kws):
        return True
    ac_indicators = ['AC', 'AIR CONDITIONER', 'BTU', 'TON', 'SPLIT', 'WINDOW',
                     'INVERTER', 'ROTARY', 'COMPRESSOR', 'COOLING', 'COLD',
                     'FLOOR STANDING', 'FREE STANDING', 'CASSETTE', 'CONCEALED', 'PORTABLE']
    has_ac_keyword = any(kw in name_upper for kw in ac_indicators)
    non_ac_brands = ['APPLE', 'XIAOMI', 'HUAWEI', 'OPPO', 'VIVO', 'REALME', 'HONOR']
    if (brand or '').upper() in non_ac_brands and not has_ac_keyword:
        return True
    model_parts = [p.strip() for p in re.split(r'[/\-]', model_upper) if p.strip()]
    if any(p in ['CHG', 'GAN', 'CBL', 'USB', 'PWR', 'PWB', 'GIFT'] for p in model_parts):
        return True
    if not (brand or '').strip() and not (product_name or '').strip() and not has_ac_keyword:
        return True
    return False


def validate_category(category, product_name, model_no):
    name_upper  = (product_name or '').upper()
    model_upper = (model_no or '').upper()
    is_window = (any(kw in name_upper for kw in WINDOW_KEYWORDS) or
                 any(model_upper.startswith(pfx) for pfx in WINDOW_MODEL_PREFIXES))
    is_split  = (any(kw in name_upper for kw in SPLIT_KEYWORDS) or
                 any(model_upper.startswith(pfx) for pfx in SPLIT_MODEL_PREFIXES))
    is_freestanding = (any(kw in name_upper for kw in FREESTANDING_KEYWORDS) or
                       any(model_upper.startswith(pfx) for pfx in FREESTANDING_MODEL_PREFIXES))
    is_portable = (any(kw in name_upper for kw in PORTABLE_KEYWORDS) or
                   any(model_upper.startswith(pfx) for pfx in PORTABLE_MODEL_PREFIXES))
    if is_window and not is_split and category != 'Window Air Conditioner':
        return 'Window Air Conditioner', True, 'Product name/model indicates Window AC'
    if is_split and not is_window and category == 'Window Air Conditioner':
        return 'Split Air Conditioner', True, 'Product name/model indicates Split AC (not Window)'
    if is_split and not is_window and not is_freestanding and category != 'Split Air Conditioner':
        return 'Split Air Conditioner', True, 'Product name/model indicates Split AC'
    if is_freestanding and not is_split and category != 'Free Standing Air Conditioner':
        return 'Free Standing Air Conditioner', True, 'Product name/model indicates Free Standing AC'
    if is_portable and not is_split and not is_window and not is_freestanding:
        return 'Portable Air Conditioner', True, 'Product name/model indicates Portable AC'
    if category == 'Portable':
        return 'Portable Air Conditioner', True, 'Normalizing Portable category name'
    return category, False, None


# ============================================================
# Playwright 브라우저 설정
# ============================================================
def setup_browser(pw):
    print("  Playwright Chromium 기동 중...")
    browser = pw.chromium.launch(
        headless=HEADLESS,
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-blink-features=AutomationControlled',
        ]
    )
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'
        ),
    )
    # 이미지 차단 → 속도 개선
    context.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico}", lambda route: route.abort())
    page = context.new_page()
    page.set_default_timeout(30000)
    print("  브라우저 준비 완료")
    return browser, context, page


# ============================================================
# 필터 조작
# ============================================================
def accept_cookies(page):
    try:
        btn = page.locator("button:has-text('Allow cookies')").first
        btn.click(timeout=5000)
        page.wait_for_timeout(1000)
    except Exception:
        pass


def _try_check_in_stock(page):
    """In Stock 체크박스 클릭 시도. 이미 체크돼 있으면 True 반환."""
    try:
        cb = page.locator('input[id*="inStock"], input[value*="inStock"]').first
        if cb.is_checked():
            return True
        cb.click()
        page.wait_for_timeout(3000)
        if cb.is_checked():
            return True
    except Exception:
        pass
    try:
        page.locator("label:has-text('In Stock')").first.click()
        page.wait_for_timeout(3000)
        return True
    except Exception:
        pass
    return False


def apply_in_stock_filter(page):
    if not APPLY_IN_STOCK_FILTER:
        print("  In Stock 필터 미적용 (전체 수집 모드)")
        return
    print("  In Stock 필터 적용 중...")
    ok = _try_check_in_stock(page)
    print(f"  In Stock {'완료' if ok else '실패(무시)'}")


def ensure_in_stock_checked(page):
    if not APPLY_IN_STOCK_FILTER:
        return
    try:
        cb = page.locator('input[id*="inStock"], input[value*="inStock"]').first
        if cb.is_checked():
            print("    In Stock 확인됨")
            return
        print("    In Stock 미체크 → 재적용...")
        _try_check_in_stock(page)
    except Exception:
        pass


def check_sub_family(page, sub_family):
    candidates = [sub_family]
    if 'portable' in sub_family.lower():
        candidates = ['Portable Air Conditioner', 'Portable']
    print(f"  {sub_family} 체크 중...")
    for label_text in candidates:
        try:
            lbl = page.locator(f"label:has-text('{label_text}')").first
            lbl.wait_for(state='visible', timeout=8000)
            lbl.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            lbl.click()
            page.wait_for_timeout(3000)
            ensure_in_stock_checked(page)
            print(f"  {sub_family} 체크 완료")
            return True
        except Exception:
            continue
    print(f"  {sub_family} 체크 실패")
    return False


def uncheck_sub_family(page, sub_family):
    candidates = [sub_family]
    if 'portable' in sub_family.lower():
        candidates = ['Portable Air Conditioner', 'Portable']
    try:
        for label_text in candidates:
            try:
                lbl = page.locator(f"label:has-text('{label_text}')").first
                lbl.click(timeout=5000)
                page.wait_for_timeout(2000)
                print(f"  {sub_family} 해제 완료")
                return
            except Exception:
                continue
    except Exception as e:
        print(f"  {sub_family} 해제 실패: {e}")


# ============================================================
# 제품 파싱 (텍스트 기반, 기존 로직 유지)
# ============================================================
BRANDS = [
    'LG', 'GREE', 'MIDEA', 'PANASONIC', 'CLASS PRO', 'CLASSPRO', 'SAMSUNG', 'TCL',
    'HAIER', 'BOSCH', 'TOSHIBA', 'HISENSE', 'CARRIER', 'DAIKIN', 'YORK',
    'GENERAL', 'ZAMIL', 'O GENERAL', 'FUJITSU', 'SHARP', 'HITACHI',
    'WHITE WESTINGHOUSE', 'WESTINGHOUSE', 'WANSA', 'BEKO', 'FRIGIDAIRE',
    'KENWOOD', 'HOME ELEC', 'HOMEELEC', 'CRAFFT', 'SUPER GENERAL', 'NIKAI',
    'AUX', 'BASIC', 'ADMIRAL', 'ZTRUST', 'TRANE', 'ELECTROLUX', 'ARCELIK',
    'TORNADO', 'OLYMPIA', 'KELVINATOR', 'WHIRLPOOL',
]


def parse_product(text, href, category):
    """카드 텍스트 + href에서 제품 정보 추출"""
    data = {}
    text_upper = text.upper()

    # Brand
    data['Brand'] = ''
    for b in BRANDS:
        if b in text_upper:
            data['Brand'] = b.replace('CLASSPRO', 'CLASS PRO').replace('HOMEELEC', 'HOME ELEC')
            break

    # SKU
    m = re.search(r'/p/(\d+)', href or '')
    data['SKU'] = m.group(1) if m else ''

    # Product Name
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    data['Product_Name'] = ''
    for line in lines:
        has_brand = any(b in line.upper() for b in BRANDS)
        has_spec  = bool(re.search(r'\d+,?\d*\s*(BTU|Ton)', line))
        is_promo  = any(x in line for x in ['Use code', 'Al Rajhi', 'Out of Stock',
                                             'eXtra Exclusive', 'Selling Out'])
        if has_brand and has_spec and not is_promo:
            data['Product_Name'] = line
            break
    if not data['Product_Name']:
        for line in lines:
            if len(line) > 20 and not any(x in line for x in ['Use code', 'SAR', 'Save', 'Offer', 'Gift']):
                data['Product_Name'] = line
                break
    if not data['Product_Name']:
        data['Product_Name'] = lines[0] if lines else ''

    data['Category'] = category

    # Cold/HC
    data['Cold_or_HC'] = 'Cold'
    match = re.search(r'Cold or H/C[:\s]*([^•\n]+)', text)
    if match:
        hc = match.group(1).strip()
        if 'Hot and Cold' in hc or 'Heat and Cold' in hc:
            data['Cold_or_HC'] = 'Hot and Cold'
    else:
        if 'Hot and Cold' in text or 'Heat and Cold' in text or 'Heat & Cold' in text:
            data['Cold_or_HC'] = 'Hot and Cold'

    # Ton / BTU
    m = re.search(r'(\d+(?:\.\d+)?)\s*Ton', text)
    data['Cooling_Capacity_Ton'] = m.group(1) if m else ''
    m = re.search(r'([\d,]+)\s*BTU', text)
    data['BTU'] = m.group(1).replace(',', '') if m else ''

    # Compressor (WindFree/Bespoke AI = Samsung inverter tech)
    INVERTER_KEYWORDS = ('Inverter', 'WindFree', 'Wind Free', 'Bespoke AI')
    if any(kw in text for kw in INVERTER_KEYWORDS):
        data['Compressor_Type'] = 'Inverter'
    elif 'Rotary' in text:
        data['Compressor_Type'] = 'Rotary'
    else:
        data['Compressor_Type'] = ''

    # Prices (BTU 값 제외)
    btu_values = {bm.group(1).replace(',', '') for bm in re.finditer(r'([\d,]+)\s*BTU', text, re.IGNORECASE)}
    all_prices = re.findall(r'\b(\d{3,5})\b', text)
    prices = sorted({int(p) for p in all_prices if p not in btu_values and 500 <= int(p) <= 20000}, reverse=True)
    if len(prices) >= 3:
        data['Standard_Price'], data['Sale_Price'], data['Jood_Gold_Price'] = prices[0], prices[1], prices[2]
    elif len(prices) == 2:
        data['Standard_Price'], data['Sale_Price'], data['Jood_Gold_Price'] = prices[0], prices[1], prices[1]
    elif len(prices) == 1:
        data['Standard_Price'] = data['Sale_Price'] = data['Jood_Gold_Price'] = prices[0]
    else:
        data['Standard_Price'] = data['Sale_Price'] = data['Jood_Gold_Price'] = ''

    # Discount
    m = re.search(r'Save\s*(\d+)', text)
    data['Discount_Amount'] = m.group(1) if m else ''
    m = re.search(r'(\d+\.?\d*)%\s*Off', text)
    data['Discount_Rate'] = f"{round(float(m.group(1)))}%" if m else ''

    # Promo
    m = re.search(r'[Cc]ode\s+([A-Za-z0-9]+)', text)
    data['Promo_Code'] = m.group(1) if m else ''
    if 'Al Rajhi' in text:
        data['Promo_Label'] = 'Al Rajhi Offer'
    elif 'eXtra Exclusive' in text:
        data['Promo_Label'] = 'eXtra Exclusive'
    else:
        data['Promo_Label'] = ''

    # Offers / Gifts
    m = re.search(r'(\d+)\s*Offer', text)
    data['Offer_Count'] = m.group(1) if m else '0'
    m = re.search(r'(\d+)\s*Gift', text)
    data['Gift_Count'] = m.group(1) if m else '0'

    # Stock
    data['Stock_Status'] = 'Out of Stock' if ('Out of Stock' in text or 'out of stock' in text) else 'In Stock'
    if 'Selling Out Fast' in text:
        data['Stock_Label'] = 'Selling Out Fast'
    elif 'Featured' in text:
        data['Stock_Label'] = 'Featured'
    else:
        data['Stock_Label'] = ''

    data['eXtra_Exclusive'] = 'Yes' if 'eXtra Exclusive' in text else 'No'

    # 상세페이지 필드 (빈값, scrape_detail에서 채움)
    data['Model_No'] = ''
    data['Gift_Value'] = ''
    data['Warranty_Period'] = ''
    data['Compressor_Warranty'] = ''
    data['Scraped_At'] = RUN_TIMESTAMP
    return data


# ============================================================
# 페이지 스크래핑
# ============================================================
def scrape_current_page(page, category, retry_count=3):
    for attempt in range(retry_count):
        try:
            products = []
            seen = set()
            # 제품 카드(section.product-tile-wrapper) 대기
            try:
                page.wait_for_selector("section.product-tile-wrapper", timeout=20000)
            except PWTimeoutError:
                # 네트워크가 안정되길 추가 대기 후 재시도
                print(f"  제품 카드 대기 타임아웃 (attempt {attempt+1})")
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                if page.locator("section.product-tile-wrapper").count() == 0:
                    if attempt < retry_count - 1:
                        page.reload(wait_until='domcontentloaded')
                        page.wait_for_timeout(5000)
                        continue
                    return products

            # 스크롤 (모든 제품 lazy-load)
            for _ in range(10):
                page.evaluate("window.scrollBy(0, 1000)")
                page.wait_for_timeout(300)
            page.wait_for_timeout(2000)

            # JS로 제품 카드(section.product-tile-wrapper) 기반 텍스트 추출
            # 메뉴/헤더 링크를 완전히 배제
            items = page.evaluate("""
                () => {
                    // section.product-tile-wrapper 안에 있는 /p/ 링크만 수집
                    const cards = Array.from(document.querySelectorAll('section.product-tile-wrapper'));
                    const seen = new Set();
                    const results = [];
                    for (const card of cards) {
                        const link = card.querySelector("a[href*='/p/']");
                        if (!link) continue;
                        const href = link.href || '';
                        const m = href.match(/\\/p\\/(\\d+)/);
                        if (!m) continue;
                        const sku = m[1];
                        if (seen.has(sku)) continue;
                        seen.add(sku);
                        results.push({ sku, href, text: card.innerText || '' });
                    }
                    return results;
                }
            """)

            for item in items:
                try:
                    product = parse_product(item['text'], item['href'], category)
                    product['SKU'] = item['sku']
                    products.append(product)
                except Exception:
                    continue

            if len(products) < 5 and attempt < retry_count - 1:
                print(f"  제품 {len(products)}개만 추출, 재시도...")
                page.reload()
                page.wait_for_timeout(5000)
                continue

            return products

        except Exception as e:
            if attempt < retry_count - 1:
                print(f"  파싱 오류 (재시도 {attempt+1}/{retry_count}): {type(e).__name__}")
                page.wait_for_timeout(3000)
                try:
                    page.reload()
                    page.wait_for_timeout(5000)
                except Exception:
                    pass
            else:
                print(f"  파싱 오류 (최종 실패): {e}")
    return []


def scrape_detail(page, sku, retry=3):
    """상세 페이지에서 Model_No, 보증기간, Gift Value 추출"""
    url = f"https://www.extra.com/en-sa/p/{sku}"

    def _parse(text):
        d = {}
        m = re.search(r'Model\s*No[:\.]?\s*([A-Z0-9\-\_\.\/]+)', text, re.IGNORECASE)
        d['Model_No'] = m.group(1).strip().rstrip('/') if m else ''
        m = re.search(r'(\d+)\s*Year[s]?\s*(?:warranty|Warranty)', text, re.IGNORECASE)
        if not m:
            m = re.search(r'[Ww]arranty[:\s]*(\d+)\s*Year', text, re.IGNORECASE)
        d['Warranty_Period'] = f"{m.group(1)} Years" if m else ''
        m = re.search(r'[Ww]arranty\s*\(?compressor\)?\s*[:.]?\s*(\d+)\s*Year', text, re.IGNORECASE)
        if not m:
            m = re.search(r'compressor\)?\s*[:.]?\s*(\d+)\s*Year', text, re.IGNORECASE)
        d['Compressor_Warranty'] = f"{m.group(1)} Years" if m else ''
        m = re.search(r'gift\(s\)?\s*worth\s*(\d+)', text, re.IGNORECASE)
        d['Gift_Value'] = m.group(1) if m else ''
        return d

    data = {}
    for attempt in range(retry):
        try:
            page.goto(url, timeout=8000, wait_until='domcontentloaded')
            text = page.inner_text('body')
            data = _parse(text)
            break
        except PWTimeoutError:
            try:
                page.evaluate("window.stop()")
                text = page.inner_text('body')
                if len(text) > 50:
                    data = _parse(text)
                    if data.get('Model_No'):
                        break
            except Exception:
                pass
            if attempt < retry - 1:
                page.wait_for_timeout(1000)
        except Exception as e:
            print(f"  SKU {sku} 상세 오류: {e}")
            break
    return data


def get_total_products(page):
    # .pagination-products-count 에서 "1 - 96 of 468 products" 형태 파싱
    try:
        page.wait_for_timeout(2000)
        el = page.locator('.pagination-products-count').first
        text = el.inner_text(timeout=5000)
        m = re.search(r'of\s+(\d+)\s*products?', text)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)\s*products?', text)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    # fallback: 페이지 텍스트 전체 검색
    try:
        text = page.inner_text('body')
        m = re.search(r'of\s+(\d+)\s*products?', text)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def goto_page(page, page_num):
    """다음 페이지로 이동 (URL pg= 파라미터 방식). 성공=True."""
    # 버튼 클릭 시도 (Svelte pagination)
    try:
        for selector in ['.pagination-wrapper a.nav-link', 'ul.nav li a', 'li.nav-item a']:
            links = page.locator(selector).all()
            for link in links:
                try:
                    if link.inner_text(timeout=1000).strip() == str(page_num):
                        link.scroll_into_view_if_needed()
                        page.wait_for_timeout(1000)
                        link.click()
                        page.wait_for_timeout(6000)
                        print(f"  버튼 클릭으로 페이지 {page_num} 이동")
                        return True
                except Exception:
                    continue
    except Exception:
        pass

    # URL 기반 이동 (pg= 파라미터)
    try:
        cur_url = page.url
        if 'pg=' in cur_url:
            new_url = re.sub(r'pg=\d+', f'pg={page_num}', cur_url)
        elif 'page=' in cur_url:
            new_url = re.sub(r'page=\d+', f'pg={page_num}', cur_url)
        elif '?' in cur_url:
            new_url = cur_url + f'&pg={page_num}'
        else:
            new_url = cur_url + f'?pg={page_num}'
        page.goto(new_url, timeout=30000, wait_until='domcontentloaded')
        page.wait_for_timeout(5000)
        count = page.locator("a[href*='/p/']").count()
        if count > 0:
            print(f"  URL 기반 이동 성공 (pg={page_num}, 링크 {count}개)")
            return True
    except Exception as e:
        print(f"  URL 기반 이동 실패: {e}")
    return False


def scrape_sub_family(page, sub_family):
    print(f"\n{'='*60}")
    print(f"  {sub_family} 스크래핑 시작")
    print(f"{'='*60}")

    all_products = []
    seen_skus = set()

    if not check_sub_family(page, sub_family):
        print(f"  {sub_family} 건너뜀")
        return all_products

    total_products = get_total_products(page)
    if total_products:
        print(f"  총 {total_products}개 예상")
        max_pages = (total_products // ITEMS_PER_PAGE) + 1
    else:
        print(f"  총 제품 수 확인 실패, 최대 10페이지로 제한")
        max_pages = 10

    current_page = 1
    while current_page <= max_pages:
        print(f"  페이지 {current_page}/{max_pages} 스크래핑...")
        products = scrape_current_page(page, sub_family)

        new_count = 0
        for p in products:
            if p['SKU'] not in seen_skus:
                seen_skus.add(p['SKU'])
                all_products.append(p)
                new_count += 1
        print(f"  {len(products)}개 추출 (신규 {new_count}개), 누적: {len(all_products)}개")

        if total_products and len(all_products) >= total_products:
            print(f"  목표 {total_products}개 도달")
            break
        if new_count == 0:
            print(f"  신규 없음, 종료")
            break

        next_page = current_page + 1
        if next_page > max_pages:
            break
        if goto_page(page, next_page):
            current_page = next_page
        else:
            break

    uncheck_sub_family(page, sub_family)

    try:
        page.goto(BASE_URL, timeout=30000, wait_until='domcontentloaded')
    except PWTimeoutError:
        print("  메인 페이지 타임아웃, 계속...")
    page.wait_for_timeout(3000)
    apply_in_stock_filter(page)

    print(f"  {sub_family} 완료: {len(all_products)}개")
    return all_products


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 60)
    print("  Extra.com 에어컨 스크래퍼 v4 (Playwright)")
    print(f"  Sub Family 순차 스크래핑 / pageSize={ITEMS_PER_PAGE}")
    print("=" * 60)

    # ── Daily 중복 방지 체크 ──────────────────────────────────
    force = os.environ.get('FORCE_RESCRAPE', '').strip() == '1'
    if not force:
        if check_already_scraped_today():
            sys.exit(0)   # 정상 종료 (이미 완료됨)
        if not acquire_lock():
            sys.exit(2)   # 다른 인스턴스 실행 중
    else:
        print("  ℹ️  FORCE_RESCRAPE=1: 오늘 데이터 덮어쓰기 모드")
        acquire_lock()    # force 시에도 락은 획득
    # ──────────────────────────────────────────────────────────

    all_products = []

    with sync_playwright() as pw:
        browser, context, page = setup_browser(pw)
        try:
            # 첫 페이지 로드
            print(f"\n  페이지 로딩: {BASE_URL}")
            try:
                page.goto(BASE_URL, timeout=30000, wait_until='domcontentloaded')
            except PWTimeoutError:
                print("  페이지 로드 타임아웃, 부분 로드로 계속...")
            page.wait_for_timeout(5000)
            accept_cookies(page)
            apply_in_stock_filter(page)

            # Sub Family별 스크래핑
            for sf in SUB_FAMILIES:
                all_products.extend(scrape_sub_family(page, sf))

            # 전체 스캔 (미분류 누락 방지)
            print(f"\n{'='*60}")
            print("  Sub Family 필터 없이 전체 스캔 (미분류 누락 방지)...")
            print(f"{'='*60}")
            try:
                page.goto(BASE_URL, timeout=30000, wait_until='domcontentloaded')
                page.wait_for_timeout(5000)
                total_all = get_total_products(page)
                max_pages_all = (total_all // 96) + 1 if total_all else 5
                print(f"  전체 제품 수: {total_all or '?'}개, 최대 {max_pages_all}페이지")
                existing_skus = {p['SKU'] for p in all_products}
                for pg in range(max_pages_all):
                    if pg > 0:
                        try:
                            cur_url = page.url
                            if 'pg=' in cur_url:
                                new_url = re.sub(r'pg=\d+', f'pg={pg + 1}', cur_url)
                            elif 'page=' in cur_url:
                                new_url = re.sub(r'page=\d+', f'pg={pg + 1}', cur_url)
                            else:
                                new_url = cur_url + f'&pg={pg + 1}'
                            page.goto(new_url, timeout=30000, wait_until='domcontentloaded')
                            page.wait_for_timeout(4000)
                        except Exception:
                            break
                    pg_products = scrape_current_page(page, 'Unknown')
                    new_cnt = sum(1 for p in pg_products if p['SKU'] not in existing_skus)
                    for p in pg_products:
                        if p['SKU'] not in existing_skus:
                            all_products.append(p)
                            existing_skus.add(p['SKU'])
                    print(f"  페이지 {pg+1}: {len(pg_products)}개 스캔, 미분류 신규 {new_cnt}개")
                    if new_cnt == 0 and pg > 0:
                        break
            except Exception as e:
                print(f"  전체 스캔 오류 (무시): {e}")

            # 중복 제거
            seen = set()
            unique = []
            for p in all_products:
                if p['SKU'] not in seen:
                    seen.add(p['SKU'])
                    unique.append(p)
            all_products = unique
            print(f"\n  중복 제거 후: {len(all_products)}개")

            # 상세 정보 수집 (timeout 단축)
            page.set_default_timeout(8000)
            total = len(all_products)
            print(f"\n  상세 정보 수집 중... (총 {total}개)")
            detail_start = time.time()
            detail_success = detail_fail = 0
            for i, p in enumerate(all_products):
                if p.get('SKU'):
                    detail = scrape_detail(page, p['SKU'])
                    if detail and any(v for v in detail.values()):
                        p.update({k: v for k, v in detail.items() if v})
                        detail_success += 1
                    else:
                        detail_fail += 1
                    if (i + 1) % 10 == 0:
                        elapsed = time.time() - detail_start
                        rate = (i + 1) / elapsed * 60
                        remaining = (total - i - 1) / (rate / 60) if rate > 0 else 0
                        print(f"  진행: {i+1}/{total} (성공 {detail_success}, 실패 {detail_fail}, "
                              f"{elapsed:.0f}s 경과, 잔여 ~{remaining:.0f}s)")
                    time.sleep(random.uniform(0.3, 0.8))
            print(f"  상세 수집 완료: {detail_success}/{total} 성공, {detail_fail}개 실패")

        finally:
            browser.close()

    # 카테고리 검증 + 비AC 필터링
    print(f"\n  카테고리 검증 중...")
    corrected_count = removed_count = 0
    validated = []
    aux_prefixes = ['ATW', 'ATWH', 'ACH', 'ACF', 'ASW', 'AMS', 'AMH']
    for p in all_products:
        pname = p.get('Product_Name', '')
        model = p.get('Model_No', '')
        brand = p.get('Brand', '')
        cat   = p.get('Category', '')
        if not brand and model and any(model.upper().startswith(px) for px in aux_prefixes):
            p['Brand'] = brand = 'AUX'
        if is_non_ac_product(pname, model, brand):
            removed_count += 1
            print(f"  비AC 제거: {brand} {pname[:40]} (SKU: {p.get('SKU')})")
            continue
        new_cat, was_corrected, reason = validate_category(cat, pname, model)
        if was_corrected:
            corrected_count += 1
            print(f"  카테고리 교정: {cat} → {new_cat} | {pname[:40]}")
            p['Category'] = new_cat
        validated.append(p)
    all_products = validated
    print(f"  검증 완료: {corrected_count}건 교정, {removed_count}건 비AC 제거")

    # ── 스파이크 감지 (중복/과다 수집 방지) ──────────────────────
    if all_products and os.path.exists(OUTPUT_FILE):
        try:
            df_hist = pd.read_excel(OUTPUT_FILE, sheet_name='Prices DB', engine='openpyxl',
                                    usecols=['Scraped_At', 'SKU'])
            df_hist['_date'] = pd.to_datetime(df_hist['Scraped_At'], errors='coerce').dt.date
            today_date = RUN_TIMESTAMP.date()
            # 최근 14일(오늘 제외) 일별 SKU 수
            recent = df_hist[df_hist['_date'] != today_date].groupby('_date')['SKU'].nunique()
            if len(recent) >= 3:
                avg_sku = recent.tail(7).mean()
                today_sku = len(all_products)
                spike_ratio = today_sku / avg_sku if avg_sku > 0 else 1.0
                print(f"\n  [스파이크 체크] 오늘 {today_sku}개 / 7일 평균 {avg_sku:.0f}개 (비율 {spike_ratio:.2f}x)")
                if spike_ratio > 1.5:
                    print(f"  ⚠️  스파이크 감지! ({spike_ratio:.1f}x > 1.5x 임계치)")
                    # 가장 최근 날짜(오늘 제외)의 SKU만 기준으로 사용
                    # (전체 역사 기준이면 폐지된 SKU도 포함되어 필터 무효화됨)
                    recent_dates = sorted(df_hist[df_hist['_date'] != today_date]['_date'].unique())
                    most_recent_date = recent_dates[-1] if recent_dates else None
                    if most_recent_date:
                        known_skus = set(str(s) for s in
                            df_hist[df_hist['_date'] == most_recent_date]['SKU'].dropna().unique())
                        print(f"  → 기준 날짜: {most_recent_date} ({len(known_skus)}개 SKU)")
                    else:
                        known_skus = set()
                    normal = [p for p in all_products if str(p['SKU']) in known_skus]
                    extra  = [p for p in all_products if str(p['SKU']) not in known_skus]
                    print(f"  → 알려진 SKU: {len(normal)}개 유지 / 신규 SKU: {len(extra)}개 별도 저장")
                    # 신규 SKU를 별도 파일로 저장
                    if extra:
                        review_file = os.path.join(CURRENT_DIR,
                            f"extra_new_skus_{today_date.strftime('%Y%m%d')}.xlsx")
                        pd.DataFrame(extra).to_excel(review_file, index=False)
                        print(f"  → 검토 파일: {review_file}")
                    all_products = normal
                    print(f"  → 최종 수집: {len(all_products)}개 (스파이크 방지 적용)")
        except Exception as e:
            print(f"  스파이크 체크 오류 (무시): {e}")
    # ─────────────────────────────────────────────────────────────

    # 저장
    if all_products:
        df_new = pd.DataFrame(all_products)
        cols = [
            'Scraped_At', 'Brand', 'Product_Name', 'Model_No', 'SKU', 'Category',
            'Cold_or_HC', 'Cooling_Capacity_Ton', 'BTU', 'Compressor_Type',
            'Standard_Price', 'Sale_Price', 'Jood_Gold_Price',
            'Discount_Amount', 'Discount_Rate',
            'Promo_Code', 'Promo_Label', 'Offer_Count', 'Gift_Count', 'Gift_Value',
            'Warranty_Period', 'Compressor_Warranty',
            'Stock_Status', 'Stock_Label', 'eXtra_Exclusive',
        ]
        df_new = df_new.reindex(columns=[c for c in cols if c in df_new.columns])

        if os.path.exists(OUTPUT_FILE):
            df_existing = pd.read_excel(OUTPUT_FILE, sheet_name='Prices DB', engine='openpyxl')
            today_date = RUN_TIMESTAMP.date()
            df_existing['_date'] = pd.to_datetime(df_existing['Scraped_At'], errors='coerce').dt.date
            today_count = (df_existing['_date'] == today_date).sum()
            if today_count > 0:
                df_existing = df_existing[df_existing['_date'] != today_date]
                print(f"  오늘({today_date}) 기존 {today_count}개 제거 후 최신 데이터로 교체")
            df_existing = df_existing.drop(columns=['_date'])
            df_all = pd.concat([df_existing, df_new], ignore_index=True)
            print(f"  기존 {len(df_existing)}개 + 신규 {len(df_new)}개 = 누적 {len(df_all)}개")
        else:
            df_all = df_new
            print(f"  신규 파일 생성: {len(df_all)}개")

        df_all.to_excel(OUTPUT_FILE, index=False, sheet_name='Prices DB', engine='openpyxl')
        release_lock()   # ← 성공 저장 후 락 해제
        print("\n" + "=" * 60)
        print(f"  완료! 이번 수집: {len(df_new)}개 / 누적: {len(df_all)}개")
        print(f"  파일: {OUTPUT_FILE}")
        print(f"  시각: {RUN_TIMESTAMP}")
        print("=" * 60)
        print(f"\n  브랜드별:\n{df_new['Brand'].value_counts().head(10).to_string()}")
        print(f"\n  카테고리별:\n{df_new['Category'].value_counts().to_string()}")
    else:
        release_lock()   # ← 실패 시에도 락 해제
        print("\n  수집 실패 (0개)")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        release_lock()   # ← 예외 발생 시에도 락 해제
        raise
