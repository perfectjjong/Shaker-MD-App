#!/usr/bin/env python3
"""
Price Tracking DB — 커넥션·PRAGMA·스키마 적용.

DB 파일 위치 우선순위:
  1. 환경변수 PT_DB_PATH
  2. OCI 서버 cron 디렉토리 (/home/ubuntu/2026/06. Price Tracking/) — 기존 운영 DB와 통합
  3. price-tracking/data/price_tracking.db (로컬 개발 폴백)
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA_SQL = Path(__file__).parent / "schema.sql"
SERVER_CRON_DIR = Path("/home/ubuntu/2026/06. Price Tracking")


def resolve_db_path() -> Path:
    if os.environ.get("PT_DB_PATH"):
        return Path(os.environ["PT_DB_PATH"])
    if SERVER_CRON_DIR.is_dir():
        return SERVER_CRON_DIR / "price_tracking.db"
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "price_tracking.db"


def connect(db_path=None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else resolve_db_path()
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection):
    """schema.sql 적용 (IF NOT EXISTS 기반 멱등) + 버전 기록."""
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    cur = conn.execute("SELECT MAX(version) FROM schema_migrations")
    current = cur.fetchone()[0] or 0
    if current < SCHEMA_VERSION:
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
    conn.commit()
