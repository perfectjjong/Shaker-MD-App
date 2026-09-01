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
SQLite. 사우디 LG 에어컨 유통 11채널의 일별 가격 스냅샷 DB.

🟢 **먼저 이 두 층을 써라. 원시 테이블은 여기로 안 되는 것만.**
   품질 판정(최신 스냅샷·지연·결함 제외)이 이미 끝나 있어 질의가 한 줄로 끝난다.

━━ ① product_current — 상품별 '지금' 상태 (1상품 1행, 3,383행) ━━
  channel_code, channel_name          채널 (extra/bh/sws/najm/alkhunaizan/almanea/
                                       tamkeen/binmomen/blackbox/technobest/alkhater)
  brand                               대문자 정규화 완료 (UPPER 다시 걸 필요 없음)
  v6_model                            LG 정본 모델코드. 채널 간 동일 모델 비교는 이것으로.
                                       LG의 96%에 부착. 비LG는 NULL(v6는 LG 마스터라 정상)
  sku, name_en, btu, ton, compressor, category
  px                                  현재가(프로모가 우선, 없으면 표준가). 이미 정리됨
  sp                                  표준가
  discount_pct                        할인율 %
  in_stock                            1=재고있음 0=품절 NULL=미상
  run_date                            이 값이 확인된 날짜
  lag_days                            기준일로부터 며칠 지났나
  is_live                             1=현재 판매중(지연 3일 이내) / 0=아님
  status                              '판매중 · 재고있음' / '판매중 · 품절' /
                                       '미판매 · N일째 리스팅 없음' / '수집중단 · 채널 최종수집 …'

  ▶ **현재 가격/재고를 묻는 질문은 거의 다 이 표 한 장으로 끝난다.**
    예) SELECT channel_name, sku, px, status FROM product_current WHERE v6_model='ND182C'

━━ ② v_price_clean — 가격 시계열 (결함 스냅샷 판정 포함, 314,863행) ━━
  product_id, run_date, px, sp, sl, fp, discount_pct, in_stock
  prev_px, next_px                    앞뒤 값 (변동 계산용, 직접 LAG 짤 필요 없음)
  is_spike                            1 = 하루 튀었다 원위치 (프로모가 미포착일 = 가짜 변동)
  is_incons                           1 = 할인율은 있는데 판매가=표준가 (모순)
  ▶ 추이·변동 질문은 이 뷰를 쓰고 **반드시 is_spike=0 AND is_incons=0** 을 건다.
    products/channels 와 조인해야 브랜드·채널을 볼 수 있다.

━━ ③ 원시 테이블 (위 둘로 안 되는 경우만) ━━
  channels(id, code, name)
  products(id, channel_id, sku, brand, model, name_en, name_ar, category,
           btu, ton, compressor, ac_type, url, first_seen, last_seen, v6_model, v6_source)
  price_snapshots(id, product_id, run_date, sp, sl, fp, fj, discount_pct,
                  in_stock, stock_qty, promo_text, attrs)
    sp=표준가 sl=프로모가 fp=조건부할인 최종가
    🔴 fj는 가격이 아니다(eXtra는 판매가의 1/20 적립성 금액). SELECT 하지 말 것.
  sku_status_events(product_id, event_date, status)  status: new/reactive/temp_oos/discontinued

【지킬 것 — 짧다】
1. **현재 상태 = product_current, 시계열 = v_price_clean.** 원시 테이블에서 최신 스냅샷을
   직접 뽑지 마라(ROW_NUMBER 같은 걸 다시 짜면 함정에 빠진다).
2. **'지금/현재/최신'을 물으면 is_live=1 로 거른다.** 지연된 값을 현재가로 내놓지 않는다.
   지연 행도 보여줄 땐 run_date·status 를 같이 내서 언제 값인지 알 수 있게 한다.
3. date('now') 금지. 기준일은 (SELECT MAX(run_date) FROM price_snapshots).
4. 우리 브랜드 = 'LG'. **주요 경쟁사 = GREE · MIDEA · TCL** (형님 확정).
   '경쟁사'라고만 하면 이 3사다. 다른 브랜드(SAMSUNG·HISENSE·MANDO·HAIER 등)는
   **이름을 명시했을 때 그 브랜드로** 답한다. 로컬 저가 브랜드를 경쟁 평균에 섞으면
   프리미엄이 부풀려진다(실측 +35.4% vs +19.5%).
5. 결과가 0건이면 단정하지 말고 조건을 넓혀라. btu는 결측이 있다.
6. 컬럼에 한국어 별칭(AS)을 붙이고 금액은 ROUND 한다.
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
- 🔴 **'현재/최신' 질문에 지연된 값을 현재가로 말하지 않는다.**
  결과에 지연일수(또는 날짜)가 있으면, **지연 3일 초과 행은 '현재가 아님'으로 분리**해 말한다.
  최저가·최고가를 꼽을 때도 **신선한 행(지연 0~3일) 안에서만** 고른다.
  지연 행은 '○일 전 값'이라고 반드시 명시한다.
- 🔴 가격으로 제시하는 값이 다른 채널 대비 1/5 이하로 터무니없이 낮으면 가격이 아닐 수 있다.
  그대로 옮기지 말고 이상함을 지적한다.
- 3~6문장. 표가 필요하면 간단한 마크다운 표 1개까지.
"""

# ── 검증된 질의 템플릿 ───────────────────────────────────────────
# 🔴 왜 필요한가 (2026-08-31 형님 지적 "오답을 안내하네, 신뢰도가 엄청 떨어지네"):
#    LLM이 매번 SQL을 새로 지으면 **같은 질문에 다른 답**이 나온다.
#    "NS182C 최신가를 유통별로" 질문에서 전역 MAX(run_date)로 거르는 SQL이 나오면
#    10개 채널 중 6개만 나오고 4개가 소리 없이 누락된다.
#    → 흔한 질문 유형은 **손으로 검증한 고정 SQL**로 처리해 항상 같은 정답이 나오게 한다.
#      템플릿에 안 걸리는 질문만 LLM이 짓는다(자유 질의는 그대로 유지).

def _canon_or_none(code):
    """ssot_model_name.canon() 로 v6 정본 표기 복원. 실패해도 질의는 계속돼야 하므로 삼킨다."""
    try:
        sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
        from ssot_model_name import canon
        return canon(code)
    except Exception:
        return None


MODEL_RE = re.compile(r"\b([A-Z]{2,5}[A-Z0-9]{2,}\d[A-Z0-9]*)\b", re.I)
CH_WORDS = ("채널별", "유통별", "유통사별", "채널 별", "유통 별", "채널마다", "유통마다",
            "채널간", "채널 간", "어디가 싼", "어디서 싼", "매장별")
LATEST_WORDS = ("최신", "최근", "지금", "현재", "요즘", "오늘")

SQL_MODEL_LATEST_BY_CHANNEL = """
-- 규칙(신선도·판매여부·결함제외)은 v_product_current 안에 있다. 여기서 다시 쓰지 않는다.
SELECT channel_name AS 유통채널, sku AS SKU,
       CASE WHEN is_live=1 THEN ROUND(px) END AS 현재_프로모가,
       CASE WHEN is_live=1 THEN ROUND(sp) END AS 현재_표준가,
       CASE WHEN is_live=1 THEN ROUND(discount_pct,1) END AS 할인율_pct,
       CASE WHEN is_live=0 THEN ROUND(px) END AS 과거값_참고용,
       run_date AS 확인일, lag_days AS 지연일수, status AS 상태
FROM product_current
WHERE v6_model = ?
ORDER BY is_live DESC, px ASC, channel_name
LIMIT 200
"""


SQL_FRESHNESS = """
SELECT channel_name AS 유통채널,
       MAX(run_date) AS 최종수집일,
       MIN(lag_days) AS 지연일수,
       COUNT(*) AS 상품수,
       SUM(is_live) AS 판매중_SKU,
       SUM(CASE WHEN is_live=0 THEN 1 ELSE 0 END) AS 미판매_SKU
FROM product_current
GROUP BY channel_id
ORDER BY 최종수집일 DESC, 유통채널
LIMIT 200
"""

# 🔴 '현재' 평균에는 **현재 판매중인 상품만** 넣는다.
#    이미 리스팅이 내려간 상품의 과거 가격이 섞이면 현재 평균가가 왜곡된다
#    (2026-08-31 실측: Al Khunaizan LG 평균이 5,127 → 실제 5,021, +106 부풀림).
SQL_BRAND_BY_CHANNEL = """
SELECT channel_name AS 유통채널,
       ROUND(AVG(CASE WHEN brand='LG'  THEN px END)) AS LG평균가,
       ROUND(AVG(CASE WHEN brand IN ('GREE','MIDEA','TCL') THEN px END)) AS 주요3사평균가,
       ROUND((AVG(CASE WHEN brand='LG' THEN px END)
              - AVG(CASE WHEN brand IN ('GREE','MIDEA','TCL') THEN px END)) * 100.0
             / AVG(CASE WHEN brand IN ('GREE','MIDEA','TCL') THEN px END), 1) AS 프리미엄_pct,
       COUNT(CASE WHEN brand='LG' THEN 1 END) AS LG_SKU수,
       COUNT(CASE WHEN brand IN ('GREE','MIDEA','TCL') THEN 1 END) AS 경쟁_SKU수,
       MAX(run_date) AS 기준일
FROM product_current
WHERE is_live = 1
GROUP BY channel_id
HAVING LG평균가 IS NOT NULL AND 주요3사평균가 IS NOT NULL
ORDER BY LG평균가 DESC
LIMIT 200
"""

FRESH_WORDS = ("언제까지 수집", "수집됐", "수집 됐", "신선도", "최종 수집",
               "언제까지 데이터", "데이터 언제", "업데이트 언제", "최신 수집")
BRANDCH_WORDS = ("채널별 lg", "유통별 lg", "채널별 평균가", "유통별 평균가",
                 "채널별 가격", "유통별 가격", "채널 별 lg")


SQL_BAND_BRAND = """
SELECT brand AS 브랜드,
       CASE WHEN brand='LG' THEN '우리'
            WHEN brand IN ('GREE','MIDEA','TCL') THEN '주요경쟁'
            ELSE '기타' END AS 구분,
       COUNT(*) AS 상품수,
       ROUND(AVG(px)) AS 평균가_SAR, ROUND(MIN(px)) AS 최저가_SAR,
       ROUND(MAX(px)) AS 최고가_SAR, MAX(run_date) AS 기준일
FROM product_current
WHERE is_live = 1 AND btu BETWEEN ? AND ?
  AND (? IS NULL OR channel_code = ?)
GROUP BY brand
HAVING COUNT(*) >= 2
ORDER BY 평균가_SAR DESC
LIMIT 200
"""

# 🔴 변동 조회에는 **스크래핑 결함 가드**가 반드시 들어가야 한다.
#    AI가 지은 SQL에는 이게 없어서 '하루 튀었다 원위치한' 가짜 변동을 그대로 보고한다
#    (Black Box LG +79% → 다음날 -44% 같은 왕복). 실제 변동이 아니라 프로모가 미포착일이다.
SQL_RECENT_MOVES = """
-- 결함 판정(스파이크·할인율모순)은 v_price_clean 안에 있다. 여기서 다시 쓰지 않는다.
SELECT c.run_date AS 일자, ch.name AS 유통채널, UPPER(p.brand) AS 브랜드,
       p.sku AS SKU, substr(COALESCE(p.name_en,''),1,55) AS 상품명, p.btu AS BTU,
       ROUND(c.prev_px) AS 이전가, ROUND(c.px) AS 현재가,
       ROUND((c.px - c.prev_px) * 100.0 / c.prev_px, 1) AS 변동률
FROM v_price_clean c
JOIN products p ON p.id = c.product_id
JOIN channels ch ON ch.id = p.channel_id
WHERE c.run_date >= date((SELECT MAX(run_date) FROM price_snapshots), ?)
  AND c.prev_px IS NOT NULL AND c.px <> c.prev_px AND c.prev_px > 0
  AND c.is_spike = 0 AND c.is_incons = 0
  AND (? = 'ALL' OR (? = 'LG' AND UPPER(p.brand)='LG')
       OR (? = 'COMP' AND UPPER(p.brand) IN ('GREE','MIDEA','TCL')))
  AND (? = 0 OR (c.px - c.prev_px) < 0)
  AND (? = 0 OR (c.px - c.prev_px) > 0)
ORDER BY ABS((c.px - c.prev_px) / c.prev_px) DESC
LIMIT 60
"""

SQL_MONTHLY_TREND = """
SELECT substr(c.run_date,1,7) AS 월,
       ROUND(AVG(CASE WHEN UPPER(p.brand)='LG'  THEN c.px END)) AS LG평균가,
       ROUND(AVG(CASE WHEN UPPER(p.brand) IN ('GREE','MIDEA','TCL') THEN c.px END)) AS 주요3사평균가,
       COUNT(DISTINCT CASE WHEN UPPER(p.brand)='LG' THEN p.id END) AS LG_SKU수,
       COUNT(DISTINCT c.run_date) AS 수집일수
FROM v_price_clean c JOIN products p ON p.id = c.product_id
WHERE c.is_spike = 0 AND c.is_incons = 0 AND p.btu BETWEEN ? AND ?
GROUP BY 월
HAVING 수집일수 >= 15
ORDER BY 월
LIMIT 200
"""

SQL_LINEUP = """
SELECT e.event_date AS 일자, ch.name AS 유통채널, UPPER(p.brand) AS 브랜드,
       p.sku AS SKU, substr(COALESCE(p.name_en,''),1,55) AS 상품명, p.btu AS BTU,
       CASE e.status WHEN 'new' THEN '신규' WHEN 'discontinued' THEN '단종'
                     WHEN 'reactive' THEN '재입고' ELSE e.status END AS 구분
FROM sku_status_events e
JOIN products p ON p.id = e.product_id
JOIN channels ch ON ch.id = p.channel_id
WHERE e.event_date >= date((SELECT MAX(run_date) FROM price_snapshots), ?)
  AND e.status = ?
  AND (? = 'ALL' OR (? = 'LG' AND UPPER(p.brand) = 'LG')
       OR (? = 'COMP' AND UPPER(p.brand) IN ('GREE','MIDEA','TCL')))
ORDER BY e.event_date DESC, ch.name
LIMIT 120
"""

CHEAP_WORDS = ("제일 싸", "가장 싸", "제일 저렴", "가장 저렴", "어디가 싸", "어디서 싸",
               "최저가", "싼 곳", "싼곳", "어디가 제일", "어디서 제일")
DOWN_WORDS = ("내린", "인하", "떨어진", "낮아진", "할인")
UP_WORDS = ("올린", "인상", "오른", "높아진")
MOVE_WORDS = ("변동", "움직", "바뀐", "변화") + DOWN_WORDS + UP_WORDS
TREND_WORDS = ("추이", "변했", "변화", "흐름", "월별", "지난 6개월", "6개월", "추세")
NEW_WORDS = ("새로 들어온", "신규", "새로 나온", "새 제품", "신제품")
GONE_WORDS = ("단종", "빠진", "사라진", "이탈")

BAND_RE = re.compile(r"(\d{1,2}[,.]?\d{3})\s*(?:btu|BTU|비티유)?", re.I)
CH_CODE_BY_NAME = {
    "extra": "extra", "엑스트라": "extra", "익스트라": "extra",
    "bh": "bh", "빈하무드": "bh", "sws": "sws",
    "najm": "najm", "나즘": "najm",
    "alkhunaizan": "alkhunaizan", "khunaizan": "alkhunaizan", "쿠나이잔": "alkhunaizan",
    "almanea": "almanea", "manea": "almanea", "마네아": "almanea",
    "tamkeen": "tamkeen", "탐킨": "tamkeen",
    "binmomen": "binmomen", "bin momen": "binmomen", "빈모멘": "binmomen",
    "blackbox": "blackbox", "black box": "blackbox", "블랙박스": "blackbox",
    "technobest": "technobest", "techno": "technobest", "테크노": "technobest",
    "alkhater": "alkhater", "khater": "alkhater",
}


def _btu_band(q):
    """질문에서 BTU를 뽑아 ±8% 구간으로. 없으면 None."""
    for m in BAND_RE.finditer(q):
        try:
            v = int(m.group(1).replace(",", "").replace(".", ""))
        except ValueError:
            continue
        if 5000 <= v <= 120000:
            return int(v * 0.92), int(v * 1.08)
    return None


def _channel_code(q):
    ql = q.lower()
    for k, v in CH_CODE_BY_NAME.items():
        if k in ql:
            return v
    return None


# 현재 판매중(리스팅 살아있는) 상품만 — 여러 템플릿이 공유하는 조건
LIVE_ONLY = """p.id IN (SELECT product_id FROM price_snapshots GROUP BY product_id
              HAVING julianday((SELECT MAX(run_date) FROM price_snapshots))
                     - julianday(MAX(run_date)) <= 3)"""

SQL_STOCK_STATUS = """
SELECT channel_name AS 유통채널, brand AS 브랜드, v6_model AS 모델코드, sku AS SKU,
       substr(COALESCE(name_en,''),1,45) AS 상품명, btu AS BTU,
       ROUND(px) AS 현재가_SAR,
       CASE WHEN in_stock=0 THEN '품절' WHEN in_stock=1 THEN '재고있음' ELSE '미상' END AS 재고,
       run_date AS 확인일
FROM product_current
WHERE is_live = 1
  AND (? = 'ALL' OR (? = 'LG') = (brand='LG'))
  AND (? = 0 OR in_stock = 0)
  AND (? IS NULL OR channel_code = ?)
ORDER BY in_stock, channel_name, px DESC
LIMIT 150
"""

SQL_BRAND_RANK = """
SELECT brand AS 브랜드, v6_model AS 모델코드, sku AS SKU,
       substr(COALESCE(name_en,''),1,45) AS 상품명, btu AS BTU,
       ROUND(px) AS 현재가_SAR, channel_name AS 유통채널, run_date AS 확인일
FROM product_current
WHERE is_live = 1 AND (? = 'ALL' OR brand = ?)
ORDER BY px {DIR}
LIMIT 30
"""

SQL_CHANNEL_LINEUP = """
SELECT channel_name AS 유통채널, brand AS 브랜드, v6_model AS 모델코드, sku AS SKU,
       substr(COALESCE(name_en,''),1,45) AS 상품명, btu AS BTU,
       ROUND(px) AS 현재가_SAR, run_date AS 확인일
FROM product_current
WHERE is_live = 1 AND channel_code = ?
  AND (? = 'ALL' OR (? = 'LG') = (brand='LG'))
ORDER BY brand, px
LIMIT 200
"""

SQL_CHANNEL_SUMMARY = """
SELECT channel_name AS 유통채널,
       COUNT(*) AS 판매중_SKU,
       COUNT(DISTINCT brand) AS 브랜드수,
       COUNT(CASE WHEN brand='LG' THEN 1 END) AS LG_SKU,
       ROUND(AVG(px)) AS 평균가_SAR,
       MAX(run_date) AS 최종확인일
FROM product_current
WHERE is_live = 1
GROUP BY channel_id
ORDER BY 판매중_SKU DESC
LIMIT 50
"""

STOCK_WORDS = ("품절", "재고", "없는", "솔드아웃", "sold out")
RANK_HI = ("제일 비싼", "가장 비싼", "최고가", "비싼 순", "높은 순")
RANK_LO = ("제일 싼", "가장 싼", "최저가", "싼 순", "저렴한 순")
LINEUP_WORDS = ("파는", "판매하는", "취급", "라인업", "모델 전부", "모델 목록", "어디서 팔")
SUMMARY_WORDS = ("SKU 개수", "sku 개수", "몇 개", "몇개", "브랜드를 파는", "브랜드 수", "취급 규모")
# 🔴 주요 경쟁사 = GREE · MIDEA · TCL (형님 확정 2026-09-01). '경쟁사'는 이 3사를 뜻한다.
MAIN_COMPETITORS = ("GREE", "MIDEA", "TCL")
# 질문에서 이름을 집어낼 대상 — 주요 3사 외 브랜드도 '명시하면' 답한다.
BRANDS_ALL = ("LG",) + MAIN_COMPETITORS + ("SAMSUNG", "HISENSE", "HAIER", "MANDO", "BASIC", "ZAMIL")


def _brand_in(q):
    up = q.upper()
    for b in BRANDS_ALL:
        if b in up:
            return b
    for ko, en in (("삼성", "SAMSUNG"), ("그리", "GREE"), ("미디어", "MIDEA"),
                   ("하이센스", "HISENSE"), ("하이얼", "HAIER"), ("만도", "MANDO")):
        if ko in q:
            return en
    return None


# 🔴 이 DB에 **없는 것**. 물으면 지어내지 말고 없다고 말해야 한다.
#    가격 스냅샷 DB일 뿐이다. 판매량·매출·이익·점유율은 애초에 담겨 있지 않다.
#    (계기: "가장 많이 팔리는 채널은?" — 판매량이 없는데 AI 생성 경로로 새어나갔다)
NOT_IN_DB = [
    (("많이 팔리", "판매량", "판매 수량", "몇 대 팔", "셀아웃", "sell out", "sell-out",
      "잘 팔리", "베스트셀러", "판매 순위"),
     "판매량·셀아웃", "이 DB는 가격 스냅샷만 담는다. 판매 수량은 들어 있지 않다.",
     "unified-sellout / ir-total 대시보드, 또는 warehouse fact_sellthru"),
    (("매출", "revenue", "거래액", "매상"),
     "매출", "가격만 있고 수량이 없어 매출을 계산할 수 없다.",
     "or-monthly-psi / ir-total"),
    (("이익", "마진", "손익", "profit", "margin", "원가", "cogs"),
     "이익·마진", "원가·마진 정보가 이 DB에 없다.", "GPC 손익 파이프라인"),
    (("점유율", "share", "시장 점유"),
     "시장 점유율", "판매량이 없어 점유율을 계산할 수 없다.", "extra-ms 계열 대시보드"),
    (("재고 수량", "재고량", "몇 대 남", "재고 몇"),
     "재고 수량",
     "대부분 채널이 재고를 있음/품절 여부로만 제공한다(수치 없음). "
     "수치 재고가 오는 곳은 Al Manea·Tamkeen·Bin Momen·Black Box뿐이다.",
     "창고 재고는 fg-available (SAP ZMB52)"),
]


def unanswerable(q: str):
    """답할 수 없는 질문이면 (주제, 이유, 대안). 아니면 None.
    **모르는 것을 지어내지 않는 것이 정확도의 절반이다.**"""
    ql = q.lower()
    for words, topic, why, alt in NOT_IN_DB:
        if any(w.lower() in ql for w in words):
            return topic, why, alt
    return None


SQL_BRAND_TREND_ANY = """
SELECT substr(c.run_date,1,7) AS 월, UPPER(p.brand) AS 브랜드,
       ROUND(AVG(c.px)) AS 평균가_SAR,
       COUNT(DISTINCT p.id) AS SKU수,
       COUNT(DISTINCT c.run_date) AS 수집일수
FROM v_price_clean c JOIN products p ON p.id = c.product_id
WHERE c.is_spike = 0 AND c.is_incons = 0
  AND (? = 'ALL' OR UPPER(p.brand) = ?)
  AND (? IS NULL OR p.btu BETWEEN ? AND ?)
GROUP BY 월, UPPER(p.brand)
HAVING 수집일수 >= 15 AND SKU수 >= 2
ORDER BY 월, 평균가_SAR DESC
LIMIT 200
"""

SQL_BRAND_CHANNELS = """
SELECT brand AS 브랜드, channel_name AS 유통채널,
       COUNT(*) AS 판매중_SKU, ROUND(AVG(px)) AS 평균가_SAR,
       ROUND(MIN(px)) AS 최저가_SAR, ROUND(MAX(px)) AS 최고가_SAR,
       MAX(run_date) AS 확인일
FROM product_current
WHERE is_live = 1 AND brand = ?
GROUP BY channel_id
ORDER BY 판매중_SKU DESC
LIMIT 50
"""

SQL_LG_VS_COMP_BY_MODEL = """
WITH comp AS (
  SELECT btu/1000 AS band, ROUND(AVG(px)) AS comp_avg, COUNT(*) n
  -- 🔴 경쟁 기준 = 주요 3사(GREE·MIDEA·TCL). 로컬 저가 브랜드를 섞으면 프리미엄이 부풀려진다
  --    (실측: 전 브랜드 기준 +35.4% vs 주요 3사 기준 +19.5% — 15.9%p 차이)
  FROM product_current WHERE is_live=1 AND brand IN ('GREE','MIDEA','TCL') AND btu IS NOT NULL
  GROUP BY band HAVING n >= 3
)
SELECT lg.v6_model AS LG모델, lg.btu AS BTU,
       ROUND(AVG(lg.px)) AS LG평균가, c.comp_avg AS 주요3사평균가,
       ROUND(AVG(lg.px) - c.comp_avg) AS 차액_SAR,
       ROUND((AVG(lg.px) - c.comp_avg) * 100.0 / c.comp_avg, 1) AS 프리미엄_pct,
       COUNT(*) AS LG_SKU수, MAX(lg.run_date) AS 확인일
FROM product_current lg JOIN comp c ON c.band = lg.btu/1000
WHERE lg.is_live=1 AND lg.brand='LG' AND lg.v6_model IS NOT NULL AND lg.btu IS NOT NULL
GROUP BY lg.v6_model, lg.btu
ORDER BY 프리미엄_pct DESC
LIMIT 40
"""

TREND2_WORDS = ("동향", "추이", "흐름", "추세", "변했", "3개월", "6개월", "월별")
WHERE_SOLD = ("어디서 팔", "어디에서 팔", "어느 채널", "판매 채널", "취급 채널", "어디서 파는")
PREMIUM_WORDS = ("경쟁사보다", "경쟁보다", "우리가 비싼", "프리미엄", "가격 경쟁력", "비싼 모델")


def match_template(q: str):
    """(설명, SQL, params) 또는 None. 정규식이 아니라 **의도**로 고른다."""
    up = q.upper()
    has_ch = any(w in q for w in CH_WORDS) or any(w in q for w in CHEAP_WORDS)
    has_latest = any(w in q for w in LATEST_WORDS)

    # 후보 모델코드 중 v6_model 에 실제 있는 것만 채택 (추측 금지)
    cands = [m.group(1).upper() for m in MODEL_RE.finditer(up)]
    if cands:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        try:
            for c0 in cands:
                # 형님이 접미 붙은 표기(NS182C2 / NS182C2.NK2)로 물을 수 있다.
                # 표기 정규화는 정본 진입점 canon() 하나만 쓴다 — 자체 규칙을 만들지 않는다.
                for cand in (c0, _canon_or_none(c0)):
                    if not cand:
                        continue
                    hit = con.execute(
                        "SELECT v6_model FROM products WHERE UPPER(v6_model)=? LIMIT 1",
                        (cand.upper(),)).fetchone()
                    if hit:
                        break
                # 🔴 모델코드가 v6에 실재하면 그것만으로 '모델 질문'이다.
                #    부가 키워드(채널별/최신)를 요구하면 "AM242C 가격 알려줘",
                #    "LO182C 어디서 파나" 같은 평범한 질문이 전부 AI 생성으로 새어나간다.
                #    (실측: 실사용 32문항 중 23개(72%)가 이 이유로 불안정 경로로 빠졌다)
                if hit:
                    return ("모델 채널별 최신가 (검증된 질의)",
                            SQL_MODEL_LATEST_BY_CHANNEL.strip(), (hit[0],))
        finally:
            con.close()

    # 데이터 신선도 — 모든 숫자의 신뢰 근거라 절대 틀리면 안 된다
    if any(w in q for w in FRESH_WORDS):
        return ("채널별 수집 신선도 (검증된 질의)", SQL_FRESHNESS.strip(), ())

    # 모델 지정 없는 채널별 LG/경쟁 평균가
    #  단, 'SKU 개수'처럼 규모를 묻는 건 평균가가 아니다 → 위 요약 템플릿이 가져간다.
    if (any(w in q.lower() for w in BRANDCH_WORDS) and not cands
            and not any(w in q for w in SUMMARY_WORDS)):
        return ("채널별 LG/경쟁 현재가 평균 (검증된 질의)", SQL_BRAND_BY_CHANNEL.strip(), ())

    band = _btu_band(q)

    # 월별 추이 (BTU 지정 필요)
    if any(w in q for w in TREND_WORDS) and band:
        return (f"{band[0]//1000}~{band[1]//1000}K 월별 LG/경쟁 평균가 추이 (검증된 질의)",
                SQL_MONTHLY_TREND.strip(), (band[0], band[1]))

    # 라인업 변화 (신규 / 단종)
    if any(w in q for w in NEW_WORDS) or any(w in q for w in GONE_WORDS):
        status = "discontinued" if any(w in q for w in GONE_WORDS) else "new"
        days = "-30 days"
        scope = "LG" if ("LG" in q.upper() and "경쟁" not in q) else (
            "COMP" if "경쟁" in q else "ALL")
        label = "신규 진입" if status == "new" else "단종·이탈"
        return (f"최근 30일 {label} 라인업 (검증된 질의)",
                SQL_LINEUP.strip(), (days, status, scope, scope, scope))

    # 최근 가격 변동 (결함 가드 포함)
    if any(w in q for w in MOVE_WORDS):
        import re as _re
        m = _re.search(r"(\d+)\s*일", q)
        days = f"-{min(int(m.group(1)), 90)} days" if m else "-7 days"
        scope = "LG" if ("LG" in q.upper() and "경쟁" not in q) else (
            "COMP" if "경쟁" in q else "ALL")
        only_down = 1 if any(w in q for w in DOWN_WORDS) and not any(w in q for w in UP_WORDS) else 0
        only_up = 1 if any(w in q for w in UP_WORDS) and not any(w in q for w in DOWN_WORDS) else 0
        dirn = "인하" if only_down else ("인상" if only_up else "전체")
        return (f"최근 {days.strip('- days')}일 가격 {dirn} (검증된 질의 · 스크래핑 결함 제외)",
                SQL_RECENT_MOVES.strip(), (days, scope, scope, scope, only_down, only_up))

    ch = _channel_code(q)
    brand = _brand_in(q)

    # 최고가/최저가 순위 — '제일 비싼 모델'은 순위 질문이지 프리미엄 질문이 아니다.
    #  (PREMIUM_WORDS 의 '비싼 모델'이 먼저 걸려 엉뚱한 표가 나가던 오답)
    if any(w in q for w in RANK_HI) or any(w in q for w in RANK_LO):
        desc = any(w in q for w in RANK_HI)
        sql = SQL_BRAND_RANK.strip().replace("{DIR}", "DESC" if desc else "ASC")
        scope = brand if brand else "ALL"
        return (f"{'최고가' if desc else '최저가'} 순위{' · '+brand if brand else ''} (검증된 질의)",
                sql, (scope, scope))

    # 채널 취급 규모 요약 — 'SKU 개수'는 평균가가 아니라 규모 질문이다.
    if any(w in q for w in SUMMARY_WORDS) and not ch:
        return ("채널별 취급 규모 요약 (검증된 질의)", SQL_CHANNEL_SUMMARY.strip(), ())

    # LG vs 경쟁 프리미엄 (모델별)
    if any(w in q for w in PREMIUM_WORDS):
        return ("LG 모델별 경쟁사 대비 프리미엄 (검증된 질의)",
                SQL_LG_VS_COMP_BY_MODEL.strip(), ())

    # 특정 브랜드가 어디서 팔리나
    if brand and any(w in q for w in WHERE_SOLD):
        return (f"{brand} 채널별 취급 현황 (검증된 질의)", SQL_BRAND_CHANNELS.strip(), (brand,))

    # 브랜드 가격 동향 (BTU 없어도 동작)
    if any(w in q for w in TREND2_WORDS) and (brand or not band):
        lo, hi = (band if band else (None, None))
        scope = brand if brand else "ALL"
        return (f"{scope} 월별 평균가 추이" + (f" · {lo//1000}~{hi//1000}K" if band else "")
                + " (검증된 질의)",
                SQL_BRAND_TREND_ANY.strip(), (scope, scope, lo, lo, hi))

    # 재고·품절 조회
    if any(w in q for w in STOCK_WORDS):
        only_oos = 1 if ("품절" in q or "없는" in q or "sold out" in q.lower()) else 0
        scope = brand if brand else "ALL"
        lbl = "품절 상품" if only_oos else "재고 현황"
        return (f"{lbl}{' · '+brand if brand else ''}{' · '+ch if ch else ''} (검증된 질의)",
                SQL_STOCK_STATUS.strip(), (scope, scope, only_oos, ch, ch))

    # 특정 채널 라인업
    if ch and any(w in q for w in LINEUP_WORDS):
        scope = brand if brand else "ALL"
        return (f"{ch} 취급 라인업{' · '+brand if brand else ''} (검증된 질의)",
                SQL_CHANNEL_LINEUP.strip(), (ch, scope, scope))

    # BTU 구간 브랜드별 평균가 (채널 지정 있으면 그 채널만)
    if band and not cands:
        return (f"{band[0]//1000}~{band[1]//1000}K 브랜드별 현재가 평균"
                + (f" · {ch}" if ch else "") + " (검증된 질의)",
                SQL_BAND_BRAND.strip(), (band[0], band[1], ch, ch))

    return None


# ── 질의 캐시 — 자유도는 지키고 안정성을 얻는 방법 ──────────────
# 🔴 2026-09-01 형님 지적: "내가 말한게 하나의 예시잖아! 전체 데이터를 자유롭게 다뤄야지"
#    질문마다 템플릿을 손으로 박는 건 DB화가 아니다. 그런데 AI 자유 질의는 불안정하다.
#    실측: 정본 계층(product_current)을 깔아도 여전히 흔들렸다.
#      "LG랑 삼성 누가 비싸" → 3회 중 2가지 답. 원인은 데이터 함정이 아니라 **질문의 모호성**
#      (전체 평균인지·BTU급별인지·채널별인지를 AI가 매번 다르게 해석한다).
#
#    → 해법: **같은 질문이면 같은 SQL을 쓴다.**
#      처음 보는 질문만 AI가 짓고, 그 SQL을 저장해 다음부터 재사용한다.
#      · 자유도 유지 — 어떤 질문이든 답한다(템플릿을 미리 짤 필요 없다)
#      · 안정성 확보 — 한 번 정해진 질의는 고정, 같은 질문엔 같은 답
#      · 고치기 쉬움 — 형님이 "이 답 이상해" 하면 그 질문의 SQL 한 줄만 고치면 끝
#      손으로 짜는 템플릿이 아니라 **쓰면서 저절로 쌓이는 템플릿**이다.

CACHE_DDL = """
CREATE TABLE IF NOT EXISTS qa_cache (
  qnorm      TEXT PRIMARY KEY,   -- 정규화된 질문
  question   TEXT NOT NULL,      -- 원문(마지막으로 물은 형태)
  sql        TEXT NOT NULL,
  created_at TEXT NOT NULL,
  used_count INTEGER DEFAULT 1,
  last_used  TEXT,
  pinned     INTEGER DEFAULT 0,  -- 1 = 사람이 검토·확정한 질의 (덮어쓰지 않는다)
  note       TEXT
)
"""


def qnorm(q: str) -> str:
    """질문 정규화 — 공백·문장부호·흔한 종결어미 차이를 흡수한다.
    과하게 뭉개면 다른 질문이 같은 SQL을 쓰게 되므로 **보수적으로만** 정리한다."""
    t = q.strip().lower()
    t = re.sub(r"[?!.,·]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # 종결어미를 떼고 나면 공백이 남을 수 있다 → 뗄 때마다 다시 strip (물음표 유무로 캐시가 갈리던 버그)
    for tail in ("알려줘", "보여줘", "얼마야", "얼마인가", "어때", "해줘", "줘", "인가", "있나"):
        if t.endswith(tail):
            t = t[: -len(tail)].strip()
    return re.sub(r"\s+", " ", t).strip()


def cache_get(q: str):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        con.execute(CACHE_DDL.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE IF NOT EXISTS"))
    except sqlite3.OperationalError:
        pass          # 읽기전용이라 생성 불가 — cache_put 이 만든다
    try:
        r = con.execute("SELECT sql, used_count, pinned FROM qa_cache WHERE qnorm=?",
                        (qnorm(q),)).fetchone()
        return r
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def cache_put(q: str, sql: str):
    con = sqlite3.connect(str(DB), timeout=10)
    try:
        con.execute(CACHE_DDL)
        con.execute("""INSERT INTO qa_cache(qnorm, question, sql, created_at, last_used)
                       VALUES(?,?,?,datetime('now'),datetime('now'))
                       ON CONFLICT(qnorm) DO UPDATE SET
                         used_count = used_count + 1,
                         last_used  = datetime('now'),
                         question   = excluded.question""",
                    (qnorm(q), q, sql))
        con.commit()
    except Exception as e:
        print(f"[cache] 저장 실패(무시): {e}", file=sys.stderr)
    finally:
        con.close()


def cache_touch(q: str):
    con = sqlite3.connect(str(DB), timeout=10)
    try:
        con.execute("UPDATE qa_cache SET used_count=used_count+1, last_used=datetime('now') "
                    "WHERE qnorm=?", (qnorm(q),))
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


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


def run_sql(sql: str, params=()):
    """읽기전용 연결 + 시간제한. 쓰기는 구문 검증 이전에 연결 수준에서 이미 불가능하다."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    deadline = time.time() + 15
    con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10000)
    try:
        cur = con.execute(sql, params)
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

        # 🔴 답할 수 없는 질문은 **먼저 거절**한다. 모르는 것을 지어내지 않는 것이 정확도의 절반이다.
        na = unanswerable(q)
        if na:
            topic, why, alt = na
            yield ev("error", {"message":
                f"이 질문은 가격 DB로 답할 수 없습니다 — {topic}.\n{why}\n\n"
                f"➜ 여기서 보셔야 합니다: {alt}"})
            return

        # 검증된 템플릿에 걸리면 LLM을 거치지 않는다 → 같은 질문엔 항상 같은 답
        tpl = match_template(q)
        if tpl:
            label, sql, params = tpl
            route = "verified"
            yield ev("stage", {"stage": "sql", "text": f"{label} 적용 중…"})
        else:
            label, params = None, ()
            cached = cache_get(q) if not hist else None   # 후속 질문은 문맥이 달라 캐시 금지
            if cached:
                sql, used, pinned = cached[0], cached[1], cached[2]
                route = "cached"
                label = (f"확정된 질의 (검토 완료)" if pinned
                         else f"이전과 같은 질의 ({used}번째 사용)")
                cache_touch(q)
                yield ev("stage", {"stage": "sql", "text": f"{label} 적용 중…"})
            else:
                route = "generated"
                yield ev("stage", {"stage": "sql", "text": "처음 보는 질문 — 질의를 새로 짓는 중…"})
                ctx = ""
                if hist:
                    ctx = "\n\n【직전 대화 — 후속 질문일 수 있다】\n" + "\n".join(
                        f"{h['role']}: {h['text'][:300]}" for h in hist[-4:])
                try:
                    sql = sanitize(llm([{"role": "system", "content": SQL_SYS + ctx},
                                        {"role": "user", "content": q}]))
                except Exception as e:
                    yield ev("error", {"message": f"질의 생성 실패: {e}"}); return
        yield ev("sql", {"sql": sql, "route": route, "label": label,
                         "elapsed": round(time.time() - t0, 1)})

        yield ev("stage", {"stage": "run", "text": "데이터 조회 중…"})
        try:
            cols, rows = run_sql(sql, params)
        except Exception as e:
            yield ev("error", {"message": f"조회 실패: {e}", "sql": sql}); return
        if route == "generated":
            cache_put(q, sql)     # 실행에 성공한 질의만 굳힌다
        yield ev("rows", {"columns": cols, "rows": rows, "row_count": len(rows),
                          "route": route, "anchor": anchor(),
                          "elapsed": round(time.time() - t0, 1)})

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
