#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run_all_channels.py
===================
9개 채널 스크래핑 + 대시보드 파이프라인을 병렬 실행하는 메인 스크립트.
스케줄러(Task Scheduler 등)에 이 파일 1개만 등록하면 됩니다.

실행: py -X utf8 run_all_channels.py
옵션:
  --only 0,3,5        특정 채널만 실행 (0-indexed)
  --skip 6,7          특정 채널 건너뛰기
  --workers N         동시 실행 채널 수 (기본: 2, 최대: 3)
  --stop-on-fail      채널 실패 시 전체 중단 (기본: 계속 진행)
  --no-ai-repair      실패 채널 AI 자동 수정 비활성화
  --no-notify         텔레그램 알림 비활성화
  --no-db             SQLite DB 기록 비활성화
"""

import subprocess
import sys
import os
import time
import io
import argparse
import urllib.request
import urllib.parse
import json
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# ── Windows UTF-8 콘솔 설정 ──────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 경로 설정 ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "99. Logs")
PYTHON = "py" if sys.platform == "win32" else sys.executable

# ── mybot 디렉토리 (텔레그램 .env 위치) ──────────────────────
_WORK_DIR = os.path.dirname(BASE_DIR)  # 01. Work

def _find_mybot_dir():
    """99. Claude_Setting 아래에서 .env 파일이 있는 mybot 디렉토리를 자동 탐색"""
    setting_dir = os.path.join(_WORK_DIR, "99. Claude_Setting")
    if not os.path.isdir(setting_dir):
        return None
    for top in os.listdir(setting_dir):
        top_path = os.path.join(setting_dir, top)
        if not os.path.isdir(top_path):
            continue
        # 같은 이름의 하위 폴더 탐색 (mybot_ver2/.../mybot_ver2/...)
        for sub in os.listdir(top_path):
            sub_path = os.path.join(top_path, sub)
            if os.path.isdir(sub_path) and os.path.isfile(os.path.join(sub_path, ".env")):
                return sub_path
        # 직접 .env가 있는 경우
        if os.path.isfile(os.path.join(top_path, ".env")):
            return top_path
    return None

_MYBOT_DIR = _find_mybot_dir() or ""

# ── Telegram 설정 로드 ────────────────────────────────────────
def _load_telegram_config():
    """mybot .env에서 텔레그램 설정 로드"""
    try:
        env_path = os.path.join(_MYBOT_DIR, ".env")
        if not os.path.isfile(env_path):
            return None, None
        token = None
        chat_ids = []
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip()
                if key == "TELEGRAM_BOT_TOKEN":
                    token = val
                elif key == "TELEGRAM_ALLOWED_USERS":
                    chat_ids = [int(x.strip()) for x in val.split(",") if x.strip().lstrip("-").isdigit()]
        return (token, chat_ids[0]) if token and chat_ids else (None, None)
    except Exception:
        return None, None


_TG_TOKEN, _TG_CHAT_ID = _load_telegram_config()


def notify_telegram(msg, silent=False):
    """텔레그램으로 메시지 전송 (실패해도 계속 진행)"""
    if not _TG_TOKEN or not _TG_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
        payload = {
            "chat_id": _TG_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_notification": silent,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  [Telegram 알림 실패: {e}]", flush=True)


# ── Claude Code 실행 경로 ────────────────────────────────────
def _find_claude_exe():
    candidates = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        cc_dir = os.path.join(appdata, "Claude", "claude-code")
        if os.path.isdir(cc_dir):
            for ver in sorted(os.listdir(cc_dir), reverse=True):
                p = os.path.join(cc_dir, ver, "claude.exe")
                if os.path.isfile(p):
                    candidates.append(p)
                    break
        user_local = os.path.join(os.path.expanduser("~"), ".local", "bin", "claude.exe")
        if os.path.isfile(user_local):
            candidates.append(user_local)
    else:
        # Linux / macOS: claude는 PATH 또는 ~/.local/bin에 설치됨
        import shutil as _shutil
        claude_in_path = _shutil.which("claude")
        if claude_in_path:
            candidates.append(claude_in_path)
        for p in [
            os.path.join(os.path.expanduser("~"), ".local", "bin", "claude"),
            "/usr/local/bin/claude",
            "/usr/bin/claude",
        ]:
            if os.path.isfile(p) and p not in candidates:
                candidates.append(p)
    for c in candidates:
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=5)
            return c
        except Exception:
            continue
    return None


_CLAUDE_EXE = _find_claude_exe()

# ── 채널 정의 (순서 = 실행 순서) ─────────────────────────────
CHANNELS = [
    {"name": "eXtra",        "dir": "00. eXtra",        "script": "extra_ac_run_all.py",  "timeout": 60 * 60},
    {"name": "BH",           "dir": "01. BH",           "script": "bh_ac_run_all.py"},
    {"name": "SWS",          "dir": "02. SWS",          "script": "sws_ac_run.py"},
    {"name": "Najm Store",   "dir": "03. Najm Store",   "script": "najm_ac_run.py"},
    {"name": "Al Khunizan",  "dir": "04. Al Khunizan",  "script": "alkhunaizan_ac_run_all.py"},
    {"name": "Al Manea",     "dir": "05. Al Manea",     "script": "almanea_ac_pipeline.py"},
    {"name": "Tamkeen",      "dir": "06. Tamkeen",      "script": "tamkeen_run.py"},
    {"name": "Bin Momen",    "dir": "07. Bin Momen",    "script": "binmomen_run.py"},
    {"name": "Black Box",    "dir": "08. Black Box",    "script": "blackbox_ac_run_all.py"},
    {"name": "Techno Best",  "dir": "09. Techno Best",  "script": "technobest_ac_run.py"},
]

TIMEOUT_SEC = 30 * 60  # 채널당 기본 최대 30분 (채널별 "timeout" 키로 개별 설정 가능)
DEFAULT_WORKERS = 2    # 기본 동시 실행 채널 수

# ── DB 관리자 (선택적 로드) ───────────────────────────────────
_db = None

def _get_db():
    global _db
    if _db is None:
        try:
            from db_manager import PriceTrackingDB
            _db = PriceTrackingDB()
        except Exception as e:
            print(f"  [DB] 초기화 실패 (무시하고 계속): {e}", flush=True)
    return _db

# ── 로그 락 (병렬 실행 시 stdout 보호) ───────────────────────
_log_lock = threading.Lock()


def log(msg, file=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with _log_lock:
        print(line, flush=True)
        if file:
            file.write(line + "\n")
            file.flush()


def run_channel(idx, ch, log_file, batch_id=None, total=None):
    """단일 채널 실행. 성공=True, 실패=False"""
    name = ch["name"]
    script_dir = os.path.join(BASE_DIR, ch["dir"])
    script_path = os.path.join(script_dir, ch["script"])
    total_str = f"/{total}" if total else f"/{len(CHANNELS)}"

    log(f"{'='*60}", log_file)
    log(f"[{idx+1}{total_str}] {name} 시작 — {ch['script']}", log_file)

    if not os.path.isfile(script_path):
        log(f"  ✗ 스크립트 없음: {script_path}", log_file)
        return False

    # DB 실행 기록 시작
    run_id = None
    if batch_id:
        db = _get_db()
        if db:
            try:
                run_id = db.start_run(batch_id, name)
            except Exception:
                pass

    t0 = time.time()
    ch_timeout = ch.get("timeout", TIMEOUT_SEC)
    rc = None
    try:
        result = subprocess.run(
            [PYTHON, "-X", "utf8", "-u", ch["script"]],
            cwd=script_dir,
            timeout=ch_timeout,
            stdin=subprocess.DEVNULL,
        )
        elapsed = time.time() - t0
        rc = result.returncode
        if rc == 0:
            log(f"  ✓ {name} 완료 ({elapsed:.0f}s)", log_file)
            if run_id and batch_id:
                db = _get_db()
                if db:
                    try:
                        db.end_run(run_id, success=True, duration_sec=elapsed, returncode=rc)
                    except Exception:
                        pass
            return True
        else:
            log(f"  ✗ {name} 실패 (returncode={rc}, {elapsed:.0f}s)", log_file)
            if run_id and batch_id:
                db = _get_db()
                if db:
                    try:
                        db.end_run(run_id, success=False, duration_sec=elapsed,
                                   returncode=rc, error_msg=f"returncode={rc}")
                    except Exception:
                        pass
            return False
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        log(f"  ✗ {name} 타임아웃 ({ch_timeout}s 초과)", log_file)
        if run_id and batch_id:
            db = _get_db()
            if db:
                try:
                    db.end_run(run_id, success=False, duration_sec=elapsed,
                               error_msg="timeout")
                except Exception:
                    pass
        return False
    except FileNotFoundError:
        log(f"  ✗ Python 인터프리터를 찾을 수 없음 ({PYTHON})", log_file)
        return False
    except Exception as e:
        elapsed = time.time() - t0
        log(f"  ✗ {name} 예외 발생: {e} ({elapsed:.0f}s)", log_file)
        if run_id and batch_id:
            db = _get_db()
            if db:
                try:
                    db.end_run(run_id, success=False, duration_sec=elapsed,
                               error_msg=str(e))
                except Exception:
                    pass
        return False


def ai_repair_channel(ch, log_file, run_id=None, batch_id=None):
    """실패 채널을 Claude Code AI로 진단·수정 후 재실행. 성공=True, 실패=False"""
    if not _CLAUDE_EXE:
        log("  [AI 수정] Claude Code 실행 파일을 찾을 수 없어 건너뜀", log_file)
        return False

    name = ch["name"]
    script_dir = os.path.join(BASE_DIR, ch["dir"])

    # 최근 로그 파일 경로 (에러 참고용)
    log_files = sorted(Path(LOG_DIR).glob("run_all_*.log"), reverse=True)
    recent_log_path = str(log_files[0]) if log_files else "(없음)"

    notify_telegram(f"[{name}] AI 수정 시작 - 코드 진단 중...")
    log(f"  [AI 수정] {name} — Claude Code 기동 중", log_file)

    # DB AI 수정 기록 시작
    repair_id = None
    db = _get_db()
    if db and run_id:
        try:
            repair_id = db.log_ai_repair(run_id, name)
        except Exception:
            pass

    prompt = (
        f"Price tracking channel '{name}' failed.\n\n"
        f"Channel directory: {script_dir}\n"
        f"Failed script: {ch['script']}\n"
        f"Run log (for error details): {recent_log_path}\n\n"
        f"Tasks:\n"
        f"1. Read the recent run log to find the error\n"
        f"2. Check {ch['script']} for root cause (website change, missing package, logic error, etc.)\n"
        f"3. Fix the issue\n"
        f"4. Re-run: py -X utf8 {ch['script']} (cwd={script_dir})\n"
        f"5. Report result to Telegram:\n"
        f"   import sys; sys.path.insert(0, r'{_MYBOT_DIR}')\n"
        f"   from telegram_sender import send_message_sync\n"
        f"   send_message_sync({_TG_CHAT_ID}, 'AI 수정 결과 [{name}]: 성공/실패 + 요약')\n"
    )

    t0 = time.time()
    try:
        result = subprocess.run(
            [_CLAUDE_EXE, "-p", "--dangerously-skip-permissions", prompt],
            cwd=script_dir,
            timeout=20 * 60,   # 20분 제한
            stdin=subprocess.DEVNULL,
        )
        elapsed = time.time() - t0
        ok = result.returncode == 0
        log(f"  [AI 수정] {name} — {'성공' if ok else '실패'} (rc={result.returncode})", log_file)

        if db and repair_id:
            try:
                db.end_ai_repair(repair_id, success=ok, exit_code=result.returncode)
            except Exception:
                pass
        if db and run_id:
            try:
                db.end_run(run_id, success=ok, duration_sec=elapsed,
                           ai_tried=True, ai_ok=ok, ai_sec=elapsed,
                           returncode=result.returncode)
            except Exception:
                pass
        return ok
    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        log(f"  [AI 수정] {name} — 20분 타임아웃", log_file)
        notify_telegram(f"[{name}] AI 수정 타임아웃 (20분 초과)")
        if db and repair_id:
            try:
                db.end_ai_repair(repair_id, success=False, error_type="timeout")
            except Exception:
                pass
        return False
    except Exception as e:
        log(f"  [AI 수정] {name} — 오류: {e}", log_file)
        if db and repair_id:
            try:
                db.end_ai_repair(repair_id, success=False, error_type="unknown",
                                 fix_desc=str(e))
            except Exception:
                pass
        return False


def _run_channel_with_repair(idx, ch, log_file, args, batch_id, total):
    """채널 실행 + 실패 시 AI 수정 (병렬 워커용). (name, ok, ai_fixed) 반환"""
    name = ch["name"]
    ok = run_channel(idx, ch, log_file, batch_id=batch_id, total=total)

    if not ok:
        notify_telegram(
            f"[{idx+1}/{total}] {name} 실패\n"
            f"AI 수정 {'시작' if not args.no_ai_repair else '비활성화'}"
        )
        if not args.no_ai_repair:
            repaired = ai_repair_channel(ch, log_file)
            if repaired:
                ok = True
                log(f"  → {name} AI 수정 후 성공!", log_file)
                notify_telegram(f"[{name}] AI 수정 완료!")
                return name, True, True  # (name, success, ai_fixed)

    return name, ok, False


def main():
    parser = argparse.ArgumentParser(description="9개 채널 병렬 실행")
    parser.add_argument("--only", type=str, default=None,
                        help="실행할 채널 인덱스 (콤마 구분, 0-based). 예: --only 0,3,5")
    parser.add_argument("--skip", type=str, default=None,
                        help="건너뛸 채널 인덱스 (콤마 구분). 예: --skip 6,7")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"동시 실행 채널 수 (기본: {DEFAULT_WORKERS}, 최대: 3)")
    parser.add_argument("--stop-on-fail", action="store_true",
                        help="채널 실패 시 전체 중단")
    parser.add_argument("--no-ai-repair", action="store_true",
                        help="실패 채널 AI 자동 수정 비활성화")
    parser.add_argument("--no-notify", action="store_true",
                        help="텔레그램 알림 비활성화")
    parser.add_argument("--no-db", action="store_true",
                        help="SQLite DB 기록 비활성화")
    args = parser.parse_args()

    # 최대 workers 제한 (3개 초과 시 과부하 위험)
    workers = max(1, min(args.workers, 3))

    # 알림 비활성화 옵션
    if args.no_notify:
        global _TG_TOKEN
        _TG_TOKEN = None

    # 실행 대상 결정
    if args.only:
        indices = [int(x.strip()) for x in args.only.split(",")]
    elif args.skip:
        skip = {int(x.strip()) for x in args.skip.split(",")}
        indices = [i for i in range(len(CHANNELS)) if i not in skip]
    else:
        indices = list(range(len(CHANNELS)))

    total = len(indices)

    # 로그 파일 준비
    os.makedirs(LOG_DIR, exist_ok=True)
    log_name = datetime.now().strftime("run_all_%Y%m%d_%H%M%S.log")
    log_path = os.path.join(LOG_DIR, log_name)

    # 배치 ID (이번 실행 묶음 식별자)
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]

    total_start = time.time()
    results = {}        # name → True/False (최종 결과)
    ai_fixed = []       # AI가 수정 성공한 채널 목록

    # ── DB 배치 시작 기록 ─────────────────────────────────────
    if not args.no_db:
        db = _get_db()
        if db:
            try:
                db.start_batch(batch_id, total)
            except Exception as e:
                log(f"[DB] 배치 시작 기록 실패: {e}", None)

    # ── 시작 알림 ────────────────────────────────────────────
    notify_telegram(
        f"Price Tracking 시작\n"
        f"{total}개 채널 / 동시 {workers}개 / {datetime.now().strftime('%m/%d %H:%M')}"
    )

    # ── SKU Status Tracker 자동 패치 (재발 방지) ──────────
    # 빌더 .py가 어떤 이유로 패치 없는 상태가 돼도 매 cron마다 자동 재적용.
    # idempotent — 이미 패치된 채널은 스킵. 채널 빌드 전에 실행하여 이번 cron부터 적용됨.
    sku_apply_path = '/home/ubuntu/Shaker-MD-App/price-tracking/apply_sku_status_tracker.py'
    if os.path.isfile(sku_apply_path):
        try:
            log("[SKU Status] 빌더 .py 패치 적용 (idempotent)", None)
            r = subprocess.run(
                [PYTHON, "-X", "utf8", sku_apply_path],
                timeout=5 * 60,
                stdin=subprocess.DEVNULL,
                capture_output=True, text=True,
            )
            log(f"[SKU Status] rc={r.returncode}", None)
        except Exception as e:
            log(f"[SKU Status 오류] {e}", None)

    stop_flag = threading.Event()

    with open(log_path, "w", encoding="utf-8") as lf:
        log(f"전체 파이프라인 시작 — {total}개 채널 / 동시 {workers}개", lf)
        log(f"로그 파일: {log_path}", lf)
        log(f"AI 수정: {'OFF' if args.no_ai_repair else 'ON'}", lf)
        log(f"배치 ID: {batch_id}", lf)

        if workers == 1:
            # ── 순차 실행 (workers=1) ─────────────────────────
            for idx in indices:
                if stop_flag.is_set():
                    break
                ch = CHANNELS[idx]
                name, ok, was_ai_fixed = _run_channel_with_repair(
                    idx, ch, lf, args, batch_id, total
                )
                results[name] = ok
                if was_ai_fixed:
                    ai_fixed.append(name)
                if not ok and args.stop_on_fail:
                    log(f"--stop-on-fail: {name} 실패로 중단", lf)
                    notify_telegram(f"--stop-on-fail: {name} 실패로 전체 중단")
                    stop_flag.set()
        else:
            # ── 병렬 실행 (workers>1) ────────────────────────
            futures = {}
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for idx in indices:
                    if stop_flag.is_set():
                        break
                    ch = CHANNELS[idx]
                    fut = executor.submit(
                        _run_channel_with_repair,
                        idx, ch, lf, args, batch_id, total
                    )
                    futures[fut] = ch["name"]

                for fut in as_completed(futures):
                    ch_name = futures[fut]
                    try:
                        name, ok, was_ai_fixed = fut.result()
                        results[name] = ok
                        if was_ai_fixed:
                            ai_fixed.append(name)
                        if not ok and args.stop_on_fail:
                            log(f"--stop-on-fail: {name} 실패로 중단 신호", lf)
                            notify_telegram(f"--stop-on-fail: {name} 실패로 전체 중단")
                            stop_flag.set()
                    except Exception as e:
                        log(f"  ✗ {ch_name} 예외 (future): {e}", lf)
                        results[ch_name] = False

        # ── 결과 요약 ────────────────────────────────────────
        elapsed_total = time.time() - total_start
        success = [n for n, ok in results.items() if ok]
        failed  = [n for n, ok in results.items() if not ok]

        log(f"{'='*60}", lf)
        log(f"전체 완료 — {elapsed_total:.0f}s ({elapsed_total/60:.1f}분)", lf)
        log(f"  성공: {len(success)}/{len(results)} {success}", lf)
        if failed:
            log(f"  실패: {len(failed)}/{len(results)} {failed}", lf)
        if ai_fixed:
            log(f"  AI 수정 후 성공: {ai_fixed}", lf)

    # ── DB 배치 완료 기록 ─────────────────────────────────────
    if not args.no_db:
        db = _get_db()
        if db:
            try:
                db.end_batch(
                    batch_id,
                    success=len(success),
                    failed=len(failed),
                    ai_repaired=len(ai_fixed),
                    duration=elapsed_total
                )
            except Exception as e:
                log(f"[DB] 배치 완료 기록 실패: {e}", None)

    # ── 완료 알림 ────────────────────────────────────────────
    lines = [
        f"Price Tracking 완료 ({elapsed_total/60:.0f}분)",
        f"성공 {len(success)}/{len(results)}",
    ]
    if failed:
        lines.append(f"실패: {', '.join(failed)}")
    if ai_fixed:
        lines.append(f"AI 수정 성공: {', '.join(ai_fixed)}")
    notify_telegram("\n".join(lines))

    # ── operation_status.json 업데이트 ────────────────────────
    try:
        import json as _json
        _op_status_file = os.path.join(os.path.dirname(BASE_DIR), "sonolbot", "operation_status.json")
        if not os.path.exists(_op_status_file):
            _op_status_file = "/home/ubuntu/sonolbot/operation_status.json"
        try:
            with open(_op_status_file) as f:
                _op_data = _json.load(f)
        except Exception:
            _op_data = {"sap": {}, "price": {}}
        _op_data["price"] = {
            "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_status": "success" if not failed else "partial_fail",
            "last_success_count": f"{len(success)}/{len(results)}",
            "failed_channels": failed,
            "next_run": "매일 03:00 (KSA)"
        }
        _op_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_op_status_file, 'w') as f:
            _json.dump(_op_data, f, ensure_ascii=False, indent=2)
    except Exception as _e:
        log(f"[operation_status 업데이트 실패] {_e}", None)

    # ── 주간 보고서 자동 생성 (수요일에만) ─────────────────────────
    if not args.no_notify:
        try:
            weekday = datetime.now().weekday()  # 0=월, 2=수
            if weekday == 2:  # 수요일
                log("[주간보고] 수요일 감지 → 주간 보고서 자동 생성 시작", None)
                notify_telegram("📊 주간 보고서 생성 중...")
                report_result = subprocess.run(
                    [PYTHON, "-X", "utf8", os.path.join(BASE_DIR, "weekly_report_generator.py")],
                    cwd=BASE_DIR,
                    timeout=10 * 60,
                    stdin=subprocess.DEVNULL,
                )
                if report_result.returncode != 0:
                    log(f"[주간보고] 생성 실패 (rc={report_result.returncode})", None)
            else:
                notify_telegram(
                    f"✅ Price Tracking 완료 ({datetime.now().strftime('%m/%d')})\n"
                    f"주간 보고서는 매주 수요일 자동 생성됩니다."
                )
        except Exception as e:
            log(f"[주간보고 오류] {e}", None)

    # 실패 채널이 있으면 exit code 1
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
