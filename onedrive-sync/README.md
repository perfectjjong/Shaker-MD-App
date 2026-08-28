# OneDrive → OCI 서버 동기화

OneDrive의 지정 폴더에 파일이 올라오면 OCI 서버의 대응 폴더로 내려받고,
새 파일이 감지되면 해당 매핑에 등록된 파이프라인을 자동 실행한다.

- **방향**: 단방향 (OneDrive → OCI). 서버에서 OneDrive로는 아무것도 쓰지 않는다.
- **트리거**: cron 폴링 (기본 5분). rclone이 변경분만 전송한다.
- **인증**: rclone이 OneDrive OAuth를 자체 처리한다.

## 왜 웹훅이 아니라 폴링인가

Graph 변경 알림(웹훅)은 OCI 서버에 공인 HTTPS 엔드포인트를 열고 구독을
며칠마다 갱신해야 한다. 반면 rclone 폴링은 열어야 할 포트가 없고,
서버가 잠깐 죽어도 다음 회차에 알아서 따라잡는다. 대신 지연이 cron 주기만큼
생긴다. 초 단위 반영이 꼭 필요해지면 그때 웹훅을 얹으면 된다.

## 구성 파일

| 파일 | 역할 |
|------|------|
| `sync-onedrive-to-oci.sh` | 동기화 본체 |
| `sync-map.conf` | 폴더 매핑 + 파이프라인 (직접 생성) |
| `sync-map.conf.example` | 매핑 작성 예시 |
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
rclone lsd "onedrive:문서/01. 2026/01. Work/08. Automation"
```

폴더 목록이 나오면 성공이다.

### 3. 매핑 작성

```bash
cd ~/Shaker-MD-App/onedrive-sync
cp sync-map.conf.example sync-map.conf
vi sync-map.conf
```

`rclone lsd`로 확인한 **실제 경로**로 고친다. 예시 경로는 추정값이라
그대로 쓰면 안 된다.

### 4. dry-run으로 먼저 확인 (중요)

```bash
./sync-onedrive-to-oci.sh --list      # 매핑이 제대로 파싱되는지
./sync-onedrive-to-oci.sh --dry-run   # 무엇이 복사될지
```

⚠️ 단방향 복사는 **OneDrive 쪽 파일이 서버의 같은 이름 파일을 덮어쓴다.**
`sell_thru.db`나 생성된 대시보드 html처럼 **서버가 직접 만드는 산출물이 있는
폴더**를 대상으로 잡으면 그게 날아갈 수 있다. dry-run 목록에 그런 파일이
보이면 매핑 대상을 `inbox` 하위 폴더로 바꾸십시오
(`sync-map.conf.example`의 inbox 예시 참고).

### 5. cron 등록

```bash
./install-cron.sh              # 5분마다
./install-cron.sh "*/2 * * * *"  # 2분마다
./install-cron.sh --remove     # 해제
```

로그: `/home/ubuntu/onedrive_sync.log`

```bash
tail -f /home/ubuntu/onedrive_sync.log
```

---

## 파이프라인 자동 실행

매핑의 4번째 칸에 명령을 적으면 **그 매핑에 새 파일이 실제로 들어온 회차에만**
실행된다. 변경이 없으면 실행되지 않는다.

넘어가는 환경변수:

| 변수 | 내용 |
|------|------|
| `SYNC_NAME` | 매핑 이름 |
| `SYNC_LOCAL_DIR` | 내려받은 서버 폴더 |
| `SYNC_REMOTE_PATH` | OneDrive 원본 경로 |
| `SYNC_FILE_COUNT` | 이번에 들어온 파일 수 |
| `SYNC_FILE_LIST` | 파일 목록이 한 줄에 하나씩 담긴 임시 파일 경로 |

파이프라인이 실패해도 다른 매핑의 동기화는 계속 진행되고, 스크립트는
마지막에 exit 1로 끝나 cron 로그에 흔적이 남는다.

---

## 동작 특성

- **중복 실행 방지**: `flock`으로 잠근다. 앞 회차가 아직 돌고 있으면 이번 회차는 건너뛴다.
- **삭제 전파 안 함**: `rclone copy`라서 OneDrive에서 파일을 지워도 서버 파일은 남는다.
  (삭제까지 맞추려면 `copy`를 `sync`로 바꿔야 하는데, 서버 파일이 지워질 수 있어 기본값으로 두지 않았다.)
- **제외 대상**: Office 임시파일(`~$*`), 잠금파일(`.~lock.*`), `*.tmp`, `.DS_Store`
- **재시도**: rclone 자체 재시도 3회 + 저수준 10회

## 문제 해결

**`rclone authorize` 에서 관리자 승인을 요구하는 경우**
테넌트가 서드파티 앱을 막고 있는 것이다. Entra 관리자에게 rclone 승인을 요청하거나,
자체 앱을 등록(위임 권한 `Files.ReadWrite.All` + `offline_access`)한 뒤
`rclone config`의 `client_id`/`client_secret`에 그 값을 넣는다.

**cron에서만 실패하는 경우**
cron은 로그인 셸 환경변수를 물려받지 않는다. rclone 설정 경로를 명시한다:

```bash
RCLONE_CONFIG=/home/ubuntu/.config/rclone/rclone.conf
```

Telegram 알림 예시처럼 `.env` 값을 쓰는 파이프라인이라면 명령 앞에
`set -a; . /home/ubuntu/Shaker-MD-App/.env; set +a;` 를 붙인다.

**한글·공백 경로가 안 잡히는 경우**
`sync-map.conf`에서 경로에 따옴표를 붙이지 않았는지 확인한다. 파이프(`|`)로만
구분하고 나머지는 원문 그대로 적어야 한다.
