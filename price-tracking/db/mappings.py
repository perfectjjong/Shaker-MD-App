#!/usr/bin/env python3
"""
채널별 컬럼 매핑 — Excel 마스터의 원본 컬럼을 정규 스키마로 변환.

설계 문서 §5 매핑표의 구현. 정규 필드:
  sku, brand, model, name_en, name_ar, category, btu, ton, compressor, ac_type, url,
  run_date, scraped_at, sp, sl, fp, fj, discount_pct, in_stock, stock_qty, promo_text, attrs

매핑 미완성 채널(mapping=None)은 적재 시 경고 후 스킵된다 (Phase 0: 서버 실물 확인 필요).
"""
import math
import re

# ── 채널 메타데이터 (PRICE_SCHEME_GUIDE.md 기준) ─────────────────────────────
CHANNELS = {
    "extra":       {"name": "eXtra",        "alert_basis": "sl", "cond_discount": "promo_code"},
    "bh":          {"name": "BH",           "alert_basis": "cp", "cond_discount": None},
    "sws":         {"name": "SWS",          "alert_basis": "sl", "cond_discount": "cashback"},
    "najm":        {"name": "Najm",         "alert_basis": "sl", "cond_discount": None},
    "alkhunaizan": {"name": "Al Khunaizan", "alert_basis": "sl", "cond_discount": "only_pay"},
    "almanea":     {"name": "Al Manea",     "alert_basis": "sl", "cond_discount": "cashback"},
    "tamkeen":     {"name": "Tamkeen",      "alert_basis": "sl", "cond_discount": None},
    "binmomen":    {"name": "Bin Momen",    "alert_basis": "sl", "cond_discount": None},
    "blackbox":    {"name": "Black Box",    "alert_basis": "fp", "cond_discount": None},
    "technobest":  {"name": "Technobest",   "alert_basis": "sl", "cond_discount": None},
}
# 🔴 alkhater 는 2026-09-02 완전 폐기(형님 지시). 되살리지 말 것.
#    2026-05-11 하루치만 수집하고 정지(Cloudflare + 데이터센터 IP 평판차단, 유료 우회 필요),
#    2026-07-22 대시보드·cron 폐기. 그 뒤에도 MAPPINGS 에 남아 ingest_daily 가 매일 exit 1 을
#    내며 "알려진 스킵"과 "진짜 적재 실패"의 구분을 망가뜨렸다.


# ── 파싱 헬퍼 ────────────────────────────────────────────────────────────────
def _is_nan(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def parse_num(v):
    """'3,299' / 'SAR 123.5' / 39.0 → float. 실패 시 None."""
    if _is_nan(v) or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v))
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def parse_int(v):
    n = parse_num(v)
    return int(n) if n is not None else None


def parse_ton(v):
    """'1.5 Ton' / '2 Ton (~24000 BTU)' → 1.5 / 2.0.
    ⚠️ parse_num을 그대로 쓰면 괄호 안 BTU까지 붙여 읽어 '1 Ton (~12000 BTU)' → 112000 이 된다.
    앞쪽 첫 숫자만 취한다."""
    if _is_nan(v) or v == "":
        return None
    m = re.match(r"\s*([\d.]+)", str(v))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_pct(v):
    """'39.0%' / '10%' / 0.39 → 39.0 (퍼센트 단위 float)."""
    n = parse_num(v)
    if n is None:
        return None
    # 0~1 사이 소수는 비율로 간주 (0.39 → 39.0)
    return round(n * 100, 2) if 0 < n < 1 else n


_TRUTHY = {"yes", "true", "1", "y", "in stock", "instock", "available", "sale"}
_FALSY = {"no", "false", "0", "n", "out of stock", "outofstock", "unavailable"}


def parse_bool(v):
    if _is_nan(v) or v == "":
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(bool(v))
    s = str(v).strip().lower()
    if s in _TRUTHY:
        return 1
    if s in _FALSY:
        return 0
    return None


def date_part(v):
    """datetime / '2026-02-23 21:13' / '2026-02-23' → 'YYYY-MM-DD'. 실패 시 None."""
    if _is_nan(v) or v == "":
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v).strip())
    return m.group(1) if m else None


def text(v):
    if _is_nan(v) or v == "":
        return None
    return str(v).strip() or None


def id_text(v):
    """SKU/ID용 문자열화. 엑셀 열에 NaN이 섞이면 pandas가 int 열을 float로 승격시켜
    1000620 → '1000620.0'이 되고, 같은 SKU가 두 상품으로 갈라진다. 정수값 float는 .0을 제거한다."""
    if _is_nan(v) or v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    return s or None


def url_slug(u):
    """상품 URL의 마지막 경로 조각 → 대체 SKU (사이트에 모델코드가 없는 상품용)."""
    u = text(u)
    if not u:
        return None
    slug = u.rstrip("/").split("/")[-1].split("?")[0]
    return slug or None


def _attrs(raw, keys):
    """채널 고유 필드를 JSON 보존용 dict로 추출 (빈 값 제외)."""
    out = {}
    for k in keys:
        v = raw.get(k)
        if not _is_nan(v) and v != "":
            out[k] = v if isinstance(v, (int, float, bool)) else str(v)
    return out


# ── 채널별 정규화 함수 ────────────────────────────────────────────────────────
def normalize_extra(raw, sheet_name=None):
    sl = parse_num(raw.get("Sale_Price"))
    promo = text(raw.get("Promo_Code"))
    # 조건부 할인: extra10 프로모 코드 → ×0.9 (PRICE_SCHEME_GUIDE.md)
    fp = round(sl * 0.9, 2) if (sl is not None and promo) else sl
    return {
        "sku": text(raw.get("SKU")),
        "brand": text(raw.get("Brand")),
        "model": text(raw.get("Model_No")),
        "name_en": text(raw.get("Product_Name")),
        "name_ar": None,
        "category": text(raw.get("Category")),
        "btu": parse_int(raw.get("BTU")),
        "ton": parse_num(raw.get("Cooling_Capacity_Ton")),
        "compressor": text(raw.get("Compressor_Type")),
        "ac_type": text(raw.get("Cold_or_HC")),
        "url": None,
        "run_date": date_part(raw.get("Scraped_At")),
        "scraped_at": text(raw.get("Scraped_At")),
        "sp": parse_num(raw.get("Standard_Price")),
        "sl": sl,
        "fp": fp,
        "fj": parse_num(raw.get("Jood_Gold_Price")),
        "discount_pct": parse_pct(raw.get("Discount_Rate")),
        "in_stock": parse_bool(raw.get("Stock_Status")),
        "stock_qty": None,
        "promo_text": promo or text(raw.get("Promo_Label")),
        "attrs": _attrs(raw, [
            "Discount_Amount", "Promo_Label", "Offer_Count", "Gift_Count", "Gift_Value",
            "Warranty_Period", "Compressor_Warranty", "Stock_Label", "eXtra_Exclusive",
        ]),
    }


def normalize_najm(raw, sheet_name=None):
    sku = id_text(raw.get("sku")) or id_text(raw.get("product_id"))
    return {
        "sku": sku,
        "brand": text(raw.get("brand_en")),
        "model": None,
        "name_en": text(raw.get("name_en")),
        "name_ar": text(raw.get("name_ar")),
        "category": text(raw.get("category_en")),
        "btu": parse_int(raw.get("btu")),
        "ton": parse_num(raw.get("ton")),
        "compressor": text(raw.get("compressor")),
        "ac_type": text(raw.get("ac_type")),
        "url": text(raw.get("url")),
        "run_date": date_part(raw.get("run_date")),
        "scraped_at": text(raw.get("scraped_at")),
        "sp": parse_num(raw.get("regular_price")),
        "sl": parse_num(raw.get("price")),
        "fp": parse_num(raw.get("bank_promo_price")) or parse_num(raw.get("price")),
        "fj": None,
        "discount_pct": parse_pct(raw.get("discount_pct")),
        "in_stock": parse_bool(raw.get("is_available")),
        "stock_qty": None,
        "promo_text": text(raw.get("bank_promo_label")) or text(raw.get("bank_promo_code")),
        "attrs": _attrs(raw, [
            "salla_tag", "brand_ar", "category_ar", "currency", "status", "is_on_sale",
            "is_out_of_stock", "rating_avg", "rating_count", "image_url",
            "bank_promo_code", "bank_promo_disc_pct", "bank_promo_label", "free_install",
        ]),
    }


def normalize_binmomen(raw, sheet_name=None):
    sl = parse_num(raw.get("Sale_Price"))
    return {
        "sku": text(raw.get("SKU")),
        "brand": text(raw.get("Brand")),
        "model": None,
        "name_en": text(raw.get("Product_Name_EN")),
        "name_ar": text(raw.get("Product_Name_AR")),
        "category": text(raw.get("Category")),
        "btu": parse_int(raw.get("BTU")),
        "ton": parse_num(raw.get("Tonnage")),
        "compressor": text(raw.get("Compressor")),
        "ac_type": text(raw.get("Cooling_Type")),
        "url": text(raw.get("Product_URL")),
        "run_date": date_part(raw.get("Scrape_Date")),
        "scraped_at": text(raw.get("Scrape_Date")),
        "sp": parse_num(raw.get("Original_Price")),
        "sl": sl,
        "fp": sl,  # 조건부 할인 없음 (PRICE_SCHEME_GUIDE.md)
        "fj": None,
        "discount_pct": parse_pct(raw.get("Discount")),
        "in_stock": parse_bool(raw.get("In_Stock")),
        "stock_qty": parse_int(raw.get("Stock_Qty")),
        "promo_text": None,
        "attrs": _attrs(raw, ["Inverter", "Warranty", "Image_URL"]),
    }


def normalize_bh(raw, sheet_name=None):
    # Weekly_Price_DB: Retailer는 'BH Store' 고정 (consolidate_ac.py가 하드코딩)
    sl = parse_num(raw.get("Current Price") or raw.get("Current_Price"))
    qty = parse_int(raw.get("Stock"))
    return {
        "sku": text(raw.get("Model Code") or raw.get("Model_Code")),
        "brand": text(raw.get("Brand")),
        "model": text(raw.get("Model Code") or raw.get("Model_Code")),
        "name_en": text(raw.get("Product Name")),
        "name_ar": None,
        "category": text(raw.get("Type")),
        "btu": parse_int(raw.get("BTU")),
        "ton": None,
        "compressor": None,
        "ac_type": text(raw.get("CO/C&H")),
        "url": text(raw.get("Product URL")),
        "run_date": date_part(raw.get("Run Timestamp") or raw.get("Run_Timestamp")),
        "scraped_at": text(raw.get("Run Timestamp") or raw.get("Run_Timestamp")),
        "sp": parse_num(raw.get("Regular Price") or raw.get("Regular_Price")),
        "sl": sl,
        "fp": sl,
        "fj": None,
        "discount_pct": parse_pct(raw.get("Discount %")),
        "in_stock": (1 if qty and qty > 0 else 0) if qty is not None else None,
        "stock_qty": qty,
        "promo_text": None,
        "attrs": _attrs(raw, ["Week", "Retailer", "Discount SAR", "Promo From",
                              "Promo To", "Last Updated"]),
    }


def normalize_sws(raw, sheet_name=None):
    d = parse_pct(raw.get("Discount"))  # '-42.08%' 형태 → 절대값 사용
    return {
        "sku": id_text(raw.get("Product ID")) or url_slug(raw.get("Product_URL")),
        "brand": text(raw.get("Brand")),
        "model": None,
        "name_en": text(raw.get("Product Name")),
        "name_ar": None,
        "category": text(raw.get("Type")),
        "btu": parse_int(raw.get("Capacity (BTU)")),
        "ton": parse_num(raw.get("Capacity (Ton)")),
        "compressor": text(raw.get("Compressor")),
        "ac_type": text(raw.get("Mode")),
        "url": text(raw.get("Product_URL")),
        "run_date": date_part(raw.get("Timestamp")),
        "scraped_at": text(raw.get("Timestamp")),
        "sp": parse_num(raw.get("Original Price (SAR)")),
        "sl": parse_num(raw.get("Price (SAR)")),
        "fp": parse_num(raw.get("Final Price (SAR)")) or parse_num(raw.get("Price (SAR)")),
        "fj": None,
        "discount_pct": abs(d) if d is not None else None,
        "in_stock": parse_bool(raw.get("Stock")),
        "stock_qty": None,
        "promo_text": text(raw.get("Cashback")),
        "attrs": _attrs(raw, ["Sub-Category", "Free Install", "Cashback"]),
    }


def normalize_alkhunaizan(raw, sheet_name=None):
    # 🔴 2026-08-31 정정: 가정이 반대였다. 원본 실측 결과
    #    Capacity = BTU 수치(18000.0) / Nominal Capacity = 톤 문자열('1.5 Ton (~18000 BTU)').
    #    이전 코드가 서로 바꿔 읽어 btu에 '1 Ton (~12000 BTU)'→112000 같은 값이 들어갔고,
    #    467개 상품 전량이 BTU 구간 집계에서 조용히 빠졌다.
    sl = parse_num(raw.get("Promotion Price (SAR)"))
    return {
        "sku": text(raw.get("SKU")) or text(raw.get("Reference")),
        "brand": text(raw.get("Brand")),
        "model": None,
        "name_en": text(raw.get("Product Name")),
        "name_ar": None,
        "category": text(raw.get("Category")),
        "btu": parse_int(raw.get("Capacity")),
        "ton": parse_ton(raw.get("Nominal Capacity")),
        "compressor": text(raw.get("Compressor Type")),
        "ac_type": text(raw.get("Type")),
        "url": text(raw.get("URL")),
        "run_date": date_part(raw.get("Scraped_At")),
        "scraped_at": text(raw.get("Scraped_At")),
        "sp": parse_num(raw.get("Original Price (SAR)")),
        "sl": sl,
        "fp": parse_num(raw.get("Only Pay Price (SAR)")) or sl,
        "fj": None,
        "discount_pct": parse_pct(raw.get("Discount Rate (%)")),
        "in_stock": parse_bool(raw.get("Stock Status")),
        "stock_qty": None,
        "promo_text": None,
        "attrs": _attrs(raw, ["Reference", "Wifi", "Color", "Energy Grade",
                              "Save amount (SAR)", "Free Installation"]),
    }


def normalize_almanea(raw, sheet_name=None):
    sl = parse_num(raw.get("Promo_Price"))
    qty = parse_int(raw.get("Stock"))
    return {
        "sku": text(raw.get("SKU")),
        "brand": text(raw.get("Brand")),
        "model": text(raw.get("Model")),
        "name_en": text(raw.get("Product_Name")),
        "name_ar": None,
        "category": text(raw.get("Category")),
        "btu": parse_int(raw.get("BTU")),
        "ton": parse_num(raw.get("Capacity_Ton")),
        "compressor": text(raw.get("Compressor_Type")),
        "ac_type": text(raw.get("Function")),
        "url": text(raw.get("URL_Key")),
        "run_date": date_part(raw.get("Scraped_At")),
        "scraped_at": text(raw.get("Scraped_At")),
        "sp": parse_num(raw.get("Original_Price")),
        "sl": sl,
        "fp": parse_num(raw.get("Final_Promo_Price")) or sl,   # Cashback 반영가
        "fj": parse_num(raw.get("AlAhli_Price")),              # Al Ahli 카드가
        "discount_pct": parse_pct(raw.get("Discount_Pct")),
        "in_stock": (1 if qty and qty > 0 else 0) if qty is not None else None,
        "stock_qty": qty,
        "promo_text": text(raw.get("Offer_Detail")),
        "attrs": _attrs(raw, ["Energy_Rating", "Color", "Country", "Warranty_Yr",
                              "Compressor_Warranty_Yr", "Has_Offer", "Free_Gift"]),
    }


def normalize_blackbox(raw, sheet_name=None):
    return {
        # Model Code 부재 상품(MANDO Concealed 등)은 URL 슬러그를 대체 SKU로 사용
        "sku": text(raw.get("Model Code")) or url_slug(raw.get("URL")),
        "brand": text(raw.get("Brand")),
        "model": text(raw.get("Model Code")),
        "name_en": text(raw.get("Name")),
        "name_ar": None,
        "category": text(raw.get("AC Type")),
        "btu": parse_int(raw.get("BTU")),
        "ton": parse_num(raw.get("Ton")),
        "compressor": text(raw.get("Compressor")),
        "ac_type": text(raw.get("Mode")),
        "url": text(raw.get("URL")),
        "run_date": date_part(raw.get("Scraped At")),
        "scraped_at": text(raw.get("Scraped At")),
        "sp": parse_num(raw.get("Original Price")),
        "sl": parse_num(raw.get("Sale Price")),
        "fp": parse_num(raw.get("Effective Price")),           # Alert 기준 (cascade)
        "fj": parse_num(raw.get("Effective BP")),              # BP 멤버십가 (별도 탭 기준)
        "discount_pct": parse_pct(raw.get("Discount %")),
        "in_stock": parse_bool(raw.get("In Stock")),
        "stock_qty": parse_int(raw.get("Stock Qty")),
        "promo_text": None,
        "attrs": _attrs(raw, ["Extra Disc %", "BP Price", "Free Install", "Install SAR",
                              "+10% Regular", "+10% BP Only", "Sale Ends"]),
    }


def normalize_tamkeen(raw, sheet_name=None):
    # file_per_date 소스: sheet_name 자리에 파일명에서 추출한 날짜('YYYY-MM-DD')가 전달됨
    sl = parse_num(raw.get("Sale Price (SR)"))
    qty = parse_int(raw.get("Stock Qty"))
    return {
        "sku": text(raw.get("SKU")),
        "brand": text(raw.get("Brand")),
        "model": None,
        "name_en": text(raw.get("Name")),
        "name_ar": None,
        "category": text(raw.get("Category")),
        "btu": parse_int(raw.get("Capacity (BTU)")),
        "ton": parse_num(raw.get("Tonnage")),
        "compressor": text(raw.get("Compressor")),
        "ac_type": text(raw.get("Cooling Type")),
        "url": text(raw.get("Product URL")),
        "run_date": sheet_name,
        "scraped_at": None,
        "sp": parse_num(raw.get("Original Price (SR)")),
        "sl": sl,
        "fp": sl,  # 조건부 할인 없음
        "fj": None,
        "discount_pct": parse_pct(raw.get("Discount (%)")),
        "in_stock": parse_bool(raw.get("In Stock")),
        "stock_qty": qty,
        "promo_text": None,
        "attrs": _attrs(raw, ["Discount (SR)", "Free Installation", "Express Delivery",
                              "Expected Delivery", "Image URL"]),
    }


def normalize_technobest(raw, sheet_name=None):
    sl = parse_num(raw.get("sale_price"))
    return {
        "sku": text(raw.get("sku")) or text(raw.get("product_id")),
        "brand": text(raw.get("brand_en")),
        "model": None,
        "name_en": None,
        "name_ar": text(raw.get("name")),
        "category": text(raw.get("category")),
        "btu": parse_int(raw.get("BTU")),
        "ton": parse_num(raw.get("Ton")),
        "compressor": None,
        "ac_type": None,
        "url": text(raw.get("url")),
        "run_date": date_part(raw.get("scrape_date")),
        "scraped_at": text(raw.get("scrape_timestamp")),
        "sp": parse_num(raw.get("regular_price")),
        "sl": sl,
        "fp": sl,  # 조건부 할인 없음
        "fj": None,
        "discount_pct": parse_pct(raw.get("discount_pct")),
        "in_stock": parse_bool(raw.get("is_available")),
        "stock_qty": None,
        "promo_text": text(raw.get("promotion")) or text(raw.get("subtitle")),
        "attrs": _attrs(raw, ["brand_ar", "currency", "is_on_sale", "is_out_of_stock",
                              "status", "subtitle", "image_url"]),
    }


# ── 채널별 소스 정의 ──────────────────────────────────────────────────────────
# source: 'single_sheet' = 시트 하나에 전 기간 누적 / 'sheet_per_date' = 날짜별 시트
# legacy_master: config.get_master_path()에 파일이 없을 때 폴백 경로 (price-tracking/ 기준)
MAPPINGS = {
    "extra": {
        "source": "single_sheet", "sheet": "Prices DB",
        "legacy_master": "channels/extra/extra_ac_Prices_Tracking_Master.xlsx",
        "normalize": normalize_extra,
    },
    "najm": {
        "source": "single_sheet", "sheet": 0,
        "legacy_master": "channels/najm/najm_ac_master.xlsx",
        "normalize": normalize_najm,
    },
    "binmomen": {
        "source": "single_sheet", "sheet": 0,
        "legacy_master": "channels/binmomen/Binmomen_AC_Data.xlsx",
        "normalize": normalize_binmomen,
    },
    "bh": {
        "source": "single_sheet", "sheet": "Weekly_Price_DB",
        "legacy_master": "channels/bh/BH_Subdealer_AC_Master.xlsx",
        "normalize": normalize_bh,
    },
    "sws": {
        "source": "single_sheet", "sheet": "Products_DB",
        "legacy_master": "channels/sws/SWS_AC_Price_Tracking_Master.xlsx",
        "normalize": normalize_sws,
    },
    "alkhunaizan": {
        "source": "single_sheet", "sheet": "Products_DB",
        "legacy_master": "channels/alkhunaizan/AlKhunaizan_AC_Prices Tracking_Master.xlsx",
        "normalize": normalize_alkhunaizan,
    },
    "almanea": {
        "source": "single_sheet", "sheet": "Products_DB",
        "legacy_master": "channels/almanea/Almanea_AC_Price_Tracking_Master.xlsx",
        "normalize": normalize_almanea,
    },
    "blackbox": {
        "source": "single_sheet", "sheet": "Product_DB",
        "legacy_master": "channels/blackbox/Black Box_AC_Price tracking_Master.xlsx",
        "normalize": normalize_blackbox,
    },
    "technobest": {
        "source": "single_sheet", "sheet": 0,
        "legacy_master": "channels/technobest/TechnoBest_AC_Master.xlsx",
        "normalize": normalize_technobest,
    },
    "tamkeen": {
        # 단일 마스터 없음 — 날짜별 스냅샷 파일 누적, 날짜당 최신 파일 사용 (대시보드와 동일 규칙)
        "source": "file_per_date", "sheet": "All Products",
        "glob": "~/2026/06. Price Tracking/06. Tamkeen/Tamkeen_Complete_*.xlsx",
        "normalize": normalize_tamkeen,
    },
}
