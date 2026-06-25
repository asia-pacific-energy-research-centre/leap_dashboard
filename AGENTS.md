# AGENTS.md — LEAP Dashboard workflow guide for agents

These are project-level instructions for Claude Code, Codex, and similar agents.

---

## REQUIRED: how to validate any code change

> **Before reporting a task complete, you must run the workflow in re-render-only mode and check the comparison dashboard. Do not skip this step.**

The existing `outputs/<token>/` directory — produced by the most recent full human run — is the baseline. You do **not** need to run the full pipeline to produce a "before" snapshot. Instead:

1. **Set re-render-only mode** in `leap_results_dashboard_workflow.py` before running. This skips the slow Excel and projection-CSV reads and only re-renders from the already-computed comparison data: `STAGE_EXTRACT = False`, `STAGE_COMPARE = False`, `STAGE_WRITE_OUTPUTS = False`, `STAGE_WRITE_COVERAGE = False`, `STAGE_RENDER_DASHBOARDS = True`.

2. **Run the workflow** (`codebase/leap_results_dashboard_workflow.py`). Before touching the chart bundles, it automatically snapshots the existing bundles as the baseline. After re-rendering, it writes the comparison site.

3. **Open `outputs/<token>/comparison/index.html`.** Pages are ranked by magnitude of change — biggest changes first, unchanged pages greyed out.

4. **Click a changed page.** Charts show the new series in their original colors and formats, with the previous run's series overlaid as faded dotted "(prev)" lines in the same color. Line charts show faded matching dots. Stacked-area charts show the old stack boundaries as dotted cumulative lines so the area shift is immediately readable.

5. **Check `outputs/<token>/comparison/comparison_summary.csv`** for the numeric delta table (`page`, `chart_key`, `trace`, `status`, `max_abs_delta`, `max_delta_year`, `series_scale`). Statuses: `unchanged`, `changed`, `trace_added`, `trace_removed`, `chart_added`, `chart_removed`.

**If only the expected charts changed, and by the expected amount, the change is safe to report as complete.**

**If unexpected charts changed:** `comparison_summary.csv` identifies the sheet/fuel/trace. Cross-reference with `supporting_files/checks/comparison_issue_summary.csv` to check whether the gap was pre-existing.

**If no charts changed when you expected them to:** make sure `STAGE_RENDER_DASHBOARDS = True` and that your code change is in a path that the renderer actually calls, not an earlier stage you skipped.

### Provenance and staleness check

Every workflow run writes `outputs/<token>/build_provenance.json` recording the git commit hash, UTC timestamp, economy, and which stage flags were set. When the comparison site builds, the `index.html` header shows both the baseline's commit and the current run's commit. Check it for:

- **"baseline commit is not an ancestor of the current commit"** — this is a red flag. It means the baseline was produced *after* the current code (e.g. from a different branch, or someone ran the workflow after you started your change). The comparison is unreliable; re-snapshot the baseline from a clean known state before proceeding.
- The baseline provenance also shows which stages were skipped in the run that produced it. If the baseline was produced with `STAGE_COMPARE = False`, the comparison data reflects an even older run — keep that in mind when reading chart deltas.

If the baseline is from many commits ago and you want to reset it, run the snapshot standalone before making your change:

```sh
python codebase/utilities/leap_results_dashboard_compare.py outputs/USA --snapshot
```

Then make your code change and run the re-render-only workflow as described above.

The comparison module is `codebase/utilities/leap_results_dashboard_compare.py`. Env flags:

- `BUILD_COMPARISON_DASHBOARD=0` — skip the comparison entirely (not recommended).
- `PIN_COMPARISON_BASELINE=1` — freeze the baseline across repeated runs so you can compare a series of commits against one fixed starting point.

### Commit frequently

Provenance works by recording the git commit hash at the time a dashboard is produced. This is only useful if the code that produced the baseline is actually captured in a commit — uncommitted changes are invisible to the ancestry check. The recommended habit is: **commit before running the workflow, and commit after verifying the comparison looks correct.** That way every baseline points to a real, inspectable commit, and the ancestry check can reliably detect if a baseline was produced from a different line of history.

---

## Repo scope and boundaries

- This repo owns the LEAP dashboard implementation and the dashboard template.
- Shared mapping/config files live in the sibling `leap_utilities` repo (`../leap_utilities` or `$LEAP_UTILITIES_ROOT`). Do **not** edit files there unless the user explicitly asks for shared utility changes.
- The primary entry point is `codebase/leap_results_dashboard_workflow.py`. All configuration that a user normally needs to change is in the `Configuration` section at the top of that file (the `#%%` cell after the imports).

## Cross-repo access

In Claude Code sessions all three repos are configured as additional working directories and are directly accessible:

- `C:\Users\Work\github\leap_initialisation`
- `C:\Users\Work\github\leap_mappings`
- `C:\Users\Work\github\leap_dashboard` (this repo)

Agents can read, search, and edit files in any of them. When a task here involves mapping or common ESTO structure concepts, read `C:\Users\Work\github\leap_mappings\docs\mappings_system.md` first rather than inferring from context.

## Rebuild scope and active documentation

The dashboard is being rebuilt. **Active development goes in the `test/` folder only.** Do not modify files outside `test/` unless explicitly asked. The old dashboard code elsewhere in the repo is the legacy version.

Within `test/`, the active design plan is at:
`test/common_esto_dashboard_agent_pack_transfer_rules/common_esto_dashboard_plan.md`

Key dependency: `leap_mappings` (`C:\Users\Work\github\leap_mappings`) is the upstream source for the common ESTO comparison data the dashboard consumes. Mapping logic, rollup design, graph partitioning, and naming conventions are documented in `leap_mappings/docs/mappings_system.md`. Do not reproduce that logic in dashboard code or documentation — reference it.

---

## Workflow pipeline overview

The workflow runs five sequential stages. Each can be skipped (set its flag to `False`) to reload cached outputs from the previous run; this saves time during iterative development.

- **`STAGE_EXTRACT`** — Reads the REF/TGT LEAP Excel workbooks and maps balance rows to ESTO flow/product pairs. *(Slowest: LEAP xlsx workbooks)*
- **`STAGE_COMPARE`** — Builds the ESTO-axis comparison table from LEAP, ESTO base data, and 9th projection CSVs. *(Slowest: 9th projection CSV)*
- **`STAGE_WRITE_OUTPUTS`** — Writes CSV/XLSX comparison tables, simple balance tables, and diagnostics.
- **`STAGE_RENDER_DASHBOARDS`** — Renders HTML dashboard pages and Plotly JSON chart bundles. *(Slowest: many charts to render)*
- **`STAGE_WRITE_COVERAGE`** — Writes runtime issues, mapping candidate files, and coverage checks.

**Common development shortcuts:**

```python
# Re-render only (skip everything before the renderer):
STAGE_EXTRACT = False
STAGE_COMPARE = False
STAGE_WRITE_OUTPUTS = False
STAGE_WRITE_COVERAGE = False

# Skip only the slow Excel read (reload cached extraction):
STAGE_EXTRACT = False
```

---

## Data model — the core tables

Everything in the workflow flows through these three tables. When diagnosing unexpected chart values, start here.

### `comparison_long` (`outputs/<token>/comparison_long.csv`)

The main working table. One row per (sheet, fuel_label, source, scenario, year).

Key columns:

- `sheet` — ESTO flow group key, e.g. `esto__16_01__Commercial_and_public_services`
- `fuel_label` — display fuel name, e.g. `Electricity`
- `source` — `base` (ESTO base year), `projection` (9th), or `leap`
- `scenario` — `ESTO`, `reference`, or `target`
- `year` — integer year
- `value` — numeric value in PJ (or whatever the sheet's display unit is after scaling)
- `ninth_pairs_label` — which 9th sector/fuel pair(s) this row maps to (useful for debugging 9th mismatches)

### `mapping_status` (`outputs/<token>/mapping_status.xlsx`)

One row per ESTO (sheet, fuel_label) pair. Describes how each row was resolved through the mapping pipeline.

Key columns:

- `mapped` — True when the row has a complete ESTO and 9th mapping
- `mapping_source` — how the ESTO mapping was found (e.g. `balance_table_esto_axis`, `explicit_mapping`)
- `esto_flow`, `esto_product` — the ESTO pair for this row
- `issue_cause`, `agent_debug_hint` — from the comparison issues table; the most actionable columns when investigating gaps

### `chart_line_mapping_ledger` (`outputs/<token>/supporting_files/charting/chart_line_mapping_ledger.csv`)

One row per rendered chart line (chart, trace). Links each visible chart series back to its mapping decision. Most useful for checking whether a specific chart line is drawing from the right ESTO pair.

---

## Key config files

- **`config/leap_comparison_dashboard_template_v3.json`** — Dashboard navigation tree, chart groupings, fuel display order, aggregate spec. **Primary config for dashboard structure changes.**
- **`config/leap_results_sheet_map.csv`** — Maps ESTO flow keys to dashboard page names and display labels.
- **`config/leap_results_explicit_mappings.csv`** — Hard-coded LEAP row → ESTO pair overrides (use sparingly; prefer updating `leap_mappings.xlsx` in `leap_utilities`).
- **`config/leap_results_explicit_reassignments.csv`** — Post-mapping source reassignments for specific rows.
- **`config/synthetic_reference_rows.csv`** — Synthetic Reference scenario rows injected when the Reference workbook is absent or has gaps.
- **`config/leap_results_balance_known_issues.json`** — Mapping issues to suppress from the runtime issues output.
- **`config/backup_leap_mappings.xlsx`** — Fallback mappings when `leap_mappings.xlsx` does not cover a row.
- **`../leap_utilities/config/leap_mappings.xlsx`** *(shared)* — Primary LEAP-to-ESTO mapping workbook. Sheet `leap_combined_esto` maps LEAP sector/fuel → ESTO flow/product. Sheet `leap_combined_ninth` maps LEAP sector/fuel → 9th sector/fuel.
- **`../leap_utilities/config/master_config.xlsx`** *(shared)* — 9th-to-ESTO canonical pairs (`ninth_pairs_to_esto_pairs` sheet); codebook for display labels.

---

## Visible series and scenario control

`VISIBLE_COMPARISON_SERIES` (set of `(source, scenario)` tuples) controls what appears in the charts.

```python
VISIBLE_COMPARISON_SERIES: set[tuple[str, str]] = {
    ("base", "ESTO"),           # ESTO base-year point
    ("projection", "Target"),   # 9th projection, Target scenario
    ("leap", "Target"),         # LEAP balance export, Target scenario
    # ("projection", "Reference"),  # uncomment to show 9th Reference
    # ("leap", "Reference"),        # uncomment to show LEAP Reference
}
```

Source labels: `"base"` = ESTO base-year data, `"projection"` = 9th projection, `"leap"` = LEAP balance export.
`"ESTO"` is the special scenario label for the ESTO base-year data (it is not scenario-tagged in the raw data).

If both `("leap", "Reference")` and `("leap", "Target")` are visible, both LEAP workbooks must use the same LEAP detail level. The workflow raises if they are mixed.

---

## Mapping pipeline — how rows get from LEAP to a chart

Understanding this chain prevents confusion when chart values don't match expectations.

1. **Extraction** (`STAGE_EXTRACT`): the LEAP xlsx workbooks are read sheet-by-sheet. Each balance row's full sector path + fuel name is looked up in `leap_combined_esto` to get an ESTO flow/product pair. If `EXPLICIT_PAIR_MAPPINGS_ONLY=True` (the default), only exact path+fuel matches count; no inheritance from parent rows.

2. **Aggregation**: mapped rows are summed within each ESTO pair per (scenario, year). The result is `ingestion["leap_long"]` and `ingestion["esto_long"]`.

3. **Comparison build** (`STAGE_COMPARE`): ESTO base-year data (from `00APEC_2025_low_with_subtotals.csv`) and 9th projections (from `merged_file_energy_ALL_20251106.csv`) are joined onto the ESTO axis using `ninth_pairs_to_esto_pairs`. The combined `comparison_long` table is produced.

4. **Filtering**: `VISIBLE_COMPARISON_SERIES` filters `comparison_long` down to only the series that will be rendered. `_normalize_base_scenario` promotes ESTO base-year rows to share the same scenario label as the LEAP scenarios. `_apply_bunker_abs_values` makes bunker chart values positive (sign convention differs for international bunkers).

5. **Render** (`STAGE_RENDER_DASHBOARDS`): the dashboard template (`CHART_NAVIGATION_GUIDE_PATH`) drives chart groupings. Each chart is a (sheet, fuel_label, measure) triple. Charts without any LEAP data can be hidden with `HIDE_CHARTS_WITHOUT_LEAP_DATA=True`.

**Debugging a specific chart line:**

1. Find the chart's `sheet` key in `comparison_long.csv` (or check `chart_line_mapping_ledger.csv` for the chart file → sheet mapping).
2. Filter `comparison_long.csv` to that sheet + fuel_label + source + scenario.
3. If the LEAP value is wrong, check `mapped_leap_to_esto_balance_rows.csv` (the raw LEAP→ESTO aggregation before the comparison stage).
4. If the 9th value is wrong, check `mapped_ninth_to_esto_balance_rows.csv` and `ninth_mapping_data_coverage.xlsx`.
5. If the row is missing entirely, check `balance_runtime_issues.csv` (unmapped rows) and `comparison_issue_summary.csv` (diagnostic gap table).

---

## Diagnostic outputs — what to look at when something looks wrong

- **`outputs/<token>/comparison/index.html`** — First stop after any code change: which charts changed and by how much.
- **`outputs/<token>/comparison/comparison_summary.csv`** — Numeric per-series delta after a code change.
- **`supporting_files/checks/comparison_issue_summary.csv`** — Charts with large LEAP vs 9th/ESTO gaps; has `issue_cause` and `agent_debug_hint` columns.
- **`supporting_files/runtime/balance_runtime_issues.csv`** — LEAP rows that could not be mapped; `reason` = `missing_esto_pair` is the most common.
- **`supporting_files/mapping/mapping_lineage_audit.csv`** — Row-level evidence of how each LEAP/9th/ESTO row was mapped, at audit years.
- **`supporting_files/mapping/mapping_rundown_by_sheet.csv`** — Sheet-level mapping completeness summary.
- **`supporting_files/checks/dashboard_comparator_pair_coverage.xlsx`** — Which ESTO pairs are actually exposed in charts vs. which are in the mapping workbook.
- **`supporting_files/checks/balance_extraction_summary.json`** — `detail_mode` for each workbook (`detailed` vs reduced); `selected_sheet_count`.
- **`supporting_files/charting/chart_series_value_delta.csv`** — Written only when `leap_mappings.xlsx` changed since the last run; shows which chart values moved.

---

## Dashboard template structure

The dashboard template (`config/leap_comparison_dashboard_template_v3.json`) controls:

- The navigation tree (top-level pages, sub-pages, chart groups)
- Which ESTO flows are shown on each page and in what order
- Fuel display labels and ordering
- Aggregate chart specifications (which flows are summed for a "total" chart)
- Chart type (`by_fuel` stacked-area chart, line chart, etc.)

When editing the template, the workflow will pick up the changes automatically on the next render (no code changes needed). The rendered template structure is written to `outputs/<token>/dashboards/dashboard_template.json` and `outputs/<token>/chart_navigation_rendered_template.json` for inspection.

`HIDE_LEAP_ONLY_CHARTS = False` keeps charts that only have ESTO/9th data and no LEAP series. Set to `True` to hide them when working with reduced-detail LEAP exports.

---

## Output directory layout

```text
outputs/<token>/
  comparison_long.csv                  main ESTO-axis comparison table
  comparison_wide.csv                  wide version (one column per source)
  mapping_status.xlsx                  per-ESTO-pair mapping decisions
  leap_long.csv                        raw LEAP rows before ESTO aggregation
  simple_leap_balance_mapped.csv       compact LEAP→ESTO summary
  simple_ninth_balance_mapped.csv      compact 9th→ESTO summary
  merged_leap_ninth_esto_balance.csv   LEAP + 9th on the same ESTO axis
  chart_bundles/                       Plotly JSON bundles (one file per page)
  charts/                              legacy per-chart HTML (page_bundles mode: empty)
  dashboards/                          rendered HTML dashboard pages
  comparison/                          visual regression comparison site
    index.html                         entry point — pages ranked by change magnitude
    comparison_summary.csv             per-series numeric delta
    dashboards/                        current dashboard pages + "(prev)" overlay
    chart_bundles/                     merged current + prev Plotly JSON bundles
  supporting_files/
    mapping/                           mapping lineage, audit, missing candidates
    checks/                            coverage, gaps, duplicate diagnostics
    runtime/                           unmapped rows, override reports, timings
    charting/                          chart ledgers, navigation hierarchy, snapshots
    comparison_baseline/               snapshotted previous-run chart bundles (for comparison)
```

---

## Guard rails — things to check before changing data-pipeline code

1. **Run the workflow first** with all `STAGE_*` flags `True` to get a current baseline in `comparison_baseline/`.
2. **Make your change.**
3. **Re-run the workflow.** The comparison site auto-builds.
4. **Open `outputs/<token>/comparison/index.html`.** If only the expected charts changed, and by the expected amount, the change is safe.
5. If no charts changed when you expected them to: check whether the stage that contains your change ran (stage flags), and whether the output is driven by the cached `comparison_baseline` from a run before your change.
6. If charts changed unexpectedly: `comparison_summary.csv` identifies the sheet/fuel/trace. Cross-reference with `comparison_issue_summary.csv` to see if the gap was pre-existing.

**Do not edit `outputs/` files directly** — they are regenerated on every workflow run.

**Do not edit files in `../leap_utilities/`** without an explicit request; those are shared across multiple dashboards.
