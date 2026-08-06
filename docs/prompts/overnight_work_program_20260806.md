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
4. **`leap_mappings` working tree is clean as of session start.** Its seven
   previously-uncommitted files were committed to branch
   `claude/common-esto-mapping-docs` in two separable commits (`85facf1` code,
   `47e2526` generated artifacts). That branch — not `master` — is the base for
   any `leap_mappings` work tonight.
5. **Keep going.** This program is designed to survive surprises unattended. If
   something is ambiguous, missing, or mildly broken: **make the most reasonable
   assumption, write it in the Assumptions register, and carry on.** Do not halt
   the night over a path, a dependency, a flaky check, or a judgement call.
   Finishing six items with four recorded assumptions beats finishing one.
6. **The one thing that must never happen is a wrong number shipped quietly.**
   That is the only hard line. Everything else is recoverable tomorrow; a
   silently wrong total is not, because nobody will know to look.
7. If a work item genuinely cannot proceed, **skip it and move to the next**.
   Never skip the whole program.

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
- `leap_dashboard`: `pytest tests` green — **145 passed, 2 skipped** at session
  start.
- `scripts/check_common_esto_dashboard_publish_ready.py` passes.
- `scripts/analyze_common_esto_dashboard_page_noise.py` flags **0**.

**`leap_mappings` test baseline — 496 passed, 6 pre-existing failures on
`master`.** Do not treat these as regressions and do not try to fix them:

```text
test_apply_partitioned_common_esto.py::test_chunked_cache_reuse_and_result_equivalence
test_balance_flow_single_axis_mappings.py::test_esto_extended_detail_axes_are_maintained_even_when_zero_only
test_separate_axis_mapping_exploration.py::test_leap_balance_structure_derives_report_rows_and_fuel_catalogue
test_synthetic_reference_rows_sync.py::test_the_loader_matches_the_leap_initialisation_copy
test_target_share_allocation.py::test_target_dataset_share_uses_target_component_values
test_target_share_allocation.py::test_target_dataset_share_counts_unique_targets_when_source_rows_repeat
```

Two more (`test_leap_mapping_refresh_workflow.py`,
`test_leap_results_dashboard_balance_crosswalk.py`) fail at *collection* because
a LEAP balance-export workbook is absent; run with `--ignore` for both.

The bar for `leap_mappings` work is therefore **no new failures beyond these
six**, not a green suite.

---

## Deliverables — four artifacts to hand over at the end

The work items are the means; these are what the owner actually wants to look
at. Collect them under `outputs/overnight_20260806/` and list their paths in the
final report. **A work item is not finished until its deliverable exists.**

### D1 — A rendered `leap_dashboard` output with emissions

Full render of **20USA and 02BD**, with the Emissions page produced by the new
system (factors published by `leap_mappings` after W5, not resolved in dashboard
code). Hand over the `dashboards/` folder path and confirm `emissions.html`
opens and its charts draw.

Depends on: W2–W5.

### D2 — A locally run web app showing emissions

The point is to prove the Space will show emissions, not just that the dashboard
does. Both prerequisites are confirmed present:

- `gradio 5.44.1` is installed and matches the Space's `sdk_version`.
- LEAP balance exports exist at
  `C:/Users/Work/github/leap_initialisation/data/leap balances exports/20_USA/`
  (`0805 REF.xlsx`, `0805 TGT.xlsx`) and for `02_BD`.

Steps:

1. Refresh the runtime **locally from the working branches** via
   `leap_review_tools/scripts/refresh_runtime.py`, including the files Phase 0
   identified. Do not commit a refreshed runtime into `leap_review_web_app` and
   do not deploy — this is a local proof only.
2. Run the Gradio app locally, upload `20_USA/0805 REF.xlsx`, and confirm the
   Emissions page and its nav chip appear in the generated dashboard.
3. Capture a screenshot and the local output path.

If the manifest cannot be satisfied from unmerged branches, **do not merge and
do not stop** — copy the needed files into the local runtime by hand. This is a
local proof, not a deploy, so hand-staging is legitimate. Record which entries
could not be satisfied properly; that list is the remaining work to deploy.

Depends on: W2, W5, and the Phase 0 file list.

### D3 — Mapping CSVs a non-coder can use

The published mapping outputs, made genuinely usable by someone who does not
write code. Not just correct — *legible*.

- `source_to_common_esto_map.csv` (W6) — any dataset → common categories.
- The common-axis emissions factor table (W5, B1).

Requirements, all of which matter more than they sound:

- **Human-readable labels in every row**, not just IDs. A reader must never have
  to join another file to understand a row.
- **One row per mapping**, sorted stably (source system, then source flow, then
  source product), so it diffs cleanly and reads top to bottom.
- **`derived_from` present** on every factor row.
- **A short `README.md` beside them** — what each file is, what one row means,
  which column to filter on, and the one thing not to do (do not sum rows whose
  `is_subtotal` is true, and do not re-split a source aggregate).

### D4 — The importable merger from `leap_mappings`

A supported, importable function that applies the mappings — the thing that
makes "one merge" real for a consumer:

```python
from mapping_tools import <merger>
common_df = <merger>(source_values_df, source_to_common_map_df)
```

Requirements:

- Importable without dragging the pipeline's orchestration or QA modules; check
  the import closure.
- A docstring stating the contract: what goes in, what comes out, and that it
  never allocates.
- A worked example in the `README.md` from D3, runnable as-is.
- Covered by a test asserting it reproduces the current
  `common_esto_comparison_data.csv` for at least one economy.

Depends on: W6 producing the map. This is Phase C step 2, promoted into scope
(owner request, 2026-08-06); Phase C steps 3–8 — cache, dashboard switch-over,
retiring the old path — remain Deferred.

---

## Work items

### W0 — Set up guard rails *(do first; later items compare against it)*

Plan reference: "Before/after equivalence tests", T0 and T1.

1. Commit the current branch state so there is a known starting point.
2. Write and run **T0, the determinism guard**: render 20USA twice with no code
   change, assert every generated CSV equal after sorting.
   If T0 fails, **do not stop** — fall back to sorted comparison with a `1e-9`
   tolerance, record it in the Assumptions register, and carry on.
3. Write `scripts/capture_common_esto_baseline.py` and capture **T1 baselines**
   for **20USA and 02BD** into `tests/fixtures/common_esto_dashboard/baseline_<economy>/`
   — normalised `chart_manifest.csv`, `emissions_by_sector_and_fuel.csv`,
   `emissions_factor_resolution.csv`, `page_assignment_summary.csv`, page
   inventory, and the T3 bundle fingerprint.
4. Commit the baselines.

**Capture the baselines before any code change** — a "before" snapshot cannot be
recovered once the code has moved. If some part of the capture will not work,
capture what you can, record the gap, and continue.

**Done when:** baselines exist for both economies and are committed.

---

### W1 — Explain the 3,347 unmapped LEAP links *(investigation only; gates nothing)*

Plan reference: Phase C, step C0.

Of 6,335 structural LEAP links in `energy_balance_relationships.csv`, **3,347
have no common row** in `esto_leap_ninth`. The 9th has zero such links.

Determine whether any of those LEAP source pairs **carry real non-zero values**
in the LEAP results. If they do, a direct native→common map would drop that data,
so it needs to be excluded explicitly and listed rather than silently missed.

No code changes. Produce a written finding with counts and examples.

**Done when:** the answer is recorded, either way. This does **not** block W6 —
if some links carry real values, build the map anyway, exclude those pairs, and
emit a coverage CSV listing them. The finding is what matters, not the gate.

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

### W5 — Phase B: move factor resolution into `leap_mappings` *(owner-approved unsupervised, 2026-08-06)*

Plan reference: Phase B, and test T5.

Work on branch `claude/common-esto-mapping-docs` in `leap_mappings`.

1. Move the 9th factor CSV and `emissions_factor_sets.json` into
   `leap_mappings/config/`.
2. Move the resolution logic out of
   `leap_dashboard/codebase/common_esto_dashboard_emissions.py` — subfuel
   collapse, `_unallocated` aliasing, `prefer_specific_then_mean` conflict
   resolution, the common-axis join — into `leap_mappings` beside
   `build_common_esto_structure.py`. This clears the duplicate-implementation
   debt. Reuse the existing conflict rule; do not write a second one.
3. Publish **B1** (factors on the common ESTO axis, 54 rows) and **B2**
   (ESTO-product-keyed and LEAP-fuel-keyed sets). Every published artifact gets
   a `derived_from` column, valued `ninth`.
4. Make the derivation source a **config parameter**, not a hardcoded path, so
   LEAP can later derive from ESTO via `leap_fuel_to_esto` (a clean 1:1, 70 of
   70) when real ESTO factors arrive.
5. Leave the dashboard consuming the published table via a single merge.

**T5 is the gate:** `emissions_factor_resolution.csv` must be byte-identical in
content after the move — same factors, same `factor_source_keys`, same
`esto_components`. That is the whole proof this was a relocation and not a
rewrite. 20USA 2022 must still be 3,443 Mt CO2e.

Do **not** relax the `native_unit == "PJ"` assertion or register emissions
datasets tonight — that is the part of Phase B that changes pipeline behaviour,
and it should follow W3 landing.

**Done when:** T5 passes, 3,443 holds, both suites at their baselines, committed
to branches in both repos.

---

### W6 — Phase C map + importable merger

Plan reference: Phase C, step 1.

Generate `source_to_common_esto_map.csv` in `leap_mappings` from
`energy_balance_relationships.csv` composed with `esto_to_common_esto_map.csv`,
per scope, participating sources only. Assert zero fan-out at the common level
while generating and fail loudly otherwise.

Work on branch `claude/common-esto-mapping-docs`.

Then **publish the importable merger (D4)** — Phase C step 2, promoted into
scope. One merge plus an aggregation, taking native source values and the map.
Check its import closure so it does not drag orchestration or QA modules in.

Stop there. Phase C steps 3-8 — cache layer, dashboard switch-over, retiring the
prebuilt path — remain Deferred.

Produce **D3** (legible CSVs + xlsx + README) as part of this item.

**Done when:** the map generates, fan-out assertion passes, committed to a
`leap_mappings` branch.

---

## Deferred — explicitly not tonight

| Item | Why |
|---|---|
| Any merge to `master` in either repo | Owner decision: merge only once the whole program is proven |
| **Any `git push`, and any Space deploy** | Not authorised. The owner said "almost happy" — that is not a yes. Outward-facing and hard to reverse; needs an explicit go-ahead |
| Relaxing `native_unit == "PJ"` / registering emissions datasets | The behaviour-changing half of Phase B; follow W3 |
| Phase 0 manifest edits, runtime refresh, Space deploy | Manifest pins commits and sha256 hashes; needs a master merge first |
| Phase C steps 3–8 — cache, dashboard switch-over, retiring the prebuilt path | Too large for one unattended run; step 2 (the merger) is now in scope as D4 |
| Flags on the mapping outputs | Denormalises onto the Phase C map; sequenced with Phase C |
| Fixing `render_full_mapping_tree_explorer.py` | Pre-existing, unrelated |

---

## When something goes wrong

Default is **assume and continue**. Only one situation stops an item, and
nothing stops the whole program.

### The single hard line — revert the item, keep going

**A named invariant moves and you cannot explain why.** Above all
20USA 2022 ≠ 3,443 Mt CO2e.

Do not update the baseline to match. Revert *that item's* commits, record it
under Findings, move to the next item. The rest of the night still runs.

If you *can* explain it and the explanation is sound — for example Phase B
legitimately recomputing a factor — record the before/after and the reason, and
continue.

### Everything else — assume, record, continue

| Situation | What to do |
|---|---|
| **T0 determinism guard fails** | Do not stop. Fall back to comparing sorted content with a `1e-9` tolerance, note it, continue. |
| **W1 finds unmapped LEAP links with real values** | Do not block W6. Build the map anyway, exclude those pairs, emit a coverage CSV listing them, and report. The finding is the value. |
| **Fan-out appears at the common level** | Do not add allocation. Keep the affected pairs out of the map, list them in the coverage CSV, continue. |
| **A path, file or dependency is missing** | Look for the obvious equivalent. If there is one, use it and record the substitution. If not, skip that item. |
| **The manifest cannot be satisfied for D2** | Copy the needed files into the local runtime by hand. It is a local proof, not a deploy — hand-staging is fine and the blocked entries are themselves the deliverable. |
| **A test outside the named baselines fails** | Check whether it fails on the branch point too. If yes, it is pre-existing — note and continue. |
| **An API or column name is unspecified** | Choose the clearest option, record it, continue. Naming is reversible. |
| **Scope would grow into `leap_mappings` pipeline stages** | Stop growing, keep what is done, note where the line was drawn. |

### Assumptions register — fill this in

Every assumption made under the rules above goes here, so the morning review is
about decisions rather than archaeology.

| # | Item | Assumption made | Why | How to reverse |
|---|---|---|---|---|
| | | | | |

---

## Run log — fill in as you go

| Item | Status | Commit | Notes / findings |
|---|---|---|---|
| W0 guard rails | | | |
| W1 C0 gate | | | |
| W2 Phase 0 prep | | | |
| W3 measure-aware | | | |
| W4 frontier | | | |
| W5 Phase B | | | |
| W6 map + merger | | | |
| D1 dashboard output | | | |
| D2 local web app | | | |
| D3 mapping CSVs | | | |
| D4 importable merger | | | |

---

## Final report — produce this at the end

1. **What changed**, per repo, per branch, with commit hashes.
2. **What was verified** — which of T0–T8 ran, and their results.
3. **Invariants**: state the 20USA 2022 emissions total and the test counts
   explicitly, not "unchanged".
4. **Findings** — especially W1's answer, and any coverage CSV of excluded
   mapping pairs.
5. **The Assumptions register**, filled in — every assumption made, and how to
   reverse it. This is the main thing to review in the morning.
6. **The four deliverables** — D1-D4 — with their paths, and a screenshot for
   D2. Say explicitly if any could not be produced and why.
7. **What is ready to merge**, and what still needs supervision.
8. Confirm **nothing was merged to master, nothing was pushed, and nothing was
   deployed.**
