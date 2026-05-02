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
