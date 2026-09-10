#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IR Main 8채널 — 판매(PSI) + 손익(GPC) 통합 데이터 빌더

형님 지시 (2026-09-08~09):
  · 대상 = IR_Main 8채널만. Box Appliance 는 IR_Main 이 아니므로 제외(= IR_Others).
  · PSI 는 수량만. 금액 비교는 2025 소스가 없어 하지 않는다.
  · 2025 는 OUD 미포함(원본이 2025-08-10 부터만 존재). 2026 만 월마감 OUD 병기.
  · GPC 는 Accrual 기준. 사다리 전 항목(GSV·YED·ADC·VPD·DSI·NSV·COGS·INV·VSP·GP·GM%).
  · **카테고리·압축기 축 필수** — 2026-09-09 형님 지적으로 추가.

축 정본 (자체 룰 금지 · SSOT import 강제):
  · 카테고리 = shared_category.normalize_category()  → CANONICAL 8종으로 통일
  · 압축기   = 라벨의 Inverter / On-Off (제품형과 **별도 축**)
    - PSI 'Split Inverter'·'Split On/Off', GPC 동일, OUD 'Split ON-OFF'(표기 상이) 모두 흡수
    - GPC 고유 세분류(CAC Ducted→Concealed Set, Applied·Accessory/Others→Others)도 SSOT 가 접는다

소스 (전부 배포된 정본 산출물 — 재계산하지 않고 그대로 읽는다):
  · PSI  : docs/dashboards/ir-monthly-psi/psi_data.js   (by_ch_cat, 실측 월마감)
  · OUD  : docs/dashboards/ir-total/data_ir.js          (oudDealerCategory, 주간 → 월 마지막 주차)
  · GPC  : docs/dashboards/gpc/gpc_data.js              (GPC_Accrual Only_*.xlsx 라인아이템)

⚠️ 앵커/역산은 여기 없다. 그건 주간 채널 대시보드(inject_ir_monthly_stock_from_irtotal.py) 얘기다.
⚠️ 2026-08 GPC 는 가마감(재무 확정 전) — 화면에 표기한다.
🔴 OUD 는 **원본 xlsx 를 직접 읽는다**(2026-09-09 형님 지적).
   ir-total 의 oudDealerCategory 는 OUD_GROUP_TO_IR 로 5종까지 접혀 있어
   Cassette/Concealed/Multi-V/Unitary/CAC 가 사라진다. 원본 Detail1 시트의 `Group` 컬럼은
   11종(Split Inve·Split on/o·Window On/·Free Stand·Cassette·Concealed·CAC Ducted·
   Multi-V·Unitary Pa·Accessorie·installati)을 그대로 갖고 있고 Split 인버터/온오프도 구분된다.
   → 가공 집계 말고 원본을 쓴다. 월마감 = 그 달 마지막 스냅샷 파일.
"""
import glob, json, os, re, sys, datetime
from collections import defaultdict

import openpyxl

D = os.path.expanduser("~/Shaker-MD-App/docs/dashboards")
OUT = os.path.join(D, "ir-main-psi-gpc", "data.js")
OUD_DIR = ("/home/ubuntu/2026/10. Automation/00. Sell Thru Dashboard/00. Raw Data/02. 2026/05. OUD")
sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
from shared_classification import channel_from_name
from shared_category import normalize_category, is_part
import shared_set_rule as _SSR

# IR SAP 라인 데이터의 짝 카테고리 — unified_sellout_dashboard_generator.PAIR_CATS_SAP 와 동일
PAIR_CATS_SAP = {'Split AC', 'Cassette AC', 'Concealed Set', 'Floor Standing AC'}

IR_MAIN = ["BH", "Al Shathri", "BM", "Tamkeen", "Star Appliance",
           "Al Ghanem", "Dhamin", "Zagzoog"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
MNUM = {m: i + 1 for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])}
YEARS = ["2025", "2026"]
LADDER = [["gsv","GSV"],["yed","YED"],["adc","ADC"],["vpd","VPD"],["dsi","DSI"],
          ["nsv","NSV"],["cogs","COGS"],["inv","INV"],["vsp","VSP"],["gp","GP"]]
QTY_KEYS = ["st", "so", "stk", "oud"]
GPC_KEYS = ["gsv","yed","adc","vpd","dsi","cogs","inv","vsp"]


def compressor(label):
    """압축기 판정. ⚠️ OUD 원본 Group 은 10자로 잘려 온다('Split Inve','Split on/o') —
    'inverter'/'on/off' 완전한 단어로 찾으면 OUD 전량이 미분류로 빠진다(2026-09-09 실측 21,675대)."""
    l = str(label).lower()
    if "inve" in l:
        return "Inverter"
    if "on/o" in l or "on-o" in l or "onoff" in l:
        return "On-Off"
    return "—"


def display_cat(label):
    """화면 카테고리 축 (2026-09-09 형님 확정).

    압축기 축이 붙는 카테고리는 **Split 하나뿐**이라(실측: 나머지 7종 전부 '해당없음'),
    필터를 둘로 나누면 7개 칩이 죽는다. → Split 만 인버터/온오프로 쪼개 **카테고리 축 하나**로 만든다.
    ir-monthly-psi 의 자체 카테고리 목록과도 같은 형태가 된다.
    (SSOT normalize_category 는 Split 을 'Split AC' 로 접으므로, 압축기를 여기서 되붙인다 —
     정본이 요구하는 '인버터/온오프 구분 의무'는 이 축으로 충족된다.)
    ⚠️ Window 는 OUD 원본에만 On/Off 표기가 있고 PSI·GPC 는 구분하지 않는다 → 쪼개지 않는다."""
    cat = normalize_category(label)
    if cat == "Split AC":
        c = compressor(label)
        if c == "Inverter":
            return "Split Inverter"
        if c == "On-Off":
            return "Split On/Off"
    return cat


CAT_ORDER = ["Split Inverter", "Split On/Off", "Window AC", "Floor Standing AC",
             "Cassette AC", "Concealed Set", "CAC Ducted", "Multi-V",
             "Unitary Package", "Others", "Split AC"]


def _js(path, const=None):
    s = open(path, encoding="utf-8").read()
    if const:
        i = s.index("const " + const); j = s.index("=", i) + 1
        k = s.find("\nconst ", j)
        return json.loads(s[j:k if k > 0 else len(s)].strip().rstrip(";").strip())
    return json.loads(s.split("=", 1)[1].rstrip().rstrip(";"))


_MN = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"APRIL":4,"MAY":5,"JUN":6,"JUNE":6,
       "JUL":7,"JULY":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}


def _oud_date(path):
    m = re.match(r"(\d{1,2})[-\s]+([A-Za-z]+)[-\s]+(\d{4})", os.path.basename(path))
    return datetime.date(int(m.group(3)), _MN[m.group(2).upper()], int(m.group(1)))


def _oud_month_end_files():
    """2026 Jan~Aug 각 월의 월마감 OUD 스냅샷 파일.

    🔴 정책 = **월말(EOM)을 넘긴 첫 스냅샷** (= 익월 첫 주간 파일). 월말 당일 파일도 해당 안 됨.
       정본 3곳:
         · project_sellthru_progress_freeze_fg_supply — "월 closing 규칙 = eom **이후** 첫 스냅샷.
           최신본이 29-AUG 라 8/31 을 넘긴 파일이 없어 skip, 05-SEP 도착 시 8월이 채워진다"
         · project_domain_knowledge — "OUD 4/14 = 3월 마감 기준 OUD"
         · AR_DSO_Analysis/patch_v7_add_bh_or.get_oud_aggregate — "보고월 익월 첫째주 파일"
       ⚠️ 내가 2026-09-09 에 "그 달 마지막 파일" → "월말 최근접" 으로 두 번 임의 정의했다가 형님께
          연속 지적받았다. "월말 최근접(±7/10일)" 은 GTM 주간 리포트·앵커 파이프라인의 **다른 계층** 규약.
       ⚠️ build_ir_total_raw_pivot.oud_last_week 는 '그 달 마지막 주차' — 정책과 다름(별건, 미수정).
    루트 + 하위폴더 전부 스캔(2026-09-07 사고: 자동배치는 하위폴더, 수동은 루트).
    """
    import calendar
    cand = {}
    for d in (OUD_DIR, os.path.join(OUD_DIR, "01. 2026")):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".xlsx") or f.startswith("~$"):
                continue
            if not re.match(r"\d{1,2}[-\s]+[A-Za-z]+[-\s]+\d{4}", f):
                continue
            p = os.path.join(d, f)
            try:
                dt = _oud_date(p)
            except (AttributeError, KeyError, ValueError):
                continue
            if dt.year == 2026:
                cand.setdefault(dt, p)
    out = {}
    for mo in range(1, 9):
        eom = datetime.date(2026, mo, calendar.monthrange(2026, mo)[1])
        after = sorted(dt for dt in cand if dt > eom)
        if not after:
            raise ValueError(f"2026-{mo:02d} 마감 OUD 없음 — {eom} 을 넘긴 스냅샷 파일 미도착")
        out[mo] = cand[after[0]]
    return out


def _oud_rows(path):
    """원본 → (Customer, Group, Material, R-Qty). 헤더 키워드로 시트·행·컬럼을 찾는다.

    ⚠️ 포맷 드리프트 실측(2026 Jan~Aug): 고객 컬럼명이 'Customer Name'(1~6월) /
       'Customer'(7~8월), 시트명이 Detail1 / Detail2, 1월만 'PGI Qty' 컬럼이 하나 더 있다.
       컬럼 좌표를 고정하면 깨진다 — 반드시 헤더 이름으로 찾을 것.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    found = None
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        for i, r in enumerate(rows[:8]):
            if not r:
                continue
            names = {str(c).strip() for c in r if c}
            if ({"Customer", "Customer Name"} & names) and "Group" in names \
                    and "R-Qty" in names and "Material" in names:
                found = (rows, i, [str(c).strip() if c else "" for c in r])
                break
        if found:
            break
    wb.close()
    if not found:
        raise ValueError(f"OUD 헤더(Customer/Group/R-Qty) 탐지 실패: {os.path.basename(path)}")
    rows, hi, hdr = found
    ci = hdr.index("Customer") if "Customer" in hdr else hdr.index("Customer Name")
    gi, qi, mi = hdr.index("Group"), hdr.index("R-Qty"), hdr.index("Material")
    out = []
    for r in rows[hi + 1:]:
        if not r or ci >= len(r) or not r[ci]:
            continue
        nm = str(r[ci]).strip()
        if nm.lower().startswith(("total", "grand", "합계")):
            continue
        q = r[qi] if qi < len(r) else None
        if not isinstance(q, (int, float)):
            continue
        out.append((nm, str(r[gi]) if gi < len(r) and r[gi] else "",
                    str(r[mi]) if mi < len(r) and r[mi] else "", float(q)))
    return out


def blank():
    return {k: 0.0 for k in QTY_KEYS + GPC_KEYS}


def _fin():
    """AR Overdue(월말 잔액) · Collection(월 수금) — 채널 x 연 x 월.

    소스 = sell-thru-progress/data.json 의 ar_monthly / col_monthly (계정 단위 재무).
    ⚠️ 카테고리 축이 없다 — 제품 카테고리와 무관한 계정 채권이므로 cell(=카테고리별)에 넣지 않고
       meta 로 분리한다. 프론트에서도 카테고리 필터에 반응시키지 말 것.
    ⚠️ ovd 는 **잔액(스냅샷)** 이라 월별로 더하면 안 된다 — 특정 월말 값만 쓴다.
       col 은 mtd(그 달 수금액)라 기간 합산이 가능하다.
    채널 매핑은 OUD 와 동일하게 shared_classification.channel_from_name 사용.
    """
    src = os.path.join(D, "sell-thru-progress", "data.json")
    if not os.path.exists(src):
        return {}
    with open(src, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for key, fld, tgt in (("ar_monthly", "ovd", "ovd"), ("col_monthly", "mtd", "col")):
        for rec in d.get(key, []):
            ym = str(rec.get("month") or "")
            if "-" not in ym:
                continue
            y, mm = ym.split("-", 1)
            if y not in YEARS:
                continue
            i = int(mm)
            if i > len(MONTHS):
                continue
            m = MONTHS[i - 1]
            for _aid, v in (rec.get("accts") or {}).items():
                ch = channel_from_name(v.get("nm") or "")
                if ch not in IR_MAIN:
                    continue
                slot = out.setdefault(ch, {}).setdefault(y, {}).setdefault(m, {"ovd": 0.0, "col": 0.0})
                slot[tgt] += v.get(fld) or 0
    for ch in out:
        for y in out[ch]:
            for m in out[ch][y]:
                for k in out[ch][y][m]:
                    out[ch][y][m][k] = round(out[ch][y][m][k], 2)
    return out


def main():
    cell = defaultdict(blank)          # (y, ch, cat, m) -> metrics

    # ── 1) PSI: 채널 x 카테고리 x 월 (수량) ──
    psi = _js(os.path.join(D, "ir-monthly-psi", "psi_data.js"))
    for y in YEARS:
        for ch in IR_MAIN:
            for raw, series in psi["years"][y]["by_ch_cat"][ch].items():
                cat = display_cat(raw)
                for m in MONTHS:
                    v = series[m]
                    c = cell[(y, ch, cat, m)]
                    c["st"] += v["st"] or 0
                    c["so"] += v["so"] or 0
                    c["stk"] += v["stk"] or 0

    # ── 2) OUD: 원본 xlsx 직접 로드 (2026 만, 각 월 **마지막 스냅샷 파일**) ──
    # ⚠️ 원본은 OBD 라인이라 분리형이 IDU·ODU 두 행으로 잡힌다. 그대로 더하면 정확히 2배가 된다
    #    (2026-08-22 실측: Free Stand 2,960 vs 세트 1,480). 세트 환산 SSOT 를 반드시 통과시킨다.
    asof = {}
    oud_rows = []
    for mo_idx, path in _oud_month_end_files().items():
        m = MONTHS[mo_idx - 1]
        asof[m] = _oud_date(path).isoformat()
        for cust, group, material, qty in _oud_rows(path):
            ch = channel_from_name(cust)
            if ch not in IR_MAIN:
                continue
            # 부품·악세사리·설치 라인 제외 (2026-09-09): ir-total/B2C 기준과 동일하게 shared_category.is_part
            # + 원본 Group 'Accessorie'/'installati'. 종전엔 'Others' 로 785대(9/6) 섞여 들어갔다.
            g = group.lower()
            if g.startswith(("accessorie", "installati")) or is_part(material):
                continue
            oud_rows.append({"ch": ch, "m": m, "model": material,
                             "cat": normalize_category(group),      # 짝맞춤은 SSOT 축으로
                             "dcat": display_cat(group),            # 표시는 Split 분리 축으로
                             "unit": _SSR.unit_type(material), "qty": qty})
    for r in _SSR.pair_to_sets(oud_rows, group_key=("ch",), model_key="model", cat_key="cat",
                               unit_key="unit", qty_key="qty", time_key=("m",),
                               pair_cats=PAIR_CATS_SAP):
        if r["qty"]:
            cell[("2026", r["ch"], r["dcat"], r["m"])]["oud"] += r["qty"]

    # ── 3) GPC: Accrual 라인아이템 ──
    gmeta = _js(os.path.join(D, "gpc", "gpc_data.js"), "GPC_META")
    grows = _js(os.path.join(D, "gpc", "gpc_data.js"), "GPC_DATA")
    for r in grows:
        y = str(r["y"])
        if y not in YEARS or not (1 <= r["m"] <= 8):
            continue
        if r["ch"] != "IR" or r["ac"] not in IR_MAIN:
            continue
        c = cell[(y, r["ac"], display_cat(r["cat"]), MONTHS[r["m"] - 1])]
        for k in GPC_KEYS:
            c[k] += r[k]

    seen = {k[2] for k in cell}
    cats = [c for c in CAT_ORDER if c in seen] + sorted(seen - set(CAT_ORDER))

    rows = []
    for (y, ch, cat, m), v in sorted(cell.items()):
        if not any(abs(x) > 0.005 for x in v.values()):
            continue
        rec = {"y": y, "ch": ch, "cat": cat, "m": m}
        for k in QTY_KEYS:
            rec[k] = round(v[k])
        for k in GPC_KEYS:
            rec[k] = round(v[k], 2)
        rows.append(rec)

    payload = {
        "meta": {
            "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "channels": IR_MAIN, "months": MONTHS, "years": YEARS,
            "cats": cats, "ladder": LADDER,
            "oudAsOf": {m: asof.get(m) for m in MONTHS},
            "fin": _fin(),
            "notes": {
                "psi": "ir-monthly-psi by_ch_cat 실측 월마감 (수량, 대)",
                "oud": "2026 만. 월말을 넘긴 첫 스냅샷(=익월 첫 파일, 05. OUD 원본) · 세트 환산 shared_set_rule 적용",
                "gpc": "GPC Accrual 라인아이템. NSV=GSV+YED+ADC+VPD+DSI, GP=NSV-COGS+INV+VSP",
                "axis": "카테고리=shared_category SSOT + Split 만 인버터/온오프 분리 (압축기 축이 Split 전용이라 단일 축으로 통합)",
                "oudCats": "OUD 는 원본 xlsx Group 컬럼(11종) 기준 — 가공 집계 아님",
            },
        },
        "rows": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// IR Main 8채널 판매+손익 통합 (build_ir_main_psi_gpc.py 자동생성 — 직접 수정 금지)\n")
        f.write("const IRM_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n")

    print(f"✅ {OUT}  ({len(rows)}행, {os.path.getsize(OUT)/1024:.0f} KB)")
    print(f"   카테고리 {cats}")
    for y in YEARS:
        st = sum(r["st"] for r in rows if r["y"] == y)
        so = sum(r["so"] for r in rows if r["y"] == y)
        stk = sum(r["stk"] for r in rows if r["y"] == y and r["m"] == "Aug")
        oud = sum(r["oud"] for r in rows if r["y"] == y and r["m"] == "Aug")
        gsv = sum(r["gsv"] for r in rows if r["y"] == y)
        nsv = sum(r["gsv"]+r["yed"]+r["adc"]+r["vpd"]+r["dsi"] for r in rows if r["y"] == y)
        gp = nsv - sum(r["cogs"] for r in rows if r["y"] == y) \
             + sum(r["inv"]+r["vsp"] for r in rows if r["y"] == y)
        print(f"  {y}: ST {st:,} · SO {so:,} · 8월재고 {stk:,} · 8월OUD {oud:,} "
              f"· GSV {gsv:,.0f} · GP {gp:,.0f} ({gp/nsv*100:.1f}%)")


if __name__ == "__main__":
    main()
