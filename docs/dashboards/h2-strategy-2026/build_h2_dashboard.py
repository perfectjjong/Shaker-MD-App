#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 하반기 전략 코크핏 (경영보고 대시보드 — 통합 3단계).
소스: ../sell-thru-progress/unified_psi.json (이중축 + 7~12월 FCST 단일 진실).
원칙(형님 확정):
  - 이중축 분리: 금액(ST_val↔AR↔OVD) / 수량(ST_qty↔SO_qty↔Stock_qty→MOS). 절대 혼합 금지.
  - 목표(2026-06-17): OR(+OR_Others) 3Q70/4Q25/H2 95, IR(+IR_Others+SME) 3Q60/4Q35/H2 95.
  - 자연전망 = 1~5실적 + 6월 RSM + 7~12월(1-5평균×2024·2025 시즌계수).
재생성: python3 build_h2_dashboard.py  → index.html
정책: 이 .py만 수정하고 재생성한다. index.html 직접 편집 금지.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'sell-thru-progress', 'unified_psi.json')
u = json.load(open(SRC))
CH = u['channels']
META = u.get('_meta', {})
TGT = META.get('target_2026', {'OR': {'3Q': 70, '4Q': 25, 'H2': 95},
                               'IR': {'3Q': 60, '4Q': 35, 'H2': 95}})

ORDER = ['eXtra', 'Al Manea', 'SWS', 'Black Box', 'Al Khunizan', 'OR_Others',
         'BH', 'BM', 'Tamkeen', 'Zagzoog', 'Dhamin', 'Star Appliance',
         'Al Ghanem', 'Al Shathri', 'IR_Others', 'SME']
KO = {'eXtra': 'eXtra', 'Al Manea': 'Al Manea', 'SWS': 'SWS', 'Black Box': 'Black Box',
      'Al Khunizan': 'Al Khunizan', 'OR_Others': 'OR 기타', 'BH': 'BH', 'BM': 'BM',
      'Tamkeen': 'Tamkeen', 'Zagzoog': 'Zagzoog', 'Dhamin': 'Dhamin',
      'Star Appliance': 'Star', 'Al Ghanem': 'Al Ghanem', 'Al Shathri': 'Al Shathri',
      'IR_Others': 'IR 기타', 'SME': 'SME'}


def vget(c, mm, key, axis='value'):
    n = CH[c].get(axis, {}).get(mm, {})
    return n.get(key, 0) if isinstance(n, dict) else 0


rows = []
grp_val = {'OR': [0.0] * 13, 'IR': [0.0] * 13}      # 월별 ST 금액(M) 1..12 → index 1~12
grp_qty = {'OR': [0.0] * 13, 'IR': [0.0] * 13}
for c in ORDER:
    if c not in CH:
        continue
    g = CH[c].get('group', 'IR')
    seg = CH[c].get('segment', False)
    mval = [vget(c, f'{m:02d}', 'st_val') for m in range(1, 13)]
    mqty = [vget(c, f'{m:02d}', 'st_qty', 'qty') for m in range(1, 13)]
    fcst = [bool(vget(c, f'{m:02d}', 'fcst')) for m in range(1, 13)]
    for m in range(1, 13):
        grp_val[g][m] += mval[m - 1] / 1e6
        grp_qty[g][m] += mqty[m - 1]
    h1 = sum(mval[0:5]) / 1e6
    jun = mval[5] / 1e6
    q3 = sum(mval[6:9]) / 1e6
    q4 = sum(mval[9:12]) / 1e6
    annual = h1 + jun + q3 + q4
    ar = vget(c, '', '', 'value') or CH[c].get('value', {}).get('ar_bal', 0)
    ovd = CH[c].get('value', {}).get('ovd', 0)
    # MOS (수량축): 최근 실측 재고 ÷ 1~5월 평균 sell-out. 세그먼트는 데이터 없음.
    stk, mos, so_avg = None, None, None
    if not seg:
        so15 = [vget(c, f'{m:02d}', 'so_qty', 'qty') for m in range(1, 6)]
        so_avg = sum(so15) / 5.0 if any(so15) else 0
        # 최근 실측 재고: 06→05→... 중 stk_qty 존재하는 마지막
        for m in (6, 5, 4, 3):
            s = vget(c, f'{m:02d}', 'stk_qty', 'qty')
            if s:
                stk = s
                break
        if stk and so_avg:
            mos = stk / so_avg
    asp = (sum(mval[0:5]) / sum(mqty[0:5])) if sum(mqty[0:5]) else 0   # 1~5월 실효 ASP
    rows.append({
        'name': c, 'ko': KO.get(c, c), 'group': g, 'seg': seg,
        'mval': [round(x, 0) for x in mval], 'mqty': [round(x, 0) for x in mqty],
        'fcst': fcst, 'h1': round(h1, 1), 'jun': round(jun, 1),
        'q3': round(q3, 1), 'q4': round(q4, 1), 'annual': round(annual, 1),
        'ar': round(ar / 1e6, 1), 'ovd': round(ovd / 1e6, 1),
        'stk': stk, 'mos': round(mos, 1) if mos else None,
        'asp': round(asp, 0), 'ac_asp': CH[c].get('ac_asp', 0),
        'so_avg': round(so_avg, 0) if so_avg else None,
        'h2qty': round(sum(mqty[6:12]), 0),
    })

# 그룹 집계
def gsum(g, lo, hi):
    return round(sum(r['annual' if (lo, hi) == (1, 12) else None] for r in rows), 1)


summary = {}
for g in ('OR', 'IR'):
    # 그룹 집계는 원시 월별값(grp_val, M SAR)에서 직접 산출 → 엔진 리포트와 정확히 일치
    h1 = round(sum(grp_val[g][1:6]), 1)
    jun = round(grp_val[g][6], 1)
    q3 = round(sum(grp_val[g][7:10]), 1)
    q4 = round(sum(grp_val[g][10:13]), 1)
    annual = round(sum(grp_val[g][1:13]), 1)
    t = TGT[g]
    summary[g] = {
        'h1': h1, 'jun': jun, 'q3': q3, 'q4': q4, 'h2': round(q3 + q4, 1),
        'annual': annual,
        't3': t['3Q'], 't4': t['4Q'], 'th2': t['H2'],
        'gap3': round(t['3Q'] - q3, 1), 'gap4': round(t['4Q'] - q4, 1),
        'gaph2': round(t['H2'] - (q3 + q4), 1),
    }
tot_annual = round(summary['OR']['annual'] + summary['IR']['annual'], 1)
tot_gap = round(summary['OR']['gaph2'] + summary['IR']['gaph2'], 1)

PAYLOAD = {
    'rows': rows, 'summary': summary, 'grp_val': grp_val, 'grp_qty': grp_qty,
    'tot_annual': tot_annual, 'tot_gap': tot_gap,
    'season': META.get('season_index', {}),
    'fcst_method': META.get('fcst_method', ''),
    'scenarios': META.get('scenarios', {}),
    'recovery': META.get('recovery_factor', {}),
    'normal_base': META.get('normal_base', {}),
    'macro': META.get('macro_timeline', []),
}

# ---- Action Plan: gap을 채널 단위로 귀속 (자연전망 기여도 비례) ----
# 음수 gap(이미 초과) 분기는 채널 푸시 불필요. 양수 gap만 채널 푸시 배분.
def attribute(g, qkey, gap):
    if gap <= 0:
        return []
    chs = [r for r in rows if r['group'] == g and r[qkey] > 0]
    base = sum(r[qkey] for r in chs)
    out = []
    for r in chs:
        share = r[qkey] / base if base else 0
        out.append({'ko': r['ko'], 'add': round(gap * share, 1),
                    'mos': r['mos'], 'ovd': r['ovd'], 'q': qkey})
    out.sort(key=lambda x: -x['add'])
    return out

PAYLOAD['plan'] = {
    'OR_3Q': attribute('OR', 'q3', summary['OR']['gap3']),
    'OR_4Q': attribute('OR', 'q4', summary['OR']['gap4']),
    'IR_3Q': attribute('IR', 'q3', summary['IR']['gap3']),
    'IR_4Q': attribute('IR', 'q4', summary['IR']['gap4']),
}

# ---- 목표 역산: 채널별 ST(출하) 목표 → 필요 Sell-out(소진) — 형님 핵심 요구 ----
# 공식 FCST=형님 목표. 채널 ST목표(금액) = 그룹목표H2 × 채널 자연전망 비중.
# 출하가 지속되려면 채널이 소진해야 → 필요 SO = (기초재고+ST목표수량)에서 기말 정상재고(2개월) 남긴 소진량.
# ⚠️정합성: ST_qty(악세사리 포함) ≠ SO_qty(AC본품). ST목표수량은 AC본품 ASP(unified의 ac_asp)로 환산해 모집단 일치(형님 강조).
TARGET_MOS = 2.0   # 하반기말 목표 재고 (개월) — 정상 회전 수준
SEASON = META.get('season_index', {})
def monthly_sim(g, stk0, so_h2):
    """월별 PSI 시뮬: SO를 시즌계수로 배분 + 재고방정식(Stock=전월+ST-SO)으로 정상화 궤적."""
    seas = {int(k): v for k, v in SEASON.get(g, {}).items() if 7 <= int(k) <= 12}
    ss = sum(seas.values()) or 1
    end_stk = so_h2 / 6 * TARGET_MOS          # 목표 기말재고(2개월)
    out, prev = [], stk0
    for i, m in enumerate(range(7, 13)):
        so = so_h2 * seas.get(m, 0) / ss
        target = stk0 + (end_stk - stk0) * (i + 1) / 6   # 재고 선형 정상화 궤적
        st = so + (target - prev)                         # 재고방정식 역산
        mos = target / (so_h2 / 6) if so_h2 else 0
        out.append({'m': m, 'so': round(so), 'st': round(max(st, 0)),
                    'stk': round(target), 'mos': round(mos, 1)})
        prev = target
    return out
def reverse_plan(g):
    grp_s1_h2 = summary[g]['h2'] or 1
    tgt_h2 = TGT[g]['H2']
    out = []
    for r in rows:
        if r['group'] != g or r['seg']:
            continue
        share = (r['q3'] + r['q4']) / grp_s1_h2
        st_val = tgt_h2 * share                                  # 채널 ST목표 금액(M)
        asp = r['ac_asp'] or r['asp']                            # AC본품 ASP(unified) 우선
        st_qty = st_val * 1e6 / asp if asp else 0                # → AC본품 수량 환산
        stk = r['stk'] or 0
        # SO_H2 + 기말재고 = 기초재고 + ST목표.  기말 = TARGET_MOS×(SO_H2/6)
        so_need = (stk + st_qty) / (1 + TARGET_MOS / 6.0) if stk else st_qty
        so_cur = (r['so_avg'] or 0) * 6                          # 현 런레이트 H2 환산
        lift = round((so_need / so_cur - 1) * 100, 0) if so_cur else None
        cm = CH[r['name']].get('cat_mix', {})
        cats = [{'cat': c, 'qty': round(so_need * sh)} for c, sh in cm.items()]
        out.append({'ko': r['ko'], 'st_val': round(st_val, 1), 'st_qty': round(st_qty, 0),
                    'so_need': round(so_need, 0), 'so_cur': round(so_cur, 0),
                    'lift': lift, 'mos': r['mos'], 'stk': stk,
                    'monthly': monthly_sim(g, stk, so_need), 'cats': cats})
    out.sort(key=lambda x: -x['st_val'])
    return out
PAYLOAD['reverse'] = {'OR': reverse_plan('OR'), 'IR': reverse_plan('IR')}

# ===== eXtra 8~9월 입고계획 (OR 3Q gap의 핵심 레버) =====
# 수량축: 매출(금액) 목표 → AC 본품 ASP로 수량 환산 → 카테고리·SKU 배분.
# ⚠️ 악세사리(Accessories) 제외 — OR 수량 2배 부풀림 함정 차단.
import re as _re
DATA = json.load(open(os.path.join(HERE, '..', 'sell-thru-progress', 'data.json')))
TXN = DATA['txn']
EX = 1120000000
AC_CATS = {'Split Inverter', 'Split on/off', 'Free Standing', 'Cassette', 'Concealed', 'Window'}  # 라벨='Window'(확인)


def _aid(t):
    try:
        return int(float(t[3]))
    except Exception:
        return None


from collections import defaultdict as _dd
ex_c15 = _dd(lambda: [0.0, 0.0])    # 2026 1-5 카테고리 [val,qty]
ex_s = _dd(lambda: [0.0, 0.0])      # 2024+2025 8~9월 시즌 카테고리 [val,qty]
for t in TXN:
    if _aid(t) != EX or t[7] not in AC_CATS:
        continue
    y, m = t[0], int(t[1])
    if y == 2026 and 1 <= m <= 5:
        ex_c15[t[7]][0] += t[8] or 0; ex_c15[t[7]][1] += t[9] or 0
    if y in (2024, 2025) and m in (8, 9):
        ex_s[t[7]][0] += t[8] or 0; ex_s[t[7]][1] += t[9] or 0

ex_avg_val = sum(v[0] for v in ex_c15.values()) / 5.0 / 1e6        # 월평균 매출(M, AC)
seas_OR = PAYLOAD['season'].get('OR', {})
s8, s9 = seas_OR.get('8', 1.06), seas_OR.get('9', 1.42)
nat8, nat9 = ex_avg_val * s8, ex_avg_val * s9                       # 8/9월 자연전망(M)
# OR 3Q gap의 eXtra 귀속(자연전망 기여도) → 8~9월에 시즌비례 집중 배분
ex_q3 = next((r['q3'] for r in rows if r['name'] == 'eXtra'), 0)
ex_share = ex_q3 / summary['OR']['q3'] if summary['OR']['q3'] else 0
ex_add = max(0.0, summary['OR']['gap3']) * ex_share                 # eXtra 추가 필요(M)
add8 = ex_add * s8 / (s8 + s9); add9 = ex_add * s9 / (s8 + s9)
tgt8, tgt9 = nat8 + add8, nat9 + add9

# 8~9월 시즌 카테고리 금액믹스 + 카테고리 ASP
seas_tot = sum(v[0] for v in ex_s.values()) or 1
cat_mix = {}
for c, (v, q) in ex_s.items():
    cat_mix[c] = {'mix': v / seas_tot, 'asp': (v / q if q else 0), 'qty_share': q}
season_asp = seas_tot / sum(v[1] for v in ex_s.values())            # 8~9월 통합 ASP


def split_cat(tgt_m):
    out = []
    for c, info in sorted(cat_mix.items(), key=lambda x: -x[1]['mix']):
        val = tgt_m * info['mix']
        qty = val * 1e6 / info['asp'] if info['asp'] else 0
        out.append({'cat': c, 'val': round(val, 2), 'qty': round(qty, 0),
                    'asp': round(info['asp'], 0), 'mix': round(info['mix'] * 100, 1)})
    return out


# SKU 우선순위: psi_model_table.js (결품임박 LOW/OOS = 입고1순위, OVER = 회피)
sku_in, sku_avoid = [], []
try:
    mt = open(os.path.join(HERE, '..', 'or-monthly-psi', 'psi_model_table.js')).read()
    mm = _re.search(r'const PSI_MODEL_TABLE\s*=\s*(\{.*?\});', mt, _re.S)
    T = json.loads(mm.group(1))
    exa = T['mos_analysis']['eXtra']
    seen = {}
    for fl in ('low', 'oos', 'over', 'slow', 'normal', 'healthy'):
        for r in exa.get(fl, []):
            seen[r['std']] = r

    def _so(r):
        return r.get('avg_so') or r.get('so_may') or 0
    allm = list(seen.values())
    for r in sorted([x for x in allm if (x.get('mos') if x.get('mos') is not None else 99) < 1.5 and _so(x) > 0],
                    key=lambda x: -_so(x))[:8]:
        sku_in.append({'std': r['std'], 'btu': r.get('btu', ''), 'hc': r.get('hc', ''),
                       'stk': r.get('stk', 0), 'so': round(_so(r), 0),
                       'mos': r.get('mos', 0), 'flag': r.get('flag', '')})
    for r in sorted([x for x in allm if (x.get('mos') or 0) >= 3 and _so(x) > 0],
                    key=lambda x: -_so(x))[:6]:
        sku_avoid.append({'std': r['std'], 'btu': r.get('btu', ''), 'so': round(_so(r), 0),
                          'mos': r.get('mos', 0)})
    sku_month = T.get('month_label', '')
except Exception as _e:
    sku_month = f'(모델표 로드 실패: {_e})'

BUF = 0.15  # 피크 결품 방지 안전버퍼
PAYLOAD['extra'] = {
    'avg_val': round(ex_avg_val, 2), 's8': round(s8, 2), 's9': round(s9, 2),
    'nat8': round(nat8, 1), 'nat9': round(nat9, 1),
    'add8': round(add8, 1), 'add9': round(add9, 1),
    'tgt8': round(tgt8, 1), 'tgt9': round(tgt9, 1),
    'ex_share': round(ex_share * 100, 0), 'ex_add': round(ex_add, 1),
    'or_gap3': summary['OR']['gap3'], 'season_asp': round(season_asp, 0),
    'cat8': split_cat(tgt8), 'cat9': split_cat(tgt9),
    'qty8': round(tgt8 * 1e6 / season_asp, 0), 'qty9': round(tgt9 * 1e6 / season_asp, 0),
    'buf': int(BUF * 100), 'sku_in': sku_in, 'sku_avoid': sku_avoid, 'sku_month': sku_month,
}

HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2026 하반기 전략 코크핏 | Saudi LG AC</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{--or:#2563eb;--ir:#dc2626;--bg:#0f172a;--card:#1e293b;--mut:#94a3b8;--line:#334155;--ok:#10b981;--warn:#f59e0b;--bad:#ef4444;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI','Malgun Gothic',sans-serif;background:var(--bg);color:#e2e8f0;line-height:1.5;padding:20px}
  .wrap{max-width:1280px;margin:0 auto}
  h1{font-size:24px;font-weight:800}
  .sub{color:var(--mut);font-size:13px;margin-top:4px}
  .tabs{display:flex;gap:8px;margin:20px 0;flex-wrap:wrap}
  .tab{padding:9px 16px;background:var(--card);border:1px solid var(--line);border-radius:8px;cursor:pointer;font-size:14px;font-weight:600}
  .tab.active{background:var(--or);border-color:var(--or);color:#fff}
  .panel{display:none}.panel.active{display:block}
  .grid{display:grid;gap:14px}
  .kpis{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
  .card .lbl{color:var(--mut);font-size:12px;font-weight:600}
  .card .val{font-size:26px;font-weight:800;margin-top:6px}
  .card .note{font-size:12px;margin-top:4px}
  .pos{color:var(--bad)}.neg{color:var(--ok)}
  table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}
  th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--line)}
  th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;position:sticky;top:0;background:var(--card)}
  td.l,th.l{text-align:left}
  tr.or-row td.l{color:#93c5fd}tr.ir-row td.l{color:#fca5a5}
  tr.seg td.l{font-style:italic;color:var(--mut)}
  tr.grp{background:#0b1220;font-weight:800}
  .chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700}
  .c-ok{background:rgba(16,185,129,.18);color:#34d399}
  .c-warn{background:rgba(245,158,11,.18);color:#fbbf24}
  .c-bad{background:rgba(239,68,68,.18);color:#f87171}
  .chartbox{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:14px}
  .chartbox h3{font-size:15px;margin-bottom:10px}
  canvas{max-height:340px}
  .secttitle{font-size:18px;font-weight:800;margin:22px 0 4px}
  .axis-tag{font-size:11px;padding:2px 8px;border-radius:6px;font-weight:700;margin-left:8px}
  .ax-val{background:rgba(37,99,235,.2);color:#93c5fd}
  .ax-qty{background:rgba(245,158,11,.2);color:#fbbf24}
  .plan-grid{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
  .footnote{color:var(--mut);font-size:12px;margin-top:18px;border-top:1px solid var(--line);padding-top:12px}
</style>
</head>
<body>
<div class="wrap">
  <h1>2026 하반기 전략 코크핏 <span style="font-size:13px;color:var(--mut);font-weight:600">OR + IR · 16 bucket · 이중축</span></h1>
  <div class="sub" id="subline"></div>

  <div class="tabs">
    <div class="tab active" data-p="overview">① 종합 (목표·Gap)</div>
    <div class="tab" data-p="psi">② 채널 PSI</div>
    <div class="tab" data-p="dual">③ 이중축 추이</div>
    <div class="tab" data-p="plan">④ Action Plan</div>
    <div class="tab" data-p="exec">⑤ 월별 실행플랜 (SO→재고정상화)</div>
    <div class="tab" data-p="extra">⑥ eXtra 입고계획</div>
  </div>

  <div class="panel active" id="overview"></div>
  <div class="panel" id="psi"></div>
  <div class="panel" id="dual"></div>
  <div class="panel" id="plan"></div>
  <div class="panel" id="exec"></div>
  <div class="panel" id="extra"></div>

  <div class="footnote" id="foot"></div>
</div>

<script>
const D = __PAYLOAD__;
const MN = ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'];
const f1 = x => (x==null?'–':x.toFixed(1));
const charts = {};

function gapChip(g){ // 양수=미달(빨강), 음수=초과(녹색)
  if(g==null) return '';
  const cls = g>0.05?'c-bad':(g<-0.05?'c-ok':'c-warn');
  const s = g>0?('+'+g.toFixed(1)):g.toFixed(1);
  return `<span class="chip ${cls}">${s}M</span>`;
}
function mosChip(m){
  if(m==null) return '<span style="color:#475569">–</span>';
  const cls = m>=4?'c-bad':(m>=2.5?'c-warn':'c-ok');
  return `<span class="chip ${cls}">${m.toFixed(1)}개월</span>`;
}
function ovdChip(o){
  if(!o) return '<span style="color:#475569">0</span>';
  const cls = o>=10?'c-bad':(o>=2.5?'c-warn':'c-ok');
  return `<span class="chip ${cls}">${o.toFixed(1)}M</span>`;
}

// ---------- ① Overview ----------
function renderOverview(){
  const s=D.summary, sc=D.scenarios, el=document.getElementById('overview');
  const pct=(g)=>{const x=sc[g];return x&&(x.S2.H2-x.S1.H2)?Math.round((x.target.H2-x.S1.H2)/(x.S2.H2-x.S1.H2)*100):0;};
  const scenCard=(g)=>{const x=sc[g];if(!x)return '';return `
    <div class="card">
      <div class="lbl">${g} 하반기 — 시나리오 밴드 (M SAR)</div>
      <div style="display:flex;justify-content:space-between;margin-top:12px;gap:6px">
        <div style="text-align:center;flex:1"><div style="font-size:11px;color:var(--mut)">S1 충격지속</div><div style="font-size:21px;font-weight:800;color:#f87171">${x.S1.H2}</div></div>
        <div style="text-align:center;flex:1;border-left:1px solid var(--line);border-right:1px solid var(--line)"><div style="font-size:11px;color:#fbbf24">🎯 목표(공식)</div><div style="font-size:26px;font-weight:800;color:#fbbf24">${x.target.H2}</div></div>
        <div style="text-align:center;flex:1"><div style="font-size:11px;color:var(--mut)">S2 정상회복</div><div style="font-size:21px;font-weight:800;color:#34d399">${x.S2.H2}</div></div>
      </div>
      <div class="note" style="color:var(--mut);margin-top:10px;text-align:center">목표는 충격지속·정상회복 사이 — <b style="color:#fbbf24">회복 ${pct(g)}% 실현</b> 지점 (달성 가능·보수적)</div>
    </div>`;};
  const macroRow=D.macro.map(e=>`<tr><td class="l" style="white-space:nowrap"><b>${e.m}</b></td>
    <td class="l">${e.event}</td><td class="l" style="color:#cbd5e1">${e.impact}</td>
    <td><span class="chip ${e.type==='shock'?'c-bad':'c-ok'}">${e.type==='shock'?'충격':'회복'}</span></td></tr>`).join('');
  el.innerHTML = `
    <div class="card" style="border-color:#fbbf24;margin-bottom:14px">
      <div class="lbl">공식 FCST = 형님 목표 채택 · 거시 회복 반영 (2026-06-18)</div>
      <div class="note" style="color:#cbd5e1;margin-top:6px;font-size:13px">1~5월은 <b>사우디제이션(1월)+이란·미국전 소비위축(4~5월)</b> 충격기. 그 바닥을 미래에 복사하면 과소추정 → 충격월 제외 <b>정상 런레이트</b>(OR ${D.normal_base.OR} / IR ${D.normal_base.IR}M·월)로 회복 시나리오 산출. 회복계수 OR ×${D.recovery.OR} / IR ×${D.recovery.IR}.</div>
    </div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(330px,1fr))">${scenCard('OR')}${scenCard('IR')}</div>

    <div class="chartbox" style="margin-top:14px"><h3>거시 타임라인 (2026) — 충격과 회복</h3>
      <table><tr><th class="l">시기</th><th class="l">사건</th><th class="l">데이터 영향</th><th>국면</th></tr>${macroRow}</table>
      <div style="color:var(--mut);font-size:12px;margin-top:8px">→ 6월 RSM 반등이 회복세 진입을 입증. 형님 목표는 <b>회복 ~60% 실현</b>을 가정한 달성권 목표. 회복 모멘텀 둔화 시 S1(충격지속)으로 회귀 리스크.</div>
    </div>

    <div class="grid kpis" style="margin-top:14px">
      <div class="card"><div class="lbl">연간 (S1 자연전망)</div><div class="val">${D.tot_annual}M</div><div class="note" style="color:var(--mut)">목표 환산 405.7M · SAR</div></div>
      <div class="card"><div class="lbl">OR 하반기 목표</div><div class="val">${s.OR.th2}M</div><div class="note">S1 ${s.OR.h2} → 메울 양 ${gapChip(s.OR.gaph2)}</div></div>
      <div class="card"><div class="lbl">IR 하반기 목표</div><div class="val">${s.IR.th2}M</div><div class="note">S1 ${s.IR.h2} → 메울 양 ${gapChip(s.IR.gaph2)}</div></div>
      <div class="card" style="border-color:var(--warn)"><div class="lbl">목표까지 추가 필요(vs S1)</div><div class="val pos">+${D.tot_gap}M</div><div class="note" style="color:var(--mut)">회복 실현 + Action Plan</div></div>
    </div>

    <div class="chartbox" style="margin-top:14px">
      <h3>분기 목표 vs 자연전망(S1) <span class="axis-tag ax-val">금액축 · M SAR</span></h3>
      <table>
        <tr><th class="l">그룹 · 분기</th><th>S1 자연전망</th><th>목표</th><th>추가 필요</th><th class="l">해석</th></tr>
        ${[['OR','3Q','t3','q3','gap3'],['OR','4Q','t4','q4','gap4'],['IR','3Q','t3','q3','gap3'],['IR','4Q','t4','q4','gap4']].map(([g,q,tk,vk,gk])=>`
          <tr class="${g.toLowerCase()}-row"><td class="l">${g} ${q}</td><td>${f1(s[g][vk])}</td><td>${s[g][tk]}</td><td>${gapChip(s[g][gk])}</td>
          <td class="l" style="color:var(--mut);font-size:12px">${s[g][gk]>0.05?'회복 푸시 필요':(s[g][gk]<-0.05?'이미 초과 — 여유':'목표권 도달')}</td></tr>`).join('')}
      </table>
    </div>
    <div class="chartbox"><h3>그룹 분기: 자연전망(S1) vs 목표</h3><canvas id="cQuarter"></canvas></div>
  `;
  drawQuarter();
}
function drawQuarter(){
  const s=D.summary;
  const ctx=document.getElementById('cQuarter');
  if(charts.q) charts.q.destroy();
  charts.q=new Chart(ctx,{type:'bar',data:{
    labels:['OR 3Q','OR 4Q','IR 3Q','IR 4Q'],
    datasets:[
      {label:'자연전망',data:[s.OR.q3,s.OR.q4,s.IR.q3,s.IR.q4],backgroundColor:'#3b82f6'},
      {label:'목표',data:[s.OR.t3,s.OR.t4,s.IR.t3,s.IR.t4],backgroundColor:'rgba(148,163,184,.45)'},
    ]},options:{responsive:true,plugins:{legend:{labels:{color:'#e2e8f0'}}},
      scales:{x:{ticks:{color:'#cbd5e1'}},y:{ticks:{color:'#cbd5e1'},title:{display:true,text:'M SAR',color:'#94a3b8'}}}}});
}

// ---------- ② 채널 PSI ----------
function renderPSI(){
  const el=document.getElementById('psi');
  let body='';
  ['OR','IR'].forEach(g=>{
    const grp=D.rows.filter(r=>r.group===g);
    const sub={h1:0,jun:0,q3:0,q4:0,annual:0,ar:0,ovd:0};
    grp.forEach(r=>{['h1','jun','q3','q4','annual','ar','ovd'].forEach(k=>sub[k]+=r[k])});
    body+=`<tr class="grp ${g.toLowerCase()}-row"><td class="l">${g}계</td>
      <td>${sub.h1.toFixed(1)}</td><td>${sub.jun.toFixed(1)}</td><td>${sub.q3.toFixed(1)}</td><td>${sub.q4.toFixed(1)}</td>
      <td>${sub.annual.toFixed(1)}</td><td>${sub.ar.toFixed(1)}</td><td>${ovdChip(sub.ovd)}</td><td>–</td></tr>`;
    grp.forEach(r=>{
      body+=`<tr class="${r.seg?'seg':g.toLowerCase()+'-row'}"><td class="l">${r.ko}</td>
        <td>${r.h1.toFixed(1)}</td><td>${r.jun.toFixed(1)}</td><td>${r.q3.toFixed(1)}</td><td>${r.q4.toFixed(1)}</td>
        <td><b>${r.annual.toFixed(1)}</b></td><td>${r.ar.toFixed(1)}</td><td>${ovdChip(r.ovd)}</td><td>${mosChip(r.mos)}</td></tr>`;
    });
  });
  el.innerHTML=`
    <div class="chartbox">
      <h3>채널별 PSI <span class="axis-tag ax-val">금액축 ST·AR·OVD</span><span class="axis-tag ax-qty">수량축 MOS</span></h3>
      <div style="overflow-x:auto"><table>
        <tr><th class="l">채널 / 세그먼트</th><th>1-5실적</th><th>6월RSM</th><th>3Q FCST</th><th>4Q FCST</th><th>연간</th>
        <th>AR</th><th>OVD</th><th>MOS</th></tr>
        ${body}
      </table></div>
      <div style="color:var(--mut);font-size:12px;margin-top:10px">
        · 금액=M SAR. 3Q/4Q는 7~12월 FCST(1-5평균×시즌계수).
        · MOS=최근 재고÷1~5월 평균 Sell-out(수량축). <span class="chip c-ok">&lt;2.5</span> 정상 · <span class="chip c-warn">2.5~4</span> 주의 · <span class="chip c-bad">≥4</span> 과재고.
        · OVD <span class="chip c-warn">2.5~10</span> 주의 · <span class="chip c-bad">≥10</span> 위험. 세그먼트(OR기타·IR기타·SME)는 SO/재고 데이터 없어 MOS 미산출.
      </div>
    </div>`;
}

// ---------- ③ 이중축 추이 ----------
function renderDual(){
  const el=document.getElementById('dual');
  el.innerHTML=`
    <div class="secttitle">금액축 <span class="axis-tag ax-val">ST_val (M SAR) · 6월 이후 FCST</span></div>
    <div class="chartbox"><canvas id="cVal"></canvas></div>
    <div class="secttitle">수량축 <span class="axis-tag ax-qty">ST_qty (대) · 6월 이후 FCST</span></div>
    <div class="chartbox"><canvas id="cQty"></canvas></div>
    <div style="color:var(--mut);font-size:12px;margin-top:10px">
      ※ 두 축은 분리: 금액축은 AR·채권·회수와, 수량축은 Sell-out·재고와 연동. 1~5월 실선=실적, 6월 이후 점선=FCST.
      OR 시즌피크 8~9월(계수 ${D.season.OR?D.season.OR['8']:'-'}/${D.season.OR?D.season.OR['9']:'-'}), IR은 6·8·9월에 분산.
    </div>`;
  drawLine('cVal','grp_val','M SAR');
  drawLine('cQty','grp_qty','대');
}
function drawLine(id,key,unit){
  const ctx=document.getElementById(id);
  if(charts[id]) charts[id].destroy();
  const orD=D[key].OR.slice(1), irD=D[key].IR.slice(1);
  const seg=(arr,from)=>arr.map((v,i)=>i>=from?v:null);
  charts[id]=new Chart(ctx,{type:'line',data:{labels:MN,datasets:[
    {label:'OR 실적',data:orD.map((v,i)=>i<=4?v:null),borderColor:'#2563eb',backgroundColor:'#2563eb',tension:.3,spanGaps:false},
    {label:'OR FCST',data:orD.map((v,i)=>i>=4?v:null),borderColor:'#2563eb',borderDash:[6,4],tension:.3,spanGaps:true,pointStyle:'rectRot'},
    {label:'IR 실적',data:irD.map((v,i)=>i<=4?v:null),borderColor:'#dc2626',backgroundColor:'#dc2626',tension:.3,spanGaps:false},
    {label:'IR FCST',data:irD.map((v,i)=>i>=4?v:null),borderColor:'#dc2626',borderDash:[6,4],tension:.3,spanGaps:true,pointStyle:'rectRot'},
  ]},options:{responsive:true,plugins:{legend:{labels:{color:'#e2e8f0'}}},
    scales:{x:{ticks:{color:'#cbd5e1'}},y:{ticks:{color:'#cbd5e1'},title:{display:true,text:unit,color:'#94a3b8'}}}}});
}

// ---------- ④ Action Plan ----------
function renderPlan(){
  const el=document.getElementById('plan'), p=D.plan, s=D.summary;
  function block(title,arr,gap){
    if(gap<=0.05) return `<div class="card"><div class="lbl">${title}</div><div class="val neg">목표 초과</div>
      <div class="note" style="color:var(--mut)">Gap ${gap.toFixed(1)}M — 추가 푸시 불필요(여유). 재고·채권 관리에 집중.</div></div>`;
    const top=arr.slice(0,5);
    return `<div class="card"><div class="lbl">${title} · 필요 추가 <span class="pos">+${gap.toFixed(1)}M</span></div>
      <table style="margin-top:8px">
        <tr><th class="l">채널</th><th>추가 목표</th><th>MOS</th><th>OVD</th></tr>
        ${top.map(x=>`<tr><td class="l">${x.ko}</td><td class="pos">+${x.add.toFixed(1)}M</td><td>${mosChip(x.mos)}</td><td>${ovdChip(x.ovd)}</td></tr>`).join('')}
      </table></div>`;
  }
  el.innerHTML=`
    <div class="card" style="border-color:var(--warn);margin-bottom:14px">
      <div class="lbl">하반기 총 Gap = <span class="pos">+${D.tot_gap}M</span> — 분기별 귀속(자연전망 기여도 비례 배분)</div>
      <div class="note" style="color:var(--mut);margin-top:6px">
        OR 3Q(+${s.OR.gap3.toFixed(1)}M)가 최대 과제 — eXtra 8~9월 시즌피크 극대화가 핵심 레버.
        IR 4Q는 자연전망이 목표를 초과(여유) → 무리한 밀어내기 대신 BH 채권(OVD)·재고 정상화 우선.
      </div>
    </div>
    <div class="grid plan-grid">
      ${block('OR · 3Q',p.OR_3Q,s.OR.gap3)}
      ${block('OR · 4Q',p.OR_4Q,s.OR.gap4)}
      ${block('IR · 3Q',p.IR_3Q,s.IR.gap3)}
      ${block('IR · 4Q',p.IR_4Q,s.IR.gap4)}
    </div>
    ${revTable('OR')}
    ${revTable('IR')}
    <div class="chartbox" style="margin-top:14px"><h3>핵심 리스크 / 레버 (참모 의견)</h3>
      <ul style="margin-left:18px;line-height:1.9;font-size:14px">
        <li><b style="color:#f87171">BH 이중 리스크</b> — OVD ${D.rows.find(r=>r.name==='BH').ovd}M(AR의 절반) + 재고 MOS ${f1(D.rows.find(r=>r.name==='BH').mos)}개월. 하반기 최대 IR 채널이나, 금액축(채권)·수량축(재고) 동시 경고 → 밀어내기보다 <b>회수·소진 정상화</b> 선행.</li>
        <li><b style="color:#93c5fd">eXtra 구조적 의존</b> — 연간 ${D.rows.find(r=>r.name==='eXtra').annual}M(전체의 ~33%), OVD ${D.rows.find(r=>r.name==='eXtra').ovd}M로 채권 건전. OR 3Q gap의 대부분을 eXtra 8~9월 입고·프로모로 메우는 것이 현실적.</li>
        <li><b style="color:#fbbf24">전제 리스크</b> — 본 전망은 "거시 회복 ~60% 실현" 가정. 2025식 연말 부진(IR 11~12월 계수 0.69/0.51)이 재연되면 S1(충격지속)으로 회귀, Gap이 30M+로 재확대 → 월별 실적 모니터링 필수.</li>
      </ul>
    </div>`;
}
function revTable(g){
  const arr=D.reverse?D.reverse[g]:null; if(!arr||!arr.length) return '';
  return `<div class="chartbox" style="margin-top:14px">
    <h3>${g} 목표 역산 — ST(출하) 목표 → 필요 Sell-out(소진) <span class="axis-tag ax-qty">수량축</span></h3>
    <div style="overflow-x:auto"><table>
      <tr><th class="l">채널</th><th>ST목표(H2)</th><th>ST목표수량</th><th>현재고</th><th>현SO(H2환산)</th><th>필요SO(H2)</th><th>필요증감</th><th>MOS</th></tr>
      ${arr.map(x=>`<tr><td class="l">${x.ko}</td><td><b>${x.st_val.toFixed(1)}M</b></td><td>${x.st_qty.toLocaleString()}</td>
        <td>${x.stk?x.stk.toLocaleString():'–'}</td><td>${x.so_cur?x.so_cur.toLocaleString():'–'}</td>
        <td><b style="color:#fbbf24">${x.so_need?x.so_need.toLocaleString():'–'}</b></td>
        <td>${x.lift==null?'–':`<span class="chip ${x.lift>30?'c-bad':(x.lift>0?'c-warn':'c-ok')}">${x.lift>0?'+':''}${x.lift}%</span>`}</td>
        <td>${mosChip(x.mos)}</td></tr>`).join('')}
    </table></div>
    <div style="color:var(--mut);font-size:12px;margin-top:8px">→ <b>출하(Sell-thru) 목표는 채널이 그만큼 소진(Sell-out)해 재고를 기말 2개월 수준으로 정상화</b>해야 지속 가능. <b>필요SO</b>=하반기 요구 소진량, <b>필요증감</b>=현 Sell-out 런레이트 대비 증가율. <span class="chip c-bad">+30%↑</span> 과부하(과재고 채널) · <span class="chip c-ok">음수</span> 여유. ASP 기반 환산이라 ±10% 오차 — 방향성 지표.</div>
  </div>`;
}

// ---------- ⑤ 월별 실행플랜 (SO→재고 정상화) ----------
function renderExec(){
  const el=document.getElementById('exec');
  const all=[...(D.reverse?D.reverse.OR:[]),...(D.reverse?D.reverse.IR:[])].filter(x=>x.monthly&&x.monthly.length);
  all.sort((a,b)=>b.so_need-a.so_need);
  window._execAll=all;
  const opts=all.map((x,i)=>`<option value="${i}">${x.ko} — SO목표 ${x.so_need.toLocaleString()}대 (${x.lift>0?'+':''}${x.lift}%)</option>`).join('');
  el.innerHTML=`
    <div class="card" style="margin-bottom:14px">
      <div class="lbl">채널별 월별 PSI 실행플랜 — Sell-out 목표 → 재고·MOS 정상화 궤적</div>
      <div class="note" style="color:#cbd5e1;margin-top:6px;font-size:13px">Sell-thru 목표 달성의 조건은 <b>밀어내기가 아니라 Sell-out</b>입니다. SO목표를 시즌계수로 월배분 → 재고방정식(재고=전월+출하−소진)으로 <b>월별 재고·MOS 정상화 궤적</b>을 산출합니다. Sell-out이 되면 재고(MOS)와 채권(OD)이 동시에 정상화됩니다.</div>
      <select id="execSel" style="margin-top:10px;padding:9px;background:var(--bg);color:#e2e8f0;border:1px solid var(--line);border-radius:8px;font-size:14px;width:100%;max-width:420px">${opts}</select>
    </div>
    <div id="execBody"></div>`;
  document.getElementById('execSel').addEventListener('change',e=>drawExec(+e.target.value));
  drawExec(0);
}
function drawExec(idx){
  const x=window._execAll[idx]; const b=document.getElementById('execBody');
  const rows=x.monthly.map(r=>`<tr><td class="l">${r.m}월</td><td>${r.so.toLocaleString()}</td><td>${r.st.toLocaleString()}</td><td>${r.stk.toLocaleString()}</td><td>${mosChip(r.mos)}</td></tr>`).join('');
  const cats=(x.cats||[]).map(c=>`<tr><td class="l">${c.cat}</td><td><b>${c.qty.toLocaleString()}대</b></td></tr>`).join('');
  b.innerHTML=`
    <div class="grid kpis" style="margin-bottom:14px">
      <div class="card"><div class="lbl">하반기 SO(소진) 목표</div><div class="val">${x.so_need.toLocaleString()}<span style="font-size:14px;color:var(--mut)">대</span></div><div class="note">현 런레이트比 <span class="${x.lift>30?'pos':''}">${x.lift>0?'+':''}${x.lift}%</span></div></div>
      <div class="card"><div class="lbl">재고 정상화</div><div class="val">${mosChip(x.mos)}<span style="font-size:15px;color:var(--mut)"> → 2.0</span></div><div class="note" style="color:var(--mut)">현재고 ${x.stk?x.stk.toLocaleString():'–'}대 → 12월 목표</div></div>
      <div class="card"><div class="lbl">ST(출하) 목표 H2</div><div class="val">${x.st_qty.toLocaleString()}<span style="font-size:13px;color:var(--mut)">대 / ${x.st_val}M</span></div></div>
    </div>
    <div class="chartbox"><h3>월별 재고·소진·MOS 정상화 궤적</h3><canvas id="cExec"></canvas></div>
    <div class="grid plan-grid" style="margin-top:14px">
      <div class="card"><div class="lbl">월별 PSI 시뮬</div>
        <table style="margin-top:6px"><tr><th class="l">월</th><th>SO목표</th><th>ST출하</th><th>기말재고</th><th>MOS</th></tr>${rows}</table></div>
      <div class="card"><div class="lbl">SO목표 카테고리 분해 — 무엇을 소진하나</div>
        <table style="margin-top:6px"><tr><th class="l">카테고리</th><th>하반기 SO목표</th></tr>${cats||'<tr><td class="l" colspan=2 style="color:var(--mut)">세그먼트 — 카테고리 데이터 없음</td></tr>'}</table>
        <div style="color:var(--mut);font-size:12px;margin-top:8px">→ 비중 큰 카테고리가 <b>프로모·영업 1순위</b>. 채널 제품 DNA에 맞춰 소진.</div></div>
    </div>`;
  drawExecChart(x);
}
function drawExecChart(x){
  const ctx=document.getElementById('cExec'); if(charts.exec)charts.exec.destroy();
  charts.exec=new Chart(ctx,{data:{labels:x.monthly.map(r=>r.m+'월'),datasets:[
    {type:'bar',label:'기말재고(대)',data:x.monthly.map(r=>r.stk),backgroundColor:'rgba(59,130,246,.5)',yAxisID:'y'},
    {type:'bar',label:'SO목표(대)',data:x.monthly.map(r=>r.so),backgroundColor:'rgba(16,185,129,.55)',yAxisID:'y'},
    {type:'line',label:'MOS(개월)',data:x.monthly.map(r=>r.mos),borderColor:'#fbbf24',backgroundColor:'#fbbf24',yAxisID:'y1',tension:.3,pointRadius:4}
  ]},options:{responsive:true,plugins:{legend:{labels:{color:'#e2e8f0'}}},scales:{
    x:{ticks:{color:'#cbd5e1'}},
    y:{position:'left',ticks:{color:'#cbd5e1'},title:{display:true,text:'대',color:'#94a3b8'}},
    y1:{position:'right',min:0,ticks:{color:'#fbbf24'},grid:{drawOnChartArea:false},title:{display:true,text:'MOS(개월)',color:'#fbbf24'}}
  }}});
}

// ---------- ⑥ eXtra 입고계획 ----------
function renderExtra(){
  const e=D.extra, el=document.getElementById('extra');
  const catRow=(arr)=>arr.map(c=>`<tr><td class="l">${c.cat}</td><td>${c.mix}%</td><td>${c.val.toFixed(1)}M</td><td>${c.asp.toFixed(0)}</td><td><b>${c.qty.toLocaleString()}대</b></td></tr>`).join('');
  const buf=(q)=>Math.round(q*(1+e.buf/100));
  el.innerHTML=`
    <div class="grid kpis" style="margin-bottom:14px">
      <div class="card"><div class="lbl">8~9월 입고 매출목표 (=Sell-in)</div><div class="val">${(e.tgt8+e.tgt9).toFixed(1)}M</div><div class="note" style="color:var(--mut)">자연 ${(e.nat8+e.nat9).toFixed(1)} + 추가 ${e.ex_add.toFixed(1)}M</div></div>
      <div class="card"><div class="lbl">8월 입고 (목표 / 권장+${e.buf}%버퍼)</div><div class="val">${e.tgt8.toFixed(1)}M</div><div class="note">${e.qty8.toLocaleString()}대 → 권장 <b>${buf(e.qty8).toLocaleString()}대</b></div></div>
      <div class="card"><div class="lbl">9월 입고 (목표 / 권장+${e.buf}%버퍼)</div><div class="val">${e.tgt9.toFixed(1)}M</div><div class="note">${e.qty9.toLocaleString()}대 → 권장 <b>${buf(e.qty9).toLocaleString()}대</b></div></div>
      <div class="card"><div class="lbl">8~9월 실효 ASP (AC본품)</div><div class="val">${e.season_asp.toLocaleString()}</div><div class="note" style="color:var(--mut)">SAR · 인버터 집중 ↑</div></div>
    </div>

    <div class="chartbox">
      <h3>산출 근거 (금액→수량 역산) <span class="axis-tag ax-qty">수량축</span></h3>
      <div style="color:#cbd5e1;font-size:13px;line-height:1.8">
        · eXtra 1~5월 AC 월평균 매출 <b>${e.avg_val.toFixed(1)}M</b> × OR 시즌계수(8월 ${e.s8}, 9월 ${e.s9}) = 자연전망 8월 ${e.nat8.toFixed(1)}M / 9월 ${e.nat9.toFixed(1)}M<br>
        · OR 3Q Gap +${e.or_gap3.toFixed(1)}M 중 eXtra 귀속 <b>${e.ex_share.toFixed(0)}%</b>(자연전망 비중) = 추가 <b>+${e.ex_add.toFixed(1)}M</b> → 8~9월 시즌비례 배분(8월 +${e.add8.toFixed(1)} / 9월 +${e.add9.toFixed(1)})<br>
        · ⚠️ <b>악세사리 제외</b> AC 본품만. 8~9월 시즌믹스(인버터 집중)·카테고리 ASP로 수량 환산.
      </div>
    </div>

    <div class="grid plan-grid" style="margin-top:14px">
      <div class="card"><div class="lbl">8월 카테고리 배분 (시즌믹스)</div>
        <table style="margin-top:6px"><tr><th class="l">카테고리</th><th>믹스</th><th>금액</th><th>ASP</th><th>입고수량</th></tr>${catRow(e.cat8)}</table></div>
      <div class="card"><div class="lbl">9월 카테고리 배분 (시즌믹스)</div>
        <table style="margin-top:6px"><tr><th class="l">카테고리</th><th>믹스</th><th>금액</th><th>ASP</th><th>입고수량</th></tr>${catRow(e.cat9)}</table></div>
    </div>

    <div class="chartbox" style="margin-top:14px">
      <h3>입고 1순위 SKU — 결품임박 (high Sell-out · MOS&lt;1.5) <span style="font-size:11px;color:var(--mut)">${e.sku_month} 기준</span></h3>
      <div style="overflow-x:auto"><table>
        <tr><th class="l">모델</th><th>BTU</th><th class="l">타입</th><th>현재고</th><th>월 Sell-out</th><th>MOS</th><th class="l">판정</th></tr>
        ${e.sku_in.map(s=>`<tr><td class="l"><b>${s.std}</b></td><td>${s.btu}</td><td class="l">${s.hc}</td><td>${s.stk.toLocaleString()}</td><td>${s.so.toLocaleString()}</td><td>${mosChip(s.mos)}</td><td class="l"><span class="chip c-bad">${s.flag}</span></td></tr>`).join('')}
      </table></div>
      <div style="color:var(--mut);font-size:12px;margin-top:8px">→ 이 SKU들은 현재 sell-out 대비 재고 1.5개월 미만(LA242H·AM242C는 사실상 결품). 8~9월 피크 전 <b>최우선 입고</b>.</div>
    </div>

    <div class="chartbox" style="margin-top:14px">
      <h3>입고 회피 SKU — 과재고 (MOS≥3)</h3>
      <table><tr><th class="l">모델</th><th>BTU</th><th>월 Sell-out</th><th>MOS</th></tr>
        ${e.sku_avoid.map(s=>`<tr><td class="l">${s.std}</td><td>${s.btu}</td><td>${s.so.toLocaleString()}</td><td>${mosChip(s.mos)}</td></tr>`).join('')}
      </table>
      <div style="color:var(--mut);font-size:12px;margin-top:8px">→ 이미 재고 과다. 8~9월 추가 입고 대신 기존 재고 소진(프로모) 우선.</div>
    </div>

    <div class="chartbox" style="margin-top:14px"><h3>입고 타이밍 · 실행 (참모 권고)</h3>
      <ul style="margin-left:18px;line-height:1.9;font-size:14px">
        <li><b>8월 판매분</b>(권장 ${buf(e.qty8).toLocaleString()}대) → <b>7월 1~2주 입고</b> 완료 (매대 사전 확보)</li>
        <li><b>9월 판매분</b>(권장 ${buf(e.qty9).toLocaleString()}대) → <b>8월 1~2주 입고</b> 완료 (9월 피크 계수 ${e.s9} 대비)</li>
        <li><b>안전버퍼 +${e.buf}%</b> — 8~9월은 결품 1건 = 판매 직결 손실. 결품임박 SKU(LA182C·NS242C·LA242H 등) 집중 배치.</li>
        <li><b>소화가능성</b> — eXtra 8~9월 인버터는 과거에도 채널 최대 흡수처(2024·2025 8~9월 인버터 16,328대). 목표 ${(e.qty8+e.qty9).toLocaleString()}대는 도전적이나 시즌피크+gap푸시로 달성권. 단 <b>매주 sell-out 모니터링</b>으로 과재고(ND182C·ND242C) 전이 차단.</li>
      </ul>
    </div>`;
}

// ---------- 탭 전환 (숨겨진 탭 차트 재렌더 — 0x0 버그 방지) ----------
const renderers={overview:renderOverview,psi:renderPSI,dual:renderDual,plan:renderPlan,exec:renderExec,extra:renderExtra};
function activate(p){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.p===p));
  document.querySelectorAll('.panel').forEach(x=>x.classList.toggle('active',x.id===p));
  renderers[p]();
}
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>activate(t.dataset.p)));

document.getElementById('subline').textContent='공식 FCST=형님 목표(거시 회복 반영): OR 3Q70·4Q25·H2 95M / IR 3Q60·4Q35·H2 95M · 충격기(사우디제이션·이란미국전) 보정 · 단위 M SAR';
document.getElementById('foot').textContent='데이터: unified_psi.json (단일 진실) · '+D.fcst_method+' · 이중축 분리(금액↔AR/OVD, 수량↔SO/재고). 재생성: build_h2_dashboard.py';
renderOverview();
</script>
</body>
</html>
"""

out = HTML.replace('__PAYLOAD__', json.dumps(PAYLOAD, ensure_ascii=False))
open(os.path.join(HERE, 'index.html'), 'w').write(out)
print('생성 완료: index.html')
print(f"연간 전망 {tot_annual}M / 하반기 총 Gap +{tot_gap}M")
print(f"OR H2 {summary['OR']['h2']}/{summary['OR']['th2']} (gap {summary['OR']['gaph2']:+}) | "
      f"IR H2 {summary['IR']['h2']}/{summary['IR']['th2']} (gap {summary['IR']['gaph2']:+})")
