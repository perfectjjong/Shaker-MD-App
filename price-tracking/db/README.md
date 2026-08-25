# Price Tracking SQLite 모듈

설계: `specs/2026-08-25-price-tracking-sqlite-migration-design.md`

## 파일

| 파일 | 역할 |
|---|---|
| `schema.sql` | DDL (channels / products / price_snapshots / sku_status_events) |
| `db.py` | 커넥션·PRAGMA(WAL)·스키마 적용. DB 경로: `PT_DB_PATH` env → 서버 cron 디렉토리 → `price-tracking/data/` |
| `mappings.py` | 채널별 컬럼 매핑 — 11개 채널 전체 구현 (원본 스키마: `master_schema_dump.txt` 참조) |
| `loader.py` | UPSERT + SKU 상태 이벤트 파생 (부실 런 자동 제외) |
| `backfill.py` | 1회성 전체 이력 백필 + 행수 대사 검증 |
| `ingest_daily.py` | 일일 적재 ETL — `run_all_channels.py`가 전 채널 완료 후 자동 호출 |

## 서버 운영 (OCI)

```bash
# 1회성 백필 (Phase 1)
python3 /home/ubuntu/Shaker-MD-App/price-tracking/db/backfill.py

# 일일 적재는 cron의 run_all_channels.py가 자동 수행 (--no-ingest로 끔)
# 특정 날짜 수동 재적재 (멱등 — 같은 날 재실행 시 교체)
python3 ingest_daily.py --date 2026-08-24 --only najm
```

## 신규 채널 추가

`mappings.py`에 ① `CHANNELS` 메타데이터(alert 기준은 `PRICE_SCHEME_GUIDE.md` 참조),
② `normalize_<채널>()` 함수, ③ `MAPPINGS` 엔트리를 추가하면 끝. 스키마 변경 불필요
(채널 고유 필드는 `attrs` JSON에 보존).
