#!/usr/bin/env python3
"""[1회성 마이그레이션 · 2026-09-09 실행 완료] 허브 HTML 인라인 카드 정의를 cards.json 으로 추출.

지금은 docs/functions/cards.json 이 카드 SSOT 이므로 이 스크립트는 다시 돌릴 일이 없다.
카드를 추가/수정하려면 cards.json 을 직접 고치고 build_access_groups.py 를 돌린다.

카드 목록이 HTML 안에 있으면 권한 없는 항목도 소스 보기로 노출된다.
추출 후에는 미들웨어가 /api/cards 로 권한에 맞는 카드만 만들어 내려보낸다.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "functions" / "cards.json"
HUBS = {
    "main": ("docs/index.html", "GROUPS"),
    "ir": ("docs/ir/index.html", "IR_GROUP"),
    "or": ("docs/or/index.html", "OR_GROUP"),
    "price": ("docs/price/index.html", "PRICE_GROUP"),
}

# 카드 그룹 -> 권한 그룹(access-config.json 의 groups 키).
# 외부 링크는 URL 로 통제할 수 없으므로 이 권한 그룹을 가진 사람에게만 보여준다.
ACL_KEY = {
    "Management Dashboard": "management",
    "OR Ch. Dashboard": "or",
    "IR Ch. Dashboard": "ir",
    "Price Tracking": "price",
    "GTM Weekly": "gtm-weekly",
    "GTM Dashboard": "gtm",
    "Archive": "archive",
}
SUB_HUB_ACL = {"ir": "ir", "or": "or", "price": "price"}

ITEM = re.compile(
    r"\{\s*name:\s*'((?:[^'\\]|\\.)*)',\s*description:\s*'((?:[^'\\]|\\.)*)',\s*"
    r"url:\s*'((?:[^'\\]|\\.)*)',\s*icon:\s*'((?:[^'\\]|\\.)*)'(,\s*indent:\s*true)?\s*\}"
)
GROUP_HEAD = re.compile(
    r"\{\s*name:\s*'((?:[^'\\]|\\.)*)',\s*description:\s*'((?:[^'\\]|\\.)*)',\s*"
    r"icon:\s*'((?:[^'\\]|\\.)*)',\s*children:\s*\["
)


def unesc(s):
    return s.replace("\\'", "'").replace("\\\\", "\\")


def parse(html, var):
    if f"const {var} = " not in html:
        raise SystemExit(
            f"{path}: 인라인 카드 정의가 없습니다. 마이그레이션이 이미 끝났습니다 — "
            "카드는 docs/functions/cards.json 에서 수정하십시오."
        )
    start = html.index(f"const {var} = ")
    # 선언부터 스크립트 끝까지에서 그룹 헤더 단위로 자른다
    body = html[start:]
    groups = []
    heads = list(GROUP_HEAD.finditer(body))
    assert heads, f"{var}: 그룹 헤더 없음"
    for i, h in enumerate(heads):
        seg = body[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        children = []
        for m in ITEM.finditer(seg):
            c = {"name": unesc(m.group(1)), "description": unesc(m.group(2)),
                 "url": unesc(m.group(3)), "icon": unesc(m.group(4))}
            if m.group(5):
                c["indent"] = True
            children.append(c)
        groups.append({"name": unesc(h.group(1)), "description": unesc(h.group(2)),
                       "icon": unesc(h.group(3)), "children": children})
    return groups


def main():
    out = {}
    for hub, (path, var) in HUBS.items():
        html = (ROOT / path).read_text(encoding="utf-8")
        groups = parse(html, var)
        for g in groups:
            acl = ACL_KEY.get(g["name"]) if hub == "main" else SUB_HUB_ACL.get(hub)
            if acl is None:
                raise SystemExit(f"! 권한 그룹 미매핑: [{hub}] {g['name']} — ACL_KEY 에 추가할 것")
            g["acl"] = acl
        out[hub] = groups
        n = sum(len(g["children"]) for g in groups)
        print(f"  {hub:6s} 그룹 {len(groups)} · 카드 {n}")
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
