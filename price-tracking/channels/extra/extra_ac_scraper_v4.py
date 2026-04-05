#!/usr/bin/env python3
"""
Extra.com 에어컨 스크래퍼 v5 - Playwright 버전
- v4 기반 Selenium → Playwright (async) 전환 (GitHub Actions 호환)
- BTU 값이 가격으로 잘못 인식되는 문제 수정
- Promo Code 대소문자 문제 수정 (extra10)
- 브랜드 목록 확장
- Scraped_At 타임스탬프 추가, 누적 저장 방식
Author: 핍쫑이
Date: 2026-04-05
"""

import asyncio
import time
import re
import sys
import os
import random

# Windows 콘솔 UTF-8 출력 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import pandas as pd
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
    from datetime import datetime
except ImportError as e:
    print("=" * 60)
    print("필수 패키지 설치 필요!")
    print("=" * 60)
    print(f"\n오류: {e}\n")
    print("pip install playwright pandas openpyxl")
    print("playwright install chromium")
    print("=" * 60)
    sys.exit(1)

# ============================================================
# 설정
# ============================================================
BASE_URL = "https://www.extra.com/en-sa/white-goods/air-conditioner/c/4-402?q=%3Arelevance&page=0&pageSize=96"
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if os.path.dirname(os.path.abspath(__file__)) else os.getcwd()

# 누적 저장 파일 (고정 파일명 - 매번 append)
OUTPUT_FILE = os.path.join(CURRENT_DIR, "extra_ac_Prices_Tracking_Master.xlsx")
# 스크래핑 실행 시각 (타임스탬프)
RUN_TIMESTAMP = datetime.now()

# 옵션
HEADLESS = True
ITEMS_PER_PAGE = 96

# Sub Family 목록 (순서대로 처리)
SUB_FAMILIES = [
    "Split Air Conditioner",
    "Window Air Conditioner",
    "Free Standing Air Conditioner"
]

# ============================================================
# 카테고리 검증/교정
# ============================================================
NON_AC_PATTERNS = [
    r'^SM-[A-Z]\d', r'^SM[A-Z]\d', r'^(iPhone|iPad|Galaxy)',
    r'^(WM|WF|WW)\d', r'^(RF|RS|RT|RR)\d',
]

WINDOW_KEYWORDS = ['WINDOW', 'WDV', 'WINDOW AC', 'WINDOW AIR']
WINDOW_MODEL_PREFIXES = ['WDV', 'GJC', 'H182EH', 'H242EH', 'W18', 'W24']
SPLIT_KEYWORDS = ['SPLIT', 'WALL MOUNT', 'WALL-MOUNT']
SPLIT_MODEL_PREFIXES = ['CLW', 'NS', 'NT', 'ND', 'NF', 'LA']
FREESTANDING_KEYWORDS = ['FLOOR STANDING', 'FREE STANDING', 'FREESTANDING', 'FLOOR-STANDING']
FREESTANDING_MODEL_PREFIXES = ['APW', 'APQ', 'FS']


def is_non_ac_product(product_name, model_no, brand):
    name_upper = (product_name or '').upper()
    model_upper = (model_no or '').upper()
    for pattern in NON_AC_PATTERNS:
        if re.match(pattern, model_upper):
            return True
    ac_indicators = ['AC', 'AIR CONDITIONER', 'BTU', 'TON', 'SPLIT', 'WINDOW',
                     'INVERTER', 'ROTARY', 'COMPRESSOR', 'COOLING', 'COLD',
                     'FLOOR STANDING', 'FREE STANDING', 'CASSETTE', 'CONCEALED']
    has_ac_keyword = any(kw in name_upper for kw in ac_indicators)
    non_ac_brands = ['APPLE', 'XIAOMI', 'HUAWEI', 'OPPO', 'VIVO', 'REALME', 'HONOR']
    if (brand or '').upper() in non_ac_brands and not has_ac_keyword:
        return True
    return False


def validate_category(category, product_name, model_no):
    name_upper = (product_name or '').upper()
    model_upper = (model_no or '').upper()
    is_window = (any(kw in name_upper for kw in WINDOW_KEYWORDS) or
                 any(model_upper.startswith(pfx) for pfx in WINDOW_MODEL_PREFIXES))
    is_split = (any(kw in name_upper for kw in SPLIT_KEYWORDS) or
                any(model_upper.startswith(pfx) for pfx in SPLIT_MODEL_PREFIXES))
    is_freestanding = (any(kw in name_upper for kw in FREESTANDING_KEYWORDS) or
                       any(model_upper.startswith(pfx) for pfx in FREESTANDING_MODEL_PREFIXES))
    if is_window and not is_split and category != 'Window Air Conditioner':
        return 'Window Air Conditioner', True, 'Product name/model indicates Window AC'
    if is_split and not is_window and not is_freestanding and category != 'Split Air Conditioner':
        return 'Split Air Conditioner', True, 'Product name/model indicates Split AC'
    if is_freestanding and not is_split and category != 'Free Standing Air Conditioner':
        return 'Free Standing Air Conditioner', True, 'Product name/model indicates Free Standing AC'
    return category, False, None


# ============================================================
# Playwright helpers
# ============================================================

async def setup_browser():
    print("Browser setup (Playwright Chromium)...")
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=HEADLESS,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )
    context.set_default_timeout(30000)
    context.set_default_navigation_timeout(90000)
    page = await context.new_page()
    print("Browser ready")
    return pw, browser, context, page


async def accept_cookies(page):
    try:
        btn = page.locator("button:has-text('Allow cookies')")
        if await btn.count() > 0:
            await btn.first.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass


async def apply_in_stock_filter(page):
    try:
        print("  In Stock filter...")
        # Try checkbox input
        checkbox = page.locator('input[id*="inStock"], input[value*="inStock"]')
        if await checkbox.count() > 0:
            cb = checkbox.first
            if await cb.is_checked():
                print("  In Stock already checked")
                return
            await cb.click()
            await page.wait_for_timeout(3000)
            if await cb.is_checked():
                print("  In Stock checked")
                return
            # Fallback: click label
            label = page.locator("label:has-text('In Stock')")
            if await label.count() > 0:
                await label.first.click()
                await page.wait_for_timeout(3000)
                print("  In Stock label clicked")
            return

        # Fallback: label click
        label = page.locator("label:has-text('In Stock')")
        if await label.count() > 0:
            await label.first.click()
            await page.wait_for_timeout(3000)
            print("  In Stock applied (label)")
    except Exception as e:
        print(f"  In Stock filter error: {e}")


async def ensure_in_stock_checked(page):
    try:
        await page.wait_for_timeout(1000)
        checkbox = page.locator('input[id*="inStock"], input[value*="inStock"]')
        if await checkbox.count() > 0:
            cb = checkbox.first
            if await cb.is_checked():
                return
            await cb.click()
            await page.wait_for_timeout(3000)
            if not await cb.is_checked():
                label = page.locator("label:has-text('In Stock')")
                if await label.count() > 0:
                    await label.first.click()
                    await page.wait_for_timeout(3000)
    except Exception:
        pass


async def check_sub_family(page, sub_family):
    try:
        print(f"  {sub_family} check...")
        label = page.locator(f"label:has-text('{sub_family}')")
        if await label.count() == 0:
            print(f"  {sub_family} label not found")
            return False
        await label.first.scroll_into_view_if_needed()
        await page.wait_for_timeout(1000)
        await label.first.click()
        await page.wait_for_timeout(3000)
        print(f"  {sub_family} checked")
        await ensure_in_stock_checked(page)
        return True
    except Exception as e:
        print(f"  {sub_family} check failed: {e}")
        return False


async def uncheck_sub_family(page, sub_family):
    try:
        print(f"  {sub_family} uncheck...")
        label = page.locator(f"label:has-text('{sub_family}')")
        if await label.count() > 0:
            await label.first.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)
            await label.first.click()
            await page.wait_for_timeout(2000)
            print(f"  {sub_family} unchecked")
    except Exception as e:
        print(f"  {sub_family} uncheck failed: {e}")


def parse_product_text(text, category):
    """Parse product info from element text (same logic as v4)."""
    data = {}
    try:
        brands = ['LG', 'GREE', 'MIDEA', 'PANASONIC', 'CLASS PRO', 'CLASSPRO', 'SAMSUNG', 'TCL',
                  'HAIER', 'BOSCH', 'TOSHIBA', 'HISENSE', 'CARRIER', 'DAIKIN', 'YORK',
                  'GENERAL', 'ZAMIL', 'O GENERAL', 'FUJITSU', 'SHARP', 'HITACHI',
                  'WHITE WESTINGHOUSE', 'WESTINGHOUSE', 'WANSA', 'BEKO', 'FRIGIDAIRE',
                  'KENWOOD', 'HOME ELEC', 'HOMEELEC', 'CRAFFT', 'SUPER GENERAL', 'NIKAI']
        data['Brand'] = ''
        text_upper = text.upper()
        for b in brands:
            if b in text_upper:
                data['Brand'] = b.replace('CLASSPRO', 'CLASS PRO').replace('HOMEELEC', 'HOME ELEC')
                break

        data['SKU'] = ''
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        data['Product_Name'] = ''
        for line in lines:
            has_brand = any(b in line.upper() for b in brands)
            has_spec = bool(re.search(r'\d+,?\d*\s*(BTU|Ton)', line))
            is_promo = any(x in line for x in ['Use code', 'Al Rajhi', 'Out of Stock', 'eXtra Exclusive', 'Selling Out'])
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
        data['Cold_or_HC'] = 'Cold'
        match = re.search(r'Cold or H/C[:\s]*([^•\n]+)', text)
        if match:
            hc_text = match.group(1).strip()
            if 'Hot and Cold' in hc_text or 'Heat and Cold' in hc_text:
                data['Cold_or_HC'] = 'Hot and Cold'
        elif 'Hot and Cold' in text or 'Heat and Cold' in text or 'Heat & Cold' in text:
            data['Cold_or_HC'] = 'Hot and Cold'

        m = re.search(r'(\d+(?:\.\d+)?)\s*Ton', text)
        data['Cooling_Capacity_Ton'] = m.group(1) if m else ''
        m = re.search(r'([\d,]+)\s*BTU', text)
        data['BTU'] = m.group(1).replace(',', '') if m else ''

        if 'Inverter' in text:
            data['Compressor_Type'] = 'Inverter'
        elif 'Rotary' in text:
            data['Compressor_Type'] = 'Rotary'
        else:
            data['Compressor_Type'] = ''

        btu_values = set()
        for btu_match in re.finditer(r'([\d,]+)\s*BTU', text, re.IGNORECASE):
            btu_values.add(btu_match.group(1).replace(',', ''))

        all_prices = re.findall(r'\b(\d{3,5})\b', text)
        prices = [int(p) for p in all_prices if p not in btu_values and 500 <= int(p) <= 20000]
        prices = sorted(set(prices), reverse=True)

        if len(prices) >= 3:
            data['Standard_Price'] = prices[0]
            data['Sale_Price'] = prices[1]
            data['Jood_Gold_Price'] = prices[2]
        elif len(prices) == 2:
            data['Standard_Price'] = prices[0]
            data['Sale_Price'] = prices[1]
            data['Jood_Gold_Price'] = prices[1]
        elif len(prices) == 1:
            data['Standard_Price'] = prices[0]
            data['Sale_Price'] = prices[0]
            data['Jood_Gold_Price'] = prices[0]
        else:
            data['Standard_Price'] = ''
            data['Sale_Price'] = ''
            data['Jood_Gold_Price'] = ''

        m = re.search(r'Save\s*(\d+)', text)
        data['Discount_Amount'] = m.group(1) if m else ''
        m = re.search(r'(\d+\.?\d*)%\s*Off', text)
        data['Discount_Rate'] = f"{round(float(m.group(1)))}%" if m else ''

        m = re.search(r'[Cc]ode\s+([A-Za-z0-9]+)', text)
        data['Promo_Code'] = m.group(1) if m else ''
        if 'Al Rajhi' in text:
            data['Promo_Label'] = 'Al Rajhi Offer'
        elif 'eXtra Exclusive' in text:
            data['Promo_Label'] = 'eXtra Exclusive'
        else:
            data['Promo_Label'] = ''

        m = re.search(r'(\d+)\s*Offer', text)
        data['Offer_Count'] = m.group(1) if m else '0'
        m = re.search(r'(\d+)\s*Gift', text)
        data['Gift_Count'] = m.group(1) if m else '0'

        data['Stock_Status'] = 'In Stock'
        if 'Selling Out Fast' in text:
            data['Stock_Label'] = 'Selling Out Fast'
        elif 'Featured' in text:
            data['Stock_Label'] = 'Featured'
        else:
            data['Stock_Label'] = ''
        data['eXtra_Exclusive'] = 'Yes' if 'eXtra Exclusive' in text else 'No'

        data['Model_No'] = ''
        data['Gift_Value'] = ''
        data['Warranty_Period'] = ''
        data['Compressor_Warranty'] = ''
        data['Scraped_At'] = RUN_TIMESTAMP

    except Exception as e:
        print(f"  Parse error: {e}")
    return data


async def scrape_current_page(page, category, retry_count=3):
    """Scrape products from current page."""
    for attempt in range(retry_count):
        try:
            products = []
            seen = set()

            try:
                await page.wait_for_selector("a[href*='/p/']", timeout=15000)
            except PlaywrightTimeout:
                print(f"  Product links timeout (attempt {attempt+1})")
                if attempt < retry_count - 1:
                    await page.reload()
                    await page.wait_for_timeout(5000)
                    continue
                return products

            # Scroll to load all products
            for _ in range(10):
                await page.evaluate("window.scrollBy(0, 1000)")
                await page.wait_for_timeout(300)
            await page.wait_for_timeout(2000)

            links = await page.query_selector_all("a[href*='/p/']")

            for link in links:
                try:
                    href = await link.get_attribute('href') or ''
                    m = re.search(r'/p/(\d+)', href)
                    if not m:
                        continue
                    sku = m.group(1)
                    if sku in seen:
                        continue
                    seen.add(sku)

                    # Walk up to find container with product info
                    container = link
                    for _ in range(8):
                        parent = await container.evaluate_handle("el => el.parentElement")
                        parent_text = await parent.inner_text() if parent else ""
                        container_text = await container.inner_text() if container else ""
                        if parent and len(str(parent_text)) > len(str(container_text)):
                            container = parent
                        if 'BTU' in str(parent_text) or 'Ton' in str(parent_text):
                            break

                    text = await container.inner_text()
                    product = parse_product_text(text, category)
                    product['SKU'] = sku

                    if product.get('Brand') or product.get('BTU'):
                        products.append(product)
                except Exception:
                    continue

            if len(products) < 5 and attempt < retry_count - 1:
                print(f"  Only {len(products)} products (too few), retrying...")
                await page.reload()
                await page.wait_for_timeout(5000)
                continue

            return products
        except Exception as e:
            if attempt < retry_count - 1:
                print(f"  Parse error (retry {attempt+1}/{retry_count}): {type(e).__name__}")
                await page.wait_for_timeout(3000)
                await page.reload()
                await page.wait_for_timeout(5000)
            else:
                print(f"  Parse error (final): {e}")
    return []


async def scrape_detail(page, sku, retry=3):
    """Scrape detail page for additional info."""
    url = f"https://www.extra.com/en-sa/p/{sku}"
    data = {}

    def _parse_body_text(text):
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

    for attempt in range(retry):
        try:
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            await page.wait_for_selector("body", timeout=8000)
            text = await page.inner_text("body")
            data = _parse_body_text(text)
            break
        except PlaywrightTimeout:
            try:
                text = await page.inner_text("body")
                if text and len(text) > 50:
                    data = _parse_body_text(text)
                    if data.get('Model_No'):
                        break
            except Exception:
                pass
            if attempt < retry - 1:
                await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"  SKU {sku} detail error: {e}")
            break

    return data


async def get_total_products(page):
    try:
        await page.wait_for_timeout(2000)
        el = page.locator("*:has-text('products')")
        texts = await el.all_inner_texts()
        for text in texts:
            match = re.search(r'of\s+(\d+)\s*products?', text)
            if match:
                return int(match.group(1))
            match = re.search(r'(\d+)\s*products?', text)
            if match:
                val = int(match.group(1))
                if val > 0:
                    return val
    except Exception:
        pass
    return None


async def scrape_sub_family(page, sub_family):
    print(f"\n{'='*60}")
    print(f"  {sub_family} scraping start")
    print(f"{'='*60}")

    all_products = []
    seen_skus = set()

    if not await check_sub_family(page, sub_family):
        print(f"  {sub_family} check failed, skipping")
        return all_products

    total_products = await get_total_products(page)
    if total_products:
        print(f"  Total {total_products} products expected")
        max_pages = (total_products // 96) + 1
    else:
        print(f"  Total unknown, limiting to 10 pages")
        max_pages = 10

    current_page = 1
    while current_page <= max_pages:
        print(f"\n  Page {current_page}/{max_pages} scraping...")
        products = await scrape_current_page(page, sub_family)

        new_count = 0
        for p in products:
            if p['SKU'] not in seen_skus:
                seen_skus.add(p['SKU'])
                all_products.append(p)
                new_count += 1

        print(f"  {len(products)} extracted (new {new_count}), total: {len(all_products)}")

        if total_products and len(all_products) >= total_products:
            print(f"  Target {total_products} reached")
            break

        if new_count == 0:
            print(f"  No new products, stopping pagination")
            break

        next_page = current_page + 1
        if next_page > max_pages:
            break

        # Try pagination
        navigated = False
        try:
            # Method 1: nav-link with page number
            nav_links = page.locator('.pagination-wrapper a.nav-link')
            count = await nav_links.count()
            for i in range(count):
                link = nav_links.nth(i)
                text = (await link.inner_text()).strip()
                if text == str(next_page):
                    await link.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)
                    await link.click()
                    await page.wait_for_timeout(5000)
                    current_page = next_page
                    navigated = True
                    break
        except Exception:
            pass

        if not navigated:
            try:
                # Method 2: li.nav-item links
                nav_items = page.locator('li.nav-item a')
                count = await nav_items.count()
                for i in range(count):
                    link = nav_items.nth(i)
                    text = (await link.inner_text()).strip()
                    if text == str(next_page):
                        await link.click()
                        await page.wait_for_timeout(5000)
                        current_page = next_page
                        navigated = True
                        break
            except Exception:
                pass

        if not navigated:
            try:
                # Method 3: li.next
                next_btn = page.locator('li.next:not(.hidden) a')
                if await next_btn.count() > 0:
                    await next_btn.first.click()
                    await page.wait_for_timeout(5000)
                    current_page = next_page
                    navigated = True
            except Exception:
                pass

        if not navigated:
            # Method 4: URL-based navigation
            try:
                current_url = page.url
                if 'page=' in current_url:
                    new_url = re.sub(r'page=\d+', f'page={next_page - 1}', current_url)
                elif '?' in current_url:
                    new_url = current_url + f'&page={next_page - 1}'
                else:
                    new_url = current_url + f'?page={next_page - 1}'
                await page.goto(new_url, timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)
                test_links = await page.query_selector_all("a[href*='/p/']")
                if test_links:
                    current_page = next_page
                    print(f"  URL navigation OK ({len(test_links)} products found)")
                else:
                    print(f"  URL navigation: no products, stopping")
                    break
            except Exception as e:
                print(f"  URL navigation failed: {e}")
                break

    # Uncheck sub family and return to main page
    await uncheck_sub_family(page, sub_family)
    try:
        await page.goto(BASE_URL, timeout=90000, wait_until="domcontentloaded")
    except PlaywrightTimeout:
        print("  Main page load timeout, continuing with partial load...")
    await page.wait_for_timeout(3000)
    await apply_in_stock_filter(page)

    print(f"\n  {sub_family} done: {len(all_products)} products")
    return all_products


async def async_main():
    print("=" * 60)
    print("  Extra.com AC Scraper v5 (Playwright)")
    print(f"  Sub Family sequential, Items per page: {ITEMS_PER_PAGE}")
    print("=" * 60)

    pw = browser = context = page = None
    all_products = []

    try:
        pw, browser, context, page = await setup_browser()

        print(f"\n  Loading: {BASE_URL}")
        try:
            await page.goto(BASE_URL, timeout=90000, wait_until="domcontentloaded")
        except PlaywrightTimeout:
            print("  Page load timeout, continuing with partial load...")
        await page.wait_for_timeout(5000)
        await accept_cookies(page)
        await apply_in_stock_filter(page)

        for sub_family in SUB_FAMILIES:
            products = await scrape_sub_family(page, sub_family)
            all_products.extend(products)

        # Deduplicate
        seen = set()
        unique = []
        for p in all_products:
            if p['SKU'] not in seen:
                seen.add(p['SKU'])
                unique.append(p)
        all_products = unique

        print(f"\n{'='*60}")
        print(f"  After dedup: {len(all_products)} products")
        print(f"{'='*60}")

        # Detail page scraping
        total = len(all_products)
        print(f"\n  Detail scraping... ({total} products)")
        detail_start = time.time()
        detail_success = 0
        detail_fail = 0
        for i, p in enumerate(all_products):
            if p.get('SKU'):
                detail = await scrape_detail(page, p['SKU'])
                if detail and any(v for v in detail.values()):
                    p.update({k: v for k, v in detail.items() if v})
                    detail_success += 1
                else:
                    detail_fail += 1
                if (i + 1) % 10 == 0:
                    elapsed = time.time() - detail_start
                    rate = (i + 1) / elapsed * 60
                    remaining = (total - i - 1) / (rate / 60) if rate > 0 else 0
                    print(f"   Progress: {i+1}/{total} (ok {detail_success}, fail {detail_fail}, {elapsed:.0f}s, ~{remaining:.0f}s remaining)")
                await page.wait_for_timeout(int(random.uniform(300, 800)))

        print(f"\n  Detail done: {detail_success}/{total} ok, {detail_fail} fail")

        # Category validation
        print(f"\n  Category validation...")
        corrected_count = 0
        removed_count = 0
        validated_products = []
        for p in all_products:
            pname = p.get('Product_Name', '')
            model = p.get('Model_No', '')
            brand = p.get('Brand', '')
            cat = p.get('Category', '')
            if is_non_ac_product(pname, model, brand):
                removed_count += 1
                continue
            new_cat, was_corrected, reason = validate_category(cat, pname, model)
            if was_corrected:
                corrected_count += 1
                p['Category'] = new_cat
            validated_products.append(p)
        all_products = validated_products
        print(f"  Validation done: {corrected_count} corrected, {removed_count} non-AC removed")

        # Save (cumulative append)
        if all_products:
            df_new = pd.DataFrame(all_products)
            cols = [
                'Scraped_At', 'Brand', 'Product_Name', 'Model_No', 'SKU', 'Category',
                'Cold_or_HC', 'Cooling_Capacity_Ton', 'BTU', 'Compressor_Type',
                'Standard_Price', 'Sale_Price', 'Jood_Gold_Price',
                'Discount_Amount', 'Discount_Rate',
                'Promo_Code', 'Promo_Label', 'Offer_Count', 'Gift_Count', 'Gift_Value',
                'Warranty_Period', 'Compressor_Warranty',
                'Stock_Status', 'Stock_Label', 'eXtra_Exclusive'
            ]
            df_new = df_new.reindex(columns=[c for c in cols if c in df_new.columns])

            if os.path.exists(OUTPUT_FILE):
                df_existing = pd.read_excel(OUTPUT_FILE, sheet_name='Prices DB', engine='openpyxl')
                df_all = pd.concat([df_existing, df_new], ignore_index=True)
                print(f"\n[*] Existing {len(df_existing)} + New {len(df_new)} = Total {len(df_all)}")
            else:
                df_all = df_new
                print(f"\n[*] New file: {len(df_all)} products")

            df_all.to_excel(OUTPUT_FILE, index=False, sheet_name='Prices DB', engine='openpyxl')

            print("\n" + "=" * 60)
            print(f"  Done! This run: {len(df_new)} / Cumulative: {len(df_all)}")
            print(f"  File: {OUTPUT_FILE}")
            print(f"  Timestamp: {RUN_TIMESTAMP}")
            print("=" * 60)

            print(f"\n  Brand breakdown (this run):")
            print(df_new['Brand'].value_counts().head(10).to_string())
            print(f"\n  Category breakdown (this run):")
            print(df_new['Category'].value_counts().to_string())
        else:
            print("\n  No products collected")

    except Exception as e:
        print(f"\n  Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if page:
            await page.close()
        if context:
            await context.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
