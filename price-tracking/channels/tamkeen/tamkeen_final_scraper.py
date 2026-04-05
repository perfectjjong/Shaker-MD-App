#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tamkeen Complete Scraper - v4 (2026-03-19)
주요 개선사항:
  - [v4] Firefox 브라우저 전환:
      Chromium headless의 반복 크래시(Page crashed) 문제 해결
      Firefox 미설치 시: playwright install firefox
  - [v4] 3단계 크래시 복구: page → context → browser 완전 재시작
  - [v3] GTM dataLayer view_item_list 활용:
      카테고리 페이지에서 직접 전체 상품 데이터 수집
  - [v3] 재고 수량(Stock Qty), FETCH_DELIVERY 옵션
  - 교차 카테고리 dataLayer 누적 이슈 해결

Firefox 미설치 시: playwright install firefox
"""

import sys
import io
import os
import logging

# Windows 콘솔 인코딩 UTF-8 강제 설정 (이모지/한글 출력 오류 방지)
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
import pandas as pd
import re
import time
from datetime import datetime
import traceback

# ── 에러 로그 설정 ──────────────────────────────────────────
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tamkeen_error.log")
logging.basicConfig(
    filename=_LOG_FILE,
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)s  %(message)s",
    encoding="utf-8",
)

def _log(msg: str, level: str = "info"):
    print(msg, flush=True)
    getattr(logging, level)(msg)

# ============================================================
# 설정
# ============================================================

CATEGORIES = {
    "Split AC":    "https://tamkeenstores.com.sa/en/category/split-ac",
    "Window AC":   "https://tamkeenstores.com.sa/en/category/window-ac",
    "Standing AC": "https://tamkeenstores.com.sa/en/category/standing-ac",
}

TIMESTAMP   = datetime.now().strftime('%Y%m%d_%H%M')
OUTPUT_FILE = f"Tamkeen_Complete_{TIMESTAMP}.xlsx"

# True  = 배송 예정일 수집 (개별 상품 페이지 방문, 속도 느림)
# False = 빠른 모드 (카테고리 페이지만, 약 6페이지 로드)
FETCH_DELIVERY = False

PAGE_TIMEOUT    = 30000   # 페이지 로드 타임아웃 (ms, domcontentloaded 기준)
WAIT_DL_TIMEOUT = 20000   # view_item_list 대기 최대 시간 (ms)
WAIT_FALLBACK   = 5       # dataLayer 이벤트 없을 때 추가 대기 (초)
MAX_RETRY       = 3       # 페이지별 최대 재시도 횟수

BASE_URL = "https://tamkeenstores.com.sa"

BRANDS = [
    'General Supreme', 'White-Westinghouse', 'White Westinghouse', 'Super General',
    'O General', 'OGeneral', 'Westinghouse', 'Panasonic', 'Electrolux',
    'Al Zamil', 'Zamil', 'LG', 'Samsung', 'Gree', 'Craft', 'TCL',
    'Hisense', 'Midea', 'Haier', 'Carrier', 'Daikin', 'Hitachi',
    'Toshiba', 'Sharp', 'York', 'Fujitsu', 'Aux', 'Chigo', 'Beko',
    'Tornado', 'Fisher', 'Arrow', 'Rowa', 'Glem Gas',
]

# ============================================================
# 유틸리티 함수
# ============================================================

def extract_brand(name):
    """제품명에서 브랜드 추출 (폴백용)"""
    if not name:
        return "Unknown"
    name_lower = name.lower()
    for brand in BRANDS:
        if brand.lower() in name_lower:
            return brand
    first_word = name.split()[0] if name.split() else ''
    return first_word if first_word and len(first_word) > 2 else "Unknown"

def extract_capacity(name, url=''):
    """BTU 추출 (제품명 우선, URL 폴백)"""
    if name:
        # "18,000 BTU", "18000BTU" 등
        match = re.search(r'([\d,]+)\s*BTU', name, re.IGNORECASE)
        if match:
            btu = int(match.group(1).replace(',', ''))
            if btu >= 5000:   # "51 BTU" 같은 약식 표기 제외
                return btu
        # "18,000 Cool", "18000 Split" 등 BTU 없는 경우
        match = re.search(
            r'\b(\d{1,2}[,.]?\d{3})\s*(?:Wifi|Wi-Fi|Cool|Cold|Hot|Split|Window)',
            name, re.IGNORECASE
        )
        if match:
            return int(match.group(1).replace(',', '').replace('.', ''))
    # URL에서 BTU 추출 폴백: "product-name-51000-btu"
    if url:
        url_match = re.search(r'[_\-](\d{4,6})[_\-]?btu', url, re.IGNORECASE)
        if url_match:
            btu = int(url_match.group(1))
            if 5000 <= btu <= 200000:
                return btu
    return 0

def extract_tonnage(btu):
    """BTU → 톤수 변환"""
    return round(btu / 12000, 1) if btu > 0 else 0

def get_cooling_type(name):
    """냉방 전용 / 냉난방 구분"""
    if not name:
        return "Cold Only"
    nl = name.lower()
    if ('heat' in nl or 'hot' in nl) and ('cool' in nl or 'cold' in nl):
        return "Heat & Cool"
    return "Cold Only"

def get_compressor_type(name):
    """인버터 / 일반 구분"""
    if not name:
        return "Rotary"
    return "Inverter" if 'inverter' in name.lower() else "Rotary"

def dismiss_popups(page):
    """팝업/모달 제거"""
    try:
        page.evaluate("""() => {
            document.querySelectorAll(
                '[class*="modal"], [class*="popup"], [class*="overlay"], [role="dialog"]'
            ).forEach(el => el.remove());
            document.body.style.overflow = 'auto';
        }""")
    except:
        pass

# ============================================================
# JavaScript 상수
# ============================================================

# 현재 dataLayer에서 미표시(__seen 없는) view_item_list 이벤트의 아이템 추출
# 없으면 마지막 이벤트로 폴백
EXTRACT_LAST_EVENT_JS = """() => {
    const dl = window.dataLayer || [];
    const targetEvent =
        [...dl].reverse().find(e => e.event === 'view_item_list' && !e.__seen) ||
        [...dl].reverse().find(e => e.event === 'view_item_list');
    if (!targetEvent) return [];
    return (targetEvent.ecommerce?.items || []).map(item => ({
        sku:          item.item_id          || '',
        name:         item.item_name        || '',
        brand:        item.item_brand       || '',
        price:        item.price            || 0,
        shelfPrice:   item.shelf_price      || 0,
        discount:     item.discount         || 0,
        quantity:     (item.quantity != null) ? item.quantity : null,
        inStock:      (item.item_availability || '').toLowerCase() !== 'out of stock',
        availability: item.item_availability || '',
        imageUrl:     item.item_image_link  || '',
        link:         item.item_link        || item.url || '',
        category2:    item.item_category2   || '',
    }));
}"""

# 개별 상품 페이지에서 배송 예정일 추출 (FETCH_DELIVERY=True 시 사용)
DELIVERY_JS = r"""() => {
    const bodyText = document.body.textContent || '';
    const expressDelivery = /24 to 48 hours/i.test(bodyText);
    const delivMatch = bodyText.match(
        /Expected[:\s]*([A-Z][a-z]+ (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},?\s*\d{4})/
    );
    return {
        expressDelivery:  expressDelivery,
        expectedDelivery: delivMatch ? delivMatch[1].trim() : '',
    };
}"""

# ============================================================
# 카테고리 페이지 데이터 수집
# ============================================================

def get_max_page(page):
    """페이지네이션에서 최대 페이지 번호 확인"""
    try:
        buttons = page.evaluate("""() => {
            const nums = [];
            document.querySelectorAll('button').forEach(b => {
                const t = b.textContent.trim();
                if (/^[0-9]+$/.test(t)) nums.push(parseInt(t));
            });
            return nums;
        }""")
        return max(buttons) if buttons else 1
    except:
        return 1

class PageCrashedError(Exception):
    """페이지 크래시 발생 시 상위로 전파하기 위한 예외."""
    pass


def collect_page_items(page, url, page_num):
    """
    카테고리 페이지 한 장에서 아이템 수집.

    이동 전 기존 view_item_list 이벤트에 __seen 마크를 붙여두고,
    이동 후 새로운(미표시) 이벤트가 push될 때까지 대기.
    → Next.js 풀 리로드(dataLayer 리셋)와 SPA 네비게이션(dataLayer 누적) 모두 대응.

    크래시/닫힘 등 복구 불가 에러는 PageCrashedError로 상위 전파.
    """
    print(f"  📄 페이지 {page_num}... ", end="", flush=True)

    # 이동 전: 현재 dataLayer의 view_item_list 이벤트를 __seen으로 표시
    try:
        page.evaluate("""() => {
            (window.dataLayer || []).forEach(e => {
                if (e.event === 'view_item_list') e.__seen = true;
            });
        }""")
    except:
        pass

    # 페이지 이동
    # domcontentloaded를 1순위로 사용 (networkidle은 무한 대기 위험)
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
    except Exception as first_err:
        err_str = str(first_err).lower()
        if 'crash' in err_str or 'closed' in err_str:
            logging.error(f"페이지 크래시 [{url}]: {first_err}")
            print(f"💥 크래시 발생")
            raise PageCrashedError(str(first_err)) from first_err
        logging.error(f"페이지 로드 실패 [{url}]: {first_err}\n{traceback.format_exc()}")
        print(f"❌ 로드 실패: {str(first_err)[:50]}")
        return []

    # 새(미표시) view_item_list 이벤트가 push될 때까지 대기
    try:
        page.wait_for_function(
            """() => (window.dataLayer || []).some(
                e => e.event === 'view_item_list' && !e.__seen
            )""",
            timeout=WAIT_DL_TIMEOUT,
        )
    except Exception as e:
        err_str = str(e).lower()
        if 'crash' in err_str or 'closed' in err_str:
            logging.error(f"대기 중 크래시 [{url}]: {e}")
            print(f"💥 크래시 발생")
            raise PageCrashedError(str(e)) from e
        logging.warning(f"view_item_list 이벤트 대기 실패 [{url}]: {e}")
        print(f"⚠️  이벤트 없음, 추가 대기... ", end="", flush=True)
        time.sleep(WAIT_FALLBACK)

    dismiss_popups(page)

    try:
        items = page.evaluate(EXTRACT_LAST_EVENT_JS)
    except Exception as e:
        err_str = str(e).lower()
        if 'crash' in err_str or 'closed' in err_str:
            logging.error(f"데이터 추출 중 크래시 [{url}]: {e}")
            print(f"💥 크래시 발생")
            raise PageCrashedError(str(e)) from e
        logging.error(f"데이터 추출 실패 [{url}]: {e}\n{traceback.format_exc()}")
        print(f"❌ 데이터 추출 실패: {str(e)[:40]}")
        return []

    print(f"✅ {len(items)}개")
    return items


def is_page_alive(page):
    """페이지가 아직 살아있는지 확인"""
    try:
        page.evaluate('1')
        return True
    except Exception:
        return False


# ── 브라우저 엔진 설정 ────────────────────────────────────────
# Chromium headless가 Tamkeen 사이트에서 반복 크래시 → Firefox 사용
# Firefox는 메모리 관리가 안정적이고 Page crashed 이슈 없음
BROWSER_ENGINE = "firefox"   # "chromium" 또는 "firefox"

CHROMIUM_ARGS = [
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--no-sandbox',
    '--disable-setuid-sandbox',
]


def launch_browser(playwright_instance):
    """브라우저 시작. Firefox 우선, 실패 시 Chromium 폴백."""
    if BROWSER_ENGINE == "firefox":
        try:
            browser = playwright_instance.firefox.launch(headless=True)
            _log("  🦊 Firefox 브라우저 시작", "info")
            return browser
        except Exception as e:
            _log(f"  ⚠️ Firefox 시작 실패 ({e}), Chromium으로 폴백", "warning")

    browser = playwright_instance.chromium.launch(
        headless=True,
        args=CHROMIUM_ARGS,
    )
    _log("  🌐 Chromium 브라우저 시작", "info")
    return browser


def create_context_and_page(browser):
    """브라우저 context + page 생성."""
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    )
    page = context.new_page()
    return context, page


def is_browser_alive(browser):
    """브라우저가 살아있는지 확인."""
    try:
        browser.contexts  # 속성 접근만으로 확인
        return True
    except Exception:
        return False


def safe_recover(page, context, browser, pw):
    """
    3단계 크래시 복구: page → context → browser 순.
    browser까지 죽었으면 완전 재시작.
    Returns: (page, context, browser)
    """
    # 1차: 기존 context에서 새 페이지 생성
    try:
        page.close()
    except Exception:
        pass

    try:
        new_page = context.new_page()
        new_page.evaluate('1')
        _log("  ✅ 페이지 복구 성공 (context 재사용)", "info")
        return new_page, context, browser
    except Exception:
        pass

    # 2차: context 재생성
    _log("  🔄 Context 불안정 → context 재생성 시도", "warning")
    try:
        context.close()
    except Exception:
        pass

    try:
        context, new_page = create_context_and_page(browser)
        new_page.evaluate('1')
        _log("  ✅ Context 재생성 성공", "info")
        return new_page, context, browser
    except Exception:
        pass

    # 3차: browser 자체가 죽음 → 완전 재시작
    _log("  🚨 Browser 죽음 → 브라우저 완전 재시작", "error")
    try:
        browser.close()
    except Exception:
        pass

    browser = launch_browser(pw)
    context, new_page = create_context_and_page(browser)
    _log("  ✅ Browser 재시작 성공", "info")
    return new_page, context, browser


def collect_page_with_retry(page, context, browser, pw, url, page_num, max_retry=MAX_RETRY):
    """
    단일 페이지 수집 + 크래시 시 재시도 (최대 max_retry회).
    browser까지 변경될 수 있으므로 (page, context, browser, items) 반환.
    """
    for attempt in range(1, max_retry + 1):
        # 페이지가 살아있는지 먼저 확인
        if not is_page_alive(page):
            _log(f"  ⚠️  페이지 크래시 감지 → 복구 시도 ({attempt}/{max_retry})", "warning")
            page, context, browser = safe_recover(page, context, browser, pw)
            time.sleep(2)

        try:
            items = collect_page_items(page, url, page_num)
            return page, context, browser, items

        except PageCrashedError as e:
            _log(f"  💥 크래시 감지 (시도 {attempt}/{max_retry}): {str(e)[:60]}", "error")
            page, context, browser = safe_recover(page, context, browser, pw)
            time.sleep(2)
            if attempt < max_retry:
                _log(f"  🔁 재시도 {attempt + 1}/{max_retry}...", "warning")
            continue

        except Exception as e:
            logging.error(f"collect_page_items 예외 [{url}] (시도 {attempt}): {e}")
            if not is_page_alive(page):
                page, context, browser = safe_recover(page, context, browser, pw)
                time.sleep(2)
            if attempt < max_retry:
                _log(f"  🔁 재시도 {attempt + 1}/{max_retry}...", "warning")
            continue

    _log(f"  ❌ {max_retry}회 시도 후 포기: {url}", "error")
    return page, context, browser, []


def collect_all_category_data(page, context, browser, pw):
    """
    모든 카테고리의 모든 페이지에서 데이터 수집.
    Page/Context/Browser 크래시 모두 자동 복구.
    """
    all_items_by_cat = {}

    for cat_name, cat_url in CATEGORIES.items():
        print(f"\n{'='*60}")
        print(f"📂 {cat_name}")
        print(f"   {cat_url}")
        print('='*60)

        cat_items = []

        # 첫 번째 페이지 (재시도 포함)
        page, context, browser, items = collect_page_with_retry(
            page, context, browser, pw, cat_url, 1
        )
        cat_items.extend(items)

        # 최대 페이지 확인 (첫 페이지 로드 후)
        max_page = get_max_page(page) if is_page_alive(page) else 1
        if max_page > 1:
            print(f"  → 총 {max_page}페이지 감지")

        # 2페이지 이상
        for pnum in range(2, max_page + 1):
            page_url = f"{cat_url}?page={pnum}"
            page, context, browser, items = collect_page_with_retry(
                page, context, browser, pw, page_url, pnum
            )

            # 이미 수집된 SKU는 제외 (중복 방지)
            existing_skus = {it['sku'] for it in cat_items if it['sku']}
            new_items = [it for it in items if it['sku'] not in existing_skus]
            cat_items.extend(new_items)
            if len(new_items) < len(items):
                print(f"    ℹ️  중복 {len(items) - len(new_items)}개 제외, 신규 {len(new_items)}개")

        all_items_by_cat[cat_name] = cat_items

        # 카테고리별 중간저장 (크래시로 나중 카테고리 실패해도 지금까지 데이터 보존)
        try:
            partial_records = []
            idx = 1
            for cn, its in all_items_by_cat.items():
                for it in its:
                    lnk = it.get('link', '') or ''
                    pu = (BASE_URL + lnk) if lnk and not lnk.startswith('http') else lnk
                    partial_records.append(build_product(it, cn, idx))
                    idx += 1
            if partial_records:
                partial_df = pd.DataFrame(partial_records).fillna('')
                partial_path = OUTPUT_FILE.replace('.xlsx', '_partial.xlsx')
                partial_df.to_excel(partial_path, sheet_name='All Products', index=False, engine='openpyxl')
                logging.info(f"중간저장: {len(partial_records)}개 → {os.path.basename(partial_path)}")
        except Exception:
            pass

        print(f"  ✅ {cat_name} 수집 완료: {len(cat_items)}개")

    return all_items_by_cat

# ============================================================
# 배송 예정일 수집 (선택적 Phase 2)
# ============================================================

def fetch_delivery_info(page, url):
    """
    개별 상품 페이지에서 배송 예정일만 수집.
    FETCH_DELIVERY=True 시 사용.
    """
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        # view_item 이벤트 대기 (React 하이드레이션 완료 신호)
        try:
            page.wait_for_function(
                """() => {
                    const path = window.location.pathname;
                    return (window.dataLayer || []).some(e => {
                        if (e.event !== 'view_item') return false;
                        const link = e.ecommerce?.items?.[0]?.item_link || '';
                        return !link || link.includes(path);
                    });
                }""",
                timeout=12000,
            )
        except:
            try:
                page.wait_for_selector('span.first_span', timeout=8000)
            except:
                time.sleep(2)
        return page.evaluate(DELIVERY_JS)
    except Exception:
        return {'expressDelivery': False, 'expectedDelivery': ''}

# ============================================================
# 데이터 변환
# ============================================================

def build_product(item, cat_name, index, delivery_info=None):
    """dataLayer view_item_list 아이템 → 최종 제품 딕셔너리"""
    name      = item.get('name', '')      or ''
    brand     = item.get('brand', '')     or extract_brand(name)
    sku       = item.get('sku', '')       or ''
    sale_p    = item.get('price', 0)      or 0
    orig_p    = item.get('shelfPrice', 0) or 0
    disc_amt  = item.get('discount', 0)   or 0
    in_stock  = item.get('inStock', True)
    stock_qty = item.get('quantity')          # None = Express 재고 없음
    image_url = item.get('imageUrl', '')  or ''

    # 상품 URL (상대경로 → 절대경로)
    link = item.get('link', '') or ''
    if link and not link.startswith('http'):
        product_url = BASE_URL + link
    else:
        product_url = link

    btu = extract_capacity(name, product_url)

    # 할인율 계산
    if orig_p > 0 and disc_amt > 0:
        disc_pct = round((disc_amt / orig_p) * 100, 1)
    elif orig_p > 0 and sale_p > 0 and orig_p > sale_p:
        disc_amt = orig_p - sale_p
        disc_pct = round((disc_amt / orig_p) * 100, 1)
    else:
        disc_pct = 0

    # Express Delivery:
    #   view_item_list에는 "24 to 48 hours" 텍스트가 없으므로
    #   quantity > 0 이면 Express 재고 있음 = Express Delivery 가능
    if delivery_info:
        express           = delivery_info.get('expressDelivery', False)
        expected_delivery = delivery_info.get('expectedDelivery', '') or ''
    else:
        express           = (stock_qty is not None and stock_qty > 0)
        expected_delivery = ''

    return {
        'No':                  index,
        'Name':                name,
        'SKU':                 sku,
        'Brand':               brand,
        'Category':            cat_name,
        'Cooling Type':        get_cooling_type(name),
        'Compressor':          get_compressor_type(name),
        'Capacity (BTU)':      btu,
        'Tonnage':             extract_tonnage(btu),
        'Original Price (SR)': orig_p,
        'Sale Price (SR)':     sale_p,
        'Discount (SR)':       disc_amt,
        'Discount (%)':        f"{disc_pct}%",
        'In Stock':            'Yes' if in_stock else 'No',
        'Stock Qty':           stock_qty,
        'Express Delivery':    'Yes' if express else 'No',
        'Expected Delivery':   expected_delivery,
        'Image URL':           image_url,
        'Product URL':         product_url,
    }

# ============================================================
# 저장 함수
# ============================================================

def save_to_excel(df, filename):
    """Excel 저장 (시트: All Products / 카테고리별 / Brand Summary)"""
    try:
        df = df.fillna('')
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='All Products', index=False)

            for cat_name in CATEGORIES:
                cat_df = df[df['Category'] == cat_name]
                if len(cat_df) > 0:
                    sheet_name = cat_name.replace(' ', '_')[:31]
                    cat_df.to_excel(writer, sheet_name=sheet_name, index=False)

            if len(df) > 0:
                brand_summary = df.groupby('Brand').agg(
                    Count=('No', 'count'),
                    Min_Price=('Sale Price (SR)', 'min'),
                    Max_Price=('Sale Price (SR)', 'max'),
                    Avg_Price=('Sale Price (SR)', 'mean'),
                ).round(0).sort_values('Count', ascending=False)
                brand_summary.to_excel(writer, sheet_name='Brand Summary')

        return True
    except Exception as e:
        print(f"  ❌ Excel 저장 오류: {e}")
        traceback.print_exc()
        return False

def save_to_csv(df, filename):
    """CSV 저장 (백업)"""
    try:
        df.fillna('').to_csv(filename, index=False, encoding='utf-8-sig')
        return True
    except Exception as e:
        print(f"  ❌ CSV 저장 오류: {e}")
        return False

# ============================================================
# 메인
# ============================================================

def main():
    print("\n" + "="*70)
    print("🚀 Tamkeen Complete Scraper - v3")
    print(f"   시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    mode_str = "배송예정일 포함 모드 (Phase 1 + 2)" if FETCH_DELIVERY else "빠른 모드 (카테고리 페이지만)"
    print(f"   모드: {mode_str}")
    print("="*70)

    all_products     = []
    delivery_cache   = {}   # {product_url: {expressDelivery, expectedDelivery}}
    all_items_by_cat = {}   # try 블록 밖에서도 참조 가능하도록 미리 초기화

    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            context, page = create_context_and_page(browser)

            # ── PHASE 1: 카테고리 페이지 → view_item_list 수집 ──
            print("\n" + "="*70)
            print("📋 PHASE 1: 카테고리 페이지에서 전체 데이터 수집")
            print("   (GTM dataLayer view_item_list 이벤트 활용)")
            print("="*70)

            all_items_by_cat = collect_all_category_data(page, context, browser, p)

            total = sum(len(v) for v in all_items_by_cat.values())
            print(f"\n✅ PHASE 1 완료: 총 {total}개 상품 데이터 수집")
            for cat, items in all_items_by_cat.items():
                print(f"  • {cat}: {len(items)}개")

            # ── PHASE 2: 배송 예정일 수집 (선택적) ──────────────
            if FETCH_DELIVERY:
                print("\n" + "="*70)
                print("🚚 PHASE 2: 배송 예정일 수집 (개별 상품 페이지 방문)")
                print("="*70)

                for cat_name, items in all_items_by_cat.items():
                    print(f"\n📂 {cat_name} ({len(items)}개)")
                    for i, item in enumerate(items, 1):
                        link = item.get('link', '') or ''
                        url  = (BASE_URL + link) if link and not link.startswith('http') else link
                        if not url:
                            continue
                        print(f"  [{i:>3}/{len(items)}] ", end="", flush=True)
                        info = fetch_delivery_info(page, url)
                        delivery_cache[url] = info
                        ed = info.get('expectedDelivery', '') or '미확인'
                        print(f"✅ {item.get('name','')[:40]}  →  {ed}")
                        time.sleep(0.3)

            try:
                browser.close()
            except Exception:
                pass

    except Exception as e:
        logging.critical(f"스크래핑 오류: {e}\n{traceback.format_exc()}")
        print(f"\n❌ 스크래핑 오류: {e}")
        traceback.print_exc()

    # ── 제품 딕셔너리 구성 ─────────────────────────────────────
    global_index = 1
    for cat_name, items in all_items_by_cat.items():
        for item in items:
            link = item.get('link', '') or ''
            url  = (BASE_URL + link) if link and not link.startswith('http') else link
            d_info = delivery_cache.get(url) if FETCH_DELIVERY else None
            product = build_product(item, cat_name, global_index, d_info)
            all_products.append(product)
            global_index += 1

    # ── 저장 ──────────────────────────────────────────────────
    if not all_products:
        msg = "수집된 제품이 없습니다."
        print(f"\n❌ {msg}")
        # 카테고리별 수집 현황을 로그에 기록
        for cat_name, items in all_items_by_cat.items():
            _log(f"  {cat_name}: {len(items)}개 수집", "error")
        _log(f"all_items_by_cat keys: {list(all_items_by_cat.keys())}", "error")
        _log(msg, "critical")
        return

    print(f"\n{'='*70}")
    print("💾 저장 중...")
    print('='*70)

    df = pd.DataFrame(all_products)

    print(f"  📊 Excel 저장 중... ", end="", flush=True)
    if save_to_excel(df, OUTPUT_FILE):
        print(f"✅  {OUTPUT_FILE}")
    else:
        csv_file = f"Tamkeen_Complete_{TIMESTAMP}.csv"
        print(f"  📊 CSV 대체 저장... ", end="", flush=True)
        if save_to_csv(df, csv_file):
            print(f"✅  {csv_file}")

    backup_csv = f"Tamkeen_Backup_{TIMESTAMP}.csv"
    print(f"  💾 CSV 백업 중... ", end="", flush=True)
    if save_to_csv(df, backup_csv):
        print(f"✅  {backup_csv}")

    # ── 결과 요약 ─────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"📊 스크래핑 결과 요약")
    print('='*70)
    print(f"\n총 제품 수: {len(df)}개")

    print(f"\n📦 카테고리별:")
    for cat_name in CATEGORIES:
        count = len(df[df['Category'] == cat_name])
        print(f"  • {cat_name}: {count}개")

    print(f"\n🏷️  브랜드별:")
    for brand, count in df['Brand'].value_counts().items():
        print(f"  • {brand}: {count}개")

    # 재고 수량 통계
    stock_series = pd.to_numeric(df['Stock Qty'], errors='coerce')
    has_stock    = stock_series.notna()
    if has_stock.any():
        print(f"\n📦 Express 재고 현황:")
        print(f"  • 재고 있는 제품: {has_stock.sum()}개 / {len(df)}개")
        low_stock = df[has_stock & (stock_series < 5)]
        if len(low_stock) > 0:
            print(f"  ⚠️  재고 5개 미만 제품:")
            for _, row in low_stock.iterrows():
                qty = int(stock_series.loc[row.name])
                print(f"     [{qty}개] {row['Name'][:55]}")
    else:
        print(f"\n⚠️  재고 수량 데이터 없음 (view_item_list 이벤트 미수집)")

    sale_prices = pd.to_numeric(df['Sale Price (SR)'], errors='coerce')
    if sale_prices.max() > 0:
        print(f"\n💰 가격 범위: {sale_prices.min():,.0f} ~ {sale_prices.max():,.0f} SR")

    out_of_stock = len(df[df['In Stock'] == 'No'])
    if out_of_stock > 0:
        print(f"\n🔴 품절 제품: {out_of_stock}개")

    print(f"\n완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        msg = traceback.format_exc()
        logging.critical("UNHANDLED EXCEPTION:\n" + msg)
        print("\n❌ 치명적 오류 발생. tamkeen_error.log 파일을 확인하세요.")
        print(msg)
