#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sell-Thru SQLite 저장 계층 (sell_thru.db)
설계: specs/2026-08-25-sell-thru-sqlite-migration-design.md

refresh_dashboard.py가 파싱 완료 후 persist_all()을 호출한다.
- 거래: 인보이스 라인 그레인, 연도 단위 전체 교체 (원본 xlsx가 SSOT — 규칙 변경 자동 소급)
- 스냅샷: (snapshot_date × account) UPSERT — 실행할 때마다 이력이 누적
- 규칙: team_overrides / account_aliases 테이블 (코드 상수는 최초 시드 + 폴백)

DB 위치: env ST_DB_PATH > (이 파일 위치의 상위 디렉토리)/sell_thru.db
매출·채권 데이터이므로 파일 권한 600, git 미추적(*.db).
"""
import os
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    team         TEXT,
    status       TEXT,
    first_txn    TEXT,
    last_txn     TEXT
);
CREATE TABLE IF NOT EXISTS account_aliases (
    alias_id     TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS team_overrides (
    account_id   TEXT PRIMARY KEY,
    team         TEXT NOT NULL,
    note         TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY,
    inv_date     TEXT NOT NULL,
    month        TEXT,
    account_id_raw TEXT,
    account_id   TEXT NOT NULL,
    account_name TEXT,
    team         TEXT,
    category     TEXT,
    raw_category TEXT,
    material     TEXT,
    emp_no       TEXT,
    raw_class    TEXT,
    value        REAL NOT NULL,
    qty          INTEGER,
    qty_raw      INTEGER,
    src_year     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions (inv_date);
CREATE INDEX IF NOT EXISTS idx_txn_acct ON transactions (account_id, inv_date);
CREATE INDEX IF NOT EXISTS idx_txn_year ON transactions (src_year);

CREATE TABLE IF NOT EXISTS oud_snapshots (
    snapshot_date TEXT NOT NULL, account_id TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    account_name TEXT, value REAL, qty REAL,
    UNIQUE (snapshot_date, account_id, category) ON CONFLICT REPLACE
);
CREATE TABLE IF NOT EXISTS ar_snapshots (
    snapshot_date TEXT NOT NULL, account_id TEXT NOT NULL,
    account_name TEXT, balance REAL, overdue REAL,
    UNIQUE (snapshot_date, account_id) ON CONFLICT REPLACE
);
CREATE TABLE IF NOT EXISTS collection_snapshots (
    snapshot_date TEXT NOT NULL, account_id TEXT NOT NULL,
    account_name TEXT, mtd REAL, ytd REAL,
    UNIQUE (snapshot_date, account_id) ON CONFLICT REPLACE
);
CREATE TABLE IF NOT EXISTS so_pipeline_snapshots (
    snapshot_date TEXT NOT NULL, kind TEXT NOT NULL,
    account_id TEXT NOT NULL, account_name TEXT, value REAL, qty REAL,
    UNIQUE (snapshot_date, kind, account_id) ON CONFLICT REPLACE
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
);
"""


def resolve_db_path():
    if os.environ.get("ST_DB_PATH"):
        return os.environ["ST_DB_PATH"]
    return os.path.join(os.path.dirname(BASE), "sell_thru.db")


def connect(db_path=None):
    path = db_path or resolve_db_path()
    existed = os.path.exists(path)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(DDL)
    conn.execute("INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                 (SCHEMA_VERSION, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    if not existed:
        try:
            os.chmod(path, 0o600)  # 매출·채권 데이터 — 소유자 외 접근 차단
        except OSError:
            pass
    return conn


# ── 규칙 (③ 코드 상수 → DB) ─────────────────────────────────────────────────
def load_rules(defaults=None, db_path=None):
    """team_overrides / account_aliases를 DB에서 로드.
    테이블이 비어 있으면 코드 상수(defaults)로 최초 시드.
    반환: {'team_override': {int: str}, 'account_alias': {int: int}}"""
    conn = connect(db_path)
    try:
        if defaults:
            for aid, team in (defaults.get("team_override") or {}).items():
                conn.execute("INSERT OR IGNORE INTO team_overrides (account_id, team, note) VALUES (?, ?, 'code seed')",
                             (str(aid), team))
            for alias, canon in (defaults.get("account_alias") or {}).items():
                conn.execute("INSERT OR IGNORE INTO account_aliases (alias_id, canonical_id) VALUES (?, ?)",
                             (str(alias), str(canon)))
            conn.commit()

        def _k(v):  # SAP ID는 숫자형으로 통일 (코드 상수와 dict 키 호환)
            return int(v) if str(v).isdigit() else v
        team_override = {_k(a): t for a, t in conn.execute("SELECT account_id, team FROM team_overrides")}
        account_alias = {_k(a): _k(c) for a, c in conn.execute("SELECT alias_id, canonical_id FROM account_aliases")}
        return {"team_override": team_override, "account_alias": account_alias}
    finally:
        conn.close()


# ── 적재 헬퍼 ────────────────────────────────────────────────────────────────
def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


def _f(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _date(v):
    s = str(v or "").strip()
    return s[:10] if len(s) >= 10 and s[4] == "-" else (s or None)


def _acct_fields(info):
    """스냅샷 계정 dict의 키 이형(name/nm, value/v, qty/q, bal, ovd...)을 흡수."""
    g = info.get
    return {
        "name": g("name") or g("nm"),
        "value": _f(g("value") if g("value") is not None else g("v")),
        "qty": _f(g("qty") if g("qty") is not None else g("q")),
        "balance": _f(g("balance") if g("balance") is not None else g("bal")),
        "overdue": _f(g("overdue") if g("overdue") is not None else g("ovd")),
        "mtd": _f(g("mtd")),
        "ytd": _f(g("ytd")),
        "cats": g("cats") or g("c") or {},
    }


def _iter_snapshots(data):
    """로더 산출물에서 (snapshot_date, accounts_dict)를 모두 뽑아낸다.
    current/prev/월별 배열/snapshots dict 등 이형 구조를 방어적으로 순회."""
    if not isinstance(data, dict):
        return
    for key in ("current", "prev"):
        d = data.get(key)
        if isinstance(d, dict) and (d.get("accounts") or d.get("accts")):
            date = _date(d.get("date") or d.get("snapshot_date"))
            if date:
                yield date, (d.get("accounts") or d.get("accts"))
    monthly = data.get("monthly") or []
    if isinstance(monthly, list):
        for d in monthly:
            if isinstance(d, dict) and (d.get("accounts") or d.get("accts")):
                date = _date(d.get("date"))
                if date:
                    yield date, (d.get("accounts") or d.get("accts"))
    snaps = data.get("snapshots")
    if isinstance(snaps, dict):
        for date, d in snaps.items():
            accs = d.get("accounts") or d.get("accts") if isinstance(d, dict) else None
            if accs and _date(date):
                yield _date(date), accs
    elif isinstance(snaps, list):
        for d in snaps:
            if isinstance(d, dict) and (d.get("accounts") or d.get("accts")):
                date = _date(d.get("date"))
                if date:
                    yield date, (d.get("accounts") or d.get("accts"))


# ── 적재 본체 ────────────────────────────────────────────────────────────────
def persist_transactions(conn, df):
    """인보이스 라인 df를 연도 단위 전체 교체. 급감(<90%) 시 해당 연도 스킵."""
    total = 0
    col = df.columns
    for year in sorted(df["Year"].dropna().unique()):
        sub = df[df["Year"] == year]
        old = conn.execute("SELECT COUNT(*) FROM transactions WHERE src_year = ?", (int(year),)).fetchone()[0]
        if old and len(sub) < old * 0.9:
            print(f"   [st_db] {int(year)}: 신규 {len(sub)}행 < 기존 {old}행의 90% — 원본 이상 의심, 교체 스킵")
            continue
        conn.execute("DELETE FROM transactions WHERE src_year = ?", (int(year),))
        rows = []
        for r in sub.itertuples(index=False):
            d = dict(zip(col, r))
            rows.append((
                _date(d.get("Day")), _s(d.get("Month")),
                _s(d.get("Account_ID_Raw")), _s(d.get("Account_ID")),
                _s(d.get("Account_Name")), _s(d.get("Team")),
                _s(d.get("Category")), _s(d.get("Raw_Category")),
                _s(d.get("Material")), _s(d.get("Emp_No")), _s(d.get("Raw_Class")),
                _f(d.get("Value")) or 0.0, _f(d.get("Quantity")), _f(d.get("Qty_Raw")),
                int(year),
            ))
        conn.executemany(
            """INSERT INTO transactions (inv_date, month, account_id_raw, account_id, account_name,
               team, category, raw_category, material, emp_no, raw_class, value, qty, qty_raw, src_year)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        total += len(rows)
    return total


def persist_accounts(conn, dm):
    conn.execute("DELETE FROM accounts")
    for r in dm.itertuples(index=False):
        d = dict(zip(dm.columns, r))
        aid = _s(d.get("Account_ID"))
        if not aid:
            continue
        conn.execute("INSERT OR REPLACE INTO accounts (account_id, name, team, status) VALUES (?,?,?,?)",
                     (aid, _s(d.get("Account_Name")) or "", _s(d.get("Team")), _s(d.get("Account_Status"))))
    conn.execute("""UPDATE accounts SET
        first_txn = (SELECT MIN(inv_date) FROM transactions t WHERE t.account_id = accounts.account_id),
        last_txn  = (SELECT MAX(inv_date) FROM transactions t WHERE t.account_id = accounts.account_id)""")


def persist_oud(conn, oud_data):
    n = 0
    for date, accounts in _iter_snapshots(oud_data or {}):
        for aid, info in accounts.items():
            f = _acct_fields(info)
            conn.execute("INSERT OR REPLACE INTO oud_snapshots VALUES (?,?,?,?,?,?)",
                         (date, _s(aid), "", f["name"], f["value"], f["qty"]))
            n += 1
            for cat, cv in (f["cats"] or {}).items():
                cf = _acct_fields(cv) if isinstance(cv, dict) else {"value": _f(cv), "qty": None, "name": None}
                conn.execute("INSERT OR REPLACE INTO oud_snapshots VALUES (?,?,?,?,?,?)",
                             (date, _s(aid), str(cat), None, cf["value"], cf["qty"]))
    return n


def persist_ar(conn, ar_data):
    n = 0
    for date, accounts in _iter_snapshots(ar_data or {}):
        for aid, info in accounts.items():
            f = _acct_fields(info)
            conn.execute("INSERT OR REPLACE INTO ar_snapshots VALUES (?,?,?,?,?)",
                         (date, _s(aid), f["name"], f["balance"], f["overdue"]))
            n += 1
    return n


def persist_collection(conn, col_data):
    n = 0
    data = dict(col_data or {})
    # col은 {date, accts} 단일 구조 — current 형태로 감싸 통일
    if data.get("date") and (data.get("accts") or data.get("accounts")):
        data = {"current": data, "monthly": data.get("monthly")}
    for date, accounts in _iter_snapshots(data):
        for aid, info in accounts.items():
            f = _acct_fields(info)
            conn.execute("INSERT OR REPLACE INTO collection_snapshots VALUES (?,?,?,?,?)",
                         (date, _s(aid), f["name"], f["mtd"], f["ytd"]))
            n += 1
    return n


def persist_so_pipeline(conn, pgi_data):
    n = 0
    for kind in ("pgi", "remain", "open"):
        for date, accounts in _iter_snapshots((pgi_data or {}).get(kind) or {}):
            for aid, info in accounts.items():
                f = _acct_fields(info)
                conn.execute("INSERT OR REPLACE INTO so_pipeline_snapshots VALUES (?,?,?,?,?,?)",
                             (date, kind, _s(aid), f["name"], f["value"], f["qty"]))
                n += 1
    return n


def persist_all(df, dm, oud_data=None, ar_data=None, col_data=None, pgi_data=None, db_path=None):
    """refresh_dashboard.main()이 파싱 완료 후 1회 호출."""
    conn = connect(db_path)
    try:
        txn = persist_transactions(conn, df)
        persist_accounts(conn, dm)
        oud = persist_oud(conn, oud_data)
        ar = persist_ar(conn, ar_data)
        col = persist_collection(conn, col_data)
        so = persist_so_pipeline(conn, pgi_data)
        conn.commit()
        acc = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        print(f"   [st_db] 적재 완료 → {resolve_db_path() if not db_path else db_path}")
        print(f"   [st_db] 거래 {txn:,}행 / 계정 {acc:,} / OUD {oud} / AR {ar} / 수금 {col} / SO파이프 {so}")
    finally:
        conn.close()
