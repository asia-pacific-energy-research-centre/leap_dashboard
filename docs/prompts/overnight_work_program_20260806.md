# Overnight work program — 2026-08-06

Single operational runbook for tonight's unattended session. Work items, gates,
verification, and the report template are all here.

**Design detail lives in
`docs/prompts/measure_aware_dashboard_and_mapping_inversion_plan.md`.** This file
says *what to do tonight and in what order*; that file says *why, and what the
target shape is*. Read the relevant plan section before starting each item.

---

## Rules of engagement

1. **Nothing is merged to `master` in either repository tonight.** All work stays
   on branches. Merging happens later, in a supervised session, once the whole
   program is proven. This means every item that requires a master merge is
   explicitly out of scope — they are listed under Deferred.
2. **Commit to the working branch often.** Small, verified checkpoints. Never
   push.
3. **A number moving is a stop condition, not a baseline to update.** See
   Verification below.
4. **`leap_mappings` has pre-existing uncommitted changes that belong to someone
   else** — at time of writing: `apec_anchor_validation.py`,
   `apply_common_esto_structure.py`, `structural_resolver.py`, and two config
   files. Do not commit, revert, stash, or refactor around them. If a required
   change collides, **stop and report**.
5. **If a work item's gate fails, stop that item and move to the next one.** Do
   not work around a gate. Record it in the log.
6. When in doubt, prefer producing a *finding* over producing a *change*.

---

## Environment

```bash
# Python
C:\Users\Work\miniconda3\python.exe

# REQUIRED in a worktree — REPO_ROOT.parent resolves to the worktrees directory,
# so every upstream path silently misses without this.
LEAP_MAPPINGS_ROOT=C:/Users/Work/github/leap_mappings
```

Reference commands:

```bash
LEAP_MAPPINGS_ROOT=C:/Users/Work/github/leap_mappings COMMON_ESTO_ECONOMIES=20_USA C:/Users/Work/miniconda3/python.exe codebase/common_esto_dashboard_workflow.py
```

```bash
C:/Users/Work/miniconda3/python.exe -m pytest tests -q
```

Timings to budget for: ~3–5 min per economy render, ~5 min for the full suite.

**Known and out of scope:** `scripts/render_full_mapping_tree_explorer.py`
crashes in a worktree (it does not honour `LEAP_MAPPINGS_ROOT`). It runs after
the dashboard render and before `publish_to_docs`, so renders and page output are
unaffected. Do not fix it.

---

## Verification — the standard every item is held to

Renders are **content-deterministic but not byte-deterministic**: two identical
runs differ in ~15 of 19 output files by row ordering alone (Python per-process
string hash randomisation). Therefore:

- **Never** compare file bytes, hashes, or `git diff` on generated outputs.
- **Always** sort by all columns and reset index before comparing.

Named invariants that must hold after every item:

- 20USA 2022 total emissions = **3,443 Mt CO2e**, equal across LEAP, ESTO, 9th.
- `pytest tests` green (**145 passed, 2 skipped** at start of session).
- `scripts/check_common_esto_dashboard_publish_ready.py` passes.
- `scripts/analyze_common_esto_dashboard_page_noise.py` flags **0**.

---

## Work items

### W0 — Set up guard rails *(blocking; everything depends on it)*

Plan reference: "Before/after equivalence tests", T0 and T1.

1. Commit the current branch state so there is a known starting point.
2. Write and run **T0, the determinism guard**: render 20USA twice with no code
   change, assert every generated CSV equal after sorting.
   **If T0 fails, stop the entire program and report.** Every later comparison
   depends on it.
3. Write `scripts/capture_common_esto_baseline.py` and capture **T1 baselines**
   for **20USA and 02BD** into `tests/fixtures/common_esto_dashboard/baseline_<economy>/`
   — normalised `chart_manifest.csv`, `emissions_by_sector_and_fuel.csv`,
   `emissions_factor_resolution.csv`, `page_assignment_summary.csv`, page
   inventory, and the T3 bundle fingerprint.
4. Commit the baselines.

**This must complete before any code change.** A "before" snapshot cannot be
recovered once the code has moved.

**Done when:** T0 passes, baselines exist for both economies and are committed.

---

### W1 — Phase C0 gate: explain the 3,347 unmapped LEAP links *(investigation only)*

Plan reference: Phase C, step C0.

Of 6,335 structural LEAP links in `energy_balance_relationships.csv`, **3,347
have no common row** in `esto_leap_ninth`. The 9th has zero such links.

Determine whether any of those LEAP source pairs **carry real non-zero values**
in the LEAP results. If they do, a direct native→common map would silently drop
data, and Phase C needs rethinking.

No code changes. Produce a written finding with counts and examples.

**Done when:** the answer is recorded in the log as one of —
*(a)* all unmapped links are value-less or out of scope → Phase C viable;
*(b)* some carry real values → **Phase C blocked**, record which.

This is deliberately early: it is cheap, needs no changes, and it is the only
finding that can invalidate a whole phase.

---

### W2 — Phase 0 code preparation *(deploy steps are Deferred)*

Plan reference: Phase 0.

Tonight covers only the code preparation. Manifest edits, runtime refresh and
deploy all require a master merge and are Deferred.

1. Switch the common-axis lookup in
   `codebase/common_esto_dashboard_emissions.py` from
   `esto_to_common_esto_map.csv` to `common_esto_rows.csv`. These give
   set-identical product→common pairs (verified 2026-08-06, zero differences),
   and `common_esto_rows.csv` is already a runtime asset, so this removes one
   manifest entry for free.
2. Add an explicit factor-config path argument so the module does not rely on
   `REPO_ROOT = __file__.parents[1]`. That resolves in the Gradio runtime layout
   but not in the portable staging, which flattens with
   `strip_prefix = "codebase"`.
3. Verify: factor table unchanged, 20USA 2022 = 3,443 Mt CO2e, suite green.

**Done when:** both changes land, all named invariants hold, committed.

---

### W3 — Phase A steps 1–4: measure-aware dashboard *(main event)*

Plan reference: Phase A, steps 1–4.

1. Add `measure` and `unit` columns to the dashboard frame, defaulting to
   `energy` / `PJ` so existing inputs are unchanged. Source the unit from the
   dataset registry's `native_unit` rather than a new registry.
2. Replace the ~24 hardcoded `"PJ"` literals with the carried unit.
3. Gate the energy-balance machinery — sign semantics, supply/TFC/TFEC
   identities, `excluded_flow_code_prefixes` — to `measure == energy` only.
4. Pair comparisons on `(source_system, measure)` so an emissions series is never
   diffed against an energy series.

**Verify against T1 baselines:** energy charts must be *identical*, not merely
similar. This item touches everything, so the baseline comparison is the whole
safety argument.

**Done when:** T2/T3/T4/T7 all match baseline, suite green, committed.

---

### W4 — Phase A step 6: frontier parenthood onto the contract

Plan reference: Phase A, step 6, and test T6.

Replace the code-expression parsing in
`common_esto_dashboard_emissions.select_non_overlapping_rows` with the declared
hierarchy from
`leap_mappings/results/hierarchy_subtotal_contract/current/axis_nodes.csv`
(`dataset_id = common_esto`), via the existing
`codebase/hierarchy_subtotal_contract_loader.py`.

Two parts stay in the dashboard: **per-source presence**, and the **three labels
outside the declared tree** (`16.03-16.05,17 Other sector including non-energy
(all demand aggregate)`, `02.01-02.08 Coal products`,
`06.03-06.04 Crude oil and NGL`).

**Write T6 first.** Assert the retained *set* of
`(source_system, scenario, common_flow_label, common_product_label)` tuples is
unchanged — assert on the set, **not** on totals, because totals can coincide
while the wrong rows are retained. T6 is the test that would have caught the
original 4,838-vs-3,443 bug.

**Done when:** T6 passes, 3,443 holds, suite green, committed.

---

### W5 — Stretch: Phase C map generation *(only if W1 returned "viable")*

Plan reference: Phase C, step 1.

Generate `source_to_common_esto_map.csv` in `leap_mappings` from
`energy_balance_relationships.csv` composed with `esto_to_common_esto_map.csv`,
per scope, participating sources only. Assert zero fan-out at the common level
while generating and fail loudly otherwise.

**Branch `leap_mappings` first**, and heed rule 4 about the pre-existing changes
there. Generate the artifact and its generator script only — do **not** move the
factor resolution upstream tonight (that is Phase B, Deferred).

**Done when:** the map generates, fan-out assertion passes, committed to a
`leap_mappings` branch.

---

## Deferred — explicitly not tonight

| Item | Why |
|---|---|
| Any merge to `master` in either repo | Owner decision: merge only once the whole program is proven |
| Phase 0 manifest edits, runtime refresh, Space deploy | Manifest pins commits and sha256 hashes; needs a master merge first |
| Phase B — moving factor resolution into `leap_mappings` | Moves files between repos and publishes artifacts the Space consumes; wants supervision |
| Phase C steps 2–8 — apply API, cache, dashboard switch-over | Depends on W5 and on Phase A landing; too large for one unattended run |
| Flags on the mapping outputs | Denormalises onto the Phase C map; sequenced with Phase C |
| Fixing `render_full_mapping_tree_explorer.py` | Pre-existing, unrelated |

---

## Stop conditions — halt the item and report

1. **T0 fails** → stop the entire program.
2. **Any named invariant moves** — especially 20USA 2022 ≠ 3,443 Mt CO2e.
3. **W1 finds unmapped LEAP links carrying real values** → W5 is blocked.
4. **Fan-out appears at the common level** when generating the map → upstream
   structure bug; report, never add allocation downstream.
5. **A collision with the pre-existing `leap_mappings` changes.**
6. **Scope would grow** into `leap_mappings` pipeline stages beyond the named
   outputs.

---

## Run log — fill in as you go

| Item | Status | Commit | Notes / findings |
|---|---|---|---|
| W0 guard rails | | | |
| W1 C0 gate | | | |
| W2 Phase 0 prep | | | |
| W3 measure-aware | | | |
| W4 frontier | | | |
| W5 map (stretch) | | | |

---

## Final report — produce this at the end

1. **What changed**, per repo, per branch, with commit hashes.
2. **What was verified** — which of T0–T8 ran, and their results.
3. **Invariants**: state the 20USA 2022 emissions total and the test counts
   explicitly, not "unchanged".
4. **Findings** — especially W1's answer, which determines whether Phase C is
   viable.
5. **Stop conditions hit**, and where each was left.
6. **What is ready to merge**, and what still needs supervision.
7. Confirm **nothing was merged to master and nothing was pushed.**
