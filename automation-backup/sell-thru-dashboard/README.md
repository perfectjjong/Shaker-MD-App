# Sell-Thru Dashboard 자동화 코드 백업

**원본 위치**: `/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/01. Python Code/refresh_dashboard.py`

**백업 목적**: 원본은 git 추적 안 됨 (로컬 파일). 코드 수정 손실 방지.

**최근 변경 이력**:
- 2026-05-02 — TEAM_OVERRIDE 2건 추가 (Zagzoog, Extra Value Est) + master 강제 적용 + ACCOUNT_ALIAS 신설 (Bin Momen 4 ID 통합)

**복구 방법**:
```bash
cp /home/ubuntu/Shaker-MD-App/automation-backup/sell-thru-dashboard/refresh_dashboard.py \
   "/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/01. Python Code/refresh_dashboard.py"
```

**다음 단계 권고**: cron으로 매일 자동 백업 (수동 변경 외에도 시점별 스냅샷 보관)

---

## SQLite 저장 계층 (2026-08-25 추가)

- `st_db.py` — sell_thru.db 스키마·적재. `refresh_dashboard.py`가 파싱 후 자동 호출 (`--no-db`로 끔)
- `backup_sell_thru_oci.sh` — OCI Object Storage 백업 (요일별 7세대, price_data.db 포함)
- 규칙(TEAM_OVERRIDE/ACCOUNT_ALIAS)은 DB 테이블이 정본 — 추가는 행 삽입:
  ```sql
  INSERT INTO team_overrides VALUES ('1180001234', 'Projects', '사유 메모');
  ```
- 배포: 이 폴더의 `refresh_dashboard.py` + `st_db.py`를 원본 위치(01. Python Code/)로 복사
- 설계: `specs/2026-08-25-sell-thru-sqlite-migration-design.md`
