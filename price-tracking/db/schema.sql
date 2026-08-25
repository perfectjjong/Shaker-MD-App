-- Price Tracking SQLite 스키마 v1
-- 설계: specs/2026-08-25-price-tracking-sqlite-migration-design.md
-- 기존 db_manager.PriceTrackingDB 테이블(batches/runs/ai_repairs)과 같은 파일을 공유한다.

-- 채널 마스터 (PRICE_SCHEME_GUIDE.md의 Alert 기준 반영)
CREATE TABLE IF NOT EXISTS channels (
    id            INTEGER PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,     -- 'extra', 'bh', ... (config.py 키와 동일)
    name          TEXT NOT NULL,
    alert_basis   TEXT NOT NULL,            -- 'sl' | 'cp' | 'fp'
    cond_discount TEXT                      -- 'promo_code' | 'cashback' | 'only_pay' | NULL
);

-- SKU 마스터 (채널 × SKU 유일. 속성은 최신 수집값으로 갱신)
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY,
    channel_id   INTEGER NOT NULL REFERENCES channels(id),
    sku          TEXT NOT NULL,
    brand        TEXT,
    model        TEXT,
    name_en      TEXT,
    name_ar      TEXT,
    category     TEXT,
    btu          INTEGER,
    ton          REAL,
    compressor   TEXT,
    ac_type      TEXT,
    url          TEXT,
    first_seen   TEXT NOT NULL,             -- 'YYYY-MM-DD'
    last_seen    TEXT NOT NULL,
    UNIQUE (channel_id, sku)
);

-- 가격 스냅샷 (1행 = SKU × 수집일). 같은 날 재수집 시 교체(멱등).
CREATE TABLE IF NOT EXISTS price_snapshots (
    id           INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    run_date     TEXT NOT NULL,             -- 'YYYY-MM-DD'
    scraped_at   TEXT,
    sp           REAL,                      -- 표준가
    sl           REAL,                      -- 프로모가 (기본 Alert 기준)
    fp           REAL,                      -- 최종가 (조건부 할인 적용 후, 정보성)
    fj           REAL,                      -- 특수 카드/멤버십가 (Jood Gold 등)
    discount_pct REAL,
    in_stock     INTEGER,
    stock_qty    INTEGER,
    promo_text   TEXT,
    attrs        TEXT,                      -- 채널 고유 필드 JSON
    run_id       INTEGER,                   -- 운영 DB runs.id (NULL 허용)
    UNIQUE (product_id, run_date) ON CONFLICT REPLACE
);
CREATE INDEX IF NOT EXISTS idx_snap_date    ON price_snapshots (run_date);
CREATE INDEX IF NOT EXISTS idx_snap_product ON price_snapshots (product_id, run_date);

-- SKU 상태 이벤트 (대시보드 SEC3 로직을 적재 시점에 파생)
CREATE TABLE IF NOT EXISTS sku_status_events (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    event_date  TEXT NOT NULL,
    status      TEXT NOT NULL,              -- 'new' | 'reactive' | 'temp_oos' | 'discontinued'
    absent_days INTEGER,
    UNIQUE (product_id, event_date, status) ON CONFLICT IGNORE
);
CREATE INDEX IF NOT EXISTS idx_status_date ON sku_status_events (event_date, status);

-- 스키마 버전 (마이그레이션 관리)
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
