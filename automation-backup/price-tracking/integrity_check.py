#!/usr/bin/env python3
"""
Price Tracking 빌더 .py 무결성 점검 + 자동 복원 도구.

cron(매일 자정 UTC) run_all_channels.py 시작 시 자동 호출.
9 빌더 .py에 다음 4가지 마커 점검:
  1. 'SKU 4-way Status Classification' (apply 박은 마커)
  2. 'sku_status' 변수 존재
  3. 'disc_records' 변수 존재
  4. records.append( 안에 'url' 키 존재 (4 빌더 — extra/sws/alkhunaizan/almanea)

마커 누락 시 automation-backup에서 자동 복원 + telegram 알림.

사용:
  python3 integrity_check.py            # 점검만 (위반 시 exit 1)
  python3 integrity_check.py --restore  # 위반 시 백업에서 자동 복원
  python3 integrity_check.py --notify   # 위반/복원 시 telegram 알림
"""
import os
import re
import sys
import shutil
import argparse
from pathlib import Path

CRON_DIR = Path("/home/ubuntu/2026/06. Price Tracking")
BACKUP_DIR = Path("/home/ubuntu/Shaker-MD-App/automation-backup/price-tracking")

# 채널별 빌더 매핑 (cron 디렉토리 기준)
BUILDERS = {
    "extra":       ("00. eXtra/extra_ac_html_dashboard_v2.py",       True),   # records url 필요
    "bh":          ("01. BH/bh_ac_html_dashboard_v2.py",             False),  # BH는 다른 구조 (RT_SKU_STATUS)
    "sws":         ("02. SWS/sws_ac_html_dashboard.py",              True),
    "najm":        ("03. Najm Store/najm_ac_html_dashboard.py",      False),  # DATA에 'u' 키만
    "alkhunaizan": ("04. Al Khunizan/alkhunaizan_ac_html_dashboard_v2.py", True),
    "almanea":     ("05. Al Manea/almanea_ac_html_dashboard_v2.py",  True),
    "tamkeen":     ("06. Tamkeen/tamkeen_ac_html_dashboard.py",      False),
    "binmomen":    ("07. Bin Momen/binmomen_ac_html_dashboard.py",   False),
    "blackbox":    ("08. Black Box/blackbox_ac_html_dashboard_v2.py", False),
    "technobest":  ("09. Techno Best/technobest_ac_html_dashboard.py", False),
}


def check_builder(name, rel_path, needs_records_url):
    """단일 빌더 점검. (위반 list 반환)"""
    path = CRON_DIR / rel_path
    if not path.is_file():
        return [f"❌ 파일 없음: {path}"]
    content = path.read_text(encoding='utf-8')
    violations = []

    if name == "bh":
        # BH는 별도 구조 — RT_SKU_STATUS / RT_DISC_RECORDS 마커
        if "RT_SKU_STATUS" not in content:
            violations.append("BH RT_SKU_STATUS 변수 없음")
        if "renderRtSkuStatus" not in content:
            violations.append("BH renderRtSkuStatus 함수 없음")
        return violations

    # 일반 9채널 마커
    if "SKU 4-way Status Classification" not in content:
        violations.append("'SKU 4-way Status Classification' 마커 없음 (apply 패치 누락)")
    if "sku_status" not in content:
        violations.append("'sku_status' 변수 없음")
    if "disc_records" not in content:
        violations.append("'disc_records' 변수 없음")

    # 4 빌더만 records에 'url' 키 필요
    if needs_records_url:
        # records.append( 다음 1500자 내에 'url': 키 존재 점검
        # (각 records.append({...}) 블록은 보통 500~1000자)
        idx = content.find('records.append(')
        if idx == -1:
            violations.append("records.append() 자체 없음")
        else:
            block = content[idx:idx + 1500]
            if "'url'" not in block:
                violations.append("records.append({...}) 블록에 'url' 키 없음 (DATA records url 누락)")

    return violations


def restore_from_backup(name, rel_path):
    """백업에서 복원."""
    src = BACKUP_DIR / Path(rel_path).name
    dst = CRON_DIR / rel_path
    if not src.is_file():
        return False, f"❌ 백업 없음: {src}"
    shutil.copy2(src, dst)
    return True, f"✅ 복원: {dst.name} (백업 → cron)"


def notify_telegram(msg):
    try:
        sys.path.insert(0, '/home/ubuntu/sonolbot')
        from telegram_sender import send_message_sync
        env_path = '/home/ubuntu/sonolbot/.env'
        chat_id = None
        if os.path.isfile(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith('TELEGRAM_ALLOWED_USERS='):
                        chat_id = int(line.split('=', 1)[1].strip().split(',')[0])
                        break
        if chat_id:
            send_message_sync(chat_id, msg)
    except Exception as e:
        print(f"⚠️ Telegram notify failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore', action='store_true', help='위반 시 백업에서 자동 복원')
    parser.add_argument('--notify', action='store_true', help='위반/복원 시 telegram 알림')
    args = parser.parse_args()

    print(f"━━ Price Tracking 빌더 무결성 점검 — {len(BUILDERS)} 채널 ━━\n")
    total_violations = 0
    restored = []
    failed_restore = []

    for name, (rel_path, needs_url) in BUILDERS.items():
        violations = check_builder(name, rel_path, needs_url)
        if violations:
            print(f"❌ {name} ({len(violations)} 위반)")
            for v in violations:
                print(f"  - {v}")
            total_violations += len(violations)
            if args.restore:
                ok, msg = restore_from_backup(name, rel_path)
                print(f"  → {msg}")
                if ok:
                    restored.append(name)
                else:
                    failed_restore.append(name)
            print()
        # 정상은 출력 생략

    print(f"━━ 종합: {total_violations}건 위반 ━━")
    if restored:
        print(f"  ✅ 복원: {len(restored)} 채널 — {', '.join(restored)}")
    if failed_restore:
        print(f"  ❌ 복원 실패: {', '.join(failed_restore)}")
    if total_violations == 0:
        print("  ✅ 모든 빌더 무결성 정상")

    if args.notify and (total_violations > 0):
        msg = f"⚠️ Price Tracking 빌더 무결성 위반\n위반: {total_violations}건"
        if restored:
            msg += f"\n자동 복원: {', '.join(restored)}"
        if failed_restore:
            msg += f"\n복원 실패: {', '.join(failed_restore)} — 수동 점검 필요"
        notify_telegram(msg)

    sys.exit(1 if total_violations > 0 and not args.restore else 0)


if __name__ == '__main__':
    main()
