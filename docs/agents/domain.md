# Domain Docs

**Layout:** Single-context

## Files

- `CONTEXT.md` — project domain language, glossary, key concepts (at repo root)
- `docs/adr/` — architectural decision records

## Consumer Rules

1. Read `CONTEXT.md` at the start of any task touching domain logic.
2. Check `docs/adr/` for past decisions before proposing architectural changes.
3. If `CONTEXT.md` does not exist yet, create it using `/grill-with-docs`.
4. ADR format: `docs/adr/NNNN-title.md` (e.g. `docs/adr/0001-use-firebase.md`).
