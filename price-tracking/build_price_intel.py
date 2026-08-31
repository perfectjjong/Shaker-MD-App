#!/usr/bin/env python3
"""
Price Intelligence 대시보드 빌더 — 검증된 경영 질문 카드.

price_data.db → docs/dashboards/price-intel/index.html
자유 질의가 아니라 고정 질문 세트만 렌더한다. 새 질문은 카드로 추가한다.

사용:
  python3 build_price_intel.py            # 대시보드 생성
  python3 build_price_intel.py --telegram # 생성 + 주간 요약 텔레그램 발송
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from price_intel_data import build_all  # noqa: E402

OUT = Path("/home/ubuntu/Shaker-MD-App/docs/dashboards/price-intel/index.html")

# 에디토리얼 팔레트 정본 [[project_editorial_theme_unification]]
PAL = {
    "paper": "#f7f3ea", "card": "#fffdf8", "panel": "#efe9db", "border": "#ddd4c2",
    "ink": "#191714", "sub": "#453f35", "muted": "#6b6355", "light": "#9a927f",
    "claret": "#8c1d2f", "claret_lt": "#a54b5e", "claret_dp": "#6d1522",
    "gold": "#a8863c", "gold_dp": "#8a6d2e",
    "green": "#1d6b45", "red": "#b3261e",
    "teal": "#2a7a6e", "plum": "#6d4b78", "rose": "#a5386b", "slate": "#33606d",
}
# 브랜드 색 — extra-ms 재배정 맵과 동일 계열 유지
BRAND_COLOR = {
    "LG": PAL["claret"], "GREE": "#5f7a2a", "MIDEA": "#b06a24",
    "SAMSUNG": PAL["slate"], "HISENSE": PAL["teal"], "TCL": "#7a4a8a",
}


def _n(v, suffix=""):
    """결손은 '—'. 거짓 0을 만들지 않는다."""
    return "—" if v is None else f"{v:,.0f}{suffix}"


def _pct(v):
    if v is None:
        return '<span class="mut">—</span>'
    cls = "up" if v > 0 else ("dn" if v < 0 else "")
    return f'<span class="{cls}">{v:+.1f}%</span>'


def render(d: dict) -> str:
    f = d["freshness"]
    g = d["gap_trend"]
    cp = d["channel_position"]
    rm = d["recent_moves"]
    bt = d["brand_trend"]
    lu = d["lineup"]
    pb = d["premium_band"]
    ms = d["model_spread"]
    mc = d["model_coverage"]

    # ── KPI ────────────────────────────────────────────────
    cur_gap = g["series"][-1]["gap_pct"] if g else None
    base_gap = g["series"][0]["gap_pct"] if g else None
    gap_delta = round(cur_gap - base_gap, 1) if (cur_gap is not None and base_gap is not None) else None
    lg_chg = comp_chg = None
    if g:
        a, b = g["series"][0], g["series"][-1]
        if a["lg"] and b["lg"]:
            lg_chg = round((b["lg"] - a["lg"]) / a["lg"] * 100, 1)
        if a["comp"] and b["comp"]:
            comp_chg = round((b["comp"] - a["comp"]) / a["comp"] * 100, 1)

    stale_banner = ""
    if f["stale_count"]:
        bad = [f'{x["name"]}({x["lag_days"]}일)' for x in f["channels"] if x["stale"]]
        stale_banner = (
            f'<div class="warn">⚠️ 수집 지연 {f["stale_count"]}개 채널: {", ".join(bad)} '
            f'— 해당 채널 수치는 과거 시점입니다.</div>')

    # ── 카드3 표 ───────────────────────────────────────────
    def moves_rows(items):
        if not items:
            return '<tr><td colspan="6" class="mut">해당 기간 변동 없음</td></tr>'
        out = []
        for m in items[:15]:
            tag = '<span class="lgtag">LG</span> ' if m["is_lg"] else ""
            out.append(
                f'<tr><td>{m["date"]}</td><td>{m["channel"]}</td>'
                f'<td>{tag}{m["brand"]}</td>'
                f'<td class="nm">{m["name"]}<span class="mut"> · {m["sku"]}</span></td>'
                f'<td class="r">{_n(m["prev"])} → <b>{_n(m["curr"])}</b></td>'
                f'<td class="r">{_pct(m["chg_pct"])}</td></tr>')
        return "".join(out)

    ch_rows = "".join(
        f'<tr class="{"thin" if r["thin"] else ""}"><td>{r["channel"]}'
        f'{" <span class=\"mut\">(표본 %d)</span>" % r["lg_n"] if r["thin"] else ""}</td>'
        f'<td class="r">{_n(r["lg"])}</td><td class="r">{_n(r["comp"])}</td>'
        f'<td class="r">{_pct(r["gap_pct"])}</td><td class="r mut">{r["lg_n"]}</td></tr>'
        for r in cp["rows"])

    pb_rows = "".join(
        f'<tr><td>{r["band"]}</td><td class="r">{_n(r["lg"])}</td>'
        f'<td class="r">{_n(r["comp"])}</td><td class="r">{_pct(r["gap_pct"])}</td>'
        f'<td class="r mut">{r["lg_n"]} / {r["comp_n"]}</td></tr>'
        for r in pb)

    fresh_rows = "".join(
        f'<tr class="{"thin" if r["stale"] else ""}"><td>{r["name"]}</td>'
        f'<td>{r["last_date"]}</td><td class="r">{r["lag_days"]}일</td>'
        f'<td class="r">{r["skus"]:,}</td><td class="r mut">{r["snaps"]:,}</td></tr>'
        for r in f["channels"])

    def lineup_rows(items, empty):
        if not items:
            return f'<tr><td colspan="4" class="mut">{empty}</td></tr>'
        return "".join(
            f'<tr><td>{i["date"]}</td><td>{i["channel"]}</td>'
            f'<td>{"<span class=\"lgtag\">LG</span> " if i["is_lg"] else ""}{i["brand"]}</td>'
            f'<td class="nm">{i["name"] or "<span class=\'mut\'>(제품명 미수집)</span>"}</td></tr>'
            for i in items[:12])

    ms_rows = "".join(
        f'<tr><td><b>{r["model"]}</b></td>'
        f'<td class="r mut">{_n(r["btu"])}</td>'
        f'<td class="r">{r["n_ch"]}</td>'
        f'<td class="r"><b>{r["lo"]:,}</b> <span class="mut">{r["lo_ch"]}</span></td>'
        f'<td class="r"><b>{r["hi"]:,}</b> <span class="mut">{r["hi_ch"]}</span></td>'
        f'<td class="r"><span class="up">{r["spread_pct"]:+.1f}%</span></td></tr>'
        for r in ms["rows"]) or '<tr><td colspan="6" class="mut">비교 가능한 모델 없음</td></tr>'

    mc_rows = "".join(
        f'<tr class="{"thin" if r["pct"] < 90 else ""}"><td>{r["channel"]}</td>'
        f'<td class="r">{r["hit"]} / {r["tot"]}</td>'
        f'<td class="r">{r["pct"]:.0f}%</td></tr>' for r in mc["rows"])

    balance_note = ""
    if g and not g["balanced"]:
        balance_note = ('<span class="mut"> · 월별 표본이 일부 변동(일시 품절 등) — '
                        '완전 균형패널은 아님</span>')
    dropped = ", ".join(f'{x["month"]}({x["days"]}일)' for x in g["dropped_months"]) if g else ""

    payload = json.dumps({
        "gap": g, "brand": bt, "pal": PAL, "bcolor": BRAND_COLOR}, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Price Intelligence — 경쟁 가격 인텔리전스</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{PAL['paper']};color:{PAL['ink']};
 font-family:Inter,-apple-system,'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.5}}
.wrap{{max-width:1240px;margin:0 auto;padding:26px 20px 60px}}
header{{border-bottom:2px solid {PAL['claret']};padding-bottom:14px;margin-bottom:20px}}
h1{{margin:0;font-size:23px;font-weight:700;letter-spacing:-.3px}}
.sub{{color:{PAL['muted']};font-size:12px;margin-top:5px}}
.warn{{background:#fbeceb;border-left:4px solid {PAL['red']};padding:9px 13px;
 border-radius:5px;font-size:12.5px;margin-bottom:16px;color:{PAL['claret_dp']}}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:24px}}
.kpi{{background:{PAL['card']};border:1px solid {PAL['border']};border-radius:9px;padding:13px 15px}}
.kpi .k{{font-size:10.5px;color:{PAL['muted']};text-transform:uppercase;letter-spacing:.5px;font-weight:600}}
.kpi .v{{font-size:25px;font-weight:700;margin-top:5px;letter-spacing:-.5px}}
.kpi .d{{font-size:11.5px;color:{PAL['muted']};margin-top:3px}}
.card{{background:{PAL['card']};border:1px solid {PAL['border']};border-radius:10px;
 padding:18px 20px;margin-bottom:18px}}
.q{{font-size:15.5px;font-weight:700;color:{PAL['claret_dp']};margin:0 0 3px}}
.q .num{{display:inline-block;background:{PAL['claret']};color:#fff;border-radius:5px;
 padding:1px 7px;font-size:11px;margin-right:8px;vertical-align:2px}}
.hint{{font-size:11.5px;color:{PAL['muted']};margin-bottom:13px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
@media(max-width:860px){{.grid2{{grid-template-columns:1fr}}}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{background:{PAL['claret_dp']};color:#fff;padding:7px 9px;text-align:left;
 font-weight:600;font-size:11px;white-space:nowrap}}
td{{padding:6px 9px;border-bottom:1px solid {PAL['panel']};white-space:nowrap}}
tr:nth-child(even) td{{background:#f9f5ec}}
td.r,th.r{{text-align:right}}
td.nm{{white-space:normal;max-width:330px;color:{PAL['sub']};font-size:11.5px}}
.mut{{color:{PAL['light']}}}
.up{{color:{PAL['red']};font-weight:600}}
.dn{{color:{PAL['green']};font-weight:600}}
tr.thin td{{opacity:.55;font-style:italic}}
.lgtag{{background:{PAL['claret']};color:#fff;border-radius:3px;padding:0 5px;
 font-size:9.5px;font-weight:700}}
.take{{background:{PAL['panel']};border-left:4px solid {PAL['gold']};padding:10px 13px;
 border-radius:5px;font-size:12.5px;margin-top:13px;color:{PAL['sub']}}}
.take b{{color:{PAL['claret_dp']}}}
canvas{{max-height:270px}}
footer{{margin-top:34px;padding-top:14px;border-top:1px solid {PAL['border']};
 font-size:11px;color:{PAL['light']}}}
</style></head><body><div class="wrap">

<header>
  <h1>Price Intelligence</h1>
  <div class="sub">경쟁 가격 인텔리전스 · 기준일 <b>{f['anchor']}</b> ·
   11채널 {sum(x['skus'] for x in f['channels']):,} SKU ·
   가격기록 {sum(x['snaps'] for x in f['channels']):,}건 ·
   생성 {datetime.now():%Y-%m-%d %H:%M}</div>
</header>
{stale_banner}

<div class="kpis">
  <div class="kpi"><div class="k">현재 LG 프리미엄 ({g['band'] if g else '—'})</div>
    <div class="v">{f'{cur_gap:+.1f}%' if cur_gap is not None else '—'}</div>
    <div class="d">경쟁사 평균 대비</div></div>
  <div class="kpi"><div class="k">프리미엄 변화 ({g['base_month'] if g else '—'}→현재)</div>
    <div class="v">{f'{gap_delta:+.1f}%p' if gap_delta is not None else '—'}</div>
    <div class="d">동일 SKU {g['sku_count'] if g else 0}개 기준</div></div>
  <div class="kpi"><div class="k">우리 가격 변화</div>
    <div class="v">{f'{lg_chg:+.1f}%' if lg_chg is not None else '—'}</div>
    <div class="d">경쟁사 {f'{comp_chg:+.1f}%' if comp_chg is not None else '—'}</div></div>
  <div class="kpi"><div class="k">채널 간 LG 가격 편차</div>
    <div class="v">{f"{cp['spread']['pct']:.1f}%" if cp['spread'] else '—'}</div>
    <div class="d">{f"{cp['spread']['lo']:,} ~ {cp['spread']['hi']:,} SAR" if cp['spread'] else '—'}</div></div>
</div>

<div class="card">
  <div class="q"><span class="num">Q1</span>우리 프리미엄은 어디로 가고 있나?</div>
  <div class="hint">{g['band'] if g else ''} 급 · <b>{g['base_month'] if g else ''}~{f['anchor'][:7]}</b> ·
   기간 내내 살아있는 동일 SKU {g['sku_count'] if g else 0}개만 비교해 신제품 출시·단종에 따른 착시를 제거했습니다.
   {f'수집 부실월 제외: {dropped}' if dropped else ''}{balance_note}</div>
  <canvas id="c1"></canvas>
  <div class="take">{_takeaway_gap(g, lg_chg, comp_chg, gap_delta)}</div>
</div>

<div class="grid2">
  <div class="card">
    <div class="q"><span class="num">Q2</span>어느 용량에서 가장 비싼가?</div>
    <div class="hint">최근 30일 평균 · 표본 3 SKU 미만은 산출하지 않습니다(—)</div>
    <table><tr><th>용량</th><th class="r">LG</th><th class="r">경쟁</th>
      <th class="r">프리미엄</th><th class="r">SKU LG/경쟁</th></tr>{pb_rows}</table>
  </div>
  <div class="card">
    <div class="q"><span class="num">Q3</span>채널마다 우리 가격이 다른가?</div>
    <div class="hint">{cp['band']} 급 · 최근 {cp['days']}일 평균 · 흐린 행은 표본 3 SKU 미만</div>
    <table><tr><th>채널</th><th class="r">LG</th><th class="r">경쟁</th>
      <th class="r">프리미엄</th><th class="r">SKU</th></tr>{ch_rows}</table>
    {_takeaway_channel(cp)}
  </div>
</div>

<div class="card">
  <div class="q"><span class="num">Q4</span>지난 {rm['days']}일, 누가 가격을 움직였나?</div>
  <div class="hint">기준일 {rm['anchor']} 직전 {rm['days']}일 · 변동폭 큰 순 · 상위 15건{_excl_note(rm)}</div>
  <div class="grid2">
    <div><table><tr><th colspan="6" style="background:{PAL['red']}">▲ 인상</th></tr>
      <tr><th>일자</th><th>채널</th><th>브랜드</th><th>제품</th><th class="r">가격</th><th class="r">변동</th></tr>
      {moves_rows(rm['up'])}</table></div>
    <div><table><tr><th colspan="6" style="background:{PAL['green']}">▼ 인하</th></tr>
      <tr><th>일자</th><th>채널</th><th>브랜드</th><th>제품</th><th class="r">가격</th><th class="r">변동</th></tr>
      {moves_rows(rm['down'])}</table></div>
  </div>
</div>

<div class="card">
  <div class="q"><span class="num">Q5</span>브랜드별로 어떻게 움직였나?</div>
  <div class="hint">{bt['band']} 급 월평균 · Q1과 동일한 월 집합(수집 부실월 제외) ·
   표본 2 SKU 미만인 달은 끊어서 표시</div>
  <canvas id="c2"></canvas>
</div>

<div class="card">
  <div class="q"><span class="num">Q7</span>같은 모델인데 채널마다 얼마나 다른가?</div>
  <div class="hint">
    LG 모델코드(v6 정본)를 붙여 채널 간 <b>동일 모델</b>을 비교합니다 —
    제품명은 채널마다 달라서(오타·아랍어 포함) 이름으로는 짝지을 수 없습니다.
    최근 {ms['days']}일 · <b>채널별 평균을 먼저 낸 뒤</b> 그들끼리 비교(프로모션 등락이
    채널 편차로 둔갑하지 않게) · 3채널 이상 · 관측 {ms['min_obs_days']}일 미만 채널 제외 ·
    비교 가능 {ms['total']}종 중 편차 상위 {len(ms['rows'])}종
  </div>
  <div class="grid2">
    <div>
      <table><tr><th>모델</th><th class="r">BTU</th><th class="r">채널</th>
        <th class="r">최저</th><th class="r">최고</th><th class="r">편차</th></tr>{ms_rows}</table>
    </div>
    <div>
      <div class="hint" style="margin-bottom:8px"><b>이 표를 믿어도 되나</b> — 모델코드 부착률
       (원본에 코드가 없으면 붙이지 않습니다. 추측하지 않음)</div>
      <table><tr><th>채널</th><th class="r">LG 부착/전체</th><th class="r">부착률</th></tr>
        {mc_rows}
        <tr><td><b>합계</b></td><td class="r"><b>{mc['hit']} / {mc['tot']}</b></td>
          <td class="r"><b>{mc['pct']:.0f}%</b></td></tr></table>
    </div>
  </div>
  {_takeaway_model(ms)}
</div>

<div class="card">
  <div class="q"><span class="num">Q6</span>경쟁사가 라인업을 바꿨나?</div>
  <div class="hint">최근 {lu['days']}일 · 신규 {lu['new_total']}건 / 단종 {lu['gone_total']}건 · 각 상위 12건</div>
  <div class="grid2">
    <div><table><tr><th colspan="4" style="background:{PAL['teal']}">신규 진입</th></tr>
      <tr><th>일자</th><th>채널</th><th>브랜드</th><th>제품</th></tr>
      {lineup_rows(lu['new'], '신규 없음')}</table></div>
    <div><table><tr><th colspan="4" style="background:{PAL['gold_dp']}">단종·이탈</th></tr>
      <tr><th>일자</th><th>채널</th><th>브랜드</th><th>제품</th></tr>
      {lineup_rows(lu['gone'], '단종 없음')}</table></div>
  </div>
</div>

<div class="card">
  <div class="q"><span class="num">Q0</span>이 숫자를 믿어도 되나? — 데이터 신선도</div>
  <div class="hint">모든 카드는 이 수집 상태 위에 계산됩니다. 지연 채널은 과거 시점 값입니다.</div>
  <table><tr><th>채널</th><th>최종 수집일</th><th class="r">지연</th>
    <th class="r">SKU</th><th class="r">누적 기록</th></tr>{fresh_rows}</table>
</div>

<footer>
  소스: <code>2026/06. Price Tracking/price_data.db</code> ·
  빌더: <code>price-tracking/build_price_intel.py</code> ·
  가격 기준 = 프로모가(sl), 결측 시 표준가(sp) 폴백 ·
  브랜드는 대소문자 통일 후 집계 · 결손은 0이 아닌 “—”로 표기
</footer>
</div>
<script>
const D = {payload};
const P = D.pal, F = {{family:'Inter'}};
Chart.defaults.font.family='Inter';
Chart.defaults.color=P.muted;

if (D.gap) {{
  const g=D.gap, L=g.series.map(s=>s.month);
  new Chart(document.getElementById('c1'),{{
    data:{{labels:L,datasets:[
      {{type:'line',label:'LG 평균가',data:g.series.map(s=>s.lg),borderColor:P.claret,
        backgroundColor:P.claret,tension:.3,yAxisID:'y',borderWidth:2.5,pointRadius:3}},
      {{type:'line',label:'경쟁사 평균가',data:g.series.map(s=>s.comp),borderColor:P.slate,
        backgroundColor:P.slate,tension:.3,yAxisID:'y',borderWidth:2.5,pointRadius:3}},
      {{type:'bar',label:'프리미엄 %',data:g.series.map(s=>s.gap_pct),
        backgroundColor:'rgba(168,134,60,.32)',borderColor:P.gold,borderWidth:1,yAxisID:'y1'}}
    ]}},
    options:{{responsive:true,animation:false,interaction:{{mode:'index',intersect:false}},
      scales:{{
        y:{{position:'left',title:{{display:true,text:'SAR'}},grid:{{color:'#e8e0d0'}}}},
        y1:{{position:'right',title:{{display:true,text:'프리미엄 %'}},grid:{{display:false}},
          ticks:{{callback:v=>v+'%'}}}}
      }},
      plugins:{{legend:{{labels:{{boxWidth:12,padding:14}}}},
        tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+
          (c.dataset.yAxisID==='y1'? c.parsed.y+'%' : c.parsed.y.toLocaleString()+' SAR')}}}}
      }}}}
  }});
}}

if (D.brand) {{
  const b=D.brand;
  new Chart(document.getElementById('c2'),{{
    type:'line',
    data:{{labels:b.months,datasets:Object.entries(b.brands).map(([k,v])=>({{
      label:k,data:v,borderColor:D.bcolor[k]||P.muted,backgroundColor:D.bcolor[k]||P.muted,
      tension:.3,borderWidth:k==='LG'?3:1.8,pointRadius:k==='LG'?3.5:2.5,spanGaps:false
    }}))}},
    options:{{responsive:true,animation:false,interaction:{{mode:'index',intersect:false}},
      scales:{{y:{{title:{{display:true,text:'SAR'}},grid:{{color:'#e8e0d0'}}}}}},
      plugins:{{legend:{{labels:{{boxWidth:12,padding:12}}}},
        tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+
          (c.parsed.y==null?'데이터 없음':c.parsed.y.toLocaleString()+' SAR')}}}}}}}}
  }});
}}
</script></body></html>"""


def _excl_note(rm):
    """제외 건수를 화면에 남긴다 — 조용히 버리면 감시할 수 없다."""
    if not rm.get("excluded"):
        return ""
    return (f' · <b style="color:{PAL["gold_dp"]}">수집 결함 {rm["excluded"]}건 제외</b>'
            f'<span class="mut">(하루 튀었다 원위치한 값 = 프로모가 미포착일. '
            f'실제 변동이 아니라 순위만 왜곡함. '
            f'⚠️ 기준일 당일에 발생한 결함은 되돌아옴을 아직 관측 못 해 걸러지지 않을 수 있음)</span>')


def _takeaway_gap(g, lg_chg, comp_chg, gap_delta):
    if not g or lg_chg is None or comp_chg is None:
        return "비교 가능한 기간이 부족합니다."
    a, b = g["series"][0], g["series"][-1]
    if comp_chg > lg_chg:
        driver = (f"격차가 줄어든 것은 우리가 내려서가 아니라 <b>경쟁사가 더 올렸기</b> 때문입니다 "
                  f"(경쟁 {comp_chg:+.1f}% vs LG {lg_chg:+.1f}%).")
        action = ("상대적 가격 위치가 개선된 구간입니다 — 이 여지를 "
                  "<b>볼륨 확보</b>에 쓸지 <b>가격 인상으로 마진 회복</b>에 쓸지 판단이 필요합니다.")
    elif comp_chg < lg_chg:
        driver = (f"격차가 벌어진 것은 <b>우리가 더 올렸기</b> 때문입니다 "
                  f"(LG {lg_chg:+.1f}% vs 경쟁 {comp_chg:+.1f}%).")
        action = "프리미엄 확대가 의도된 것인지, 볼륨 손실로 이어지는지 셀아웃과 대조가 필요합니다."
    else:
        driver = "양측이 같은 폭으로 움직였습니다."
        action = "상대 위치 변화 없음 — 별도 조치 불요."
    return (f"{a['month']} → {b['month']} 프리미엄 <b>{a['gap_pct']:+.1f}% → {b['gap_pct']:+.1f}%"
            f"({gap_delta:+.1f}%p)</b>. {driver} {action}")


def _takeaway_model(ms):
    if not ms["rows"]:
        return ""
    t = ms["rows"][0]
    return (f'<div class="take">동일 모델 <b>{t["model"]}</b>({_n(t["btu"])} BTU)이 '
            f'<b>{t["lo_ch"]} {t["lo"]:,} SAR</b> vs <b>{t["hi_ch"]} {t["hi"]:,} SAR</b>로 '
            f'<b>{t["spread_pct"]:.1f}% 차이</b>가 납니다. '
            f'Q3의 채널 편차는 상품 구성이 달라서일 수도 있지만, <b>여기는 완전히 같은 모델</b>이라 '
            f'변명의 여지가 없습니다 — 저가 채널 가격이 온라인으로 노출되면 '
            f'고가 채널 딜러의 판매 저항과 가격 보상 요구로 직결됩니다. '
            f'비교 가능 {ms["total"]}종 중 편차 20% 이상이 '
            f'{sum(1 for r in ms["rows"] if r["spread_pct"] >= 20)}종.</div>')


def _takeaway_channel(cp):
    solid = [r for r in cp["rows"] if not r["thin"]]
    if len(solid) < 2 or not cp["spread"]:
        return ""
    lo = min(solid, key=lambda r: r["gap_pct"])
    hi = max(solid, key=lambda r: r["gap_pct"])
    return (f'<div class="take">같은 {cp["band"]} 급인데 채널 간 LG 가격이 '
            f'<b>{cp["spread"]["lo"]:,} ~ {cp["spread"]["hi"]:,} SAR ({cp["spread"]["pct"]:.1f}% 차이)</b>로 '
            f'벌어져 있습니다. 프리미엄이 가장 낮은 곳은 <b>{lo["channel"]} ({lo["gap_pct"]:+.1f}%)</b>, '
            f'가장 높은 곳은 <b>{hi["channel"]} ({hi["gap_pct"]:+.1f}%)</b>. '
            f'저가 채널이 시장가를 끌어내리면 타 채널 딜러 항의로 이어집니다 — 채널 가격 정책 점검 대상.</div>')


def telegram_summary(d) -> str:
    f, g, cp, rm = d["freshness"], d["gap_trend"], d["channel_position"], d["recent_moves"]
    L = [f"💰 *경쟁 가격 인텔리전스* ({f['anchor']})", ""]
    if g:
        a, b = g["series"][0], g["series"][-1]
        L.append(f"*LG 프리미엄* ({g['band']}): {a['gap_pct']:+.1f}% → *{b['gap_pct']:+.1f}%*")
        L.append(f"  LG {a['lg']:,}→{b['lg']:,} / 경쟁 {a['comp']:,}→{b['comp']:,} SAR")
        L.append(f"  (동일 SKU {g['sku_count']}개, {a['month']}~{b['month']})")
        L.append("")
    if cp["spread"]:
        L.append(f"*채널 편차*: {cp['spread']['lo']:,}~{cp['spread']['hi']:,} SAR "
                 f"({cp['spread']['pct']:.1f}%)")
        solid = [r for r in cp["rows"] if not r["thin"]]
        if solid:
            lo = min(solid, key=lambda r: r["gap_pct"])
            L.append(f"  최저 프리미엄: {lo['channel']} {lo['gap_pct']:+.1f}%")
        L.append("")
    L.append(f"*지난 {rm['days']}일 변동*: 인상 {len(rm['up'])}건 / 인하 {len(rm['down'])}건")
    for m in (rm["down"][:3] + rm["up"][:3]):
        L.append(f"  {m['brand']} {m['channel']} {m['chg_pct']:+.1f}% "
                 f"({m['prev']:,}→{m['curr']:,})")
    if f["stale_count"]:
        bad = ", ".join(f'{x["name"]}({x["lag_days"]}일)' for x in f["channels"] if x["stale"])
        L += ["", f"⚠️ 수집 지연: {bad}"]
    L += ["", "https://perfectjjong.github.io/Shaker-MD-App/dashboards/price-intel/"]
    return "\n".join(L)


REPO = Path("/home/ubuntu/Shaker-MD-App")


def deploy():
    """커밋 + push. rc=0을 배포 성공으로 믿지 않는다 [[project_deploy_branch_drift_incident]].

    2026-08-30 사고: 피처 브랜치에 있으면 `push origin main`이 로컬 main(정지 상태)을
    밀어 "Everything up-to-date" rc=0으로 통과 → 이틀치 배포가 조용히 증발했다.
    그래서 ①main 여부를 먼저 막고 ②push 후 원격과의 차이를 실측한다."""
    import subprocess

    def git(*args, check=True):
        return subprocess.run(["git", "-C", str(REPO), *args],
                              capture_output=True, text=True, check=check)

    branch = git("branch", "--show-current").stdout.strip()
    if branch != "main":
        raise RuntimeError(
            f"배포 중단 — 현재 브랜치가 '{branch}'다(main 아님). "
            f"여기서 push하면 조용히 누락된다. main으로 되돌린 뒤 재실행할 것.")

    rel = str(OUT.relative_to(REPO))
    git("add", rel)
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        print("· 변경 없음 — 커밋 생략")
    else:
        git("-c", "commit.gpgsign=false", "commit", "-q", "-m",
            f"chore(price-intel): 대시보드 갱신 {datetime.now():%Y-%m-%d}")
        print(f"· 커밋 {git('rev-parse', '--short', 'HEAD').stdout.strip()}")

    git("push", "origin", "main")
    git("fetch", "-q", "origin", "main")
    behind = git("rev-list", "--count", "origin/main..main").stdout.strip()
    if behind != "0":
        raise RuntimeError(f"배포 실패 — push 후에도 미반영 커밋 {behind}개. 원격 확인 필요.")
    print("✅ 배포 검증: 원격 main 일치")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--telegram", action="store_true", help="주간 요약 텔레그램 발송")
    ap.add_argument("--deploy", action="store_true", help="커밋+push (원격 검증 포함)")
    a = ap.parse_args()

    d = build_all()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(d), encoding="utf-8")
    print(f"✅ 생성: {OUT}  ({OUT.stat().st_size:,} bytes)")
    print(f"   기준일 {d['freshness']['anchor']} · 지연채널 {d['freshness']['stale_count']}개")

    if a.deploy:
        deploy()

    if a.telegram:
        # chat_id/토큰은 notify 모듈이 정본 — 하드코딩하지 않는다
        sys.path.insert(0, "/home/ubuntu/sonolbot")
        from notify import telegram_send
        if not telegram_send(telegram_summary(d)):
            print("❌ 텔레그램 발송 실패", file=sys.stderr)
            return 2   # 발송 실패는 조용히 넘기지 않는다 — 크론 관제가 rc로 잡는다
        print("✅ 텔레그램 발송 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
