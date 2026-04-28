#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Techno Best (techno-best.com) - Air Conditioner Scraper  v1.0
Platform : Salla  |  API: https://api.salla.dev/store/v1/
Output   : TechnoBest_AC_Master.xlsx  (누적 append)

Features:
  - Salla REST API 기반 (Selenium 불필요, 빠르고 안정적)
  - 4개 AC 카테고리 순회 (Split/Window/Floor Standing/Portable)
  - 커서 기반 페이지네이션 (15개/페이지)
  - Excel 누적 저장 + 날짜별 스냅샷
  - 스크래핑 타임스탬프 포함
  - BTU → Ton 변환

Requirements:
    pip install requests pandas openpyxl
"""

import sys
import io
import re
import os
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

# Windows console UTF-8 fix
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


# ══════════════════════════════════════════════
#  설정
# ══════════════════════════════════════════════

STORE_ID   = "522237285"
BASE_URL   = "https://api.salla.dev/store/v1/products"
SCRIPT_DIR = Path(__file__).parent
MASTER_FILE = SCRIPT_DIR / "TechnoBest_AC_Master.xlsx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://techno-best.com",
    "Referer": "https://techno-best.com/",
}

CATEGORIES = {
    "Split AC":          "2123329472",
    "Window AC":         "1885762858",
    "Floor Standing AC": "1299691706",
    "Portable AC":       "1112314923",
}

REQ_DELAY = 0.3  # API 요청 간 딜레이 (초)


# ══════════════════════════════════════════════
#  BTU → Ton 변환 테이블
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

def btu_to_ton(btu):
    """BTU → Ton 변환 (범위 룩업)"""
    try:
        btu = int(float(btu))
    except (TypeError, ValueError):
        return None
    for lo, hi, ton in _BTU_TON_RANGES:
        if lo <= btu < hi:
            return ton
    return None


# ══════════════════════════════════════════════
#  브랜드 매핑 (아랍어 → 영어)
# ══════════════════════════════════════════════

BRAND_MAP = {
    "تي سي ال": "TCL",
    "ميديا": "Midea",
    "يونيكس": "Unix",
    "يونكس": "Unix",
    "جري": "Gree",
    "شارب": "Sharp",
    "دانسات": "Dansat",
    "ال جي": "LG",
    "الجي": "LG",
    "سامسونج": "Samsung",
    "هايسنس": "Hisense",
    "كاريير": "Carrier",
    "جنرال": "General",
    "جنرال سوبريم": "General Supreme",
    "سوبر جنرال": "Super General",
    "باناسونيك": "Panasonic",
    "هاير": "Haier",
    "فيشر": "Fisher",
    "كرافت": "Craft",
    "كرفت": "Craft",
    "ماندو": "Mando",
    "بيسك": "Basic",
    "نيكاي": "Nikai",
    "تكنو بيست": "Techno Best",
    "يونيون اير": "Union Air",
    "ميتسوبيشي": "Mitsubishi",
    "توشيبا": "Toshiba",
    "او جنرال": "O General",
    "اوجنرال": "O General",
    "اوكس": "AUX",
    "كولين": "Colin",
    "ويرلبول": "Whirlpool",
    "فوجي": "Fuji",
    "الزامل": "Zamil",
    "بان كول": "Pan Cool",
    "جستنج هاوس": "Westinghouse",
    "وايت وستنجهاوس": "White Westinghouse",
    "زيترست": "Zetrust",
    "امبكس": "Impex",
    "اوسكار": "Oscar",
    "هام": "Ham",
    "ام تي سي": "MTC",
    "كول سينس": "Cool Sense",
    "سوبر كلاسيك": "Super Classic",
    "يورك": "York",
    "جي في سي برو": "GVC Pro",
    "جي في سي برو GVC Pro": "GVC Pro",
    "الجزيرة للتكييف": "Al Jazeera AC",
    "كيون": "Keon",
    "سيمفوني": "Symphony",
    "اكسبير": "Xper",
    "الغدير": "Al Ghadeer",
}

# 영문 브랜드 패턴 (name에서 fallback 추출용)
_BRAND_EN_LIST = sorted([
    "TCL", "Midea", "Unix", "Gree", "Sharp", "Dansat", "LG", "Samsung",
    "Hisense", "Carrier", "General Supreme", "Super General", "General",
    "Panasonic", "Haier", "Fisher", "Craft", "Mando", "Basic", "Nikai",
    "Techno Best", "Union Air", "Mitsubishi", "Toshiba", "O General",
    "AUX", "Colin", "Whirlpool", "Fuji", "Zamil", "Pan Cool",
    "Westinghouse", "White Westinghouse", "Zetrust", "Impex", "Oscar",
    "Ham", "MTC", "Cool Sense", "Super Classic", "York", "GVC Pro",
    "Al Jazeera AC", "Al Ghadeer", "Keon", "Symphony", "Xper",
], key=len, reverse=True)


# ══════════════════════════════════════════════
#  BTU 추출
# ══════════════════════════════════════════════

_BTU_PATTERN = re.compile(r'(\d{4,6})\s*(?:وحدة|BTU|btu|Btu|وحده)', re.IGNORECASE)
_BTU_PATTERN2 = re.compile(r'(\d{2,3})[,.]?(\d{3})\s*(?:وحدة|BTU|btu|وحده)', re.IGNORECASE)

def extract_btu(name: str, description: str = "") -> int | None:
    """제품명/설명에서 BTU 추출"""
    for text in [name, description]:
        if not text:
            continue
        # "18,000" or "18000" 패턴
        m = _BTU_PATTERN2.search(text)
        if m:
            btu = int(m.group(1) + m.group(2))
            if 5000 <= btu <= 70000:
                return btu
        m = _BTU_PATTERN.search(text)
        if m:
            btu = int(m.group(1))
            if 5000 <= btu <= 70000:
                return btu
    return None


def extract_brand_en(brand_ar: str, name: str) -> str:
    """브랜드 추출: 아랍어 매핑 → 영문 이름 fallback"""
    if brand_ar:
        brand_ar_stripped = brand_ar.strip()
        if brand_ar_stripped in BRAND_MAP:
            return BRAND_MAP[brand_ar_stripped]
        # 이미 영문이면 그대로
        if all(c.isascii() or c.isspace() for c in brand_ar_stripped):
            return brand_ar_stripped

    # name에서 영문 브랜드 fallback
    if name:
        for b in _BRAND_EN_LIST:
            if b.lower() in name.lower():
                return b
    return brand_ar or "Unknown"


# ══════════════════════════════════════════════
#  Salla API 호출
# ══════════════════════════════════════════════

def fetch_category(category_name: str, category_id: str) -> list[dict]:
    """카테고리의 모든 제품을 Salla API로 수집"""
    url = f"{BASE_URL}?source=categories&filterable=1&source_value[]={category_id}&store_id={STORE_ID}"
    products = []
    page = 1

    while url:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  ❌ API 오류 (page {page}): {e}")
            break

        batch = data.get("data", [])
        products.extend(batch)
        print(f"  page {page}: {len(batch)}개 | 누적 {len(products)}개")

        # 커서 기반 페이지네이션
        cursor = data.get("cursor", {})
        url = cursor.get("next")
        page += 1

        if url:
            import time
            time.sleep(REQ_DELAY)

    return products


def fetch_product_details(product_id: str) -> dict | None:
    """개별 상품 상세 API (max_quantity 등 추가 필드)"""
    url = f"{BASE_URL}/{product_id}/details?store_id={STORE_ID}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json().get("data", {})
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════
#  메인 스크래핑
# ══════════════════════════════════════════════

def scrape_all() -> pd.DataFrame:
    """전체 AC 제품 스크래핑"""
    scrape_date = datetime.now().strftime("%Y-%m-%d")
    scrape_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_rows = []

    print("=" * 60)
    print(f"  Techno Best AC Scraper v1.0")
    print(f"  Scrape date: {scrape_date}")
    print(f"  Categories : {len(CATEGORIES)}")
    print("=" * 60)

    for cat_name, cat_id in CATEGORIES.items():
        print(f"\n{'─' * 50}")
        print(f"[{cat_name}]  category_id={cat_id}")
        print(f"{'─' * 50}")

        products = fetch_category(cat_name, cat_id)
        print(f"  → 총 {len(products)}개 수집 완료")

        for p in products:
            brand_ar = p.get("brand", {}).get("name", "") if p.get("brand") else ""
            name = p.get("name", "")
            desc = p.get("description", "")

            btu = extract_btu(name, desc)
            ton = btu_to_ton(btu)
            brand_en = extract_brand_en(brand_ar, name)

            # 할인율 계산
            regular = p.get("regular_price")
            sale = p.get("sale_price") or p.get("price")
            discount_pct = None
            if regular and sale and regular > 0 and sale < regular:
                discount_pct = round((1 - sale / regular) * 100, 1)

            row = {
                "scrape_date":       scrape_date,
                "scrape_timestamp":  scrape_time,
                "category":          cat_name,
                "product_id":        p.get("id"),
                "sku":               p.get("sku"),
                "name":              name,
                "brand_ar":          brand_ar,
                "brand_en":          brand_en,
                "BTU":               btu,
                "Ton":               ton,
                "regular_price":     regular,
                "sale_price":        sale,
                "discount_pct":      discount_pct,
                "currency":          p.get("currency", "SAR"),
                "is_on_sale":        p.get("is_on_sale"),
                "is_available":      p.get("is_available"),
                "is_out_of_stock":   p.get("is_out_of_stock"),
                "status":            p.get("status"),
                "promotion":         p.get("promotion_title", ""),
                "subtitle":          p.get("subtitle", ""),
                "url":               p.get("url"),
                "image_url":         p.get("image", {}).get("url", ""),
            }
            all_rows.append(row)

    df = pd.DataFrame(all_rows)
    print(f"\n{'=' * 60}")
    print(f"  총 수집: {len(df)}개 제품")

    # 카테고리별 요약
    if not df.empty:
        print(f"\n  카테고리별:")
        for cat, cnt in df["category"].value_counts().items():
            print(f"    {cat}: {cnt}개")

        print(f"\n  브랜드별:")
        for brand, cnt in df["brand_en"].value_counts().head(15).items():
            print(f"    {brand}: {cnt}개")

        print(f"\n  가격 범위: {df['sale_price'].min():,.0f} ~ {df['sale_price'].max():,.0f} SAR")

        on_sale = df["is_on_sale"].sum()
        print(f"  할인 중: {on_sale}개 / {len(df)}개")

    print(f"{'=' * 60}")
    return df


# ══════════════════════════════════════════════
#  Excel 저장 (누적 append)
# ══════════════════════════════════════════════

def _load_master(master: Path) -> pd.DataFrame | None:
    """Master 엑셀 읽기. 손상(BadZipFile 등)이면 스냅샷으로 재건."""
    import zipfile
    try:
        df = pd.read_excel(master)
        return df
    except (zipfile.BadZipFile, Exception) as e:
        print(f"\n  ⚠ Master 파일 손상 ({e.__class__.__name__}): {e}")
        # 손상된 파일을 백업으로 이동
        backup = master.with_suffix(".corrupted.xlsx")
        master.rename(backup)
        print(f"  → 손상 파일을 '{backup.name}'으로 이동, 스냅샷에서 재건 시도...")
        # 날짜별 스냅샷으로 재건
        snaps = sorted(SCRIPT_DIR.glob("TechnoBest_AC_2*.xlsx"))
        if snaps:
            frames = []
            for s in snaps:
                try:
                    df_s = pd.read_excel(s)
                    frames.append(df_s)
                except Exception:
                    pass
            if frames:
                df_rebuilt = pd.concat(frames, ignore_index=True)
                if "No" in df_rebuilt.columns:
                    df_rebuilt = df_rebuilt.drop(columns=["No"])
                print(f"  ✓ 스냅샷 {len(snaps)}개로 {len(df_rebuilt)}행 재건 완료")
                return df_rebuilt
        print("  → 재건 실패: 새 Master 파일 생성")
        return None


def save_to_excel(df_new: pd.DataFrame):
    """Master Excel에 누적 저장 + 스냅샷"""
    master = MASTER_FILE

    if master.exists():
        df_old = _load_master(master)
        if df_old is not None:
            # ── 중복 방지: 오늘 날짜 데이터가 이미 있으면 스킵 ────────────
            today_date = datetime.now().strftime('%Y-%m-%d')
            if 'scrape_date' in df_old.columns:
                existing_dates = pd.to_datetime(df_old['scrape_date'], errors='coerce').dt.strftime('%Y-%m-%d')
                if today_date in existing_dates.values:
                    print(f"\n  [SKIP] Today's data ({today_date}) already exists in '{master.name}'. Skipping append.")
                    ts = datetime.now().strftime("%Y%m%d_%H%M")
                    snap_path = SCRIPT_DIR / f"TechnoBest_AC_{ts}.xlsx"
                    df_snap = df_new.copy()
                    if "No" not in df_snap.columns:
                        df_snap.insert(0, "No", range(1, len(df_snap) + 1))
                    df_snap.to_excel(snap_path, index=False)
                    print(f"  📸 Snapshot saved (not appended): '{snap_path.name}'")
                    return
            # ─────────────────────────────────────────────────────────────
            if "No" in df_old.columns:
                df_old = df_old.drop(columns=["No"])
            df_combined = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_combined = df_new.copy()
        df_combined.insert(0, "No", range(1, len(df_combined) + 1))
        df_combined.to_excel(master, index=False)
        print(f"\n  📎 Appended {len(df_new)} rows → '{master.name}'")
        print(f"     Total rows: {len(df_combined)}")
    else:
        df_new.insert(0, "No", range(1, len(df_new) + 1))
        df_new.to_excel(master, index=False)
        print(f"\n  📁 Created '{master.name}' ({len(df_new)} rows)")

    # 날짜별 스냅샷
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    snap_path = SCRIPT_DIR / f"TechnoBest_AC_{ts}.xlsx"
    df_snap = df_new.copy()
    if "No" not in df_snap.columns:
        df_snap.insert(0, "No", range(1, len(df_snap) + 1))
    df_snap.to_excel(snap_path, index=False)
    print(f"  📸 Snapshot: '{snap_path.name}'")


# ══════════════════════════════════════════════
#  실행
# ══════════════════════════════════════════════

if __name__ == "__main__":
    t0 = datetime.now()

    df = scrape_all()

    if df.empty:
        print("\n  ⚠ 수집된 데이터 없음!")
        sys.exit(1)

    save_to_excel(df)

    elapsed = int((datetime.now() - t0).total_seconds())
    print(f"\n  ⏱ 소요 시간: {elapsed}초")
    print(f"  ✅ 완료!")
