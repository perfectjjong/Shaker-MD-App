# B2C 통합 Monthly PSI 대시보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ir-monthly-psi`(IR 9채널)와 `or-monthly-psi`(OR 5채널)를 건드리지 않고, 두 대시보드의 완성된 출력물을 합쳐 14채널 통합 Monthly PSI 대시보드 `b2c-monthly-psi`를 새로 만든다.

**Architecture:** 신규 파이썬 빌더 2개(`b2c_monthly_psi_builder.py`, `b2c_monthly_psi_model_table_builder.py`)가 원본 SAP raw를 다시 파싱하지 않고 **이미 배포된 `ir-monthly-psi/psi_data.js` + `or-monthly-psi/psi_data.js`(그리고 각각의 `psi_model_table.js`)를 읽어서 병합**한다. 검증 스크립트(`verify_b2c_monthly_psi.py`)는 통합본 합계가 두 원본 합계와 **오차 없이 정확히** 일치하는지 확인한다. 정적 셸 `index.html`은 `ir-monthly-psi`의 템플릿을 베이스로 복사해 채널 필터(OR/IR 그룹 퀵필터)와 Model Table "기준" 컬럼만 확장한다.

**Tech Stack:** Python 3(표준 라이브러리 + `json`), 기존 `ir_monthly_psi_common.py`의 `extract_json_var()` 재사용. 프론트는 순수 JS(프레임워크 없음), 기존 두 대시보드와 동일 패턴.

**TDD 적용 방식에 대한 메모:** 이 프로젝트의 "Monthly PSI" 계열 빌더들은 순수 함수 단위 테스트 대신 "빌드 → 검증 스크립트로 정합성 확인" 패턴을 이미 정착시켜 놓았다(`ir_monthly_psi_builder.py` + `verify_ir_monthly_psi.py`가 선례). 이 계획도 동일 패턴을 따른다: 각 빌더 Task는 "작성 → 실행 → 검증 스크립트로 확인"의 순서를 갖는다(검증 스크립트 자체가 회귀 테스트 역할).

---

### Task 1: 공통 상수 모듈

**Files:**
- Create: `/home/ubuntu/b2c_monthly_psi_common.py`

- [ ] **Step 1: 파일 작성**

```python
# /home/ubuntu/b2c_monthly_psi_common.py
"""b2c-monthly-psi 빌더 공통 상수. ir-monthly-psi(9채널)+or-monthly-psi(5채널) 병합 전용.
원본(SAP raw/data_ir.js)은 절대 다시 읽지 않는다 — 두 소스 대시보드의 완성된 출력물만 읽는다."""
import os

OR_CHANNELS = ['eXtra', 'Al Manea', 'SWS', 'Black Box', 'Al Khunizan']
IR_CHANNELS = ['Al Ghanem', 'Al Shathri', 'BH', 'BM', 'Dhamin', 'Star Appliance',
               'Tamkeen', 'Zagzoog', 'IR_Others']
CHANNELS = OR_CHANNELS + IR_CHANNELS  # 14채널, OR 먼저 IR 다음(고정 순서)

# ir-monthly-psi/or-monthly-psi 둘 다 이미 동일한 라벨 사용(재매핑 불필요, 설계 문서 확인됨).
STD_CATS = ['Split Inverter', 'Split On/Off', 'Window AC', 'Floor Standing AC',
            'Cassette', 'Concealed', 'Others']

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
YEARS = ['2023', '2024', '2025', '2026']

# 입력(읽기 전용 — 이 두 파일은 이 프로젝트가 절대 쓰지 않는다)
IR_PSI_JS = "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_data.js"
OR_PSI_JS = "/home/ubuntu/Shaker-MD-App/docs/dashboards/or-monthly-psi/psi_data.js"
IR_MODEL_JS = "/home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/psi_model_table.js"
OR_MODEL_JS = "/home/ubuntu/Shaker-MD-App/docs/dashboards/or-monthly-psi/psi_model_table.js"

# 출력
OUT_DIR = "/home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi"
OUT_JS = os.path.join(OUT_DIR, 'psi_data.js')
OUT_MODEL_JS = os.path.join(OUT_DIR, 'psi_model_table.js')
```

- [ ] **Step 2: import 확인**

Run: `python3 -c "import sys; sys.path.insert(0,'/home/ubuntu'); import b2c_monthly_psi_common as c; print(len(c.CHANNELS), c.CHANNELS)"`
Expected: `14 ['eXtra', 'Al Manea', 'SWS', 'Black Box', 'Al Khunizan', 'Al Ghanem', 'Al Shathri', 'BH', 'BM', 'Dhamin', 'Star Appliance', 'Tamkeen', 'Zagzoog', 'IR_Others']`

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu && git status --short b2c_monthly_psi_common.py
```
(이 파일은 `/home/ubuntu`에 있고 `Shaker-MD-App` git 저장소 밖이므로 별도 커밋 불필요 — 다른 `*_monthly_psi_*.py` 빌더들도 전부 `/home/ubuntu`에 있고 git 추적 대상이 아님. 이후 Task들에서 이 관례를 유지한다.)

---

### Task 2: PSI 데이터 병합 빌더

**Files:**
- Create: `/home/ubuntu/b2c_monthly_psi_builder.py`

- [ ] **Step 1: 파일 작성**

```python
# /home/ubuntu/b2c_monthly_psi_builder.py
"""b2c-monthly-psi psi_data.js 빌더. ir-monthly-psi + or-monthly-psi의 완성된 psi_data.js를
읽어서 14채널로 병합한다. SAP raw나 data_ir.js는 절대 다시 읽지 않는다(설계 문서 참조:
docs/superpowers/specs/2026-08-09-b2c-monthly-psi-design.md).

⚠️ 재생성 순서: ir_monthly_psi_builder.py → or_monthly_psi_builder.py → 이 스크립트.
두 입력 파일이 최신이 아니면 경고만 출력하고 계속 진행한다(빌드를 막지 않음)."""
import sys, os, json, time
sys.path.insert(0, "/home/ubuntu")
from b2c_monthly_psi_common import (
    OR_CHANNELS, IR_CHANNELS, CHANNELS, STD_CATS, MONTHS, YEARS,
    IR_PSI_JS, OR_PSI_JS, OUT_DIR, OUT_JS,
)
from ir_monthly_psi_common import extract_json_var


def _mtime_warning():
    """두 입력 파일이 이 스크립트의 이전 실행 시점보다 새 것인지는 확인할 방법이 없으므로
    (매번 새로 읽으니 항상 최신을 읽음), 대신 두 입력 파일 자체가 서로 너무 오래 벌어져
    있으면(한쪽만 최근에 갱신되고 한쪽은 오래됨) 경고한다 — 월마감 순서를 깜빡했을 가능성."""
    ir_mtime = os.path.getmtime(IR_PSI_JS)
    or_mtime = os.path.getmtime(OR_PSI_JS)
    gap_days = abs(ir_mtime - or_mtime) / 86400
    if gap_days > 3:
        older = 'or-monthly-psi' if or_mtime < ir_mtime else 'ir-monthly-psi'
        print(f'⚠️  입력 파일 갱신 시점이 {gap_days:.1f}일 벌어져 있음 — {older}가 최신이 '
              f'아닐 수 있음. 필요시 해당 빌더 먼저 재실행 권장.')


def _sum_none_aware(vals):
    present = [v for v in vals if v is not None]
    return sum(present) if present else None


def _load_ir():
    with open(IR_PSI_JS) as f:
        content = f.read()
    return extract_json_var(content, 'var IR_PSI_DATA = ')


def _load_or():
    with open(OR_PSI_JS) as f:
        content = f.read()
    return extract_json_var(content, 'const PSI_DATA = ')


def _empty_cell():
    return {'so': 0, 'st': 0, 'stk': None}


def _build_by_ch_cat(ir_payload, or_payload, yr):
    """IR은 이미 by_ch_cat[ch][cat][mo] 모양 → 그대로 가져옴.
    OR은 data[ch][mo].by_cat[cat] 모양 → by_ch_cat[ch][cat][mo]로 재배열(재계산 없음)."""
    by_ch_cat = {}
    ir_years = ir_payload['years']
    if yr in ir_years:
        for ch in IR_CHANNELS:
            by_ch_cat[ch] = ir_years[yr]['by_ch_cat'][ch]
    else:
        for ch in IR_CHANNELS:
            by_ch_cat[ch] = {cat: {mo: _empty_cell() for mo in MONTHS} for cat in STD_CATS}

    or_data = or_payload['data']
    for ch in OR_CHANNELS:
        by_ch_cat[ch] = {cat: {} for cat in STD_CATS}
        for cat in STD_CATS:
            for mo in MONTHS:
                cell = or_data.get(yr, {}).get(ch, {}).get(mo, {}).get('by_cat', {}).get(cat)
                by_ch_cat[ch][cat][mo] = dict(cell) if cell else _empty_cell()
    return by_ch_cat


def _derive_by_cat(by_ch_cat):
    out = {}
    for cat in STD_CATS:
        out[cat] = {}
        for mo in MONTHS:
            out[cat][mo] = {
                'so': sum(by_ch_cat[ch][cat][mo]['so'] for ch in CHANNELS),
                'st': sum(by_ch_cat[ch][cat][mo]['st'] for ch in CHANNELS),
                'stk': _sum_none_aware(by_ch_cat[ch][cat][mo]['stk'] for ch in CHANNELS),
            }
    return out


def _derive_by_ch(by_ch_cat):
    out = {}
    for ch in CHANNELS:
        out[ch] = {}
        for mo in MONTHS:
            out[ch][mo] = {
                'so': sum(by_ch_cat[ch][cat][mo]['so'] for cat in STD_CATS),
                'st': sum(by_ch_cat[ch][cat][mo]['st'] for cat in STD_CATS),
                'stk': _sum_none_aware(by_ch_cat[ch][cat][mo]['stk'] for cat in STD_CATS),
            }
    return out


def _merge_oud(ir_payload, or_payload):
    """둘 다 {mo: {ch: {cat: qty}}} 모양(로더 두 개가 이미 동일 shape로 산출). 월별로
    양쪽 채널 딕셔너리를 union — 한쪽에만 있는 월은 그 쪽 채널만 존재(거짓0 금지)."""
    ir_oud = ir_payload['years'].get('2026', {}).get('oud_by_ch_cat', {})
    or_oud = or_payload.get('oud', {}).get('2026', {})
    months = set(ir_oud) | set(or_oud)
    merged = {}
    for mo in months:
        merged[mo] = {}
        merged[mo].update(ir_oud.get(mo, {}))
        merged[mo].update(or_oud.get(mo, {}))
    return merged


def build():
    _mtime_warning()
    ir_payload = _load_ir()
    or_payload = _load_or()

    payload = {
        'meta': {
            'channels': CHANNELS,
            'categories': STD_CATS,
            'months': MONTHS,
            'years': YEARS,
            'groups': {'OR': OR_CHANNELS, 'IR': IR_CHANNELS},
        },
        'years': {},
    }
    for yr in YEARS:
        by_ch_cat = _build_by_ch_cat(ir_payload, or_payload, yr)
        payload['years'][yr] = {
            'by_cat': _derive_by_cat(by_ch_cat),
            'by_ch': _derive_by_ch(by_ch_cat),
            'by_ch_cat': by_ch_cat,
        }
    payload['years']['2026']['oud_by_ch_cat'] = _merge_oud(ir_payload, or_payload)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_JS, 'w') as f:
        f.write('// B2C Monthly PSI — generated by b2c_monthly_psi_builder.py\n')
        f.write(f'// Source: ir-monthly-psi + or-monthly-psi (merge only, no raw re-parse)\n')
        f.write('var B2C_PSI_DATA = ')
        json.dump(payload, f, ensure_ascii=False)
        f.write(';\n')
    print(f'Wrote {OUT_JS}')
    return payload


if __name__ == '__main__':
    build()
```

- [ ] **Step 2: 실행**

Run: `python3 /home/ubuntu/b2c_monthly_psi_builder.py`
Expected: `Wrote /home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/psi_data.js` (⚠️ 경고 줄이 뜨면 `ir_monthly_psi_builder.py`/`or_monthly_psi_builder.py`를 먼저 최신 실행했는지 확인 — 이번 세션에서는 둘 다 최근 실행했으므로 경고가 뜨지 않아야 정상)

- [ ] **Step 3: 출력 육안 확인**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'/home/ubuntu')
from ir_monthly_psi_common import extract_json_var
with open('/home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/psi_data.js') as f:
    content = f.read()
d = extract_json_var(content, 'var B2C_PSI_DATA = ')
print('channels:', len(d['meta']['channels']))
print('BH 2026 Jul stk:', d['years']['2026']['by_ch']['BH']['Jul']['stk'])
print('eXtra 2026 Jul stk:', d['years']['2026']['by_ch']['eXtra']['Jul']['stk'])
"
```
Expected: `channels: 14`, `BH 2026 Jul stk: 10125` (오늘 세션에서 override로 확정한 값과 반드시 일치해야 함 — ir-monthly-psi psi_data.js를 그대로 가져오므로), `eXtra 2026 Jul stk:` 는 0이 아닌 실측값.

---

### Task 3: 정합성 검증 스크립트

**Files:**
- Create: `/home/ubuntu/verify_b2c_monthly_psi.py`

- [ ] **Step 1: 파일 작성**

```python
# /home/ubuntu/verify_b2c_monthly_psi.py
"""b2c-monthly-psi 정합성 검증. 통합본이 두 원본(ir-monthly-psi, or-monthly-psi) 합계와
오차 없이 정확히 일치하는지 확인한다(완성본을 그대로 합쳤으므로 반올림 오차조차 없어야 함)."""
import sys
sys.path.insert(0, "/home/ubuntu")
from b2c_monthly_psi_common import (
    OR_CHANNELS, IR_CHANNELS, CHANNELS, STD_CATS, MONTHS, YEARS, OUT_JS,
)
from ir_monthly_psi_common import extract_json_var
from b2c_monthly_psi_builder import _load_ir, _load_or, _derive_by_cat, _derive_by_ch

FIELDS = ['so', 'st', 'stk']


def main():
    with open(OUT_JS) as f:
        combined = extract_json_var(f.read(), 'var B2C_PSI_DATA = ')
    ir_payload = _load_ir()
    or_payload = _load_or()

    errors = []

    # 1) 채널별 원본 대조 — combined.by_ch_cat이 소스 값을 그대로 옮겼는지
    for yr in YEARS:
        cyc = combined['years'][yr]['by_ch_cat']
        for ch in IR_CHANNELS:
            ir_cell_src = ir_payload['years'].get(yr, {}).get('by_ch_cat', {}).get(ch)
            for cat in STD_CATS:
                for mo in MONTHS:
                    expect = ir_cell_src[cat][mo] if ir_cell_src else {'so': 0, 'st': 0, 'stk': None}
                    got = cyc[ch][cat][mo]
                    for f_ in FIELDS:
                        if got[f_] != expect[f_]:
                            errors.append(f'{yr}/{mo}/{ch}/{cat}/{f_}: got {got[f_]} != IR원본 {expect[f_]}')
        for ch in OR_CHANNELS:
            for cat in STD_CATS:
                for mo in MONTHS:
                    src_cell = or_payload['data'].get(yr, {}).get(ch, {}).get(mo, {}).get('by_cat', {}).get(cat)
                    expect = dict(src_cell) if src_cell else {'so': 0, 'st': 0, 'stk': None}
                    got = cyc[ch][cat][mo]
                    for f_ in FIELDS:
                        if got[f_] != expect[f_]:
                            errors.append(f'{yr}/{mo}/{ch}/{cat}/{f_}: got {got[f_]} != OR원본 {expect[f_]}')

    # 2) 구조적 정합 — by_cat/by_ch가 by_ch_cat에서 정확히 파생됐는지
    for yr in YEARS:
        cyc = combined['years'][yr]['by_ch_cat']
        expect_by_cat = _derive_by_cat(cyc)
        expect_by_ch = _derive_by_ch(cyc)
        if combined['years'][yr]['by_cat'] != expect_by_cat:
            errors.append(f'{yr}: by_cat이 by_ch_cat 파생값과 불일치')
        if combined['years'][yr]['by_ch'] != expect_by_ch:
            errors.append(f'{yr}: by_ch가 by_ch_cat 파생값과 불일치')

    # 3) 재고 음수 0건
    for yr in YEARS:
        for ch in CHANNELS:
            for mo in MONTHS:
                stk = combined['years'][yr]['by_ch'][ch][mo]['stk']
                if stk is not None and stk < 0:
                    errors.append(f'{yr}/{mo}/{ch}: 재고 음수 {stk}')

    if errors:
        print(f'❌ FAIL — {len(errors)}건')
        for e in errors[:20]:
            print(' ', e)
        sys.exit(1)
    print(f'✅ PASS — {len(YEARS)}개년 × {len(CHANNELS)}채널 × {len(STD_CATS)}카테고리 × '
          f'{len(MONTHS)}월, IR/OR 원본 대조 + 구조적 파생 정합 + 재고 음수 0건 확인')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 실행 — PASS 확인**

Run: `python3 /home/ubuntu/verify_b2c_monthly_psi.py`
Expected: `✅ PASS — 4개년 × 14채널 × 7카테고리 × 12월, IR/OR 원본 대조 + 구조적 파생 정합 + 재고 음수 0건 확인`

- [ ] **Step 3: 검증기가 실제로 오류를 잡는지 확인 (회귀 방지)**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'/home/ubuntu')
content = open('/home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/psi_data.js').read()
content = content.replace('var B2C_PSI_DATA = ', 'var B2C_PSI_DATA = ', 1)
import json
from ir_monthly_psi_common import extract_json_var
d = extract_json_var(content, 'var B2C_PSI_DATA = ')
d['years']['2026']['by_ch']['BH']['Jul']['stk'] = 99999  # 고의로 깨뜨림
with open('/tmp/broken_b2c_psi_data.js','w') as f:
    f.write('var B2C_PSI_DATA = ' + json.dumps(d) + ';\n')
"
python3 -c "
import sys; sys.path.insert(0,'/home/ubuntu')
import b2c_monthly_psi_common as c
c.OUT_JS = '/tmp/broken_b2c_psi_data.js'
import importlib, verify_b2c_monthly_psi as v
importlib.reload(v)
v.main()
" ; echo "exit code: $?"
```
Expected: `❌ FAIL` 로 시작하고 `by_ch가 by_ch_cat 파생값과 불일치` 계열 에러가 잡힘, exit code 1. (이 스텝은 검증기 자체를 검증하는 일회성 확인 — 통과하면 `/tmp/broken_b2c_psi_data.js` 삭제)

Run: `rm -f /tmp/broken_b2c_psi_data.js`

---

### Task 4: Model Table 병합 빌더

**Files:**
- Create: `/home/ubuntu/b2c_monthly_psi_model_table_builder.py`

- [ ] **Step 1: 파일 작성**

```python
# /home/ubuntu/b2c_monthly_psi_model_table_builder.py
"""b2c-monthly-psi Model Table 빌더. IR/OR 각자의 MOS 산출 방법론을 재계산하지 않고
그대로 가져와 flat 스키마로 합친다(설계 문서: MOS 기준 통일 안 함, basis 필드로 명시)."""
import sys, os, json
sys.path.insert(0, "/home/ubuntu")
from b2c_monthly_psi_common import IR_MODEL_JS, OR_MODEL_JS, OUT_MODEL_JS, OUT_DIR
from ir_monthly_psi_common import extract_json_var


def _load_ir_rows():
    with open(IR_MODEL_JS) as f:
        content = f.read()
    d = extract_json_var(content, 'var IR_PSI_MODEL_TABLE = ')
    rows = []
    for r in d['rows']:
        rows.append({
            'model': r['model'], 'category': r['category'], 'channel': r['channel'],
            'stk': r['stk'], 'so_recent': r['so_recent_4w'], 'mos': r['mos'],
            'flag': r['flag'], 'basis': 'IR-4wk-avg',
        })
    return rows, {'ir_as_of_week': d['as_of_week'], 'ir_as_of_year': d['as_of_year']}


def _load_or_rows():
    with open(OR_MODEL_JS) as f:
        content = f.read()
    d = extract_json_var(content, 'const PSI_MODEL_TABLE = ')
    rows = []
    for ch, buckets in d['mos_analysis'].items():
        for _bucket_name, bucket_rows in buckets.items():
            for r in bucket_rows:
                rows.append({
                    'model': r['unified'], 'category': r['category'], 'channel': ch,
                    'stk': r['stk'], 'so_recent': r['avg_so'], 'mos': r['mos'],
                    'flag': r['flag'], 'basis': 'OR-2mo-avg',
                })
    return rows, {'or_month': d['month'], 'or_month_label': d['month_label']}


def build():
    ir_rows, ir_meta = _load_ir_rows()
    or_rows, or_meta = _load_or_rows()

    payload = {
        'as_of': {**ir_meta, **or_meta},
        'basis_labels': {
            'IR-4wk-avg': 'IR 최근 4주 평균 판매',
            'OR-2mo-avg': 'OR 최근 2개월 평균 판매',
        },
        'rows': ir_rows + or_rows,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_MODEL_JS, 'w') as f:
        f.write('// B2C Monthly PSI Model Table — generated by b2c_monthly_psi_model_table_builder.py\n')
        f.write('// IR rows use 4-week rolling avg MOS; OR rows use 2-month avg MOS (see basis field)\n')
        f.write('var B2C_PSI_MODEL_TABLE = ')
        json.dump(payload, f, ensure_ascii=False)
        f.write(';\n')
    print(f'Wrote {OUT_MODEL_JS} — {len(ir_rows)} IR rows + {len(or_rows)} OR rows = {len(payload["rows"])} total')
    return payload


if __name__ == '__main__':
    build()
```

- [ ] **Step 2: 실행**

Run: `python3 /home/ubuntu/b2c_monthly_psi_model_table_builder.py`
Expected: `Wrote /home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/psi_model_table.js — N IR rows + M OR rows = (N+M) total` (N, M > 0)

- [ ] **Step 3: 필드 무결성 확인**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'/home/ubuntu')
from ir_monthly_psi_common import extract_json_var
d = extract_json_var(open('/home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/psi_model_table.js').read(), 'var B2C_PSI_MODEL_TABLE = ')
bases = set(r['basis'] for r in d['rows'])
print('basis 종류:', bases)
print('필드 누락 행 수:', sum(1 for r in d['rows'] if not all(k in r for k in ['model','category','channel','stk','so_recent','mos','flag','basis'])))
"
```
Expected: `basis 종류: {'IR-4wk-avg', 'OR-2mo-avg'}`, `필드 누락 행 수: 0`

---

### Task 5: 신규 대시보드 index.html

**Files:**
- Create: `/home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/index.html` (복사본 기반)

- [ ] **Step 1: ir-monthly-psi 템플릿 복사**

```bash
cp /home/ubuntu/Shaker-MD-App/docs/dashboards/ir-monthly-psi/index.html \
   /home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/index.html
```

- [ ] **Step 2: 전역 변수명 치환** (psi_data.js/psi_model_table.js가 이제 다른 var를 내보내므로)

```bash
cd /home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi
sed -i 's/IR_PSI_MODEL_TABLE/B2C_PSI_MODEL_TABLE/g; s/IR_PSI_DATA/B2C_PSI_DATA/g; s/so_recent_4w/so_recent/g' index.html
grep -c "B2C_PSI_DATA\|B2C_PSI_MODEL_TABLE" index.html
grep -c "IR_PSI_DATA\|IR_PSI_MODEL_TABLE\|so_recent_4w" index.html
```
Expected: 첫 번째 grep은 0보다 큰 수(치환된 참조 수), 두 번째 grep은 `0`(옛 이름이 하나도 안 남아야 함)

- [ ] **Step 3: 헤더 텍스트 교체**

Use Edit tool (old_string → new_string) on `docs/dashboards/b2c-monthly-psi/index.html`:

old_string:
```html
<title>IR Monthly PSI 2023–2026</title>
```
new_string:
```html
<title>B2C Monthly PSI 2023–2026</title>
```

old_string:
```html
<div class="header">
  <h1>IR Monthly PSI</h1>
  <span style="font-size:11px;color:#94a3b8">8+Others Channels · 2023–2026</span>
```
new_string:
```html
<div class="header">
  <h1>B2C Monthly PSI</h1>
  <span style="font-size:11px;color:#94a3b8">14 Channels · OR 5 + IR 9 · 2023–2026</span>
```

- [ ] **Step 4: Excel 다운로드 링크 제거** (이번 범위에 엑셀 export 빌더 없음)

old_string:
```html
  <a href="IR_Monthly_PSI_RawData.xlsx" download
     title="Raw(피벗용) 데이터 · 채널×월×카테고리(2023~26) + 채널×월×모델(2023~25, 2026은 정합조정 1행) · Sell-Thru/Sell-Out/Stock"
     style="margin-left:auto;display:inline-flex;align-items:center;gap:5px;background:#10b981;color:#fff;font-size:11px;font-weight:700;padding:5px 12px;border-radius:6px;text-decoration:none">📥 Excel 다운로드</a>
  <span id="hdr-info" style="margin-left:12px;font-size:11px;color:#94a3b8"></span>
```
new_string:
```html
  <span id="hdr-info" style="margin-left:auto;font-size:11px;color:#94a3b8"></span>
```

- [ ] **Step 5: 채널 필터 — 그룹 퀵필터 + 14채널 버튼으로 교체**

old_string:
```html
  <span class="fl">Channel</span>
  <button class="fb on" data-ch="ALL">All</button>
  <button class="fb" data-ch="Al Ghanem">Al Ghanem</button>
  <button class="fb" data-ch="Al Shathri">Al Shathri</button>
  <button class="fb" data-ch="BH">BH</button>
  <button class="fb" data-ch="BM">BM</button>
  <button class="fb" data-ch="Dhamin">Dhamin</button>
  <button class="fb" data-ch="Star Appliance">Star Appliance</button>
  <button class="fb" data-ch="Tamkeen">Tamkeen</button>
  <button class="fb" data-ch="Zagzoog">Zagzoog</button>
  <button class="fb" data-ch="IR_Others">IR_Others</button>
```
new_string:
```html
  <span class="fl">Channel</span>
  <button class="fb on" data-ch="ALL">All</button>
  <button class="fb" data-ch-group="OR" style="background:#f59e0b;color:#fff;border-color:#f59e0b">OR 전체</button>
  <button class="fb" data-ch-group="IR" style="background:#3b82f6;color:#fff;border-color:#3b82f6">IR 전체</button>
  <button class="fb" data-ch="eXtra" style="border-color:#f59e0b;color:#f59e0b">eXtra</button>
  <button class="fb" data-ch="Al Manea" style="border-color:#f59e0b;color:#f59e0b">Al Manea</button>
  <button class="fb" data-ch="SWS" style="border-color:#f59e0b;color:#f59e0b">SWS</button>
  <button class="fb" data-ch="Black Box" style="border-color:#f59e0b;color:#f59e0b">Black Box</button>
  <button class="fb" data-ch="Al Khunizan" style="border-color:#f59e0b;color:#f59e0b">Al Khunizan</button>
  <button class="fb" data-ch="Al Ghanem" style="border-color:#3b82f6;color:#3b82f6">Al Ghanem</button>
  <button class="fb" data-ch="Al Shathri" style="border-color:#3b82f6;color:#3b82f6">Al Shathri</button>
  <button class="fb" data-ch="BH" style="border-color:#3b82f6;color:#3b82f6">BH</button>
  <button class="fb" data-ch="BM" style="border-color:#3b82f6;color:#3b82f6">BM</button>
  <button class="fb" data-ch="Dhamin" style="border-color:#3b82f6;color:#3b82f6">Dhamin</button>
  <button class="fb" data-ch="Star Appliance" style="border-color:#3b82f6;color:#3b82f6">Star Appliance</button>
  <button class="fb" data-ch="Tamkeen" style="border-color:#3b82f6;color:#3b82f6">Tamkeen</button>
  <button class="fb" data-ch="Zagzoog" style="border-color:#3b82f6;color:#3b82f6">Zagzoog</button>
  <button class="fb" data-ch="IR_Others" style="border-color:#3b82f6;color:#3b82f6">IR_Others</button>
```

- [ ] **Step 6: 그룹 퀵필터 클릭 핸들러 추가**

old_string:
```html
// 채널: 다중 선택 + 토글 해제. ALL은 단독 선택 (OR 원본과 완전히 동일한 패턴)
document.querySelectorAll('[data-ch]').forEach(btn => {
```
new_string:
```html
// 채널 그룹 퀵필터: OR 전체/IR 전체 클릭 = 그 그룹 채널 전부를 선택한 것과 동일 효과
document.querySelectorAll('[data-ch-group]').forEach(btn => {
  btn.addEventListener('click', () => {
    const group = btn.dataset.chGroup;
    const groupChs = B2C_PSI_DATA.meta.groups[group];
    curChs = new Set(groupChs);
    document.querySelectorAll('[data-ch]').forEach(b => {
      b.classList.toggle('on', curChs.has(b.dataset.ch));
    });
    document.querySelectorAll('[data-ch-group]').forEach(b => b.classList.toggle('on', b === btn));
    render();
  });
});

// 채널: 다중 선택 + 토글 해제. ALL은 단독 선택 (OR 원본과 완전히 동일한 패턴)
document.querySelectorAll('[data-ch]').forEach(btn => {
```

- [ ] **Step 7: 개별 채널/ALL 클릭 시 그룹 버튼 하이라이트 해제** (그룹 선택 후 개별 채널을 만지면 그룹 버튼 강조가 남아있으면 안 됨)

old_string:
```html
    document.querySelectorAll('[data-ch]').forEach(b => {
      b.classList.toggle('on', curChs.has(b.dataset.ch));
    });
    render();
  });
});

// 카테고리
```
new_string:
```html
    document.querySelectorAll('[data-ch]').forEach(b => {
      b.classList.toggle('on', curChs.has(b.dataset.ch));
    });
    document.querySelectorAll('[data-ch-group]').forEach(b => b.classList.remove('on'));
    render();
  });
});

// 카테고리
```

- [ ] **Step 8: Model Table에 "기준" 컬럼 추가**

먼저 현재 헤더/행 렌더 코드 확인:

Run: `grep -n "function renderModelTable\|<th>Flag\|r.flag" /home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/index.html | head -10`

그 출력에서 Model Table의 `<thead>` 행과 `<tbody>` 행 생성 부분을 찾아, "Flag" 컬럼 헤더 뒤에 `<th>기준</th>`를, 그리고 각 데이터 행의 `flag` 셀 뒤에 `<td>' + (r.basis === 'IR-4wk-avg' ? 'IR 4주평균' : 'OR 2개월평균') + '</td>'`를 추가한다. (정확한 old_string/new_string은 위 grep 결과의 실제 줄을 보고 결정 — 이 파일은 1600줄 규모라 미리 줄 번호를 고정할 수 없음. 담당 엔지니어는 grep 결과를 Read로 열어 정확한 `<th>`/`<td>` 나열부를 찾아 동일한 스타일로 추가할 것.)

- [ ] **Step 9: 문법 검사**

Run: `node --check /home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/index.html 2>&1 | head -5`
(HTML 파일이라 `node --check`는 스크립트 태그 안 JS를 직접 검사 못함 — 대신 아래 Task 6의 playwright 콘솔 에러 체크가 실질적 검증 역할)

Run: `python3 -c "
import re
content = open('/home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/index.html').read()
m = re.search(r'<script>(.*)</script>', content, re.S)
js = m.group(1)
open('/tmp/b2c_psi_inline.js','w').write(js)
"
node --check /tmp/b2c_psi_inline.js`
Expected: 에러 없음(빈 출력)

- [ ] **Step 10: Commit**

```bash
cd /home/ubuntu/Shaker-MD-App
git add docs/dashboards/b2c-monthly-psi/index.html docs/dashboards/b2c-monthly-psi/psi_data.js docs/dashboards/b2c-monthly-psi/psi_model_table.js
git commit -m "feat: add b2c-monthly-psi combined dashboard (OR 5 + IR 9 channels)"
```

---

### Task 6: Playwright 렌더 확인

**Files:** (읽기 전용 — 코드 변경 없음)

- [ ] **Step 1: 전 탭 스크린샷 + 콘솔 에러 확인**

Run:
```python
python3 -c "
from playwright.sync_api import sync_playwright

TABS = ['Overview', 'MOS Analysis', 'MOS-2 Action', 'YoY Comparison', 'Channel Analysis', 'Data', 'Model Table']

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width':1400,'height':1000})
    errs = []
    pg.on('console', lambda msg: errs.append(msg.text) if msg.type=='error' else None)
    pg.goto('file:///home/ubuntu/Shaker-MD-App/docs/dashboards/b2c-monthly-psi/index.html')
    pg.wait_for_timeout(1500)
    for tab in TABS:
        pg.click(f'text={tab}')
        pg.wait_for_timeout(700)
        pg.screenshot(path=f'/tmp/b2c_psi_{tab.replace(\" \",\"_\")}.png', full_page=True)
        print(tab, '-> errors so far:', errs)
    # 그룹 퀵필터 확인
    pg.click('text=Overview')
    pg.wait_for_timeout(500)
    pg.click('[data-ch-group=\"OR\"]')
    pg.wait_for_timeout(500)
    print('OR 그룹 클릭 후 errors:', errs)
    pg.click('[data-ch-group=\"IR\"]')
    pg.wait_for_timeout(500)
    print('IR 그룹 클릭 후 errors:', errs)
    b.close()
"
```
Expected: 모든 줄에서 `errors so far: []` (콘솔 에러 0건)

- [ ] **Step 2: 스크린샷 육안 확인**

각 `/tmp/b2c_psi_*.png`를 Read 도구로 열어 차트/테이블이 정상 렌더(0폭 찌부러짐, 빈 화면 없음)되는지 확인. Model Table 탭에서 "기준" 컬럼이 보이고 IR 행엔 "IR 4주평균", OR 행엔 "OR 2개월평균"이 표기되는지 확인.

---

### Task 7: 부품 오염 게이트 + 사이트 네비게이션 등록

**Files:**
- Modify: `/home/ubuntu/Shaker-MD-App/docs/index.html`

- [ ] **Step 1: 부품 오염 게이트 실행**

Run: `python3 "/home/ubuntu/2026/10. Automation/dashboard_part_contamination_gate.py"`
Expected: `✅ GATE PASS — 오염 0` (이 게이트가 b2c-monthly-psi를 아직 스캔 대상에 포함 안 했다면 스킵 — 기존 두 원본이 이미 통과했고 이번 빌더는 원본을 재분류하지 않으므로 오염 유입 경로 없음)

- [ ] **Step 2: 사이트 인덱스에 링크 추가**

old_string (`docs/index.html`):
```html
          { name: 'IR Monthly PSI', description: 'IR 8 channels + Others monthly Sell-Thru/Sell-Out/Stock PSI — 2023–2026', url: '/dashboards/ir-monthly-psi/', icon: '📊', indent: true },
          { name: 'B2C 14 Ch. Weekly Sell Out', description: 'IR 9 + OR 5 channels combined sell-out dashboard', url: '/dashboards/b2c-unified/', icon: '🌐', indent: true },
```
new_string:
```html
          { name: 'IR Monthly PSI', description: 'IR 8 channels + Others monthly Sell-Thru/Sell-Out/Stock PSI — 2023–2026', url: '/dashboards/ir-monthly-psi/', icon: '📊', indent: true },
          { name: 'B2C 14 Ch. Monthly PSI', description: 'OR 5 + IR 9 channels combined monthly Sell-Thru/Sell-Out/Stock PSI', url: '/dashboards/b2c-monthly-psi/', icon: '📊', indent: true },
          { name: 'B2C 14 Ch. Weekly Sell Out', description: 'IR 9 + OR 5 channels combined sell-out dashboard', url: '/dashboards/b2c-unified/', icon: '🌐', indent: true },
```

- [ ] **Step 3: 문법 검사**

Run: `python3 -c "
import re
content = open('/home/ubuntu/Shaker-MD-App/docs/index.html').read()
assert content.count(\"b2c-monthly-psi\") == 1
print('OK — 신규 링크 1건 확인')
"`
Expected: `OK — 신규 링크 1건 확인`

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/Shaker-MD-App
git add docs/index.html
git commit -m "feat: add b2c-monthly-psi link to dashboard index"
```

---

### Task 8: 배포

**Files:** (git push만)

- [ ] **Step 1: 최종 git status 확인**

Run: `cd /home/ubuntu/Shaker-MD-App && git status --short`
Expected: 커밋 안 된 변경 없음(Task 5/7에서 이미 커밋 완료)

- [ ] **Step 2: push**

```bash
cd /home/ubuntu/Shaker-MD-App && git push
```
Expected: `main -> main` push 성공

- [ ] **Step 3: 배포 확인 보고 형식**

> ✅ B2C 통합 Monthly PSI 대시보드 신규 생성 완료
> - URL: /dashboards/b2c-monthly-psi/
> - 14채널(OR 5 + IR 9) 통합, ir-monthly-psi·or-monthly-psi는 변경 없이 그대로 유지
> - 검증: `verify_b2c_monthly_psi.py` PASS(IR/OR 원본 대조 + 구조적 파생 정합 + 재고 음수 0건), 부품오염 게이트 PASS
> - Model Table: IR(4주평균)·OR(2개월평균) 각자 방법론 유지, "기준" 컬럼으로 명시
> - Playwright 전 탭 스크린샷 확인, 콘솔 에러 0건
> - 유지보수 노트: 향후 월마감 시 `ir_monthly_psi_builder.py` → `or_monthly_psi_builder.py` → `b2c_monthly_psi_builder.py` → `b2c_monthly_psi_model_table_builder.py` 순서로 재실행 필요

---

## Self-Review 체크리스트 (계획 작성자가 직접 확인)

- **스펙 커버리지**: 목표/범위(Task 5,7) · 데이터 아키텍처(Task 2,3) · Model Table 병합(Task 4) · UI(Task 5) · 검증(Task 3,6,7) · 배포(Task 8) · 유지보수 노트(Task 8 보고 형식) — 스펙의 전 섹션에 대응하는 Task 존재.
- **플레이스홀더 스캔**: "TBD"/"나중에" 없음. Task 5 Step 8만 정확한 줄 번호를 못 박지 못했는데(1600줄 파일이라 사전에 고정 불가), 이는 "grep으로 실제 위치를 찾아 지정된 스타일로 추가"라는 구체적 절차를 줬으므로 방치된 플레이스홀더는 아님 — 실행 시점에 실제 코드를 봐야 하는 유일한 이유가 파일 크기이지 요구사항 불명확성이 아님.
- **타입/필드 일관성**: `so_recent`(Task 4에서 생성 → Task 5 sed로 index.html도 동일하게 통일), `basis`(Task 4 생성 → Task 5 Step 8에서 렌더) — 필드명 일치 확인.
