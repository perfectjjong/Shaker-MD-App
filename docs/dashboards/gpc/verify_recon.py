#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPC 대시보드 배포 데이터 ↔ 원본 대조 (2026-09-12 임원 보고용 점검).
현재 스키마(채널 4분할·비B2C 제외·조정행 안분·IR_Others 실명·가마감·예상·AR)에 맞춘 독립 재계산.
층 1: 연 합계 — 원본 전 행 Σ == 대시보드 Σ + 제외(meta.excluded)  [완전 독립: SSOT 판정 불필요]
층 2: 연×월 / 연×월×카테고리 — 원본(계정 있는 행은 SSOT 로 제외 판정) == 대시보드
층 3: 연×월×sub×계정 — SSOT 함수로 재집계(정의 그 자체) == 대시보드 (조정행 안분분은 별도 대조)
층 4: 가마감 8월 — Financial_Final 재집계 == gpc_provisional.json (sub×cat)
층 5: 예상 — RSM FCST 원본 총액 == gpc_forecast.json
층 6: AR — 월말 원본 재집계(회사코드1000·SSOT B2C) == gpc_ar.json (표본 6개월)
"""
import collections, glob, json, os, re, sys
import openpyxl
sys.path.insert(0, '/home/ubuntu/2026/10. Automation/03. Operation/00. GPC/_engine')
sys.path.insert(0, '/home/ubuntu/2026/10. Automation')
sys.path.insert(0, '/home/ubuntu/Shaker-MD-App/docs/dashboards/gpc')
import gpc_core as G
from shared_classification import ACCOUNT_ALIAS, IR_CHANNEL_MAP, OR_CHANNEL_MAP
import build_gpc_dashboard as B          # 카테고리 정규화·월 파싱·컬럼 좌표는 빌더 정의를 그대로 씀(재구현하면 그게 오답)

JS = '/home/ubuntu/Shaker-MD-App/docs/dashboards/gpc/gpc_data.js'
K = ('qty', 'gsv', 'yed', 'adc', 'vpd', 'dsi', 'cogs', 'inv', 'vsp')
num = lambda v: float(v) if isinstance(v, (int, float)) else 0.0
FAIL = []


def arr(t, n):
    s = t.index(f'const {n} = ') + len(f'const {n} = ')
    return json.loads(t[s:t.index(';\n', s)])


t = open(JS, encoding='utf-8').read()
META, DATA, OFF, FC, AR = (arr(t, n) for n in ('GPC_META', 'GPC_DATA', 'GPC_OFFICIAL', 'GPC_FORECAST', 'GPC_AR'))
PV = META['provisional']
MAIN_ID = {**OR_CHANNEL_MAP, **{k: v for k, v in IR_CHANNEL_MAP.items() if v != 'IR_Others'}}


def sums(rows, keyf):
    o = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        k = keyf(r)
        if k is None: continue
        for f in K: o[k][f] += r[f]
    return o


def cmp(title, a, b, tol=1.0, show=8):
    keys = set(a) | set(b); bad = 0; worst = []
    for k in keys:
        for f in K:
            d = b.get(k, {}).get(f, 0.0) - a.get(k, {}).get(f, 0.0)
            if abs(d) > tol:
                bad += 1; worst.append((abs(d), k, f, a.get(k, {}).get(f, 0.0), b.get(k, {}).get(f, 0.0)))
    worst.sort(reverse=True)
    print(f"  {title}: {len(keys)*len(K):,}셀 · 불일치 {bad}건 {'✅' if bad == 0 else '❌'}")
    for _, k, f, va, vb in worst[:show]: print(f"     ❌ {k} {f}: 원본 {va:,.1f} vs 대시보드 {vb:,.1f} (Δ {vb-va:+,.1f})")
    if bad: FAIL.append(f"{title} {bad}건")
    return bad


# ───────── 원본 Accrual 읽기 (빌더와 같은 좌표/정규화) ─────────
src = B.latest_src(); print('원본:', os.path.basename(src))
wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
raw = []            # 모든 행 (제외·조정행 포함)
for sheet in wb.sheetnames:
    mo = re.fullmatch(r'Raw (20\d\d)', sheet)
    if not mo: continue
    y = int(mo.group(1))
    for row in wb[sheet].iter_rows(min_row=2, values_only=True):
        if row[28] is None and row[19] is None and row[12] is None: continue
        m = B.row_month(row)
        chan = str(row[29] or '')
        ch = 'IR' if 'IR' in chan else ('OR' if 'OR' in chan else None)
        if not m or not ch: continue                       # 빌더도 skip 하는 행
        try: cid = int(float(row[4]))
        except (TypeError, ValueError): cid = None
        rec = dict(y=y, m=m, ch=ch, cid=cid, name=str(row[5] or ''), cat=B.row_cat(row), qty=num(row[18]))
        for f in K[1:]: rec[f] = num(row[B.AMT[f]])
        ac = B.account_of(row)
        rec['ac0'] = ac
        rec['sub'] = B.sub_channel(cid, ac)
        raw.append(rec)
wb.close()
print(f'원본 행 {len(raw):,} · 계정없음(조정행) {sum(1 for r in raw if r["cid"] is None):,} · 제외(sub None, 계정있음) {sum(1 for r in raw if r["sub"] is None and r["cid"] is not None):,}')
actual = [r for r in DATA if not (r['y'] == PV['year'] and r['m'] == PV['month'])]     # 가마감 제외한 실적

print('\n[층1] 연 합계 — 원본 전 행 Σ  ==  대시보드 Σ + meta.excluded')
a = sums(raw, lambda r: r['y'])
b = sums(actual, lambda r: r['y'])
for y, e in META['excluded'].items():
    for f in K: b[int(y)][f] += e[f]
cmp('연 합계(9지표)', a, b, tol=2.0)

print('\n[층2] 연×월 · 연×월×카테고리 — 제외분(SSOT)을 원본에서 빼고 대조')
inc = [r for r in raw if not (r['sub'] is None and r['cid'] is not None)]        # 대시보드 포함 모집단(조정행 포함)
cmp('연×월', sums(inc, lambda r: (r['y'], r['m'])), sums(actual, lambda r: (r['y'], r['m'])), tol=2.0)
cmp('연×월×카테고리', sums(inc, lambda r: (r['y'], r['m'], r['cat'])), sums(actual, lambda r: (r['y'], r['m'], r['cat'])), tol=2.0)
# 조정행(계정 없음) 은 같은 (연,월,ch,cat) 안에서 안분되므로 그 입도까지는 Δ0 이어야 한다
cmp('연×월×ch(IR/OR)×카테고리', sums(inc, lambda r: (r['y'], r['m'], r['ch'] if r['sub'] is None else ('OR' if r['sub'] == 'OR' else 'IR'), r['cat'])),
    sums(actual, lambda r: (r['y'], r['m'], r['ch'], r['cat'])), tol=2.0)

print('\n[층3] 연×월×sub×계정 — SSOT 재집계 vs 대시보드 (조정행은 안분 전 별도)')
def ac_of(r):
    if r['sub'] is None: return None
    ac = r['ac0']
    if ac == 'Others' and r['sub'] == 'IR_Others': ac = G.account_name(r['cid'], r['name'])
    return ac
with_cid = [dict(r, ac=ac_of(r)) for r in inc if r['sub'] is not None]   # 계정 ID 없어도 이름으로 메인 계정이 식별되면(eXtra 법인명 등) 조정행이 아니다 — 빌더와 동일
lump = [r for r in inc if r['sub'] is None]
a3 = sums(with_cid, lambda r: (r['y'], r['m'], r['sub'], r['ac']))
b3 = sums(actual, lambda r: (r['y'], r['m'], r['sub'], r['ac']))
# 조정행 총액을 (연,월,ch,cat) 별로 대시보드 셀들에 GSV 비중 안분 → 원본 측에 더해 대조 (빌더 규칙 재현)
L = sums(lump, lambda r: (r['y'], r['m'], r['ch'], r['cat']))
cells = collections.defaultdict(list)
for r in actual: cells[(r['y'], r['m'], r['ch'], r['cat'])].append(r)
cells2 = collections.defaultdict(list)
for r in actual: cells2[(r['y'], r['m'], r['ch'])].append(r)
for k, v in L.items():
    cand = cells.get(k) or cells2.get(k[:3]) or []
    tot = sum(abs(c['gsv']) for c in cand)
    for c in cand:
        w = abs(c['gsv']) / tot if tot else 1.0 / len(cand)
        for f in K: a3[(c['y'], c['m'], c['sub'], c['ac'])][f] += v[f] * w
cmp('연×월×sub×계정(안분 재현 포함)', a3, b3, tol=2.0)
print(f'  참고: 조정행 {len(lump)}건 · GSV {sum(r["gsv"] for r in lump):,.0f} · VSP {sum(r["vsp"] for r in lump):,.0f}')

print('\n[층4] 가마감 — Financial_Final 재집계 == gpc_provisional.json (sub×cat)')
import build_provisional_financial as BP
pj = json.load(open('/home/ubuntu/Shaker-MD-App/docs/dashboards/gpc/gpc_provisional.json'))
rows, sk = BP.build('3. Aug 2026 GPC Financial_Final.xlsx', flip_cost=False)
cmp('가마감 sub×cat', sums(rows, lambda r: (r['sub'], r['cat'])), sums(pj['rows'], lambda r: (r['sub'], r['cat'])), tol=1.0)
prov_in_data = [r for r in DATA if r['y'] == PV['year'] and r['m'] == PV['month']]
cmp('가마감 → GPC_DATA 주입', sums(pj['rows'], lambda r: (r['sub'], r['ac'], r['cat'])), sums(prov_in_data, lambda r: (r['sub'], r['ac'], r['cat'])), tol=0.5)

print('\n[층5] 예상 — RSM FCST 원본 총액 == gpc_forecast.json')
FD = '/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/00. Raw Data/02. 2026/06. RSM FCST/'
wb = openpyxl.load_workbook(glob.glob(FD + '00. OR/*Sep Plan Nestor format.xlsx')[0], read_only=True, data_only=True)
rows_ = list(wb['Sep'].iter_rows(values_only=True)); wb.close()
or_v = or_q = 0.0
for r in rows_[2:]:
    if not r or not r[0] or not r[3]: continue
    mm = str(r[3]).strip()
    if mm.upper().endswith('TTL') or mm.upper() == 'TOTAL': continue
    for j in range(6):
        q = r[5 + j] if isinstance(r[5 + j], (int, float)) else 0
        v = r[11 + j] if isinstance(r[11 + j], (int, float)) else 0
        if q > 0: or_q += q; or_v += v
wb = openpyxl.load_workbook(glob.glob(FD + '01. IR/09. Sep/*Accum*.xlsx')[0], read_only=True, data_only=True)
rows_ = list(wb.worksheets[0].iter_rows(values_only=True)); wb.close()
hdr = [str(x).replace('\n', ' ').strip() if x else '' for x in rows_[1]]
qi = next(i for i, h in enumerate(hdr) if h.lower().startswith('sep') and 'plan' in h.lower())
vi = next(i for i, h in enumerate(hdr) if h.lower().startswith('sep') and 'value' in h.lower())
ir_v = ir_q = 0.0
for r in rows_[2:]:
    try: q = float(r[qi] or 0); v = float(r[vi] or 0)
    except (TypeError, ValueError): continue
    if q > 0: ir_q += q; ir_v += v
fc_v = sum(l['gsv'] for l in FC['lines']); fc_q = sum(l['sets'] for l in FC['lines'])
print(f"  RSM FCST 원본 GSV OR {or_v:,.0f} + IR {ir_v:,.0f} = {or_v+ir_v:,.0f} · 세트 {or_q+ir_q:,.0f}")
print(f"  gpc_forecast   GSV {fc_v:,.0f} · 세트 {fc_q:,.0f} · Δ GSV {fc_v-(or_v+ir_v):+,.0f} · Δ 세트 {fc_q-(or_q+ir_q):+,.0f}  {'✅' if abs(fc_v-(or_v+ir_v))<2 and abs(fc_q-(or_q+ir_q))<0.5 else '❌'}")
if abs(fc_v - (or_v + ir_v)) >= 2: FAIL.append('예상 총액')
# rows(집계) vs lines(상세) 내부 정합
UPU = {'Split Inverter': 2, 'Split On/Off': 2, 'Window AC': 1, 'Floor Standing AC': 2, 'Concealed Set': 2}   # rows.qty = 세트×유닛
cmp('예상 rows==lines 집계', sums([dict(l, **{f: l.get(f, 0.0) for f in K if f not in l and f != 'qty'}, qty=l['sets'] * UPU[l['cat']]) for l in FC['lines']], lambda r: (r['sub'], r['ac'], r['cat'])),
    sums(FC['rows'], lambda r: (r['sub'], r['ac'], r['cat'])), tol=1.5)

print('\n[층6] AR — 월말 원본(회사코드 1000·SSOT B2C) 재집계 == gpc_ar.json  (표본 6개월)')
OV = '/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/00. Raw Data/02. 2026/04. Overdue/00. Daily Overdue'
HO = '/home/ubuntu/2026/10. Automation/11. June Hand over/Receivable'
wb = openpyxl.load_workbook(f'{HO}/Combined_2024~2026 Salvage Data~JCO.xlsx', read_only=True, data_only=True); MP = {}
for sh in wb.sheetnames:
    if 'ALL DATA' not in sh: continue
    it = wb[sh].iter_rows(values_only=True); next(it, None); h = [str(x).strip() if x else '' for x in (next(it, None) or [])]
    Kk = {x: i for i, x in enumerate(h) if x}; o, n = Kk.get('Customer NO Org.'), Kk.get('New Customer No. Mapping')
    for r in it:
        if o is None: break
        if r[o] and r[n]:
            v = str(r[n]).strip().lstrip('0')
            if v.isdigit(): MP.setdefault(str(r[o]).strip().lstrip('0'), v)
wb.close()
def ar_raw(path, um):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True); ws = wb[wb.sheetnames[0]]; it = ws.iter_rows(values_only=True)
    for r in it:
        if r and any(isinstance(x, str) and x.strip() == 'Customer NO' for x in r[:8]): h = [str(x).strip() if x else '' for x in r]; break
    Kk = {x: i for i, x in enumerate(h) if x}; bal = collections.defaultdict(float); ex = 0.0
    for r in it:
        c = r[Kk['Customer NO']]
        if c is None or str(r[Kk['Company Code']]).strip() != '1000': continue
        k = str(c).strip().lstrip('0'); k = MP.get(k, k) if um else k
        try: cid = ACCOUNT_ALIAS.get(int(k), int(k))
        except ValueError: continue
        sub = G.sub_channel(cid, MAIN_ID.get(cid))
        if sub is None: ex += num(r[Kk['Balance']]); continue
        bal[sub] += num(r[Kk['Balance']])
    wb.close(); return bal, ex
samples = [(2024, 3, f'{HO}/2024 AR data/3. End of Mar 24 Actual.xlsx', True), (2024, 12, f'{HO}/2024 AR data/12. End of Dec 24 Coll Actual.xlsx', True),
           (2025, 6, f'{OV}/250630_Overdue.xlsx', False), (2025, 12, f'{OV}/251231_Overdue.xlsx', False),
           (2026, 3, f'{OV}/260331_Overdue.xlsx', False), (2026, 8, f'{OV}/260831_Overdue.xlsx', False)]
bad6 = 0
for y, m, p, um in samples:
    bal, ex = ar_raw(p, um)
    js = collections.defaultdict(float)
    for r in AR['rows']:
        if r['y'] == y and r['m'] == m: js[r['sub']] += r['ar']
    exj = AR['excluded'][f'{y}-{m:02d}']['ar']
    d = {s: js[s] - bal[s] for s in set(bal) | set(js)}; mx = max(abs(v) for v in d.values()) if d else 0
    ok = mx < 12 and abs(exj - ex) < 2      # sub 합 = 계정별 정수 반올림값의 합(계정 ~20개 × ±0.5) → 누적 반올림 허용
    bad6 += (not ok)
    print(f"  {y}-{m:02d}: B2C {sum(bal.values())/1e6:8.2f}M vs {sum(js.values())/1e6:8.2f}M · 제외 {ex/1e6:7.2f}M vs {exj/1e6:7.2f}M · sub 최대Δ {mx:,.0f} {'✅' if ok else '❌'}")
if bad6: FAIL.append(f'AR 표본 {bad6}개월')
# AR 5구간 Σ = AR 항등식 전수
viol = sum(1 for r in AR['rows'] if abs((r['o1'] + r['o2'] + r['o3'] + r['o4'] + r['o5']) - r['ar']) > 2)
print(f"  AR 연령 Σ=AR 항등식 위반: {viol}/{len(AR['rows'])} {'✅' if viol == 0 else '❌'}")
if viol: FAIL.append('AR 항등식')

print('\n' + '=' * 70)
print('결과:', '전 층 Δ0 ✅' if not FAIL else '불일치 ❌ ' + ' / '.join(FAIL))
