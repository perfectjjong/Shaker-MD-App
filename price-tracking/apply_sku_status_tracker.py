#!/usr/bin/env python3
"""
SKU Status Tracker 일괄 적용 스크립트
najm 채널의 구현을 나머지 8개 채널에 적용한다.
"""
import os, sys, re, subprocess

# ── najm에서 추출한 JS SEC 3 블록 ──────────────────────────────────────────────
JS_SEC3_BLOCK = r"""// ═══ SEC 3: SKU STATUS TRACKER ══════════════════════════════════════════════
// New        : 역대 첫 등장
// Reactive   : 2일+ 부재 후 복귀
// Temp OOS   : 연속 부재 1~13 스크래핑일 (재고 부족 → 영업 챌린지)
// Discontinued: 연속 부재 14+ 스크래핑일 (단종 가능성)

// 날짜별 카테고리 카운트 (런 품질 체크용)
const CAT_COUNT_BY_DATE=(()=>{
  const m={};
  DATA.forEach(r=>{if(!m[r.d])m[r.d]={};m[r.d][r.c]=(m[r.d][r.c]||0)+1;});
  return m;
})();

function checkRunQuality(date){
  const idx=DATES.indexOf(date);
  if(idx<=0)return{ok:true,reasons:[]};
  const baselineDts=DATES.slice(Math.max(0,idx-14),idx);
  const dayCounts=CAT_COUNT_BY_DATE[date]||{};
  const totalToday=Object.values(dayCounts).reduce((a,b)=>a+b,0);
  const reasons=[];
  const baseTotals=baselineDts.map(d=>Object.values(CAT_COUNT_BY_DATE[d]||{}).reduce((a,b)=>a+b,0)).sort((a,b)=>a-b);
  if(baseTotals.length>0){
    const med=baseTotals[Math.floor(baseTotals.length/2)];
    if(med>0&&totalToday/med<0.85)reasons.push(`총 수집량 급감 (${totalToday}/${med}건, ${Math.round(totalToday/med*100)}%)`);
  }
  const knownCats=new Set();
  baselineDts.forEach(d=>Object.keys(CAT_COUNT_BY_DATE[d]||{}).forEach(c=>knownCats.add(c)));
  knownCats.forEach(cat=>{
    const hits=baselineDts.filter(d=>(CAT_COUNT_BY_DATE[d]||{})[cat]>0).length;
    if(hits>=3&&!(dayCounts[cat]>0))reasons.push(`'${cat}' 카테고리 완전 누락`);
  });
  return{ok:reasons.length===0,reasons};
}

// 탭 상태
let ACTIVE_SKU_TAB='new';

// 탭별 설명
const TAB_DESC={
  new:'역대 처음 등장한 신규 SKU',
  reactive:'단종/품절 후 재입고된 SKU — 공급 정상화 확인',
  temp_disc:'최근 1~13일 연속 부재 — 일시 재고 부족 의심 → 영업 챌린지 검토',
  disc:'14일+ 연속 부재 — 단종 가능성 높음 → 대체 모델 파악'
};

// 현재 최신 날짜의 런 품질 (전체 섹션 상단 경고용)
const _latestQ=checkRunQuality(LATEST_DATE);

function renderSkuStatus(){
  // 카운트 업데이트
  const newSkus=Object.entries(SKU_STATUS).filter(([,v])=>v.st==='new');
  const reactiveSkus=Object.entries(SKU_STATUS).filter(([,v])=>v.st==='reactive');
  const tempDiscSkus=DISC_RECORDS.filter(r=>r.st==='temp_disc');
  const discSkus=DISC_RECORDS.filter(r=>r.st==='disc');
  document.getElementById('cntNew').textContent=newSkus.length;
  document.getElementById('cntReactive').textContent=reactiveSkus.length;
  document.getElementById('cntTempDisc').textContent=tempDiscSkus.length;
  document.getElementById('cntDisc').textContent=discSkus.length;

  // 런 품질 경고 (최신 날짜 이상 시)
  const warnEl=document.getElementById('skuRunWarn');
  if(!_latestQ.ok){
    warnEl.innerHTML=`<div class="flex items-start gap-2 bg-amber-50 border border-amber-300 rounded-lg p-2.5 mb-2 text-[10px] text-amber-800"><span class="text-amber-500 text-sm leading-none mt-0.5">⚠</span><div><div class="font-bold mb-0.5">최신 수집 이상 — Temp OOS/Disc 목록 신뢰도 낮음</div>${_latestQ.reasons.map(r=>`<div>${r}</div>`).join('')}</div></div>`;
  } else { warnEl.innerHTML=''; }

  // 탭 설명
  document.getElementById('skuTabDesc').textContent=TAB_DESC[ACTIVE_SKU_TAB]||'';

  // 카드 렌더링
  const latestData=DATA.filter(r=>r.d===LATEST_DATE);
  const latestMap={};latestData.forEach(r=>latestMap[r.s]=r);

  function skuCard(r,cfg){
    const abLabel=r.ab>0?`<span class="text-[9px] font-bold px-1.5 py-0.5 rounded-full ${cfg.badgeCls}">${r.ab}일 부재</span>`:'';
    const gbLabel=r.gb>0?`<span class="text-[9px] text-gray-400">(${r.gb}일 만에 복귀)</span>`:'';
    const nameHtml=r.url?`<a href="${r.url}" target="_blank" class="text-blue-600 hover:underline">${r.n||r.s}</a>`:(r.n||r.s);
    return `<div class="border ${cfg.border} ${cfg.bg} rounded-lg p-2.5 flex justify-between items-start gap-2">
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="text-xs font-bold" style="color:${colorOf(r.b)}">${r.b||'Unknown'}</span>
          <span class="text-[10px] text-gray-400">${r.m||''}</span>
          ${abLabel}${gbLabel}
        </div>
        <div class="text-[11px] mt-0.5 truncate">${nameHtml}</div>
        <div class="text-[10px] text-gray-400 mt-0.5">${r.c||''} &middot; ${r.t?r.t.toFixed(1)+'T':''} &middot; ${r.h||''} &middot; 마지막: ${r.ls||''}</div>
      </div>
      <div class="text-sm font-bold text-gray-700 whitespace-nowrap">${fmtSAR(r.fp)} SAR</div>
    </div>`;
  }

  let html='';
  if(ACTIVE_SKU_TAB==='new'){
    const recs=newSkus.map(([sku])=>latestMap[sku]).filter(Boolean);
    html=recs.length?recs.map(r=>skuCard({...r,ab:0,gb:0,ls:LATEST_DATE},{border:'border-green-200',bg:'bg-green-50',badgeCls:''})).join(''):'<p class="text-xs text-gray-400 py-4 text-center">신규 SKU 없음</p>';
  } else if(ACTIVE_SKU_TAB==='reactive'){
    const recs=reactiveSkus.map(([sku,st])=>{const d=latestMap[sku];return d?{...d,...st}:null;}).filter(Boolean);
    html=recs.length?recs.map(r=>skuCard(r,{border:'border-blue-200',bg:'bg-blue-50',badgeCls:'bg-blue-100 text-blue-700'})).join(''):'<p class="text-xs text-gray-400 py-4 text-center">복귀 SKU 없음</p>';
  } else if(ACTIVE_SKU_TAB==='temp_disc'){
    const sorted=tempDiscSkus.slice().sort((a,b)=>b.ab-a.ab);
    html=sorted.length?sorted.map(r=>skuCard(r,{border:'border-amber-200',bg:'bg-amber-50',badgeCls:'bg-amber-100 text-amber-700'})).join(''):'<p class="text-xs text-gray-400 py-4 text-center">Temp OOS 없음</p>';
  } else {
    const sorted=discSkus.slice().sort((a,b)=>b.ab-a.ab);
    html=sorted.length?sorted.map(r=>skuCard(r,{border:'border-red-200',bg:'bg-red-50',badgeCls:'bg-red-100 text-red-700'})).join(''):'<p class="text-xs text-gray-400 py-4 text-center">Discontinued 없음</p>';
  }
  document.getElementById('skuCards').innerHTML=html;
}

// 탭 클릭 이벤트 (init에서 등록)
function initSkuTabs(){
  document.querySelectorAll('.sku-tab').forEach(btn=>{
    btn.addEventListener('click',()=>{
      document.querySelectorAll('.sku-tab').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      ACTIVE_SKU_TAB=btn.dataset.tab;
      renderSkuStatus();
    });
  });
}

"""

# ── HTML SEC 3 교체 내용 ───────────────────────────────────────────────────────
HTML_SEC3 = """<!-- SEC 3: SKU Status Tracker -->
<section id="sec-new" class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-sm font-bold text-navy-800 border-b-2 border-navy-800 pb-2 mb-3">SKU Status Tracker</h2>
  <div class="flex gap-2 mb-3 flex-wrap" id="skuTabBar">
    <button class="sku-tab active" data-tab="new">🟢 New <span id="cntNew" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-green-100 text-green-700"></span></button>
    <button class="sku-tab" data-tab="reactive">🔵 Reactive <span id="cntReactive" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-700"></span></button>
    <button class="sku-tab" data-tab="temp_disc">🟡 Temp OOS <span id="cntTempDisc" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700"></span></button>
    <button class="sku-tab" data-tab="disc">🔴 Discontinued <span id="cntDisc" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700"></span></button>
  </div>
  <div id="skuRunWarn"></div>
  <div id="skuTabDesc" class="text-[10px] text-gray-400 mb-2"></div>
  <div id="skuCards" class="space-y-2 max-h-[420px] overflow-y-auto"></div>
</section>
"""

# ── CSS 추가 ──────────────────────────────────────────────────────────────────
CSS_SKU_TAB = """.sku-tab{padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid #e5e7eb;background:#f9fafb;color:#6b7280;cursor:pointer;transition:all .15s}
.sku-tab:hover{background:#f3f4f6}
.sku-tab.active{background:#1F4E79;color:#fff;border-color:#1F4E79}"""

# ── 채널 설정 ─────────────────────────────────────────────────────────────────
CHANNELS = {
    'alkhunaizan': {
        'file': '/home/ubuntu/2026/06. Price Tracking/04. Al Khunizan/alkhunaizan_ac_html_dashboard_v2.py',
        'sku_col': 'SKU',
    },
    'almanea': {
        'file': '/home/ubuntu/2026/06. Price Tracking/05. Al Manea/almanea_ac_html_dashboard_v2.py',
        'sku_col': 'SKU',
    },
    'bh': {
        'file': '/home/ubuntu/2026/06. Price Tracking/01. BH/bh_ac_html_dashboard_v2.py',
        'sku_col': '_sku',
    },
    'binmomen': {
        'file': '/home/ubuntu/2026/06. Price Tracking/07. Bin Momen/binmomen_ac_html_dashboard.py',
        'sku_col': '_sku',
    },
    'blackbox': {
        'file': '/home/ubuntu/2026/06. Price Tracking/08. Black Box/blackbox_ac_html_dashboard_v2.py',
        'sku_col': '_sku',
    },
    'extra': {
        'file': '/home/ubuntu/2026/06. Price Tracking/00. eXtra/extra_ac_html_dashboard_v2.py',
        'sku_col': 'SKU',
    },
    'najm': {
        'file': '/home/ubuntu/2026/06. Price Tracking/03. Najm Store/najm_ac_html_dashboard.py',
        'sku_col': '_sku',
    },
    'sws': {
        'file': '/home/ubuntu/2026/06. Price Tracking/02. SWS/sws_ac_html_dashboard.py',
        'sku_col': '_sku',
    },
    'tamkeen': {
        'file': '/home/ubuntu/2026/06. Price Tracking/06. Tamkeen/tamkeen_ac_html_dashboard.py',
        'sku_col': '_sku',
    },
    'technobest': {
        'file': '/home/ubuntu/2026/06. Price Tracking/09. Techno Best/technobest_ac_html_dashboard.py',
        'sku_col': '_sku',
    },
}


def build_python_sku_block(sku_col):
    """채널별 SKU 분류 Python 코드 블록 생성"""
    return f'''
# ── SKU 4-way Status Classification ───────────────────────────────────────────
# New / Reactive / Temp OOS / Discontinued
TEMP_OOS_THRESHOLD = 14
REACTIVE_GAP_MIN   = 2

all_dates_seq = sorted([d for d in df['date_only'].unique() if pd.notna(d)])
latest_d      = all_dates_seq[-1]

sku_date_map  = df.groupby('{sku_col}')['date_only'].apply(lambda s: set(d for d in s if pd.notna(d))).to_dict()

sku_status   = {{}}
disc_records = []

for sku, dates_set in sku_date_map.items():
    first_d = min(dates_set)
    last_d  = max(dates_set)

    if last_d == latest_d:
        if first_d == latest_d:
            sku_status[sku] = {{'st':'new','ab':0,'ls':str(last_d),'fs':str(first_d),'gb':0}}
        else:
            idx = all_dates_seq.index(latest_d)
            gap = 0
            for pd_ in reversed(all_dates_seq[:idx]):
                if pd_ not in dates_set: gap += 1
                else: break
            if gap >= REACTIVE_GAP_MIN:
                sku_status[sku] = {{'st':'reactive','ab':0,'ls':str(last_d),'fs':str(first_d),'gb':gap}}
    else:
        absent_days = sum(1 for d in all_dates_seq if d > last_d)
        st = 'disc' if absent_days >= TEMP_OOS_THRESHOLD else 'temp_disc'
        sku_status[sku] = {{'st':st,'ab':absent_days,'ls':str(last_d),'fs':str(first_d),'gb':0}}
        row = df[(df['{sku_col}']==sku) & (df['date_only']==last_d)].iloc[0]
        disc_records.append({{
            's':str(sku),'st':st,'ab':absent_days,'ls':str(last_d),
            'b':safe(row.get('brand_en') if 'brand_en' in row else (row.get('Brand') if 'Brand' in row else None)),
            'n':next((str(row[k])[:70] for k in ['name_en','Name','Product_Name_EN','Product_Name','Product Name','product_name','name','title','Title','subtitle','Description','description'] if k in row.index and pd.notna(row.get(k)) and str(row.get(k)).strip()), ''),
            'm':str(sku),
            'c':safe(row.get('category_en') if 'category_en' in row else row.get('Category')),
            'h':safe(row.get('ac_type') if 'ac_type' in row else row.get('Cold_or_HC')),
            'cp':safe(row.get('compressor') if 'compressor' in row else row.get('Compressor_Type')),
            't':safe(row.get('ton') if 'ton' in row else row.get('Cooling_Capacity_Ton')),
            'fp':safe(row.get('price') if 'price' in row else row.get('Final_Sale_Price')),
            'url':next((str(row[k]) for k in ['url','URL','Product URL','Product_URL','URL_Key','product_url','link','Link'] if k in row.index and pd.notna(row.get(k)) and str(row.get(k)).strip()), ''),
        }})

'''


def apply_channel(channel, cfg):
    filepath = cfg['file']
    sku_col = cfg['sku_col']
    print(f"\n{'='*60}")
    print(f"[{channel}] 처리 시작: {filepath}")

    if not os.path.exists(filepath):
        print(f"  ❌ 파일 없음: {filepath}")
        return False

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 이미 적용됐으면 스킵
    if 'SKU 4-way Status Classification' in content:
        print(f"  ⏭  이미 SKU Status Tracker 적용됨 — 스킵")
        return True

    original = content

    # ── 변경 1: Python SKU 분류 코드 삽입 (generated_at 바로 앞) ──────────────
    py_block = build_python_sku_block(sku_col)
    target = "generated_at = datetime.now().strftime("
    if target not in content:
        print(f"  ❌ 삽입 위치('generated_at = datetime') 찾기 실패")
        return False
    content = content.replace(target, py_block + target, 1)
    print(f"  ✅ 변경1: Python SKU 분류 코드 삽입 완료")

    # ── 변경 2: JS 변수 추가 (BRAND_COLORS 줄 다음) ───────────────────────────
    brand_colors_js = "const BRAND_COLORS={json.dumps(BRAND_COLORS)};"
    if brand_colors_js not in content:
        print(f"  ❌ BRAND_COLORS JS 변수 라인 찾기 실패")
        return False
    js_vars = "\nconst SKU_STATUS={json.dumps(sku_status,ensure_ascii=False)};\nconst DISC_RECORDS={json.dumps(disc_records,ensure_ascii=False)};"
    content = content.replace(
        brand_colors_js,
        brand_colors_js + js_vars,
        1
    )
    print(f"  ✅ 변경2: JS 변수(SKU_STATUS, DISC_RECORDS) 추가 완료")

    # ── 변경 3: HTML SEC 3 섹션 교체 ─────────────────────────────────────────
    # <!-- SEC 3: New & Disc --> 로 시작하는 section 블록을 교체
    # 다음 <!-- SEC 4: 가 나오기 직전까지
    sec3_pattern = re.compile(
        r'<!-- SEC 3: New & Disc -->\n<section[^>]*>.*?</section>\n',
        re.DOTALL
    )
    if not sec3_pattern.search(content):
        print(f"  ❌ HTML SEC 3 섹션 패턴 찾기 실패")
        return False
    content = sec3_pattern.sub(HTML_SEC3, content, count=1)
    print(f"  ✅ 변경3: HTML SEC 3 섹션 교체 완료")

    # ── 변경 4: CSS 추가 ──────────────────────────────────────────────────────
    css_anchor = "#newCards span[style*=\"color\"],#discCards span[style*=\"color\"]"
    if css_anchor not in content:
        print(f"  ⚠️  CSS 앵커 찾기 실패 — CSS 추가 스킵")
    elif '.sku-tab{' not in content:
        # css_anchor 줄 찾아서 그 줄 끝에 추가
        # 실제로는 줄 끝의 중괄호 + 다음 줄에 삽입
        # 해당 줄 자체를 찾아서 교체
        css_line_pat = re.compile(r'(#newCards span\[style\*="color"\],#discCards span\[style\*="color"\][^\n]*\n)')
        m = css_line_pat.search(content)
        if m:
            content = content[:m.end()] + CSS_SKU_TAB + '\n' + content[m.end():]
            print(f"  ✅ 변경4: CSS .sku-tab 추가 완료")
        else:
            print(f"  ⚠️  CSS 라인 패턴 실패 — CSS 추가 스킵")
    else:
        print(f"  ⏭  CSS 이미 존재 — 스킵")

    # ── 변경 5: JS SEC 3 블록 교체 ────────────────────────────────────────────
    # "// ═══ SEC 3:" 또는 "// === SEC 3:" 로 시작하는 줄부터
    # "// ═══ SEC 4:" 또는 "// === SEC 4:" 바로 직전까지
    js_sec3_pat = re.compile(
        r'(// [═=]+ SEC 3:[^\n]*\n(?:.*?\n)*?)(?=// [═=]+ SEC 4:)',
        re.DOTALL
    )
    m = js_sec3_pat.search(content)
    if not m:
        print(f"  ❌ JS SEC 3 블록 패턴 찾기 실패")
        return False
    content = content[:m.start()] + JS_SEC3_BLOCK + content[m.end():]
    print(f"  ✅ 변경5: JS SEC 3 블록 교체 완료")

    # ── 변경 6: renderNewDisc 호출 → renderSkuStatus 교체 ─────────────────────
    if 'renderNewDisc(curData,prevData);' in content:
        content = content.replace('renderNewDisc(curData,prevData);', 'renderSkuStatus();')
        print(f"  ✅ 변경6: renderNewDisc → renderSkuStatus 교체 완료")
    else:
        print(f"  ⚠️  renderNewDisc(curData,prevData) 호출 없음 — 스킵")

    # ── 변경 7: initSkuTabs() 추가 ────────────────────────────────────────────
    if 'initSkuTabs();' in content:
        print(f"  ⏭  initSkuTabs() 이미 존재 — 스킵")
    else:
        # refreshGlobal(); 바로 앞에 initSkuTabs(); 삽입
        # init 함수 내 refreshGlobal() 호출 찾기
        # 패턴: 공백 + refreshGlobal(); (단독 라인)
        refresh_pat = re.compile(r'([ \t]+refreshGlobal\(\);\n)(?![\s\S]*refreshGlobal\(\);)')
        m7 = refresh_pat.search(content)
        if m7:
            indent = re.match(r'([ \t]+)', m7.group(1)).group(1)
            content = content[:m7.start()] + indent + 'initSkuTabs();\n' + content[m7.start():]
            print(f"  ✅ 변경7: initSkuTabs() 삽입 완료")
        else:
            # 마지막 refreshGlobal(); 앞에 삽입하는 fallback
            idx = content.rfind('refreshGlobal();')
            if idx != -1:
                line_start = content.rfind('\n', 0, idx) + 1
                indent = ''
                for ch in content[line_start:idx]:
                    if ch in (' ', '\t'):
                        indent += ch
                    else:
                        break
                content = content[:line_start] + indent + 'initSkuTabs();\n' + content[line_start:]
                print(f"  ✅ 변경7: initSkuTabs() 삽입 완료 (fallback)")
            else:
                print(f"  ⚠️  refreshGlobal() 호출 없음 — initSkuTabs() 삽입 스킵")

    # ── 저장 ──────────────────────────────────────────────────────────────────
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  💾 파일 저장 완료")

    # ── 문법 검증 (py compile) ─────────────────────────────────────────────────
    result = subprocess.run(
        [sys.executable, '-m', 'py_compile', filepath],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ❌ Python 문법 오류:\n{result.stderr}")
        # 롤백
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(original)
        print(f"  ↩️  원본으로 롤백 완료")
        return False

    print(f"  ✅ Python 문법 검증 통과")
    return True


def main():
    results = {}
    for channel, cfg in CHANNELS.items():
        ok = apply_channel(channel, cfg)
        results[channel] = ok

    print(f"\n{'='*60}")
    print("최종 결과 요약:")
    for ch, ok in results.items():
        status = "✅ 성공" if ok else "❌ 실패"
        print(f"  {status}  {ch}")

    failed = [ch for ch, ok in results.items() if not ok]
    if failed:
        print(f"\n⚠️  실패 채널: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"\n🎉 모든 채널 적용 성공!")


if __name__ == '__main__':
    main()
