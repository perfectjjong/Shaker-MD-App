#!/usr/bin/env python3
"""
1회성 전체 이력 백필: 채널 마스터 xlsx → price_tracking.db

사용법:
  python3 backfill.py                    # 매핑된 전 채널
  python3 backfill.py --only najm,extra  # 특정 채널만
  python3 backfill.py --db /path/to.db   # DB 경로 지정 (기본: db.resolve_db_path())

적재 후 검증(설계 §6.1): 채널×날짜별 행수 대사 + 소스 행수 일치 확인.
상태 이벤트는 날짜 오름차순으로 파생하며, 부실 런 날짜는 스킵하고 리포트한다.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db as dbmod
import loader
from mappings import MAPPINGS


def backfill_channel(conn, channel: str) -> bool:
    master = loader.resolve_master_path(channel)
    if master is None:
        print(f"  [{channel}] 마스터 파일 없음 — 스킵 (서버에서 실행 필요)")
        return False
    print(f"  [{channel}] 소스: {master}")
    by_date, errors = loader.read_master_rows(channel, master)
    if errors:
        print(f"  [{channel}] ⚠ 정규화 실패 {len(errors)}행 (sku/run_date 누락) — 미적재")
        for e in errors[:3]:
            print(f"      예시: {e['raw']}")
    src_total = sum(len(v) for v in by_date.values())

    channel_id = loader.get_channel_id(conn, channel)
    loaded = 0
    for run_date in sorted(by_date):
        loaded += loader.upsert_rows(conn, channel_id, run_date, by_date[run_date])
    conn.commit()

    # 검증 1: 소스 vs DB 행수 대사 (채널 전체 + 날짜별)
    db_total = conn.execute(
        """SELECT COUNT(*) FROM price_snapshots s JOIN products p ON p.id = s.product_id
           WHERE p.channel_id = ?""", (channel_id,)).fetchone()[0]
    db_by_date = dict(conn.execute(
        """SELECT s.run_date, COUNT(*) FROM price_snapshots s
           JOIN products p ON p.id = s.product_id
           WHERE p.channel_id = ? GROUP BY s.run_date""", (channel_id,)))
    mismatch = []
    dup_in_src = 0
    for d, rows in by_date.items():
        uniq = len({r["sku"] for r in rows})
        dup_in_src += len(rows) - uniq
        if db_by_date.get(d, 0) != uniq:
            mismatch.append((d, uniq, db_by_date.get(d, 0)))
    status = "OK" if not mismatch else f"불일치 {len(mismatch)}일"
    print(f"  [{channel}] 적재 {loaded}행 → DB {db_total}행 "
          f"(소스 {src_total}행, 소스 내 동일일 중복 SKU {dup_in_src}행은 최신값으로 교체) — 대사 {status}")
    for d, s, dbc in mismatch[:5]:
        print(f"      {d}: 소스(유니크) {s} vs DB {dbc}")

    # 상태 이벤트 파생 (날짜 오름차순)
    skipped_dates = []
    totals = {"new": 0, "reactive": 0, "temp_oos": 0, "discontinued": 0}
    for run_date in sorted(by_date):
        r = loader.derive_status_events(conn, channel_id, run_date)
        if r["skipped"]:
            skipped_dates.append((run_date, r["reasons"]))
        else:
            for k, v in r["counts"].items():
                totals[k] += v
    conn.commit()
    print(f"  [{channel}] 상태 이벤트: new {totals['new']} / reactive {totals['reactive']} / "
          f"temp_oos {totals['temp_oos']} / discontinued {totals['discontinued']}"
          + (f" — 부실 런 {len(skipped_dates)}일 제외" if skipped_dates else ""))
    for d, reasons in skipped_dates[:5]:
        print(f"      부실 런 {d}: {'; '.join(reasons)}")
    return not mismatch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="쉼표 구분 채널 코드 (기본: 매핑된 전 채널)")
    ap.add_argument("--db", help="DB 파일 경로")
    args = ap.parse_args()

    channels = ([c.strip() for c in args.only.split(",")] if args.only
                else [c for c, m in MAPPINGS.items() if m])
    unmapped = [c for c in channels if not MAPPINGS.get(c)]
    if unmapped:
        print(f"매핑 미완성 채널 (Phase 0 필요): {unmapped}")
        channels = [c for c in channels if c not in unmapped]

    conn = dbmod.connect(args.db)
    print(f"DB: {args.db or dbmod.resolve_db_path()}")
    ok = True
    for ch in channels:
        ok = backfill_channel(conn, ch) and ok
    conn.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
