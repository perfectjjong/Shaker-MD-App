#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unified_psi.json에 7~12월 FCST(금액·수량 이중축)를 산출해 추가한다.
방법론(2026-06-17 형님 확정):
  - 1~5월 = data.json txn 실적 (권위)
  - 6월   = rsm_fcst embed (account별 RSM FCST)
  - 7~12월 = bucket 1~5월 평균 × 그룹(OR/IR) 시즌계수
            시즌계수(m) = 2025 그룹 m월 / 2025 그룹 1~5월 평균  (OR/IR 분리 곡선)
  - 이중축: value(st_val) / qty(st_qty) 각각 동일 로직.
16 bucket = 13채널 + OR_Others + IR_Others + SME.
"""
import json, sys
sys.path.insert(0, '/home/ubuntu/2026/10. Automation')
import shared_classification as sc

DASH = '/home/ubuntu/Shaker-MD-App/docs/dashboards/sell-thru-progress'
d = json.load(open(f'{DASH}/data.json'))
txn, rsm, master = d['txn'], d['rsm_fcst'], d['master']
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

# ---- 1) 그룹 시즌계수 = 2024·2025 평균 (형님 2026-06-17: 2024 트렌드까지 반영) ----
# 2025 단년은 하반기(특히 4Q)가 유난히 약했음 → 2개년 평균으로 편향 제거.
SEASON_YEARS = (2024, 2025)
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
    accum = {m: [] for m in range(1, 13)}
    for y in SEASON_YEARS:
        base = sum(gyr[y][grp][1:6]) / 5.0   # 해당 연도 1~5월 평균
        if base <= 0:
            continue
        for m in range(1, 13):
            accum[m].append(gyr[y][grp][m] / base)
    season[grp] = {m: (sum(accum[m]) / len(accum[m]) if accum[m] else 0) for m in range(1, 13)}

# ---- 2) bucket별 1~5월 실적 (value, qty) ----
buckets = {}
def ensure(b):
    if b not in buckets:
        buckets[b] = {'val': {m: 0.0 for m in range(1, 13)}, 'qty': {m: 0.0 for m in range(1, 13)}}
    return buckets[b]
for t in txn:
    if t[0] != 2026 or not (1 <= int(t[1]) <= 5):
        continue
    b = to_bucket(t[3], t[5])
    if not b:
        continue
    e = ensure(b); e['val'][int(t[1])] += (t[8] or 0); e['qty'][int(t[1])] += (t[9] or 0)

# 13채널 0행 보장 (Zagzoog 등 ST=0 채널도 표시)
for b in ('eXtra','Al Manea','SWS','Black Box','Al Khunizan','BH','BM','Tamkeen',
          'Zagzoog','Dhamin','Star Appliance','Al Ghanem','Al Shathri'):
    ensure(b)

# 검증: bucket 1~5월 합 = txn 2026 1~5월 OR/IR 그룹 합
_chk = {'OR':0.0,'IR':0.0}
for b,e in buckets.items():
    _chk[GROUP.get(b,'IR')] += sum(e['val'][m] for m in range(1,6))
print(f"[검증] 1~5월 OR={_chk['OR']/1e6:.1f}M (기대 102.2)  IR={_chk['IR']/1e6:.1f}M (기대 77.9)")

# ---- 3) 6월 = RSM FCST (account별) ----
for aid, v in rsm['value'].items():
    b = to_bucket(aid, master_team.get(int(float(aid)), ''))
    if b:
        ensure(b)['val'][6] += v
for aid, q in rsm['qty'].items():
    b = to_bucket(aid, master_team.get(int(float(aid)), ''))
    if b:
        ensure(b)['qty'][6] += q

# ---- 4) 7~12월 FCST = 1~5월 평균 × 그룹 시즌계수 ----
for b, e in buckets.items():
    grp = GROUP.get(b, 'IR')
    avg_v = sum(e['val'][m] for m in range(1, 6)) / 5.0
    avg_q = sum(e['qty'][m] for m in range(1, 6)) / 5.0
    for m in range(7, 13):
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
    for m in range(1, 13):   # 1~5 실적도 기록(세그먼트 누락 버그 수정) / 6 RSM / 7~12 FCST
        mm = f'{m:02d}'
        node['value'].setdefault(mm, {})['st_val'] = round(e['val'][m], 0)
        node['qty'].setdefault(mm, {})['st_qty'] = round(e['qty'][m], 0)
        if m >= 7:
            node['value'][mm]['fcst'] = True
            node['qty'][mm]['fcst'] = True
u['_meta'] = u.get('_meta', {})
u['_meta']['fcst_method'] = '1-5월 실적 + 6월 RSM + 7-12월(1-5평균×OR/IR 분리 시즌계수, 2024·2025 2개년평균). 2026-06-17'
u['_meta']['season_index'] = {g: {m: round(season[g][m], 3) for m in range(1, 13)} for g in ('OR', 'IR')}
u['_meta']['target_2026'] = {  # 형님 2026-06-17 확정 (OR=+OR_Others, IR=+IR_Others+SME)
    'OR': {'3Q': 70, '4Q': 25, 'H2': 95}, 'IR': {'3Q': 60, '4Q': 35, 'H2': 95}}
json.dump(u, open(f'{DASH}/unified_psi.json', 'w'), ensure_ascii=False, indent=1)

# ---- 6) 리포트 출력 ----
order = ['eXtra', 'Al Manea', 'SWS', 'Black Box', 'Al Khunizan', 'OR_Others',
         'BH', 'BM', 'Tamkeen', 'Zagzoog', 'Dhamin', 'Star Appliance',
         'Al Ghanem', 'Al Shathri', 'IR_Others', 'SME']
print('='*78)
print('시즌계수 (2024·2025 2개년 평균, 1~5월평균=1.0):')
for g in ('OR', 'IR'):
    print(' ', g, {m: round(season[g][m], 2) for m in [6,7,8,9,10,11,12]})
print('='*78)
print(f"{'bucket':<16}{'1-5실적':>9}{'6월RSM':>8}{'7-12FCST':>9}{'연간':>8}  (M SAR)")
tot_or = tot_ir = 0
for b in order:
    if b not in buckets: continue
    e = buckets[b]
    h1a = sum(e['val'][m] for m in range(1,6))/1e6
    jun = e['val'][6]/1e6
    h2 = sum(e['val'][m] for m in range(7,13))/1e6
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
