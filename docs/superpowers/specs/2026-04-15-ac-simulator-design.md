# AC 판매 예측 + 가격 Gap + 공급 계획 통합 시뮬레이터 설계

Date: 2026-04-15
Status: APPROVED
Based on: /office-hours design (2026-04-15) + /superpowers-brainstorming deep dive

---

## 1. 문제 정의

LG AC 팀의 세 가지 반복 의사결정이 현재 "대시보드 보면서 직관"으로 처리됨:

| 결정 | 빈도 | 현재 방식 | 비용 |
|------|------|---------|------|
| 채널별 분기 판매 예측 | 분기마다 | 직관 + 과거 유사 시즌 참고 | 담당자마다 다른 숫자 |
| 경쟁사 대비 프로모션 가격 | 매주 | 가격 비교 보면서 감각 | 비일관적, 문서화 안 됨 |
| 채널별 공급 수량 결정 | 매월 | 재고 + 직관 | 과재고/품절 반복 |

하나의 인터랙티브 도구에서 이 세 가지를 연동해서 보여줘야 함.

---

## 2. 사용 시나리오

1. **주간 가격 리뷰 회의**: "Gree가 어젯밤 가격 내렸다 → 우리도 대응해야 하나? 얼마 내리면 얼마 팔릴까? 그러면 얼마 더 보내야 하나?" → 실시간 시뮬레이션
2. **분기 전략 수립**: Q2/Q3/Q4 시작 전 전체 채널 계획 → 모델별 예측 + 공급 계획 수립
3. **수시 애드혹**: 경쟁사 가격 변화 발생 시 즉시 임팩트 확인

---

## 3. 데이터 현황 및 특성

### 3.1 채널별 데이터 가용성 + 기준 채널

| 채널 유형 | LG 판매량 | 경쟁사 판매량 | 가격 데이터 | 역할 |
|---------|---------|------------|----------|------|
| **eXtra (OR 기준점)** | ✅ 일별, 2024~ | ✅ 전체 브랜드 | ✅ VAT 제외 실판매가 | OR 트렌드 기준 + 탄력성 도출 |
| SWS/Black Box/Al Manea | ✅ 주별, LG만 | ❌ | ✅ Price tracking (2026.3~) | eXtra 트렌드 × 채널 비율 |
| **BH (IR 기준점)** | ✅ 주별, 2023~ | ❌ | ✅ Price tracking (2026.3~) | IR 트렌드 기준 |
| BM/Tamkeen/Zagzoog 등 IR 8채널 | ✅ 주별, LG만 | ❌ | ✅ Price tracking (2026.3~) | BH 트렌드 × 채널 비율 |

**기준점 전략 (핵심):**
- **OR 기준 = eXtra**: 데이터 풍부 (일별, 전체 브랜드 가격+수량) → 탄력성 도출 + OR 트렌드 선행지표
- **IR 기준 = BH (Bin Hamoud)**: 주간 LG 판매 2023~2026, IR 채널 중 가장 대표성 높음

다른 채널들은 독립적인 시계열 모델 대신 **기준 채널의 패턴 × 채널별 스케일 팩터**로 예측:
```
other_OR_forecast = eXtra_forecast × (avg_other_OR_sales / avg_eXtra_sales)
other_IR_forecast = BH_forecast    × (avg_other_IR_sales / avg_BH_sales)
```
데이터 희소한 소규모 채널에 독립 모델을 맞추는 것보다 훨씬 강건함.
스케일 팩터는 최근 8-13주 평균으로 주간 자동 갱신.

### 3.2 데이터 소스 파일

```
1. extra-sellout/data.json (15MB)
   - 325,152 rows, compact index format
   - 차원: year, day, week, brand(30+), sub_family, type, size, region, promo, branch
   - eXtra item code → brand+sf+type+size 조합
   - 마지막 2 컬럼: 판매가격(SAR), 판매수량

2. sell-thru-progress/data.json (13MB)
   - txn: 거래 데이터 (계정별, 모델별 sell-thru)
   - remain.current: 현재 재고 (계정별)
   - pgi.current: 공급 완료 물량 (계정별)
   - open: 오픈 오더

3. price tracking dashboards (alkhunaizan-price 등 10개)
   - 10개 채널 × 전체 브랜드 × 일별 가격 (2026.3~)

4. item_master.json
   - eXtra item code (숫자) → {description, sub_family, brand, type, size}
   - LG 모델 60개 포함, 모델코드는 description에 내장

5. IR/OR channel weekly dashboards
   - 각 채널별 LG 주간 sell-out
```

---

## 4. 아키텍처

### 4.1 전체 데이터 흐름

```
[기존 파이프라인 - 변경 없음]
raw xlsx → generate_sellout_data.py → extra-sellout/data.json
stock xlsx → generate_stock_data.py → extra-mgmt/index.html
sell-thru xlsx → sell-thru generator → sell-thru-progress/data.json

[신규 파이프라인 - 3개 스크립트 추가]

generate_forecast_data.py  [NEW]
  입력: extra-sellout/data.json, bh-sellout/index.html (embedded data), 나머지 채널 HTML
  처리:
    STEP 1 - 기준 채널 예측 (독립 시계열 모델)
      - eXtra: data.json → LG 주간 판매 집계 (sub_family × type × size × week)
               item_master.json으로 모델코드 역추적 (description regex 파싱)
               ETS/Prophet으로 Q2-Q4 주간 예측 + 시즌 팩터
      - BH:    bh-sellout HTML embedded data → _ALL 객체에서 주간 sell-out 추출
               동일한 ETS/Prophet으로 Q2-Q4 예측

    STEP 2 - 나머지 채널: 기준 채널 Transfer
      - OR 채널 (SWS/BlackBox/Al Manea):
          scale_factor = avg(채널 최근 8주) / avg(eXtra 최근 8주)
          forecast = eXtra_forecast × scale_factor
      - IR 채널 (BM/Tamkeen/Zagzoog/Dhamin/Star/Al Ghanem/Al Shathri):
          scale_factor = avg(채널 최근 8주) / avg(BH 최근 8주)
          forecast = BH_forecast × scale_factor

    STEP 3 - 데이터 품질 체크
      - 스케일 팩터 계산에 사용한 주간 수 기록 (신뢰도 지표)
      - 기준 채널 예측 신뢰구간 (low/mid/high)을 다른 채널에도 동일 비율 적용
  출력: forecast_data.json

generate_simulation_params.py  [NEW]
  입력: extra-sellout/data.json (LG + 경쟁사 가격+수량)
  처리:
    - B-lite: 파라메트릭 (elasticity=-1.5 기본값, 사용자 조정 가능)
    - B-full: log-log 회귀로 모델별 탄력성 계수 계산
      ln(주간판매량) = α + β×ln(자사가격) + γ×ln(경쟁사최저가) + δ×월
    - Hold-out 4주 백테스트, R² < 0.6 경고 표시
    - 채널 조정 계수 (eXtra 탄력성 × channel_factor)
  출력: simulation_params.json

generate_supply_data.py  [NEW]
  입력: sell-thru-progress/data.json (remain.current), forecast_data.json
  처리:
    - 현재 재고 (WOS 기준): remain.current
    - WOS 목표: OR=8주, IR=24주
    - 공급 추천 = (WOS목표 × 주간예측판매량) - 현재재고
    - 음수(과재고)도 표시
  출력: supply_data.json

[프론트엔드]
extra-simulator/index.html
  - 3개 JSON 로드 (fetch)
  - 채널/모델/카테고리 필터
  - 인터랙티브 3패널
```

### 4.2 JSON 스키마

**forecast_data.json**
```json
{
  "meta": {
    "generated_at": "2026-W15",
    "anchor_OR": "extra",
    "anchor_IR": "bh",
    "channels": ["extra", "sws", "blackbox", "almanea", "bh", "bm", "tamkeen", ...],
    "forecast_horizon": ["Q2_2026", "Q3_2026", "Q4_2026"]
  },
  "by_channel": {
    "extra": {
      "APQ55GT3E4": {
        "sub_family": "FREE STANDING AIR CONDITIONER",
        "type": "Cold - Inverter",
        "size": "3.5 Ton",
        "historical_weekly": [
          {"week": "2025-W01", "qty": 45}, ...
        ],
        "forecast": {
          "Q2_2026": {"low": 180, "mid": 240, "high": 310, "weekly_rate": 18.5},
          "Q3_2026": {"low": 250, "mid": 340, "high": 430, "weekly_rate": 26.2},
          "Q4_2026": {"low": 90,  "mid": 130, "high": 170, "weekly_rate": 10.0}
        },
        "season_peak": "Q3",
        "forecast_method": "ets_direct",  // "ets_direct" | "bh_transfer" | "extra_transfer"
        "data_quality": "ok"
      }
    },
    "bm": {
      "APQ55GT3E4": {
        "forecast": {
          "Q2_2026": {"low": 22, "mid": 29, "high": 38, "weekly_rate": 2.2}
        },
        "forecast_method": "bh_transfer",
        "scale_factor": 0.12,          // BM는 BH의 약 12% 볼륨
        "scale_weeks_used": 12,        // 스케일 팩터 계산에 사용한 주간 수 (신뢰도)
        "data_quality": "ok"
      }
    }
  }
}
```

**simulation_params.json**
```json
{
  "meta": {"type": "parametric", "version": "B-lite"},
  "models": {
    "APQ55GT3E4": {
      "base_price_SAR": 2200,
      "elasticity": -1.5,
      "elasticity_r2": null,  // B-full에서 채움
      "competitor_prices": {
        "gree": {"current": 1950, "source": "extra", "date": "2026-W15"},
        "samsung": {"current": 2100, "source": "extra", "date": "2026-W15"},
        "midea": {"current": 1800, "source": "extra", "date": "2026-W15"}
      },
      "channel_factors": {
        "extra": 1.0,      // 기준 (탄력성 직접 계산)
        "sws": 0.9,        // eXtra 대비 90% (더 가격 민감, 초기값 — B-full에서 검증)
        "ir": 0.8          // eXtra 대비 80% (대리점, 대량 구매자, 덜 가격 민감, 초기값)
      },
      "recommended_price_range": {
        "lower_SAR": 1980,
        "upper_SAR": 2100,
        "rationale": "경쟁사 최저가 대비 +5~+10%"
      }
    }
  }
}
```

**supply_data.json**
```json
{
  "meta": {"wos_targets": {"OR": 8, "IR": 24}, "date": "2026-W15"},
  "by_channel": {
    "extra": {
      "APQ55GT3E4": {
        "current_stock": 320,
        "weekly_forecast_rate": 18.5,
        "target_stock_OR8": 148,
        "recommended_supply": -172,  // 음수 = 과재고, 양수 = 부족
        "status": "overstock"  // "overstock", "ok", "understock", "critical"
      }
    }
  }
}
```

---

## 5. 프론트엔드 설계

### 5.1 페이지 레이아웃

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER: AC 시뮬레이터  │  채널: [eXtra ▾]  모델: [APQ55GT3E4 ▾] │
├────────────────────┬─────────────────────────────────────────┤
│                    │                                         │
│  PANEL 1           │  PANEL 2                                │
│  수요 예측          │  가격 포지셔닝                            │
│                    │                                         │
│  과거 + Q2~Q4 밴드  │  [===●=========] 가격 슬라이더 SAR 1,800 │
│  (Line+Area chart) │  LG   ████████████ 2,200 SAR           │
│                    │  Gree ███████████  1,950 SAR  -12%     │
│  Mid: 240대/Q2     │  Midea██████████   1,800 SAR  -18%     │
│  Range: 180~310    │                                         │
│                    │  → 슬라이더 2,000으로 내리면:            │
│                    │    예측 판매량: +18% (283대/Q2)          │
├────────────────────┴─────────────────────────────────────────┤
│  PANEL 3: 공급 계획 (WOS 기반)                                │
│                                                             │
│  현재 재고: 320대  │  WOS 목표(OR8): 8×18.5=148대  │  상태: 과재고  │
│  필요 공급: -172대 (발주 보류) ← 현재 가격 기준                │
│  가격 2,000 기준 필요 공급: -42대 (여전히 과재고, 판매 촉진 우선) │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 인터랙션 흐름

```
사용자: 가격 슬라이더 조작 (2,200 → 2,000)
  ↓
JS 엔진: 새 판매량 = 현재판매량 × (2000/2200)^elasticity
         = 240 × (2000/2200)^(-1.5) = 240 × 1.18 = 283대
  ↓
Panel 1 업데이트: 예측 밴드 이동 (Mid: 283대/Q2)
Panel 2 업데이트: Gap 표시 (vs Gree: -2.5% 포지션)
Panel 3 업데이트: 필요 공급 = (8×21.8) - 320 = -145 → 여전히 과재고
  ↓
경영진: "그래도 과재고네, 그럼 먼저 재고 소진 후 프로모션 종료가 맞겠다"
```

### 5.3 컴포넌트 목록

| 컴포넌트 | 설명 | 의존성 |
|---------|------|--------|
| ChannelModelSelector | 채널/모델 드롭다운 | forecast_data.json |
| ForecastChart | Chart.js line+area | forecast_data.json |
| PriceSlider | range input + 실시간 계산 | simulation_params.json |
| CompetitorGapBar | 수평 바 차트 | simulation_params.json |
| SupplyPanel | 재고+WOS 계산 테이블 | supply_data.json |
| SimulationEngine | JS 클래스, 연산 담당 | 모두 |

---

## 6. 구현 순서 (B-lite → B-full)

### B-lite (2-3주): 기동 가능한 최소 버전

**Week 1:**
- [ ] `generate_forecast_data.py`: eXtra 한 채널 → ETS → Q2~Q4 예측
- [ ] `forecast_data.json` 스키마 확정 및 검증 (숫자가 말이 되는지 확인)
- [ ] `simulation_params.json` 기본 구조 (elasticity=-1.5 하드코딩)

**Week 2:**
- [ ] `extra-simulator/index.html`: 3패널 레이아웃
- [ ] Panel 1: 예측 차트 (Chart.js)
- [ ] Panel 2: 가격 슬라이더 + 경쟁사 Gap 바 차트
- [ ] SimulationEngine 클래스 (가격 → 수요 계산)

**Week 3:**
- [ ] `generate_supply_data.py`: sell-thru remain 데이터 연동
- [ ] Panel 3: 공급 계획 (WOS 기반 재고 상태)
- [ ] 3패널 연동 완성
- [ ] Cloudflare 배포 (`docs/dashboards/extra-simulator/`)
- [ ] `run_all.py`에 `extra_simulator` 스텝 추가

### B-full (추가 3주): 실제 데이터 기반 계수

- [ ] `generate_simulation_params.py` 업그레이드: log-log 회귀 탄력성 계산
- [ ] Hold-out 백테스트 (최근 4주)
- [ ] R² 신뢰도 표시 UI 추가
- [ ] 채널별 조정 계수 도입 (eXtra elasticity → 다른 채널 transfer)
- [ ] 13채널 전체 커버리지 확장

---

## 7. 데이터 품질 가드레일

| 조건 | 처리 |
|-----|------|
| 주간 데이터 2주 이상 공백 | 선형 보간 + "⚠ 갭 있음" 표시 |
| 주간 판매량 3σ 초과 이상치 | 제외 후 로그 |
| 모델별 26주(6개월) 미만 데이터 | "데이터 부족" 표기 |
| R² < 0.6 (B-full) | "⚠ 낮은 신뢰도" 경고 |
| forecast_data.json 생성 실패 | 이전 버전 유지, 에러 로그 |

---

## 8. 미해결 사항 (구현 전 확인 필요)

1. **sell-thru remain 데이터의 모델별 세분화**: `remain.current`가 계정별 합계인지, 모델별 재고인지 확인 필요. 모델별 재고가 없으면 Panel 3은 카테고리 수준으로 제한.

2. **eXtra data.json의 가격 컬럼**: col10/col11 중 어느 것이 실판매가격인지 `generate_sellout_data.py` 소스코드 확인 필요.

3. **item_master.json 모델코드 파싱**: description에서 모델코드 추출 regex 확정 필요 (예: `APQ55GT3E4` 추출 방식).

4. **IR 채널 sell-out 주간 집계 구조**: 9개 IR 채널 데이터의 실제 파일 위치/구조 확인 필요 (IR unified dashboard의 input format).

---

## 9. 성공 기준

**B-lite 완료 기준:**
- [ ] eXtra 채널 APQ55GT3E4, APW55GT3E4 두 모델 예측이 차트에 표시됨
- [ ] 가격 슬라이더 조작 시 예측 판매량 실시간 변화
- [ ] 경쟁사 3개(Gree, Samsung, Midea) Gap 시각화
- [ ] 현재 재고 기반 WOS 상태 표시 (과재고/정상/부족/위험)
- [ ] Cloudflare Pages URL에서 접근 가능
- [ ] `run_all.py extra` 한 번으로 전체 업데이트

**B-full 완료 기준:**
- [ ] 탄력성 계수 실데이터 기반 (R² 0.6 이상)
- [ ] 13채널 전체 적용
- [ ] 백테스트 정확도: Q2 예측 vs 실제 ±25% 이내 (모델의 80% 이상)

---

## 10. 배포 정보

- URL: `https://shaker-dashboard.pages.dev/dashboards/extra-simulator/`
- 파일: `Shaker-MD-App/docs/dashboards/extra-simulator/index.html`
- 데이터: `extra-simulator/forecast_data.json`, `simulation_params.json`, `supply_data.json`
- 배포: 기존 git push → Cloudflare 자동 배포
- 업데이트 명령: `python run_all.py extra` (또는 `▶ Update eXtra.bat`)
