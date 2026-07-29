# IR Monthly PSI 대시보드 설계 (2026-07-29)

## 목표
`or-monthly-psi`(https://shaker-dashboard.pages.dev/dashboards/or-monthly-psi/)와 동일한 스타일로 IR(Inside Retail) 8채널용 월별 PSI(Sell-Thru/Sell-Out/Stock) 대시보드를 신설한다. 기존 `ir-total`(딜러/리전/OUD추적 8탭 대시보드)은 그대로 유지하고, 새 대시보드는 별도 경로로 추가한다.

## 관계 구조
- 기존 `ir-total`: 유지. 목적이 다름(딜러/OUD 심층 분석 vs 채널/카테고리 트렌드 빠른 파악).
- 신규 `ir-monthly-psi`: `dashboards/ir-monthly-psi/` 경로에 신설.

## 채널 스킴 (8개 실채널 + IR_Others)
Al Ghanem · Al Shathri · BH · BM · Dhamin · Star Appliance · Tamkeen · Zagzoog
→ 그 외 전부(Box Appliance 포함, 2023-24 raw의 미분류 "Others" 버킷 포함) `IR_Others`로 통합.

연도별 실채널 존재 시점(원본 확인):
- 2023-24: Al Shathri/BH/BM/Dhamin/Tamkeen (5개) + IR_Others
- 2025~: + Al Ghanem/Star Appliance/Zagzoog (8개) + IR_Others
- 2026: + Box Appliance → 본 대시보드에서는 IR_Others로 접음

## 카테고리 스킴
OR-monthly-psi와 동일 7종: Split Inverter / Split On-Off / Window AC / Floor Standing AC / Cassette AC / Concealed Set / Others.
원본 raw의 `c` 필드는 2023~2025에 3종(Split/Window/Floor Standing)뿐이므로 **절대 그대로 쓰지 않고**, `model`/`code`(실 SKU)를 `shared_category.category_from_sku()`로 재분류해 7종을 복원한다.

## 데이터 아키텍처 (원본 직접 확인·교차검증 완료)

| 연도 | 소스 | 검증 결과 |
|---|---|---|
| 2023 | `unified-sellout` 임베드 JSON(`_ALL.data['2023']`) — 원 계보: 리전별 월간 PSI raw + v6 `2023 Model Mapping`/`2023 Channel Mapping` | Consolidated 롤업 대조 12월 완전일치, 그 외 5%이내(잔차=계정매칭 정밀도) |
| 2024 | `unified-sellout` 임베드 JSON(`_ALL.data['2024']`) — 원 계보: `~/2026/B2C Dealer Sell out FCST_2025_Actual_W17_rev_재작업.xlsx`(`for Bi RAW_Weekly Sell out` 시트, Col K=SO/Col O=ST, 실SKU) | **전 12개월 SO·ST 정수단위 100% 일치** |
| 2025 | `unified-sellout` 임베드 JSON(`_ALL.data['2025']`) — 동일 B2C 마스터 파일 | 2024와 동일 파이프라인(재검증 생략, 신뢰) |
| 2026 | `ir-total`(`data_ir.js`) | 기존에 영업사원 파일 100% 교차검증된 정본 |

**⚠️ 함정**: `2026/10. Automation/01. Sell Out Dashboard/2024/LG PSI - {리전}.xlsx`는 프로덕션 미사용 스냅샷(대조 시 매달 12~200% 어긋남 확인) — 소스로 쓰지 말 것.
**⚠️ 예외**: `unified-sellout`의 2026분은 `ir-total`과 최대 47% 차이 — **2026은 반드시 ir-total에서만 가져온다.**

### 필요 가공
1. 2025 주간(W1~W50+) → 월 집계(레코드 자체의 `m` 필드로 groupby, 별도 week-to-month 매핑 불필요)
2. 카테고리 재분류(`category_from_sku`)
3. 채널 8+Others 통일(Box Appliance·2023-24 Others버킷 fold-in)
4. `is_part` 부품 제외 + `ssot_fix_category_inplace` 적용
5. 부품오염 게이트(`dashboard_part_contamination_gate.py`) PASS 확인

## 화면 설계 (`dashboards/ir-monthly-psi/index.html`)
OR-monthly-psi 레이아웃 미러링:
- 상단 필터: 기간(Q1/Q2/Jan-May/H1/Full Year) + 연도(2023~2026) + **채널 멀티셀렉트**(8+Others) + **카테고리 멀티셀렉트**(7종)
  - ⚠️ OR 원본은 단일선택 버튼이지만, 이후 확정된 "모든 대시보드 필터=멀티 선택" 규칙(2026-06-23)을 신규 대시보드는 따라야 함.
- 메인 지표 토글: Sell-Thru(P) / Sell-Out(S) / Stock(I)
- 본문: 월별 트렌드 차트 + 채널별·카테고리별 브레이크다운(OR과 동일 차트 구성)
- 모델 테이블 탭: 최신월 스냅샷. `unified-sellout`의 `stock.channels[ch].models`(모델별 주간재고+WOS 신호 이미 계산됨)를 재사용해 OR 모델테이블과 동일한 LOW/OVER/OOS/SLOW 플래그 로직 적용.

## Excel 다운로드 (OR·IR 기존 컨벤션 동일 적용)
기존 `or_psi_raw_export_builder.py`/`build_ir_total_raw_pivot.py`의 확립된 패턴을 그대로 따른다.

- **출력**: 단일 시트 tidy long-format. 컬럼 `Year | Month | Channel | Category | Model code | Sell Thru | Sell Out | Stock` (+검증/정보 시트 별도).
- **정합 종속 원칙(절대)**: 엑셀의 연·채널·월·카테고리 합계는 반드시 `ir-monthly-psi` 자체 psi_data(=이 대시보드의 SSOT)와 100% 일치해야 한다. **모델 breakdown은 총계 안에서 실측만 채우고, 총계−모델합 잔차는 절대 비율배분하지 않고 `(정합조정 · 대시보드 SSOT)` 1행으로 무배분 흡수한다.**
- **결손 = 빈칸**(0으로 채우지 않음).
- **다운로드 버튼**: 대시보드 헤더에 `📥 Excel 다운로드` → 같은 폴더의 정적 xlsx로 링크.
- **자동 재생성 훅**: `ir_monthly_psi_builder.py`의 `__main__`에 배포훅(`ir_monthly_psi_pivot_deploy_hook.py`) 연결 — 대시보드 데이터 재생성 시 엑셀도 같은 폴더에 자동 재생성, 같은 커밋으로 배포.
- **검증 게이트(하드)**: KPI 합 + 카테고리별 합 둘 다 대조 후 **PASS일 때만 배포 폴더로 copy**. 실패 시 직전 정상본 유지(조용히 틀린 엑셀 배포 금지).

## 빌드 파이프라인
1. `ir_monthly_psi_builder.py` (신규): unified-sellout(2023-25) + ir-total(2026) 로드 → 위 가공 5단계 적용 → `dashboards/ir-monthly-psi/psi_data.js` 생성
2. 모델 테이블 별도 빌더(OR의 `psi_model_table.js` 패턴과 동일 분리)
3. Excel export builder + 배포훅 (위 섹션)
4. 배포 전: playwright 탭별 스크린샷, 부품오염 게이트 PASS 확인

## 남은 리스크 / 정직 고지
- 2023 데이터는 계정명 매칭 정밀도로 인한 5% 이내 잔차 있음(unified-sellout 자체 오류 아님으로 판단되나 완전 재현은 안 함).
- unified-sellout 2026분과 ir-total 간 최대 47% 불일치의 근본 원인은 미상(범위 밖, 별도 이슈로 기록만).
- 2023~2025 카테고리는 raw 3종을 SKU 재분류로 7종 복원하는 것이므로, 극소수 모델이 v6 미등록일 경우 `Others`로 폴백될 수 있음(부품게이트로 감지).

## 참고 메모리
`project_ir_unified_sellout_ssot.md` / `project_2023_stock_source.md` / `project_or_psi_raw_excel_download.md` / `project_ir_total_raw_pivot_excel.md` / `feedback_dashboard_filters_multiselect.md` / `project_part_contamination_fix.md`
