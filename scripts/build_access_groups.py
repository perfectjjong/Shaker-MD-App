#!/usr/bin/env python3
"""docs/functions/cards.json 의 카드 정의로 접근제어 그룹 매핑을 생성한다.

cards.json 이 카드 SSOT (2026-09-09 이전에는 index.html 인라인이었다).
대시보드가 추가/삭제되면 cards.json 수정 후 이 스크립트를 다시 돌린다.
출력: docs/functions/access-config.json 의 "groups" 키만 갱신 (users/superusers 보존).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "docs" / "functions" / "cards.json"
CFG = ROOT / "docs" / "functions" / "access-config.json"

# 미들웨어 resourceOf() 와 동일 규칙 — 바꾸려면 양쪽 같이 고칠 것
SECTIONS = ["gtm-weekly", "gtm", "psi", "mega-promo", "reports"]

# 허브 카드가 외부 링크뿐이라 자동 파싱으로는 안 잡히지만, 폴더에 실제 콘텐츠가 있는 섹션
GROUP_SECTIONS = {"gtm": ["sec:gtm"]}


def resource_of(url: str):
    if not url.startswith("/"):
        return None  # 외부 링크는 통제 불가
    if url.startswith("/dashboards/"):
        parts = url.split("/")
        return "dash:" + parts[2] if len(parts) > 2 and parts[2] else None
    for s in SECTIONS:
        if url == "/" + s or url.startswith("/" + s + "/"):
            return "sec:" + s
    return None


def main():
    cards = json.loads(CARDS.read_text(encoding="utf-8"))
    groups, external = {}, []
    for g in cards["hubs"]["main"]:
        key = g["acl"]
        res = groups.setdefault(key, [])
        for c in g["children"]:
            r = resource_of(c["url"])
            if r is None:
                external.append((g["name"], c["url"]))
            elif r not in res:
                res.append(r)

    for key, extra in GROUP_SECTIONS.items():
        for r in extra:
            if r not in groups.setdefault(key, []):
                groups[key].append(r)

    # 어느 그룹에도 안 잡힌 자원 — 누락 시 조용히 차단되므로 personal 에 덧붙인다.
    # (덮어쓰면 Personal 카드로 이미 등재된 것들이 지워진다)
    covered = {r for v in groups.values() for r in v}
    existing = ["dash:" + d.name for d in sorted((ROOT / "docs" / "dashboards").iterdir()) if d.is_dir()]
    existing += ["sec:" + sec for sec in SECTIONS if (ROOT / "docs" / sec).is_dir()]
    orphans = [r for r in existing if r not in covered]
    personal = groups.setdefault("personal", [])
    personal.extend(r for r in orphans if r not in personal)
    if orphans:
        print(f"  ! 카드 없는 자원 {len(orphans)}건 -> personal 편입: {orphans}")

    cfg = json.loads(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}
    cfg["groups"] = groups
    CFG.parent.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    total = sum(len(v) for v in groups.values())
    uniq = len({r for v in groups.values() for r in v})
    for k, v in groups.items():
        print(f"  {k:12s} {len(v):3d}")
    print(f"  합계 {total} (중복 제외 {uniq})")
    if external:
        print(f"  외부 링크 {len(external)}건 (통제 불가, 카드 항상 노출):")
        for n, u in external:
            print(f"    - [{n}] {u}")


if __name__ == "__main__":
    main()
