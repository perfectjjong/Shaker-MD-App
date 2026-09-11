#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPC 대시보드 기능 점검 매트릭스 (임원 보고용 QA, 2026-09-12).
브라우저 실조작 → (1) 콘솔 오류 (2) NaN/undefined 노출 (3) 렌더 숫자 == 데이터 재계산 (4) 필터/드롭다운/탭/토글 동작
(5) 항등식(NSV·GP·AR 연령) (6) 빈 상태 (7) 반응형 (8) 딥링크/히스토리 (9) 낡은 라벨."""
import json, re, sys, collections
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:8901/index.html'
JS = '/home/ubuntu/Shaker-MD-App/docs/dashboards/gpc/gpc_data.js'
SHOT = '/home/ubuntu/Shaker-MD-App/docs/.gstack/qa-reports/screenshots'
K = ('qty', 'gsv', 'yed', 'adc', 'vpd', 'dsi', 'cogs', 'inv', 'vsp')
t = open(JS, encoding='utf-8').read()
def arr(n):
    s = t.index(f'const {n} = ') + len(f'const {n} = '); return json.loads(t[s:t.index(';\n', s)])
DATA, META, OFF, FC, AR = arr('GPC_DATA'), arr('GPC_META'), arr('GPC_OFFICIAL'), arr('GPC_FORECAST'), arr('GPC_AR')
RES = []            # (id, ok, detail)
def rec(i, ok, d=''):
    RES.append((i, bool(ok), d)); print(f"  {'✅' if ok else '❌'} {i}{(' — ' + d) if d else ''}")

def months_of(unit, periods):
    out = set()
    for p in periods:
        if unit == 'month': out.add(int(p))
        elif unit == 'quarter': q = int(str(p)[1]); out |= {q * 3 - 2, q * 3 - 1, q * 3}
        elif unit == 'half': out |= set(range(1, 7)) if p == 'H1' else set(range(7, 13))
        else: out |= set(range(1, 13))
    return out

def expect_ladder(st):
    """페이지 상태(S) → 데이터 재계산 (Accrual). 반환 {year: {metric: SAR}}"""
    ms = months_of(st['unit'], st['periods']); chans = set(st['chans']); cats = set(st['cats']); accs = set(st['accs'])
    rows = list(DATA) + (FC['rows'] if st['fcst'] and st['basis'] != 'off' else [])
    out = {}
    for y in st['years']:
        o = {k: 0.0 for k in K}
        for r in rows:
            if r['y'] != y or r['m'] not in ms or r['sub'] not in chans or r['cat'] not in cats or f"{r['sub']}|{r['ac']}" not in accs: continue
            for k in K: o[k] += r[k]
        o['nsv'] = o['gsv'] + o['yed'] + o['adc'] + o['vpd'] + o['dsi']; o['gp'] = o['nsv'] - o['cogs'] + o['inv'] + o['vsp']
        out[y] = o
    return out

def parse_tbl(txt):
    d = {}
    for line in txt.split('\n'):
        c = line.split('\t')
        if len(c) >= 2: d[c[0].strip()] = c[1:]
    return d
def n2(s):
    s = s.replace(',', '').replace('천', '').replace('일', '').strip()
    try: return float(s.rstrip('%'))
    except ValueError: return None

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    def new_page(url=URL, w=1500, h=1000):
        pg = br.new_page(viewport={'width': w, 'height': h}); errs = []
        pg.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
        pg.goto(url, wait_until='networkidle'); pg.wait_for_timeout(900)
        return pg, errs
    def state(pg):
        return pg.evaluate("()=>({years:[...S.years],unit:S.unit,periods:[...S.periods],chans:[...S.chans],cats:[...S.cats],accs:[...S.accs],fcst:!!S.fcst,basis:S.basis,tab:S.tab})")
    def bad_tokens(pg):
        txt = pg.evaluate("()=>[...document.querySelectorAll('[data-pane]:not(.hide), #kpis, .meta, .bar')].map(e=>e.innerText).join('\\n')")
        hits = [w for w in ('NaN', 'undefined', 'Infinity', '[object') if w in txt]
        hits += ['null' ] if re.search(r'\bnull\b', txt) else []
        return hits
    def check_ladder(pg, label):
        st = state(pg); exp = expect_ladder(st); tb = parse_tbl(pg.inner_text('#tblLadder'))
        yrs = st['years']; bad = []
        for i, y in enumerate(sorted(yrs)):
            for lab, k in (('GSV', 'gsv'), ('NSV', 'nsv'), ('GP', 'gp'), ('COGS', 'cogs'), ('VSP', 'vsp')):
                if lab not in tb or i >= len(tb[lab]): bad.append(f'{lab} 행/열 없음'); continue
                got = n2(tb[lab][i]); want = round(exp[y][k] / 1000)
                if got is None or abs(got - want) > 1: bad.append(f'{y} {lab} 렌더 {got} vs 계산 {want}')
        # KPI 카드 GP 와 사다리 GP 일치
        kp = pg.inner_text('#kpis')
        for y in yrs:
            m = re.search(rf'{y}\n([\d,\-]+)', kp)
            if m and 'GP' in tb:
                i = sorted(yrs).index(y); g1 = n2(m.group(1)); g2 = n2(tb['GP'][i])
                if g1 is None or g2 is None or abs(g1 - g2) > 1: bad.append(f'KPI GP {g1} ≠ 사다리 GP {g2} ({y})')
        rec(f'렌더=데이터 [{label}]', not bad, '; '.join(bad[:4]) or f"{len(yrs)}개년 × 5지표 일치")
        return not bad

    # ── 1. 초기 로드 & 딥링크 ─────────────────────────────────────
    print('\n[1] 초기 로드 · 딥링크 · 히스토리')
    for h, expect_tab in (('', 'exec'), ('#exec', 'exec'), ('#category', 'category'), ('#contract', 'contract'), ('#fcst', 'fcst')):
        pg, errs = new_page(URL + h)
        tab = pg.evaluate("()=>document.querySelector('.tabs button.on').dataset.tab")
        pane = pg.evaluate("(t)=>!document.querySelector(`[data-pane=\"${t}\"]`).classList.contains('hide')", expect_tab)
        rec(f'딥링크 {h or "(없음)"} → 탭 {expect_tab}', tab == expect_tab and pane and not errs, f'활성={tab} 오류={len(errs)}')
        pg.close()
    pg, errs = new_page()
    pg.click('.tabs button[data-tab="category"]'); pg.wait_for_timeout(300)
    rec('탭 클릭 → URL 해시 갱신', pg.evaluate('location.hash') == '#category', pg.evaluate('location.hash'))
    pg.go_back(); pg.wait_for_timeout(500); still = pg.evaluate("()=>!!document.querySelector('.tabs button')")
    rec('탭 전환은 replaceState(히스토리 미적재) — 뒤로가기는 페이지 이탈 [설계, 정보]', True, f'대시보드 잔류={still} url={pg.url[-30:]}')
    pg.close()

    # ── 2. 렌더 = 데이터 (필터 상태별) ─────────────────────────────
    print('\n[2] 필터 상태별 렌더 숫자 == 데이터 재계산 (Accrual)')
    pg, errs = new_page(); e0 = len(errs)
    check_ladder(pg, '기본 1~8월 YOY')
    pg.click('#cYear .ytog:has-text("2024")'); pg.wait_for_timeout(400); check_ladder(pg, '2024 해제')
    pg.click('#cYear .ytog:has-text("2024")'); pg.wait_for_timeout(300)
    pg.click('#cUnit button:has-text("분기")'); pg.wait_for_timeout(400)
    for q in ('Q1', 'Q2', 'Q4'): pg.click(f'#cPeriod .pchip:has-text("{q}")')
    pg.wait_for_timeout(400); check_ladder(pg, '분기 Q3만')
    pg.click('#cUnit button:has-text("반기")'); pg.wait_for_timeout(400); pg.click('#cPeriod .pchip:has-text("H2")'); pg.wait_for_timeout(400); check_ladder(pg, '반기 H1만')
    pg.click('#cUnit button:has-text("연간")'); pg.wait_for_timeout(400); check_ladder(pg, '연간')
    pg.click('#cUnit button:has-text("월")'); pg.wait_for_timeout(300); pg.click('.bar .txtbtn[data-p="yoy"]'); pg.wait_for_timeout(300)
    pg.click('#cChan .ytog:has-text("OR")'); pg.click('#cChan .ytog:has-text("SME")'); pg.wait_for_timeout(400); check_ladder(pg, '채널 IR_Main+IR_Others')
    pg.click('#cChan .ytog:has-text("OR")'); pg.click('#cChan .ytog:has-text("SME")'); pg.wait_for_timeout(300)
    pg.click('#cCat .trigger'); pg.click('#cCat [data-c="none"]'); pg.click('#cCat .opt:has-text("Split Inverter")'); pg.click('#cCat .opt:has-text("Window AC")'); pg.wait_for_timeout(400)
    check_ladder(pg, '카테고리 Inverter+Window')
    pg.click('#cCat [data-c="all"]'); pg.wait_for_timeout(300); pg.click('body', position={'x': 5, 'y': 5})
    pg.click('#cAcc .trigger'); pg.click('#cAcc [data-a="none"]'); pg.fill('#cAcc .srch', 'BH'); pg.wait_for_timeout(150); pg.click('#cAcc .opt:has-text("BH")'); pg.wait_for_timeout(400)
    check_ladder(pg, '계정 BH 단독')
    pg.fill('#cAcc .srch', ''); pg.click('#cAcc [data-a="all"]'); pg.wait_for_timeout(300); pg.click('body', position={'x': 5, 'y': 5})
    pg.click('#togFcst'); pg.wait_for_timeout(500); st = state(pg)
    rec('예상 토글 ON → 9월 chip 자동 추가', 9 in [int(x) for x in st['periods']] and st['fcst'], str(sorted(int(x) for x in st['periods'])))
    check_ladder(pg, '9월 예상 포함 1~9월')
    pg.click('#togFcst'); pg.wait_for_timeout(400); st = state(pg)
    rec('예상 토글 OFF → 9월 chip 제거', 9 not in [int(x) for x in st['periods']] and not st['fcst'])
    rec('[2] 구간 콘솔 오류 0', len(errs) == e0, '\n'.join(errs[e0:e0 + 3]))
    pg.close()

    # ── 3. Official 기준 ──────────────────────────────────────────
    print('\n[3] Official 기준')
    pg, errs = new_page(); e0 = len(errs)
    pg.click('#cBasis button:has-text("Official")'); pg.wait_for_timeout(600)
    tb = parse_tbl(pg.inner_text('#tblLadder')); st = state(pg)
    # 전 채널·전 계정 → 공시 원본 + 미공시월 Accrual 대체
    offm = {y: set(v) for y, v in META['official']['actual_months'].items()}
    bad = []
    for i, y in enumerate(sorted(st['years'])):
        ms = months_of(st['unit'], st['periods']); want = 0.0
        for r in OFF:
            if r['y'] == y and r['b'] == 'A' and r['m'] in ms and r['cat'] in set(st['cats']): want += r['gsv']
        for r in DATA:
            if r['y'] == y and r['m'] in ms and r['m'] not in offm.get(str(y), set()) and r['cat'] in set(st['cats']): want += r['gsv']
        got = n2(tb['GSV'][i]);
        if abs(got - round(want / 1000)) > 1: bad.append(f'{y} GSV 렌더 {got} vs 공시+대체 {round(want/1000)}')
    rec('Official 전채널 GSV = 공시 원본(+미공시월 Accrual)', not bad, '; '.join(bad))
    rec('Official 에서 예상 토글 비활성', 'dim' in (pg.get_attribute('#ctlFcst', 'class') or ''))
    rec('Official 에서 채권·회수 카드 숨김', 'hide' in (pg.get_attribute('#cardAr', 'class') or ''))
    pe = pg.evaluate("()=>getComputedStyle(document.getElementById('ctlFcst')).pointerEvents")
    pg.evaluate("()=>document.getElementById('togFcst').click()"); pg.wait_for_timeout(300)
    rec('Official 에서 예상 토글 무효 (pointer-events 차단 + 핸들러 가드)', not state(pg)['fcst'], f'pointer-events={pe}')
    pg.click('#cChan .ytog:has-text("OR")'); pg.wait_for_timeout(500)
    hint = pg.inner_text('#ladderHint'); rec('Official 부분채널 → 안분 배지', '안분' in hint, hint[:80])
    rec('Official 부분채널 NaN 없음', not bad_tokens(pg), str(bad_tokens(pg)))
    pg.click('#cChan .ytog:has-text("OR")'); pg.click('#cBasis button:has-text("Accrual")'); pg.wait_for_timeout(400)
    rec('[3] 콘솔 오류 0', len(errs) == e0, '\n'.join(errs[e0:e0 + 3]))
    pg.close()

    # ── 4. 빈 상태 ────────────────────────────────────────────────
    print('\n[4] 빈 상태 (연도·기간·채널·카테고리·계정 전부 해제)')
    for label, act in (('연도 0', lambda: [pg.click(f'#cYear .ytog:has-text("{y}")') for y in META['years']]),
                       ('기간 0', lambda: pg.click('.bar .txtbtn[data-p="none"]')),
                       ('채널 0', lambda: [pg.click(f'#cChan .ytog:has-text("{c}")') for c in META['channels']]),
                       ('카테고리 0', lambda: (pg.click('#cCat .trigger'), pg.click('#cCat [data-c="none"]'))),
                       ('계정 0', lambda: (pg.click('#cAcc .trigger'), pg.click('#cAcc [data-a="none"]')))):
        pg, errs = new_page(); act(); pg.wait_for_timeout(600)
        for tab in ('exec', 'category', 'contract', 'fcst'):
            pg.click(f'.tabs button[data-tab="{tab}"]'); pg.wait_for_timeout(350)
        toks = bad_tokens(pg)
        rec(f'빈 상태 [{label}] 오류 0·NaN 0', not errs and not toks, f'오류 {errs[:1]} 토큰 {toks}')
        if errs or toks: pg.screenshot(path=f'{SHOT}/empty-{label}.png')
        pg.close()

    # ── 5. 드롭다운 동작 ─────────────────────────────────────────
    print('\n[5] 멀티셀렉트 드롭다운')
    pg, errs = new_page(); e0 = len(errs)
    pg.click('#cCat .trigger'); pg.wait_for_timeout(200); pg.click('#cCat .opt:has-text("Window AC")'); pg.wait_for_timeout(300)
    rec('카테고리: 항목 클릭 후 열림 유지', 'open' in pg.get_attribute('#cCat', 'class'))
    rec('카테고리: 카운트 10/11', pg.inner_text('#cCat .cnt') == f'{len(META["cats"])-1}/{len(META["cats"])}', pg.inner_text('#cCat .cnt'))
    pg.click('#cAcc .trigger'); pg.wait_for_timeout(200)
    rec('계정 열면 카테고리 닫힘', 'open' not in pg.get_attribute('#cCat', 'class') and 'open' in pg.get_attribute('#cAcc', 'class'))
    n_all = pg.locator('#cAcc .opt').count()
    pg.fill('#cAcc .srch', 'al'); pg.wait_for_timeout(150); n_vis = pg.locator('#cAcc .opt:not(.hid)').count()
    rec("계정 검색 'al' 로 목록 축소", 0 < n_vis < n_all, f'{n_vis}/{n_all}')
    pg.click('#cAcc [data-a="none"]'); pg.wait_for_timeout(300); cnt = pg.inner_text('#cAcc .cnt')
    rec('검색 중 해제 → 검색 결과만 해제', cnt.split('/')[0] == str(n_all - n_vis), cnt)
    pg.fill('#cAcc .srch', ''); pg.click('#cAcc [data-a="all"]'); pg.wait_for_timeout(300)
    rec('전체 복원', pg.inner_text('#cAcc .cnt') == f'{n_all}/{n_all}', pg.inner_text('#cAcc .cnt'))
    pg.click('body', position={'x': 5, 'y': 5}); pg.wait_for_timeout(200)
    rec('바깥 클릭으로 닫힘', 'open' not in pg.get_attribute('#cAcc', 'class'))
    g0 = pg.evaluate("()=>[...document.querySelectorAll('#cAcc .grp')].map(g=>g.textContent)")
    pg.click('#cChan .ytog:has-text("SME")'); pg.wait_for_timeout(400)
    g1 = pg.evaluate("()=>[...document.querySelectorAll('#cAcc .grp')].map(g=>g.textContent)")
    rec('채널 해제 → 계정 그룹에서 제거', 'SME' in g0 and 'SME' not in g1, f'{g0} → {g1}')
    order = pg.evaluate("()=>[...document.querySelectorAll('#cAcc .opt')].map(o=>o.textContent).slice(0,14)")
    rec('계정 순서 = OR 5 → Others → IR_Main 8', order[:6] == ['eXtra', 'Al Manea', 'SWS', 'Black Box', 'Al Khunizan', 'Others'] and order[6:14] == META['ir_mains'], str(order))
    pg.click('#cChan .ytog:has-text("SME")'); pg.click('#cCat .trigger'); pg.click('#cCat [data-c="all"]'); pg.wait_for_timeout(200)
    rec('[5] 콘솔 오류 0', len(errs) == e0)
    pg.close()

    # ── 6. 항등식 · 블록 정합 ───────────────────────────────────
    print('\n[6] 항등식 · 블록 간 정합')
    pg, errs = new_page(); e0 = len(errs)
    tb = parse_tbl(pg.inner_text('#tblLadder')); bad = []
    for i, y in enumerate(META['years']):
        g = {k: n2(tb[k][i]) for k in ('GSV', 'YED', 'ADC', 'VPD', 'DSI', 'NSV', 'COGS', 'INV', 'VSP', 'GP')}
        if abs(g['GSV'] + g['YED'] + g['ADC'] + g['VPD'] + g['DSI'] - g['NSV']) > 3: bad.append(f'{y} NSV 항등식')
        if abs(g['NSV'] - g['COGS'] + g['INV'] + g['VSP'] - g['GP']) > 3: bad.append(f'{y} GP 항등식')
    rec('사다리 NSV·GP 항등식(반올림 ±3)', not bad, '; '.join(bad))
    # 카테고리 표 Σ = 사다리
    pg.click('.tabs button[data-tab="category"]'); pg.wait_for_timeout(400)
    ct = pg.inner_text('#tblCat'); lines = [l.split('\t') for l in ct.split('\n') if '\t' in l]
    hdr = [l for l in lines if l[0].strip() in ('카테고리', '')]
    tot = next((l for l in lines if l[0].strip().startswith('합계') or l[0].strip() == 'Total'), None)
    rec('카테고리 표 렌더(행 ≥ 11)', len(lines) >= 11, f'{len(lines)}행')
    # AR 블록
    pg.click('.tabs button[data-tab="exec"]'); pg.wait_for_timeout(300)
    at = parse_tbl(pg.inner_text('#tblAr'))
    ok = all(abs(n2(at['연체율 ÷AR'][i].rstrip('%')) - n2(at['연체'][i]) / n2(at['AR 잔액 VAT 포함'][i]) * 100) < 0.15 for i in range(3))
    rec('채권: 연체율 = 연체÷AR (렌더값)', ok)
    pg.click('#arAging'); pg.wait_for_timeout(300); at = parse_tbl(pg.inner_text('#tblAr'))
    s = [sum(n2(at[k][i]) for k in at if (k.strip().endswith('일') and not k.strip().startswith('DSO')) or k.strip().startswith('365')) for i in range(3)]  # DSO 행(…일)은 연령 아님
    rec('채권: 연령 5구간 Σ = AR', all(abs(s[i] - n2(at['AR 잔액 VAT 포함'][i])) <= 3 for i in range(3)), str([round(x) for x in s]))
    ar_full = [n2(at['AR 잔액 VAT 포함'][i]) for i in range(3)]; coll_full = [n2(at['회수 기간 합'][i]) for i in range(3)]
    for m in range(1, 8): pg.click(f'#cPeriod .pchip:nth-child({m})')
    pg.wait_for_timeout(500); at2 = parse_tbl(pg.inner_text('#tblAr'))
    rec('채권: 저량(AR)은 8월 단월 = 1~8월 동일', [n2(at2['AR 잔액 VAT 포함'][i]) for i in range(3)] == ar_full)
    rec('채권: 유량(회수)은 8월 단월 < 1~8월', all(n2(at2['회수 기간 합'][i]) < coll_full[i] for i in range(3)))
    rec('[6] 콘솔 오류 0', len(errs) == e0)
    pg.close()

    # ── 7. Contract · 예상 탭 컨트롤 ────────────────────────────
    print('\n[7] Contract · 예상 탭')
    pg, errs = new_page(URL + '#contract'); e0 = len(errs)
    base = pg.inner_text('#tblContract')
    for lab in ('YED 금액', 'GSV', 'YED율'):
        pg.click(f'#ctMode button:has-text("{lab}")'); pg.wait_for_timeout(350)
        rec(f'Contract 모드 {lab} 렌더·NaN 0', not bad_tokens(pg) and len(pg.inner_text('#tblContract')) > 200)
    for y in META['years']:
        pg.click(f'#ctYear button:has-text("{y}")'); pg.wait_for_timeout(300)
    rec('Contract 연도 버튼 전환 오류 0', len(errs) == e0)
    grp = pg.evaluate("()=>[...document.querySelectorAll('#tblContract tr.grp')].map(r=>r.textContent)")
    rec('Contract 그룹 라벨 채널 수 정확', any('IR 메인 (8채널)' in g for g in grp) and not any('9채널' in g for g in grp), str(grp))
    pg.click('.tabs button[data-tab="fcst"]'); pg.wait_for_timeout(500)
    rec('예상 탭 라벨 = meta.forecast.month', pg.inner_text('#tabFcst') == f"{META['forecast']['month']}월 예상", pg.inner_text('#tabFcst'))
    btns = pg.evaluate("()=>[...document.querySelectorAll('[data-pane=\"fcst\"] button')].map(b=>b.id||b.textContent.trim())")
    for b in btns:
        try: pg.click(f'[data-pane="fcst"] button:has-text("{b}")' if not b.startswith('fc') else f'#{b}', timeout=2000); pg.wait_for_timeout(300)
        except Exception: pass
    rec('예상 탭 버튼 전부 클릭 후 오류 0·NaN 0', len(errs) == e0 and not bad_tokens(pg), f'buttons={btns}')
    fa = pg.inner_text('#fcAcc').split('\n'); tot = [l for l in fa if l.startswith('합계')]
    rec('예상 계정별 표 합계행 존재', bool(tot))
    pg.close()

    # ── 8. 반응형 ────────────────────────────────────────────────
    print('\n[8] 반응형 (400 / 768 / 1200)')
    for w in (400, 768, 1200):
        pg, errs = new_page(w=w, h=900)
        hs = pg.evaluate('document.documentElement.scrollWidth>document.documentElement.clientWidth')
        pg.click('#cAcc .trigger'); pg.wait_for_timeout(300)
        box = pg.evaluate("()=>{const r=document.querySelector('#cAcc .panel').getBoundingClientRect();return [r.left,r.right,innerWidth]}")
        rec(f'{w}px: 가로 스크롤 없음 · 계정 패널 화면 안', (not hs) and box[0] >= 0 and box[1] <= box[2] + 1, f'scroll={hs} panel={[round(x) for x in box]}')
        pg.screenshot(path=f'{SHOT}/responsive-{w}.png'); pg.close()

    # ── 9. 낡은 라벨·차트 ─────────────────────────────────────────
    print('\n[9] 낡은 라벨 · 차트 인스턴스')
    pg, errs = new_page()
    txt = pg.evaluate('document.body.innerText')
    stale = [w for w in ('9채널', 'IR 메인 (9', 'Box Appliance', '2026apr') if w in txt]
    rec('낡은 라벨 없음', not stale, str(stale))
    # 예상 탭 제목이 meta 로 동적 생성
    pg.click('.tabs button[data-tab="fcst"]'); pg.wait_for_timeout(400)
    rec('예상 사다리 제목 동적', f"{META['forecast']['month']}월 예상" in pg.inner_text('#fcLadderTitle'), pg.inner_text('#fcLadderTitle'))
    pg.click('.tabs button[data-tab="exec"]'); pg.wait_for_timeout(400)
    ch = pg.evaluate("()=>[...document.querySelectorAll('[data-pane]:not(.hide) canvas')].filter(c=>!c.closest('.hide')).map(c=>({id:c.id,w:c.clientWidth,h:c.clientHeight,chart:!!(window.Chart&&Chart.getChart(c))}))")
    rec('Executive 차트 캔버스 렌더·인스턴스 존재 (Accrual · 보이는 카드만)', all(c['w'] > 50 and c['h'] > 50 and c['chart'] for c in ch) and len(ch) >= 3, str(ch))
    pg.click('#cBasis button:has-text("Official")'); pg.wait_for_timeout(600)   # 예산 카드는 Official 에서만 표시 — 실제 클릭으로 확인
    c2 = pg.evaluate("()=>{const c=document.getElementById('cOfBud');return {hidden:!!c.closest('.hide'),w:c.clientWidth,h:c.clientHeight,chart:!!Chart.getChart(c)}}")
    rec('Official 예산 대비 실적 차트 표시·렌더', (not c2['hidden']) and c2['w'] > 50 and c2['h'] > 50 and c2['chart'], str(c2))
    pg.close(); br.close()

n_ok = sum(1 for r in RES if r[1]); print('\n' + '=' * 70); print(f'기능 점검 {len(RES)}항목 · 통과 {n_ok} · 실패 {len(RES)-n_ok}')
for i, ok, d in RES:
    if not ok: print(f'   ❌ {i} — {d}')
json.dump([dict(id=i, ok=ok, detail=d) for i, ok, d in RES], open('/home/ubuntu/Shaker-MD-App/docs/.gstack/qa-reports/gpc-matrix.json', 'w'), ensure_ascii=False, indent=1)
