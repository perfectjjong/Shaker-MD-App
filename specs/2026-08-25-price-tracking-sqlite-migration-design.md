# Price Tracking SQLite 이관 — 설계 문서

- 날짜: 2026-08-25
- 상태: 초안 (형님 검토 대기)
- 대상: `price-tracking/` 10개 채널 가격 마스터 (Excel) → SQLite
- 실행 위치: OCI 서버 (`/home/ubuntu/2026/06. Price Tracking/` cron 환경)
- 범위: **가격 데이터 저장 계층만.** 스크래퍼 수집 로직·대시보드 UI·cron 스케줄은 변경 없음.

## 1. 배경 / 현황

### 1.1 현재 데이터 저장 구조

| 데이터 | 저장 형태 | 위치 |
|---|---|---|
| 채널별 가격 이력 (10개 채널) | Excel 마스터 (채널당 1개 xlsx, 매일 append) | OCI 서버 (레포에는 심링크만) |
| 스크래핑 실행 이력 | SQLite (`PriceTrackingDB` — batches/runs/ai_repairs) | OCI 서버, git 미추적 |
| 대시보드 | HTML에 데이터 인라인 임베드 | `docs/dashboards/*-price/` |

가격 마스터는 **long format**(1행 = SKU × 수집일)으로 매일 누적되며, 채널별 스키마가 제각각이다:

- **eXtra**: `Prices DB` 시트, 25컬럼 (`Standard_Price`, `Sale_Price`, `Jood_Gold_Price`, 프로모/사은품/보증 등)
- **Najm**: `Sheet1`, 32컬럼 (`price`/`regular_price`, 은행 프로모, 아랍어 상품명, 평점 등)
- **Bin Momen**: `Sheet1`, 20컬럼 (`Original_Price`/`Sale_Price`, `Stock_Qty`, 보증)
- **Al Khater**: **날짜별 시트 분리** (시트명 = `2026-05-11` 형식), 16컬럼
- 나머지 6개 채널(BH, SWS, Al Khunaizan, Al Manea, Black Box, Tamkeen, Technobest)은 서버에서 실물 확인 필요 (레포 심링크 깨짐)

### 1.2 문제점

1. **파일 비대화** — Najm 마스터가 이미 2.6MB/10,160행. 매일 수백 행씩 늘어나며 xlsx 전체를 읽고 다시 쓰는 구조라 시간이 갈수록 느려짐.
2. **동시성 없음** — `run_all_channels.py`가 workers 2~3으로 병렬 실행. 파일 단위라 지금은 채널별 분리로 버티지만, 크로스 채널 집계·조회가 불가능.
3. **중복/무결성 수단 없음** — 같은 날 재실행 시 중복 제거를 각 스크래퍼가 pandas로 직접 구현 (eXtra는 "오늘 행 삭제 후 재삽입", 채널마다 다름). DB 제약이 없어 실수에 취약.
4. **조회 불가** — "지난 90일 LG 18K 인버터의 채널별 최저가 추이" 같은 질의를 하려면 10개 xlsx를 pandas로 열어야 함.
5. **스키마 이질성** — 대시보드 빌더마다 자기 채널 컬럼 → `sp/sl/fp/fj` 변환 코드를 중복 보유.
6. **백업 취약** — 마스터가 git 미추적 서버 파일. 서버 유실 = 전체 가격 이력 유실.

## 2. 목표 / 비목표

### 목표

- 10개 채널 가격 이력을 **단일 SQLite 파일**로 통합 (정규화된 공통 스키마 + 채널 고유 필드 보존)
- 기존 Excel 마스터 **전체 이력 백필** (데이터 손실 0)
- 기존 운영 DB(`PriceTrackingDB`의 batches/runs)와 **같은 파일**로 통합 → 수집 실행 메타데이터와 가격 데이터를 join 가능
- 전환 기간 동안 **Excel 병행 운영** (스크래퍼·대시보드 무중단)
- 일일 백업 체계

### 비목표

- PostgreSQL 등 서버형 DBMS 도입 (현 규모에서 불필요 — §7.1 용량 추정 참조)
- 스크래퍼 수집 로직 변경
- 대시보드 실시간화 / API 서버 구축
- 셀아웃·PSI 데이터 이관 (별도 과제)

## 3. 아키텍처

```
[스크래퍼 × 10채널] ──(기존 그대로)──> [Excel 마스터 append]
                                            │
                                            ▼
                          [NEW] ingest_daily.py  ← run_all_channels.py 말미에 1회 호출
                          채널별 컬럼 매핑 → 정규화 → UPSERT
                                            │
                                            ▼
                              price_tracking.db (SQLite, WAL)
                              ├─ 가격: channels / products / price_snapshots
                              ├─ 상태: sku_status_events (파생)
                              └─ 운영: batches / runs / ai_repairs (기존 PriceTrackingDB)
                                            │
                        (Phase 3) 대시보드 빌더가 xlsx 대신 DB에서 read
```

**핵심 결정:**

- **D1. 수집기 무변경, 적재는 후처리 ETL** — 스크래퍼 10개를 고치지 않고, `run_all_channels.py` 전 채널 완료 후 `ingest_daily.py`가 각 마스터의 "오늘 행"을 읽어 DB에 적재. 스크래퍼 실패·수정과 DB 적재가 분리되어 리스크 최소.
- **D2. 단일 파일, 단일 라이터** — 적재는 ETL 1개 프로세스만 수행 (채널 병렬 스크래핑과 무관). `journal_mode=WAL`, `busy_timeout=5000`으로 운영 DB 기록(`db_manager`)과의 동시 접근 충돌 방지.
- **D3. 공통 스키마 + JSON 확장** — 가격·재고·식별자 등 공통 필드는 정규 컬럼으로, 채널 고유 필드(사은품, 은행 프로모, 평점 등)는 `attrs` JSON 컬럼에 원본 보존. 스키마 변경 없이 신규 채널 수용.
- **D4. 파일 위치** — `/home/ubuntu/2026/06. Price Tracking/price_data.db` (cron 작업 디렉토리, **운영 로그 DB와 별도 파일**). `.gitignore`의 `*.db` 규칙 유지 (git 미추적), 백업은 §7.2.
  - *(2026-08-25 수정)* 당초 운영 DB(`price_tracking.db`)와 단일 파일 통합을 계획했으나, 서버 실물 확인 결과 `db_manager`가 이미 `channels`/`price_snapshots`/`products`(잔재)/`price_alerts` 등의 테이블 이름을 자기 스키마로 점유 중이어서 충돌 — 별도 파일로 분리한다. 실행 메타데이터와의 join은 `ATTACH DATABASE 'price_tracking.db' AS ops`로 동일하게 가능하며, `db.py`에 운영 DB를 잘못 여는 실수를 막는 안전장치를 둔다.

## 4. 스키마 설계 (DDL)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 채널 마스터 (10행, PRICE_SCHEME_GUIDE.md의 Alert 기준 반영)
CREATE TABLE channels (
    id            INTEGER PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,     -- 'extra', 'bh', 'sws', ...  (config.py 키와 동일)
    name          TEXT NOT NULL,            -- 'eXtra', 'Bin Momen', ...
    alert_basis   TEXT NOT NULL,            -- 'sl' | 'cp' | 'fp'  (Alert 비교 기준 필드)
    cond_discount TEXT                      -- 조건부 할인 유형: 'promo_code'|'cashback'|'only_pay'|NULL
);

-- SKU 마스터 (채널 × SKU 유일. 속성은 최신 수집값으로 갱신)
CREATE TABLE products (
    id           INTEGER PRIMARY KEY,
    channel_id   INTEGER NOT NULL REFERENCES channels(id),
    sku          TEXT NOT NULL,             -- 채널 원본 SKU (Najm은 product_id 폴백)
    brand        TEXT,
    model        TEXT,
    name_en      TEXT,
    name_ar      TEXT,
    category     TEXT,                      -- 'Split AC', 'Window', 'Cassette', ...
    btu          INTEGER,
    ton          REAL,
    compressor   TEXT,                      -- 'Inverter' | 'Rotary' | ...
    ac_type      TEXT,                      -- 'Heat & Cool' | 'Cooling Only' | ...
    url          TEXT,
    first_seen   TEXT NOT NULL,             -- 'YYYY-MM-DD'
    last_seen    TEXT NOT NULL,
    UNIQUE (channel_id, sku)
);

-- 가격 스냅샷 (1행 = SKU × 수집일). 같은 날 재수집 시 교체.
CREATE TABLE price_snapshots (
    id           INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    run_date     TEXT NOT NULL,             -- 'YYYY-MM-DD'
    scraped_at   TEXT,                      -- 'YYYY-MM-DD HH:MM:SS'
    sp           REAL,                      -- 표준가 (Standard Price)
    sl           REAL,                      -- 프로모가 (Sale Price) — 기본 Alert 기준
    fp           REAL,                      -- 최종가 (조건부 할인 적용 후) — 정보성
    fj           REAL,                      -- 특수 카드/멤버십가 (Jood Gold, BP, Al Ahli 등)
    discount_pct REAL,
    in_stock     INTEGER,                   -- 1/0/NULL
    stock_qty    INTEGER,
    promo_text   TEXT,                      -- 프로모 코드/라벨 요약
    attrs        TEXT,                      -- 채널 고유 필드 JSON (사은품, 보증, 평점, 은행프로모 등)
    run_id       INTEGER,                   -- 운영 DB runs.id (수집 실행과 연결, NULL 허용)
    UNIQUE (product_id, run_date) ON CONFLICT REPLACE
);
CREATE INDEX idx_snap_date    ON price_snapshots (run_date);
CREATE INDEX idx_snap_product ON price_snapshots (product_id, run_date);

-- SKU 상태 이벤트 (대시보드 SEC3 로직을 적재 시점에 파생·물질화)
CREATE TABLE sku_status_events (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    event_date  TEXT NOT NULL,
    status      TEXT NOT NULL,              -- 'new' | 'reactive' | 'temp_oos' | 'discontinued'
    absent_days INTEGER,                    -- 연속 부재 스크래핑일 수 (temp_oos/discontinued)
    UNIQUE (product_id, event_date, status)
);

-- 스키마 버전 (마이그레이션 관리)
CREATE TABLE schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- batches / runs / ai_repairs: 기존 db_manager.PriceTrackingDB 테이블을 같은 파일에 유지
```

**스키마 결정 근거:**

- `sp/sl/fp/fj` 컬럼명은 `PRICE_SCHEME_GUIDE.md` 및 전 대시보드 빌더가 이미 쓰는 표준 약어를 그대로 채택 — 변환 계층의 개념 불일치 제거.
- `UNIQUE(product_id, run_date) ON CONFLICT REPLACE`가 eXtra의 "오늘 행 삭제 후 교체" 로직을 DB 제약으로 일반화 — 채널별 중복 제거 코드가 불필요해짐.
- `sku_status_events`는 조회 시 계산(view)이 아닌 적재 시 파생(materialize)을 선택 — 현재 각 대시보드 JS(SEC3)가 전체 이력을 스캔해 계산하는 로직을 서버에서 1회만 수행하고, "run 품질 미달 날짜 제외" 규칙(`checkRunQuality`)도 함께 서버로 이동.

## 5. 채널별 컬럼 매핑

정규화 매핑은 `ingest_daily.py` 내 선언적 dict로 관리한다. 확인 완료된 4개 채널:

| 정규 필드 | eXtra (`Prices DB`) | Najm (`Sheet1`) | Bin Momen (`Sheet1`) | Al Khater (날짜 시트) |
|---|---|---|---|---|
| `sku` | `SKU` | `sku` (폴백 `product_id`) | `SKU` | `SKU` |
| `brand` | `Brand` | `brand_en` | `Brand` | `Brand` |
| `model` | `Model_No` | (name에서 추출 or NULL) | (NULL) | `Model` |
| `name_en` / `name_ar` | `Product_Name` / — | `name_en` / `name_ar` | `Product_Name_EN` / `Product_Name_AR` | `Product_Name` / — |
| `category` | `Category` | `category_en` | `Category` | `AC_Type` |
| `btu` / `ton` | `BTU` / `Cooling_Capacity_Ton` | `btu` / `ton` | `BTU` / `Tonnage` | — / `Ton` |
| `compressor` | `Compressor_Type` | `compressor` | `Compressor` | `Compressor` |
| `ac_type` | `Cold_or_HC` | `ac_type` | `Cooling_Type` | `Cold_HC` |
| `sp` | `Standard_Price` | `regular_price` | `Original_Price` | `Original_Price_SAR` |
| `sl` | `Sale_Price` | `price` | `Sale_Price` | `Price_SAR` |
| `fp` | (프로모코드 ×0.9 계산) | `bank_promo_price` | = `sl` | = `sl` |
| `fj` | `Jood_Gold_Price` | — | — | — |
| `discount_pct` | `Discount_Rate` | `discount_pct` (% 문자 제거) | `Discount` (% 문자 제거) | `Discount_Pct` |
| `in_stock` / `stock_qty` | `Stock_Status` / — | `is_available` / — | `In_Stock` / `Stock_Qty` | `In_Stock` / — |
| `run_date` | `Scraped_At`의 date부 | `run_date` | `Scrape_Date`의 date부 | 시트명 |
| `attrs` (JSON 보존) | Promo/Gift/Warranty/Exclusive 등 | salla_tag, rating, bank_promo_* 등 | Warranty, Image_URL | Page |

나머지 6개 채널(BH, SWS, Al Khunaizan, Al Manea, Black Box, Tamkeen, Technobest)은 **서버의 실물 마스터를 열어 같은 표를 완성한 뒤 구현** (Phase 0 작업). BH는 `cp`(현금가) 기준, Black Box는 `fp` cascade 등 `PRICE_SCHEME_GUIDE.md`의 채널별 Alert 기준을 `channels.alert_basis`에 반영한다.

## 6. 이관 절차 (Phased Rollout)

| Phase | 작업 | 산출물 | 완료 기준 |
|---|---|---|---|
| **0. 스키마 확정** | 서버에서 나머지 6개 마스터 스키마 확인, 매핑표 완성. 기존 `db_manager.py` 테이블 DDL 회수 → 레포에 백업 | `price-tracking/db/schema.sql`, `db_manager.py`의 `automation-backup/` 사본 | 매핑표 10/10 채널 |
| **1. 백필** | `backfill.py`: 10개 마스터 전체 이력 → DB 적재 (Al Khater는 시트 순회) | `price_tracking.db` 초기 구축 | §6.1 검증 통과 |
| **2. 일일 병행 적재** | `ingest_daily.py` 작성, `run_all_channels.py` 말미에 호출 추가 (`--no-db`와 독립된 `--no-ingest` 옵션). Excel append는 그대로 유지 | cron마다 DB 자동 적재 | 7일 연속 xlsx↔DB 행수 일치 |
| **3. 대시보드 전환** | 빌더의 `read_excel` → DB 쿼리 교체. 채널별 `sp/sl/fp/fj` 변환 코드 삭제 (DB가 이미 정규형) | 빌더 10개 수정 | 대시보드 산출 HTML diff 무변화 확인 |
| **4. Excel 강등** | 마스터 xlsx를 "주간 export 산출물"로 전환 (엑셀로 보고 싶은 수요 대응), append 로직 제거 | export 스크립트 | 1개월 병행 후 |

각 Phase는 독립 배포 가능하며, Phase 2까지는 기존 파이프라인에 어떤 변경도 가하지 않는다 (호출 1줄 추가 제외).

### 6.1 백필 검증 (Phase 1 완료 기준)

1. **행수 대사**: 채널×날짜별 `COUNT(*)` = xlsx 행수 (전 채널, 전 기간)
2. **스팟 체크**: 채널당 무작위 30행의 `sp/sl` 원본 대조
3. **집계 대사**: 채널×월별 `AVG(sl)`, `MIN(sl)`, `MAX(sl)`을 pandas 계산치와 대조 (오차 0)
4. **SKU 상태 대사**: 기존 대시보드 SEC3의 New/Discontinued 카운트와 `sku_status_events` 파생 결과 일치

## 7. 운영

### 7.1 용량·성능 추정

- 현재: 10채널 × 평균 ~300 SKU × 일 1회 ≈ **일 3,000행 / 연 ~110만 행**
- SQLite 기준 연 100~200MB 수준 (attrs JSON 포함 넉넉히) — SQLite 실용 한계(수십 GB) 대비 수십 년 여유. 서버형 DB 불필요.
- 인덱스 2개로 대시보드의 주력 질의(SKU별 시계열, 날짜별 단면) 모두 커버.

### 7.2 백업

- cron 말미에 `sqlite3 price_data.db ".backup '<dir>/price_data_$(date +%u).db'"` — **요일별 로테이션 7세대**
- 주 1회 `VACUUM INTO`로 압축 스냅샷을 `/home/ubuntu/Shaker-MD-App/automation-backup/price-tracking-db/` 에 보관 (git 추적 여부는 용량 보고 결정 — LFS 검토)
- `integrity_check.py`에 `PRAGMA integrity_check` 항목 추가, 실패 시 기존 텔레그램 알림 경로로 통보

### 7.3 코드 배치

```
price-tracking/
├── db/
│   ├── schema.sql          # DDL (버전 관리, schema_migrations로 적용 추적)
│   ├── db.py               # 커넥션·PRAGMA·마이그레이션 러너
│   ├── mappings.py         # 채널별 컬럼 매핑 선언 (§5)
│   ├── ingest_daily.py     # 일일 적재 ETL (run_all_channels가 호출)
│   └── backfill.py         # 1회성 전체 이력 백필
```

기존 `db_manager.py`(운영 로그)는 그대로 두고 같은 DB 파일을 공유한다. 장기적으로 `db/` 모듈로 흡수 가능하나 이번 범위 아님.

## 8. 리스크

| 리스크 | 대응 |
|---|---|
| 서버에만 있는 6개 채널 스키마가 예상과 다름 | Phase 0에서 실물 확인 후 매핑 확정 — 그 전에는 구현 착수 안 함 |
| 병렬 스크래핑 중 운영 DB 기록과 ETL 적재의 락 충돌 | ETL은 전 채널 완료 후 단독 실행 + WAL + busy_timeout |
| 같은 날 수동 재실행으로 인한 이중 적재 | `ON CONFLICT REPLACE`가 자동 교체 — 멱등 |
| Al Khater처럼 스키마가 아예 다른 신규 채널 | 매핑 dict 1개 추가로 수용 (D3) |
| 백필 중 xlsx의 더러운 데이터 (%, 문자 섞인 가격 등) | 정규화 함수에서 파싱 실패 시 원본을 attrs에 보존하고 NULL 적재 + 리포트 |

## 9. 확인 필요 사항 (형님 결정)

1. **백업 사본의 git 보관 여부** — 압축 스냅샷을 레포(LFS)에 올릴지, 서버 로컬 보관만 할지
2. **Phase 4 (Excel 강등) 진행 여부** — 엑셀 파일을 계속 정본으로 쓸 수요가 있으면 Phase 3까지만
3. **Al Khater 채널 포함 여부** — `config.py`의 10개 채널 목록에 없는 별도 존재 (스크래퍼는 있음). 포함 시 11개 채널로 진행
