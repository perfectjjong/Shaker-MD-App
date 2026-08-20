#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unified_psi.json에 7~12월 FCST(금액·수량 이중축)를 산출해 추가한다.
방법론(2026-06-17 형님 확정):
  - 실적구간(1~ACT_END월) = data.json txn 실적 (권위). ACT_END = sell_thru_date 직전 마감월.
  - RSM월 = rsm_fcst embed (account별). 실적으로 마감된 달이면 실적 우선.
  - 이후~12월 = bucket 실적구간 평균 × 그룹(OR/IR) 시즌계수
            시즌계수(m) = 과거연도 m월 / 그 연도 '동일 실적구간' 평균 (분모 구간 일치 필수)
  ⚠️ 월 리터럴 금지: 구간은 전부 ACT_END/RSM_M/FCST_START 에서 파생시킨다 (2026-08-20).
  - 이중축: value(st_val) / qty(st_qty) 각각 동일 로직.
16 bucket = 13채널 + OR_Others + IR_Others + SME.
"""
import json, sys
sys.path.insert(0, '/home/ubuntu/2026/10. Automation')
import shared_classification as sc

DASH = '/home/ubuntu/Shaker-MD-App/docs/dashboards/sell-thru-progress'
d = json.load(open(f'{DASH}/data.json'))
txn, rsm, master = d['txn'], d['rsm_fcst'], d['master']

# ── 실적/예측 경계 (2026-08-20 동적화) ──────────────────────────────
# 기존에는 "1~5월 실적 / 6월 RSM / 7~12월 예측"이 하드코딩이라, data.json 에 6·7월
# 실적이 쌓여도 계속 예측치로 덮어썼다 (H2 대시보드가 6/17 기준에서 정지한 원인).
# ⚠️ 예측 산식(1~5월 평균 × 시즌계수)은 형님 확정 방법론이라 그대로 둔다.
#    바뀌는 것은 "실적이 있는 달은 실적을 쓴다"는 부분뿐.
_MONTH_NAMES = ['january', 'february', 'march', 'april', 'may', 'june',
                'july', 'august', 'september', 'october', 'november', 'december']
_sd = str(d.get('sell_thru_date', '')).strip()          # 예: '08-19'
try:
    ACT_END = int(_sd.split('-')[0]) - 1                 # 진행중 월 직전까지가 마감 실적
except (ValueError, IndexError):
    ACT_END = 5
ACT_END = max(1, min(12, ACT_END))
_rm = str(rsm.get('_month', '')).strip().lower()         # 예: 'August 2026'
RSM_M = next((i + 1 for i, n in enumerate(_MONTH_NAMES) if n in _rm), 0)
FCST_START = max(ACT_END, RSM_M) + 1
print(f"[경계] 실적 1~{ACT_END}월 (sell_thru_date={_sd}) · "
      f"RSM {RSM_M or '-'}월 · 예측 {FCST_START}~12월")
ALIAS = sc.ACCOUNT_ALIAS
ORC, IRC = sc.OR_CHANNEL_MAP, sc.IR_CHANNEL_MAP
master_team = {int(float(r['id'])): r.get('team', '') for r in master}

def to_bucket(aid, team):
    """account_id + team → 16 bucket 중 하나."""
    try:
        aid = int(float(aid))
    except Exception:
        return None
    aid = ALIAS.get(aid, aid)
    if aid in ORC:
        return ORC[aid]
    if aid in IRC and IRC[aid] != 'IR_Others':
        return IRC[aid]
    # 세그먼트 (13채널 외) — 형님 5그룹 화이트리스트만. B2B(Projects/AFS/ESCO/AMC 등)는 제외.
    if team in ('OR', 'OR_Others'):
        return 'OR_Others'
    if team == 'SME':
        return 'SME'
    if team == 'IR_Others' or team == 'IR':
        return 'IR_Others'   # IR team 중 13채널 외 + IR_Others team
    return None   # Projects/AFS/ESCO/AMC/Showrooms/Workshops/Spare/E-Commerce/빈값 → 목표 범위 밖

GROUP = {  # bucket → 시즌곡선 그룹
    'eXtra': 'OR', 'Al Manea': 'OR', 'SWS': 'OR', 'Black Box': 'OR',
    'Al Khunizan': 'OR', 'OR_Others': 'OR',
    'BH': 'IR', 'BM': 'IR', 'Tamkeen': 'IR', 'Zagzoog': 'IR', 'Dhamin': 'IR',
    'Star Appliance': 'IR', 'Al Ghanem': 'IR', 'Al Shathri': 'IR',
    'IR_Others': 'IR', 'SME': 'IR',
}

# ---- 1) 그룹 시즌계수 = 2024·2025 가중평균 (형님 2026-06-18: 최근 추세 반영, 2024:2025=4:6) ----
# 2024만 보면 하반기 강세 편향, 2025만 보면 하반기 비정상 부진 → 최근(2025)에 가중.
SEASON_YEARS = (2024, 2025)
WEIGHTS = {2024: 0.4, 2025: 0.6}
gyr = {y: {'OR': [0.0]*13, 'IR': [0.0]*13} for y in SEASON_YEARS}
for t in txn:
    if t[0] not in SEASON_YEARS:
        continue
    team = t[5]
    grp = 'OR' if team in ('OR', 'OR_Others') else ('IR' if team in ('IR', 'IR_Others', 'SME') else None)
    if not grp:
        continue
    gyr[t[0]][grp][int(t[1])] += (t[8] or 0)
season = {}
for grp in ('OR', 'IR'):
    num = {m: 0.0 for m in range(1, 13)}; den = 0.0
    for y in SEASON_YEARS:
        base = sum(gyr[y][grp][1:ACT_END + 1]) / ACT_END   # 해당 연도 실적구간 평균
        if base <= 0:
            continue
        w = WEIGHTS[y]; den += w
        for m in range(1, 13):
            num[m] += w * (gyr[y][grp][m] / base)
    season[grp] = {m: (num[m] / den if den else 0) for m in range(1, 13)}

# ---- 2) bucket별 1~5월 실적 (value, qty) + AC본품 ASP(악세사리 제외) ----
AC_CATS = {'Split Inverter', 'Split on/off', 'Free Standing', 'Cassette', 'Concealed', 'Window'}  # 라벨='Window'(확인). Multi-V/Unitary/AHU=상업용 제외(리테일 SO 모집단 일치)
buckets = {}
ac_acc = {}   # bucket → [AC val, AC qty] (ST_qty↔SO_qty 모집단 일치용)
cat_acc = {}  # bucket → {category: qty} (카테고리 믹스 — SO목표 카테고리 분해용)
def ensure(b):
    if b not in buckets:
        buckets[b] = {'val': {m: 0.0 for m in range(1, 13)}, 'qty': {m: 0.0 for m in range(1, 13)}}
    return buckets[b]
for t in txn:
    if t[0] != 2026 or not (1 <= int(t[1]) <= ACT_END):
        continue
    b = to_bucket(t[3], t[5])
    if not b:
        continue
    e = ensure(b); e['val'][int(t[1])] += (t[8] or 0); e['qty'][int(t[1])] += (t[9] or 0)
    if t[7] in AC_CATS:
        a = ac_acc.setdefault(b, [0.0, 0.0]); a[0] += (t[8] or 0); a[1] += (t[9] or 0)
        cm = cat_acc.setdefault(b, {}); cm[t[7]] = cm.get(t[7], 0) + (t[9] or 0)

# 13채널 0행 보장 (Zagzoog 등 ST=0 채널도 표시)
for b in ('eXtra','Al Manea','SWS','Black Box','Al Khunizan','BH','BM','Tamkeen',
          'Zagzoog','Dhamin','Star Appliance','Al Ghanem','Al Shathri'):
    ensure(b)

# 검증: bucket 1~5월 합 = txn 2026 1~5월 OR/IR 그룹 합
_chk = {'OR':0.0,'IR':0.0}
for b,e in buckets.items():
    _chk[GROUP.get(b,'IR')] += sum(e['val'][m] for m in range(1, ACT_END + 1))
print(f"[검증] 1~{ACT_END}월 실적 OR={_chk['OR']/1e6:.1f}M  IR={_chk['IR']/1e6:.1f}M")

# ---- 3) RSM FCST 적용월 (account별) — 실적 마감월이면 실적 우선, RSM skip ----
_use_rsm = RSM_M > ACT_END
for aid, v in (rsm['value'].items() if _use_rsm else []):
    b = to_bucket(aid, master_team.get(int(float(aid)), ''))
    if b:
        ensure(b)['val'][RSM_M] += v
for aid, q in (rsm['qty'].items() if _use_rsm else []):
    b = to_bucket(aid, master_team.get(int(float(aid)), ''))
    if b:
        ensure(b)['qty'][RSM_M] += q

# ---- 4) 예측 = 실적구간 평균 × 그룹 시즌계수 ----
# 산식(월평균×시즌계수)은 형님 확정 그대로. 다만 '평균 구간'이 1~5월로 박혀 있어
# 6·7월 실적이 쌓여도 예측이 계속 1~5월 충격기 바닥을 베이스로 삼던 것을 수정(2026-08-20).
# ⚠️ 시즌계수 분모(과거연도 base)와 2026 베이스는 반드시 같은 구간이어야 정합 —
#    두 곳 모두 ACT_END 를 쓴다. ACT_END=5 면 기존 동작과 정확히 동일.
for b, e in buckets.items():
    grp = GROUP.get(b, 'IR')
    avg_v = sum(e['val'][m] for m in range(1, ACT_END + 1)) / ACT_END
    avg_q = sum(e['qty'][m] for m in range(1, ACT_END + 1)) / ACT_END
    for m in range(FCST_START, 13):
        e['val'][m] = avg_v * season[grp][m]
        e['qty'][m] = avg_q * season[grp][m]

# ---- 5) unified_psi.json 갱신: 채널 fcst + 세그먼트 행 추가 ----
u = json.load(open(f'{DASH}/unified_psi.json'))
ch = u['channels']
for b, e in buckets.items():
    if b not in ch:
        ch[b] = {'group': GROUP.get(b, 'IR'), 'value': {}, 'qty': {},
                 'segment': True}
    node = ch[b]
    node.setdefault('value', {}); node.setdefault('qty', {})
    _ac = ac_acc.get(b, [0.0, 0.0])
    node['ac_asp'] = round(_ac[0] / _ac[1], 0) if _ac[1] else 0   # AC본품 ASP (역산 정합용)
    _cm = cat_acc.get(b, {}); _ct = sum(_cm.values())
    node['cat_mix'] = {c: round(q / _ct, 3) for c, q in sorted(_cm.items(), key=lambda x: -x[1])} if _ct else {}
    for m in range(1, 13):   # 1~5 실적도 기록(세그먼트 누락 버그 수정) / 6 RSM / 7~12 FCST
        mm = f'{m:02d}'
        node['value'].setdefault(mm, {})['st_val'] = round(e['val'][m], 0)
        node['qty'].setdefault(mm, {})['st_qty'] = round(e['qty'][m], 0)
        if m >= FCST_START:
            node['value'][mm]['fcst'] = True
            node['qty'][mm]['fcst'] = True
u['_meta'] = u.get('_meta', {})
_rsm_txt = f' + {RSM_M}월 RSM' if _use_rsm else ''
u['_meta']['fcst_method'] = (
    f'1-{ACT_END}월 실적{_rsm_txt} + {FCST_START}-12월'
    f'(1-{ACT_END}평균×OR/IR 분리 시즌계수, 2024:2025=4:6 가중평균)')
u['_meta']['built'] = __import__('datetime').date.today().isoformat()
# 실적/예측 경계를 '값'으로 심는다 — 하류(H2 코크핏 등)가 문자열을 파싱하거나
# 자체 월 리터럴을 다시 박지 않도록. 경계가 바뀌면 소비자가 자동으로 따라온다.
u['_meta']['period'] = {'act_end': ACT_END, 'rsm_month': RSM_M if _use_rsm else None,
                        'fcst_start': FCST_START}
u['_meta']['season_index'] = {g: {m: round(season[g][m], 3) for m in range(1, 13)} for g in ('OR', 'IR')}
TARGET = {  # 형님 2026-06-17 확정 (OR=+OR_Others, IR=+IR_Others+SME)
    'OR': {'3Q': 70, '4Q': 25, 'H2': 95}, 'IR': {'3Q': 60, '4Q': 35, 'H2': 95}}
u['_meta']['target_2026'] = TARGET

# ---- 거시 회복 시나리오 (형님 2026-06-18: 1~5월은 충격기 — 정상 런레이트로 보정) ----
# 1~5월 = 사우디제이션(1월)+이란미국전 소비위축(4~5월) 충격기. 평균을 베이스로 쓰면 과소추정.
# 정상기(충격월 제외): OR 2~4월 / IR 1~3월 → 회복계수 = 정상런레이트 / 1~5평균.
def _grpv(group, months):
    return sum(buckets[b]['val'][m] for b in buckets
               if GROUP.get(b, 'IR') == group for m in months) / 1e6
NORMAL = {'OR': [2, 3, 4], 'IR': [1, 2, 3]}
recovery, normal_base = {}, {}
for g in ('OR', 'IR'):
    a15 = _grpv(g, [1, 2, 3, 4, 5]) / 5.0
    nb = _grpv(g, NORMAL[g]) / len(NORMAL[g])
    normal_base[g] = round(nb, 1)
    recovery[g] = round(nb / a15, 3) if a15 else 1.0
Qm = {'3Q': [7, 8, 9], '4Q': [10, 11, 12]}
scen = {}
for g in ('OR', 'IR'):
    s1 = {q: _grpv(g, Qm[q]) for q in Qm}; s1['H2'] = s1['3Q'] + s1['4Q']
    s2 = {q: s1[q] * recovery[g] for q in Qm}; s2['H2'] = s2['3Q'] + s2['4Q']
    scen[g] = {'S1': {k: round(v, 1) for k, v in s1.items()},  # 충격 지속(=자연전망)
               'target': TARGET[g],                            # 형님 목표(공식 FCST)
               'S2': {k: round(v, 1) for k, v in s2.items()}}  # 정상 회복
u['_meta']['recovery_factor'] = recovery
u['_meta']['normal_base'] = normal_base
u['_meta']['scenarios'] = scen
u['_meta']['macro_timeline'] = [
    {'m': '1월', 'event': '사우디제이션 본격 시행', 'impact': 'OR −41% (vs 2개년 평균)', 'type': 'shock'},
    {'m': '3~4월', 'event': '이란–미국 군사긴장 고조', 'impact': '소비심리 위축 진입', 'type': 'shock'},
    {'m': '5월', 'event': '전쟁발 소비위축 정점', 'impact': 'IR −69% · OR −48%', 'type': 'shock'},
    {'m': '6월~', 'event': '회복세 진입 (RSM 반등)', 'impact': 'OR +32% · IR +203%', 'type': 'recovery'},
]
json.dump(u, open(f'{DASH}/unified_psi.json', 'w'), ensure_ascii=False, indent=1)

# ---- 6) 리포트 출력 ----
order = ['eXtra', 'Al Manea', 'SWS', 'Black Box', 'Al Khunizan', 'OR_Others',
         'BH', 'BM', 'Tamkeen', 'Zagzoog', 'Dhamin', 'Star Appliance',
         'Al Ghanem', 'Al Shathri', 'IR_Others', 'SME']
print('='*78)
print('시즌계수 (2024·2025 가중평균 4:6, 최근 가중, 1~5월평균=1.0):')
for g in ('OR', 'IR'):
    print(' ', g, {m: round(season[g][m], 2) for m in [6,7,8,9,10,11,12]})
print('='*78)
_lab_act=f'1-{ACT_END}실적'; _lab_rsm=(f'{RSM_M}월RSM' if _use_rsm else '-')
_lab_fc=f'{FCST_START}-12FCST'
print(f"{'bucket':<16}{_lab_act:>9}{_lab_rsm:>8}{_lab_fc:>9}{'연간':>8}  (M SAR)")
tot_or = tot_ir = 0
for b in order:
    if b not in buckets: continue
    e = buckets[b]
    h1a = sum(e['val'][m] for m in range(1, ACT_END + 1))/1e6
    jun = (e['val'][RSM_M]/1e6) if _use_rsm else 0.0
    h2 = sum(e['val'][m] for m in range(FCST_START, 13))/1e6
    yr = h1a+jun+h2
    grp = GROUP.get(b)
    if grp=='OR': tot_or+=yr
    else: tot_ir+=yr
    print(f"{b:<16}{h1a:>9.1f}{jun:>8.1f}{h2:>9.1f}{yr:>8.1f}")
print('-'*78)
print(f"OR계 {tot_or:.1f}  +  IR계 {tot_ir:.1f}  =  연간 전망 {tot_or+tot_ir:.1f} M SAR")
# 분기 목표 vs 자연전망 gap
def grp_val(group, months):
    return sum(ch[b]['value'].get(f'{m:02d}', {}).get('st_val', 0)
               for b, n in ch.items() if n.get('group') == group for m in months) / 1e6
tgt = {('OR','3Q'):70,('IR','3Q'):60,('OR','4Q'):25,('IR','4Q'):35}
Q = {'3Q':[7,8,9],'4Q':[10,11,12]}
print('='*78)
print(f"{'그룹':6}{'3Q자연':>8}{'3Q목표':>8}{'gap':>7} |{'4Q자연':>8}{'4Q목표':>8}{'gap':>7} |{'H2 gap':>8}")
TOT = 0
for g in ('OR','IR'):
    f3, f4 = grp_val(g, Q['3Q']), grp_val(g, Q['4Q'])
    g3, g4 = tgt[(g,'3Q')]-f3, tgt[(g,'4Q')]-f4
    TOT += g3+g4
    print(f"{g:6}{f3:>8.1f}{tgt[(g,'3Q')]:>8}{g3:>+7.1f} |{f4:>8.1f}{tgt[(g,'4Q')]:>8}{g4:>+7.1f} |{g3+g4:>+8.1f}")
print('-'*78)
print(f"하반기 총 gap = {TOT:+.1f} M SAR (이만큼을 채널별 Action Plan으로 메워야 함)")
