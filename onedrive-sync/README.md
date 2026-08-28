# OneDrive → OCI 서버 동기화

OneDrive의 `08. Automation` 폴더에 파일이 올라오면 OCI 서버의 대응 폴더로
내려받고, 무엇이 들어왔는지에 따라 해당 파이프라인만 자동 실행한다.

- **방향**: 단방향 (OneDrive → OCI). 서버에서 OneDrive로는 아무것도 쓰지 않는다.
- **트리거**: cron 폴링 (기본 5분). rclone이 변경분만 전송한다.
- **인증**: rclone이 OneDrive OAuth를 자체 처리한다.

## 중복 파일 처리

| 상황 | 동작 |
|------|------|
| 서버에 이미 있고 내용도 같음 (크기·수정시각 일치) | **건너뜀** — 전송하지 않는다 |
| 같은 이름, OneDrive 쪽이 더 최신 | **업데이트** — OneDrive 버전으로 갱신 |
| 같은 이름, **서버 쪽이 더 최신** | **건너뜀** — 서버 최신본을 보존한다 |
| 서버에 없음 | 새로 받는다 |
| OneDrive에서 삭제됨 | 서버 파일은 그대로 둔다 (`copy`라 삭제를 전파하지 않음) |

세 번째 줄이 핵심이다. `KEEP_NEWER_ON_SERVER="true"`(기본값)가 rclone에 `--update`를
넘겨서, 서버가 생성한 산출물이 OneDrive의 옛 버전으로 되돌아가는 것을 막는다.
이 설정을 끄면 최신 여부와 무관하게 항상 OneDrive 것으로 덮어쓴다.

수정시각 비교 허용오차는 `MODIFY_WINDOW`(기본 `1s`)다. OneDrive가 초 단위
정밀도라 이보다 작게 두면 같은 파일이 매 회차 다시 전송될 수 있다.

## 용량

`08. Automation` 전체는 **약 784 MB**다. 내역:

| 경로 | 용량 |
|------|------|
| `01. Sell Out Dashboard` | 492 MB (IR 285, OR 201) |
| `00. Sell Thru Dashboard` | 207 MB (대부분 `00. Raw Data`) |
| `03. Operation` | 76 MB (`00. GPC` 59 MB) |
| `04. GFK Data` | 9 MB |
| `05. B2B` | 20 KB |

**784 MB는 서버가 비어 있을 때의 상한이다.** 서버에 이미 같은 파일이 있으면
그만큼 전송하지 않으므로 실제 최초 전송량은 이보다 적다. 정확한 양은
`--dry-run`으로 확인할 수 있다. 이후 회차는 새로 올라온 파일만 내려오며,
추세로 보면 월 30~60 MB 수준이다.

용량 대부분이 raw 엑셀이라 확장자 화이트리스트만으로는 크게 줄지 않는다.
그래서 가드를 네 겹으로 뒀다 (`sync-settings.conf`):

1. **확장자 화이트리스트** — `.py`, `.html`, `.bat`, `.db` 등 서버가 이미 갖고 있거나
   직접 생성하는 것은 아예 받지 않는다
2. **단일 파일 크기 상한** (기본 100 MB)
3. **회차당 전송 상한** (기본 2 GB) — 최초 대량 유입을 여러 회차로 쪼갠다
4. **디스크 여유 점검** (기본 5 GB) — 부족하면 **복사를 시작하지 않는다**
5. **서버 최신본 보존** — 위 표 참고. 덮어쓰기 사고 자체를 막는다

## 구성 파일

| 파일 | 역할 |
|------|------|
| `sync-onedrive-to-oci.sh` | 동기화 본체 |
| `sync-map.conf` | 폴더 매핑 (직접 생성) |
| `sync-settings.conf` | 용량 가드 (직접 생성, 없으면 기본값) |
| `dispatch-pipeline.sh` | 들어온 경로에 따라 파이프라인 선택 |
| `pipeline-rules.conf` | 경로 접두사 → 실행할 명령 (직접 생성) |
| `install-cron.sh` | cron 등록/해제 |

---

## 설치 (OCI 서버에서 1회)

### 1. rclone 설치

```bash
curl https://rclone.org/install.sh | sudo bash
rclone version
```

### 2. OneDrive 리모트 등록

서버에는 브라우저가 없으므로 **인증만 노트북에서** 하고 토큰을 붙여넣는다.

서버에서:

```bash
rclone config
```

- `n` (New remote) → 이름은 **`onedrive`**
- Storage → `onedrive`
- `client_id`, `client_secret` → 그냥 Enter (rclone 기본값 사용)
- Region → `global`
- **`Use auto config?` → `n`**  ← 헤드리스 서버라 반드시 n
- 화면에 `rclone authorize "onedrive"` 명령이 뜬다

노트북(브라우저 있는 PC)에서 rclone을 설치한 뒤 그 명령을 그대로 실행하면
Microsoft 로그인 창이 열린다. `J_Park@shaker.com.sa`로 로그인하면 터미널에
`{"access_token":...}` 형태의 토큰이 출력된다. **그 한 줄 전체를** 서버 쪽
프롬프트에 붙여넣는다.

- 이어서 드라이브 목록이 뜨면 **OneDrive (Business)** 항목을 고른다
- `y` 로 저장 → `q` 로 종료

확인:

```bash
rclone lsd onedrive:
rclone lsd "onedrive:문서/01. 2026/01. Work"
```

### 3. 설정 3종 작성

```bash
cd ~/Shaker-MD-App/onedrive-sync
cp sync-map.conf.example       sync-map.conf
cp sync-settings.conf.example  sync-settings.conf
cp pipeline-rules.conf.example pipeline-rules.conf
```

`sync-map.conf`의 경로를 **`rclone lsd`로 확인한 실제 경로**로 고친다.
서버 경로(`/home/ubuntu/2026/10. Automation`)도 실제 경로인지 확인한다 —
기존 백업 스크립트에서 역산한 추정값이다.

### 4. 디스크 확인 후 dry-run

```bash
df -h /home/ubuntu          # 최초 1회 ~700MB가 들어갈 여유가 있는지
./sync-onedrive-to-oci.sh --list      # 매핑과 가드 설정 확인
./sync-onedrive-to-oci.sh --dry-run   # 무엇이 복사될지
```

덮어쓰기는 두 겹으로 막혀 있다 — 화이트리스트에서 `.py`·`.html`·`.db`를 뺐고,
`KEEP_NEWER_ON_SERVER`가 서버 최신본을 지킨다. 그래도 dry-run 목록에 서버가
생성하는 산출물이 보이면 `INCLUDE_EXT`를 더 좁히십시오 — 서버 파일이 어쩌다
OneDrive 것보다 오래된 수정시각을 갖게 되면 갱신 대상이 된다.

### 5. cron 등록

```bash
./install-cron.sh              # 5분마다
./install-cron.sh "*/2 * * * *"  # 2분마다
./install-cron.sh --remove     # 해제
```

로그: `tail -f /home/ubuntu/onedrive_sync.log`

최초 회차는 수백 MB를 받으므로 오래 걸린다. `flock`으로 잠기므로 다음 cron
회차가 겹쳐 들어오지 않는다.

---

## 파이프라인 라우팅

폴더 하나를 통째로 받기 때문에, 무엇이 들어왔는지에 따라 실행할 작업이 달라진다.
`pipeline-rules.conf`가 그 매핑을 담는다:

```
00. Sell Thru Dashboard/ | cd /home/ubuntu/Shaker-MD-App && python3 -m automation-backup.sell-thru-dashboard.st_db
03. Operation/03. PSI/   | cd /home/ubuntu/Shaker-MD-App && python3 price-tracking/orchestrator.py
```

이번 회차에 그 접두사로 시작하는 파일이 **하나라도 들어온 경우에만** 명령이
한 번 실행된다. Sell Thru 파일만 들어왔다면 PSI 파이프라인은 돌지 않는다.

명령에 넘어가는 환경변수:

| 변수 | 내용 |
|------|------|
| `SYNC_NAME` | 매핑 이름 |
| `SYNC_LOCAL_DIR` | 내려받은 서버 폴더 |
| `SYNC_FILE_COUNT` | 이번 회차 전체 파일 수 |
| `SYNC_FILE_LIST` | 전체 파일 목록 파일 경로 |
| `SYNC_MATCHED_COUNT` | 이 규칙에 걸린 파일 수 |
| `SYNC_MATCHED_LIST` | 이 규칙에 걸린 파일 목록 파일 경로 |
| `SYNC_MATCHED_PREFIX` | 걸린 접두사 |

---

## 동작 특성

- **중복 실행 방지**: `flock`. 앞 회차가 아직 돌고 있으면 이번 회차는 건너뛴다.
- **삭제 전파 안 함**: `rclone copy`라서 OneDrive에서 파일을 지워도 서버 파일은 남는다.
- **부분 실패 격리**: 매핑 하나나 파이프라인 하나가 실패해도 나머지는 계속 진행하고,
  스크립트는 마지막에 exit 1로 끝나 로그에 흔적이 남는다.
- **제외 대상**: Office 임시파일(`~$*`), 잠금파일(`.~lock.*`), `*.tmp`, `.DS_Store`.
  `--include`와 `--exclude`를 섞으면 rclone이 평가 순서를 보장하지 않아
  `~$보고서.xlsx`가 화이트리스트에 먼저 걸릴 수 있다. 그래서 `--filter`로
  제외 규칙 → 화이트리스트 → 나머지 전부 제외 순서를 명시한다.

## 문제 해결

**`rclone authorize` 에서 관리자 승인을 요구하는 경우**
테넌트가 서드파티 앱을 막고 있는 것이다. Entra 관리자에게 rclone 승인을 요청하거나,
자체 앱을 등록(위임 권한 `Files.ReadWrite.All` + `offline_access`)한 뒤
`rclone config`의 `client_id`/`client_secret`에 그 값을 넣는다.

**디스크 부족으로 계속 중단되는 경우**
`sync-settings.conf`의 `INCLUDE_EXT`를 좁히거나, `sync-map.conf`의 대상을
`08. Automation` 전체 대신 필요한 하위 폴더만으로 바꾼다. 부모와 자식 폴더를
동시에 등록하면 같은 파일을 두 번 받으니 주의.

**cron에서만 실패하는 경우**
cron은 로그인 셸 환경변수를 물려받지 않는다. rclone 설정 경로를 명시한다:

```bash
RCLONE_CONFIG=/home/ubuntu/.config/rclone/rclone.conf
```

`.env` 값을 쓰는 파이프라인이라면 명령 앞에
`set -a; . /home/ubuntu/Shaker-MD-App/.env; set +a;` 를 붙인다.

**한글·공백 경로가 안 잡히는 경우**
설정 파일에서 경로에 따옴표를 붙이지 않았는지 확인한다. 파이프(`|`)로만
구분하고 나머지는 원문 그대로 적어야 한다.
