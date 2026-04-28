#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binmomen Air Conditioner Scraper  v3
────────────────────────────────────────────────────────────────
 핵심 원칙
  1. 메인 AC 카테고리 페이지를 페이지네이션으로 전수 수집
     → 카테고리 필터 클릭 없이 모델 누락 방지
  2. 카테고리는 ① listing 페이지 CSS 클래스 ② 제품명/URL 키워드 순으로 결정
  3. BTU/Tonnage는 ① 상세설명 ② 제품명에서 추출
  4. Brand/Warranty는 ① 속성 테이블 ② 제품명에서 추출
  5. 실행 시마다 데이터를 기존 Excel에 append (대시보드용 누적)
────────────────────────────────────────────────────────────────
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
import time
from urllib.parse import urljoin, unquote
import os
import sys
import io
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows console UTF-8 fix (emoji + Arabic in print)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── CONFIG ──────────────────────────────────────────────────────────────────────
BASE_URL    = "https://binmomen.com.sa"
AC_CATEGORY = "/product-category/air-conditioning-devices/"
OUTPUT_FILE = "Binmomen_AC_Data.xlsx"   # cumulative file (append each run)
DELAY       = 0.5                        # seconds between requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.9",
}

# ── CATEGORY MAPS ──────────────────────────────────────────────────────────────
# CSS slug  →  English category
CAT_SLUG_TO_EN = {
    "split-air-conditioners":    "Split AC",
    "window-air-conditioners":   "Window AC",
    "cupboard-air-conditioners": "Floor Standing AC",
}

# Arabic keyword (in title/URL) → English category
CAT_KEYWORD_TO_EN = {
    # Window
    "شباك":   "Window AC",
    "window":  "Window AC",
    # Floor Standing
    "دولابي":  "Floor Standing AC",
    "دولاب":   "Floor Standing AC",
    "خزانة":   "Floor Standing AC",
    "cupboard":"Floor Standing AC",
    "floor":   "Floor Standing AC",
    "standing":"Floor Standing AC",
    # Split  (check after window/floor)
    "سبليت":   "Split AC",
    "إسبليت":  "Split AC",
    "اسبليت":  "Split AC",
    "جداري":   "Split AC",
    "split":   "Split AC",
    "wall":    "Split AC",
}

# Slugs/keywords that mean EXCLUDE
EXCLUDE_KEYWORDS = {
    "desert-coolers", "صحراوي", "صحراوية",
    "صحرواي", "صحروا",         # alternate spellings of desert
    "fans-and-air-coolers", "مروحة", "مبرد",
    "متنقل", "فريون",          # portable coolers
    "fan", "cooler",
}

# Arabic breadcrumb  →  English category (fallback)
BREADCRUMB_TO_EN = {
    "مكيفات سبليت":             "Split AC",
    "مكيفات شباك":              "Window AC",
    "مكيفات دولابي":            "Floor Standing AC",
    "مكيفات صحراوية":           "EXCLUDE",
    "المراوح ومبردات الهواء":   "EXCLUDE",
}

# ── BRAND MAPS ─────────────────────────────────────────────────────────────────
BRANDS_AR = {
    "ال جي":         "LG",
    "إل جي":         "LG",
    "lg":            "LG",
    "سامسونج":       "Samsung",
    "samsung":       "Samsung",
    "جري":           "Gree",
    "جرى":           "Gree",
    "gree":          "Gree",
    "ميديا":         "Midea",
    "midea":         "Midea",
    "هاير":          "Haier",
    "haier":         "Haier",
    "كاريير":        "Carrier",
    "كارير":         "Carrier",
    "carrier":       "Carrier",
    "تي سي ال":     "TCL",
    "tcl":           "TCL",
    "هايسنس":        "Hisense",
    "hisense":       "Hisense",
    "سوبر جنرال":   "Super General",
    "جنرال":         "General",
    "general":       "General",
    "ستار فيجن":    "Star Vision",
    "starvision":    "Star Vision",
    "سمارت الكتريك":  "Smart Electric",
    "سمارت اليكتريك": "Smart Electric",
    "smartelcrtric":  "Smart Electric",
    "smartelectric":  "Smart Electric",
    "سمارت":          "Smart",
    "smart":          "Smart",
    "كرافت":         "Crafft",
    "crafft":        "Crafft",
    "دانسات":        "Dansat",
    "dansat":        "Dansat",
    "اوكس":          "AUX",
    "aux":           "AUX",
    "يورك":          "York",
    "york":          "York",
    "دايكن":         "Daikin",
    "daikin":        "Daikin",
    "توشيبا":        "Toshiba",
    "toshiba":       "Toshiba",
    "شارب":          "Sharp",
    "sharp":         "Sharp",
    "باناسونيك":     "Panasonic",
    "panasonic":     "Panasonic",
    "وستنغهاوس":     "Westinghouse",
    "westinghouse":  "Westinghouse",
    "يونيكس":        "UNIX",
    "unix":          "UNIX",
    "الزامل":        "Zamil",
    "زاميل":         "Zamil",
    "zamil":         "Zamil",
    "كيلون":         "Kelon",
    "kelon":         "Kelon",
    "رووا":          "ROWA",
    "رواء":          "ROWA",
    "rowa":          "ROWA",
    "رود":           "RUUD",
    "ruud":          "RUUD",
    "ستار فجن":      "Star Vision",
    "ستار فيجن":     "Star Vision",
    "black+decker":  "Black+Decker",
    "tornado":       "Tornado",
    "wansa":         "Wansa",
    "fisher":        "Fisher",
    "يونكس":         "UNIX",
    "يونيكس":        "UNIX",
}

BRANDS_EN = sorted(
    ["LG","Samsung","Gree","Midea","Haier","Carrier","TCL","Hisense",
     "Super General","General","Star Vision","Smart Electric","Smart",
     "Crafft","Dansat","AUX","York","Daikin","Toshiba","Sharp","Panasonic",
     "Black+Decker","Electro General","Wansa","Tornado","Fisher",
     "Westinghouse","UNIX","Zamil","ROWA","RUUD"],
    key=len, reverse=True   # longest first to avoid partial matches
)

# ── ARABIC→ENGLISH WORD REPLACEMENTS (for product name translation) ────────────
AR_EN_WORDS = {
    # AC type (longest first to avoid partial match)
    "سمارت اليكتريك": "Smart Electric",
    "سمارت الكتريك":  "Smart Electric",
    "سوبر جنرال":     "Super General",
    "ستار فيجن":      "Star Vision",
    "تي سي ال":       "TCL",
    "ال جي":          "LG",
    "إل جي":          "LG",
    "الجي":           "LG",
    "جيت كول":        "Jet Cool",
    "جت كول":         "Jet Cool",
    "ريش مزدوجة":     "Dual Vane",
    "دولابي":         "Floor Standing",
    "انفيرتر":        "Inverter",
    "انفرتر":         "Inverter",
    "إنفرتر":         "Inverter",
    "إسبليت":         "Split",
    "اسبليت":         "Split",
    "اسلبيت":         "Split",   # common misspelling variant
    "سبليت":          "Split",
    "مكيف":           "AC",
    "مكيفات":         "ACs",
    "شباك":           "Window",
    "جداري":          "Wall",
    "تدفئة":          "Heating",
    "تبريد":          "Cooling",
    "بارد":           "Cold",
    "ح / ب":          "H&C",    # حار/بارد shorthand
    "ح/ب":            "H&C",
    "ساخن":           "Hot",
    "حار":            "Hot",
    "فقط":            "Only",
    "وحدة":           "BTU",
    "طن":             "Ton",
    "فريش":           "Fresh",
    "الترا":          "Ultra",
    "سمارت":          "Smart",
    "جنرال":          "General",
    "هاير":           "Haier",
    "جري":            "Gree",
    "جرى":            "Gree",
    "ميديا":          "Midea",
    "شارب":           "Sharp",
    "أبيض":           "White",
    "ابيض":           "White",
    "أسود":           "Black",
    "ذهبي":           "Gold",
    "جديد":           "New",
    "الجديد":         "New",
    "سعة":            "",
    "و":              "&",
}


# ── UTILITIES ──────────────────────────────────────────────────────────────────
def get_soup(url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = "utf-8"
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"    ⚠️  [{attempt}/{retries}] {e}")
            if attempt < retries:
                time.sleep(3)
    return None


def translate_name(ar_name):
    """Word-level Arabic→English for product name (longest match first)."""
    result = ar_name
    for ar, en in sorted(AR_EN_WORDS.items(), key=lambda x: len(x[0]), reverse=True):
        result = result.replace(ar, en)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def extract_brand(text, attrs_brand=None):
    """Brand from: attributes table → Arabic map → English brand list."""
    if attrs_brand:
        # clean up attrs brand (might already be English)
        ab = attrs_brand.strip()
        for en in BRANDS_EN:
            if en.lower() == ab.lower():
                return en
        # Try Arabic map
        for ar, en in BRANDS_AR.items():
            if ar == ab.lower():
                return en
        return ab  # return as-is if not matched

    text_l = text.lower()
    # Longest-first matching to avoid "General" matching "Super General"
    for ar in sorted(BRANDS_AR.keys(), key=len, reverse=True):
        if ar in text or ar in text_l:
            return BRANDS_AR[ar]
    for brand in BRANDS_EN:
        if brand.lower() in text_l:
            return brand
    return None


def extract_btu(text):
    """
    Extract BTU value from combined name + description text.
    Priority: explicit large number → 'سعة X وحدة' → short number * 1000
    """
    # 1. Explicit 'سعة 18000 وحدة' in description
    m = re.search(r"سعة\s+(\d{4,6})\s+وحدة", text)
    if m:
        return int(m.group(1))
    # 2. Any number + BTU/وحدة marker
    m = re.search(r"(\d{4,6})\s*(?:BTU|وحدة|btu)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # 3. Common BTU values (use (?<!\d) / (?!\d) instead of \b for Arabic text)
    m = re.search(
        r"(?<!\d)(9000|10000|12000|18000|18400|21000|24000|27000|30000|36000|48000|60000)(?!\d)",
        text,
    )
    if m:
        return int(m.group(1))
    # 4. Any 4-5 digit number in realistic AC BTU range (8000–65000)
    for m in re.finditer(r"(?<!\d)(\d{4,5})(?!\d)", text):
        v = int(m.group(1))
        if 8000 <= v <= 65000:
            return v
    # 5. Tonnage phrase: "X طن" → X * 12000
    m = re.search(r"(?<!\d)([1-9]\.?[05]?)\s*طن", text)
    if m:
        try:
            return int(float(m.group(1)) * 12000)
        except ValueError:
            pass
    # 6. Short numbers in product name: "18 سبليت" → 18000
    m = re.search(r"(?<!\d)(9|10|12|18|21|24|25|27|30|36|48|55|60)(?!\d)", text)
    if m:
        return int(m.group(1)) * 1000
    return None


BTU_TO_TON_TABLE = [
    ( 9000, 15000, 1.0),
    (15000, 21000, 1.5),
    (21000, 27000, 2.0),
    (27000, 33000, 2.5),
    (33000, 39000, 3.0),
    (39000, 45000, 3.5),
    (45000, 51000, 4.0),
    (51000, 57000, 4.5),
    (57000, 63000, 5.0),
]


def btu_to_ton(btu):
    """BTU 범위 기반 톤수 룩업."""
    if not btu:
        return None
    for lo, hi, ton in BTU_TO_TON_TABLE:
        if lo <= btu < hi:
            return ton
    return None


def get_cooling_type(text):
    t = text.lower()
    if any(w in text for w in ["تبريد وتدفئة", "ساخن", "حار"]) or any(
        w in t for w in ["hot", "heat", "heating"]
    ):
        return "Hot & Cold"
    return "Cold Only"


def get_inverter(text):
    return (
        "Yes"
        if re.search(r"انفرتر|إنفرتر|انفيرتر|inverter", text, re.IGNORECASE)
        else "No"
    )


def get_compressor(desc_text):
    if "دوار" in desc_text:
        return "Rotary"
    if re.search(r"انفرتر|إنفرتر|inverter", desc_text, re.IGNORECASE):
        return "Inverter"
    return "Rotary"


def parse_warranty(raw):
    if not raw:
        return None
    t = raw.strip()
    # Already in English
    m = re.search(r"(\d+)\s*[Yy]ear", t)
    if m:
        n = int(m.group(1))
        return f"{n} Year{'s' if n > 1 else ''}"
    # Arabic dual/plural forms
    if "سنتان" in t or "سنتين" in t:
        return "2 Years"
    if re.search(r"سنوات|سنتان|سنتين", t):
        m2 = re.search(r"(\d+)", t)
        if m2:
            n = int(m2.group(1))
            return f"{n} Years"
        return "3 Years"
    if re.search(r"سنة|year", t, re.I):
        return "1 Year"
    m = re.search(r"(\d+)", t)
    if m:
        n = int(m.group(1))
        return f"{n} Year{'s' if n > 1 else ''}"
    return t


def extract_price(price_el):
    """Returns (original_price, sale_price) as int or None."""
    if not price_el:
        return None, None

    def to_int(el):
        if not el:
            return None
        txt = el.get_text().replace(",", "")
        nums = re.findall(r"\d+\.?\d*", txt)
        return int(float(nums[0])) if nums else None

    del_el = price_el.select_one("del .woocommerce-Price-amount")
    ins_el = price_el.select_one("ins .woocommerce-Price-amount")
    cur_el = price_el.select_one(".woocommerce-Price-amount")

    if del_el and ins_el:
        return to_int(del_el), to_int(ins_el)
    v = to_int(cur_el)
    return v, v


def discount_pct(orig, sale):
    if orig and sale and orig > sale:
        return f"{round((1 - sale / orig) * 100)}%"
    return "0%"


# ── CATEGORY DETECTION ─────────────────────────────────────────────────────────
def should_exclude(text):
    tl = text.lower()
    return any(kw in text or kw in tl for kw in EXCLUDE_KEYWORDS)


def category_from_classes(class_str):
    """Detect category from .wd-product CSS classes."""
    for slug, en in CAT_SLUG_TO_EN.items():
        if slug in class_str:
            return en
    return None


def category_from_text(text):
    """
    Detect category from product name or decoded URL slug.
    Uses keyword priority: window/floor before split.
    """
    tl = text.lower()
    for kw, en in CAT_KEYWORD_TO_EN.items():
        if kw in text or kw in tl:
            return en
    return None


def category_from_breadcrumb(soup):
    bc = soup.select_one(".woocommerce-breadcrumb, .breadcrumbs")
    if not bc:
        return None
    bc_text = bc.get_text(" ", strip=True)
    for ar, en in BREADCRUMB_TO_EN.items():
        if ar in bc_text:
            return en
    return None


# ── LISTING PAGE: collect all product refs ─────────────────────────────────────
def get_all_product_refs(base_cat_url):
    """
    Iterate all pagination pages and collect:
      {url, category_hint}  for every AC product (non-excluded).
    """
    refs = []
    seen = set()
    page = 1

    while True:
        url = base_cat_url if page == 1 else f"{base_cat_url}page/{page}/"
        print(f"  📄 Listing p.{page:02d} → {url}")
        soup = get_soup(url)
        if not soup:
            print("    ❌ Failed – stopping pagination.")
            break

        rc = soup.select_one(".woocommerce-result-count")
        if rc:
            print(f"    ℹ️  {rc.get_text(strip=True)}")

        product_divs = soup.select("div.wd-product")
        if not product_divs:
            print("    ⚠️  No .wd-product divs – stopping.")
            break

        added = 0
        for div in product_divs:
            class_str = " ".join(div.get("class", []))

            # --- Category hint from listing-page CSS class ---
            cat_hint = category_from_classes(class_str)

            # --- Check exclusion via CSS class ---
            if should_exclude(class_str):
                continue

            # --- Product URL ---
            a_tag = div.select_one("a.product-image-link, a[href*='/product/']")
            if not a_tag:
                continue
            href = a_tag.get("href", "").strip()
            if not href or href in seen:
                continue
            seen.add(href)

            # --- Exclude check via URL slug ---
            url_decoded = unquote(href)
            if should_exclude(url_decoded):
                continue

            # If no sub-category class, try URL slug for category
            if not cat_hint:
                cat_hint = category_from_text(url_decoded)

            refs.append({"url": href, "category_hint": cat_hint})
            added += 1

        print(f"    ✅ +{added} products  (running total: {len(refs)})")

        # --- Next page? ---
        load_more = (
            soup.select_one("a.wd-load-more") or
            soup.select_one("a.next.page-numbers") or
            soup.select_one("nav.woocommerce-pagination a.next")
        )
        if not load_more:
            print("    ℹ️  No 'load more' link → pagination complete.")
            break

        page += 1
        time.sleep(DELAY)

    return refs


# ── PRODUCT DETAIL PAGE ────────────────────────────────────────────────────────
def scrape_product(ref):
    url = ref["url"]
    cat_hint = ref.get("category_hint")
    soup = get_soup(url)
    if not soup:
        return None

    # ── Product name (Arabic) ──────────────────────────────────────────────────
    h1 = soup.select_one("h1.product_title, h1.entry-title")
    name_ar = h1.get_text(strip=True) if h1 else ""
    if not name_ar:
        return None

    # ── English name ──────────────────────────────────────────────────────────
    name_en = translate_name(name_ar)

    # ── SKU ───────────────────────────────────────────────────────────────────
    sku_el = soup.select_one(".sku")
    sku = sku_el.get_text(strip=True) if sku_el else ""

    # ── Attributes table ──────────────────────────────────────────────────────
    attrs = {}
    for tr in soup.select(".woocommerce-product-attributes tr"):
        th = tr.select_one("th")
        td = tr.select_one("td")
        if th and td:
            attrs[th.get_text(strip=True)] = td.get_text(strip=True)

    attrs_brand   = attrs.get("ماركة") or attrs.get("Brand")
    attrs_warranty= attrs.get("ضمان") or attrs.get("Warranty")

    # ── Short description ─────────────────────────────────────────────────────
    sd_el    = soup.select_one(".woocommerce-product-details__short-description")
    short_desc = sd_el.get_text("\n", strip=True) if sd_el else ""

    # ── Combined text for extraction ──────────────────────────────────────────
    combined = name_ar + "\n" + short_desc

    # ── Category (best available) ─────────────────────────────────────────────
    category = cat_hint  # from listing page

    # If still no category, check breadcrumb
    if not category:
        category = category_from_breadcrumb(soup)
        if category == "EXCLUDE":
            return None

    # If still no category, parse from product name
    if not category:
        category = category_from_text(name_ar)

    # Final exclusion check
    if should_exclude(name_ar) or should_exclude(unquote(url)):
        return None

    # Default fallback (almost all uncategorised are Split ACs)
    if not category:
        category = "Split AC"


    # ── Brand ─────────────────────────────────────────────────────────────────
    brand = extract_brand(name_ar + " " + name_en, attrs_brand)

    # ── BTU & Tonnage ─────────────────────────────────────────────────────────
    btu     = extract_btu(combined)
    tonnage = btu_to_ton(btu)

    # ── Cooling / Inverter / Compressor ───────────────────────────────────────
    cooling   = get_cooling_type(combined)
    inverter  = get_inverter(combined)
    compressor= get_compressor(short_desc or name_ar)

    # ── Price ─────────────────────────────────────────────────────────────────
    price_el             = soup.select_one("p.price")
    orig_price, sale_price = extract_price(price_el)
    disc                 = discount_pct(orig_price, sale_price)
    if not orig_price:
        orig_price = sale_price

    # Skip obvious accessories (price < 200 SAR and no BTU number in name)
    if sale_price and sale_price < 200 and not re.search(
        r"\d{4,}", name_ar
    ):
        return None

    # ── Stock ─────────────────────────────────────────────────────────────────
    stock_el  = soup.select_one(".stock")
    stock_txt = stock_el.get_text(strip=True) if stock_el else ""
    qty_m     = re.search(r"(\d+)", stock_txt)
    stock_qty = int(qty_m.group(1)) if qty_m else None
    in_stock  = bool(
        stock_el and "متوفر" in stock_txt and "غير" not in stock_txt
    )

    # ── Warranty ──────────────────────────────────────────────────────────────
    warranty = parse_warranty(attrs_warranty)
    # Fallback: search full page text for warranty
    if not warranty:
        page_text = soup.get_text()
        wm = re.search(
            r"ضمان\s*(سنتان|سنتين|سنة|\d+\s*سنو?ات?|\d+\s*[Yy]ear)",
            page_text
        )
        if wm:
            warranty = parse_warranty(wm.group(1))

    # ── Image ─────────────────────────────────────────────────────────────────
    img_el = soup.select_one(
        ".woocommerce-product-gallery__image img, .wp-post-image"
    )
    image_url = ""
    if img_el:
        image_url = (
            img_el.get("data-large_image")
            or img_el.get("data-src")
            or img_el.get("src", "")
        )

    return {
        "Product_Name_EN": name_en,
        "Product_Name_AR": name_ar,
        "SKU":             sku,
        "Brand":           brand,
        "Category":        category,
        "BTU":             btu,
        "Tonnage":         tonnage,
        "Cooling_Type":    cooling,
        "Inverter":        inverter,
        "Compressor":      compressor,
        "Original_Price":  orig_price,
        "Sale_Price":      sale_price,
        "Discount":        disc,
        "In_Stock":        "Yes" if in_stock else "No",
        "Stock_Qty":       stock_qty,
        "Warranty":        warranty,
        "Image_URL":       image_url,
        "Product_URL":     url,
        "Scrape_Date":     datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  Binmomen AC Scraper  v3  –  Full coverage, no missing models")
    print("=" * 65)
    t0 = datetime.now()

    # ── Step 1: collect all product URLs from listing pages ───────────────────
    print("\n[Step 1]  Collecting product URLs …")
    refs = get_all_product_refs(BASE_URL + AC_CATEGORY)
    total = len(refs)
    print(f"\n  ✅  {total} AC products found (after excluding Desert/Fan)\n")
    if total == 0:
        print("Nothing to scrape. Exiting.")
        sys.exit(0)

    # ── Step 2: scrape each product detail page (parallel) ────────────────────
    print("[Step 2]  Scraping product pages … (parallel, 8 workers)\n")
    products = []
    skipped  = []
    print_lock = threading.Lock()

    def scrape_with_index(args):
        i, ref = args
        slug = unquote(ref["url"]).split("/product/")[-1].strip("/")[:45]
        data = scrape_product(ref)
        with print_lock:
            if data:
                print(
                    f"  [{i:3d}/{total}] ✅  {data['Brand'] or 'N/A':15s} | "
                    f"{str(data['BTU'] or '?'):>6} BTU | "
                    f"{data['Tonnage'] or '?'} Ton | "
                    f"{data['Category']}"
                )
            else:
                print(f"  [{i:3d}/{total}] ⏭️   Skipped — {slug}")
        return i, data

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(scrape_with_index, (i, ref)): i
                   for i, ref in enumerate(refs, 1)}
        for future in as_completed(futures):
            i, data = future.result()
            if data:
                products.append(data)
            else:
                skipped.append(refs[i - 1]["url"])

    if not products:
        print("\n❌  No products collected.")
        sys.exit(0)

    # ── Step 3: Build DataFrame ────────────────────────────────────────────────
    df_new = pd.DataFrame(products)

    COL_ORDER = [
        "Product_Name_EN", "Product_Name_AR", "SKU", "Brand", "Category",
        "BTU", "Tonnage", "Cooling_Type", "Inverter", "Compressor",
        "Original_Price", "Sale_Price", "Discount",
        "In_Stock", "Stock_Qty", "Warranty",
        "Image_URL", "Product_URL", "Scrape_Date",
    ]
    df_new = df_new.reindex(columns=COL_ORDER)

    # ── Step 4: Append to cumulative Excel file ────────────────────────────────
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, OUTPUT_FILE)

    if os.path.exists(output_path):
        df_old = pd.read_excel(output_path)
        # ── 중복 방지: 오늘 날짜 데이터가 이미 있으면 스킵 ──────────────
        today_date = datetime.now().strftime('%Y-%m-%d')
        if 'Scrape_Date' in df_old.columns:
            existing_dates = pd.to_datetime(df_old['Scrape_Date'], errors='coerce').dt.strftime('%Y-%m-%d')
            if today_date in existing_dates.values:
                print(f"\n  [SKIP] Today's data ({today_date}) already exists in '{OUTPUT_FILE}'. Skipping append and snapshot.")
                return
        # ─────────────────────────────────────────────────────────────────
        # Drop existing "No" column to avoid duplicate column error on insert
        if "No" in df_old.columns:
            df_old = df_old.drop(columns=["No"])
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        # Renumber (optional – helps dashboard row ID)
        df_combined.insert(0, "No", range(1, len(df_combined) + 1))
        df_combined.to_excel(output_path, index=False)
        print(
            f"\n  📎  Appended {len(df_new)} rows → '{OUTPUT_FILE}'"
            f"  (total rows: {len(df_combined)})"
        )
    else:
        df_new.insert(0, "No", range(1, len(df_new) + 1))
        df_new.to_excel(output_path, index=False)
        print(f"\n  📁  Created '{OUTPUT_FILE}'  ({len(df_new)} rows)")

    # Also save a timestamped snapshot for this run
    ts       = datetime.now().strftime("%Y%m%d_%H%M")
    snap_path= os.path.join(script_dir, f"Binmomen_AC_{ts}.xlsx")
    df_new.to_excel(snap_path, index=False)
    print(f"  📸  Snapshot: '{os.path.basename(snap_path)}'")

    # ── Step 5: Summary ────────────────────────────────────────────────────────
    elapsed = int((datetime.now() - t0).total_seconds())
    print("\n" + "=" * 65)
    print(f"  ✅  Done!  {len(products)} scraped  |  {len(skipped)} skipped  |  {elapsed}s")
    print("=" * 65)

    print(f"\n  Category breakdown:\n{df_new['Category'].value_counts().to_string()}")
    print(f"\n  Brand breakdown:\n{df_new['Brand'].value_counts().to_string()}")

    null_report = {
        "BTU":      df_new["BTU"].isna().sum(),
        "Tonnage":  df_new["Tonnage"].isna().sum(),
        "Brand":    df_new["Brand"].isna().sum(),
        "Warranty": df_new["Warranty"].isna().sum(),
    }
    print("\n  Null counts (ideal = 0 for critical fields):")
    for field, cnt in null_report.items():
        flag = "⚠️ " if cnt > 0 else "✅"
        print(f"    {flag}  {field}: {cnt} / {len(df_new)}")

    if skipped:
        print(f"\n  Skipped URLs ({len(skipped)}):")
        for u in skipped[:10]:
            print(f"    • {u}")
        if len(skipped) > 10:
            print(f"    … and {len(skipped)-10} more")

    return output_path


if __name__ == "__main__":
    main()
