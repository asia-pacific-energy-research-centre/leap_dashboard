# Rebuild the anchor validation section of the Mapping diagnostics page

## Objective

Make the anchor-validation evidence on the Mapping diagnostics page navigable:
one source parent boundary is one check, with fuels and years nested beneath it
as evidence, filterable by source system, comparison scope, economy, scenario,
year, validation axis, and status.

This is a presentation and aggregation task inside `leap_dashboard`. It changes
no mapping semantics and no `leap_mappings` artifact.

## Repository

```text
C:\Users\Work\github\leap_dashboard
```

Read `AGENTS.md` and `docs/handover_mapping_diagnostics.md` first. Read
`leap_mappings/docs/mappings_system.md` before making any claim about what a
number means. Inspect `git status --short` and preserve unrelated changes.

## The problem to fix

The page currently prints a headline tile:

```text
Failed anchor checks   5,467
```

That is a raw detail-row count from `source_parent_anchor_validation.csv`: one
parent boundary that disagrees across 27 fuels and 34 years contributes hundreds
of rows to it. `source_parent_anchor_validation_summary.csv` for the same run
reports failures per comparison scope and source system, and the scopes overlap
(`esto_leap` and `esto_leap_ninth` re-check the same source data;
`esto_extended_*` is a separate basis). Neither number is wrong, but the page
presents the largest available count with no unit and no scope, which reads as
"5,467 broken mappings" when it is not.

## Work

1. Aggregate `source_parent_anchor_validation.csv` to one row per
   (comparison scope, source system, validation axis, economy, parent boundary).
   That grouped row is the check. Keep fuel-level and year-level rows as nested
   evidence, not as headline counts.
2. Replace the headline tile with counts that state their unit and scope
   explicitly — for example "parent boundaries failing, ordinary ESTO basis,
   `esto_leap_ninth`" — and never sum across overlapping comparison scopes.
   `scripts/render_mapping_pipeline_health_report.py` already implements this
   rule in `_anchor_section()`; reuse its wording and its per-scope subtotal
   table rather than inventing a second convention.
3. Add the filters listed in the objective. Prefer explicit controls over hidden
   defaults, consistent with the existing Dataset/Scenario/Year controls.
4. Keep raw parent/child source values visually distinct from mapped Common ESTO
   frontier values. A raw source contradiction (parent is 0 while children are
   non-zero) must not be presented as a missing map.
5. Preserve the reviewed-exception section using the explicit confirmation
   fields independently of numerical status. Confirmed source issues remain
   failures, stay in numerical totals, and are shown separately from
   unconfirmed failures. Confirmation must not be described as proof that the
   mapping is correct or that the source issue caused the anchor failure.
6. Handle a skipped or errored anchor run defensively. If
   `source_parent_anchor_validation_summary.csv` reports `skipped` or an error,
   show that reason prominently. Never render `Failed anchor checks: 0` for a run
   that did not validate anything.

## Existing helpers

`codebase/common_esto_dashboard_mapping_diagnostics.py`:
`_paired_anchor_aggregate_summary()`, `_paired_tree_html()`, `_failure_summary()`,
`_anchor_value_summary()`, and the summary functions near the top of the file.

## Constraints

- The renderer uses a large embedded JavaScript template with post-render string
  replacement. Make targeted edits. If a refactor looks necessary, write a plan
  first rather than folding it into this UI change.
- Keep the page self-contained, and keep the embedded payload filtered to the
  records actually rendered. Do not embed all Common ESTO comparison rows.
- Do not change mapping workbook rows from this repo.
- Do not treat parent, child, and generated rollup rows as one additive total.
- Apply the selected economy consistently to failure tables, reviewed-issue
  tables, exception candidates, and summary cards.

## Validation

1. Add focused tests to `tests/test_mapping_diagnostics_page.py` for every new
   aggregation and interaction, including the skipped-run defensive path.
2. `C:\Users\Work\miniconda3\python.exe -m pytest tests\test_mapping_diagnostics_page.py -q`
3. `C:\Users\Work\miniconda3\python.exe scripts\render_transformation_rollup_diagnostics_prototype.py`
   and review the USA prototype output.
4. State the grouped check count and the raw detail-row count side by side in the
   completion report, so the change in headline meaning is explicit.

## Historical prerequisite worth knowing

The 2026-07-27 artifact generation originally used while drafting this prompt
doubled ordinary-ESTO values for 15 generated rollup flows. That upstream defect
was fixed in `leap_mappings` commit `eb3a293`; run
`common_esto_20260727T113042584213Z` removed the doubling and added a guard.
The completed mappings prompt is no longer present on mappings `master`.
`docs/handover_mapping_diagnostics.md` preserves the incident evidence.

This does not change the layout objective. Do not use any historical anchor
failure count as a permanent test baseline: report grouped-check and raw-detail
counts from the same selected run.
