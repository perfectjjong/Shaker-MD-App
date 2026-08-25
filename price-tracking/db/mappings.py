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
    "alkhater":    {"name": "Al Khater",    "alert_basis": "sl", "cond_discount": None},
}


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
    sku = text(raw.get("sku")) or text(raw.get("product_id"))
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


def normalize_alkhater(raw, sheet_name=None):
    sl = parse_num(raw.get("Price_SAR"))
    return {
        "sku": text(raw.get("SKU")),
        "brand": text(raw.get("Brand")),
        "model": text(raw.get("Model")),
        "name_en": text(raw.get("Product_Name")),
        "name_ar": None,
        "category": text(raw.get("AC_Type")),
        "btu": None,
        "ton": parse_num(raw.get("Ton")),
        "compressor": text(raw.get("Compressor")),
        "ac_type": text(raw.get("Cold_HC")),
        "url": text(raw.get("URL")),
        "run_date": sheet_name or date_part(raw.get("Scraped_At")),  # 시트명 = 수집일
        "scraped_at": text(raw.get("Scraped_At")),
        "sp": parse_num(raw.get("Original_Price_SAR")),
        "sl": sl,
        "fp": sl,  # 조건부 할인 없음
        "fj": None,
        "discount_pct": parse_pct(raw.get("Discount_Pct")),
        "in_stock": parse_bool(raw.get("In_Stock")),
        "stock_qty": None,
        "promo_text": None,
        "attrs": _attrs(raw, ["Is_On_Sale", "Page"]),
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
    "alkhater": {
        "source": "sheet_per_date", "sheet": None,
        "legacy_master": "channels/alkhater/alkhater_ac_prices.xlsx",
        "normalize": normalize_alkhater,
    },
    # ── Phase 0: 서버 실물 마스터 확인 후 매핑 작성 필요 ──
    "bh": None,
    "sws": None,
    "alkhunaizan": None,
    "almanea": None,
    "tamkeen": None,
    "blackbox": None,
    "technobest": None,
}
