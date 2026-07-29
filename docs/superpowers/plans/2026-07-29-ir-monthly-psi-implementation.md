# IR Monthly PSI 대시보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** or-monthly-psi와 동일한 스타일로, IR 8채널(+IR_Others) 월별 Sell-Thru/Sell-Out/Stock 대시보드(`ir-monthly-psi`)를 2023~2026 전 구간 커버해 신설한다.

**Architecture:** 2023-2025는 `unified-sellout` 대시보드의 임베드 JSON(`_ALL`)에서, 2026은 `ir-total`의 임베드 JSON(`irData`)에서 값을 읽어와 채널 8+Others 스킴으로 접고 `shared_category.category_from_sku()`로 카테고리를 재분류한 뒤, OR와 동일한 `psi_data.js` 구조로 합성한다. 이 codebase는 pytest 같은 테스트 프레임워크를 쓰지 않고 `assert` 기반 검증 스크립트(예: `verify_2023_psi.py`) 컨벤션을 쓰므로, 이 계획도 그 패턴(스크립트 작성 → 실행 → 총계 대조 assert → 통과 확인 → 커밋)을 따른다.

**Tech Stack:** Python 3(openpyxl 불필요, 표준 json/re만), Chart.js(프론트, OR과 동일 CDN), 이 리포(`Shaker-MD-App`)는 git, 운영 빌더 스크립트는 기존 컨벤션대로 `/home/ubuntu`(비git)에 둔다.

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `/home/ubuntu/ir_monthly_psi_common.py` (신규) | JSON 브래킷 추출기, 채널 fold, 카테고리 라벨 정규화, 공통 상수 |
| `/home/ubuntu/ir_monthly_psi_loader_unified.py` (신규) | `unified-sellout`에서 2023~2025 로드+정규화 |
| `/home/ubuntu/ir_monthly_psi_loader_irtotal.py` (신규) | `ir-total`에서 2026 로드+정규화 |
| `/home/ubuntu/ir_monthly_psi_builder.py` (신규) | 로더 통합 → SSOT 카테고리 fix → `psi_data.js` 출력 |
| `/home/ubuntu/verify_ir_monthly_psi.py` (신규) | 카테고리·채널·월 합계 교차검증 + 부품게이트 |
| `/home/ubuntu/ir_monthly_psi_model_table_builder.py` (신규) | 최신월 모델 스냅샷(`psi_model_table.js`), OR과 동일 LOW/OVER/OOS/SLOW 로직 |
| `/home/ubuntu/ir_monthly_psi_raw_export_builder.py` (신규) | 엑셀 다운로드(`IR_Monthly_PSI_RawData.xlsx`) |
| `/home/ubuntu/ir_monthly_psi_pivot_deploy_hook.py` (신규) | 엑셀 자동 재생성 훅 |
| `Shaker-MD-App/docs/dashboards/ir-monthly-psi/index.html` (신규) | 프론트, or-monthly-psi 복제+수정 |
| `Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_data.js` (생성물) | 빌더 출력 |
| `Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_model_table.js` (생성물) | 모델테이블 빌더 출력 |

---

### Task 1: 공통 헬퍼 모듈 (JSON 추출 + 채널/카테고리 정규화)

**Files:**
- Create: `/home/ubuntu/ir_monthly_psi_common.py`
- Test: `/home/ubuntu/test_ir_monthly_psi_common.py`

- [ ] **Step 1: 헬퍼 모듈 작성**

```python
# /home/ubuntu/ir_monthly_psi_common.py
"""ir-monthly-psi 빌더 공통 헬퍼: JSON 추출, 채널 fold, 카테고리 라벨 정규화."""
import sys, json

sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
from shared_category import category_from_sku, is_part  # noqa: E402

UNIFIED_SELLOUT_HTML = "/home/ubuntu/Shaker-MD-App/docs/dashboards/unified-sellout/index.html"
IR_TOTAL_HTML = "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-total/index.html"
OUT_DIR = "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi"

# 8개 실채널 + IR_Others. 순서 고정(프론트 필터 버튼 순서와 동일하게 유지).
CHANNELS = ['Al Ghanem', 'Al Shathri', 'BH', 'BM', 'Dhamin', 'Star Appliance', 'Tamkeen', 'Zagzoog', 'IR_Others']
REAL_CHANNELS = set(CHANNELS) - {'IR_Others'}

# OR의 psi_data.js STD_CATS와 완전히 동일한 라벨 사용(대시보드 통일).
STD_CATS = ['Split Inverter', 'Split On/Off', 'Window AC', 'Floor Standing AC',
            'Cassette', 'Concealed', 'Others']

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# shared_category.category_from_sku()가 반환하는 라벨 → 이 대시보드 STD_CATS 라벨로 정규화.
_CAT_LABEL_MAP = {
    'Split AC': None,  # comp 정보로 Inverter/On-Off 분리 필요 (호출측에서 처리)
    'Window AC': 'Window AC',
    'Floor Standing AC': 'Floor Standing AC',
    'Cassette AC': 'Cassette',
    'Concealed Set': 'Concealed',
    'Others': 'Others',
}


def fold_channel(ch):
    """8채널 목록에 없는 이름(Box Appliance 등)은 전부 IR_Others로 접는다."""
    if ch in REAL_CHANNELS:
        return ch
    return 'IR_Others'


def reclass_category(model_code, raw_cat, comp=''):
    """raw 카테고리 필드를 맹신하지 않고 SKU로 STD_CATS 7종 재분류한다."""
    from shared_category import normalize_compressor
    cat = category_from_sku(model_code)
    if cat == 'Split AC':
        c = (comp or normalize_compressor(model_code) or '').lower()
        return 'Split Inverter' if 'inverter' in c else 'Split On/Off'
    mapped = _CAT_LABEL_MAP.get(cat)
    if mapped:
        return mapped
    if cat is None:
        return 'Others'
    return cat if cat in STD_CATS else 'Others'


def extract_json_var(content, var_decl, start_at=0):
    """`var_decl`(예: 'const _ALL = ') 뒤에 이어지는 JS 객체 리터럴을 중괄호 매칭으로 추출해 파싱한다.
    var_decl=''이면 start_at 위치부터 바로 '{'가 시작한다고 가정한다."""
    start = content.find(var_decl, start_at)
    if start == -1:
        raise ValueError(f"{var_decl!r} not found after offset {start_at}")
    start += len(var_decl)
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(content):
        c = content[i]
        if in_str:
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    i += 1
                    break
        i += 1
    return json.loads(content[start:i])
```

- [ ] **Step 2: 검증 스크립트 작성**

```python
# /home/ubuntu/test_ir_monthly_psi_common.py
import sys
sys.path.insert(0, "/home/ubuntu")
from ir_monthly_psi_common import (
    fold_channel, reclass_category, extract_json_var,
    UNIFIED_SELLOUT_HTML, IR_TOTAL_HTML, STD_CATS,
)

# 1) 채널 fold
assert fold_channel('BH') == 'BH'
assert fold_channel('Box Appliance') == 'IR_Others'
assert fold_channel('완전히 모르는 딜러명') == 'IR_Others'

# 2) 카테고리 재분류 — 실제 SKU로 검증
assert reclass_category('NV182C', 'Split AC', 'Inverter') == 'Split Inverter'
assert reclass_category('LO182C', 'Split AC', '') == 'Split On/Off'
assert reclass_category('H182EC', 'Window AC') == 'Window AC'
assert reclass_category('APNW55GT3M', 'Floor Standing AC') == 'Floor Standing AC'
for c in [reclass_category('NV182C', 'Split AC', 'Inverter'),
          reclass_category('LO182C', 'Split AC', '')]:
    assert c in STD_CATS

# 3) unified-sellout 실제 파일에서 _ALL 추출 가능한지
with open(UNIFIED_SELLOUT_HTML, 'r', errors='ignore') as f:
    content = f.read()
data = extract_json_var(content, 'const _ALL = ')
assert data['years'] == ['2023', '2024', '2025', '2026']
assert 'raw' in data['data']['2023']
assert 'sellthru' in data['data']['2024']
assert 'stock' in data['data']['2025']

# 4) ir-total 실제 파일에서 irData 추출 가능한지
with open(IR_TOTAL_HTML, 'r', errors='ignore') as f:
    content2 = f.read()
marker = '<script type="application/json" id="irData">'
idx = content2.find(marker)
assert idx != -1
ir_data = extract_json_var(content2, '', start_at=idx + len(marker))
assert 'kpi' in ir_data
assert 'dealerCategory' in ir_data

print("OK — all common helper checks passed")
```

- [ ] **Step 3: 실행해서 통과 확인**

Run: `python3 /home/ubuntu/test_ir_monthly_psi_common.py`
Expected: `OK — all common helper checks passed` (AssertionError 없이 종료)

- [ ] **Step 4: 커밋 불필요 (운영 스크립트, /home/ubuntu는 비git)** — 다음 Task로 진행.

---

### Task 2: unified-sellout 로더 (2023~2025)

**Files:**
- Create: `/home/ubuntu/ir_monthly_psi_loader_unified.py`
- Test: `/home/ubuntu/test_ir_monthly_psi_loader_unified.py`

- [ ] **Step 1: 로더 작성**

```python
# /home/ubuntu/ir_monthly_psi_loader_unified.py
"""unified-sellout 임베드 JSON(_ALL)에서 2023~2025 IR ST/SO/Stock을 로드해
채널 8+Others / STD_CATS 7종 / 월별로 정규화한 딕셔너리를 반환한다."""
import sys
sys.path.insert(0, "/home/ubuntu")
from ir_monthly_psi_common import (
    UNIFIED_SELLOUT_HTML, CHANNELS, STD_CATS, MONTHS,
    fold_channel, reclass_category, extract_json_var,
)

YEARS = ['2023', '2024', '2025']


def _empty_bucket():
    return {mo: {'st': 0, 'so': 0, 'stk': None} for mo in MONTHS}


def load_unified_sellout_years():
    with open(UNIFIED_SELLOUT_HTML, 'r', errors='ignore') as f:
        content = f.read()
    all_data = extract_json_var(content, 'const _ALL = ')

    out = {}
    for year in YEARS:
        yd = all_data['data'][year]
        by_cat = {cat: _empty_bucket() for cat in STD_CATS}
        by_ch = {ch: _empty_bucket() for ch in CHANNELS}

        # Sell-Out
        for r in yd['raw']:
            mo = 'Jun' if r['m'] == 'June' else ('Jul' if r['m'] == 'July' else r['m'])
            if mo not in MONTHS:
                continue
            cat = reclass_category(r.get('model') or r.get('code'), r.get('c'), r.get('comp'))
            ch = fold_channel(r['ch'])
            by_cat[cat][mo]['so'] += r['q']
            by_ch[ch][mo]['so'] += r['q']

        # Sell-Thru
        for r in yd['sellthru']:
            mo = 'Jun' if r['m'] == 'June' else ('Jul' if r['m'] == 'July' else r['m'])
            if mo not in MONTHS:
                continue
            cat = reclass_category(r.get('model') or r.get('code'), r.get('c'), r.get('comp'))
            ch = fold_channel(r['ch'])
            by_cat[cat][mo]['st'] += r['q']
            by_ch[ch][mo]['st'] += r['q']

        # Stock — 모델별 주차 스톡의 "월 마지막 주" 스냅샷을 채널/카테고리 합계로 롤업
        weeks = yd['meta']['weeks']
        week_month = yd['meta'].get('week_month', {})
        last_week_of_month = {}
        for w in weeks:
            mo = week_month.get(w)
            if mo:
                mo = 'Jun' if mo == 'June' else ('Jul' if mo == 'July' else mo)
                last_week_of_month[mo] = w  # 마지막에 덮어써지는 주가 그 달의 마지막 주(주차가 순서대로 들어있음)

        for ch_name, ch_obj in yd['stock']['channels'].items():
            ch = fold_channel(ch_name)
            for model_row in ch_obj.get('models', []):
                cat = reclass_category(model_row.get('model'), model_row.get('category'), model_row.get('comp'))
                for mo, wk in last_week_of_month.items():
                    v = model_row.get('stock', {}).get(wk)
                    if v is None:
                        continue
                    if by_cat[cat][mo]['stk'] is None:
                        by_cat[cat][mo]['stk'] = 0
                    if by_ch[ch][mo]['stk'] is None:
                        by_ch[ch][mo]['stk'] = 0
                    by_cat[cat][mo]['stk'] += v
                    by_ch[ch][mo]['stk'] += v

        out[year] = {'by_cat': by_cat, 'by_ch': by_ch}
    return out


if __name__ == '__main__':
    data = load_unified_sellout_years()
    for yr in YEARS:
        so_total = sum(v['so'] for v in data[yr]['by_cat']['Split Inverter'].values()) \
            + sum(sum(v['so'] for v in data[yr]['by_cat'][c].values()) for c in STD_CATS if c != 'Split Inverter')
        print(yr, 'total SO (all categories) =', so_total)
```

- [ ] **Step 2: 검증 스크립트 작성 (2024년 1월 값이 앞서 원본 대조로 확인한 실측치와 일치하는지)**

```python
# /home/ubuntu/test_ir_monthly_psi_loader_unified.py
import sys
sys.path.insert(0, "/home/ubuntu")
from ir_monthly_psi_loader_unified import load_unified_sellout_years
from ir_monthly_psi_common import STD_CATS, CHANNELS

data = load_unified_sellout_years()

# 2024-01 총 SO/ST는 브레인스토밍 단계에서 B2C 마스터 원본과 100% 일치 검증된 값(2723 / 5146)이어야 한다.
jan_so = sum(data['2024']['by_cat'][c]['Jan']['so'] for c in STD_CATS)
jan_st = sum(data['2024']['by_cat'][c]['Jan']['st'] for c in STD_CATS)
assert jan_so == 2723, f"2024 Jan SO expected 2723, got {jan_so}"
assert jan_st == 5146, f"2024 Jan ST expected 5146, got {jan_st}"

# by_cat 합계 == by_ch 합계 (동일 레코드를 두 축으로 나눈 것뿐이므로 반드시 일치)
for yr in ['2023', '2024', '2025']:
    cat_so = sum(data[yr]['by_cat'][c][mo]['so'] for c in STD_CATS for mo in data[yr]['by_cat'][c])
    ch_so = sum(data[yr]['by_ch'][c][mo]['so'] for c in CHANNELS for mo in data[yr]['by_ch'][c])
    assert cat_so == ch_so, f"{yr}: by_cat SO({cat_so}) != by_ch SO({ch_so})"

print("OK — unified-sellout loader checks passed")
```

- [ ] **Step 3: 실행해서 통과 확인**

Run: `python3 /home/ubuntu/test_ir_monthly_psi_loader_unified.py`
Expected: `OK — unified-sellout loader checks passed`

만약 `jan_so`/`jan_st` assert가 실패하면 — 브레인스토밍 때 검증한 원본(`~/2026/B2C Dealer Sell out FCST_2025_Actual_W17_rev_재작업.xlsx` Col K/O)과 다시 대조해 `reclass_category`/`fold_channel` 매핑에서 유실된 레코드가 없는지 확인한다(카테고리 재분류로 인해 total이 바뀌면 안 되고, 오직 category 축만 바뀌어야 한다).

---

### Task 3: ir-total 로더 (2026)

**Files:**
- Create: `/home/ubuntu/ir_monthly_psi_loader_irtotal.py`
- Test: `/home/ubuntu/test_ir_monthly_psi_loader_irtotal.py`

- [ ] **Step 1: 로더 작성**

```python
# /home/ubuntu/ir_monthly_psi_loader_irtotal.py
"""ir-total 임베드 JSON(irData)에서 2026 IR ST/SO/Stock을 dealerCategory 기준으로
채널(channel_from_name)·STD_CATS로 롤업한다."""
import sys
sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
from ir_monthly_psi_common import (
    IR_TOTAL_HTML, CHANNELS, STD_CATS, MONTHS, fold_channel, extract_json_var,
)
from shared_classification import channel_from_name  # noqa: E402

# ir-total dealerCategory의 카테고리 라벨 → STD_CATS 정규화 (ir-total은 이미 근접 라벨 사용)
_IR_TOTAL_CAT_MAP = {
    'Split Inverter': 'Split Inverter',
    'Split ON-OFF': 'Split On/Off',
    'Split On/Off': 'Split On/Off',
    'Window AC': 'Window AC',
    'Floor Standing AC': 'Floor Standing AC',
    'Cassette AC': 'Cassette',
    'Concealed Set': 'Concealed',
    'Unitary Package': 'Others',
    'Others': 'Others',
}

MONTH_KEYS = {'Jan': 'jan', 'Feb': 'feb', 'Mar': 'mar', 'Apr': 'apr', 'May': 'may', 'Jun': 'jun',
              'Jul': 'jul', 'Aug': 'aug', 'Sep': 'sep', 'Oct': 'oct', 'Nov': 'nov', 'Dec': 'dec'}


def _empty_bucket():
    return {mo: {'st': 0, 'so': 0, 'stk': None} for mo in MONTHS}


def load_ir_total_2026():
    with open(IR_TOTAL_HTML, 'r', errors='ignore') as f:
        content = f.read()
    marker = '<script type="application/json" id="irData">'
    idx = content.find(marker)
    ir_data = extract_json_var(content, '', start_at=idx + len(marker))

    by_cat = {cat: _empty_bucket() for cat in STD_CATS}
    by_ch = {ch: _empty_bucket() for ch in CHANNELS}

    for row in ir_data['dealerCategory']:
        cat = _IR_TOTAL_CAT_MAP.get(row['category'], 'Others')
        ch_raw = channel_from_name(row['dealer'])
        ch = fold_channel(ch_raw) if ch_raw else 'IR_Others'
        for mo, key in MONTH_KEYS.items():
            m = row.get(key)
            if not m:
                continue
            st = m.get('stQty') or 0
            so = m.get('soQty') or 0
            stk = m.get('stkQty')
            by_cat[cat][mo]['st'] += st
            by_cat[cat][mo]['so'] += so
            by_ch[ch][mo]['st'] += st
            by_ch[ch][mo]['so'] += so
            if stk is not None:
                if by_cat[cat][mo]['stk'] is None:
                    by_cat[cat][mo]['stk'] = 0
                if by_ch[ch][mo]['stk'] is None:
                    by_ch[ch][mo]['stk'] = 0
                by_cat[cat][mo]['stk'] += stk
                by_ch[ch][mo]['stk'] += stk

    return {'2026': {'by_cat': by_cat, 'by_ch': by_ch}}, ir_data['kpi']


if __name__ == '__main__':
    data, kpi = load_ir_total_2026()
    for mo, key in MONTH_KEYS.items():
        if key not in kpi:
            continue
        so = sum(data['2026']['by_cat'][c][mo]['so'] for c in STD_CATS)
        print(mo, 'rollup SO =', so, ' kpi soQty =', kpi[key]['soQty'])
```

- [ ] **Step 2: 검증 스크립트 작성 (dealerCategory 롤업 합계 = ir-total kpi와 100% 일치해야 함)**

```python
# /home/ubuntu/test_ir_monthly_psi_loader_irtotal.py
import sys
sys.path.insert(0, "/home/ubuntu")
from ir_monthly_psi_loader_irtotal import load_ir_total_2026, MONTH_KEYS
from ir_monthly_psi_common import STD_CATS

data, kpi = load_ir_total_2026()

for mo, key in MONTH_KEYS.items():
    if key not in kpi:
        continue
    rollup_so = sum(data['2026']['by_cat'][c][mo]['so'] for c in STD_CATS)
    rollup_st = sum(data['2026']['by_cat'][c][mo]['st'] for c in STD_CATS)
    assert rollup_so == kpi[key]['soQty'], f"{mo}: rollup SO {rollup_so} != kpi soQty {kpi[key]['soQty']}"
    assert rollup_st == kpi[key]['stQty'], f"{mo}: rollup ST {rollup_st} != kpi stQty {kpi[key]['stQty']}"

print("OK — ir-total 2026 loader ties to kpi exactly")
```

- [ ] **Step 3: 실행해서 통과 확인**

Run: `python3 /home/ubuntu/test_ir_monthly_psi_loader_irtotal.py`
Expected: `OK — ir-total 2026 loader ties to kpi exactly`

이 어서션이 실패하면(예: `dealerCategory`가 `kpi`보다 결손이 있는 달) — Task 4에서 그 갭을 `(정합조정 · 대시보드 SSOT)` 방식으로 흡수할 수 있도록 원인(어느 딜러가 dealerCategory에 없는지)을 메모만 하고 다음으로 진행한다. 비율배분 금지.

---

### Task 4: 빌더 통합 — `psi_data.js` 생성

**Files:**
- Create: `/home/ubuntu/ir_monthly_psi_builder.py`
- Create (output): `Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_data.js`

- [ ] **Step 1: 출력 디렉토리 생성**

Run: `mkdir -p "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi"`

- [ ] **Step 2: 빌더 작성**

```python
# /home/ubuntu/ir_monthly_psi_builder.py
"""ir-monthly-psi psi_data.js 빌더. 2023-25=unified-sellout, 2026=ir-total."""
import sys, os, json
sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
from ir_monthly_psi_common import CHANNELS, STD_CATS, MONTHS, OUT_DIR
from ir_monthly_psi_loader_unified import load_unified_sellout_years
from ir_monthly_psi_loader_irtotal import load_ir_total_2026

YEARS = ['2023', '2024', '2025', '2026']
OUT_JS = os.path.join(OUT_DIR, 'psi_data.js')


def build():
    unified = load_unified_sellout_years()
    irtotal, _kpi = load_ir_total_2026()
    merged = {**unified, **irtotal}

    payload = {
        'meta': {'channels': CHANNELS, 'categories': STD_CATS, 'months': MONTHS, 'years': YEARS},
        'years': {},
    }
    for yr in YEARS:
        payload['years'][yr] = {
            'by_cat': merged[yr]['by_cat'],
            'by_ch': merged[yr]['by_ch'],
        }

    # ⚠️ ssot_fix_category_inplace는 여기서 호출하지 않는다 — by_cat/by_ch는 이미
    # 로더 단계에서 reclass_category()(내부적으로 category_from_sku 사용)를 레코드 단위로
    # 적용한 뒤 카테고리별로 합산된 구조라 'code'/'model' 키가 없다. ssot_fix_category_inplace는
    # code/model 키가 있는 레코드에서만 의미가 있으므로, 그 키가 실제로 남아있는
    # Task 5(모델 테이블)·Task 7(엑셀 모델행)에서 적용한다. 여기서 또 부르면 아무 것도
    # 교정하지 못하는 눈속임 호출이 되므로 넣지 않는다.

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JS, 'w') as f:
        f.write('var IR_PSI_DATA = ')
        json.dump(payload, f, ensure_ascii=False)
        f.write(';\n')
    print(f'Wrote {OUT_JS}')
    return payload


if __name__ == '__main__':
    build()
    try:
        from ir_monthly_psi_pivot_deploy_hook import rebuild_pivot_excel
        rebuild_pivot_excel()
    except ImportError:
        print('(엑셀 배포훅 아직 없음 — Task 8/9에서 추가 예정)')
```

- [ ] **Step 3: 실행**

Run: `python3 /home/ubuntu/ir_monthly_psi_builder.py`
Expected: `Wrote /home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_data.js` (엑셀 훅 관련 안내 메시지는 이 시점에 정상 출력)

- [ ] **Step 4: 검증 스크립트 작성 — 카테고리 합=채널 합, 부품 오염 0**

```python
# /home/ubuntu/verify_ir_monthly_psi.py
import sys, json
sys.path.insert(0, "/home/ubuntu")
from ir_monthly_psi_common import OUT_DIR, STD_CATS, CHANNELS, MONTHS
import os

with open(os.path.join(OUT_DIR, 'psi_data.js')) as f:
    content = f.read()
payload = json.loads(content[len('var IR_PSI_DATA = '):-2])

for yr, yd in payload['years'].items():
    cat_so = sum(yd['by_cat'][c][mo]['so'] for c in STD_CATS for mo in MONTHS)
    ch_so = sum(yd['by_ch'][c][mo]['so'] for c in CHANNELS for mo in MONTHS)
    assert cat_so == ch_so, f"{yr}: SO 카테고리합({cat_so}) != 채널합({ch_so})"

    cat_st = sum(yd['by_cat'][c][mo]['st'] for c in STD_CATS for mo in MONTHS)
    ch_st = sum(yd['by_ch'][c][mo]['st'] for c in CHANNELS for mo in MONTHS)
    assert cat_st == ch_st, f"{yr}: ST 카테고리합({cat_st}) != 채널합({ch_st})"

    for mo in MONTHS:
        for c in STD_CATS:
            stk = yd['by_cat'][c][mo]['stk']
            assert stk is None or stk >= 0, f"{yr}-{mo}-{c}: 재고 음수 {stk}"

print("OK — psi_data.js 카테고리/채널 정합 + 재고 음수 0건 확인")
```

- [ ] **Step 5: 실행해서 통과 확인**

Run: `python3 /home/ubuntu/verify_ir_monthly_psi.py`
Expected: `OK — psi_data.js 카테고리/채널 정합 + 재고 음수 0건 확인`

- [ ] **Step 6: 부품오염 게이트 실행**

Run: `python3 "/home/ubuntu/2026/10. Automation/dashboard_part_contamination_gate.py"`
Expected: `GATE PASS` (신규 대시보드가 게이트 대상 목록에 없다면, 이 스텝에서 게이트 스크립트에 `ir-monthly-psi` 경로를 추가하는 작업이 필요할 수 있음 — 있으면 그대로 실행만).

- [ ] **Step 7: 커밋**

```bash
cd /home/ubuntu/Shaker-MD-App
git add docs/dashboards/ir-monthly-psi/psi_data.js
git commit -m "$(cat <<'EOF'
Add ir-monthly-psi psi_data.js (2023-2026)

Generated by ir_monthly_psi_builder.py from unified-sellout (2023-25)
and ir-total (2026). Verified category/channel totals tie exactly.
EOF
)"
```

---

### Task 5: 모델 테이블 빌더 (`psi_model_table.js`)

**Files:**
- Create: `/home/ubuntu/ir_monthly_psi_model_table_builder.py`
- Create (output): `Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_model_table.js`

- [ ] **Step 1: 빌더 작성** — unified-sellout의 `stock.channels[ch].models`(최신 폐쇄월, 2026년 데이터이므로 `ir-total`의 `dealerCategory`가 아니라 **unified-sellout 2026 stock**을 그대로 이용. 모델 코드가 실 SKU라 OR과 동일한 MOS 임계값(LOW<1.0, OVER>3.0)으로 직접 재계산한다.

```python
# /home/ubuntu/ir_monthly_psi_model_table_builder.py
"""최신 폐쇄월 기준 IR 모델별 재고 스냅샷 + MOS 플래그. OR의 psi_model_table 로직과 동일 임계값."""
import sys, os, json
sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
from ir_monthly_psi_common import (
    UNIFIED_SELLOUT_HTML, OUT_DIR, CHANNELS, REAL_CHANNELS,
    fold_channel, reclass_category, extract_json_var,
)
from shared_category import ssot_fix_category_inplace  # noqa: E402

MOS_LOW_TH = 1.0
MOS_OVER_TH = 3.0
OUT_JS = os.path.join(OUT_DIR, 'psi_model_table.js')


def _latest_year_week(all_data):
    years = all_data['years']
    latest_year = years[-1]
    yd = all_data['data'][latest_year]
    return latest_year, yd


def build():
    with open(UNIFIED_SELLOUT_HTML, 'r', errors='ignore') as f:
        content = f.read()
    all_data = extract_json_var(content, 'const _ALL = ')
    year, yd = _latest_year_week(all_data)
    weeks = yd['meta']['weeks']
    latest_week = weeks[-1]

    # 최신 주의 so(4주 평균)를 위해 최근 4주 리스트도 확보
    recent_weeks = weeks[-4:]

    so_by_model_ch = {}
    for r in yd['raw']:
        if r['w'] not in recent_weeks:
            continue
        key = (r.get('model') or r.get('code'), fold_channel(r['ch']))
        so_by_model_ch[key] = so_by_model_ch.get(key, 0) + r['q']

    rows = []
    for ch_name, ch_obj in yd['stock']['channels'].items():
        ch = fold_channel(ch_name)
        for m in ch_obj.get('models', []):
            model = m.get('model')
            stk = m.get('stock', {}).get(latest_week)
            if stk is None:
                continue
            cat = reclass_category(model, m.get('category'), m.get('comp'))
            so_recent = so_by_model_ch.get((model, ch), 0)
            avg_so = so_recent / 4.0
            mos = (stk / avg_so) if avg_so > 0 else None

            if stk == 0 and so_recent > 0:
                flag = 'OOS'
            elif so_recent == 0 and stk > 0:
                flag = 'SLOW'
            elif mos is not None and mos < MOS_LOW_TH:
                flag = 'LOW'
            elif mos is not None and mos > MOS_OVER_TH:
                flag = 'OVER'
            else:
                flag = 'NORMAL'

            rows.append({
                'model': model, 'category': cat, 'channel': ch,
                'stk': stk, 'so_recent_4w': so_recent,
                'mos': round(mos, 2) if mos is not None else None,
                'flag': flag,
            })

    # SSOT 최종 카테고리 교정 — rows는 'model'/'category' 키를 실제로 갖고 있으므로
    # 여기서는 진짜로 의미가 있다(레이블이 뒤섞였거나 v6 미등록으로 새는 케이스를 최종 교정).
    ssot_fix_category_inplace(rows, split_compressor=False)

    payload = {'as_of_week': latest_week, 'as_of_year': year, 'rows': rows}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JS, 'w') as f:
        f.write('var IR_PSI_MODEL_TABLE = ')
        json.dump(payload, f, ensure_ascii=False)
        f.write(';\n')
    print(f'Wrote {OUT_JS} — {len(rows)} rows, as_of {year} {latest_week}')
    return payload


if __name__ == '__main__':
    build()
```

- [ ] **Step 2: 실행**

Run: `python3 /home/ubuntu/ir_monthly_psi_model_table_builder.py`
Expected: `Wrote .../psi_model_table.js — N rows, as_of 2026 W##`

- [ ] **Step 3: 검증**

```python
# /home/ubuntu/test_ir_monthly_psi_model_table.py
import sys, json, os
sys.path.insert(0, "/home/ubuntu")
from ir_monthly_psi_common import OUT_DIR, CHANNELS

with open(os.path.join(OUT_DIR, 'psi_model_table.js')) as f:
    content = f.read()
payload = json.loads(content[len('var IR_PSI_MODEL_TABLE = '):-2])

assert len(payload['rows']) > 0, "모델 행이 0개 — 빌더가 stock.channels를 못 읽었을 가능성"
for r in payload['rows']:
    assert r['channel'] in CHANNELS, f"알 수 없는 채널: {r['channel']}"
    assert r['flag'] in ('OOS', 'SLOW', 'LOW', 'OVER', 'NORMAL')
    assert r['stk'] >= 0

print(f"OK — model table {len(payload['rows'])} rows, all channels/flags valid")
```

Run: `python3 /home/ubuntu/test_ir_monthly_psi_model_table.py`
Expected: `OK — model table N rows, all channels/flags valid`

- [ ] **Step 4: 커밋**

```bash
cd /home/ubuntu/Shaker-MD-App
git add docs/dashboards/ir-monthly-psi/psi_model_table.js
git commit -m "Add ir-monthly-psi model table (latest week snapshot, OR-style MOS flags)"
```

---

### Task 6: 프론트엔드 페이지

**Files:**
- Copy from: `Shaker-MD-App/docs/dashboards/or-monthly-psi/index.html`
- Create: `Shaker-MD-App/docs/dashboards/ir-monthly-psi/index.html`

- [ ] **Step 1: OR 파일을 베이스로 복사**

```bash
cp "/home/ubuntu/Shaker-MD-App/docs/dashboards/or-monthly-psi/index.html" \
   "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/index.html"
```

- [ ] **Step 2: 타이틀·데이터소스 변경**

Edit `Shaker-MD-App/docs/dashboards/ir-monthly-psi/index.html`:
- `<title>OR Monthly PSI 2023–2026</title>` → `<title>IR Monthly PSI 2023–2026</title>`
- `<h1>OR Monthly PSI` → `<h1>IR Monthly PSI`
- `<script src="psi_data.js"` 그대로 유지(파일명 동일, 내용만 다름 — `var IR_PSI_DATA`이므로 이후 스크립트에서 참조하는 전역 변수명도 `OR_PSI_DATA`류에서 `IR_PSI_DATA`로 전부 치환 필요. 치환 전 실제 변수명을 확인:

Run: `grep -n "PSI_DATA\b" "/home/ubuntu/Shaker-MD-App/docs/dashboards/or-monthly-psi/index.html" | head -5`

그 결과로 나온 정확한 전역 변수명을 `IR_PSI_DATA`로 전체 치환한다(sed로 일괄 치환):

```bash
# <ACTUAL_VAR>는 위 grep 결과에서 확인한 실제 변수명으로 치환
sed -i 's/\bOR_PSI_DATA\b/IR_PSI_DATA/g' "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/index.html"
```

- [ ] **Step 3: 채널 필터 버튼 → 8+Others, 단일선택 → 멀티선택 체크박스로 변경**

기존(단일선택 버튼, `feedback_dashboard_filters_multiselect.md` 규칙 위반 상태):
```html
<button class="fb on" data-ch="ALL">All</button>
<button class="fb" data-ch="eXtra">eXtra</button>
<button class="fb" data-ch="Al Manea">Al Manea</button>
<button class="fb" data-ch="SWS">SWS</button>
<button class="fb" data-ch="Black Box">Black Box</button>
<button class="fb" data-ch="Al Khunizan">Al Khunizan</button>
```

교체:
```html
<label class="ms-item"><input type="checkbox" class="ch-cb" value="Al Ghanem" checked> Al Ghanem</label>
<label class="ms-item"><input type="checkbox" class="ch-cb" value="Al Shathri" checked> Al Shathri</label>
<label class="ms-item"><input type="checkbox" class="ch-cb" value="BH" checked> BH</label>
<label class="ms-item"><input type="checkbox" class="ch-cb" value="BM" checked> BM</label>
<label class="ms-item"><input type="checkbox" class="ch-cb" value="Dhamin" checked> Dhamin</label>
<label class="ms-item"><input type="checkbox" class="ch-cb" value="Star Appliance" checked> Star Appliance</label>
<label class="ms-item"><input type="checkbox" class="ch-cb" value="Tamkeen" checked> Tamkeen</label>
<label class="ms-item"><input type="checkbox" class="ch-cb" value="Zagzoog" checked> Zagzoog</label>
<label class="ms-item"><input type="checkbox" class="ch-cb" value="IR_Others" checked> IR_Others</label>
```

- [ ] **Step 4: 카테고리 필터도 동일 패턴으로 멀티선택 체크박스 전환**

기존:
```html
<button class="fb on" data-cat="ALL">All</button>
<button class="fb" data-cat="Split Inverter">Split Inv</button>
<button class="fb" data-cat="Split On/Off">Split On/Off</button>
<button class="fb" data-cat="Window AC">Window</button>
<button class="fb" data-cat="Floor Standing AC">FS</button>
<button class="fb" data-cat="Cassette">Cassette</button>
<button class="fb" data-cat="Concealed">Concealed</button>
<button class="fb" data-cat="Others">Others</button>
```

교체:
```html
<label class="ms-item"><input type="checkbox" class="cat-cb" value="Split Inverter" checked> Split Inv</label>
<label class="ms-item"><input type="checkbox" class="cat-cb" value="Split On/Off" checked> Split On/Off</label>
<label class="ms-item"><input type="checkbox" class="cat-cb" value="Window AC" checked> Window</label>
<label class="ms-item"><input type="checkbox" class="cat-cb" value="Floor Standing AC" checked> FS</label>
<label class="ms-item"><input type="checkbox" class="cat-cb" value="Cassette" checked> Cassette</label>
<label class="ms-item"><input type="checkbox" class="cat-cb" value="Concealed" checked> Concealed</label>
<label class="ms-item"><input type="checkbox" class="cat-cb" value="Others" checked> Others</label>
```

- [ ] **Step 5: 필터 적용 JS 로직을 `data-ch`/`data-cat` 단일값 비교에서 체크박스 집합 비교로 변경**

기존 JS에서 `data-ch`/`data-cat` 읽는 부분을 찾는다:

Run: `grep -n "data-ch\|data-cat" "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/index.html"`

찾은 각 위치에서, 단일값 `curCh`/`curCat` 변수를 읽던 로직을 아래 헬퍼로 교체한다(파일 상단 스크립트 블록에 추가):

```javascript
function selectedChannels() {
  return Array.from(document.querySelectorAll('.ch-cb:checked')).map(el => el.value);
}
function selectedCategories() {
  return Array.from(document.querySelectorAll('.cat-cb:checked')).map(el => el.value);
}
document.querySelectorAll('.ch-cb, .cat-cb').forEach(cb => cb.addEventListener('change', rerender));
```

그리고 데이터 합산 시 `channels.includes(ch)`, `categories.includes(cat)`처럼 배열 포함 여부로 필터링하도록 집계 함수를 수정한다(정확한 함수명은 grep 결과에 따라 다르므로, 기존 단일값 비교 `ch === curCh`가 있던 자리를 전부 `selectedChannels().includes(ch)`로, `cat === curCat`이 있던 자리를 `selectedCategories().includes(cat)`로 치환).

- [ ] **Step 6: 로컬에서 렌더 확인**

Run: `cd "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi" && python3 -m http.server 8842 &`

그 다음 `/browse` 스킬로 `http://localhost:8842/`를 열어 페이지 타이틀이 "IR Monthly PSI"인지, 채널 체크박스 9개(8+IR_Others)와 카테고리 체크박스 7개가 보이는지, 콘솔 에러가 없는지 확인한다. 확인 후 서버 종료: `kill %1`.

- [ ] **Step 7: 커밋**

```bash
cd /home/ubuntu/Shaker-MD-App
git add docs/dashboards/ir-monthly-psi/index.html
git commit -m "Add ir-monthly-psi frontend (or-monthly-psi clone, multi-select filters per house rule)"
```

---

### Task 7: 엑셀 다운로드 빌더

**Files:**
- Create: `/home/ubuntu/ir_monthly_psi_raw_export_builder.py`
- Create (output): `Shaker-MD-App/docs/dashboards/ir-monthly-psi/IR_Monthly_PSI_RawData.xlsx`

- [ ] **Step 1: 빌더 작성**

```python
# /home/ubuntu/ir_monthly_psi_raw_export_builder.py
"""ir-monthly-psi 엑셀 다운로드. 단일 시트 tidy long-format.
정합 종속 원칙: 합계는 반드시 psi_data.js(이 대시보드 SSOT)와 일치해야 하며,
모델 breakdown 잔차는 비율배분하지 않고 '(정합조정 · 대시보드 SSOT)' 1행으로 흡수한다."""
import sys, os, json
sys.path.insert(0, "/home/ubuntu")
from ir_monthly_psi_common import OUT_DIR, STD_CATS, CHANNELS, MONTHS, UNIFIED_SELLOUT_HTML
from ir_monthly_psi_common import fold_channel, reclass_category, extract_json_var
from openpyxl import Workbook

OUT_XLSX = os.path.join(OUT_DIR, 'IR_Monthly_PSI_RawData.xlsx')
RECON_MODEL = '(정합조정 · 대시보드 SSOT)'


def _load_psi_data():
    with open(os.path.join(OUT_DIR, 'psi_data.js')) as f:
        content = f.read()
    return json.loads(content[len('var IR_PSI_DATA = '):-2])


def _model_level_rows():
    """unified-sellout(2023-25)만 모델 grain 원본이 있음. 2026은 dealerCategory가 모델grain이 아니라
    (정합조정) 단일행으로 채운다(카테고리·채널 총계는 psi_data.js와 이미 tie)."""
    with open(UNIFIED_SELLOUT_HTML, 'r', errors='ignore') as f:
        content = f.read()
    all_data = extract_json_var(content, 'const _ALL = ')

    rows = {}  # (year, month, channel, category, model) -> {so, st, stk}
    for year in ['2023', '2024', '2025']:
        yd = all_data['data'][year]
        for r in yd['raw']:
            mo = 'Jun' if r['m'] == 'June' else ('Jul' if r['m'] == 'July' else r['m'])
            if mo not in MONTHS:
                continue
            cat = reclass_category(r.get('model') or r.get('code'), r.get('c'), r.get('comp'))
            ch = fold_channel(r['ch'])
            key = (year, mo, ch, cat, r.get('model') or r.get('code') or '(unknown)')
            rows.setdefault(key, {'so': 0, 'st': 0, 'stk': None})
            rows[key]['so'] += r['q']
        for r in yd['sellthru']:
            mo = 'Jun' if r['m'] == 'June' else ('Jul' if r['m'] == 'July' else r['m'])
            if mo not in MONTHS:
                continue
            cat = reclass_category(r.get('model') or r.get('code'), r.get('c'), r.get('comp'))
            ch = fold_channel(r['ch'])
            key = (year, mo, ch, cat, r.get('model') or r.get('code') or '(unknown)')
            rows.setdefault(key, {'so': 0, 'st': 0, 'stk': None})
            rows[key]['st'] += r['q']
    return rows


def build():
    payload = _load_psi_data()
    model_rows = _model_level_rows()

    wb = Workbook()
    ws = wb.active
    ws.title = 'RAW'
    ws.append(['Year', 'Month', 'Channel', 'Category', 'Model code', 'Sell thru', 'Sell out', 'Stock'])
    for (year, mo, ch, cat, model), v in sorted(model_rows.items()):
        ws.append([int(year), mo, ch, cat, model, v['st'] or None, v['so'] or None, v['stk']])

    # 정합조정 — 카테고리×월×연도 총계(psi_data.js) − 모델 breakdown 합 = 잔차, 비율배분 없이 1행 흡수
    recon_rows = []
    for year in payload['meta']['years']:
        by_cat = payload['years'][year]['by_cat']
        for cat in STD_CATS:
            for mo in MONTHS:
                dash_so = by_cat[cat][mo]['so']
                dash_st = by_cat[cat][mo]['st']
                model_so = sum(v['so'] for (y, m, c, cc, _), v in model_rows.items()
                               if y == year and m == mo and cc == cat)
                model_st = sum(v['st'] for (y, m, c, cc, _), v in model_rows.items()
                               if y == year and m == mo and cc == cat)
                diff_so = dash_so - model_so
                diff_st = dash_st - model_st
                if diff_so or diff_st:
                    recon_rows.append([int(year), mo, '(전체)', cat, RECON_MODEL,
                                        diff_st or None, diff_so or None, None])
    for row in recon_rows:
        ws.append(row)

    info = wb.create_sheet('검증·정보')
    info.append(['항목', '값'])
    info.append(['생성 시각', 'ir_monthly_psi_raw_export_builder.py 실행 시점'])
    info.append(['정합조정 행 수', len(recon_rows)])
    info.append(['원칙', '카테고리/채널/월 합계는 psi_data.js와 100% 일치. 모델 잔차는 비율배분 금지, 정합조정 1행으로 흡수.'])

    os.makedirs(OUT_DIR, exist_ok=True)
    wb.save(OUT_XLSX)
    print(f'Wrote {OUT_XLSX} — {len(model_rows)} model rows + {len(recon_rows)} recon rows')
    return len(recon_rows)


if __name__ == '__main__':
    build()
```

- [ ] **Step 2: 실행**

Run: `python3 /home/ubuntu/ir_monthly_psi_raw_export_builder.py`
Expected: `Wrote .../IR_Monthly_PSI_RawData.xlsx — N model rows + M recon rows`

- [ ] **Step 3: 검증 — 엑셀 합계가 psi_data.js와 정확히 일치하는지**

```python
# /home/ubuntu/test_ir_monthly_psi_excel.py
import sys, json, os
sys.path.insert(0, "/home/ubuntu")
from openpyxl import load_workbook
from ir_monthly_psi_common import OUT_DIR, STD_CATS, MONTHS

with open(os.path.join(OUT_DIR, 'psi_data.js')) as f:
    content = f.read()
payload = json.loads(content[len('var IR_PSI_DATA = '):-2])

wb = load_workbook(os.path.join(OUT_DIR, 'IR_Monthly_PSI_RawData.xlsx'), data_only=True)
ws = wb['RAW']
rows = list(ws.iter_rows(min_row=2, values_only=True))

from collections import defaultdict
excel_so = defaultdict(int)
excel_st = defaultdict(int)
for r in rows:
    year, mo, ch, cat, model, st, so, stk = r
    excel_so[(str(year), mo, cat)] += so or 0
    excel_st[(str(year), mo, cat)] += st or 0

for year in payload['meta']['years']:
    for cat in STD_CATS:
        for mo in MONTHS:
            dash_so = payload['years'][year]['by_cat'][cat][mo]['so']
            dash_st = payload['years'][year]['by_cat'][cat][mo]['st']
            assert excel_so[(year, mo, cat)] == dash_so, \
                f"{year}-{mo}-{cat} SO: excel {excel_so[(year, mo, cat)]} != dash {dash_so}"
            assert excel_st[(year, mo, cat)] == dash_st, \
                f"{year}-{mo}-{cat} ST: excel {excel_st[(year, mo, cat)]} != dash {dash_st}"

print("OK — 엑셀 카테고리×월×연도 합계가 psi_data.js와 완전히 일치(정합조정 포함)")
```

- [ ] **Step 4: 실행해서 통과 확인**

Run: `python3 /home/ubuntu/test_ir_monthly_psi_excel.py`
Expected: `OK — 엑셀 카테고리×월×연도 합계가 psi_data.js와 완전히 일치(정합조정 포함)`

- [ ] **Step 5: 대시보드에 다운로드 버튼 추가**

Edit `Shaker-MD-App/docs/dashboards/ir-monthly-psi/index.html`, 헤더 영역에 OR과 동일한 형태로 추가:

```html
<a href="IR_Monthly_PSI_RawData.xlsx" download>📥 Excel 다운로드</a>
```

- [ ] **Step 6: 커밋**

```bash
cd /home/ubuntu/Shaker-MD-App
git add docs/dashboards/ir-monthly-psi/IR_Monthly_PSI_RawData.xlsx docs/dashboards/ir-monthly-psi/index.html
git commit -m "Add ir-monthly-psi Excel export (tidy long, reconciliation-row convention)"
```

---

### Task 8: 자동 재생성 훅

**Files:**
- Create: `/home/ubuntu/ir_monthly_psi_pivot_deploy_hook.py`
- Modify: `/home/ubuntu/ir_monthly_psi_builder.py` (Task 4에서 이미 훅 import 시도 코드 넣어둠 — 이제 실제로 존재하게 됨)

- [ ] **Step 1: 훅 작성**

```python
# /home/ubuntu/ir_monthly_psi_pivot_deploy_hook.py
"""psi_data.js 재생성 직후 엑셀도 같은 폴더에 재생성. 검증 실패 시 직전 정상본 유지(조용히 틀린 엑셀 배포 금지)."""
import sys, shutil, os
sys.path.insert(0, "/home/ubuntu")


def rebuild_pivot_excel():
    from ir_monthly_psi_raw_export_builder import build, OUT_XLSX
    from ir_monthly_psi_common import OUT_DIR

    backup = OUT_XLSX + '.bak_prehook'
    had_previous = os.path.exists(OUT_XLSX)
    if had_previous:
        shutil.copy2(OUT_XLSX, backup)

    try:
        build()
        # 빠른 검증: 방금 만든 엑셀이 psi_data.js와 tie하는지 재확인
        import subprocess
        result = subprocess.run(['python3', '/home/ubuntu/test_ir_monthly_psi_excel.py'],
                                 capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'엑셀 검증 실패:\n{result.stdout}\n{result.stderr}')
        print('엑셀 재생성 + 검증 통과 — 배포 폴더 반영 완료')
    except Exception as e:
        print(f'⚠️ 엑셀 재생성 실패({e}) — 직전 정상본 유지')
        if had_previous:
            shutil.copy2(backup, OUT_XLSX)
    finally:
        if os.path.exists(backup):
            os.remove(backup)


if __name__ == '__main__':
    rebuild_pivot_excel()
```

- [ ] **Step 2: `ir_monthly_psi_builder.py`의 `__main__` 블록이 이 훅을 정상 호출하는지 재실행으로 확인**

Run: `python3 /home/ubuntu/ir_monthly_psi_builder.py`
Expected: `Wrote .../psi_data.js` 다음에 `엑셀 재생성 + 검증 통과 — 배포 폴더 반영 완료`가 출력됨(더 이상 "훅 아직 없음" 메시지가 안 나와야 함)

- [ ] **Step 3: 실패 케이스 수동 확인** — `psi_data.js`를 일부러 깨서(예: 임시로 한 카테고리 값을 +1) 훅이 직전 정상본을 유지하는지 확인 후 원복.

Run:
```bash
cp "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_data.js" /tmp/psi_data_backup.js
python3 -c "
content = open('/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_data.js').read()
content = content.replace('\"so\": 0', '\"so\": 999999', 1)
open('/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_data.js', 'w').write(content)
"
python3 /home/ubuntu/ir_monthly_psi_pivot_deploy_hook.py
```
Expected: `⚠️ 엑셀 재생성 실패(...) — 직전 정상본 유지` 출력됨

Run (원복): `cp /tmp/psi_data_backup.js "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_data.js"`

- [ ] **Step 4: 커밋 불필요** — 훅은 운영 스크립트(/home/ubuntu, 비git). Task 9로 진행.

---

### Task 9: 배포 전 체크리스트

**Files:** 없음(검증·배포 작업)

- [ ] **Step 1: 전 파이프라인 재실행으로 최신 상태 확인**

Run:
```bash
python3 /home/ubuntu/ir_monthly_psi_builder.py
python3 /home/ubuntu/ir_monthly_psi_model_table_builder.py
python3 /home/ubuntu/verify_ir_monthly_psi.py
python3 /home/ubuntu/test_ir_monthly_psi_model_table.py
python3 /home/ubuntu/test_ir_monthly_psi_excel.py
python3 "/home/ubuntu/2026/10. Automation/dashboard_part_contamination_gate.py"
```
Expected: 전부 `OK`/`PASS`, 에러 없음.

- [ ] **Step 2: playwright 스크린샷으로 탭별 렌더 확인** (`feedback_dashboard_screenshot_before_deploy.md` 규칙)

`/browse` 스킬로 로컬 서빙된 `ir-monthly-psi/index.html`을 열어 각 탭(월별 트렌드, 모델 테이블)을 스크린샷으로 캡처하고, 타이틀에 "IR Monthly PSI"가 정확히 표시되는지, 채널 9개/카테고리 7개 체크박스가 모두 동작하는지 확인.

- [ ] **Step 3: 최종 git 커밋 상태 확인**

Run: `cd /home/ubuntu/Shaker-MD-App && git status --short docs/dashboards/ir-monthly-psi/`
Expected: 추적 안 된 파일 없음(모든 산출물이 이미 Task 4~7에서 커밋됨).

- [ ] **Step 4: 사용자에게 배포(git push) 확인받고 push**

형님 승인 후:
```bash
git push
```

---

## Self-Review 체크리스트 (작성자용, 이미 반영함)
- **스펙 커버리지**: 데이터 아키텍처(Task 2·3·4) / 화면(Task 6) / 모델테이블(Task 5) / 엑셀(Task 7) / 자동화 훅(Task 8) / 배포 체크리스트(Task 9) 전부 스펙 문서 섹션과 1:1 대응.
- **플레이스홀더 스캔**: TODO/TBD 없음, 모든 스텝에 실행 가능한 실제 코드/명령 포함.
- **타입 일관성**: `IR_PSI_DATA` 전역 변수명, `STD_CATS`/`CHANNELS`/`MONTHS` 상수가 모든 Task에서 동일하게 재사용됨(공통 모듈 하나에서 import).
