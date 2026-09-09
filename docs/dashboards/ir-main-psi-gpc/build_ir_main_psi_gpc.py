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
⚠️ OUD 는 카테고리 5종(Split Inverter/ON-OFF·Window·Floor Standing·Others)만 제공 →
   Cassette/Concealed/Multi-V/Unitary 로 필터하면 OUD 는 0 이다. 화면에 명시한다.
"""
import json, os, re, sys, datetime
from collections import defaultdict

D = os.path.expanduser("~/Shaker-MD-App/docs/dashboards")
OUT = os.path.join(D, "ir-main-psi-gpc", "data.js")
sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
from shared_classification import channel_from_name
from shared_category import normalize_category

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
    """제품형과 별도인 압축기 축. 정본: Split 은 Inverter/On-Off 구분 의무."""
    l = str(label).lower()
    if "inverter" in l:
        return "Inverter"
    if "on/off" in l or "on-off" in l or "onoff" in l:
        return "On-Off"
    return "—"


def _js(path, const=None):
    s = open(path, encoding="utf-8").read()
    if const:
        i = s.index("const " + const); j = s.index("=", i) + 1
        k = s.find("\nconst ", j)
        return json.loads(s[j:k if k > 0 else len(s)].strip().rstrip(";").strip())
    return json.loads(s.split("=", 1)[1].rstrip().rstrip(";"))


def blank():
    return {k: 0.0 for k in QTY_KEYS + GPC_KEYS}


def main():
    cell = defaultdict(blank)          # (y, ch, cat, cmp, m) -> metrics

    # ── 1) PSI: 채널 x 카테고리 x 월 (수량) ──
    psi = _js(os.path.join(D, "ir-monthly-psi", "psi_data.js"))
    for y in YEARS:
        for ch in IR_MAIN:
            for raw, series in psi["years"][y]["by_ch_cat"][ch].items():
                cat, cmp_ = normalize_category(raw), compressor(raw)
                for m in MONTHS:
                    v = series[m]
                    c = cell[(y, ch, cat, cmp_, m)]
                    c["st"] += v["st"] or 0
                    c["so"] += v["so"] or 0
                    c["stk"] += v["stk"] or 0

    # ── 2) OUD: 2026 만, 각 월 마지막 주차 스냅샷 ──
    t = _js(os.path.join(D, "ir-total", "data_ir.js"))
    wkdate = {}
    for e in t["oudMeta"]:
        mm = re.match(r"(\d+)\s+(\w+)\s+(\d+)", e["label"])
        wkdate[e["key"]] = datetime.date(int(mm.group(3)), MNUM[mm.group(2)[:3]], int(mm.group(1)))
    lastwk, asof = {}, {}
    for k, d in wkdate.items():
        mo = d.strftime("%b")
        if mo not in lastwk or wkdate[lastwk[mo]] < d:
            lastwk[mo], asof[mo] = k, d.isoformat()
    for r in t["oudDealerCategory"]:
        ch = channel_from_name(r["dealer"])
        if ch not in IR_MAIN:
            continue
        cat, cmp_ = normalize_category(r["category"]), compressor(r["category"])
        for m in MONTHS:
            k = lastwk.get(m)
            if k and k in r:
                cell[("2026", ch, cat, cmp_, m)]["oud"] += r[k]["qty"]

    # ── 3) GPC: Accrual 라인아이템 ──
    gmeta = _js(os.path.join(D, "gpc", "gpc_data.js"), "GPC_META")
    grows = _js(os.path.join(D, "gpc", "gpc_data.js"), "GPC_DATA")
    for r in grows:
        y = str(r["y"])
        if y not in YEARS or not (1 <= r["m"] <= 8):
            continue
        if r["ch"] != "IR" or r["ac"] not in IR_MAIN:
            continue
        cat, cmp_ = normalize_category(r["cat"]), compressor(r["cat"])
        c = cell[(y, r["ac"], cat, cmp_, MONTHS[r["m"] - 1])]
        for k in GPC_KEYS:
            c[k] += r[k]

    cats = sorted({k[2] for k in cell})
    cmps = ["Inverter", "On-Off", "—"]
    cmps = [x for x in cmps if any(k[3] == x for k in cell)]

    rows = []
    for (y, ch, cat, cmp_, m), v in sorted(cell.items()):
        if not any(abs(x) > 0.005 for x in v.values()):
            continue
        rec = {"y": y, "ch": ch, "cat": cat, "cmp": cmp_, "m": m}
        for k in QTY_KEYS:
            rec[k] = round(v[k])
        for k in GPC_KEYS:
            rec[k] = round(v[k], 2)
        rows.append(rec)

    payload = {
        "meta": {
            "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "channels": IR_MAIN, "months": MONTHS, "years": YEARS,
            "cats": cats, "cmps": cmps, "ladder": LADDER,
            "oudAsOf": {m: asof.get(m) for m in MONTHS},
            "notes": {
                "psi": "ir-monthly-psi by_ch_cat 실측 월마감 (수량, 대)",
                "oud": "2026 만. 각 월 마지막 주차 스냅샷 (ir-total)",
                "gpc": "GPC Accrual 라인아이템. NSV=GSV+YED+ADC+VPD+DSI, GP=NSV-COGS+INV+VSP",
                "axis": "카테고리=shared_category.normalize_category SSOT · 압축기=별도 축",
                "oudCats": "OUD 원본은 Split·Window·Floor Standing·Others 만 제공",
            },
        },
        "rows": rows,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// IR Main 8채널 판매+손익 통합 (build_ir_main_psi_gpc.py 자동생성 — 직접 수정 금지)\n")
        f.write("const IRM_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n")

    print(f"✅ {OUT}  ({len(rows)}행, {os.path.getsize(OUT)/1024:.0f} KB)")
    print(f"   카테고리 {cats}")
    print(f"   압축기   {cmps}")
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
