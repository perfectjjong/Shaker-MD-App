# B2C 통합 Monthly PSI 대시보드 — 설계

## 배경
`ir-monthly-psi`(IR 8+1채널)와 `or-monthly-psi`(OR 5채널)가 각각 별도 Monthly PSI(Sell-Thru/Sell-Out/Stock) 대시보드로 운영 중. 경영진이 OR+IR 합산 "사우디 B2C AC 시장 전체" 관점을 한 화면에서 보고 싶어함.

기존 `b2c-unified`(`b2c_unified_dashboard_generator.py`)는 **Weekly Sell-out/Sell-thru** 통합본이며, 이번 요청은 **Monthly PSI**(Sell-Thru/Sell-Out/Stock+OUD+MOS/YoY/Model Table) 계열의 별도 통합본이다. 서로 다른 대시보드 계열이므로 신규 생성.

## 목표 & 범위
- 기존 `ir-monthly-psi`, `or-monthly-psi`는 **삭제/변경하지 않고 그대로 유지**.
- 신규 대시보드 `docs/dashboards/b2c-monthly-psi/`: OR 5채널 + IR 9채널(8개 실채널 + IR_Others) = **14채널** 통합.
- 카테고리·채널 수준은 물론 **Model Table(SKU 단위)까지 통합**.
- 탭 구성은 기존 두 대시보드와 동일하게 유지: Overview / MOS Analysis / MOS-2 Action / YoY Comparison / Channel Analysis / Data / Model Table.
- Period 필터(Q1~Q4/H1/H2/Full Year)는 최근 두 원본에 추가한 것과 동일하게 처음부터 포함.
- Channel 필터: `All` / **`OR 전체`** / **`IR 전체`** 그룹 퀵필터 추가 + 개별 14개 채널 버튼(OR=주황 테두리, IR=파랑 테두리로 색 구분).
  - 동작 명확화: `OR 전체`/`IR 전체` 클릭 = 해당 그룹의 채널 전부를 멀티셀렉트한 것과 동일 효과(그룹 내 채널 합산 표시). 기존 `All` 버튼(전 채널 합산)과 같은 동작 패턴을 그룹 단위로 축소 적용한 것.

## 데이터 아키텍처

### 카테고리 라벨은 이미 동일
IR·OR `psi_data.js` 모두 동일한 STD_CATS 라벨 사용: `Split Inverter / Split On/Off / Window AC / Floor Standing AC / Cassette / Concealed / Others`. 병합 시 카테고리 재매핑 불필요.

### 채널×카테고리 교차표 구조는 서로 다름
- IR (`ir-monthly-psi/psi_data.js`): `years[yr] = {by_cat, by_ch, by_ch_cat}` 3개 교차표. `by_cat`/`by_ch`는 `by_ch_cat`에서 파생되어 구조적으로 항상 정합.
- OR (`or-monthly-psi/psi_data.js`): `data[yr][channel][month] = {so, st, stk, by_cat:{...}}` — 채널이 최상위, 카테고리가 그 아래 중첩.

### 병합 방식 (승인됨: "완성본 병합", 원본 재파싱 아님)
신규 빌더 `b2c_monthly_psi_builder.py`가:
1. `ir-monthly-psi/psi_data.js`와 `or-monthly-psi/psi_data.js`를 **그대로 읽는다** (SAP raw나 data_ir.js를 다시 열지 않음).
2. OR의 `data[yr][channel][month].by_cat` 구조를 IR과 동일한 `by_ch_cat[channel][cat][month]` 모양으로 변환(단순 재배열, 재계산 없음).
3. 두 소스의 `by_ch_cat`을 채널 축으로 union(14채널) → `by_cat`/`by_ch`는 IR 빌더와 동일한 방식으로 `by_ch_cat`에서 파생시켜 구조적 정합 보장.
4. OUD(`oud_by_ch_cat`)도 동일하게 union.

**왜 원본 재파싱이 아니라 완성본을 합치는가**: 원본을 세 번째로 재분류하는 로직을 만들면 분류 결과가 세 곳에서 어긋날 위험이 생긴다(2026-08-09 BH 재고 override 작업 중 "대시보드 로더"와 "엑셀 export 빌더"가 같은 로직을 중복 구현해뒀다가 한쪽만 고쳐서 정합이 깨진 사고를 실제로 겪음). 이미 검증된 두 대시보드의 최종 숫자를 그대로 합치면 "통합본 합계 = 두 원본 합계"가 **오차 없이 정확히** 성립하고, 이 자체가 강력한 자동 검증 기준이 된다.

**트레이드오프 — 순서 의존**: 이 빌더는 반드시 `ir_monthly_psi_builder.py`와 `or_monthly_psi_builder.py`가 최신 상태로 실행된 *이후*에 실행해야 한다. 빌더 상단에 이 순서를 주석으로 명시하고, 두 입력 파일의 mtime을 비교해 통합 빌더 실행 시점보다 오래되었거나 없으면 경고를 출력한다(빌드를 막지는 않음 — 경고만).

### Model Table 병합
- IR (`psi_model_table.js`): flat `rows[]`, 필드 `{model, category, channel, stk, so_recent_4w, mos, flag}` — **최근 4주 평균 판매** 기준 MOS.
- OR (`psi_model_table.js`): `mos_analysis[channel][flag_bucket][]`, 필드 `{std, unified, category, btu, hc, stk, so_may, so_apr, mos, avg_so, flag}` — **최근 1개월 판매**(월 리터럴 필드명) 기준 MOS.

두 대시보드의 MOS 산출 **방법론 자체가 다름** (4주 롤링 평균 vs 최근월 단일값). 재계산해서 하나로 통일하면 세 번째 계산 로직이 추가되는 셈이라 위험 범위가 커짐.

**결정(승인됨)**: 재계산하지 않는다. 각 소스의 `mos`/`flag`/`stk` 값을 **그대로** 가져와 공통 flat 스키마로 매핑하고 (`std`→`model`, `so_may`/최신월→`so_recent`), **행마다 `basis` 필드**를 추가해 `"IR-4wk-avg"` 또는 `"OR-latest-month"`로 원산지 방법론을 명시한다. Model Table UI에 "기준" 컬럼을 추가해 사용자가 채널군별 산출 기준 차이를 알 수 있게 한다.

## UI / 화면 구성
- `docs/dashboards/b2c-monthly-psi/index.html`은 정적 셸로 직접 작성(기존 두 대시보드와 동일 정책 — generator 스크립트 없이 직접 수정이 원칙. `psi_data.js`/`psi_model_table.js`/엑셀만 빌더를 거침).
- 기존 두 대시보드의 템플릿(탭 구조, 필터 바, 차트 렌더링 로직)을 베이스로 시작해 채널 목록·필터 UI만 확장.
- 헤더에 "14 Channels · OR 5 + IR 9" 배지.
- Channel 필터: `All` / `OR 전체` / `IR 전체` 퀵필터 + 개별 14개 채널(OR=주황 테두리, IR=파랑 테두리).
- Model Table 탭: "기준" 컬럼 추가(IR 4주평균 / OR 최근월).

## 검증
- 신규 `verify_b2c_monthly_psi.py`: 통합본 `by_cat`/`by_ch`가 카테고리×월×연도 전 조합에서 **정확히** `ir-monthly-psi + or-monthly-psi` 원본 합과 일치하는지 체크(오차 0 허용 — 완성본을 그대로 합치므로 반올림 오차조차 없어야 함).
- 기존 `dashboard_part_contamination_gate.py` 재사용 가능 범위에서 함께 확인.
- Playwright로 전 탭 스크린샷 확인(사고 이력 규칙 — 렌더 깨짐은 구문 검사로 못 잡음) 후 배포.

## 배포
- git commit + push, Cloudflare 자동 배포.
- 사이트 인덱스/네비게이션에 링크 추가.

## 유지보수 노트
- 향후 OR/IR 월마감 시 재생성 순서: `ir_monthly_psi_builder.py` → `or_monthly_psi_builder.py` → `b2c_monthly_psi_builder.py`.
- 이 순서를 CLAUDE.md 트리거 테이블/handoff에 추가할지는 별도 논의(이번 스펙 범위 밖).

## 스코프 밖 (이번엔 안 함)
- OR/IR 원본(raw) 재분류 로직 신규 작성 — 안 함(완성본만 병합).
- Model Table MOS 산출 기준 통일 재계산 — 안 함(각자 원본 유지 + 기준 표기).
- `ir-monthly-psi`/`or-monthly-psi` 자체의 변경·폐기 — 안 함.
