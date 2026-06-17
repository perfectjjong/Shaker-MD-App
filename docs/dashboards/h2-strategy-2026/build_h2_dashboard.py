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
    rows.append({
        'name': c, 'ko': KO.get(c, c), 'group': g, 'seg': seg,
        'mval': [round(x, 0) for x in mval], 'mqty': [round(x, 0) for x in mqty],
        'fcst': fcst, 'h1': round(h1, 1), 'jun': round(jun, 1),
        'q3': round(q3, 1), 'q4': round(q4, 1), 'annual': round(annual, 1),
        'ar': round(ar / 1e6, 1), 'ovd': round(ovd / 1e6, 1),
        'stk': stk, 'mos': round(mos, 1) if mos else None,
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
  </div>

  <div class="panel active" id="overview"></div>
  <div class="panel" id="psi"></div>
  <div class="panel" id="dual"></div>
  <div class="panel" id="plan"></div>

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
  const s=D.summary, el=document.getElementById('overview');
  el.innerHTML = `
    <div class="grid kpis">
      <div class="card"><div class="lbl">연간 전망 (16 bucket)</div><div class="val">${D.tot_annual}M</div><div class="note" style="color:var(--mut)">목표 400M 권 · SAR</div></div>
      <div class="card"><div class="lbl">OR 하반기 (3Q+4Q)</div><div class="val">${s.OR.h2}<span style="font-size:15px;color:var(--mut)"> / ${s.OR.th2}M</span></div><div class="note">Gap ${gapChip(s.OR.gaph2)}</div></div>
      <div class="card"><div class="lbl">IR 하반기 (3Q+4Q)</div><div class="val">${s.IR.h2}<span style="font-size:15px;color:var(--mut)"> / ${s.IR.th2}M</span></div><div class="note">Gap ${gapChip(s.IR.gaph2)}</div></div>
      <div class="card" style="border-color:var(--warn)"><div class="lbl">하반기 총 Gap</div><div class="val pos">+${D.tot_gap}M</div><div class="note" style="color:var(--mut)">Action Plan으로 메울 양</div></div>
    </div>

    <div class="chartbox" style="margin-top:18px">
      <h3>분기 목표 vs 자연전망 <span class="axis-tag ax-val">금액축 · M SAR</span></h3>
      <table>
        <tr><th class="l">그룹 · 분기</th><th>자연전망</th><th>목표</th><th>Gap</th><th class="l">해석</th></tr>
        ${[['OR','3Q','t3','q3','gap3'],['OR','4Q','t4','q4','gap4'],['IR','3Q','t3','q3','gap3'],['IR','4Q','t4','q4','gap4']].map(([g,q,tk,vk,gk])=>`
          <tr class="${g.toLowerCase()}-row"><td class="l">${g} ${q}</td><td>${f1(s[g][vk])}</td><td>${s[g][tk]}</td><td>${gapChip(s[g][gk])}</td>
          <td class="l" style="color:var(--mut);font-size:12px">${s[g][gk]>0.05?'추가 푸시 필요':(s[g][gk]<-0.05?'이미 초과 — 여유':'목표권 도달')}</td></tr>`).join('')}
      </table>
    </div>

    <div class="chartbox"><h3>그룹 분기 자연전망 vs 목표</h3><canvas id="cQuarter"></canvas></div>
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
    <div class="chartbox" style="margin-top:14px"><h3>핵심 리스크 / 레버 (참모 의견)</h3>
      <ul style="margin-left:18px;line-height:1.9;font-size:14px">
        <li><b style="color:#f87171">BH 이중 리스크</b> — OVD ${D.rows.find(r=>r.name==='BH').ovd}M(AR의 절반) + 재고 MOS ${f1(D.rows.find(r=>r.name==='BH').mos)}개월. 하반기 최대 IR 채널이나, 금액축(채권)·수량축(재고) 동시 경고 → 밀어내기보다 <b>회수·소진 정상화</b> 선행.</li>
        <li><b style="color:#93c5fd">eXtra 구조적 의존</b> — 연간 ${D.rows.find(r=>r.name==='eXtra').annual}M(전체의 ~33%), OVD ${D.rows.find(r=>r.name==='eXtra').ovd}M로 채권 건전. OR 3Q gap의 대부분을 eXtra 8~9월 입고·프로모로 메우는 것이 현실적.</li>
        <li><b style="color:#fbbf24">전제 리스크</b> — 본 전망은 "2024 수준 하반기 회복" 가정. 2025식 연말 부진(IR 11~12월 계수 0.69/0.51)이 재연되면 Gap이 30M+로 재확대 → 월별 실적 모니터링 필수.</li>
      </ul>
    </div>`;
}

// ---------- 탭 전환 (숨겨진 탭 차트 재렌더 — 0x0 버그 방지) ----------
const renderers={overview:renderOverview,psi:renderPSI,dual:renderDual,plan:renderPlan};
function activate(p){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.p===p));
  document.querySelectorAll('.panel').forEach(x=>x.classList.toggle('active',x.id===p));
  renderers[p]();
}
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>activate(t.dataset.p)));

document.getElementById('subline').textContent='목표(2026-06-17 형님 확정): OR(+OR기타) 3Q70·4Q25·H2 95M / IR(+IR기타+SME) 3Q60·4Q35·H2 95M · 단위 M SAR';
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
