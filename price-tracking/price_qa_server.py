#!/usr/bin/env python3
"""
Price Q&A — 형님이 한국어로 물으면 DB를 조회해 답하는 실시간 대화 서버.

흐름: 질문 → LLM이 SQL 생성 → **안전 검증** → 읽기전용 조회 → LLM이 한국어 답변

자유 질의의 위험을 '막아서' 없애지 않는다. **보여줘서** 없앤다:
  - 실행한 SQL을 항상 함께 반환한다 (형님이 근거를 직접 볼 수 있게)
  - 조회 행수·기준일을 함께 반환한다
  - DB는 읽기전용으로만 연다. 쓰기 구문은 애초에 실행 불가.

실행: python3 price_qa_server.py  (기본 5071)

⚠️ 포트 주의: 5060/5061은 **Chrome이 차단**한다(SIP 예약 → net::ERR_UNSAFE_PORT).
   터널(443) 경유로는 문제없지만 로컬 테스트가 조용히 실패하므로 5071을 쓴다.
"""
import json
import os
import re
import sqlite3
import sys
import time
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request, Response

DB = Path("/home/ubuntu/2026/06. Price Tracking/price_data.db")
MAX_ROWS = 200

app = Flask(__name__)


def llm(messages, max_tokens=1400, temperature=0.0):
    """`claude -p` 로 텍스트 생성.

    왜 이걸 쓰나 (2026-08-31 실측):
      - 무료 NVIDIA NIM: deepseek-v4-flash(추론모델)는 2분 초과, 다수 모델은 404/타임아웃.
        대화형 UI를 떠받칠 수 없다.
      - `claude -p`: 5.5초, 정확. 이 시스템의 실행층으로 이미 쓰고 있고 구독이라 추가 비용 없음.

    ⚠️ 도구를 전부 끈다. 여기서 필요한 건 **순수 텍스트 생성**뿐이고,
       파일·셸 접근을 열어두면 통제할 수 없다.
    """
    sys_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_parts = [m["content"] for m in messages if m["role"] == "user"]
    prompt = "\n\n".join(user_parts)
    cmd = ["claude", "-p", "--allowedTools", "", "--max-turns", "1"]
    if sys_parts:
        cmd += ["--append-system-prompt", "\n\n".join(sys_parts)]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=150)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p 실패(rc={r.returncode}): {r.stderr[:300]}")
    return r.stdout.strip()


# ── 스키마 + 도메인 규칙 (LLM이 우리 데이터를 오해하지 않게) ────────────
SCHEMA = """
SQLite. 사우디 LG 에어컨 유통 11채널의 일별 가격 스냅샷.

channels(id, code, name, alert_basis, cond_discount)
  code: extra, bh, sws, najm, alkhunaizan, almanea, tamkeen, binmomen, blackbox, technobest, alkhater
products(id, channel_id, sku, brand, model, name_en, name_ar, category, btu, ton,
         compressor, ac_type, url, first_seen, last_seen, v6_model, v6_source)
  v6_model = LG 정본 모델코드(v6 마스터). 채널 간 동일 모델 비교는 반드시 이 컬럼으로.
             LG 상품의 97%에 부착됨. NULL이면 원본에 코드가 없는 상품.
price_snapshots(id, product_id, run_date, scraped_at, sp, sl, fp, fj,
                discount_pct, in_stock, stock_qty, promo_text, attrs, run_id)
  run_date 'YYYY-MM-DD', 상품×날짜 1행. 2026-01-27 ~ 현재.
  sp=표준가  sl=프로모가(기본 기준가)  fp=조건부할인 최종가  fj=멤버십가(Jood Gold 등)
sku_status_events(product_id, event_date, status, absent_days)
  status: 'new' | 'reactive' | 'temp_oos' | 'discontinued'

【반드시 지킬 규칙】
1. 가격은 COALESCE(s.sl, s.sp) 를 쓴다. sl이 기준가고 결측 시 sp 폴백.
2. 브랜드 비교는 반드시 UPPER(p.brand) — 원본에 Gree/GREE, Midea/MIDEA 혼재.
3. 오늘 날짜/date('now') 쓰지 말 것. 기준일은 (SELECT MAX(run_date) FROM price_snapshots).
   수집 결손일이 있어 오늘 데이터가 없을 수 있다.
4. Al Khater(code='alkhater')는 2026-05-11에 수집이 멈춘 채널이다. 최신 비교에서는 제외하거나
   따로 언급할 것.
5. 결과가 0건이면 "없다"고 단정하지 말고 조건을 넓힐 것.
6. BTU는 결측이 있다(NULL). 용량 비교 시 p.btu IS NOT NULL 조건을 넣을 것.
7. 채널 간 가격 비교는 **채널별 평균을 먼저 낸 뒤** 비교한다. 기간 전체 min/max를 쓰면
   프로모션 등락이 채널 편차로 둔갑한다.
8. 우리 브랜드는 'LG'. 주요 경쟁사는 SAMSUNG, GREE, MIDEA, HISENSE, TCL.
"""

SQL_SYS = f"""당신은 SQLite 전문가다. 아래 스키마로 사용자의 한국어 질문에 답할 SELECT 한 문장을 쓴다.

{SCHEMA}

【출력 형식】
SQL 한 문장만 출력한다. 설명·주석·마크다운 코드펜스 금지.
- 반드시 SELECT 또는 WITH 로 시작한다.
- 세미콜론을 쓰지 않는다.
- 반드시 LIMIT {MAX_ROWS} 이하를 포함한다.
- 컬럼에 사람이 읽을 별칭(AS)을 한국어로 붙인다.
- 금액은 ROUND(...) 로 정수화한다.
"""

ANSWER_SYS = """당신은 사우디 LG 에어컨 사업 책임자('형님')의 데이터 참모다.
조회 결과를 근거로 **한국어 존댓말**로 답한다.

- 숫자를 나열하지 말고 **의미**를 말한다. 마지막은 반드시 시사점이나 권고로 맺는다.
- 결과가 비었으면 "데이터가 없다"가 아니라 **왜 비었을지**(조건이 좁음/수집 결손/채널 정지)를 말한다.
- 표본이 적으면(3건 미만) 해석을 보류하라고 명시한다.
- 추측한 수치를 만들어내지 않는다. 결과에 있는 숫자만 쓴다.
- 3~6문장. 표가 필요하면 간단한 마크다운 표 1개까지.
"""

# ── 안전 검증 ────────────────────────────────────────────────────
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM|"
    r"REINDEX|TRIGGER|GRANT|LOAD_EXTENSION)\b", re.I)


def sanitize(sql: str) -> str:
    s = sql.strip()
    s = re.sub(r"^```(?:sql)?|```$", "", s, flags=re.I | re.M).strip()
    s = s.rstrip(";").strip()
    if ";" in s:
        raise ValueError("여러 문장은 실행하지 않습니다.")
    if not re.match(r"^(SELECT|WITH)\b", s, re.I):
        raise ValueError("SELECT 조회만 실행합니다.")
    if FORBIDDEN.search(s):
        raise ValueError("조회 외 구문이 포함되어 실행하지 않습니다.")
    if not re.search(r"\bLIMIT\s+\d+", s, re.I):
        s += f"\nLIMIT {MAX_ROWS}"
    return s


def run_sql(sql: str):
    """읽기전용 연결 + 시간제한. 쓰기는 구문 검증 이전에 연결 수준에서 이미 불가능하다."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    deadline = time.time() + 15
    con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10000)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [list(r) for r in cur.fetchmany(MAX_ROWS)]
        return cols, rows
    finally:
        con.close()


def anchor():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute("SELECT MAX(run_date) FROM price_snapshots").fetchone()[0]
    finally:
        con.close()


@app.after_request
def cors(r: Response):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return r


@app.route("/health")
def health():
    return jsonify({"ok": True, "anchor": anchor(), "db": str(DB)})


@app.route("/ask", methods=["POST", "OPTIONS"])
def ask():
    if request.method == "OPTIONS":
        return ("", 204)
    q = (request.json or {}).get("question", "").strip()
    if not q:
        return jsonify({"error": "질문이 비어 있습니다."}), 400

    t0 = time.time()
    hist = (request.json or {}).get("history") or []
    ctx = ""
    if hist:
        ctx = "\n\n【직전 대화 — 후속 질문일 수 있다】\n" + "\n".join(
            f"{h['role']}: {h['text'][:300]}" for h in hist[-4:])

    try:
        sql_raw = llm([{"role": "system", "content": SQL_SYS + ctx},
                       {"role": "user", "content": q}])
        sql = sanitize(sql_raw)
    except Exception as e:
        return jsonify({"error": f"질의 생성 실패: {e}", "sql": locals().get("sql_raw")}), 200

    try:
        cols, rows = run_sql(sql)
    except Exception as e:
        return jsonify({"error": f"조회 실패: {e}", "sql": sql}), 200

    preview = {"columns": cols, "rows": rows[:60], "row_count": len(rows)}
    try:
        answer = llm([
            {"role": "system", "content": ANSWER_SYS},
            {"role": "user", "content":
             f"질문: {q}\n\n실행한 SQL:\n{sql}\n\n결과(JSON):\n"
             f"{json.dumps(preview, ensure_ascii=False)[:6000]}\n\n"
             f"데이터 기준일: {anchor()}"},
        ], max_tokens=1200, temperature=0.3)
    except Exception as e:
        answer = f"(답변 생성 실패: {e}) 아래 조회 결과를 직접 확인해 주십시오."

    return jsonify({"answer": answer, "sql": sql, "columns": cols, "rows": rows,
                    "row_count": len(rows), "anchor": anchor(),
                    "elapsed": round(time.time() - t0, 1)})


@app.route("/ask_stream", methods=["POST", "OPTIONS"])
def ask_stream():
    """SSE. 26초를 통째로 기다리게 하지 않는다 —
    SQL이 나오면 즉시 보내고, 조회 결과 표를 먼저 띄운 뒤, 해설을 나중에 붙인다.
    형님은 10초쯤에 이미 숫자를 본다."""
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.json or {}
    q = (payload.get("question") or "").strip()
    hist = payload.get("history") or []

    def ev(kind, data):
        return f"data: {json.dumps({'type': kind, **data}, ensure_ascii=False)}\n\n"

    def gen():
        t0 = time.time()
        if not q:
            yield ev("error", {"message": "질문이 비어 있습니다."}); return
        yield ev("stage", {"stage": "sql", "text": "질문을 SQL로 옮기는 중…"})
        ctx = ""
        if hist:
            ctx = "\n\n【직전 대화 — 후속 질문일 수 있다】\n" + "\n".join(
                f"{h['role']}: {h['text'][:300]}" for h in hist[-4:])
        try:
            sql = sanitize(llm([{"role": "system", "content": SQL_SYS + ctx},
                                {"role": "user", "content": q}]))
        except Exception as e:
            yield ev("error", {"message": f"질의 생성 실패: {e}"}); return
        yield ev("sql", {"sql": sql, "elapsed": round(time.time() - t0, 1)})

        yield ev("stage", {"stage": "run", "text": "데이터 조회 중…"})
        try:
            cols, rows = run_sql(sql)
        except Exception as e:
            yield ev("error", {"message": f"조회 실패: {e}", "sql": sql}); return
        yield ev("rows", {"columns": cols, "rows": rows, "row_count": len(rows),
                          "anchor": anchor(), "elapsed": round(time.time() - t0, 1)})

        yield ev("stage", {"stage": "answer", "text": "해석하는 중…"})
        try:
            ans = llm([{"role": "system", "content": ANSWER_SYS},
                       {"role": "user", "content":
                        f"질문: {q}\n\n실행한 SQL:\n{sql}\n\n결과(JSON):\n"
                        f"{json.dumps({'columns': cols, 'rows': rows[:60], 'row_count': len(rows)}, ensure_ascii=False)[:6000]}\n\n"
                        f"데이터 기준일: {anchor()}"}], temperature=0.3)
        except Exception as e:
            ans = f"(해설 생성 실패: {e}) 위 표를 직접 확인해 주십시오."
        yield ev("answer", {"answer": ans, "elapsed": round(time.time() - t0, 1)})
        yield ev("done", {"elapsed": round(time.time() - t0, 1)})

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5071
    print(f"Price Q&A 서버 :{port}  DB={DB}  기준일={anchor()}")
    app.run(host="127.0.0.1", port=port, threaded=True)
