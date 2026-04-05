"""
Najm Store (najm.store) - Air Conditioner Scraper  v2.5
Platform : Salla  |  API: https://api.salla.dev/store/v1/
Output   : najm_ac_master.xlsx  (누적 append)

v2.3 fixes:
  - brand_en: BRAND_MAP → 아랍어 번역 → name_en 패턴 매칭 3단계 fallback
  - BTU: 아랍어 파싱 실패 시 name_en "24,000 BTU" 형태에서 재추출
  - Compressor: 아랍어 키워드 없으면 name_en 검사, 없으면 Rotary 기본값
  - AC Type: 아랍어 키워드 없으면 name_en 영문 패턴 fallback

v2.2 fixes:
  - Ton: BTU 범위 기반 룩업 테이블 (9000~63000 → 1~5 ton)
  - discount_pct: 숫자 → "36.1%" 문자열 형식

v2.1 fixes:
  - Arabic normalization: إنفرتر / أنفرتر / انفرتر 모두 Inverter로 인식
  - Ton 계산: 이름에서만 추출 후 BTU 기반 검증, 설명문 잡음 제거
  - sub_category 제거 → salla_tag (Salla 자체 1차 카테고리 라벨, 참고용)
  - 100% null 컬럼 제거 (mpn, sale_price, discount_ends, quantity)

Requirements:
    pip install requests pandas deep_translator
"""

import sys
import io
# Windows 터미널 UTF-8 강제 설정 (아랍어/특수문자 출력)
# hasattr 체크: VS Code / IDLE / Jupyter 등 buffer 속성이 없는 환경에서 AttributeError 방지
try:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

import re
import unicodedata
import requests
import pandas as pd
import time
import json
from pathlib import Path
from datetime import datetime

try:
    from deep_translator import GoogleTranslator
    TRANSLATION_AVAILABLE = True
except ImportError:
    TRANSLATION_AVAILABLE = False
    print("⚠  deep_translator 미설치 → pip install deep_translator")


# ══════════════════════════════════════════════
#  설정
# ══════════════════════════════════════════════

STORE_ID   = "1874210423"
BASE_URL   = "https://api.salla.dev/store/v1/products"
MASTER_XLSX = Path(__file__).parent / "najm_ac_master.xlsx"  # 스크립트 위치 기준 절대경로

HEADERS = {
    "Accept"           : "application/json",
    "X-Requested-With" : "XMLHttpRequest",
    "S-SOURCE"         : "twilight",
    "S-APP-VERSION"    : "2.14.363",
    "S-APP-OS"         : "browser",
    "Store-Identifier" : STORE_ID,
    "currency"         : "SAR",
    "accept-language"  : "ar",
    "cache-control"    : "no-cache",
}

CATEGORIES = {
    "مكيف سبليت"   : {"id": "1310134820", "name_en": "Split AC"},
    "مكيف شباك"    : {"id": "2085286875", "name_en": "Window AC"},
    "مكيف صحراوي"  : {"id": "1350612441", "name_en": "Floor-standing AC"},
    "مكيف كاسيت"   : {"id": "886929375",  "name_en": "Cassette AC"},
    "مكيفات انفرتر": {"id": "1048125595", "name_en": "Inverter AC"},
    "مكيف مخفي"    : {"id": "343271290",  "name_en": "Concealed Central AC"},
}

PER_PAGE    = 20
REQ_DELAY   = 0.5
TRANS_DELAY = 0.25


# ══════════════════════════════════════════════
#  브랜드 교정 사전
# ══════════════════════════════════════════════

BRAND_MAP = {
    "جري": "Gree", "جري آي": "Gree", "ميديا": "Midea",
    "توشيبا": "Toshiba", "سامسونج": "Samsung",
    "ال جي": "LG", "الجي": "LG", "ال  جي": "LG",
    "باناسونيك": "Panasonic", "داي وو": "Daewoo",
    "شارب": "Sharp", "هيتاشي": "Hitachi",
    "كاريير": "Carrier", "كريتال": "Crystal",
    "يونيون اير": "Union Air", "يونيون": "Union",
    "ميتسوبيشي": "Mitsubishi", "فريش": "Fresh",
    "هاير": "Haier", "ويرلبول": "Whirlpool",
    "هيسنس": "Hisense", "تكنو": "Tecno",
    "دايسون": "Dyson", "دبليو بوكس": "W-Box",
    "جنرال": "General", "ماكس": "Max",
    "فيشر": "Fisher", "نيكاي": "Nikai",
    "او جنرال": "O General", "اوجنرال": "O General",
    "اوكس": "Aux", "تي سي ال": "TCL",
    "ارو": "Arrow", "اورورا": "Aurora",
    "ام تي سي": "MTC", "كولين": "Colin",
    # 아랍어 → 구글번역이 일반 단어를 반환하는 브랜드 직접 교정
    "روى"   : "Rawa",
    "سرين"  : "Serene",
    "زيترست": "Zetrust",
    "فوجي"  : "Fuji",
    "وايت وستنجهاوس": "White Westinghouse",
}

# 영문 브랜드 리스트 (name_en에서 brand_en 추출 fallback용)
# 다중 단어 브랜드가 먼저 매칭되도록 길이 내림차순 정렬
_BRAND_EN_LIST = [
    "White Westinghouse", "O General", "Union Air", "W-Box", "W Box",
    "Gree", "Midea", "Toshiba", "Samsung", "LG", "Panasonic", "Daewoo",
    "Sharp", "Hitachi", "Carrier", "Crystal", "Union", "Mitsubishi",
    "Fresh", "Haier", "Whirlpool", "Hisense", "Tecno", "Dyson",
    "General", "Max", "Basic", "OX", "TCL", "Aux", "Chigo",
    "Fisher", "Nikai", "Arrow", "Aurora", "MTC", "Colin",
    "Rawa", "Serene", "Zetrust", "Fuji",
]
_BRAND_EN_PATTERN = re.compile(
    r'(?:^|\b)(' +
    '|'.join(re.escape(b) for b in sorted(_BRAND_EN_LIST, key=len, reverse=True)) +
    r')\b',
    re.IGNORECASE,
)


# ══════════════════════════════════════════════
#  번역 유틸
# ══════════════════════════════════════════════

_cache: dict = {}

def translate(text: str | None) -> str | None:
    if not text or not TRANSLATION_AVAILABLE:
        return text
    text = str(text).strip()
    if not text or text in _cache:
        return _cache.get(text, text)
    if all(c.isascii() for c in text):
        _cache[text] = text
        return text
    try:
        result = GoogleTranslator(source="ar", target="en").translate(text)
        _cache[text] = result or text
        time.sleep(TRANS_DELAY)
    except Exception as e:
        print(f"    ⚠ 번역 실패: {e}")
        _cache[text] = text
    return _cache[text]


# ══════════════════════════════════════════════
#  아랍어 정규화
# ══════════════════════════════════════════════

# 아랍어 Alef 계열 모두 → 기본 Alef(ا)로 통일
_ALEF_NORM = str.maketrans("أإآٱ", "اااا")
# 아랍어 단모음 부호(harakat) 제거용 패턴
_HARAKAT = re.compile(r'[\u064B-\u065F\u0670]')

def norm_ar(text: str) -> str:
    """아랍어 텍스트 정규화: Alef 변형 통일 + 단모음 제거"""
    if not text:
        return ""
    return _HARAKAT.sub("", text.translate(_ALEF_NORM))


# ══════════════════════════════════════════════
#  BTU → Ton 범위 룩업 테이블
#  (산업 표준 기준, 1~5 ton, 0.5 단위)
# ══════════════════════════════════════════════

_BTU_TON_RANGES = [
    (9000,  15000, 1.0),
    (15000, 21000, 1.5),
    (21000, 27000, 2.0),
    (27000, 33000, 2.5),
    (33000, 39000, 3.0),
    (39000, 45000, 3.5),
    (45000, 51000, 4.0),
    (51000, 57000, 4.5),
    (57000, 63000, 5.0),
]

def btu_to_ton(btu: int) -> float | None:
    """BTU 값을 범위 룩업 테이블로 Ton 변환 (1~5, 0.5 단위)"""
    for lo, hi, ton in _BTU_TON_RANGES:
        if lo <= btu < hi:
            return ton
    return None  # 범위 밖 (9000 미만 or 63000 이상)


# ══════════════════════════════════════════════
#  스펙 파서  (제품명 + 설명문에서 추출)
# ══════════════════════════════════════════════

def parse_specs(name: str, description: str, name_en: str = "") -> dict:
    """
    BTU, Ton, Compressor type, AC type 추출
    - 아랍어 Alef 정규화로 إنفرتر / أنفرتر / انفرتر 모두 인식
    - Ton: BTU 범위 룩업 테이블 우선 (BTU 없을 때만 이름 텍스트 fallback)
    - BTU: 아랍어 파싱 실패 시 name_en ("24,000 BTU") 에서 재시도
    - Compressor: 아랍어 키워드 없으면 name_en 검사 후 최종 Rotary 기본값
    """
    name_n  = norm_ar(name or "")
    desc_n  = norm_ar(description or "")
    name_text = name_n
    full_text = name_n + " " + desc_n
    name_en_l = (name_en or "").lower()

    # ── BTU (우선: 아랍어 وحدة/BTU — 콤마 포함 숫자 허용: "12,000 وحدة")
    btu = None
    m = re.search(r'([\d,]{4,8})\s*(?:وحدة|BTU)', full_text, re.IGNORECASE)
    if m:
        try:
            btu = int(m.group(1).replace(',', ''))
        except ValueError:
            pass

    # BTU fallback: 영문 제품명 "24,000 BTU" 또는 "12,000 units" 형태
    if btu is None and name_en:
        m = re.search(r'([\d,]{4,8})\s*(?:BTU|units?)\b', name_en, re.IGNORECASE)
        if m:
            try:
                btu = int(m.group(1).replace(',', ''))
            except ValueError:
                pass

    # ── Ton: BTU 범위 룩업 우선 → BTU 없으면 이름 텍스트 fallback
    ton = None
    if btu:
        ton = btu_to_ton(btu)
    if ton is None:
        m = re.search(r'(\d+(?:\.\d+)?)\s*طن', name_text)
        if m:
            ton = float(m.group(1))

    # ── Compressor type
    # 우선순위 1: 설명문 구조화 스펙 "تقنية التشغيل: ..."
    compressor = None
    m = re.search(r'تقنية التشغيل\s*[:：]\s*([^\n\r،,|<]+)', desc_n)
    if m:
        c_raw = norm_ar(m.group(1).strip())
        if 'انفرتر' in c_raw or 'inverter' in c_raw.lower():
            compressor = 'Inverter'
        elif 'روتري' in c_raw or 'rotary' in c_raw.lower():
            compressor = 'Rotary'
        elif 'اون اوف' in c_raw or 'on-off' in c_raw.lower() or 'on/off' in c_raw.lower():
            compressor = 'On-Off'

    # 우선순위 2: 전체 아랍어 텍스트 키워드 탐지
    if compressor is None:
        if 'انفرتر' in full_text or 'inverter' in full_text.lower():
            compressor = 'Inverter'
        elif 'روتري' in full_text or 'rotary' in full_text.lower():
            compressor = 'Rotary'
        elif re.search(r'اون\s*اوف|on[- /]off', full_text, re.IGNORECASE):
            compressor = 'On-Off'

    # 우선순위 3: 영문 제품명에서 Inverter/Inver 키워드 탐지
    if compressor is None:
        if re.search(r'\binver(ter)?\b', name_en_l):
            compressor = 'Inverter'
        else:
            # Inverter 언급 없음 → Rotary (On-Off 계열 기본값)
            compressor = 'Rotary'

    # ── AC Type
    ac_type = None
    if re.search(r'بارد\s*و\s*حار|حار\s*و\s*بارد', full_text):
        ac_type = 'Heat & Cool'
    elif re.search(r'بارد\s*فقط|cooling.?only', full_text, re.IGNORECASE):
        ac_type = 'Cooling Only'
    elif re.search(r'حار\s*فقط|heating.?only', full_text, re.IGNORECASE):
        ac_type = 'Heating Only'
    # AC Type fallback: 영문 제품명에서 추출
    if ac_type is None and name_en:
        if re.search(r'hot.?and.?cold|heat.?&.?cool|h[/&]c\b', name_en_l):
            ac_type = 'Heat & Cool'
        elif re.search(r'cooling.?only|cold.?only', name_en_l):
            ac_type = 'Cooling Only'
        elif re.search(r'heating.?only', name_en_l):
            ac_type = 'Heating Only'

    return {
        "btu"       : btu,
        "ton"       : ton,
        "compressor": compressor,
        "ac_type"   : ac_type,
    }


# ══════════════════════════════════════════════
#  제품 파싱
# ══════════════════════════════════════════════

def parse_product(p: dict, category_ar: str, category_en: str, run_date: str) -> dict:
    brand_ar    = (p.get("brand") or {}).get("name")
    salla_tag   = (p.get("category") or {}).get("name")   # Salla 내부 1차 카테고리 (프로모션 태그 포함)
    name_ar     = p.get("name") or ""
    description = p.get("description") or ""

    # 번역 먼저 수행 → parse_specs에 전달 (BTU/Compressor/AC Type 영문 fallback용)
    name_en = translate(name_ar) or ""
    specs   = parse_specs(name_ar, description, name_en)

    regular  = p.get("regular_price") or 0
    price    = p.get("price") or 0
    disc_pct = f"{round((1 - price / regular) * 100, 1)}%" if regular > 0 else None

    # brand_ar 정제: "ال جي: مكيفات سبليت وشباك" → "ال جي" (콜론 뒤 카테고리 제거)
    brand_ar_clean = brand_ar.split(":")[0].strip() if brand_ar else None

    # brand_en: BRAND_MAP → 아랍어 번역 → name_en 패턴/첫 단어 순으로 fallback
    brand_en = (
        BRAND_MAP.get(brand_ar)            # 원본 그대로 먼저 시도
        or BRAND_MAP.get(brand_ar_clean)   # 콜론 제거 후 재시도
        or translate(brand_ar_clean)       # 번역 (깨끗한 브랜드명만)
    )
    # 번역 결과에 ": ..." 카테고리 suffix가 붙은 경우 제거
    if brand_en and ":" in brand_en:
        brand_en = brand_en.split(":")[0].strip()
    # name_en 패턴 매칭: brand_en이 없거나 너무 길거나 all-lowercase (번역 부산물 의심)
    if name_en and (not brand_en or len(brand_en) > 30 or brand_en == brand_en.lower()):
        m = _BRAND_EN_PATTERN.search(name_en)
        if m:
            raw = m.group(1)
            brand_en = "W-Box" if raw.lower() in ("w box", "w-box") else raw
        elif not brand_en or brand_en == brand_en.lower():
            # 패턴 미매칭이면 name_en 첫 단어를 브랜드로 사용 (고유명사 유사 여부 확인)
            first_word = name_en.split()[0] if name_en else ""
            if first_word and first_word[0].isupper() and len(first_word) >= 3:
                brand_en = first_word

    return {
        # ── 식별
        "product_id"    : p.get("id"),
        "sku"           : p.get("sku"),

        # ── 제품명
        "name_ar"       : name_ar,
        "name_en"       : name_en,

        # ── 카테고리 (우리가 필터링한 카테고리)
        "category_en"   : category_en,
        "category_ar"   : category_ar,
        # salla_tag: Salla가 제품에 붙인 1차 카테고리 (참고용, 프로모션 태그 섞임)
        "salla_tag"     : salla_tag,

        # ── 브랜드
        "brand_ar"      : brand_ar,
        "brand_en"      : brand_en,

        # ── 스펙
        "btu"           : specs["btu"],
        "ton"           : specs["ton"],
        "compressor"    : specs["compressor"],  # Inverter / On-Off / Rotary
        "ac_type"       : specs["ac_type"],     # Heat & Cool / Cooling Only / Heating Only

        # ── 가격 (SAR)
        "currency"      : p.get("currency", "SAR"),
        "price"         : price,          # 현재 실판매가 (할인 적용)
        "regular_price" : regular,        # 정가
        "is_on_sale"    : p.get("is_on_sale"),
        "discount_pct"  : disc_pct,

        # ── 재고 / 상태
        "status"        : p.get("status"),
        "is_available"  : p.get("is_available"),
        "is_out_of_stock": p.get("is_out_of_stock"),

        # ── 평점
        "rating_avg"    : (p.get("rating") or {}).get("average"),
        "rating_count"  : (p.get("rating") or {}).get("count"),

        # ── 링크
        "url"           : p.get("url"),
        "image_url"     : (p.get("image") or {}).get("url"),

        # ── 메타
        "run_date"      : run_date,
        "scraped_at"    : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ══════════════════════════════════════════════
#  카테고리 수집  ← cursor.next URL 직접 follow
# ══════════════════════════════════════════════

def fetch_category(category_ar: str, category_id: str, category_en: str, run_date: str) -> list[dict]:
    products = []
    # 첫 요청은 기본 URL
    next_url = (
        f"{BASE_URL}"
        f"?filters%5Bcategory_id%5D={category_id}"
        f"&page=1&per_page={PER_PAGE}"
    )
    page = 0

    print(f"\n{'─'*55}")
    print(f"[{category_en}]  category_id={category_id}")
    print(f"{'─'*55}")

    while next_url:
        try:
            resp = requests.get(next_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"  ⚠ 요청 오류 (page {page+1}): {e}")
            break
        except json.JSONDecodeError:
            print(f"  ⚠ JSON 파싱 실패 (page {page+1})")
            break

        items = data.get("data", [])
        if not items:
            break

        page += 1
        print(f"  page {page}: {len(items)}개 번역 중...", end=" ", flush=True)
        for item in items:
            products.append(parse_product(item, category_ar, category_en, run_date))
        print(f"완료 | 누적 {len(products)}개")

        # ✅ cursor.next URL 직접 사용 (cursor 토큰 포함)
        next_url = data.get("cursor", {}).get("next") or None
        if next_url:
            time.sleep(REQ_DELAY)

    print(f"  → 총 {len(products)}개 수집 완료")
    return products


# ══════════════════════════════════════════════
#  마스터 파일 누적 저장
# ══════════════════════════════════════════════

def save_to_master(new_df: pd.DataFrame):
    """
    najm_ac_master.xlsx에 누적 append
    동일 (product_id + run_date) 조합은 중복 저장하지 않음
    """
    if MASTER_XLSX.exists():
        existing = pd.read_excel(MASTER_XLSX, engine="openpyxl")
        combined = pd.concat([existing, new_df], ignore_index=True)
        # 같은 날짜에 같은 제품 중복 방지
        combined = combined.drop_duplicates(subset=["product_id", "run_date"], keep="last")
    else:
        combined = new_df

    combined.to_excel(MASTER_XLSX, index=False, engine="openpyxl")
    return combined


# ══════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════

def main():
    run_date = datetime.now().strftime("%Y-%m-%d")

    print("=" * 55)
    print("  Najm Store - Air Conditioner Scraper  v2.5")
    print(f"  Run date   : {run_date}")
    print(f"  Categories : {len(CATEGORIES)}")
    print(f"  Master file: {MASTER_XLSX}")
    print(f"  Translation: {'ON' if TRANSLATION_AVAILABLE else 'OFF'}")
    print("=" * 55)

    all_products: list[dict] = []

    for cat_ar, info in CATEGORIES.items():
        rows = fetch_category(
            category_ar=cat_ar,
            category_id=info["id"],
            category_en=info["name_en"],
            run_date=run_date,
        )
        all_products.extend(rows)
        time.sleep(REQ_DELAY)

    if not all_products:
        print("\n수집된 데이터가 없습니다.")
        return None

    new_df = pd.DataFrame(all_products)
    master = save_to_master(new_df)

    print(f"\n{'='*55}")
    print(f"  오늘 수집 : {len(new_df)}개")
    print(f"  마스터 총 : {len(master)}행  ({MASTER_XLSX.resolve()})")

    # 카테고리별 요약
    print(f"\n{'─'*55}")
    print("  [오늘 수집] 카테고리별 요약")
    print(f"{'─'*55}")
    summary = new_df.groupby("category_en").agg(
        products   = ("product_id", "count"),
        avg_price  = ("price",      "mean"),
        min_price  = ("price",      "min"),
        max_price  = ("price",      "max"),
        on_sale    = ("is_on_sale", "sum"),
        inverter   = ("compressor", lambda x: (x == "Inverter").sum()),
        heat_cool  = ("ac_type",    lambda x: (x == "Heat & Cool").sum()),
        cool_only  = ("ac_type",    lambda x: (x == "Cooling Only").sum()),
    ).round(2)
    print(summary.to_string())

    # 스펙 파싱 커버리지 확인
    print(f"\n{'─'*55}")
    print("  [스펙 파싱 커버리지]")
    print(f"  BTU 파싱 성공  : {new_df['btu'].notna().sum()} / {len(new_df)}")
    print(f"  Compressor     : {new_df['compressor'].notna().sum()} / {len(new_df)}")
    print(f"  AC Type        : {new_df['ac_type'].notna().sum()} / {len(new_df)}")
    print(f"  Compressor 분포: {new_df['compressor'].value_counts().to_dict()}")
    print(f"  AC Type 분포   : {new_df['ac_type'].value_counts().to_dict()}")

    return new_df


if __name__ == "__main__":
    df = main()
