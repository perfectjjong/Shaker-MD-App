#!/usr/bin/env python3
"""
일일 적재 ETL: 각 채널 마스터의 "당일 행"만 DB에 UPSERT.
run_all_channels.py가 전 채널 스크래핑 완료 후 1회 호출한다 (설계 D1).

사용법:
  python3 ingest_daily.py                     # 오늘 날짜
  python3 ingest_daily.py --date 2026-08-24   # 특정 날짜 재적재 (멱등)
  python3 ingest_daily.py --only najm         # 특정 채널만

exit code: 0 = 전 채널 성공, 1 = 일부 실패 (스케줄러 감지용)
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db as dbmod
import loader
from mappings import MAPPINGS


def ingest_channel(conn, channel: str, target_date: str) -> bool:
    master = loader.resolve_master_path(channel)
    if master is None:
        print(f"  [{channel}] 마스터 파일 없음 — 스킵")
        return False
    by_date, errors = loader.read_master_rows(channel, master)
    rows = by_date.get(target_date, [])
    if not rows:
        print(f"  [{channel}] {target_date} 데이터 없음 (마스터 최신일: {max(by_date) if by_date else '-'})")
        return False

    channel_id = loader.get_channel_id(conn, channel)
    loaded = loader.upsert_rows(conn, channel_id, target_date, rows)
    conn.commit()
    result = loader.derive_status_events(conn, channel_id, target_date)
    conn.commit()
    if result["skipped"]:
        print(f"  [{channel}] {loaded}행 적재 — 상태 파생 스킵 (부실 런: {'; '.join(result['reasons'])})")
    else:
        c = result["counts"]
        print(f"  [{channel}] {loaded}행 적재 — new {c['new']} / reactive {c['reactive']} / "
              f"temp_oos {c['temp_oos']} / disc {c['discontinued']}")
    if errors:
        print(f"  [{channel}] ⚠ 정규화 실패 {len(errors)}행")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--only", help="쉼표 구분 채널 코드")
    ap.add_argument("--db", help="DB 파일 경로")
    args = ap.parse_args()

    channels = ([c.strip() for c in args.only.split(",")] if args.only
                else [c for c, m in MAPPINGS.items() if m])
    conn = dbmod.connect(args.db)
    print(f"[ingest_daily] {args.date} → {args.db or dbmod.resolve_db_path()}")
    results = {ch: ingest_channel(conn, ch, args.date) for ch in channels}
    conn.close()
    failed = [ch for ch, ok in results.items() if not ok]
    if failed:
        print(f"[ingest_daily] 실패/스킵: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
