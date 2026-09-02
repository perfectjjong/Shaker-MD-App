#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Official GPC (Finance 공시 최종본) 로더 — build_gpc_dashboard.py 에서 import.

소스: 03. Operation/00. GPC/02. 2026/04. Official GPC/NN. GPC official_MMM_YYYY.xlsx
      시트 1개, 12블록(Total + 카테고리 11종) x 23행, 열 = 기간.

⚠️ 원본 파일 함정 (2026-09-02 전수 해부로 확인, 우회 코드 아래에 있음)
  1) DR열(122)에 기간 라벨 문자열 잔재 100개 → 헤더를 dict 로 만들면 G열이 덮어써진다.
     ⇒ 월 컬럼(G~CT, idx 6~97)만 채택하고 파생/잔재 컬럼은 전면 배제.
  2) 분기/반기/연간/YTD 컬럼은 실적+FCST 혼합. YTD 는 D2 셀(=8) 하나가 지배.
     ⇒ 월 컬럼만 읽고 소계는 우리가 만든다.
  3) 'vs Budget' 컬럼은 예산이 아니라 2024년으로 나눈다(원본 버그). ⇒ 읽지 않는다.
  4) 부호 규약이 대시보드와 정반대. Official 은 할인·INV 를 양수로 저장해 차감한다:
       GSV-YED-ADC-VPD-DSI = NSV / NSV-COGS-INV+VSP = GM   (항등식 Δ0 검증됨)
     대시보드는 할인·INV 를 음수로 저장해 가산한다. ⇒ 적재 시 부호를 뒤집는다.
  5) FCST 는 8월 한 달치뿐이고 9~12월 실적란은 리터럴 0. ⇒ 전 지표 0 인 (월,기준)은 버린다.

카테고리 크로스워크의 정본은 Accrual 워크북의 숨김 시트 'Mapping 2024' 이다.
추측하지 않고 그 표를 그대로 옮겼다. 미등재 라벨이 나오면 조용히 넘기지 않고 즉시 중단한다.
"""
import collections
import glob
import re

import openpyxl

SRC_DIR = ("/home/ubuntu/2026/10. Automation/03. Operation/00. GPC/"
           "02. 2026/04. Official GPC")

# Official 라벨 → 대시보드 정본 라벨.
# 출처 = GPC_Accrual Only_*.xlsx 숨김시트 'Mapping 2024' + 빌더 _SRC_TO_CANON 을 합성한 결과.
# 'Others' 만 Mapping 2024 에 없는 Official 자체 잔여버킷이라 Accessory/Others 로 받는다.
OFF_TO_CANON = {
    "window":            "Window AC",
    "split (on / off)":  "Split On/Off",
    "split inverter":    "Split Inverter",
    "free standing":     "Floor Standing AC",
    "cassette":          "Cassette AC",
    "concealed (cac)":   "Concealed Set",
    "package (cac)":     "Unitary Package",
    "convertible (cac)": "CAC Ducted",
    "air purifier":      "Accessory/Others",
    "multi v":           "Multi-V",
    "others":            "Accessory/Others",
}

# Official 지표 → (대시보드 키, 부호). 할인 4종과 INV 는 부호를 뒤집는다.
MET = {"GSV": ("gsv", 1), "YED": ("yed", -1), "ADC": ("adc", -1),
       "VPD": ("vpd", -1), "DSI": ("dsi", -1), "COGS": ("cogs", 1),
       "INV": ("inv", -1), "VSP": ("vsp", 1),
       "NSV": ("nsv", 1), "GM": ("gm", 1)}
KEYS = [v[0] for v in MET.values()]

# Accrual 에만 있는 축. Official 은 이 매출을 Others 에 담으므로 대사 시 흡수한다.
# (2026 GSV 31,953 SAR = 전체의 0.01%. 2024/2025 는 0)
ABSORB = {"Applied": "Accessory/Others"}


def _nk(x):
    """대조용 정규화: 소문자 + 공백압축 + 하이픈/공백 동일시 (Multi V ↔ Multi-V)."""
    return re.sub(r"[\s\-]+", " ", re.sub(r"\s+", " ", str(x or "")).strip().lower()).strip()


def latest_src():
    files = sorted(glob.glob(f"{SRC_DIR}/*GPC official*.xlsx"))
    return files[-1] if files else None


def _period_cols(lab, band):
    """월 컬럼만 채택. 반환 {col: (year, month, 'A'|'B', band)}"""
    cols = {}
    for j in range(6, 98):                       # G~CT. DC~DR(파생·잔재)은 배제
        mo = re.fullmatch(r"(?:\((A|B)\))?(\d{4})(\d{2})", str(lab[j] or ""))
        if mo:
            cols[j] = (int(mo.group(2)), int(mo.group(3)),
                       mo.group(1) or "A", str(band[j] or ""))
    dup = [k for k, v in collections.Counter(str(lab[j]) for j in cols).items() if v > 1]
    if dup:
        raise SystemExit(f"❌ Official 월 컬럼에 중복 라벨 {dup} — DR열 잔재 배제 실패")
    return cols


def load(accrual_records):
    """Official 실적/예산/FCST 레코드와 메타를 만든다.

    accrual_records 는 재분류 의심 셀 플래그 계산에만 쓴다(값은 섞지 않는다).
    """
    src = latest_src()
    if not src:
        print(f"  ⏭  Official 파일 없음 ({SRC_DIR}) — Official 레이어 생략")
        return [], None

    wb = openpyxl.load_workbook(src, read_only=True, data_only=True)
    V = list(wb.active.iter_rows(values_only=True))
    wb.close()
    lab, band = V[2], V[1]
    cols = _period_cols(lab, band)

    agg = collections.defaultdict(lambda: dict.fromkeys(KEYS, 0.0))
    total_rows = collections.defaultdict(lambda: collections.defaultdict(float))
    unknown = set()
    for r in V[3:279]:
        met = str(r[5])
        if met not in MET:
            continue
        key, sign = MET[met]
        is_total = str(r[3]) == "Total"
        if not is_total:
            cat = OFF_TO_CANON.get(_nk(r[4]))
            if cat is None:
                unknown.add(str(r[4]))
                continue
        for j, (y, m, kind, bd) in cols.items():
            v = r[j]
            if v in (None, ""):
                continue
            val = float(v) * sign
            basis = "B" if kind == "B" else ("F" if bd == "FCST" else "A")
            if is_total:
                total_rows[(y, m, basis)][key] += val
            else:
                agg[(y, m, basis, cat)][key] += val
    if unknown:
        raise SystemExit(f"❌ Official 카테고리 미등재 {sorted(unknown)} — "
                         f"'Mapping 2024' 확인 후 OFF_TO_CANON 갱신 필요")

    # ── 검증 1: 적재값의 카테고리 합 == 엑셀 Total 행 (전 월 x 전 기준 x 전 지표) ──
    bad = 0
    for (y, m, b), tv in total_rows.items():
        for k in KEYS:
            s = sum(a[k] for (yy, mm, bb, _), a in agg.items()
                    if (yy, mm, bb) == (y, m, b))
            if abs(tv[k] - s) > 0.5:
                bad += 1
                print(f"  ❌ Official {y}-{m:02d}({b}) {k}: 엑셀Total={tv[k]:,.2f} 적재합={s:,.2f}")
    n1 = len(total_rows) * len(KEYS)
    print(f"  검증1 적재합=엑셀Total: {n1}셀 / 불일치 {bad}건")

    # ── 검증 2: 사다리 항등식 (부호 뒤집기가 맞았는지 증명) ──
    # 대시보드 규약으로 계산한 NSV/GP 가, 엑셀에서 직접 읽은 NSV/GM 과 같아야 한다.
    bad2 = 0
    for (y, m, b, cat), a in agg.items():
        nsv = a["gsv"] + a["yed"] + a["adc"] + a["vpd"] + a["dsi"]
        gp = nsv - a["cogs"] + a["inv"] + a["vsp"]
        if abs(nsv - a["nsv"]) > 0.5 or abs(gp - a["gm"]) > 0.5:
            bad2 += 1
            print(f"  ❌ 사다리 {y}-{m:02d}({b}) {cat}: "
                  f"계산NSV={nsv:,.2f} 엑셀NSV={a['nsv']:,.2f} / "
                  f"계산GP={gp:,.2f} 엑셀GM={a['gm']:,.2f}")
    print(f"  검증2 사다리 항등식: {len(agg)}셀 / 불일치 {bad2}건")
    if bad or bad2:
        raise SystemExit("❌ Official 적재값이 엑셀과 불일치 — 중단")

    # ── 전 지표 0 인 (월,기준)은 버린다 (2026-09~12 FCST 미입력분) ──
    rows = []
    for (y, m, b, cat), a in sorted(agg.items()):
        if all(abs(a[k]) < 0.5 for k in KEYS):
            continue
        rec = {"y": y, "m": m, "b": b, "cat": cat}
        rec.update({k: round(a[k], 6) for k in KEYS})
        rows.append(rec)

    # ── 재분류 의심 셀 플래그 ──
    # 카테고리 레벨 차이는 Finance 의 재분류가 섞여 있어 '보정'이 아니다.
    # 한쪽이 0인데 다른 쪽이 1만 SAR 초과 / |Δ| > 10% 인 셀에 표시한다.
    # ⚠️ 양측 (연,월,카테고리) 합집합으로 돈다. Official 레코드만 순회하면
    #    'Official 이 그 카테고리를 통째로 비워둔' 셀(2026 CAC Ducted 등 — 재분류의
    #    가장 뚜렷한 신호)이 누락된다.
    acc = collections.defaultdict(float)
    for r in accrual_records:
        cat = ABSORB.get(r["cat"], r["cat"])
        acc[(r["y"], r["m"], cat)] += r.get("gsv", 0.0) or 0.0
    off_a = {(r["y"], r["m"], r["cat"]): r["gsv"] for r in rows if r["b"] == "A"}
    off_ym = {(r["y"], r["m"]) for r in rows if r["b"] == "A"}
    flags = []
    for k in sorted(set(acc) | set(off_a)):
        if k[:2] not in off_ym:
            continue                      # Official 이 그 달 자체를 안 준 경우는 대사 대상 아님
        a, o = acc.get(k, 0.0), off_a.get(k, 0.0)
        if (abs(a) < 1 and abs(o) > 10000) or (abs(o) < 1 and abs(a) > 10000) \
                or (abs(a) > 100000 and abs((o - a) / a) > 0.10):
            flags.append([k[0], k[1], k[2]])

    ay = sorted({r["y"] for r in rows if r["b"] == "A"})
    meta = {
        "source": src.split("/")[-1],
        "actual_months": {str(y): sorted({r["m"] for r in rows if r["b"] == "A" and r["y"] == y})
                          for y in ay},
        "budget_months": {str(y): sorted({r["m"] for r in rows if r["b"] == "B" and r["y"] == y})
                          for y in sorted({r["y"] for r in rows if r["b"] == "B"})},
        "fcst_months": {str(y): sorted({r["m"] for r in rows if r["b"] == "F" and r["y"] == y})
                        for y in sorted({r["y"] for r in rows if r["b"] == "F"})},
        "absorb": ABSORB,
        "flags": flags,
        "inv_note": ("Official INV 는 실측이 아니라 배부·계획값이다. 2024 는 월 250,000 정액, "
                     "2025·2026 은 실적란이 예산값과 동일(타 9개 지표는 일치 0건). "
                     "Accrual INV(실제 발생액)와 성격이 달라 보정이 아닌 정의 차이로 표기한다."),
    }
    print(f"  Official 적재: {len(rows)}건 (실적월 {meta['actual_months']}, "
          f"FCST {meta['fcst_months']}) · 재분류 의심 {len(flags)}셀")
    return rows, meta
