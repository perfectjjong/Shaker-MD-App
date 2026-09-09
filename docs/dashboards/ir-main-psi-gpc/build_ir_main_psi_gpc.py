#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IR Main 8채널 — 판매(PSI) + 손익(GPC) 통합 데이터 빌더

형님 지시 (2026-09-08~09):
  · 대상 = IR_Main 8채널만. Box Appliance 는 IR_Main 이 아니므로 제외(= IR_Others).
  · PSI 는 수량만. 금액 비교는 2025 소스가 없어 하지 않는다.
  · 2025 는 OUD 미포함(원본이 2025-08-10 부터만 존재). 2026 만 월마감 OUD 병기.
  · GPC 는 Accrual 기준.

소스 (전부 배포된 정본 산출물 — 재계산하지 않고 그대로 읽는다):
  · PSI  : docs/dashboards/ir-monthly-psi/psi_data.js   (ir-total dealerCategory 집계 실측 월마감)
  · OUD  : docs/dashboards/ir-total/data_ir.js          (oudDealerCategory, 주간 → 월 마지막 주차)
  · GPC  : docs/dashboards/gpc/gpc_data.js              (GPC_Accrual Only_*.xlsx 라인아이템)

⚠️ 앵커/역산은 여기 없다. 그건 주간 채널 대시보드(inject_ir_monthly_stock_from_irtotal.py) 얘기다.
⚠️ 2026-08 GPC 는 가마감(재무 확정 전) — 화면에 표기한다.
"""
import json, os, re, sys, datetime

D = os.path.expanduser("~/Shaker-MD-App/docs/dashboards")
OUT = os.path.join(D, "ir-main-psi-gpc", "data.js")
sys.path.insert(0, "/home/ubuntu/2026/10. Automation")
from shared_classification import channel_from_name

IR_MAIN = ["BH", "Al Shathri", "BM", "Tamkeen", "Star Appliance",
           "Al Ghanem", "Dhamin", "Zagzoog"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
MNUM = {m: i + 1 for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])}
YEARS = ["2025", "2026"]


def _js(path, const=None):
    s = open(path, encoding="utf-8").read()
    if const:
        i = s.index("const " + const); j = s.index("=", i) + 1
        k = s.find("\nconst ", j)
        return json.loads(s[j:k if k > 0 else len(s)].strip().rstrip(";").strip())
    return json.loads(s.split("=", 1)[1].rstrip().rstrip(";"))


def load_psi():
    p = _js(os.path.join(D, "ir-monthly-psi", "psi_data.js"))
    out = {}
    for y in YEARS:
        for ch in IR_MAIN:
            src = p["years"][y]["by_ch"][ch]
            for m in MONTHS:
                v = src[m]
                out[(y, ch, m)] = {"st": v["st"] or 0, "so": v["so"] or 0, "stk": v["stk"] or 0}
    return out


def load_oud_2026():
    """ir-total 주간 OUD → 각 월의 '마지막 주차' 스냅샷을 그 달 월마감 OUD 로 쓴다."""
    t = _js(os.path.join(D, "ir-total", "data_ir.js"))
    wk = {}
    for e in t["oudMeta"]:
        mm = re.match(r"(\d+)\s+(\w+)\s+(\d+)", e["label"])
        wk[e["key"]] = datetime.date(int(mm.group(3)), MNUM[mm.group(2)[:3]], int(mm.group(1)))
    last, asof = {}, {}
    for k, d in wk.items():
        mo = d.strftime("%b")
        if mo not in last or wk[last[mo]] < d:
            last[mo] = k; asof[mo] = d.isoformat()
    out = {(ch, m): 0.0 for ch in IR_MAIN for m in MONTHS}
    for r in t["oudDealerCategory"]:
        ch = channel_from_name(r["dealer"])
        if ch not in IR_MAIN:
            continue
        for m in MONTHS:
            k = last.get(m)
            if k and k in r:
                out[(ch, m)] += r[k]["qty"]
    return out, {m: asof.get(m) for m in MONTHS}


def load_gpc():
    meta = _js(os.path.join(D, "gpc", "gpc_data.js"), "GPC_META")
    rows = _js(os.path.join(D, "gpc", "gpc_data.js"), "GPC_DATA")
    keys = meta["metric_keys"]
    out = {}
    for y in YEARS:
        for ch in IR_MAIN:
            for m in MONTHS:
                out[(y, ch, m)] = {k: 0.0 for k in keys}
    for r in rows:
        y, mi = str(r["y"]), r["m"]
        if y not in YEARS or not (1 <= mi <= 8):
            continue
        if r["ch"] != "IR" or r["ac"] not in IR_MAIN:
            continue
        cell = out[(y, r["ac"], MONTHS[mi - 1])]
        for k in keys:
            cell[k] += r[k]
    return out, keys


def main():
    psi = load_psi()
    oud, oud_asof = load_oud_2026()
    gpc, gkeys = load_gpc()

    data = {}
    for y in YEARS:
        data[y] = {}
        for ch in IR_MAIN:
            data[y][ch] = {}
            for m in MONTHS:
                p = psi[(y, ch, m)]
                g = gpc[(y, ch, m)]
                nsv = g["gsv"] + g["yed"] + g["adc"] + g["vpd"] + g["dsi"]
                gp = nsv - g["cogs"] + g["inv"] + g["vsp"]
                # GPC 손익 사다리 전 항목 (gpc 대시보드 LADDER 와 동일 순서·부호 규약)
                #   GSV → YED·ADC·VPD·DSI(할인 4종, 음수) → NSV → COGS·INV·VSP → GP, GM%=GP/NSV
                rec = {"st": p["st"], "so": p["so"], "stk": p["stk"],
                       "oud": round(oud[(ch, m)]) if y == "2026" else None,
                       "gsv": round(g["gsv"], 2), "yed": round(g["yed"], 2),
                       "adc": round(g["adc"], 2), "vpd": round(g["vpd"], 2),
                       "dsi": round(g["dsi"], 2), "nsv": round(nsv, 2),
                       "cogs": round(g["cogs"], 2), "inv": round(g["inv"], 2),
                       "vsp": round(g["vsp"], 2), "gp": round(gp, 2)}
                data[y][ch][m] = rec

    payload = {
        "meta": {
            "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "channels": IR_MAIN,
            "months": MONTHS,
            "years": YEARS,
            "oudAsOf": oud_asof,
            "ladder": [["gsv","GSV"],["yed","YED"],["adc","ADC"],["vpd","VPD"],["dsi","DSI"],
                       ["nsv","NSV"],["cogs","COGS"],["inv","INV"],["vsp","VSP"],["gp","GP"]],
            "notes": {
                "psi": "ir-monthly-psi 실측 월마감 (수량, 대)",
                "oud": "2026 만. 각 월 마지막 주차 스냅샷 (ir-total)",
                "gpc": "GPC Accrual 라인아이템. NSV=GSV+YED+ADC+VPD+DSI, GP=NSV-COGS+INV+VSP",
                "provisional": "2026-08 GPC 는 가마감(재무 확정 전)",
            },
        },
        "data": data,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("// IR Main 8채널 판매+손익 통합 (build_ir_main_psi_gpc.py 자동생성 — 직접 수정 금지)\n")
        f.write("const IRM_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n")

    # 검증 출력
    print(f"✅ {OUT}")
    for y in YEARS:
        st = sum(data[y][c][m]["st"] for c in IR_MAIN for m in MONTHS)
        so = sum(data[y][c][m]["so"] for c in IR_MAIN for m in MONTHS)
        stk = sum(data[y][c]["Aug"]["stk"] for c in IR_MAIN)
        gsv = sum(data[y][c][m]["gsv"] for c in IR_MAIN for m in MONTHS)
        gp = sum(data[y][c][m]["gp"] for c in IR_MAIN for m in MONTHS)
        nsv = sum(data[y][c][m]["nsv"] for c in IR_MAIN for m in MONTHS)
        o = sum(data[y][c]["Aug"]["oud"] or 0 for c in IR_MAIN)
        print(f"  {y}: ST {st:,.0f} · SO {so:,.0f} · 8월재고 {stk:,.0f} · 8월OUD {o:,.0f} "
              f"· GSV {gsv:,.0f} · GP {gp:,.0f} ({gp/nsv*100:.1f}%)")


if __name__ == "__main__":
    main()
