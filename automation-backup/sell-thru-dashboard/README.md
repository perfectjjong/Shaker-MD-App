# ⚠️ 이 폴더는 백업 사본입니다 — 현행 코드가 아닙니다

## 절대 규칙 (2026-08-26 사고 후 신설)

**이 폴더의 파일을 편집하거나, 실제 경로로 복사하지 마십시오.**

### 실제 코드(정본) 경로
```
/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/01. Python Code/refresh_dashboard.py
```
수정은 **반드시 위 실경로에서** 합니다.

### 왜 이 경고가 생겼나 (2026-08-25 사고)
`refresh_dashboard.py` 사본이 **2026-05-02에 백업된 뒤 3개월간 갱신되지 않았는데**,
8/25 저녁 작업에서 이 낡은 사본을 현행 코드로 착각해 편집하고 실제 경로로 복사했습니다.

그 결과 5~8월에 쌓인 개선이 통째로 사라졌습니다:
- `import shared_category` / `from shared_classification` (카테고리·계정 SSOT)
- `B2B_SE_TEAMS` (8/19 B2B Division = SE 기준 개편)
- `is_part` (부품 오염 게이트)
- `MIXED_ACCOUNTS` (8/25 혼재 계정 분리)
- 2024 소스가 구 파일로 회귀

**배포 데이터 피해**: 카테고리가 구 라벨로 회귀(Concealed Set→Concealed 등),
설치비 45M이 매출로 유입, 부품 10만대 혼입. 파이프라인은 조용히 성공했고
3회 배포될 때까지 아무도 몰랐습니다.

### 재발 방지
1. `refresh_dashboard.py` **배포 직전 산출물 게이트** (`predeploy_gate()`) — 카테고리 정본 이탈·
   부품/설치비 유입·SSOT 미적재 감지 시 **배포 차단 + 텔레그램 경보**
2. 이 README (낡은 사본을 만지지 않도록)
3. 아래 `refresh_dashboard.py` 사본은 **제거**했습니다 — 낡은 코드가 남아 있는 것 자체가 위험합니다.
   백업이 필요하면 실경로의 `.bak_*` 파일과 memory-vault를 사용하십시오.

### 이 폴더에 남는 것
- `st_db.py` — Sell-Thru SQLite 저장 계층 (2026-08-25 신규 작업물, 실경로 사본 아님)
- `backup_sell_thru_oci.sh` — DB 백업 스크립트 (코드 백업 아님)
