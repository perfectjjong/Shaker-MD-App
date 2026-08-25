# Sell-Thru SQLite 이관 (2단계) — 설계 문서

- 날짜: 2026-08-25
- 상태: 초안 (형님 검토 대기)
- 대상: Sell-Thru 대시보드 파이프라인의 데이터 계층 (거래 / OUD / AR / 수금 / SO 파이프라인)
- 실행 위치: OCI 서버 (`~/2026/10. Automation/00. Sell Thru Dashboard/`)
- 선행: 1단계 Price Tracking 이관 (PR #25, 완료) — 동일한 패턴 재사용
- 범위: **저장 계층만.** 팀 분류·수량 보정 등 비즈니스 규칙과 대시보드 UI는 변경 없음.

## 1. 배경 / 현황

### 1.1 현재 파이프라인 (`refresh_dashboard.py`, 2,716줄)

```
[SAP 추출 수기 다운로드]                [refresh_dashboard.py]              [출력]
연도별 Raw xlsx (2024/25/26) ──┐
00. Daily Sell Thru (일일)   ──┤   → 파싱·팀분류·수량보정·계정통합 →   Sell_Thru_Dashboard_Data.xlsx
Classification / Dealer Map  ──┤      (.cache/*.pkl 캐시)               index.html + data.json(14MB)
OUD / AR / 수금 / PGI·잔여·오픈 ──┘                                      → docs/dashboards/sell-thru-progress/
```

- **거래**: 연도별 Raw xlsx는 SAP 빌링 추출본(행당 101+열, 인보이스 라인 단위). 대시보드에는 42,764행(2024~현재)이 일×계정×카테고리로 집계돼 `data.json`의 `txn` 배열로 인라인.
- **스냅샷류**: OUD(미출고 주문), AR/연체(에이징), 수금(MTD/YTD), PGI·잔여·오픈 SO가 각각 날짜별 스냅샷 파일로 쌓이고, 파이프라인이 매번 전 파일을 재파싱.
- **비즈니스 규칙이 코드에 하드코딩**: `TEAM_OVERRIDE`, `SME_EMPLOYEES`, OR 5채널/IR 8채널 ID, `HALF_QTY_CATS`/`ZERO_QTY_CATS`, `MATERIAL_CAT_OVERRIDE`, `ACCOUNT_ALIAS`(Bin Momen 4개 ID 통합 등).

### 1.2 문제점

1. **원천이 전부 서버 로컬 xlsx** — git 미추적. 서버 유실 = 3개년 거래 이력 유실 (백업은 코드만 존재).
2. **14MB data.json** — 전체 이력을 브라우저에 인라인 전송. 모바일에서 무겁고, 커질수록 악화.
3. **매 실행 전체 재파싱** — .pkl 캐시로 완화했지만, 스냅샷 파일 수백 개를 매번 순회하는 구조.
4. **규칙 변경 시 소급 불가** — TEAM_OVERRIDE를 고치면 다음 빌드부터만 반영. 과거 데이터에 새 규칙을 재적용하려면 원본 xlsx 전체 재파싱이 유일한 방법.
5. **조회 불가** — "Bin Momen의 월별 매출 vs AR 잔액 추이" 같은 질의를 하려면 대시보드를 열거나 pandas 코드를 짜야 함.
6. **가격 DB와 결합 불가** — 1단계에서 만든 `price_data.db`(가격 인하)와 셀스루 반응을 교차 분석할 접점이 없음.

## 2. 목표 / 비목표

### 목표

- 거래(인보이스 라인)와 스냅샷류(OUD/AR/수금/SO 파이프라인)를 **`sell_thru.db`** 로 통합
- **원본 필드와 파생 필드를 분리 저장** — 규칙(팀/카테고리/수량 보정)이 바뀌면 원본에서 SQL로 소급 재파생 가능
- 3개년 백필 + 일일 병행 적재 (1단계와 동일한 검증 절차)
- `data.json`을 DB 쿼리 산출물로 전환할 기반 마련 (14MB → 필요 범위만)

### 비목표

- 비즈니스 규칙 변경 (분류 로직·수량 보정은 현행 유지, 저장 위치만 이동 검토)
- 대시보드 UI 변경
- unified_psi / RSM 포캐스트 / IR Target 이관 (소규모 파라미터성 — JSON 유지)
- SAP 직접 연동 (수기 다운로드 → Daily 폴더 투입 프로세스는 그대로)

## 3. 아키텍처

```
[SAP 추출 xlsx들] ──(기존 그대로)──> refresh_dashboard.py 파싱 단계
                                          │
                                          ▼
                          [NEW] st_db.persist(...)  ← 파싱 직후 프레임을 UPSERT
                                          │
                                          ▼
                              sell_thru.db (SQLite, WAL)
                              ├─ 거래: accounts / transactions
                              ├─ 스냅샷: oud / ar / collection / so_pipeline
                              └─ 규칙: account_aliases / team_overrides (Phase B)
                                          │
                       (Phase 3) data.json·Excel을 DB 쿼리로 생성 (기간 축소)
```

**핵심 결정 (1단계 패턴 계승 + 2가지 차이):**

- **D1. 파서 재사용, 적재는 후처리** — `refresh_dashboard.py`의 검증된 파싱·분류 로직을 그대로 쓰고, 파싱 완료 시점의 DataFrame을 DB에 UPSERT하는 훅만 추가. 별도 ETL 프로세스를 만들지 않는다 (가격 추적과 달리 파서가 단일 스크립트에 집중돼 있어 훅 방식이 더 단순).
- **D2. 원본+파생 이중 저장** — 거래 행에 SAP 원본 값(고객ID, 원본 카테고리 `product_hierarchy`, 자재코드, 직원번호)과 파생 값(team, category, 보정 qty)을 나란히 저장. 규칙 변경 시 `UPDATE ... FROM` 한 번으로 소급 적용 — xlsx 재파싱 불필요. *(1단계에는 없던 요구 — 가격은 원본=파생이지만 셀스루는 분류 규칙이 자주 바뀜: 2026-05-02 TEAM_OVERRIDE 2건 추가 등)*
- **D3. 별도 파일** — `sell_thru.db`. 가격 DB(`price_data.db`)·운영 DB와 분리, 필요 시 ATTACH로 교차 조회. 금액·채권 데이터이므로 파일 권한 600.
- **D4. 스냅샷은 (snapshot_date × account) 그레인으로 정규화** — 현재 JSON의 current/prev/월말 배열 구조를 전부 커버하면서, 임의 시점 비교("6월 말 vs 8월 말 AR")가 가능해짐.

## 4. 스키마 설계 (DDL 요지)

```sql
-- 계정 마스터 (data.json 'master' 2,700행 대응)
CREATE TABLE accounts (
    account_id   TEXT PRIMARY KEY,          -- SAP Payer ID (normalize_id 적용)
    name         TEXT NOT NULL,
    team         TEXT,                      -- 파생: OR/IR/OR_Others/IR_Others/SME/Projects/...
    status       TEXT,                      -- Active / Need to re-active / ...
    classification TEXT,                    -- IR-X 등 원본 분류
    first_txn    TEXT, last_txn TEXT
);

-- 계정 통합 (ACCOUNT_ALIAS를 코드 → 데이터로)
CREATE TABLE account_aliases (
    alias_id     TEXT PRIMARY KEY,          -- 통합 전 ID
    canonical_id TEXT NOT NULL REFERENCES accounts(account_id)
);

-- 거래 (인보이스 라인 그레인 — 현 data.json 'txn'보다 세밀)
CREATE TABLE transactions (
    id           INTEGER PRIMARY KEY,
    inv_date     TEXT NOT NULL,             -- 'YYYY-MM-DD'
    account_id   TEXT NOT NULL,             -- 원본 (alias 통합 전)
    account_id_c TEXT NOT NULL,             -- 파생: canonical
    material     TEXT,                      -- 자재코드 (원본)
    raw_category TEXT,                      -- product hierarchy (원본, r[77])
    category     TEXT,                      -- 파생: map_category + MATERIAL_CAT_OVERRIDE
    emp_no       TEXT,                      -- 영업사원 번호 (원본, SME 판별 근거)
    raw_class    TEXT,                      -- classification 컬럼 (원본, r[98])
    team         TEXT,                      -- 파생: override→SME→classification 캐스케이드
    value        REAL NOT NULL,
    qty_raw      INTEGER,                   -- 원본 수량
    qty          INTEGER,                   -- 파생: HALF/ZERO 보정 후
    src_year     INTEGER NOT NULL,          -- 어느 Raw 파일에서 왔는지 (2024/2025/2026)
    UNIQUE (inv_date, account_id, material, value, qty_raw) ON CONFLICT IGNORE  -- 중복 재적재 방지 키 (§8 리스크 참조)
);
CREATE INDEX idx_txn_date ON transactions (inv_date);
CREATE INDEX idx_txn_acct ON transactions (account_id_c, inv_date);

-- 스냅샷류: 공통 그레인 = 스냅샷일 × 계정
CREATE TABLE oud_snapshots (        -- 미출고 주문 (카테고리 분해 포함)
    snapshot_date TEXT NOT NULL, account_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',      -- '' = 계정 합계
    value REAL, qty REAL,
    UNIQUE (snapshot_date, account_id, category) ON CONFLICT REPLACE
);
CREATE TABLE ar_snapshots (         -- AR 잔액/연체 (credit days 기반 계산 결과)
    snapshot_date TEXT NOT NULL, account_id TEXT NOT NULL,
    balance REAL, overdue REAL, credit_days INTEGER,
    UNIQUE (snapshot_date, account_id) ON CONFLICT REPLACE
);
CREATE TABLE collection_snapshots ( -- 수금
    snapshot_date TEXT NOT NULL, account_id TEXT NOT NULL,
    mtd REAL, ytd REAL,
    UNIQUE (snapshot_date, account_id) ON CONFLICT REPLACE
);
CREATE TABLE so_pipeline_snapshots ( -- PGI / 잔여 / 오픈 SO
    snapshot_date TEXT NOT NULL, kind TEXT NOT NULL,  -- 'pgi' | 'remain' | 'open'
    account_id TEXT NOT NULL, value REAL, qty REAL,
    UNIQUE (snapshot_date, kind, account_id) ON CONFLICT REPLACE
);
-- + schema_migrations (1단계와 동일)
```

**스키마 결정 근거:**

- 거래를 **일×계정×카테고리 집계가 아닌 인보이스 라인**으로 저장 — 현재 42,764행짜리 `txn`은 이 테이블의 GROUP BY 뷰로 재현 가능하고, 자재 단위 분석(어떤 모델이 팔렸나)이 처음으로 가능해짐. 가격 DB의 SKU와 자재코드 매핑이 생기면 "가격 인하 → 판매 반응" 교차 분석의 접점.
- `account_id` vs `account_id_c` 분리 — Bin Momen처럼 ID 4개가 한 딜러인 케이스를 데이터로 관리. 새 통합이 생기면 `account_aliases`에 1행 추가 + 재파생.
- 스냅샷 테이블에 current/prev 개념이 없음 — "최신 2개"는 쿼리(`ORDER BY snapshot_date DESC LIMIT 2`)로 해결. 월말 스냅샷 배열(`oud_monthly` 등)도 동일.

## 5. 소스 → 테이블 매핑

| 소스 (서버 로컬) | 파서 (기존 함수) | 대상 테이블 |
|---|---|---|
| `00. Raw Data/0X. {연도}/... Raw data.xlsx` ×3 | `load_2024` / `load_raw_2025_2026` | `transactions` (백필) |
| `02. 2026/00. Daily Sell Thru/` 일일 파일 | (2026 raw에 병합되는 기존 흐름) | `transactions` (일일) |
| `01. Classfication.xlsx`, `02. 2026 Dealer Mapping.xlsx` | `load_classification`, `_load_dealer_map_2026` | `accounts` (파생 입력) |
| OUD 디렉토리 스냅샷 파일들 | `load_oud` | `oud_snapshots` |
| AR/Overdue 스냅샷 파일들 | `load_ar_overdue` | `ar_snapshots` |
| 수금 파일들 | (col 로더) | `collection_snapshots` |
| PGI/잔여/오픈 파일들 | `load_pgi_remain_open` | `so_pipeline_snapshots` |
| 코드 상수 `ACCOUNT_ALIAS`, `TEAM_OVERRIDE` | — | `account_aliases` (+선택: `team_overrides`) |

정확한 컬럼 인덱스(r[1], r[5], r[6], r[27], r[38], r[70], r[77], r[98] 등)는 `refresh_dashboard.py`에 이미 구현돼 있으므로 **별도 스키마 확인 작업 불필요** — 1단계의 Phase 0(서버 실물 확인)에 해당하는 리스크가 낮다. 단, 2024 Raw는 포맷이 달라(`load_2024` 별도 함수) 백필 시 원본 필드 일부(자재코드 등)가 없을 수 있음 → 해당 컬럼 NULL 허용으로 흡수.

## 6. 이관 절차

| Phase | 작업 | 완료 기준 |
|---|---|---|
| **1. 모듈 + 백필** | `sell-thru-dashboard/st_db.py` (schema/커넥션/UPSERT) + `backfill_st.py`: 기존 파서 함수를 import해 3개년 raw + 전체 스냅샷 파일 적재 | §6.1 검증 통과 |
| **2. 일일 병행 적재** | `refresh_dashboard.py`에 persist 훅 추가 (파싱 직후, HTML 생성 전. `--no-db` 옵션). xlsx·JSON 출력은 그대로 | 7일간 data.json의 txn 집계 = DB GROUP BY 결과 일치 |
| **3. 출력 전환** | `data.json`의 `txn`을 DB 쿼리 산출로 교체 + 오래된 연도는 월 집계로 축소 (14MB → 수 MB 목표). 스냅샷 JSON도 동일 | 대시보드 화면 diff 무변화 |
| **4. 규칙의 데이터화 (선택)** | `TEAM_OVERRIDE`/`ACCOUNT_ALIAS`를 DB 테이블로 이전, 코드에는 로더만 | 규칙 변경 시 재배포 불필요 |

### 6.1 백필 검증

1. **집계 대사**: 연×팀×카테고리별 `SUM(value)`, `SUM(qty)`가 현재 `data.json` `txn` 집계와 일치 (반올림 오차 허용 ±1)
2. **계정 대사**: `accounts` 행수·팀 분포가 `master` 2,700행과 일치
3. **스냅샷 대사**: 최신/직전 스냅샷 합계가 대시보드 표시값과 일치
4. **멱등성**: 백필 2회 실행 시 행수 불변

## 7. 운영

- **용량**: 인보이스 라인 기준 연 수만~수십만 행 + 스냅샷 → 연 수십 MB. SQLite 여유.
- **백업**: 1단계와 동일 (요일별 `.backup` 7세대 + 주간 `VACUUM INTO`). **거래·채권 금액 데이터이므로 백업 사본을 git에 올리지 않는다** (가격 DB와 다른 점 — §9-1).
- **파일 권한**: `chmod 600 sell_thru.db` (서버 내 다른 프로세스 열람 방지).
- **1단계와의 교차 조회**: `ATTACH '<경로>/price_data.db' AS price` — 자재코드↔SKU 매핑 테이블은 3단계 이후 별도 과제.

## 8. 리스크

| 리스크 | 대응 |
|---|---|
| 인보이스 라인의 자연키 부재 — SAP 추출본에 라인 고유 ID가 있는지 미확인 | Phase 1 착수 시 raw 헤더에서 인보이스 번호+라인 번호 존재 확인. 있으면 그걸 UNIQUE 키로 교체, 없으면 §4의 합성 키(동일 값 라인 중복 리스크 있음 → 백필 대사로 검출) |
| 2024 Raw 포맷 상이 | `load_2024` 파서를 그대로 사용, 결측 원본 필드는 NULL |
| Daily 파일 재투입/수정 시 이중 적재 | 날짜 단위 재적재 시 해당 `inv_date` 범위 삭제 후 삽입 (eXtra 패턴) |
| refresh_dashboard.py가 git 미추적 원본 — 훅 추가분 유실 위험 | 1단계처럼 `automation-backup/`이 정본, 서버 사본에 배포하는 절차 유지 |
| 금액·채권 데이터 유출 | DB 파일 600 권한 + git 제외 + 백업도 서버 내 보관 |

## 9. 확인 필요 사항 (형님 결정)

1. **백업의 외부 보관** — 가격 DB와 달리 매출·AR 금액이라 git 보관 부적절. 서버 내 보관만 할지, 별도 사설 저장소(OCI Object Storage 등)를 쓸지
2. **거래 그레인** — 인보이스 라인(권장, 자재 단위 분석 가능) vs 현행 일×계정×카테고리 집계(가볍지만 확장성 없음)
3. **Phase 4 (규칙의 데이터화)** 진행 여부 — TEAM_OVERRIDE 변경이 잦다면 가치 있음
4. **수금(col) 상세** — 현재 코드에서 수금 로더 구조를 아직 정밀 확인 안 함. Phase 1 착수 시 확정
