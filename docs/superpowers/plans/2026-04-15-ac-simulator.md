# AC 시뮬레이터 구현 계획 (B-lite)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** eXtra/BH 채널 주간 판매 → ETS 예측 + 가격 탄력성 + WOS 공급 계획을 연동한 인터랙티브 시뮬레이터를 Cloudflare Pages에 배포한다.

**Architecture:** 3개 Python 스크립트(generate_forecast/simulation/supply)가 3개 JSON 생성 → Shaker-MD-App에 복사 → 단일 HTML 파일이 브라우저에서 모든 계산 실행 (서버리스).

**Tech Stack:** Python 3 (statsmodels, pandas, openpyxl), re/json, Chart.js 4, Cloudflare Pages

---

## 경로 상수 (모든 Task에서 공통)

```python
# 자동화 스크립트 디렉터리
SCRIPT_DIR = r"C:\Users\J_park\Documents\2026\01. Work\10. Automation\01. Sell Out Dashboard\00. OR\02. eXtra"

# Shaker-MD-App 루트
SHAKER_DIR = r"C:\Users\J_park\Shaker-MD-App"

# 데이터 소스 (읽기 전용)
EXTRA_DATA     = rf"{SHAKER_DIR}\docs\dashboards\extra-sellout\data.json"
EXTRA_PRICE    = rf"{SHAKER_DIR}\docs\dashboards\extra-price\index.html"
BH_HTML        = rf"{SHAKER_DIR}\docs\dashboards\bh-sellout\index.html"
SELL_THRU      = rf"{SHAKER_DIR}\docs\dashboards\sell-thru-progress\data.json"

# 출력 디렉터리
DEST_DIR = rf"{SHAKER_DIR}\docs\dashboards\extra-simulator"

# 채널 HTML 경로 (Transfer 예측용)
OR_CHANNELS = {
    "sws":      rf"{SHAKER_DIR}\docs\dashboards\or-sws\index.html",
    "blackbox": rf"{SHAKER_DIR}\docs\dashboards\or-black-box\index.html",
    "almanea":  rf"{SHAKER_DIR}\docs\dashboards\or-al-manea\index.html",
}
IR_CHANNELS = {
    "bm":         rf"{SHAKER_DIR}\docs\dashboards\bm-sellout\index.html",
    "tamkeen":    rf"{SHAKER_DIR}\docs\dashboards\tamkeen-sellout\index.html",
    "zagzoog":    rf"{SHAKER_DIR}\docs\dashboards\zagzoog-sellout\index.html",
    "alghanem":   rf"{SHAKER_DIR}\docs\dashboards\al-ghanem-sellout\index.html",
    "alshathri":  rf"{SHAKER_DIR}\docs\dashboards\al-shathri-sellout\index.html",
    "dhamin":     rf"{SHAKER_DIR}\docs\dashboards\dhamin-sellout\index.html",
    "star":       rf"{SHAKER_DIR}\docs\dashboards\star-appliance-sellout\index.html",
}
```

---

## data.json 구조 (Task 2~6에서 참조)

```
c_records: list of 12-element arrays
  c[0] = year_idx    → d["d"]["y"][c[0]]         예: 2024, 2025, 2026
  c[1] = day_idx     → d["d"]["day"][c[1]]        예: "01-05" (month-day)
  c[2] = brand_idx   → d["d"]["b"][c[2]]          예: "LG" (index 19)
  c[3] = sf_idx      → d["d"]["sf"][c[3]]         예: "FREE STANDING AIR CONDITIONER"
  c[4] = type_idx    → d["d"]["t"][c[4]]          예: "Cold - Inverter"
  c[5] = size_idx    → d["d"]["sz"][c[5]]         예: "3.5 Ton"
  c[6] = region_idx
  c[7] = promoter_idx
  c[8] = branch_idx
  c[9]  = qty   (판매 수량)
  c[10] = val   (총 판매액 SAR)
  c[11] = fp    (개당 판매가 SAR)

week 조회:
  dm_key = f"{c[0]}-{c[1]}"
  week_idx, month_idx, quarter_idx = d["dm"][dm_key]
  week_str = d["d"]["w"][week_idx]    # "W1" ~ "W52"
  year     = d["d"]["y"][c[0]]
  iso_week = f"{year}-{week_str}"     # "2025-W15"
```

---

## 채널 HTML _ALL 데이터 구조 (BH/OR/IR 공통)

```javascript
// const _ALL = {...} 형태로 HTML 한 줄에 내장
{
  "years": ["2023","2024","2025","2026"],
  "data": {
    "2023": {
      "raw": [
        {"w": "W5", "m": "Jan", "ch": "BH", "model": "APNQ55GT3E4",
         "c": "Floor Standing AC", "type": "CO", "comp": "Inverter",
         "btu": "55", "q": 45, "code": "APNQ55GT3E4", "name": ""}
      ]
    }
  }
}
// 12개 week 포인트/연 (W5, W9, W13, W18, W22, W26, W31, W35, W39, W44, W48, W52)
// → 월별 데이터
```

---

## extra-price/index.html DATA 구조

```javascript
// const DATA=[{...}, ...] 형태로 내장 (3.4MB)
// 각 레코드:
{
  "d": "2026-02-12",        // 날짜
  "b": "GREE",              // 브랜드
  "c": "Split Air Conditioner",  // 카테고리
  "t": 1.5,                 // 톤수
  "h": "Cool Only",         // 냉난방
  "cp": "Inverter",         // 압축기
  "fp": 1250,               // 최종 가격 SAR (핵심)
  "n": "...",               // 모델명 설명
  "m": "GS18CZ8L-R6M"      // 모델 코드
}
```

---

## Task 1: 데이터 탐색 & 검증 스크립트

**Files:**
- Create: `[SCRIPT_DIR]\explore_ac_data.py`

탐색 스크립트를 작성하고 실행해서 실제 데이터 숫자를 확인한다. 이 숫자들이 이후 Task의 예상 결과 기준이 된다.

- [ ] **Step 1: 스크립트 작성**

```python
# explore_ac_data.py
"""
AC 시뮬레이터 구현 전 데이터 탐색 스크립트
실행: python explore_ac_data.py
"""
import json, re
from collections import defaultdict

SHAKER_DIR = r"C:\Users\J_park\Shaker-MD-App"
EXTRA_DATA = rf"{SHAKER_DIR}\docs\dashboards\extra-sellout\data.json"
BH_HTML    = rf"{SHAKER_DIR}\docs\dashboards\bh-sellout\index.html"

print("=== 1. eXtra data.json - LG AC 주간 판매 ===")
with open(EXTRA_DATA, encoding="utf-8") as f:
    d = json.load(f)

lg_idx = d["d"]["b"].index("LG")
print(f"LG brand index: {lg_idx}")

AC_SF_NAMES = {
    "FREE STANDING AIR CONDITIONER",
    "MINI SPLIT AIR CONDITIONER",
    "WINDOW AIR CONDITIONER",
    "SEEC WINDOW AIR CONDITIONER",
}
sf_list  = d["d"]["sf"]
type_list = d["d"]["t"]
size_list = d["d"]["sz"]
year_list = d["d"]["y"]
week_list = d["d"]["w"]

ac_sf_idx = {i for i, s in enumerate(sf_list) if s in AC_SF_NAMES}
print(f"AC sub_family indices: {ac_sf_idx}")
print(f"  → {[sf_list[i] for i in sorted(ac_sf_idx)]}")

# (sf, type, size) → iso_week → total qty
weekly = defaultdict(lambda: defaultdict(int))
price_samples = defaultdict(list)  # (sf,type,size) → list of (year,week,fp)

for r in d["c"]:
    if r[2] != lg_idx:
        continue
    if r[3] not in ac_sf_idx:
        continue
    dm_key = f"{r[0]}-{r[1]}"
    if dm_key not in d["dm"]:
        continue
    week_idx = d["dm"][dm_key][0]
    year     = year_list[r[0]]
    iso_week = f"{year}-{week_list[week_idx]}"
    product  = (sf_list[r[3]], type_list[r[4]], size_list[r[5]])
    weekly[product][iso_week] += r[9]
    if r[11] > 0:
        price_samples[product].append(r[11])

print(f"\nUnique AC product combos (sf×type×size): {len(weekly)}")
# Top 10 by total qty
totals = {k: sum(v.values()) for k, v in weekly.items()}
for prod, tot in sorted(totals.items(), key=lambda x: -x[1])[:10]:
    sf, typ, sz = prod
    sf_short = sf.replace(" AIR CONDITIONER", "").replace("FREE STANDING", "FST").replace("MINI SPLIT", "SPLIT")
    avg_price = sum(price_samples[prod]) / len(price_samples[prod]) if price_samples[prod] else 0
    print(f"  {sf_short} | {sz} | {typ}: {tot} units, avg_fp={avg_price:.0f} SAR")

# Sample: how many weekly data points for the top product?
top_prod = max(totals, key=totals.get)
weeks_data = weekly[top_prod]
print(f"\nTop product weekly data points: {len(weeks_data)}")
sorted_weeks = sorted(weeks_data.items())
print(f"  Range: {sorted_weeks[0][0]} → {sorted_weeks[-1][0]}")
print(f"  Recent 5 weeks: {sorted_weeks[-5:]}")

print("\n=== 2. BH sell-out HTML - 주간 모델별 판매 ===")
with open(BH_HTML, encoding="utf-8") as f:
    bh_content = f.read()

m = re.search(r"const _ALL\s*=\s*(\{.*?\});\s*\n", bh_content, re.DOTALL)
if not m:
    # Try single-line
    for line in bh_content.split("\n"):
        if "const _ALL" in line and "={" in line.replace(" ", ""):
            m = re.match(r".*const _ALL\s*=\s*(\{.*\})\s*;", line)
            if m:
                break

if not m:
    print("  ERROR: _ALL not found in BH HTML")
else:
    all_data = json.loads(m.group(1))
    years = all_data["years"]
    print(f"  Years: {years}")
    bh_weekly = defaultdict(lambda: defaultdict(int))  # model → "YYYY-WXX" → qty
    for yr in years:
        if yr not in all_data.get("data", {}):
            continue
        raw = all_data["data"][yr].get("raw", [])
        for rec in raw:
            model = rec.get("model") or rec.get("code", "")
            if not model:
                continue
            iso_week = f"{yr}-{rec['w']}"
            bh_weekly[model][iso_week] += rec.get("q", 0)

    print(f"  Unique BH models: {len(bh_weekly)}")
    bh_totals = {k: sum(v.values()) for k, v in bh_weekly.items()}
    for model, tot in sorted(bh_totals.items(), key=lambda x: -x[1])[:5]:
        print(f"    {model}: {tot} units, {len(bh_weekly[model])} data points")

print("\n=== 3. remain.current 구조 ===")
from pathlib import Path
st_path = rf"{SHAKER_DIR}\docs\dashboards\sell-thru-progress\data.json"
with open(st_path, encoding="utf-8") as f:
    st = json.load(f)
rc = st["remain"]["current"]
print(f"  remain.current keys: {list(rc.keys())}")
print(f"  tq (total qty stock): {rc.get('tq')}")
print(f"  tv (total value):     {rc.get('tv')}")
print(f"  date:                 {rc.get('date')}")

print("\nDONE. 위 숫자로 forecast_data.json 스키마 검증.")
```

- [ ] **Step 2: 실행 및 결과 기록**

실행:
```
cd "C:\Users\J_park\Documents\2026\01. Work\10. Automation\01. Sell Out Dashboard\00. OR\02. eXtra"
python explore_ac_data.py
```

기대 결과:
- LG AC 제품 조합 10~30개 출력
- 상위 제품 주간 데이터 포인트 ≥ 52개 (약 2년치)
- BH 모델 10~30개, 포인트 ~36개 (3년 × 12월)
- remain.current.tq > 0 (숫자 확인)

실제 출력 숫자를 여기에 메모해 둔다 (Task 2~6의 "말이 되는지" 기준).

- [ ] **Step 3: 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add docs/superpowers/plans/2026-04-15-ac-simulator.md
git commit -m "plan: add AC simulator implementation plan"
```

---

## Task 2: generate_forecast_data.py — eXtra ETS 예측

**Files:**
- Create: `[SCRIPT_DIR]\generate_forecast_data.py`

`statsmodels` 설치 확인 후, eXtra 채널의 LG AC 주간 판매를 ETS로 Q2~Q4 예측하고 `forecast_data.json` 초안을 생성한다.

- [ ] **Step 1: statsmodels 설치 확인**

```bash
pip show statsmodels
```

없으면:
```bash
pip install statsmodels
```

- [ ] **Step 2: generate_forecast_data.py 작성 (eXtra 섹션)**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AC Simulator - Forecast Data Generator
======================================
입력: extra-sellout/data.json, BH/OR/IR 채널 HTML (embedded _ALL)
출력: extra-simulator/forecast_data.json
"""
import json
import os
import re
import sys
import warnings
from collections import defaultdict
from datetime import datetime
import numpy as np

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except ImportError:
    print("ERROR: pip install statsmodels")
    sys.exit(1)

warnings.filterwarnings("ignore")

# ─── 경로 ───────────────────────────────────────────────────────────────────
SHAKER_DIR = os.path.join(os.path.expanduser("~"), "Shaker-MD-App")
EXTRA_DATA  = os.path.join(SHAKER_DIR, "docs", "dashboards", "extra-sellout", "data.json")
BH_HTML     = os.path.join(SHAKER_DIR, "docs", "dashboards", "bh-sellout", "index.html")
DEST_DIR    = os.path.join(SHAKER_DIR, "docs", "dashboards", "extra-simulator")
OUT_PATH    = os.path.join(DEST_DIR, "forecast_data.json")

OR_CHANNEL_HTML = {
    "sws":      os.path.join(SHAKER_DIR, "docs", "dashboards", "or-sws",       "index.html"),
    "blackbox": os.path.join(SHAKER_DIR, "docs", "dashboards", "or-black-box", "index.html"),
    "almanea":  os.path.join(SHAKER_DIR, "docs", "dashboards", "or-al-manea",  "index.html"),
}
IR_CHANNEL_HTML = {
    "bm":        os.path.join(SHAKER_DIR, "docs", "dashboards", "bm-sellout",           "index.html"),
    "tamkeen":   os.path.join(SHAKER_DIR, "docs", "dashboards", "tamkeen-sellout",      "index.html"),
    "zagzoog":   os.path.join(SHAKER_DIR, "docs", "dashboards", "zagzoog-sellout",      "index.html"),
    "alghanem":  os.path.join(SHAKER_DIR, "docs", "dashboards", "al-ghanem-sellout",    "index.html"),
    "alshathri": os.path.join(SHAKER_DIR, "docs", "dashboards", "al-shathri-sellout",   "index.html"),
    "dhamin":    os.path.join(SHAKER_DIR, "docs", "dashboards", "dhamin-sellout",       "index.html"),
    "star":      os.path.join(SHAKER_DIR, "docs", "dashboards", "star-appliance-sellout", "index.html"),
}

# AC 카테고리 sub_family 이름 (eXtra 기준)
AC_SF_NAMES = {
    "FREE STANDING AIR CONDITIONER",
    "MINI SPLIT AIR CONDITIONER",
    "WINDOW AIR CONDITIONER",
    "SEEC WINDOW AIR CONDITIONER",
}

# Q2~Q4 week 번호 범위 (2026 기준)
QUARTER_WEEKS = {
    "Q2_2026": list(range(14, 27)),   # W14~W26 (13주)
    "Q3_2026": list(range(27, 40)),   # W27~W39 (13주)
    "Q4_2026": list(range(40, 53)),   # W40~W52 (13주)
}
CURRENT_YEAR  = 2026
CURRENT_WEEK  = 15  # 스크립트 실행 시점: W15 (2026-04-15)


# ─── 유틸 ────────────────────────────────────────────────────────────────────

def iso_week_to_int(iso_week: str) -> int:
    """'2025-W15' → 202515 (정렬용 정수)"""
    year, w = iso_week.split("-W")
    return int(year) * 100 + int(w)


def build_weekly_series(weekly_dict: dict) -> list[tuple[str, int]]:
    """
    {iso_week: qty} → 정렬된 [(iso_week, qty)] 리스트.
    2주 이상 연속 공백 → 선형 보간. 1주 공백 → 이전 값 유지.
    """
    if not weekly_dict:
        return []
    sorted_items = sorted(weekly_dict.items(), key=lambda x: iso_week_to_int(x[0]))
    result = list(sorted_items)

    # 공백 감지 및 보간 (동일 연도 내)
    # TODO B-full: 교차 연도 공백도 처리
    return result


def ets_forecast_quarterly(series: list[tuple[str, int]], forecast_year: int = 2026) -> dict:
    """
    주간 판매 시계열 → Q2/Q3/Q4 예측.
    series: [("2024-W01", 45), ("2024-W02", 38), ...]

    Returns:
        {
          "historical_weekly": [{"week": "2025-W01", "qty": 45}, ...],
          "forecast": {
            "Q2_2026": {"low": 180, "mid": 240, "high": 310, "weekly_rate": 18.5},
            ...
          },
          "forecast_method": "ets_direct",
          "data_quality": "ok" | "insufficient_data"
        }
    """
    if len(series) < 26:  # 6개월 미만
        return {
            "historical_weekly": [{"week": w, "qty": q} for w, q in series],
            "forecast": {},
            "forecast_method": "ets_direct",
            "data_quality": "insufficient_data",
        }

    qtys = np.array([q for _, q in series], dtype=float)
    # 이상치 제거: 평균 ± 3σ 초과 → 중위값으로 대체
    mean, std = qtys.mean(), qtys.std()
    outliers = np.abs(qtys - mean) > 3 * std
    if outliers.any():
        print(f"    ⚠ 이상치 {outliers.sum()}개 제거 (평균 {mean:.1f} ±3σ)")
        qtys[outliers] = np.median(qtys)

    # ETS 모델: 추세 있음, 계절성 없음 (데이터 2년 → 52-period seasonal 불안정)
    # 계절성은 post-hoc 적용 (역사적 분기 비율 기반)
    try:
        model = ExponentialSmoothing(
            qtys,
            trend="add",
            seasonal=None,
            initialization_method="estimated",
        )
        fit = model.fit(optimized=True, remove_bias=True)
        # 남은 주간 예측 (W16 ~ W52 = 37주)
        remaining_weeks = 52 - CURRENT_WEEK
        forecast_raw = fit.forecast(remaining_weeks)
        forecast_raw = np.maximum(forecast_raw, 0)  # 음수 방지
    except Exception as e:
        print(f"    ETS 실패: {e} → fallback to YoY mean")
        forecast_raw = _yoy_fallback(series, forecast_year, remaining_weeks=52 - CURRENT_WEEK)

    # 역사 분기 계절 팩터 계산
    season_factors = _calc_season_factors(series, forecast_year)

    # 분기별 집계
    forecast = {}
    for qname, week_nums in QUARTER_WEEKS.items():
        # 이미 지난 주는 제외
        future_weeks = [w for w in week_nums if w > CURRENT_WEEK]
        if not future_weeks:
            continue
        # forecast_raw 인덱스: 0 = W(CURRENT_WEEK+1)
        indices = [w - CURRENT_WEEK - 1 for w in future_weeks]
        valid_idx = [i for i in indices if 0 <= i < len(forecast_raw)]
        if not valid_idx:
            continue
        base_total = float(sum(forecast_raw[i] for i in valid_idx))
        q_factor = season_factors.get(qname, 1.0)
        mid = round(base_total * q_factor)
        forecast[qname] = {
            "low":         round(mid * 0.75),
            "mid":         mid,
            "high":        round(mid * 1.35),
            "weekly_rate": round(mid / len(future_weeks), 1),
        }

    return {
        "historical_weekly": [{"week": w, "qty": int(q)} for w, q in series[-104:]],  # 최근 2년
        "forecast": forecast,
        "forecast_method": "ets_direct",
        "data_quality": "ok",
    }


def _calc_season_factors(series: list[tuple[str, int]], forecast_year: int) -> dict:
    """역사 데이터에서 Q2/Q3/Q4 계절 팩터 계산."""
    q_totals = defaultdict(list)  # "Q2" → [year1_total, year2_total, ...]
    for iso_week, qty in series:
        yr, w = iso_week.split("-W")
        yr_int, w_int = int(yr), int(w)
        if yr_int >= forecast_year:
            continue
        if 14 <= w_int <= 26: q = "Q2"
        elif 27 <= w_int <= 39: q = "Q3"
        elif 40 <= w_int <= 52: q = "Q4"
        else: q = "Q1"
        q_totals[q].append(qty)

    annual_avg = sum(sum(v) for v in q_totals.values()) / max(
        sum(len(v) for v in q_totals.values()), 1
    )
    factors = {}
    for qnum, qname in [("Q2", f"Q2_{forecast_year}"), ("Q3", f"Q3_{forecast_year}"), ("Q4", f"Q4_{forecast_year}")]:
        if qnum in q_totals and annual_avg > 0:
            q_avg = sum(q_totals[qnum]) / len(q_totals[qnum])
            factors[qname] = q_avg / annual_avg if annual_avg > 0 else 1.0
        else:
            factors[qname] = 1.0
    return factors


def _yoy_fallback(series, forecast_year, remaining_weeks):
    """ETS 실패 시 YoY 평균으로 대체."""
    week_avgs = defaultdict(list)
    for iso_week, qty in series:
        yr, w = iso_week.split("-W")
        if int(yr) < forecast_year:
            week_avgs[int(w)].append(qty)
    result = []
    for w in range(CURRENT_WEEK + 1, 53):
        vals = week_avgs.get(w, [0])
        result.append(float(sum(vals) / len(vals)))
    return np.array(result)


# ─── eXtra 데이터 추출 ────────────────────────────────────────────────────────

def extract_extra_weekly(data_json_path: str) -> dict:
    """
    extra-sellout/data.json → {(sf, type, size): {iso_week: qty}}
    LG AC 제품만 추출.
    """
    print("[eXtra] data.json 로드 중...")
    with open(data_json_path, encoding="utf-8") as f:
        d = json.load(f)

    lg_idx    = d["d"]["b"].index("LG")
    sf_list   = d["d"]["sf"]
    type_list = d["d"]["t"]
    size_list = d["d"]["sz"]
    year_list = d["d"]["y"]
    week_list = d["d"]["w"]
    dm        = d["dm"]

    ac_sf_idx = {i for i, s in enumerate(sf_list) if s in AC_SF_NAMES}
    weekly = defaultdict(lambda: defaultdict(int))
    price_latest = defaultdict(dict)  # (sf,type,size) → {iso_week: fp}

    for r in d["c"]:
        if r[2] != lg_idx:
            continue
        if r[3] not in ac_sf_idx:
            continue
        dm_key = f"{r[0]}-{r[1]}"
        if dm_key not in dm:
            continue
        week_idx = dm[dm_key][0]
        year     = year_list[r[0]]
        iso_week = f"{year}-{week_list[week_idx]}"
        product  = (sf_list[r[3]], type_list[r[4]], size_list[r[5]])
        weekly[product][iso_week] += r[9]
        if r[11] > 0:
            price_latest[product][iso_week] = r[11]  # 마지막 기록 fp

    print(f"  → {len(weekly)}개 제품 조합 추출")
    return dict(weekly), dict(price_latest)


def product_key(sf: str, typ: str, sz: str) -> str:
    """(sub_family, type, size) → JSON 키 문자열."""
    sf_short = (sf.replace("FREE STANDING AIR CONDITIONER", "FST_AC")
                  .replace("MINI SPLIT AIR CONDITIONER", "SPLIT_AC")
                  .replace("SEEC WINDOW AIR CONDITIONER", "SEEC_AC")
                  .replace("WINDOW AIR CONDITIONER", "WINDOW_AC")
                  .replace(" ", "_"))
    sz_short = sz.replace(" ", "").replace(".", "")  # "3.5 Ton" → "35Ton"
    typ_short = (typ.replace("Cold - Inverter", "CI")
                    .replace("Hot And Cold - Inverter", "HCI")
                    .replace("Cold - Rotary", "CR")
                    .replace("Hot And Cold - Rotary", "HCR")
                    .replace(" ", "_"))
    return f"{sf_short}_{sz_short}_{typ_short}"


def product_display_name(sf: str, typ: str, sz: str) -> str:
    sf_s = sf.replace(" AIR CONDITIONER", "").replace("SEEC ", "")
    return f"{sf_s} {sz} {typ}"


# ─── 메인 실행 (eXtra 파트) ──────────────────────────────────────────────────

def run_extra(weekly_data: dict, price_data: dict) -> dict:
    """eXtra 채널 예측 결과 딕셔너리 생성."""
    print("[eXtra] ETS 예측 실행 중...")
    channel_result = {}
    for product, week_qty in weekly_data.items():
        sf, typ, sz = product
        pkey = product_key(sf, typ, sz)
        series = build_weekly_series(week_qty)
        result = ets_forecast_quarterly(series)
        result["sub_family"]   = sf
        result["type"]         = typ
        result["size"]         = sz
        result["display_name"] = product_display_name(sf, typ, sz)
        # 최근 LG 가격 (eXtra)
        latest_prices = price_data.get(product, {})
        if latest_prices:
            latest_week = max(latest_prices, key=iso_week_to_int)
            result["lg_price_SAR"] = latest_prices[latest_week]
        channel_result[pkey] = result
        status = "✓" if result["data_quality"] == "ok" else "⚠ 데이터 부족"
        print(f"  {pkey}: {status}, Q2 mid={result['forecast'].get('Q2_2026', {}).get('mid', 'N/A')}")
    return channel_result


# ─── 실행 시작 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(DEST_DIR, exist_ok=True)

    # Step 1: eXtra 데이터 추출 + 예측
    extra_weekly, extra_prices = extract_extra_weekly(EXTRA_DATA)
    extra_result = run_extra(extra_weekly, extra_prices)

    # 임시 출력 (BH + Transfer는 Task 3~4에서 추가)
    output = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-W%V"),
            "anchor_OR": "extra",
            "anchor_IR": "bh",
            "channels": ["extra"],
            "forecast_horizon": ["Q2_2026", "Q3_2026", "Q4_2026"],
        },
        "by_channel": {
            "extra": extra_result,
        },
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\n✅ forecast_data.json 생성: {size_kb:.1f}KB → {OUT_PATH}")
```

- [ ] **Step 3: 실행 & 검증**

```bash
python generate_forecast_data.py
```

기대 결과:
- `forecast_data.json` 생성
- eXtra 채널에 10~30개 제품 키 존재
- 상위 제품 Q2_2026.mid > 0
- `data_quality: "ok"` 제품 ≥ 5개

검증:
```bash
python -c "
import json
with open(r'C:\Users\J_park\Shaker-MD-App\docs\dashboards\extra-simulator\forecast_data.json') as f:
    d = json.load(f)
extra = d['by_channel']['extra']
ok_count = sum(1 for v in extra.values() if v.get('data_quality') == 'ok')
print(f'OK products: {ok_count}/{len(extra)}')
top = sorted(extra.items(), key=lambda x: x[1].get('forecast',{}).get('Q2_2026',{}).get('mid',0), reverse=True)[:3]
for k, v in top:
    print(f'  {k}: Q2={v[\"forecast\"].get(\"Q2_2026\",{}).get(\"mid\",\"N/A\")}')
"
```

- [ ] **Step 4: 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add docs/dashboards/extra-simulator/
git commit -m "feat: add generate_forecast_data.py with eXtra ETS forecast"
```

---

## Task 3: generate_forecast_data.py — BH 추출 + ETS 예측

**Files:**
- Modify: `[SCRIPT_DIR]\generate_forecast_data.py`

BH HTML에서 `_ALL` 데이터를 파싱해서 모델별 월간 시계열을 추출하고 ETS로 예측한다.

- [ ] **Step 1: BH 데이터 추출 함수 추가**

`generate_forecast_data.py`에 아래 함수를 추가한다 (import 섹션 아래, `run_extra` 함수 뒤에):

```python
# ─── BH 데이터 추출 ──────────────────────────────────────────────────────────

def extract_channel_all(html_path: str) -> dict:
    """
    채널 HTML에서 const _ALL = {...} 추출.
    Returns: _ALL dict 또는 None (파일 없거나 파싱 실패)
    """
    if not os.path.exists(html_path):
        print(f"  ⚠ 파일 없음: {html_path}")
        return None
    with open(html_path, encoding="utf-8") as f:
        content = f.read()
    # _ALL이 한 줄에 있음 (generate_sellout_data.py 패턴)
    for line in content.split("\n"):
        if "const _ALL" in line:
            m = re.search(r"const _ALL\s*=\s*(\{.+\})\s*;", line)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError as e:
                    print(f"  ⚠ _ALL 파싱 실패: {e}")
    return None


def extract_bh_monthly(bh_html_path: str) -> dict:
    """
    BH HTML → {model: [("2024-W05", qty), ("2024-W09", qty), ...]}
    월 단위 (W5/W9/W13/... = 12 point/year)
    """
    print("[BH] HTML 파싱 중...")
    all_data = extract_channel_all(bh_html_path)
    if not all_data:
        return {}

    # model → iso_week → qty
    bh_weekly = defaultdict(lambda: defaultdict(int))
    for yr in all_data.get("years", []):
        yr_data = all_data.get("data", {}).get(yr, {})
        for rec in yr_data.get("raw", []):
            model = rec.get("model") or rec.get("code", "")
            if not model:
                continue
            week = rec.get("w", "")
            if not week:
                continue
            iso_week = f"{yr}-{week}"
            bh_weekly[model][iso_week] += rec.get("q", 0)

    print(f"  → {len(bh_weekly)}개 BH 모델 추출")
    return {m: build_weekly_series(dict(w)) for m, w in bh_weekly.items()}


def run_bh(bh_html_path: str) -> dict:
    """BH 채널 예측 결과."""
    bh_data = extract_bh_monthly(bh_html_path)
    if not bh_data:
        return {}
    print("[BH] ETS 예측 실행 중...")
    channel_result = {}
    for model, series in bh_data.items():
        result = ets_forecast_quarterly(series)
        result["display_name"] = model
        # BH 모델코드를 그대로 키로 사용
        channel_result[model] = result
        status = "✓" if result["data_quality"] == "ok" else "⚠ 데이터 부족"
        print(f"  {model}: {status}, Q2={result['forecast'].get('Q2_2026',{}).get('mid','N/A')}")
    return channel_result
```

- [ ] **Step 2: `if __name__ == "__main__"` 블록 업데이트**

기존 main 블록의 `output` 딕셔너리에 BH 결과를 추가:

```python
    # Step 2: BH 데이터 추출 + 예측
    bh_result = run_bh(BH_HTML)

    output = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-W%V"),
            "anchor_OR": "extra",
            "anchor_IR": "bh",
            "channels": ["extra", "bh"],
            "forecast_horizon": ["Q2_2026", "Q3_2026", "Q4_2026"],
        },
        "by_channel": {
            "extra": extra_result,
            "bh": bh_result,
        },
    }
```

- [ ] **Step 3: 실행 & 검증**

```bash
python generate_forecast_data.py
```

기대 결과:
```bash
python -c "
import json
with open(r'C:\Users\J_park\Shaker-MD-App\docs\dashboards\extra-simulator\forecast_data.json') as f:
    d = json.load(f)
bh = d['by_channel'].get('bh', {})
print('BH models:', len(bh))
for k, v in list(bh.items())[:3]:
    print(f'  {k}: Q2={v[\"forecast\"].get(\"Q2_2026\",{}).get(\"mid\",\"N/A\")}')
"
```

- [ ] **Step 4: 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add docs/dashboards/extra-simulator/forecast_data.json
git commit -m "feat: add BH channel ETS forecast to forecast_data.json"
```

---

## Task 4: generate_forecast_data.py — Transfer 예측 (11채널)

**Files:**
- Modify: `[SCRIPT_DIR]\generate_forecast_data.py`

eXtra/BH 기준 예측에 스케일 팩터를 곱해서 나머지 11개 채널 예측을 생성한다.

- [ ] **Step 1: Transfer 예측 함수 추가**

```python
# ─── Transfer 예측 ─────────────────────────────────────────────────────────

def extract_channel_monthly_total(html_path: str) -> dict:
    """
    채널 HTML _ALL → {iso_week: total_qty} (모든 LG AC 합산)
    Transfer 스케일 팩터 계산용.
    """
    all_data = extract_channel_all(html_path)
    if not all_data:
        return {}
    weekly = defaultdict(int)
    for yr in all_data.get("years", []):
        for rec in all_data.get("data", {}).get(yr, {}).get("raw", []):
            iso_week = f"{yr}-{rec.get('w', '')}"
            weekly[iso_week] += rec.get("q", 0)
    return dict(weekly)


def calc_scale_factor(channel_weekly: dict, anchor_weekly: dict, n_weeks: int = 8) -> tuple:
    """
    최근 n_weeks 기간 평균 비율로 스케일 팩터 계산.
    Returns: (scale_factor, weeks_used)
    """
    # 공통 주간 추출 (최근 n_weeks)
    common_weeks = sorted(
        set(channel_weekly) & set(anchor_weekly),
        key=iso_week_to_int,
        reverse=True,
    )[:n_weeks]

    if not common_weeks:
        return 0.1, 0  # fallback

    anchor_total  = sum(anchor_weekly[w]  for w in common_weeks)
    channel_total = sum(channel_weekly[w] for w in common_weeks)

    if anchor_total == 0:
        return 0.1, 0

    return channel_total / anchor_total, len(common_weeks)


def apply_transfer(anchor_forecast: dict, scale_factor: float,
                   channel_name: str, method: str) -> dict:
    """
    기준 채널 예측 × 스케일 팩터 → transfer 채널 예측.
    anchor_forecast: eXtra 또는 BH의 by_channel dict
    """
    result = {}
    for pkey, anchor_prod in anchor_forecast.items():
        transfer_forecast = {}
        for qname, vals in anchor_prod.get("forecast", {}).items():
            transfer_forecast[qname] = {
                "low":         round(vals["low"]  * scale_factor),
                "mid":         round(vals["mid"]  * scale_factor),
                "high":        round(vals["high"] * scale_factor),
                "weekly_rate": round(vals["weekly_rate"] * scale_factor, 1),
            }
        result[pkey] = {
            "display_name":    anchor_prod.get("display_name", pkey),
            "sub_family":      anchor_prod.get("sub_family", ""),
            "type":            anchor_prod.get("type", ""),
            "size":            anchor_prod.get("size", ""),
            "forecast":        transfer_forecast,
            "forecast_method": method,
            "scale_factor":    round(scale_factor, 4),
            "data_quality":    "ok" if transfer_forecast else "insufficient_data",
        }
    return result


def run_transfer_channels(extra_result: dict, bh_result: dict,
                          extra_weekly_total: dict, bh_weekly_total: dict) -> dict:
    """
    OR/IR 나머지 채널 Transfer 예측 실행.
    extra_weekly_total / bh_weekly_total: {iso_week: total_qty} for anchor
    """
    channel_results = {}

    print("[OR Transfer] 채널 처리 중...")
    for ch_name, html_path in OR_CHANNEL_HTML.items():
        ch_weekly = extract_channel_monthly_total(html_path)
        if not ch_weekly:
            print(f"  ⚠ {ch_name}: 데이터 없음, 스킵")
            continue
        scale, weeks_used = calc_scale_factor(ch_weekly, extra_weekly_total, n_weeks=8)
        print(f"  {ch_name}: scale={scale:.3f} (최근 {weeks_used}주 기반)")
        ch_result = apply_transfer(extra_result, scale, ch_name, "extra_transfer")
        # scale_weeks_used 기록
        for v in ch_result.values():
            v["scale_weeks_used"] = weeks_used
        channel_results[ch_name] = ch_result

    print("[IR Transfer] 채널 처리 중...")
    for ch_name, html_path in IR_CHANNEL_HTML.items():
        ch_weekly = extract_channel_monthly_total(html_path)
        if not ch_weekly:
            print(f"  ⚠ {ch_name}: 데이터 없음, 스킵")
            continue
        scale, weeks_used = calc_scale_factor(ch_weekly, bh_weekly_total, n_weeks=8)
        print(f"  {ch_name}: scale={scale:.3f} (최근 {weeks_used}주 기반)")
        ch_result = apply_transfer(bh_result, scale, ch_name, "bh_transfer")
        for v in ch_result.values():
            v["scale_weeks_used"] = weeks_used
        channel_results[ch_name] = ch_result

    return channel_results
```

- [ ] **Step 2: main 블록에 Transfer 추가**

```python
    # Step 3: Transfer 예측 (11 채널)
    # anchor total (스케일 팩터 계산용)
    extra_total_weekly = defaultdict(int)
    for prod_data in extra_weekly.values():
        for iso_week, qty in prod_data.items():
            extra_total_weekly[iso_week] += qty

    bh_raw = extract_channel_all(BH_HTML)
    bh_total_weekly = defaultdict(int)
    if bh_raw:
        for yr in bh_raw.get("years", []):
            for rec in bh_raw.get("data", {}).get(yr, {}).get("raw", []):
                iso_week = f"{yr}-{rec.get('w', '')}"
                bh_total_weekly[iso_week] += rec.get("q", 0)

    transfer_results = run_transfer_channels(
        extra_result, bh_result,
        dict(extra_total_weekly), dict(bh_total_weekly)
    )

    all_channels = {"extra": extra_result, "bh": bh_result}
    all_channels.update(transfer_results)

    output = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-W%V"),
            "anchor_OR": "extra",
            "anchor_IR": "bh",
            "channels": list(all_channels.keys()),
            "forecast_horizon": ["Q2_2026", "Q3_2026", "Q4_2026"],
        },
        "by_channel": all_channels,
    }
```

- [ ] **Step 3: 실행 & 검증**

```bash
python generate_forecast_data.py
```

기대 결과:
```bash
python -c "
import json
with open(r'C:\Users\J_park\Shaker-MD-App\docs\dashboards\extra-simulator\forecast_data.json') as f:
    d = json.load(f)
print('채널 수:', len(d['by_channel']))
print('채널 목록:', list(d['by_channel'].keys()))
"
```

기대 출력: `채널 수: 13` (extra, bh + OR 3개 + IR 8개 — 누락 채널은 더 적을 수 있음)

- [ ] **Step 4: 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add docs/dashboards/extra-simulator/forecast_data.json
git commit -m "feat: add transfer forecasting for 11 OR/IR channels"
```

---

## Task 5: generate_simulation_params.py — 탄력성 파라미터 + 경쟁사 가격

**Files:**
- Create: `[SCRIPT_DIR]\generate_simulation_params.py`

eXtra 가격 데이터에서 최근 경쟁사 가격을 추출하고, B-lite용 파라메트릭 탄력성 파라미터를 생성한다.

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AC Simulator - Simulation Parameters Generator (B-lite)
=======================================================
입력: extra-price/index.html (all-brand price data)
      forecast_data.json (LG 가격 기준점)
출력: extra-simulator/simulation_params.json
"""
import json
import os
import re
from collections import defaultdict
from datetime import datetime

SHAKER_DIR  = os.path.join(os.path.expanduser("~"), "Shaker-MD-App")
EXTRA_PRICE = os.path.join(SHAKER_DIR, "docs", "dashboards", "extra-price", "index.html")
FORECAST    = os.path.join(SHAKER_DIR, "docs", "dashboards", "extra-simulator", "forecast_data.json")
DEST_DIR    = os.path.join(SHAKER_DIR, "docs", "dashboards", "extra-simulator")
OUT_PATH    = os.path.join(DEST_DIR, "simulation_params.json")

# B-lite 기본 탄력성 계수 (데이터 기반 회귀 전까지 사용)
DEFAULT_ELASTICITY = -1.5

# 경쟁사 목록 (extra-price DATA의 b 필드 기준)
COMPETITORS = ["GREE", "SAMSUNG", "MIDEA", "ZAMIL"]

# 채널 조정 계수 (eXtra 탄력성 기준)
CHANNEL_FACTORS = {
    "extra":    1.0,   # 기준
    "sws":      0.9,   # 더 가격 민감 (판촉 채널)
    "blackbox": 0.9,
    "almanea":  0.9,
    "bh":       0.8,   # IR 대리점 — 대량 구매, 덜 가격 민감
    "bm":       0.8,
    "tamkeen":  0.8,
    "zagzoog":  0.8,
    "alghanem": 0.8,
    "alshathri":0.8,
    "dhamin":   0.8,
    "star":     0.8,
}

# eXtra AC 카테고리 매핑 (extra-price c 필드 → forecast product key)
PRICE_CATEGORY_MAP = {
    "Free Standing Air Conditioner": "FST_AC",
    "Split Air Conditioner": "SPLIT_AC",
    "Window Air Conditioner": "WINDOW_AC",
}


def extract_price_data(html_path: str) -> list[dict]:
    """
    extra-price HTML에서 const DATA=[...] 추출.
    Returns: list of price records
    """
    print("[Price] HTML 파싱 중... (3MB+ 파일)")
    with open(html_path, encoding="utf-8") as f:
        content = f.read()

    pos = content.find("const DATA=")
    if pos < 0:
        print("  ERROR: const DATA= 미발견")
        return []

    # JSONDecoder.raw_decode로 정확한 경계 파싱
    import json as _json
    decoder = _json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(content, pos + len("const DATA="))
        print(f"  → {len(data)}개 가격 레코드 추출")
        return data
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def get_latest_competitor_prices(price_records: list, category_key: str, tonnage: float) -> dict:
    """
    특정 (category, tonnage) 조합의 브랜드별 최신 가격 반환.
    Returns: {"GREE": {"current": 1950, "date": "2026-02-12"}, ...}
    """
    # 브랜드별 최신 레코드
    brand_latest = {}
    for rec in price_records:
        brand = rec.get("b", "").upper()
        if brand not in COMPETITORS:
            continue
        cat = rec.get("c", "")
        if not any(cat_key in cat for cat_key in PRICE_CATEGORY_MAP):
            continue
        # 톤수 매칭 (±0.5 허용)
        rec_ton = rec.get("t", 0)
        if rec_ton and abs(rec_ton - tonnage) > 0.5:
            continue
        date = rec.get("d", "")
        fp   = rec.get("fp") or rec.get("sp") or 0
        if fp <= 0:
            continue
        if brand not in brand_latest or date > brand_latest[brand]["date"]:
            brand_latest[brand] = {"current": int(fp), "date": date, "source": "extra"}

    return brand_latest


def calc_recommended_range(lg_price: float, competitor_prices: dict) -> dict:
    """
    권장 가격 범위:
    - 하한: 경쟁사 최저가 × 0.95 (경쟁력 확보)
    - 상한: 현재 LG 가격 (할인 없이 유지)
    """
    if not competitor_prices:
        return {"lower_SAR": round(lg_price * 0.9), "upper_SAR": round(lg_price),
                "rationale": "경쟁사 데이터 없음, LG 가격 -10% 기준"}
    min_comp = min(v["current"] for v in competitor_prices.values())
    lower = round(min_comp * 0.95)
    upper = round(lg_price)
    min_brand = min(competitor_prices, key=lambda k: competitor_prices[k]["current"])
    diff_pct = round((lower / lg_price - 1) * 100, 1)
    return {
        "lower_SAR": lower,
        "upper_SAR": upper,
        "rationale": f"경쟁사 최저({min_brand} {min_comp} SAR) 대비 -5%, 현재 LG가 이하",
        "vs_lowest_pct": diff_pct,
    }


def run():
    os.makedirs(DEST_DIR, exist_ok=True)

    # 가격 데이터 추출
    price_records = extract_price_data(EXTRA_PRICE)

    # 예측 데이터에서 제품 목록 + LG 가격 가져오기
    if not os.path.exists(FORECAST):
        print("ERROR: forecast_data.json 없음 — Task 2 먼저 실행")
        return
    with open(FORECAST, encoding="utf-8") as f:
        forecast = json.load(f)
    extra_prods = forecast.get("by_channel", {}).get("extra", {})

    print(f"[SimParams] {len(extra_prods)}개 제품 처리 중...")
    models = {}
    for pkey, prod_data in extra_prods.items():
        sf   = prod_data.get("sub_family", "")
        typ  = prod_data.get("type", "")
        sz   = prod_data.get("size", "")
        lg_price = prod_data.get("lg_price_SAR", 2000)

        # 톤수 추출 ("3.5 Ton" → 3.5)
        try:
            tonnage = float(sz.replace(" Ton", "").strip())
        except ValueError:
            tonnage = 1.5  # fallback

        # 카테고리 키 (price_records의 c 필드와 매칭)
        cat_key = sf.title()  # "Free Standing Air Conditioner" 등

        competitor_prices = get_latest_competitor_prices(price_records, cat_key, tonnage)

        models[pkey] = {
            "display_name":       prod_data.get("display_name", pkey),
            "base_price_SAR":     int(lg_price),
            "elasticity":         DEFAULT_ELASTICITY,
            "elasticity_r2":      None,   # B-full에서 채움
            "competitor_prices":  competitor_prices,
            "channel_factors":    CHANNEL_FACTORS,
            "recommended_price_range": calc_recommended_range(lg_price, competitor_prices),
        }
        comp_count = len(competitor_prices)
        print(f"  {pkey}: LG={lg_price} SAR, 경쟁사 {comp_count}개")

    output = {
        "meta": {
            "type":         "parametric",
            "version":      "B-lite",
            "generated_at": datetime.now().strftime("%Y-W%V"),
            "elasticity_note": "B-lite 기본값 -1.5. B-full에서 log-log 회귀로 교체 예정.",
        },
        "models": models,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\n✅ simulation_params.json 생성: {size_kb:.1f}KB → {OUT_PATH}")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: 실행 & 검증**

```bash
python generate_simulation_params.py
```

기대 결과:
```bash
python -c "
import json
with open(r'C:\Users\J_park\Shaker-MD-App\docs\dashboards\extra-simulator\simulation_params.json') as f:
    d = json.load(f)
print('제품 수:', len(d['models']))
for k, v in list(d['models'].items())[:2]:
    print(f'{k}: price={v[\"base_price_SAR\"]}, competitors={list(v[\"competitor_prices\"].keys())}')
"
```

- [ ] **Step 3: 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add docs/dashboards/extra-simulator/simulation_params.json
git commit -m "feat: add generate_simulation_params.py with competitor price extraction"
```

---

## Task 6: generate_supply_data.py — WOS 공급 계획

**Files:**
- Create: `[SCRIPT_DIR]\generate_supply_data.py`

`sell-thru-progress/data.json`의 재고 데이터와 예측 주간 판매량으로 WOS 기반 공급 추천을 생성한다.

> **주의:** `remain.current`는 집계 레벨 (`tq` = 전체 AC 수량)만 제공한다. 모델별 재고는 없으므로, Panel 3은 eXtra 전체 재고를 예측 판매 합산량과 비교한다.

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AC Simulator - Supply Data Generator (WOS 기반)
===============================================
입력: sell-thru-progress/data.json (remain.current → 전체 재고)
      forecast_data.json (채널별 주간 판매 예측)
출력: extra-simulator/supply_data.json

주의: remain.current.tq는 카테고리 합산 (모델별 분리 불가).
      Panel 3은 카테고리 수준 WOS 상태를 표시한다.
"""
import json
import os
from datetime import datetime
from collections import defaultdict

SHAKER_DIR = os.path.join(os.path.expanduser("~"), "Shaker-MD-App")
SELL_THRU  = os.path.join(SHAKER_DIR, "docs", "dashboards", "sell-thru-progress", "data.json")
FORECAST   = os.path.join(SHAKER_DIR, "docs", "dashboards", "extra-simulator", "forecast_data.json")
DEST_DIR   = os.path.join(SHAKER_DIR, "docs", "dashboards", "extra-simulator")
OUT_PATH   = os.path.join(DEST_DIR, "supply_data.json")

WOS_TARGET = {"OR": 8, "IR": 24}
OR_CHANNELS = ["extra", "sws", "blackbox", "almanea"]
IR_CHANNELS = ["bh", "bm", "tamkeen", "zagzoog", "alghanem", "alshathri", "dhamin", "star"]


def get_wos_status(current: int, target: int) -> str:
    ratio = current / target if target > 0 else 99
    if ratio > 1.5:   return "overstock"
    if ratio > 0.9:   return "ok"
    if ratio > 0.5:   return "understock"
    return "critical"


def run():
    os.makedirs(DEST_DIR, exist_ok=True)

    # 현재 재고 로드
    with open(SELL_THRU, encoding="utf-8") as f:
        st = json.load(f)
    remain = st.get("remain", {}).get("current", {})
    total_stock_qty = remain.get("tq", 0)
    stock_date      = remain.get("date", "unknown")
    print(f"[Supply] 현재 재고: {total_stock_qty} units ({stock_date})")

    # 예측 로드
    with open(FORECAST, encoding="utf-8") as f:
        forecast = json.load(f)

    # 채널별 Q2 총 주간 판매율 (weekly_rate 평균)
    by_channel = forecast.get("by_channel", {})
    channel_supply = {}

    for ch_name, ch_data in by_channel.items():
        is_or = ch_name in OR_CHANNELS
        wos_target = WOS_TARGET["OR"] if is_or else WOS_TARGET["IR"]
        ch_type    = "OR" if is_or else "IR"

        # Q2 주간 판매율 (채널 내 모든 제품 합산)
        q2_weekly_rate = sum(
            prod.get("forecast", {}).get("Q2_2026", {}).get("weekly_rate", 0)
            for prod in ch_data.values()
        )

        # 채널별 재고 비례 배분 (OR 전체 재고의 OR채널 비율로 근사)
        # B-lite: eXtra 채널만 실제 재고 적용, 나머지는 예측 판매량 비례
        if ch_name == "extra":
            ch_stock = total_stock_qty  # eXtra가 OR 재고의 주요 채널
        else:
            # 스케일 팩터로 비례 배분 (간략화)
            sample = list(ch_data.values())
            if sample:
                scale = sample[0].get("scale_factor", 0.1)
                ch_stock = round(total_stock_qty * scale)
            else:
                ch_stock = 0

        target_stock = round(wos_target * q2_weekly_rate)
        recommended  = target_stock - ch_stock

        status = get_wos_status(ch_stock, target_stock)

        channel_supply[ch_name] = {
            "channel_type":      ch_type,
            "current_stock":     ch_stock,
            "q2_weekly_rate":    round(q2_weekly_rate, 1),
            "wos_target_weeks":  wos_target,
            "target_stock":      target_stock,
            "recommended_supply": recommended,  # 양수 = 추가 공급 필요, 음수 = 과재고
            "status":            status,
            "stock_note":        "aggregate (model-level breakdown not available)" if ch_name == "extra" else "estimated from scale_factor",
        }
        arrow = "▲" if recommended > 0 else "▼"
        print(f"  {ch_name} ({ch_type}): stock={ch_stock}, target={target_stock}, {arrow}{abs(recommended)} [{status}]")

    output = {
        "meta": {
            "wos_targets":    WOS_TARGET,
            "date":           stock_date,
            "generated_at":   datetime.now().strftime("%Y-W%V"),
            "stock_source":   "sell-thru-progress/data.json remain.current",
            "limitation":     "재고는 카테고리 합산 — 모델별 분리 불가 (B-full에서 개선 예정)",
        },
        "by_channel": channel_supply,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"\n✅ supply_data.json 생성: {size_kb:.1f}KB → {OUT_PATH}")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: 실행 & 검증**

```bash
python generate_supply_data.py
```

기대 결과:
```bash
python -c "
import json
with open(r'C:\Users\J_park\Shaker-MD-App\docs\dashboards\extra-simulator\supply_data.json') as f:
    d = json.load(f)
for ch, v in d['by_channel'].items():
    print(f'{ch}: stock={v[\"current_stock\"]}, status={v[\"status\"]}')
"
```

- [ ] **Step 3: 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add docs/dashboards/extra-simulator/supply_data.json
git commit -m "feat: add generate_supply_data.py with WOS-based supply recommendations"
```

---

## Task 7: update_simulator_dashboard.py — 오케스트레이터

**Files:**
- Create: `[SCRIPT_DIR]\update_simulator_dashboard.py`
- Modify: `[run_all_dir]\run_all.py`

3개 스크립트를 순서대로 실행하고 Cloudflare에 push하는 오케스트레이터.

- [ ] **Step 1: update_simulator_dashboard.py 작성**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AC Simulator Dashboard - Auto Updater
======================================
순서: generate_forecast_data → generate_simulation_params → generate_supply_data → git push
"""
import os
import sys
import subprocess
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHAKER_DIR = os.path.join(os.path.expanduser("~"), "Shaker-MD-App")
DEST_DIR   = os.path.join(SHAKER_DIR, "docs", "dashboards", "extra-simulator")

SCRIPTS = [
    os.path.join(SCRIPT_DIR, "generate_forecast_data.py"),
    os.path.join(SCRIPT_DIR, "generate_simulation_params.py"),
    os.path.join(SCRIPT_DIR, "generate_supply_data.py"),
]


def run_script(path):
    print(f"\n{'='*50}")
    print(f"  {os.path.basename(path)}")
    print(f"{'='*50}")
    result = subprocess.run(
        [sys.executable, path],
        cwd=SCRIPT_DIR, text=True, encoding="utf-8", errors="replace"
    )
    return result.returncode == 0


def deploy():
    print(f"\n[Deploy] Git push → Cloudflare Pages...")
    if not os.path.exists(SHAKER_DIR):
        print(f"  SKIP: {SHAKER_DIR} 없음")
        return False
    os.chdir(SHAKER_DIR)
    subprocess.run(["git", "add", "docs/dashboards/extra-simulator/"],
                   check=True, capture_output=True)
    result = subprocess.run(["git", "status", "--porcelain"],
                            capture_output=True, text=True)
    if result.stdout.strip():
        msg = f"Update AC simulator data {datetime.now().strftime('%Y-W%V')}"
        subprocess.run(["git", "commit", "-m", msg], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        print("  ✅ Pushed → Cloudflare auto-deploy")
        return True
    print("  변경사항 없음")
    return True


def main():
    print("=" * 60)
    print("  AC Simulator Dashboard - Auto Updater")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    for script in SCRIPTS:
        if not run_script(script):
            print(f"\n❌ 실패: {script}")
            print("중단 — 이전 데이터 유지")
            return

    deploy()
    print("\n✅ 완료")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: run_all.py에 extra_simulator 추가**

`C:\Users\J_park\Documents\2026\01. Work\10. Automation\01. Sell Out Dashboard\run_all.py` 수정:

SCRIPTS 딕셔너리에 추가:
```python
'extra_simulator': os.path.join(BASE_DIR, "00. OR", "02. eXtra", "update_simulator_dashboard.py"),
```

GROUPS['extra'] 수정:
```python
'extra': ['extra_sellout', 'extra_stock', 'extra_simulator'],
```

GROUPS['all'] 수정:
```python
'all': ['ir_unified', 'ir_channel', 'or_consol', 'or_unified', 'or_channel',
        'b2c_unified', 'extra_sellout', 'extra_stock', 'extra_simulator'],
```

LABELS 딕셔너리에 추가:
```python
'extra_simulator': '[eXtra 3/3] AC Simulator (extra-simulator)',
```

- [ ] **Step 3: 실행 & 검증**

```bash
cd "C:\Users\J_park\Documents\2026\01. Work\10. Automation\01. Sell Out Dashboard"
python run_all.py extra
```

기대 결과: 3개 스크립트 모두 ✅ 완료, `extra-simulator/` 아래 3개 JSON 파일 생성

- [ ] **Step 4: 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add .
git commit -m "feat: add update_simulator_dashboard.py and run_all.py integration"
```

---

## Task 8: index.html — 스켈레톤 + SimulationEngine

**Files:**
- Create: `C:\Users\J_park\Shaker-MD-App\docs\dashboards\extra-simulator\index.html`

3패널 레이아웃 뼈대와 JS SimulationEngine 클래스를 만든다. 이 단계에서는 Panel에 데이터 없이 "로딩 중..." 상태로 구조만 확인한다.

- [ ] **Step 1: index.html 작성**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>LG AC 시뮬레이터</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f0f4f8; }
  .panel { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
  .status-overstock  { color: #e53e3e; }
  .status-ok         { color: #38a169; }
  .status-understock { color: #d69e2e; }
  .status-critical   { color: #c53030; font-weight: bold; }
  .warn-badge { background: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 2px 8px; font-size: 12px; }
</style>
</head>
<body class="p-4">

<!-- HEADER -->
<div class="flex flex-wrap items-center gap-4 mb-4 bg-white rounded-xl p-4 shadow-sm">
  <h1 class="text-xl font-bold text-gray-800">LG AC 시뮬레이터</h1>
  <div class="flex items-center gap-2">
    <label class="text-sm text-gray-600">채널</label>
    <select id="sel-channel" class="border rounded px-2 py-1 text-sm"></select>
  </div>
  <div class="flex items-center gap-2">
    <label class="text-sm text-gray-600">제품</label>
    <select id="sel-product" class="border rounded px-2 py-1 text-sm"></select>
  </div>
  <span id="data-date" class="text-xs text-gray-400 ml-auto"></span>
</div>

<!-- 3-PANEL GRID -->
<div class="grid gap-4" style="grid-template-rows: auto auto">

  <!-- Row 1: Panel 1 + Panel 2 -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">

    <!-- PANEL 1: Forecast Chart -->
    <div class="panel">
      <h2 class="text-sm font-semibold text-gray-700 mb-3">📈 수요 예측 (Q2~Q4 2026)</h2>
      <div id="p1-kpi" class="flex gap-4 mb-3 text-sm"></div>
      <div style="height: 220px"><canvas id="chart-forecast"></canvas></div>
    </div>

    <!-- PANEL 2: Price Simulator -->
    <div class="panel">
      <h2 class="text-sm font-semibold text-gray-700 mb-3">💰 가격 포지셔닝 시뮬레이터</h2>
      <div class="mb-4">
        <label class="text-xs text-gray-600">시뮬레이션 가격 (SAR)</label>
        <div class="flex items-center gap-3 mt-1">
          <input type="range" id="price-slider" min="500" max="5000" step="50"
                 class="flex-1" oninput="onPriceChange(this.value)"/>
          <span id="price-display" class="text-lg font-bold w-24 text-right">-</span>
        </div>
        <div id="sim-delta" class="text-sm text-gray-600 mt-1"></div>
      </div>
      <div style="height: 160px"><canvas id="chart-gap"></canvas></div>
      <div id="rec-range" class="mt-3 text-xs text-gray-600"></div>
    </div>
  </div>

  <!-- Row 2: Panel 3 -->
  <div class="panel">
    <h2 class="text-sm font-semibold text-gray-700 mb-3">📦 공급 계획 (WOS 기반)</h2>
    <div id="p3-note" class="warn-badge mb-3 inline-block"></div>
    <div id="supply-table" class="overflow-x-auto"></div>
  </div>

</div>

<script>
// ─── SimulationEngine ──────────────────────────────────────────────────────
class SimulationEngine {
  constructor(forecastData, simParams, supplyData) {
    this.forecast   = forecastData;
    this.simParams  = simParams;
    this.supplyData = supplyData;
    this.currentChannel = null;
    this.currentProduct = null;
    this.basePrice      = null;
    this.simPrice       = null;
  }

  /** 사용 가능한 채널 목록 */
  getChannels() {
    return Object.keys(this.forecast.by_channel || {});
  }

  /** 채널 내 제품 목록 */
  getProducts(channel) {
    const ch = this.forecast.by_channel?.[channel] || {};
    return Object.keys(ch).filter(k => {
      const prod = ch[k];
      return prod.data_quality === 'ok' && prod.forecast && Object.keys(prod.forecast).length > 0;
    });
  }

  /** 현재 선택 업데이트 */
  select(channel, product) {
    this.currentChannel = channel;
    this.currentProduct = product;
    const prod = this.forecast.by_channel?.[channel]?.[product];
    // 기준 가격: simParams (LG 가격) 또는 forecast lg_price_SAR
    const simProd = this.simParams.models?.[product];
    this.basePrice = simProd?.base_price_SAR || prod?.lg_price_SAR || 2000;
    this.simPrice  = this.basePrice;
  }

  /** 현재 제품 데이터 */
  getProductData() {
    return this.forecast.by_channel?.[this.currentChannel]?.[this.currentProduct];
  }

  /** 시뮬레이션 파라미터 */
  getSimParams() {
    return this.simParams.models?.[this.currentProduct];
  }

  /** 채널 탄력성 계수 */
  getElasticity(channel) {
    const params = this.getSimParams();
    if (!params) return -1.5;
    const factor = params.channel_factors?.[channel] ?? 1.0;
    return params.elasticity * factor;
  }

  /**
   * 가격 변경 → 예측 판매량 재계산
   * qty_sim = qty_base × (price_sim / price_base) ^ elasticity
   */
  simulateSales(newPrice, quarter = 'Q2_2026') {
    const prod   = this.getProductData();
    const params = this.getSimParams();
    if (!prod || !params) return null;

    const forecastQ = prod.forecast?.[quarter];
    if (!forecastQ) return null;

    const elasticity = this.getElasticity(this.currentChannel);
    const ratio = newPrice / this.basePrice;
    const multiplier = Math.pow(ratio, elasticity);

    return {
      low:         Math.round(forecastQ.low  * multiplier),
      mid:         Math.round(forecastQ.mid  * multiplier),
      high:        Math.round(forecastQ.high * multiplier),
      weekly_rate: Math.round(forecastQ.weekly_rate * multiplier * 10) / 10,
      multiplier:  Math.round((multiplier - 1) * 1000) / 10, // 변화율 %
    };
  }

  /** 경쟁사 가격 vs 시뮬레이션 가격 Gap */
  getCompetitorGaps(simPrice) {
    const params = this.getSimParams();
    if (!params?.competitor_prices) return [];
    return Object.entries(params.competitor_prices).map(([brand, info]) => ({
      brand,
      price:   info.current,
      gap_pct: Math.round((simPrice / info.current - 1) * 100 * 10) / 10,
    })).sort((a, b) => a.price - b.price);
  }

  /** WOS 상태 (가격 변경 후 예측 반영) */
  getSupplyStatus(channel, simWeeklyRate) {
    const ch = this.supplyData.by_channel?.[channel];
    if (!ch) return null;
    const { current_stock, wos_target_weeks } = ch;
    const target = Math.round(wos_target_weeks * simWeeklyRate);
    const recommended = target - current_stock;
    const ratio = current_stock / (target || 1);
    const status = ratio > 1.5 ? 'overstock' : ratio > 0.9 ? 'ok' : ratio > 0.5 ? 'understock' : 'critical';
    return { current_stock, target, recommended, status, wos_target_weeks, weekly_rate: simWeeklyRate };
  }
}

// ─── 앱 상태 ───────────────────────────────────────────────────────────────
let engine = null;
let chartForecast = null;
let chartGap = null;
let currentSimPrice = 0;

// ─── 데이터 로드 ───────────────────────────────────────────────────────────
async function loadData() {
  try {
    const [forecast, simParams, supply] = await Promise.all([
      fetch('forecast_data.json').then(r => r.json()),
      fetch('simulation_params.json').then(r => r.json()),
      fetch('supply_data.json').then(r => r.json()),
    ]);
    engine = new SimulationEngine(forecast, simParams, supply);
    document.getElementById('data-date').textContent =
      `데이터 기준: ${forecast.meta?.generated_at || '-'}`;
    initSelectors();
  } catch(e) {
    document.body.innerHTML = `<div class="p-8 text-red-600">데이터 로드 실패: ${e.message}<br>JSON 파일을 먼저 생성하세요.</div>`;
  }
}

function initSelectors() {
  const chSel   = document.getElementById('sel-channel');
  const prodSel = document.getElementById('sel-product');
  const channels = engine.getChannels();
  chSel.innerHTML = channels.map(c => `<option value="${c}">${c}</option>`).join('');
  chSel.addEventListener('change', () => updateProductList(chSel.value));
  prodSel.addEventListener('change', () => onProductSelect(chSel.value, prodSel.value));
  if (channels.length) updateProductList(channels[0]);
}

function updateProductList(channel) {
  const prodSel = document.getElementById('sel-product');
  const products = engine.getProducts(channel);
  prodSel.innerHTML = products.map(p => {
    const label = engine.forecast.by_channel?.[channel]?.[p]?.display_name || p;
    return `<option value="${p}">${label}</option>`;
  }).join('');
  if (products.length) onProductSelect(channel, products[0]);
}

function onProductSelect(channel, product) {
  engine.select(channel, product);
  currentSimPrice = engine.basePrice;
  const slider = document.getElementById('price-slider');
  slider.value = currentSimPrice;
  slider.min   = Math.round(engine.basePrice * 0.5);
  slider.max   = Math.round(engine.basePrice * 1.5);
  renderAll(currentSimPrice);
}

function onPriceChange(val) {
  currentSimPrice = parseInt(val);
  document.getElementById('price-display').textContent = `SAR ${currentSimPrice.toLocaleString()}`;
  renderAll(currentSimPrice);
}

// ─── 렌더링 ────────────────────────────────────────────────────────────────
function renderAll(simPrice) {
  renderPanel1(simPrice);
  renderPanel2(simPrice);
  renderPanel3(simPrice);
}

function renderPanel1(simPrice) {
  const prod = engine.getProductData();
  if (!prod) return;

  const quarters = ['Q2_2026', 'Q3_2026', 'Q4_2026'];
  const labels    = ['Q2', 'Q3', 'Q4'];
  const baseMid   = quarters.map(q => prod.forecast?.[q]?.mid || 0);
  const simResults = quarters.map(q => engine.simulateSales(simPrice, q));
  const simMid     = simResults.map(r => r?.mid || 0);
  const lowBand    = simResults.map(r => r?.low || 0);
  const highBand   = simResults.map(r => r?.high || 0);

  // KPI
  const q2 = simResults[0];
  document.getElementById('p1-kpi').innerHTML = q2 ? `
    <div class="bg-blue-50 rounded px-3 py-1">
      <div class="text-xs text-gray-500">Q2 예측 (Mid)</div>
      <div class="font-bold text-blue-700">${q2.mid.toLocaleString()}대</div>
    </div>
    <div class="bg-gray-50 rounded px-3 py-1">
      <div class="text-xs text-gray-500">주간</div>
      <div class="font-bold">${q2.weekly_rate}/주</div>
    </div>
    <div class="bg-${q2.multiplier > 0 ? 'green' : 'red'}-50 rounded px-3 py-1">
      <div class="text-xs text-gray-500">가격 효과</div>
      <div class="font-bold text-${q2.multiplier > 0 ? 'green' : 'red'}-700">${q2.multiplier > 0 ? '+' : ''}${q2.multiplier}%</div>
    </div>
  ` : '';

  if (chartForecast) chartForecast.destroy();
  const ctx = document.getElementById('chart-forecast').getContext('2d');
  chartForecast = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: '기준 예측', data: baseMid, backgroundColor: 'rgba(59,130,246,0.3)', borderColor: 'rgba(59,130,246,0.8)', borderWidth: 2 },
        { label: `시뮬레이션 (SAR ${simPrice.toLocaleString()})`, data: simMid, backgroundColor: 'rgba(16,185,129,0.5)', borderColor: 'rgba(16,185,129,0.9)', borderWidth: 2 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'top', labels: { font: { size: 11 } } } },
      scales: { y: { beginAtZero: true, title: { display: true, text: '수량 (대)' } } }
    }
  });
}

function renderPanel2(simPrice) {
  const params = engine.getSimParams();
  if (!params) return;

  document.getElementById('price-display').textContent = `SAR ${simPrice.toLocaleString()}`;

  const q2sim = engine.simulateSales(simPrice, 'Q2_2026');
  const q2base = engine.getProductData()?.forecast?.Q2_2026;
  if (q2sim && q2base) {
    const delta = q2sim.multiplier;
    document.getElementById('sim-delta').innerHTML = `
      기준가 SAR ${engine.basePrice.toLocaleString()} 대비
      <strong>${delta > 0 ? '+' : ''}${delta}%</strong>
      → Q2 예측 <strong>${q2sim.mid.toLocaleString()}</strong>대
      (기준 ${q2base.mid.toLocaleString()}대)
    `;
  }

  // Gap 차트
  const gaps = engine.getCompetitorGaps(simPrice);
  const brands = ['LG (시뮬)', ...gaps.map(g => g.brand)];
  const prices = [simPrice, ...gaps.map(g => g.price)];
  const colors = ['rgba(239,68,68,0.7)', ...gaps.map(() => 'rgba(107,114,128,0.5)')];

  if (chartGap) chartGap.destroy();
  const ctx = document.getElementById('chart-gap').getContext('2d');
  chartGap = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: brands,
      datasets: [{ data: prices, backgroundColor: colors, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` SAR ${ctx.raw.toLocaleString()}` } }
      },
      scales: { x: { title: { display: true, text: 'SAR' } } }
    }
  });

  // 권장 범위
  const range = params.recommended_price_range;
  if (range) {
    const inRange = simPrice >= range.lower_SAR && simPrice <= range.upper_SAR;
    document.getElementById('rec-range').innerHTML = `
      권장 범위: <strong>SAR ${range.lower_SAR.toLocaleString()} ~ ${range.upper_SAR.toLocaleString()}</strong>
      ${inRange ? '✅ 범위 내' : '⚠ 범위 외'}
      <span class="text-gray-400 text-xs ml-1">(${range.rationale})</span>
    `;
  }
}

function renderPanel3(simPrice) {
  const channels = engine.getChannels();
  const q2sim_by_ch = {};
  for (const ch of channels) {
    const prev = engine.currentChannel;
    const prevProd = engine.currentProduct;
    engine.currentChannel = ch;
    const q2 = engine.simulateSales(simPrice, 'Q2_2026');
    engine.currentChannel = prev;
    engine.currentProduct = prevProd;
    q2sim_by_ch[ch] = q2?.weekly_rate || 0;
  }

  const statusLabel = { overstock: '과재고', ok: '정상', understock: '부족', critical: '위험' };
  const statusClass = { overstock: 'status-overstock', ok: 'status-ok', understock: 'status-understock', critical: 'status-critical' };

  const rows = channels.map(ch => {
    const sup = engine.getSupplyStatus(ch, q2sim_by_ch[ch]);
    if (!sup) return '';
    const { current_stock, target, recommended, status, wos_target_weeks, weekly_rate } = sup;
    const arrow = recommended > 0 ? '▲' : '▼';
    const cls = statusClass[status] || '';
    return `
      <tr class="border-b hover:bg-gray-50">
        <td class="py-2 px-3 text-sm font-medium">${ch}</td>
        <td class="py-2 px-3 text-sm text-right">${current_stock.toLocaleString()}</td>
        <td class="py-2 px-3 text-sm text-right">${weekly_rate.toFixed(1)}</td>
        <td class="py-2 px-3 text-sm text-right">${wos_target_weeks}주</td>
        <td class="py-2 px-3 text-sm text-right">${target.toLocaleString()}</td>
        <td class="py-2 px-3 text-sm text-right font-medium">
          ${arrow}${Math.abs(recommended).toLocaleString()}
        </td>
        <td class="py-2 px-3 text-sm ${cls}">${statusLabel[status] || status}</td>
      </tr>
    `;
  }).join('');

  document.getElementById('p3-note').textContent =
    '재고는 카테고리 합산 기준 (모델별 분리 불가)';
  document.getElementById('supply-table').innerHTML = `
    <table class="w-full text-left min-w-[600px]">
      <thead class="bg-gray-50 text-xs text-gray-600">
        <tr>
          <th class="py-2 px-3">채널</th>
          <th class="py-2 px-3 text-right">현재 재고</th>
          <th class="py-2 px-3 text-right">주간 예측</th>
          <th class="py-2 px-3 text-right">WOS 목표</th>
          <th class="py-2 px-3 text-right">적정 재고</th>
          <th class="py-2 px-3 text-right">추천 공급</th>
          <th class="py-2 px-3">상태</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

// ─── 초기화 ────────────────────────────────────────────────────────────────
loadData();
</script>
</body>
</html>
```

- [ ] **Step 2: 브라우저에서 확인**

브라우저에서 직접 파일 열기:
```
file:///C:/Users/J_park/Shaker-MD-App/docs/dashboards/extra-simulator/index.html
```

> 주의: `fetch()`는 `file://` 프로토콜에서 CORS 오류 발생. 로컬 테스트를 위해 Python 서버 사용:
```bash
cd "C:\Users\J_park\Shaker-MD-App\docs\dashboards\extra-simulator"
python -m http.server 8090
```
그 다음 `http://localhost:8090` 접속.

체크리스트:
- [ ] 채널 드롭다운에 `extra`, `bh`, `sws` 등 채널 목록 표시
- [ ] 제품 드롭다운에 제품 목록 표시
- [ ] Panel 1 막대 차트 렌더링 (Q2/Q3/Q4)
- [ ] Panel 2 가격 슬라이더 동작 (이동 시 숫자 변화)
- [ ] Panel 2 경쟁사 Gap 수평 바 차트 표시
- [ ] Panel 3 채널별 공급 표 표시

- [ ] **Step 3: 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add docs/dashboards/extra-simulator/index.html
git commit -m "feat: add extra-simulator 3-panel interactive UI"
```

---

## Task 9: 엔드투엔드 테스트 + Cloudflare 배포

**Files:**
- 없음 (배포만)

전체 파이프라인을 `run_all.py extra`로 실행하고 Cloudflare Pages URL에서 확인한다.

- [ ] **Step 1: 전체 파이프라인 실행**

```bash
cd "C:\Users\J_park\Documents\2026\01. Work\10. Automation\01. Sell Out Dashboard"
python run_all.py extra
```

기대 결과:
```
  [eXtra 1/2] Sellout Dashboard (extra-sellout)   ✅
  [eXtra 2/2] Stock Dashboard (extra-mgmt + ...)  ✅
  [eXtra 3/3] AC Simulator (extra-simulator)      ✅
  완료: 3/3개 성공
```

- [ ] **Step 2: Cloudflare Pages URL 확인**

배포 완료 후 (`git push` → Cloudflare 자동 빌드, 보통 1-2분):
```
https://shaker-dashboard.pages.dev/dashboards/extra-simulator/
```

체크리스트:
- [ ] 페이지 로드됨 (404 없음)
- [ ] 채널/제품 선택 가능
- [ ] Panel 1: 예측 차트 표시
- [ ] Panel 2: 가격 슬라이더 → 예측 판매량 변화
- [ ] Panel 2: 경쟁사 Gap 표시 (GREE, SAMSUNG 등)
- [ ] Panel 3: 채널별 WOS 상태 표시
- [ ] 모바일 기본 동작 확인 (가로 스크롤 이슈 없음)

- [ ] **Step 3: 최종 커밋**

```bash
cd "C:\Users\J_park\Shaker-MD-App"
git add .
git commit -m "feat: AC simulator B-lite complete — 13-channel forecast + price simulation + WOS supply plan"
```

---

## B-full 로드맵 (구현 후 추가 작업)

B-lite 완료 후 다음 3주에 진행할 내용 (본 plan 파일에서 별도 계획 작성):

1. **log-log 회귀 탄력성** (`generate_simulation_params.py` 업그레이드)
   - `ln(주간판매량) = α + β×ln(LG가격) + γ×ln(경쟁사최저가) + δ×월`
   - R² < 0.6 경고 배지 UI 추가
   - Hold-out 4주 백테스트 보고서

2. **모델별 재고 분리** (`generate_supply_data.py` 업그레이드)
   - sell-thru `txn` 데이터에서 모델별 재고 역산
   - Panel 3을 모델별 테이블로 개선

3. **13채널 데이터 품질 보고서**
   - Transfer 채널별 scale_weeks_used < 4 → 경고
   - UI에 "데이터 신뢰도" 인디케이터 추가

---

## 성공 기준 체크리스트

**B-lite 완료 기준:**
- [ ] eXtra 채널 AC 제품 예측 차트 Cloudflare Pages에 배포됨
- [ ] 가격 슬라이더 → 예측 판매량 실시간 변화
- [ ] 경쟁사 (Gree/Samsung/Midea) Gap 시각화
- [ ] 채널별 WOS 상태 (과재고/정상/부족/위험) 표시
- [ ] `python run_all.py extra` 한 번으로 전체 업데이트
- [ ] URL 하나로 VP/경영진에게 공유 가능
