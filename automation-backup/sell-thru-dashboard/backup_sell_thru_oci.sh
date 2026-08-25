#!/bin/bash
# sell_thru.db 백업 → OCI Object Storage (비공개 버킷)
# 매출·채권 데이터이므로 git에 올리지 않는다 (설계 §9-1 확정: OCI Object Storage).
#
# 최초 1회 준비 (서버에서):
#   1) OCI CLI 설치·인증:  bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"
#      oci setup config   (콘솔의 사용자 OCID/테넌시 OCID 입력)
#   2) 비공개 버킷 생성:   oci os bucket create --name shaker-db-backup --compartment-id <compartment-ocid>
#   3) cron 등록 (매일 04:00 UTC, 스크래핑 cron 이후):
#      0 4 * * * /home/ubuntu/Shaker-MD-App/automation-backup/sell-thru-dashboard/backup_sell_thru_oci.sh >> /home/ubuntu/st_backup.log 2>&1
set -euo pipefail

DB="${ST_DB_PATH:-/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/sell_thru.db}"
BUCKET="${ST_BACKUP_BUCKET:-shaker-db-backup}"
STAMP=$(date +%u)   # 요일(1~7) 로테이션 — 버킷에 최대 7세대 유지
TMP="/tmp/sell_thru_backup_${STAMP}.db"

[ -f "$DB" ] || { echo "[backup] DB 없음: $DB"; exit 1; }

# 온라인 백업 (쓰기 중에도 일관된 사본 — sqlite3 CLI 없이 python 표준 라이브러리 사용)
python3 - "$DB" "$TMP" <<'EOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
EOF
gzip -f "$TMP"

oci os object put --bucket-name "$BUCKET" --file "${TMP}.gz" \
    --name "sell_thru/sell_thru_day${STAMP}.db.gz" --force
rm -f "${TMP}.gz"
echo "[backup] $(date '+%F %T') → oci://${BUCKET}/sell_thru/sell_thru_day${STAMP}.db.gz"

# price_data.db도 같은 버킷에 백업 (가격 DB — 1단계)
PRICE_DB="/home/ubuntu/2026/06. Price Tracking/price_data.db"
if [ -f "$PRICE_DB" ]; then
    TMP2="/tmp/price_data_backup_${STAMP}.db"
    python3 - "$PRICE_DB" "$TMP2" <<'EOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
EOF
    gzip -f "$TMP2"
    oci os object put --bucket-name "$BUCKET" --file "${TMP2}.gz" \
        --name "price/price_data_day${STAMP}.db.gz" --force
    rm -f "${TMP2}.gz"
    echo "[backup] price_data.db → oci://${BUCKET}/price/price_data_day${STAMP}.db.gz"
fi
