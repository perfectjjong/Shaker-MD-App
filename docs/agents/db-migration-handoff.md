# DB 이관 핸드오프 (2026-08-25 세션)

> 다음 세션(사람/AI)이 이 문서 하나로 SQLite 이관 작업의 전체 맥락을 이어받기 위한 문서.
> 관련 설계: `specs/2026-08-25-price-tracking-sqlite-migration-design.md`, `specs/2026-08-25-sell-thru-sqlite-migration-design.md`

## 1. 완료된 것 (2026-08-25 하루 세션, PR #25~#28 전부 main 머지)

| 항목 | 상태 | 검증 |
|---|---|---|
| **1단계: 가격 DB** `price_data.db` | ✅ 운영 중 | 11채널 268,190행 백필, 채널×날짜 행수 대사 전체 일치, najm 30행 스팟체크 일치 |
| **2단계: 셀스루 DB** `sell_thru.db` | ✅ 운영 중 | 거래 214,876행(3개년 인보이스 라인) + 계정 2,335 / OUD 99 / AR 2,187 / 수금 1,425 / SO파이프 47,002 |
| 규칙 데이터화 | ✅ | `team_overrides`(21)·`account_aliases`(3) 테이블이 정본, 코드 상수는 시드+폴백 |
| 기존 버그 수정 ① | ✅ | 서비스센터(AFS) 17행이 카테고리 누락으로 2월부터 병합 차단 → OWNO* 자재를 Miscellaneous로 분류해 복구 (PR #27) |
| 기존 버그 수정 ② | ✅ | OUD 대시보드 섹션 수개월 공백 → 2026-08부터 바뀐 신양식(HVAC.xlsx, 헤더 'Customer') 인식 추가로 복구 (PR #28) |

## 2. 시스템 지도

### DB 파일 (전부 OCI 서버, git 미추적 `*.db`)

| 파일 | 위치 (서버) | 내용 |
|---|---|---|
| `price_data.db` | `~/2026/06. Price Tracking/` | 가격 스냅샷 (channels/products/price_snapshots/sku_status_events) |
| `price_tracking.db` | `~/2026/06. Price Tracking/` | **기존 운영 로그 DB(db_manager)** — 이름이 비슷하니 혼동 금지. `channels`/`price_snapshots` 등 테이블명이 겹쳐 가격 DB를 별도 파일로 분리했음 (설계 D4). join은 ATTACH |
| `sell_thru.db` | `~/2026/10. Automation/00. Sell Thru Dashboard/` | 셀스루 거래+스냅샷+규칙. **매출·채권 데이터 — 권한 600, git·외부 공유 금지** |

### 코드 (레포가 정본, 서버 사본에 배포하는 구조)

| 레포 경로 | 서버 배포 위치 | 역할 |
|---|---|---|
| `price-tracking/db/` (schema.sql, db.py, mappings.py, loader.py, backfill.py, ingest_daily.py) | 서버의 레포 클론에서 직접 실행 | 가격 DB 모듈. 채널 매핑 11/11 구현 |
| `automation-backup/price-tracking/run_all_channels.py` | `~/2026/06. Price Tracking/` 에 cp | 새벽 cron. 말미에 `ingest_daily.py` 자동 호출 (`--no-ingest`로 끔) |
| `automation-backup/sell-thru-dashboard/st_db.py` | `.../01. Python Code/` 에 cp | 셀스루 DB 스키마+적재 |
| `automation-backup/sell-thru-dashboard/refresh_dashboard.py` | 위와 동일 | 파싱 후 `st_db.persist_all()` 훅 (`--no-db`로 끔). 실행 = 3개년 전체 재적재(멱등) |
| `automation-backup/sell-thru-dashboard/backup_sell_thru_oci.sh` | (미배포) | OCI Object Storage 백업 — §4-1 참조 |

**배포 절차**: 레포에서 수정 → main 머지 → 서버 `git pull` → 해당 파일을 위 표의 서버 위치로 `cp`. (price-tracking/db/는 cp 불필요 — 레포 클론에서 직접 실행)

## 3. 운영 런북

- **가격 DB**: 매일 03:00 KSA cron(`run_all_channels.py`)이 스크래핑 후 자동 적재. 로그에 `[ingest]` 줄. 특정일 재적재: `python3 price-tracking/db/ingest_daily.py --date YYYY-MM-DD --only <채널>` (멱등)
- **셀스루 DB**: `refresh_dashboard.py` 실행 시마다 자동 적재(연 단위 전체 교체 + 90% 급감 가드). 로그에 `[st_db]` 줄
- **분류 규칙 추가** (코드 수정·재배포 불필요):
  ```sql
  -- sell_thru.db에서
  INSERT INTO team_overrides VALUES ('1180001234', 'Projects', '사유');
  INSERT INTO account_aliases VALUES ('구ID', '대표ID');
  ```
  다음 refresh 실행에서 3개년 전체에 소급 반영됨
- **신규 가격 채널 추가**: `price-tracking/db/mappings.py`에 CHANNELS 메타 + normalize 함수 + MAPPINGS 엔트리 (README 참조). 스키마 변경 불필요
- **상태 점검 쿼리** (서버):
  ```bash
  python3 -c "import sqlite3; c=sqlite3.connect('/home/ubuntu/2026/06. Price Tracking/price_data.db'); \
  [print(r) for r in c.execute('SELECT c.code, MAX(s.run_date), COUNT(*) FROM price_snapshots s JOIN products p ON p.id=s.product_id JOIN channels c ON c.id=p.channel_id GROUP BY c.code')]"
  ```

## 4. 미완료 / 보류 항목

1. **OCI 백업 버킷 셋업** (사용자 작업, 1회) — `backup_sell_thru_oci.sh` 상단 3단계(OCI CLI 설치 → 비공개 버킷 생성 → cron 등록). 두 DB 모두 백업함. **완료 전까지 DB는 서버 단일 사본** — 최우선 잔여 작업
2. **7일 병행 관찰** — 2026-09-01 15:00Z에 이 세션 셀프 체크인 예약됨(trigger `trig_01UnaeQ1sWRRW2z7eVpnyhTE`). xlsx↔DB 대사 후 Phase 2 완료 판정
3. **Phase 3 (출력 전환)** — 미착수. 대시보드 빌더가 xlsx/전체이력 인라인 대신 DB에서 읽기 (가격 대시보드 11MB HTML, 셀스루 data.json 18MB 축소). 관찰 완료 후 진행
4. **잔여 정리거리**: `refresh_dashboard.py`의 `datetime.utcnow()` deprecation 경고 3곳, IR Target 파일 경로가 2026-Jan로 하드코딩(`WARNING: IR Target file not found` 매 실행), OUD에서 ID 매핑 안 되는 계정은 이름 키로 저장됨(예: 'Gebal Asir Est')
5. **SWS 364행** — sku·URL·날짜가 모두 없는 원본 불량 행, 복구 불가로 미적재 확정 (전체의 1%)

## 5. 다음 활용 로드맵 (사용자와 합의된 우선순위)

1. **아침 가격 변동 텔레그램 브리핑** — cron 적재 직후 전일 대비 변동 요약을 sonolbot 경로로 발송 (반나절 작업)
2. **크로스 채널 가격 포지셔닝 대시보드** — Excel로는 불가능했던 채널 간 비교 (LG vs 경쟁 브랜드 매트릭스, 채널 간 가격 역전 감지)
3. **GPC 시뮬레이션 연동** — `sell_thru.db`에 `gpc_lines` 테이블 추가 (`build_gpc_dashboard.py`에 동일 패턴 훅). 셀스루가 인보이스 라인 그레인이라 join 키 확보됨. 설계: 셀스루 설계 문서 §10
4. **3단계 이관 후보**: AR 이력(ar_history.json), 셀아웃(extra-sellout 16MB) — 셀스루 패턴 재사용

## 6. 세션 관례 (다음 AI 세션용)

- 작업 브랜치: `claude/database-data-check-h5qqla` — 머지 후 재사용 시 `git checkout -B <branch> origin/main`으로 재시작
- 이 레포 원격 세션은 네트워크가 이 레포로 제한됨: gstack 설치 불가(로컬에서만), 서버 파일은 사용자가 Termius로 명령 실행 → 출력 붙여넣기 또는 브랜치에 파일 커밋으로 주고받음 (서버 마스터 스키마는 `price-tracking/db/master_schema_dump.txt`에 덤프해 둠)
- PR은 draft 생성 → 사용자 확인 필요 없는 건은 세션에서 직접 머지해 왔음 (사용자 위임)
