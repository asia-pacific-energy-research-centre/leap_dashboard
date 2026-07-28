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
Mapping diagnostics implementation now prefers the selected canonical
contract when its manifest exists. It adapts `axis_nodes.csv` into the
read-only tree and filters `value_conformance_diagnostics.csv` to Common ESTO
rows. A selected but invalid contract fails closed; legacy tree artifacts are
used only when no contract manifest has been selected.

The page displays the selected build ID. Registered expanding, non-expanding,
and detached relationships continue to come from the rollup catalogue and
remain separate from the contract's ordinary parent edges.
