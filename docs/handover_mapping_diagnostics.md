# Handover: Mapping diagnostics development

Updated: 2026-07-27

## Purpose

The Mapping diagnostics page is a read-only, static HTML diagnostic page for
understanding how raw ESTO, 9th Outlook, LEAP, and Common ESTO structures relate.
It is intentionally separate from the production chart pages: its job is to make
mapping and hierarchy evidence inspectable, not to present final model results.

Current prototype output:

```text
outputs/prototypes/transformation_rollup_diagnostics/dashboards/mapping_diagnostics.html
```

The production dashboard also renders the same page under each economy's
`dashboards/` output directory.

## Main entry points

| Area | File | Role |
| --- | --- | --- |
| Diagnostics page renderer | `codebase/common_esto_dashboard_mapping_diagnostics.py` | Builds the self-contained HTML, rollup cards/SVG, anchor sections, and mapping QA tables. |
| Production dashboard workflow | `codebase/common_esto_dashboard_workflow.py` | Loads Common ESTO data, invokes the diagnostics page renderer, and adds the page to dashboard navigation. |
| Lightweight USA prototype renderer | `scripts/render_transformation_rollup_diagnostics_prototype.py` | Regenerates the page above without running the entire dashboard. |
| Full mapping tree explorer | `scripts/render_full_mapping_tree_explorer.py` | Renders the separate interactive original-source / ESTO / Common ESTO tree explorer. |
| Diagnostics tests | `tests/test_mapping_diagnostics_page.py` | Focused renderer tests. |

The mapping inputs and generated Common ESTO data live in the sibling repo:

```text
C:\Users\Work\github\leap_mappings
```

Read `leap_mappings/docs/mappings_system.md` before changing mapping semantics.

## Current diagnostics page

The page currently contains:

- A short guide to hierarchy/anchor terminology.
- Collapsible **All rollup boundaries** cards, showing parent, children,
  siblings, contributors, rollup mode, and reconciled values.
- A zoomable/pannable **All sector rollup structure** SVG. It includes all
  Common ESTO flow hierarchy levels and all registered ESTO rollup boundaries.
- Collapsible hierarchy-failure, aggregate mismatch, exception, and mapping
  coverage sections.
- Paired raw-source versus mapped-Common-ESTO views for NINTH and LEAP anchor
  cases.
- A separate **Full mapping tree explorer** page linked from the dashboard.

The SVG and rollup-boundary cards share Dataset, Scenario, and Year controls.
Values are green only when a rollup target equals the listed contributors within
tolerance; red means a mismatch; unavailable values are not treated as failures.

## ESTO Extended behaviour

The diagnostics page now uses ordinary ESTO by default.

- **Include ESTO Extended** is a checkbox above the SVG.
- When enabled, `ESTO_EXTENDED` becomes available in the Dataset selector.
- Selecting a source displays that source alone. Ordinary and Extended ESTO are
  never summed together for a reconciliation check.
- The page includes separately labelled raw helper values (`ESTO_RAW` and
  `ESTO_EXTENDED_RAW`) so rollup contributors can be shown even when they do
  not exist as standalone Common ESTO flow labels.

The page payload is deliberately limited to flow labels that appear in the SVG
or rollup boundaries. Do not embed all Common ESTO comparison rows in the HTML:
the Extended scopes make that static file unnecessarily large.

The Extended source data will be fully correct only after the mapping-pipeline
artifact is rebuilt using the source-identity fix in `leap_mappings` commit
`eb3a293` (`codex: preserve ESTO Extended rollup source identity`). Before that
rebuild, existing artifact values can still reflect the earlier duplicate-label
problem.

## Recent fixes and commits

| Repo | Commit | Change |
| --- | --- | --- |
| `leap_mappings` | `eb3a293` | Generated ESTO Extended rollups now retain `ESTO_EXTENDED`, rather than leaking into ordinary ESTO comparison scopes. |
| `leap_dashboard` | `f128456` | Added the diagnostics-page Extended toggle, raw Extended contributor values, compact payload filtering, test coverage, and documentation. |

The diagnostic found the original bug using `20_USA`, 2023 electricity plants:
raw contributors totalled `-17,096.58`, while the Common ESTO target was exactly
double at `-34,193.16`. The dashboard was reporting the underlying Common ESTO
artifact correctly; it was not double-counting in the browser.

## Additive update: current anchor and mapping-integrity state (2026-07-27)

Do not replace the rollup/Extended work above. This section records additional
Mapping diagnostics work and the current mapping-pipeline provenance.

### Fresh anchor results are now available

`leap_mappings` has since completed a real source-parent anchor-validation run:

```text
run_id: common_esto_20260727T034511926826Z
input: results/common_esto/common_esto_comparison_data.csv
detail status counts: 183,367 passed; 5,467 failed; 1,156,204 skipped
```

The summary includes the new Extended scopes:

- `esto_extended_leap` (LEAP: 183 failed);
- `esto_extended_leap_ninth` (LEAP: 175 failed; NINTH: 2,286 failed);
- ordinary ESTO scopes remain separately available.

This supersedes the earlier `MemoryError`-skipped anchor run. The older
dashboard batch was rendered before this result, so regenerate the dashboard
before interpreting its anchor cards or failure counts as current.

The renderer still needs a defensive status treatment: if a future anchor run
is skipped, do not render `Failed anchor checks: 0` as though validation passed.
Read `source_parent_anchor_validation_summary.csv` and show the skipped/error
reason prominently instead.

### Mapping-integrity sections added to the renderer

`common_esto_dashboard_mapping_diagnostics.py` also now renders the following
conditional tables inside Direct mapping coverage review:

- **Mapped target ancestor overlaps**: one source pair reaches both a Common
  ESTO target and its target-tree descendant.
- **Source parent and child mapped to one target**: one Common ESTO target is
  reached by both a source-tree parent and its descendant. This is a review
  signal, not proof that the routes should be added.
- **Active many-to-many mapping conflicts**: sourced from the canonical
  `leap_mappings/results/maintenance/many_to_many_conflicts.csv` artifact.

These are mapping-workbook integrity checks. They are global and should remain
visible with an explicit "mapping-workbook integrity" label when an ESTO
Extended view is selected; they do not become Extended-specific merely because
the comparison basis changes.

### Follow-up dashboard backlog

The next diagnostics with the strongest value are separate from the anchor-card
layout and should be added only from their canonical mapping-pipeline artifacts:

1. **Structural compilation health**: concise counts and conditional tables for
   `qa_ambiguous_structural.csv` and `qa_unresolved_structural.csv`, while
   showing conflicting/cyclic/duplicate states as clean only when their files
   prove that.
2. **Non-expanding rollup integrity**: expose violations from
   `qa_common_esto_non_expanding_frontier_check.csv`, not every successful
   check.
3. **Material non-zero mapping gaps**: rank
   `leap_missing_esto_absent_nonzero_pairs_actionable.csv` by absolute value
   and affected economies/years, rather than showing an unranked coverage list.
4. **Candidate readiness**: display review-only, non-workbook candidates with
   evidence and destination sheet. Never add them to the workbook from the
   dashboard.
5. **Crosswalk target conflicts and duplicate mappings**: first classify
   intentional duplicates versus accidental duplicates; do not present all raw
   duplicate rows as errors.

For a future ESTO Extended checkbox, basis-dependent diagnostics must use real
parallel Extended pipeline artifacts/scopes. Do not make a control merely
relabel ordinary ESTO values. The global workbook-integrity sections above stay
visible for both bases.

## How to render and test

Use the Windows Miniconda interpreter:

```powershell
C:\Users\Work\miniconda3\python.exe -m pytest tests\test_mapping_diagnostics_page.py -q
C:\Users\Work\miniconda3\python.exe scripts\render_transformation_rollup_diagnostics_prototype.py
```

The prototype renderer chunk-reads large files. It is safe for a focused page
render, but it is not a replacement for rebuilding Common ESTO artifacts.

Avoid running the full ESTO Extended pipeline merely to inspect this page; that
has previously caused memory pressure. When the mapping artifacts must be
corrected, rebuild them in the `leap_mappings` workflow first, then rerender the
dashboard.

## Next development work

### 1. Anchor validation section

The current anchor sections are evidence-rich but still hard to navigate. The
next agent should:

1. Start from `source_parent_anchor_validation.csv`,
   `source_parent_anchor_child_context_values.csv`, and
   `source_parent_anchor_mapped_component_context_values.csv` in
   `leap_mappings/results/tree_structure/`.
2. Keep one parent boundary as one check/failure; fuels and years should be
   evidence nested beneath it rather than headline failure counts.
3. Add clear filters for source system, comparison scope, economy, scenario,
   year, validation axis, and status.
4. Keep raw parent/child values visually distinct from mapped Common ESTO
   frontiers. Do not imply that a source-data contradiction is a missing map.
5. Preserve the existing reviewed-exception section. Exceptions must remain
   visible and must not silently disappear from the evidence.

Useful current helpers are `_paired_anchor_aggregate_summary()`,
`_paired_tree_html()`, and the summary functions near the top of
`common_esto_dashboard_mapping_diagnostics.py`.

### 2. Full mapping tree explorer

The explorer already offers source-tree selection, year/scenario selectors,
mapping-label modes, node search, and an ESTO Extended preference checkbox.
The next agent should make its relationship to the diagnostics page clearer:

1. Use the same source terminology and Extended inclusion/exclusion semantics
   as Mapping diagnostics.
2. Make it obvious that the three columns are: original source hierarchy,
   original ESTO component hierarchy, and Common ESTO representation.
3. Show mapping routes and cardinality warnings without presenting repeated
   routes as additive values.
4. Add a direct link from a rollup boundary/card to the relevant explorer node
   only if the link can carry a stable flow identifier and preserve the selected
   source/year/scenario context.
5. Keep the tree explorer separate from the page's rollup arithmetic: it is a
   structural navigation tool, not a second total-calculation engine.

### 3. General page quality

- Prefer small, explicit controls over hidden default behaviours.
- Keep static HTML self-contained, but filter embedded records to the elements
  actually rendered.
- Do not change mapping workbook rows from the dashboard repo.
- Do not treat parent, child, and generated rollup rows as one additive total.
- Add focused renderer tests for every new interaction and rerender the USA
  prototype for visual review.

## Known limitations

- The mapping diagnostics renderer currently uses a large embedded JavaScript
  template and post-render string replacement. Make targeted edits and retain
  the focused tests; a larger refactor should be planned rather than slipped
  into a UI change.
- Browser automation may be blocked for `file:///` dashboard outputs. Static
  HTML checks, focused tests, and manual refresh in the in-app browser are the
  current verification route.
- The earlier rendered artifacts may contain stale values from before the
  `leap_mappings` Stage 3 rebuild after commit `eb3a293`. The current mapping
  outputs have been rebuilt, but each dashboard economy must be rerendered to
  consume them.
