#!/usr/bin/env python3
"""
정규화된 행을 DB에 적재하는 공통 로직 + SKU 상태 이벤트 파생.

backfill.py(전체 이력)와 ingest_daily.py(당일분)가 공유한다.
"""
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))         # db/ (mappings.py)
sys.path.insert(0, str(Path(__file__).parent.parent))  # price-tracking/ (config.py)
from mappings import CHANNELS, MAPPINGS

PT_ROOT = Path(__file__).parent.parent

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# checkRunQuality (대시보드 SEC3) 서버 이식 파라미터
QUALITY_BASELINE_DAYS = 14   # 직전 N개 스크래핑일을 기준선으로
QUALITY_MIN_RATIO = 0.85     # 총 수집량이 기준선 중앙값의 85% 미만이면 부실 런
REACTIVE_MIN_ABSENT = 2      # 연속 부재 N일 이상 후 복귀 시 'reactive'
DISCONTINUED_DAYS = 14       # 연속 부재 N일 도달 시 'discontinued'


def resolve_master_path(channel: str) -> Path:
    """config.py의 중앙 data/ 경로 우선, 없으면 채널 폴더의 legacy 마스터 폴백."""
    try:
        import config
        p = config.get_master_path(channel)
        if p.exists():
            return p
    except (ImportError, KeyError):
        pass
    m = MAPPINGS.get(channel)
    if m and m.get("legacy_master"):
        p = PT_ROOT / m["legacy_master"]
        if p.exists():
            return p
    return None


def read_master_rows(channel: str, master_path: Path):
    """마스터 xlsx → (run_date, [정규화 행]) dict. 정규화 실패 행은 errors에 수집."""
    import pandas as pd
    m = MAPPINGS[channel]
    norm = m["normalize"]
    by_date, errors = {}, []

    if m["source"] == "sheet_per_date":
        sheets = pd.read_excel(master_path, sheet_name=None, engine="openpyxl")
        frames = [(name, df) for name, df in sheets.items() if DATE_RE.match(str(name))]
    else:
        df = pd.read_excel(master_path, sheet_name=m["sheet"], engine="openpyxl")
        frames = [(None, df)]

    for sheet_name, df in frames:
        for raw in df.to_dict("records"):
            row = norm(raw, sheet_name=sheet_name)
            if not row["sku"] or not row["run_date"]:
                errors.append({"reason": "sku/run_date 누락", "raw": {k: str(v)[:80] for k, v in raw.items()}})
                continue
            by_date.setdefault(row["run_date"], []).append(row)
    return by_date, errors


def get_channel_id(conn, code: str) -> int:
    meta = CHANNELS[code]
    conn.execute(
        "INSERT INTO channels (code, name, alert_basis, cond_discount) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(code) DO UPDATE SET name=excluded.name, alert_basis=excluded.alert_basis, "
        "cond_discount=excluded.cond_discount",
        (code, meta["name"], meta["alert_basis"], meta["cond_discount"]),
    )
    return conn.execute("SELECT id FROM channels WHERE code = ?", (code,)).fetchone()[0]


def upsert_rows(conn, channel_id: int, run_date: str, rows: list, run_id=None) -> int:
    """한 채널 × 한 수집일 분량을 UPSERT. 반환: 적재 행수."""
    count = 0
    for r in rows:
        conn.execute(
            """INSERT INTO products (channel_id, sku, brand, model, name_en, name_ar, category,
                                     btu, ton, compressor, ac_type, url, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(channel_id, sku) DO UPDATE SET
                 brand      = COALESCE(excluded.brand, brand),
                 model      = COALESCE(excluded.model, model),
                 name_en    = COALESCE(excluded.name_en, name_en),
                 name_ar    = COALESCE(excluded.name_ar, name_ar),
                 category   = COALESCE(excluded.category, category),
                 btu        = COALESCE(excluded.btu, btu),
                 ton        = COALESCE(excluded.ton, ton),
                 compressor = COALESCE(excluded.compressor, compressor),
                 ac_type    = COALESCE(excluded.ac_type, ac_type),
                 url        = COALESCE(excluded.url, url),
                 first_seen = MIN(first_seen, excluded.first_seen),
                 last_seen  = MAX(last_seen, excluded.last_seen)""",
            (channel_id, r["sku"], r["brand"], r["model"], r["name_en"], r["name_ar"],
             r["category"], r["btu"], r["ton"], r["compressor"], r["ac_type"], r["url"],
             run_date, run_date),
        )
        pid = conn.execute(
            "SELECT id FROM products WHERE channel_id = ? AND sku = ?",
            (channel_id, r["sku"]),
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO price_snapshots (product_id, run_date, scraped_at, sp, sl, fp, fj,
                                            discount_pct, in_stock, stock_qty, promo_text, attrs, run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, run_date, r["scraped_at"], r["sp"], r["sl"], r["fp"], r["fj"],
             r["discount_pct"], r["in_stock"], r["stock_qty"], r["promo_text"],
             json.dumps(r["attrs"], ensure_ascii=False) if r["attrs"] else None, run_id),
        )
        count += 1
    return count


# ── SKU 상태 이벤트 파생 (대시보드 SEC3 서버 이식) ────────────────────────────
def _scrape_dates(conn, channel_id: int):
    return [row[0] for row in conn.execute(
        """SELECT DISTINCT s.run_date FROM price_snapshots s
           JOIN products p ON p.id = s.product_id
           WHERE p.channel_id = ? ORDER BY s.run_date""", (channel_id,))]


def check_run_quality(conn, channel_id: int, run_date: str):
    """부실 런 판별: 총 수집량 급감 or 기존 카테고리 완전 누락. (ok, reasons) 반환."""
    dates = _scrape_dates(conn, channel_id)
    if run_date not in dates:
        return False, ["해당 날짜 스냅샷 없음"]
    idx = dates.index(run_date)
    if idx == 0:
        return True, []
    baseline = dates[max(0, idx - QUALITY_BASELINE_DAYS):idx]
    reasons = []

    def day_cat_counts(d):
        return dict(conn.execute(
            """SELECT COALESCE(p.category, ''), COUNT(*) FROM price_snapshots s
               JOIN products p ON p.id = s.product_id
               WHERE p.channel_id = ? AND s.run_date = ? GROUP BY 1""", (channel_id, d)))

    today = day_cat_counts(run_date)
    total_today = sum(today.values())
    base_totals = [sum(day_cat_counts(d).values()) for d in baseline]
    if base_totals:
        med = statistics.median(base_totals)
        if med > 0 and total_today / med < QUALITY_MIN_RATIO:
            reasons.append(f"총 수집량 급감 ({total_today}/{med:.0f}건)")
    cat_hits = {}
    for d in baseline:
        for c in day_cat_counts(d):
            cat_hits[c] = cat_hits.get(c, 0) + 1
    for c, hits in cat_hits.items():
        if hits >= 3 and today.get(c, 0) == 0:
            reasons.append(f"'{c}' 카테고리 완전 누락")
    return len(reasons) == 0, reasons


def derive_status_events(conn, channel_id: int, run_date: str, skip_quality_check=False) -> dict:
    """run_date 시점의 New/Reactive/Temp OOS/Discontinued 이벤트를 물질화."""
    if not skip_quality_check:
        ok, reasons = check_run_quality(conn, channel_id, run_date)
        if not ok:
            return {"skipped": True, "reasons": reasons}

    dates = _scrape_dates(conn, channel_id)
    idx = dates.index(run_date)
    counts = {"new": 0, "reactive": 0, "temp_oos": 0, "discontinued": 0}

    # 제품별 최초/직전 등장일 (run_date 이전 기준)
    present_today = {row[0] for row in conn.execute(
        """SELECT s.product_id FROM price_snapshots s JOIN products p ON p.id = s.product_id
           WHERE p.channel_id = ? AND s.run_date = ?""", (channel_id, run_date))}
    history = conn.execute(
        """SELECT s.product_id, MIN(s.run_date), MAX(s.run_date)
           FROM price_snapshots s JOIN products p ON p.id = s.product_id
           WHERE p.channel_id = ? AND s.run_date < ? GROUP BY s.product_id""",
        (channel_id, run_date)).fetchall()
    prev_last = {pid: (first, last) for pid, first, last in history}

    def emit(pid, status, absent=None):
        cur = conn.execute(
            "INSERT INTO sku_status_events (product_id, event_date, status, absent_days) VALUES (?, ?, ?, ?)",
            (pid, run_date, status, absent))
        if cur.rowcount:
            counts[status] += 1

    for pid in present_today:
        if pid not in prev_last:
            emit(pid, "new")                                   # 역대 첫 등장
        else:
            absent = idx - dates.index(prev_last[pid][1]) - 1  # 스크래핑일 기준 부재 수
            if absent >= REACTIVE_MIN_ABSENT:
                emit(pid, "reactive", absent)                  # 부재 후 복귀

    for pid, (_first, last) in prev_last.items():
        if pid in present_today:
            continue
        absent = idx - dates.index(last)                       # 오늘 포함 연속 부재
        if absent == 1:
            emit(pid, "temp_oos", absent)                      # 부재 시작
        elif absent == DISCONTINUED_DAYS:
            emit(pid, "discontinued", absent)                  # 단종 가능성
    return {"skipped": False, "counts": counts}
