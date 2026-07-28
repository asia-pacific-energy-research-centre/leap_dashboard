# Hierarchy/subtotal structural contract

`leap_mappings` owns structural subtotal classification and publishes
`hierarchy_subtotal_contract_v1`. The dashboard is a checking surface; it must
not infer or override parenthood.

Use `codebase/hierarchy_subtotal_contract_loader.py` with an explicitly
selected contract directory and expected build/input hashes. A missing,
invalid, stale, or mismatched selection fails without falling back to legacy
tree files.

The Mapping diagnostics surface must display structure and value conformance
separately:

```text
Structural subtotal: YES
Children add to parent in this context: NO
```

Ordinary hierarchy edges must be shown separately from expanding,
non-expanding, detached, alias, and synthetic relationships. The active
Mapping diagnostics implementation had an uncommitted owner diff during the
loader migration, so wiring the loader into that page remains an explicit
follow-up rather than overwriting the active work.

