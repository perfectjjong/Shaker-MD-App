# b2c-unified Overview 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** b2c-unified 대시보드 Overview 탭을 경영 브리핑형(So-What 밴드 + KPI 5종 YoY + 4분면 콕핏 + 비교연도 선택기 + 전 차트 데이터 라벨)으로 개편한다.

**Architecture:** 단일 생성기 `b2c_unified_dashboard_generator.py`(1,308줄, HTML/CSS/JS를 `'''` 문자열 연결로 조립 — f-string 아님, JS 중괄호 이스케이프 불필요)만 수정한다. 데이터는 내장 4개년 `_ALL` 재사용, 신규 소스 없음. 브리핑 문장은 파이썬 `build_briefing()`(정적, `_BRIEFING` embed) + JS 룰(필터 적용 시) 하이브리드.

**Tech Stack:** Python 3, pytest, Chart.js 4.4.4 + chartjs-plugin-datalabels 2.2.0(이미 로드됨), Playwright(검증)

**Spec:** `specs/2026-08-16-b2c-overview-redesign-design.md`

---

## 필수 배경지식 (엔지니어 온보딩)

- **생성기**: `/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/02. B2C/01. Python Code/b2c_unified_dashboard_generator.py` (이하 `$GEN`). IR/OR 통합 HTML에서 `_ALL` JSON을 추출·합산해 완성 HTML을 만들고 `~/Shaker-MD-App/docs/dashboards/b2c-unified/index.html`로 복사 후 **자체적으로 git commit+push까지 한다** (`main()` 끝부분). 개발 중 실수 push 방지가 Task 1이다.
- **개발 중 재생성**: IR/OR 소스 HTML은 건드리지 않으므로 상위 파이프라인(consolidator 등) 재실행 불필요. `python3 "$GEN" --no-deploy`만 반복 실행한다 (Task 1에서 플래그 신설). 로컬 출력: 같은 폴더의 `B2C_Unified_Dashboard.html`.
- **JS 데이터 구조** (연도별 `_ALL.data[Y]`):
  - `raw`: 셀아웃 행 `{w:'W33',m:'Aug',ch,model,c(카테고리),type,comp,btu,q}`
  - `sellthru`: 동일 스키마(comp 없음, v 추가)
  - `stock.channels[ch]` = `{total_by_week:{W1:9454,...}, by_category:{cat:{week:qty}}, wos_by_week:{W33:{wos_m8,wos_p8,signal_m8,signal_p8}}}`; `stock.weeks`=주차 배열
  - 시그널: `OPPORTUNITY`(재고부족)/`HEALTHY`/`OVERSTOCK`(과잉)/`INACTIVE` — `getWosSignal()` 기존 함수 재사용
- **연도 특성**: 2023·2024는 스냅샷 주차(~12개: W5,W9,…)만 존재 → 주 단위 YoY 불가, **월 폴백**. 2025·2026은 W1~W52. 판별: `meta.weeks.length>=40`.
- **필터 모델**: `FILTER_STATE={m,w,ch,c,comp,type,btu}` 각각 Set이며 **"제외" 집합**이다 (`has(x)→false` 반환 = 숨김). 필터 UI 재구축+재렌더 진입점은 `cascadeAndUpdate()`(L633).
- **주요 JS 함수 앵커** (생성기 내 라인, 수정 후 밀림 주의 — 앵커 문자열로 찾을 것): `filtered()` L645, `filteredSellthru()` L657, `update()` L708 (KPI L733), `mk()` L692(차트 헬퍼), `updateSD()` L904, `updateWOS()` L989, yearSelect 초기화 L431.
- **문자열 조립**: `html = '''...''' + data_json + '''...'''` — 일반 문자열. JS를 문자 그대로 삽입 가능.

---

### Task 1: `--no-deploy` 개발 안전 플래그

**Files:**
- Modify: `$GEN` (`main()` Step 4 부분, 앵커: `# Step 4: Deploy to Cloudflare`)

- [ ] **Step 1: 플래그 파싱 추가** — `OUTPUT_FILE = ...` 정의 아래에:

```python
NO_DEPLOY = '--no-deploy' in sys.argv
```

- [ ] **Step 2: Step 4 배포 블록 감싸기** — `print("\n[Step 4] Deploying to Cloudflare...")`부터 git push try/except 끝까지를:

```python
    if NO_DEPLOY:
        print("\n[Step 4] SKIPPED (--no-deploy)")
    else:
        print("\n[Step 4] Deploying to Cloudflare...")
        # ... (기존 블록 그대로 들여쓰기 한 단계 추가)
```

- [ ] **Step 3: 검증** — `python3 "$GEN" --no-deploy` 실행. 기대: `[Step 4] SKIPPED (--no-deploy)` 출력, `git -C ~/Shaker-MD-App status` 변화 없음, 로컬 `B2C_Unified_Dashboard.html` 갱신됨.
- [ ] **Step 4: 백업 후 커밋 없음** — 이 폴더는 git 저장소가 아님. 대신 최초 수정 전 1회: `cp "$GEN" "$GEN.bak_$(date +%Y%m%d)"`

### Task 2: 파이썬 `build_briefing()` — TDD

**Files:**
- Modify: `$GEN` (`generate_html` 함수 위에 함수 추가)
- Test: `/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/02. B2C/01. Python Code/tests/test_briefing.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_briefing.py`:

```python
import sys, os, importlib.util
GEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "b2cgen", os.path.join(GEN_DIR, "b2c_unified_dashboard_generator.py"))
b2cgen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b2cgen)

def _merged():
    """2026 W33=100 vs 2025 W33=200 (YoY -50%), eXtra만 하락, BH WOS 과잉 픽스처"""
    def rows(year_qty):
        out = []
        for ch, q in year_qty.items():
            out.append({'w': 'W33', 'm': 'Aug', 'ch': ch, 'model': 'M1',
                        'c': 'Split AC', 'type': 'CO', 'comp': 'Rotary', 'btu': '18000', 'q': q})
        return out
    stock = {'weeks': ['W33'], 'channels': {
        'BH': {'total_by_week': {'W33': 1240},
               'by_category': {'Split AC': {'W33': 1240}},
               'wos_by_week': {'W33': {'wos_m8': 30.0, 'wos_p8': None,
                                       'signal_m8': 'OVERSTOCK', 'signal_p8': 'INACTIVE'}}}},
        'wos_thresholds_ir': {'opportunity': 12, 'healthy': 24},
        'wos_thresholds_or': {'opportunity': 6, 'healthy': 8}}
    return {'years': ['2025', '2026'], 'current': '2026', 'data': {
        '2025': {'meta': {'weeks': ['W%d' % i for i in range(1, 53)], 'months': ['Aug']},
                 'dims': {'channels': ['eXtra', 'BH'], 'categories': ['Split AC']},
                 'raw': rows({'eXtra': 150, 'BH': 50}), 'sellthru': [], 'stock': {}},
        '2026': {'meta': {'weeks': ['W%d' % i for i in range(1, 34)], 'months': ['Aug']},
                 'dims': {'channels': ['eXtra', 'BH'], 'categories': ['Split AC']},
                 'raw': rows({'eXtra': 40, 'BH': 60}),
                 'sellthru': [{'w': 'W33', 'm': 'Aug', 'ch': 'eXtra', 'model': 'M1',
                               'c': 'Split AC', 'type': 'CO', 'btu': '', 'q': 90, 'v': 0}],
                 'stock': stock}}}

def test_briefing_structure_and_yoy():
    b = b2cgen.build_briefing(_merged())
    assert set(b) >= {'week', 'diag', 'reco'}
    assert b['week'] == 'W33'
    assert '-50%' in b['diag']            # 100 vs 200
    assert 'eXtra' in b['diag']           # 최대 하락 채널 (-73%)

def test_briefing_wos_and_reco():
    b = b2cgen.build_briefing(_merged())
    assert 'BH' in b['reco']              # OVERSTOCK 채널 권고
    assert '30' in b['reco']              # WOS 주수 숫자 포함 (라벨 원칙)
```

- [ ] **Step 2: 실패 확인** — `cd "$GEN_DIR" && python3 -m pytest tests/ -v` (pytest 없으면 `pip3 install pytest`). 기대: `AttributeError: build_briefing` FAIL. ⚠️ 모듈 import 시 `main()`이 실행되지 않는지 확인 — `$GEN` 하단이 `if __name__ == '__main__':` 가드인지 먼저 확인하고, 가드가 없으면 이 태스크에서 가드부터 추가한다.
- [ ] **Step 3: 구현** — `$GEN`의 `generate_html` 정의 바로 위에:

```python
def build_briefing(merged):
    """정적 So-What 브리핑(필터 미적용 초기 화면용). 현재연도 vs 직전연도."""
    cur = merged['current']
    prev = str(int(cur) - 1)
    d = merged['data'].get(cur, {})
    cd = merged['data'].get(prev, {})
    raw, craw = d.get('raw', []), cd.get('raw', [])
    weeks = d.get('meta', {}).get('weeks', [])
    lw = weeks[-1] if weeks else ''
    prev_weekly = len(cd.get('meta', {}).get('weeks', [])) >= 40

    def q(rows, **kw):
        return sum(r['q'] for r in rows if all(r.get(k) == v for k, v in kw.items()))

    lq = q(raw, w=lw)
    parts, recos = [], []
    # 1) 최신주 YoY (직전연도 주차 결손 시 동월 합으로 폴백)
    lm = next((r['m'] for r in raw if r['w'] == lw), '')
    cq = q(craw, w=lw) if prev_weekly else 0
    basis = 'YoY'
    if not cq and lm:
        cq, basis = q(craw, m=lm), 'YoY(월기준)'
    if cq:
        yoy = round((lq - cq) / cq * 100)
        parts.append(f"{lw} 셀아웃 {lq:,}대 ({basis} {yoy:+d}%).")
        # 2) 최대 하락 채널 (동일 기준)
        chs = sorted({r['ch'] for r in raw if r['w'] == lw})
        worst = None
        for ch in chs:
            a = q(raw, w=lw, ch=ch)
            b = q(craw, w=lw, ch=ch) if prev_weekly and q(craw, w=lw, ch=ch) else q(craw, m=lm, ch=ch)
            if b:
                g = round((a - b) / b * 100)
                if worst is None or g < worst[1]:
                    worst = (ch, g)
        if worst and worst[1] < 0:
            parts.append(f"최대 하락: {worst[0]} ({worst[1]:+d}%).")
    else:
        parts.append(f"{lw} 셀아웃 {lq:,}대 (비교연도 데이터 없음).")
    # 3) WOS 위험 → 권고
    stk = d.get('stock', {}) or {}
    sweeks = stk.get('weeks', [])
    slw = sweeks[-1] if sweeks else ''
    for ch, c in (stk.get('channels', {}) or {}).items():
        wb = (c.get('wos_by_week', {}) or {}).get(slw, {})
        sig, wos = wb.get('signal_m8'), wb.get('wos_m8')
        if sig == 'OVERSTOCK':
            recos.append(f"{ch} 과재고(WOS {wos:.0f}주) 소진 프로모션 검토")
        elif sig == 'OPPORTUNITY':
            recos.append(f"{ch} 재고부족(WOS {wos:.0f}주) 긴급 보충 검토")
    if not recos:
        recos.append("주요 재고 위험 없음 — 현 운영 유지")
    return {'week': lw, 'diag': ' '.join(parts),
            'reco': '권고: ' + ' / '.join(f"{i+1}) {r}" for i, r in enumerate(recos[:3]))}
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/ -v` 기대: 2 passed.
- [ ] **Step 5: embed** — `generate_html` 내 `const _ALL = ''' + data_json + ''';` 라인을 다음으로 교체:

```python
const _ALL = ''' + data_json + ''';
const _BRIEFING = ''' + json.dumps(build_briefing(merged), ensure_ascii=False) + ''';
```

(파이썬 쪽: `data_json = ...` 아래에 `briefing_json = json.dumps(build_briefing(merged), ensure_ascii=False)` 만들고 문자열 연결에 사용해도 동일 — 스타일 자유, 결과는 `const _BRIEFING = {...};` 한 줄)
- [ ] **Step 6: 재생성 검증** — `python3 "$GEN" --no-deploy && grep -c "_BRIEFING" B2C_Unified_Dashboard.html` 기대: ≥2 (선언+사용... 이 시점엔 1도 허용).

### Task 3: JS 비교연도 상태 + 필터 함수 일반화

**Files:**
- Modify: `$GEN` JS부 (앵커: `let D=_ALL.data[currentYear];`, `function filtered(){`, `function filteredSellthru(){`)

- [ ] **Step 1: 전역 상태 추가** — `let D=_ALL.data[currentYear];` 바로 아래:

```js
// ===== YoY compare state =====
function defaultCompareYear(){const p=String(+currentYear-1);const c=_ALL.years.filter(y=>y!==currentYear);return c.includes(p)?p:(c[c.length-1]||currentYear);}
let compareYear=defaultCompareYear();
let CD=_ALL.data[compareYear];
function cmpWeekly(){return ((CD&&CD.meta&&CD.meta.weeks)||[]).length>=40;} // 2023/24 스냅샷=false→월 폴백
```

- [ ] **Step 2: filtered 일반화** — `function filtered(){ return D.raw.filter(...) }` 본문을 데이터셋 인자 버전으로 분리:

```js
function filteredRows(dd){
  if(!dd||!dd.raw)return[];
  return dd.raw.filter(r=>{
    if(FILTER_STATE.m.size>0&&FILTER_STATE.m.has(r.m))return false;
    if(FILTER_STATE.w.size>0&&FILTER_STATE.w.has(r.w))return false;
    if(FILTER_STATE.ch.size>0&&FILTER_STATE.ch.has(r.ch))return false;
    if(FILTER_STATE.c.size>0&&FILTER_STATE.c.has(r.c))return false;
    if(FILTER_STATE.comp.size>0&&FILTER_STATE.comp.has(r.comp))return false;
    if(FILTER_STATE.type.size>0&&FILTER_STATE.type.has(r.type))return false;
    if(FILTER_STATE.btu.size>0&&FILTER_STATE.btu.has(r.btu))return false;
    return true;
  });
}
function filtered(){return filteredRows(D);}
```

(주의: 비교연도 적용 시 주차 제외 필터(`FILTER_STATE.w`)는 라벨이 같아야 의미가 있음 — 월 폴백 모드에서는 KPI/차트 계산이 월 기준이라 자연 무해)
- [ ] **Step 3: sellthru 동일 처리** — `filteredSellthruRows(dd)` + `filteredSellthru(){return filteredSellthruRows(D);}` (기존 본문 그대로, `D.sellthru`→`dd.sellthru`)
- [ ] **Step 4: 재생성 + 콘솔 검증** — `python3 "$GEN" --no-deploy` 후 브라우저(또는 Playwright)로 로컬 파일 열어 콘솔 에러 0, 기존 화면 동일 렌더 확인.

### Task 4: "vs 연도" 선택기 UI

**Files:**
- Modify: `$GEN` HTML부(앵커: `id="fYear"` filter-group 라인), JS부(앵커: `// Build year selector`)

- [ ] **Step 1: HTML** — Year filter-group `</div></div>` 바로 뒤에:

```html
<div class="filter-group"><div class="filter-label">vs Year</div><div class="ms-wrap"><select id="vsYearSelect" class="ms-btn" style="padding:4px 8px;border:1px solid var(--border);border-radius:4px;font-size:12px;font-weight:600;cursor:pointer;background:var(--teal);color:#fff"></select></div></div>
```

- [ ] **Step 2: JS 빌더** — `// Build year selector` IIFE 아래에:

```js
function rebuildVsYear(){
  const sel=document.getElementById('vsYearSelect');
  sel.innerHTML='';
  _ALL.years.filter(y=>y!==currentYear).forEach(yr=>{
    const o=document.createElement('option');o.value=yr;o.textContent='vs '+yr;
    if(yr===compareYear)o.selected=true;sel.appendChild(o);
  });
}
rebuildVsYear();
document.getElementById('vsYearSelect').addEventListener('change',e=>{
  compareYear=e.target.value;CD=_ALL.data[compareYear];update();
});
```

- [ ] **Step 3: 연도 전환 연동** — 기존 `yearSelect` change 핸들러에서 `update()` 호출 전(앵커: `WEEKS=D.meta.weeks;MONTHS=D.meta.months;` 근처)에 추가:

```js
    compareYear=defaultCompareYear();CD=_ALL.data[compareYear];rebuildVsYear();
```

- [ ] **Step 4: 검증** — 재생성 후 브라우저: vs 드롭다운 표시(기본 vs 2025), 2024 선택/연도 전환 시 콘솔 에러 0.

### Task 5: Overview pane HTML + CSS 재구성

**Files:**
- Modify: `$GEN` HTML부(앵커: `<!-- OVERVIEW -->` ~ `<!-- CHANNEL -->` 직전), CSS부(앵커: `.grid-6{` 라인 뒤)

- [ ] **Step 1: pane-overview 교체** — 기존 블록 전체를:

```html
<!-- OVERVIEW -->
<div class="tab-pane active" id="pane-overview">
<div id="sowhatBand" class="sowhat" style="display:none"></div>
<div class="grid-5" id="kpiRow"></div>
<div class="grid-2">
<div class="card"><h3>Weekly Sell-Out Trend <span class="h3sub" id="trendSub"></span></h3><div class="ch-300"><canvas id="cWeekly"></canvas></div></div>
<div class="card"><h3>Channel × Category YoY <span class="h3sub" id="hmSub"></span></h3><div class="ch-300" style="overflow:auto"><table class="yoyhm" id="tblYoyHm"></table></div></div>
</div>
<div class="grid-2">
<div class="card"><h3>WOS Signal (Latest Week)</h3><div class="ch-300" style="overflow-y:auto" id="wosSignalList"></div></div>
<div class="card"><h3>Sell-Thru vs Sell-Out Gap</h3><div class="ch-300" style="overflow-y:auto" id="gapList"></div></div>
</div>
<details class="ov-fold" id="ovFold"><summary>▸ Detail Charts — Monthly Sales · Sales by Category · Category Weekly Trend</summary>
<div class="grid-3" style="margin-top:12px">
<div class="card"><h3>Monthly Sales</h3><div class="ch-300"><canvas id="cMonthly"></canvas></div></div>
<div class="card"><h3>Sales by Category</h3><div class="ch-300"><canvas id="cCatPie"></canvas></div></div>
<div class="card"><h3>Category Weekly Trend</h3><div class="ch-300"><canvas id="cCatWeek"></canvas></div></div>
</div></details>
</div>
```

- [ ] **Step 2: CSS 추가** — `.grid-6{...}` 라인 다음에:

```css
.sowhat{background:var(--primary);color:var(--card);border-radius:var(--radius);padding:12px 18px;margin-bottom:16px;position:relative}
.sowhat .sw-h{font-size:11px;letter-spacing:.06em;text-transform:uppercase;opacity:.85;font-weight:700;margin-bottom:4px}
.sowhat p{margin:0 0 3px;font-size:13px;line-height:1.6}
.sowhat .sw-mode{position:absolute;top:10px;right:14px;font-size:10px;border:1px solid currentColor;border-radius:10px;padding:1px 8px;opacity:.8}
.h3sub{font-weight:400;color:var(--muted);font-size:11px}
.cmp-badge{background:var(--amber);color:#fff;border-radius:8px;font-size:10px;padding:1px 7px;margin-left:6px;vertical-align:1px}
table.yoyhm{border-collapse:collapse;width:100%;font-size:11px}
.yoyhm th{color:var(--muted);font-weight:600;padding:3px 5px;text-align:right;position:sticky;top:0;background:var(--card)}
.yoyhm th:first-child,.yoyhm td:first-child{text-align:left}
.yoyhm td{padding:4px 5px;text-align:right;font-weight:700;cursor:pointer;border-radius:3px}
.wos-row,.gap-row{display:flex;align-items:center;gap:8px;font-size:12px;padding:5px 2px;border-bottom:1px solid var(--border)}
.wos-row{cursor:pointer}
.wos-dot{width:11px;height:11px;border-radius:50%;flex:none}
.wos-ch,.gap-ch{width:110px;font-weight:600;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gap-bars{flex:1;display:flex;flex-direction:column;gap:2px;min-width:0}
.gap-bar{height:7px;border-radius:3px;min-width:2px}
.gap-pct{width:52px;text-align:right;font-weight:800;font-size:11px;flex:none}
.ov-fold{margin-bottom:20px}
.ov-fold summary{cursor:pointer;font-size:12px;font-weight:600;color:var(--muted);padding:8px 4px}
```

- [ ] **Step 3: details 열림 시 차트 리사이즈** — JS 말미(앵커: 파일 끝 `update();` 근처)에:

```js
document.getElementById('ovFold').addEventListener('toggle',()=>{['cMonthly','cCatPie','cCatWeek'].forEach(id=>{if(charts[id])charts[id].resize()});});
```

- [ ] **Step 4: 검증** — 재생성 후 브라우저: 새 구조 표시(4분면 자리 2개는 아직 빈 카드), 접이식 열면 기존 3차트 정상 렌더, 콘솔 에러 0. ⚠️ 기존 `update()`가 지운 `cWeekly` 스택차트는 아직 옛 코드로 렌더됨 — 정상(다음 태스크에서 교체).

### Task 6: KPI 5종 교체

**Files:**
- Modify: `$GEN` JS `update()` 내 KPI 블록(앵커: `document.getElementById('kpiRow').innerHTML=[` 배열 전체와 그 위 `chCount`/`modelCount` 라인)

- [ ] **Step 1: 비교 집계 계산 삽입** — `const ar=(v)=>...` 라인 위에:

```js
  // ===== YoY vs compareYear =====
  const crows=filteredRows(CD);
  const isWk=cmpWeekly();
  const wkNum=w=>+String(w).replace('W','')||0;
  const cwq=sumBy(crows,'w');
  const yoyPct=(a,b)=>b?Math.round((a-b)/b*100):null;
  // ① 최신주
  const cLW=isWk?(cwq[_lw]||0):0;
  const yoyW=isWk?yoyPct(lq,cLW):null;
  // ② 월누적(MTD): 주간모드=비교연도 동월 同주차까지 / 월모드=동월 전체
  const dMTD=rows.filter(r=>r.m===_cm).reduce((a,r)=>a+r.q,0);
  const cMTD=crows.filter(r=>r.m===_cm&&(!isWk||wkNum(r.w)<=wkNum(_lw))).reduce((a,r)=>a+r.q,0);
  const yoyM=yoyPct(dMTD,cMTD);
  // ③ YTD
  const cmi=MONTHS.indexOf(_cm);
  const cYTD=crows.filter(r=>isWk?wkNum(r.w)<=wkNum(_lw):(MONTHS.indexOf(r.m)>=0&&MONTHS.indexOf(r.m)<=cmi)).reduce((a,r)=>a+r.q,0);
  const yoyY=yoyPct(total,cYTD);
  // ④ WOS 위험 (최신 재고주, 그룹/채널 필터 반영)
  const stkW=((D.stock||{}).weeks||[]);const slw=stkW[stkW.length-1]||'';
  const wosRisks=[];
  Object.entries((D.stock||{}).channels||{}).forEach(([ch,c])=>{
    if(FILTER_STATE.ch.size>0&&FILTER_STATE.ch.has(ch))return;
    const wb=(c.wos_by_week||{})[slw];if(!wb)return;
    if(wb.signal_m8==='OVERSTOCK'||wb.signal_m8==='OPPORTUNITY')
      wosRisks.push({ch,sig:wb.signal_m8,wos:wb.wos_m8,stk:(c.total_by_week||{})[slw]||0});
  });
  wosRisks.sort((a,b)=>(b.sig==='OVERSTOCK'?b.wos:99-b.wos)-(a.sig==='OVERSTOCK'?a.wos:99-a.wos));
  const nOver=wosRisks.filter(r=>r.sig==='OVERSTOCK').length,nShort=wosRisks.length-nOver;
  // ⑤ ST−SO 갭
  const stRows=filteredSellthru();
  const stq=sumBy(stRows,'ch'),soq=sumBy(rows,'ch');
  const stT=stRows.reduce((a,r)=>a+r.q,0);
  const gapPct=total?Math.round((stT-total)/total*100):null;
  let gapMax={ch:'-',g:0};
  Object.keys(soq).forEach(ch=>{if(!soq[ch])return;const g=Math.round(((stq[ch]||0)-soq[ch])/soq[ch]*100);if(Math.abs(g)>Math.abs(gapMax.g))gapMax={ch,g};});
  const modeBadge=isWk?'':'<span class="cmp-badge">월 기준 비교</span>';
  const yy=v=>v===null?'N/A':(ar(v)+' '+Math.abs(v)+'% YoY');
```

- [ ] **Step 2: KPI 배열 교체** — 기존 5개 객체 배열(`{l:'Latest Week...'}` ~ `{l:'Unified Models'...}`)을:

```js
    {l:'Latest Week ('+_lw+') vs '+compareYear,v:lq.toLocaleString(),s:yy(yoyW)+' · WoW '+ar(wow)+Math.abs(wow)+'%'+modeBadge,c:cl(yoyW===null?wow:yoyW),b:'var(--primary)'},
    {l:'Month ('+_cm+') MTD vs '+compareYear,v:dMTD.toLocaleString(),s:yy(yoyM)+' · MoM '+ar(mom)+Math.abs(mom)+'%',c:cl(yoyM||0),b:'var(--teal)'},
    {l:'YTD vs '+compareYear,v:total.toLocaleString(),s:yy(yoyY)+' · \''+compareYear.slice(2)+' 동기 '+cYTD.toLocaleString(),c:cl(yoyY||0),b:'var(--green)'},
    {l:'WOS Risk ('+slw+')',v:wosRisks.length+'건',s:'과잉 '+nOver+' · 부족 '+nShort+(wosRisks[0]?' · 최다: '+wosRisks[0].ch:''),c:wosRisks.length?'down':'up',b:'var(--amber)'},
    {l:'ST−SO Gap',v:(gapPct===null?'N/A':(gapPct>0?'+':'')+gapPct+'%'),s:(gapPct>15?'밀어넣기 주의':gapPct<-15?'결품 위험':'균형')+' · 최대: '+gapMax.ch+' '+(gapMax.g>0?'+':'')+gapMax.g+'%',c:Math.abs(gapPct||0)>15?'down':'',b:'var(--purple)'},
```

(주의: 기존 `chCount`/`modelCount` 계산 라인은 삭제)
- [ ] **Step 3: 검증** — 재생성 후 파이썬 독립 재계산과 대사(Task 12 스크립트의 초기 버전을 이 시점에 만들어도 됨): 최소 `ALL` 기준 최신주/YTD YoY 값을 파이썬으로 계산해 화면 숫자와 일치 확인. `vs 2024` 전환 시 "월 기준 비교" 배지 표시 확인.

### Task 7: 4분면 ① 트렌드 오버레이 (+라벨)

**Files:**
- Modify: `$GEN` JS `update()` 내 `// Weekly bar (stacked by channel)` mk('cWeekly') 호출 블록

- [ ] **Step 1: mk 호출 교체**:

```js
  // Q1: 셀아웃 트렌드 — 올해 스택바 + 비교연도 라인 (월 폴백 시 월 축)
  const activeChs=D.dims.channels.filter(ch=>!FILTER_STATE.ch.has(ch));
  const cmpName=compareYear+(isWk?'':' (month)');
  let q1Labels,q1Bars,q1Line;
  if(isWk){
    const cwk=sumByTwo(rows,'ch','w');
    q1Labels=filteredWeeks;
    q1Bars=activeChs.map(ch=>({label:ch,data:filteredWeeks.map(w=>(cwk[ch]||{})[w]||0),backgroundColor:CH_COLORS[ch]||'#999',stack:'cur',order:2}));
    q1Line={type:'line',label:cmpName,data:filteredWeeks.map(w=>cwq[w]||0),borderColor:'var(--green)'.startsWith('var')?getComputedStyle(document.documentElement).getPropertyValue('--green').trim():'#1d6b45',borderWidth:2,borderDash:[6,4],pointRadius:2,fill:false,order:1};
    document.getElementById('trendSub').innerHTML=currentYear+' bar vs '+compareYear+' line';
  }else{
    const cmn=sumByTwo(rows,'ch','m');
    const cmm=sumBy(crows,'m');
    q1Labels=MONTHS;
    q1Bars=activeChs.map(ch=>({label:ch,data:MONTHS.map(m=>(cmn[ch]||{})[m]||0),backgroundColor:CH_COLORS[ch]||'#999',stack:'cur',order:2}));
    q1Line={type:'line',label:cmpName,data:MONTHS.map(m=>cmm[m]||0),borderColor:getComputedStyle(document.documentElement).getPropertyValue('--green').trim()||'#1d6b45',borderWidth:2,borderDash:[6,4],pointRadius:2,fill:false,order:1};
    document.getElementById('trendSub').innerHTML=currentYear+' bar vs '+compareYear+' line <span class="cmp-badge">월 기준 비교</span>';
  }
  mk('cWeekly','bar',{labels:q1Labels,datasets:[...q1Bars,q1Line]},
    {datalabels:{display:true,anchor:'end',align:'top',font:{size:9,weight:'bold'},color:'#453f35',
      formatter:(v,ctx)=>{
        const ds=ctx.chart.data.datasets,idx=ctx.dataIndex;
        if(ds[ctx.datasetIndex].type==='line')return idx===ds[ctx.datasetIndex].data.length-1?v.toLocaleString():'';
        const bars=ds.filter(d=>d.type!=='line');
        if(ds[ctx.datasetIndex]===bars[bars.length-1]){let t=0;bars.forEach(d=>{t+=d.data[idx]||0});return t.toLocaleString()}
        return'';
      }},
    scales:{x:{stacked:true},y:{stacked:true,beginAtZero:true}},plugins:{legend:{position:'top',labels:{font:{size:9}}}}});
```

(주의: 기존 블록의 `const cwk=...`, `const activeChs=...` 중복 선언 제거. 라벨의 주차 날짜 표기(`week_dates`)는 라벨 복잡도 때문에 주간모드에서 기존 방식 유지 가능 — `filteredWeeks.map(w=>w+'\n'+(D.meta.week_dates[w]||''))` 대신 위처럼 단순화; 시각 확인 후 결정)
- [ ] **Step 2: 검증** — 재생성 후 브라우저: 바+점선 라인 동시 표시, 바 합계 라벨·라인 끝 값 라벨 표시, vs 2024 선택 시 X축이 월로 전환+배지.

### Task 8: 4분면 ② YoY 히트맵 + 셀 드릴다운

**Files:**
- Modify: `$GEN` JS — `update()` 내 (기존 `// Category pie` 블록 앞), 전역에 `hmDrill` 추가

- [ ] **Step 1: 렌더 코드 삽입** — `update()` 내부:

```js
  // Q2: 채널×카테고리 YoY 히트맵 (라벨 원칙: 셀 안 % 숫자)
  const hmCur=sumByTwo(rows,'ch','c'),hmCmp=sumByTwo(crows,'ch','c');
  const hmCats=D.dims.categories.filter(c=>!FILTER_STATE.c.has(c));
  const hmChs=activeChs.filter(ch=>Object.keys(hmCur[ch]||{}).length||Object.keys(hmCmp[ch]||{}).length);
  const hmCell=(g)=>{
    if(g===null)return'background:var(--bg);color:var(--muted-light)';
    if(g<=-25)return'background:var(--red);color:#fff';
    if(g<0)return'background:rgba(179,38,30,.16);color:var(--red)';
    if(g>=10)return'background:rgba(29,107,69,.2);color:var(--green-deep-text)';
    return'background:var(--bg);color:var(--muted)';
  };
  document.getElementById('hmSub').innerHTML='YoY vs '+compareYear+(isWk?'':' · 월 기준')+' — 셀 클릭=드릴다운';
  document.getElementById('tblYoyHm').innerHTML=
    '<thead><tr><th></th>'+hmCats.map(c=>'<th>'+c.replace(' AC','').replace(' Set','')+'</th>').join('')+'</tr></thead><tbody>'+
    hmChs.map(ch=>'<tr><td>'+ch+'</td>'+hmCats.map(c=>{
      const a=(hmCur[ch]||{})[c]||0,b=(hmCmp[ch]||{})[c]||0;
      const g=b?Math.round((a-b)/b*100):null;
      return'<td style="'+hmCell(g)+'" data-ch="'+ch+'" data-c="'+c+'" onclick="hmDrill(this)" title="'+currentYear+': '+a.toLocaleString()+' / '+compareYear+': '+b.toLocaleString()+'">'+(g===null?'–':(g>0?'+':'')+g+'%')+'</td>';
    }).join('')+'</tr>').join('')+'</tbody>';
```

- [ ] **Step 2: 드릴다운 전역 함수** — `cascadeAndUpdate()` 정의 아래:

```js
function hmDrill(td){
  const ch=td.dataset.ch,cat=td.dataset.c;
  FILTER_STATE.ch.clear();FILTER_STATE.c.clear();
  D.dims.channels.filter(x=>x!==ch).forEach(x=>FILTER_STATE.ch.add(x));
  D.dims.categories.filter(x=>x!==cat).forEach(x=>FILTER_STATE.c.add(x));
  cascadeAndUpdate();
}
```

- [ ] **Step 3: 검증** — 히트맵 % 숫자 표시, 툴팁에 양 연도 수량, 셀 클릭 → 필터 적용(filterCount 갱신)·체크박스 UI 동기화 확인. UI 미동기 시 `cascadeAndUpdate()` 대신 `FILTER_ORDER.forEach(id=>buildMultiSelect(id));update();`로 교정.

### Task 9: 4분면 ③ WOS 신호등

**Files:**
- Modify: `$GEN` JS `update()` 내 (Task 8 코드 아래)

- [ ] **Step 1: 렌더 코드**:

```js
  // Q3: WOS 신호등 (라벨 원칙: WOS 주수·재고수량 숫자 병기)
  const wosAll=[];
  Object.entries((D.stock||{}).channels||{}).forEach(([ch,c])=>{
    if(FILTER_STATE.ch.size>0&&FILTER_STATE.ch.has(ch))return;
    const wb=(c.wos_by_week||{})[slw];if(!wb||wb.wos_m8===null||wb.wos_m8===undefined)return;
    wosAll.push({ch,sig:wb.signal_m8,wos:wb.wos_m8,stk:(c.total_by_week||{})[slw]||0});
  });
  const sigRank={OVERSTOCK:0,OPPORTUNITY:1,HEALTHY:2,INACTIVE:3};
  wosAll.sort((a,b)=>(sigRank[a.sig]-sigRank[b.sig])||(b.wos-a.wos));
  const sigKo={OVERSTOCK:'과잉',OPPORTUNITY:'부족',HEALTHY:'적정',INACTIVE:'-'};
  document.getElementById('wosSignalList').innerHTML=wosAll.map(r=>
    '<div class="wos-row" onclick="document.querySelector(\'[data-tab=wos]\').click()">'+
    '<span class="wos-dot" style="background:'+WOS_COLORS[r.sig]+'"></span>'+
    '<span class="wos-ch">'+r.ch+'</span>'+
    '<b style="color:'+WOS_COLORS[r.sig]+'">'+sigKo[r.sig]+' '+r.wos.toFixed(1)+'주</b>'+
    '<span style="color:var(--muted);margin-left:auto">재고 '+r.stk.toLocaleString()+'</span></div>'
  ).join('')||'<div style="color:var(--muted);padding:8px">No stock data for '+currentYear+'</div>';
```

- [ ] **Step 2: 검증** — 위험(빨강) 상단 정렬, "과잉 21.3주 · 재고 1,240" 형식 숫자 표기, 행 클릭 → WOS 탭 전환.

### Task 10: 4분면 ④ ST vs SO 갭

**Files:**
- Modify: `$GEN` JS `update()` 내 (Task 9 코드 아래)

- [ ] **Step 1: 렌더 코드**:

```js
  // Q4: 채널별 Sell-Thru vs Sell-Out 갭 (라벨 원칙: ST/SO 수량+갭%)
  const gapRows=Object.keys(soq).filter(ch=>soq[ch]>0).map(ch=>({ch,st:stq[ch]||0,so:soq[ch],g:Math.round(((stq[ch]||0)-soq[ch])/soq[ch]*100)}));
  gapRows.sort((a,b)=>Math.abs(b.g)-Math.abs(a.g));
  const gMax=Math.max(1,...gapRows.map(r=>Math.max(r.st,r.so)));
  document.getElementById('gapList').innerHTML=gapRows.slice(0,10).map(r=>
    '<div class="gap-row"><span class="gap-ch">'+r.ch+'</span>'+
    '<div class="gap-bars">'+
    '<div class="gap-bar" style="width:'+Math.round(r.st/gMax*100)+'%;background:var(--primary)" title="Sell-Thru '+r.st.toLocaleString()+'"></div>'+
    '<div class="gap-bar" style="width:'+Math.round(r.so/gMax*100)+'%;background:var(--sky)" title="Sell-Out '+r.so.toLocaleString()+'"></div></div>'+
    '<span style="color:var(--muted);font-size:10px;flex:none">ST '+r.st.toLocaleString()+' / SO '+r.so.toLocaleString()+'</span>'+
    '<span class="gap-pct" style="color:'+(Math.abs(r.g)>20?'var(--red)':'var(--muted)')+'">'+(r.g>0?'+':'')+r.g+'%</span></div>'
  ).join('')||'<div style="color:var(--muted);padding:8px">No sell-thru data</div>';
```

- [ ] **Step 2: 검증** — |갭%| 내림차순 상위 10채널, ST/SO 수량 텍스트+갭% 표시, ±20% 초과 빨강.

### Task 11: So-What 밴드 하이브리드 렌더

**Files:**
- Modify: `$GEN` JS — 전역 상수 + `update()` 마지막(Overview 렌더 뒤)

- [ ] **Step 1: 플래그** — `const WOS_LABELS=...` 아래:

```js
const SHOW_BRIEFING=true; // 품질 검증 후 형님 결정으로 false 가능 (spec §3.4)
```

- [ ] **Step 2: 렌더 함수** — `update()` 정의 위:

```js
function renderBriefing(m){
  const el=document.getElementById('sowhatBand');
  if(!SHOW_BRIEFING){el.style.display='none';return;}
  const pristine=currentGroup==='ALL'&&currentYear===_ALL.current&&compareYear===defaultCompareYear()
    &&Object.values(FILTER_STATE).every(s=>s.size===0);
  let diag,reco,mode;
  if(pristine&&typeof _BRIEFING!=='undefined'&&_BRIEFING.diag){
    diag=_BRIEFING.diag;reco=_BRIEFING.reco;mode='기준: 전체 · 생성시점 분석';
  }else{
    const p=[];
    p.push(m.lw+' 셀아웃 '+m.lq.toLocaleString()+'대'+(m.yoyW===null?'':' (YoY '+(m.yoyW>0?'+':'')+m.yoyW+'%)')+'.');
    if(m.yoyM!==null)p.push('월누적 YoY '+(m.yoyM>0?'+':'')+m.yoyM+'%.');
    const r=[];
    if(m.wosRisks.length)r.push(m.wosRisks[0].ch+' '+(m.wosRisks[0].sig==='OVERSTOCK'?'과재고':'재고부족')+'(WOS '+m.wosRisks[0].wos.toFixed(0)+'주) 대응');
    if(Math.abs(m.gapMax.g)>20)r.push(m.gapMax.ch+' ST−SO 갭 '+(m.gapMax.g>0?'+':'')+m.gapMax.g+'% 점검');
    diag=p.join(' ');reco=r.length?'권고: '+r.map((x,i)=>(i+1)+') '+x).join(' / '):'권고: 특이 위험 없음';
    mode='기준: 현재 필터';
  }
  el.style.display='block';
  el.innerHTML='<div class="sw-mode">'+mode+'</div><div class="sw-h">🚨 '+m.lw+' Briefing — So What</div><p><b>'+diag+'</b></p><p>'+reco+'</p>';
}
```

- [ ] **Step 3: 호출** — `update()` 내 KPI 렌더 직후:

```js
  renderBriefing({lw:_lw,lq,yoyW,yoyM,wosRisks,gapMax});
```

- [ ] **Step 4: 검증** — 초기 화면=embed 문장+"생성시점 분석" 표기, 필터 하나 적용 시 룰 문장+"현재 필터" 표기로 전환.

### Task 12: 통합 검증 스크립트 + 게이트

**Files:**
- Create: `/home/ubuntu/2026/10. Automation/01. Sell Out Dashboard/02. B2C/01. Python Code/verify_overview.py`

- [ ] **Step 1: 검증 스크립트 작성**:

```python
#!/usr/bin/env python3
"""Overview 개편 검증: (1) KPI YoY 파이썬 독립 재계산 (2) Playwright DOM 대사 (3) 탭 회귀"""
import json, re, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "B2C_Unified_Dashboard.html")

def load_all():
    c = open(HTML, encoding='utf-8').read()
    m = re.search(r'const _ALL = (\{.*?\});\n', c, re.S)
    return json.loads(m.group(1))

def expected_kpis(all_data, group='ALL'):
    IR = ['BH','BM','Tamkeen','Zagzoog','Dhamin','Star Appliance','Al Ghanem','Al Shathri','Box Appliance','IR_Others']
    OR = ['Al Manea','SWS','Black Box','Al Khunizan','eXtra','OR_Others']
    cur, cmp_ = all_data['current'], str(int(all_data['current'])-1)
    d, cd = all_data['data'][cur], all_data['data'][cmp_]
    keep = {'ALL': IR+OR, 'IR': IR, 'OR': OR}[group]
    rows = [r for r in d['raw'] if r['ch'] in keep]
    crows = [r for r in cd['raw'] if r['ch'] in keep]
    wk = lambda w: int(str(w).replace('W','') or 0)
    weeks_pos = sorted({r['w'] for r in rows}, key=wk)
    lw = weeks_pos[-1]
    lq = sum(r['q'] for r in rows if r['w'] == lw)
    cq = sum(r['q'] for r in crows if r['w'] == lw)
    ytd = sum(r['q'] for r in rows)
    cytd = sum(r['q'] for r in crows if wk(r['w']) <= wk(lw))
    pct = lambda a,b: round((a-b)/b*100) if b else None
    return {'lw': lw, 'lq': lq, 'yoyW': pct(lq,cq), 'ytd': ytd, 'yoyY': pct(ytd,cytd)}

def main():
    all_data = load_all()
    print("=== [1] KPI 독립 재계산 ===")
    exp = {}
    for g in ('ALL','IR','OR'):
        exp[g] = expected_kpis(all_data, g)
        print(f"  {g}: {exp[g]}")
    print("=== [2] Playwright DOM 대사 (group=ALL) ===")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        errors = []
        pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        pg.goto('file://' + HTML); pg.wait_for_timeout(2500)
        kpi = pg.inner_text('#kpiRow')
        e = exp['ALL']
        for label, val in (('최신주 수량', f"{e['lq']:,}"), ('YoY주간', str(abs(e['yoyW']))), ('YTD', f"{e['ytd']:,}")):
            ok = val in kpi
            print(f"  KPI {label}={val}: {'OK' if ok else 'MISMATCH'}"); assert ok, kpi
        for sel in ('#sowhatBand', '#tblYoyHm td', '#wosSignalList .wos-row', '#gapList .gap-row', '#vsYearSelect'):
            n = pg.locator(sel).count()
            print(f"  {sel}: {n}개"); assert n > 0, sel
        print("=== [3] 탭 회귀 (7탭 렌더 + 콘솔에러 0) ===")
        for t in ('channel','product','supplydemand','wos','price','detail','overview'):
            pg.click(f'[data-tab={t}]'); pg.wait_for_timeout(600)
        pg.screenshot(path=os.path.join(HERE, 'verify_overview.png'), full_page=False)
        b.close()
        assert not errors, errors
        print("  콘솔 에러 0 OK")
    print("\nALL CHECKS PASSED")

if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 실행** — `python3 "$GEN" --no-deploy && python3 verify_overview.py` 기대: `ALL CHECKS PASSED`. (playwright 미설치 시 `. /home/ubuntu/ai_env/bin/activate` 후 실행 — 가격 추적이 쓰는 환경에 이미 있음)
- [ ] **Step 3: IR/OR 그룹 대사** — 브라우저에서 Group=IR/OR 클릭 후 KPI YoY가 `expected_kpis`의 IR/OR 값과 일치하는지 수동 확인(또는 Playwright에 `#btnIR` 클릭 추가).
- [ ] **Step 4: vs 2024 폴백** — Playwright/수동: vs 2024 선택 → "월 기준 비교" 배지, 트렌드 X축=월 확인.
- [ ] **Step 5: 부품 오염 게이트** — `python3 "/home/ubuntu/2026/10. Automation/dashboard_part_contamination_gate.py"` 기대: **GATE PASS**. 미통과 시 '완료' 단어 금지.
- [ ] **Step 6: pytest 재실행** — `python3 -m pytest tests/ -v` 전부 통과.

### Task 13: 배포 + 보고

- [ ] **Step 1: 최종 생성+배포** — `python3 "$GEN"` (플래그 없이). 생성기가 Cloudflare 복사 + git commit/push 자동 수행. 기대: `Pushed to GitHub -> Cloudflare auto-deploy`.
- [ ] **Step 2: 스펙/플랜 체크박스 갱신 + Shaker-MD-App 커밋** — `specs/` 문서 상태 갱신 후 커밋·푸시(대시보드 push에 편승 금지, 별도 커밋).
- [ ] **Step 3: 라이브 확인** — 1~2분 후 https://shaker-dashboard.pages.dev/dashboards/b2c-unified/ 새로고침, Overview 렌더 확인.
- [ ] **Step 4: 보고** — 형식: "✅ Overview 개편 배포 완료 (검증: KPI 재계산 3그룹 일치 · Playwright 7탭 회귀 통과 · GATE PASS)" + So-What 밴드 품질 샘플 제시 → 유지/제거 결정 요청. 미검증 항목 있으면 명시.

---

## Self-Review 결과

- **스펙 커버리지**: §3.1 비교선택기=Task 4 / §3.2 KPI=Task 6 / §3.3 4분면=Task 7~10 / §3.3.1 라벨=Task 7(합계·끝점)·8(셀%)·9(주수)·10(수량%) / §3.4 밴드=Task 2·11 / §3.5 접이식=Task 5 / §5 검증=Task 12 / 게이트=Task 12 Step 5 — 누락 없음.
- **타입 일관성**: `filteredRows(dd)`/`crows`/`isWk`/`slw`/`wosRisks`/`gapMax`는 Task 6에서 정의, Task 7~11이 같은 `update()` 스코프에서 사용 — Task 6을 먼저 완료해야 함 (순서 고정).
- **알려진 유의점**: ① Task 7의 `getComputedStyle` 색상 추출은 다크모드 대응용 ② `--no-deploy` 없이 실행하면 즉시 push되므로 개발 중 항상 플래그 사용 ③ 기존 KPI의 `chCount/modelCount` 삭제 시 다른 참조 없는지 grep 확인(`grep -n "chCount\|modelCount" "$GEN"`).
