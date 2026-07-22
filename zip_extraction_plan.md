# Common ESTO dashboard: repository cleanup and implementation plan

Last reconciled: 2026-07-22.

This document replaces the former `config data outputs leap_dashbaord.zip`
extraction plan. That plan described an older LEAP-results dashboard workflow
and is no longer an accurate description of this repository.

The current repository is the production Common ESTO dashboard. This document
establishes the current boundary first, then gives a safe order for cleanup and
future implementation work.

## 1. Current repository boundary

The production entrypoint is:

```text
codebase/common_esto_dashboard_workflow.py
```

Its production modules are:

```text
codebase/common_esto_dashboard_data.py
codebase/common_esto_dashboard_renderer.py
codebase/common_esto_dashboard_output_layout.py
codebase/common_esto_dashboard_convergence.py
```

Configuration is under `config/common_esto_dashboard/`. Tests, fixtures, and
operational checks are under `tests/`, `tests/fixtures/common_esto_dashboard/`,
and `scripts/`.

The frozen historical dashboard is maintained separately at:

```text
C:\Users\Work\github\leap_dashboard_legacy
```

Do not restore the legacy ESTO-axis workflow, its direct mapping pipeline, or
its configuration into this repository.

## 2. Upstream data boundary

This dashboard is downstream of:

```text
C:\Users\Work\github\leap_mappings
```

The dashboard consumes generated Common ESTO outputs, principally:

```text
leap_mappings/results/common_esto/common_esto_comparison_data.csv
leap_mappings/results/common_esto/common_esto_rows.csv
```

The full workflow also imports upstream mapping code and reads these
`leap_mappings` files when refreshing data or determining economy-specific
coverage:

```text
leap_mappings/results/mapping_relationships/leap_results_converted_to_esto.csv
leap_mappings/results/mapping_relationships/ninth_results_converted_to_esto.csv
leap_mappings/results/mapping_relationships/esto_results_exact_rows.csv
leap_mappings/config/all_demand_aggregated_components.json
```

It does not read raw ESTO or 9th Outlook source files, rebuild mapping
relationships, or maintain dashboard-owned mapping logic. Mapping semantics,
comparison scopes, component membership, rollups, and generated category
labels belong to `leap_mappings`.

The authoritative upstream guidance is:

```text
C:\Users\Work\github\leap_mappings\docs\mappings_system.md
```

The tracked sample inputs are:

```text
tests/fixtures/common_esto_dashboard/common_esto_comparison_data_sample.csv
tests/fixtures/common_esto_dashboard/common_esto_rows.csv
```

Do not restore the old projection CSVs, base-table CSVs, or LEAP balance
workbooks described by the obsolete extraction plan. Those are upstream data,
not this dashboard repository's runtime boundary.

## 3. Inputs, outputs, and publishing

### Inputs

The core renderer and tests can use the tracked sample fixture. The production
workflow normally uses generated files in `leap_mappings/results/common_esto/`
and may refresh those inputs first. Relevant environment overrides include:

```text
COMMON_ESTO_INPUT_DATA_PATH
COMMON_ESTO_ROWS_PATH
COMMON_ESTO_ECONOMIES
COMMON_ESTO_COMPARISON_SCOPE
COMMON_ESTO_WIDE_FILE_SCOPE
COMMON_ESTO_UPDATE_DATA
```

### Generated outputs

Normal renders write to the ignored directory:

```text
outputs/common_esto_dashboard/<economy>/
├── dashboards/
├── chart_bundles/
└── supporting_files/
```

Important generated checks include:

```text
supporting_files/chart_manifest.csv
supporting_files/page_assignment_summary.csv
supporting_files/sign_semantics_summary.csv
```

`outputs/` is disposable and should be regenerated rather than restored from
an archive. Retain cached generated files only when needed for a specific
diagnostic or stage-skip workflow.

The workflow also has an optional capacity-unmet convergence enrichment. In
the current checkout it is enabled by default and points to:

```text
C:\Users\Work\github\leap_initialisation\outputs\leap_exports\supply_reconciliation\results_update\supporting_files\runtime\capacity_unmet_convergence.csv
```

The convergence writer tolerates a missing history file and skips that page,
but this external dependency must be considered before calling a render fully
self-contained. It should eventually be disabled by default, made explicitly
optional, or given a repository-independent configured path.

### Published dashboard

Serving assets are copied explicitly into the tracked GitHub Pages tree:

```text
docs/<economy>/dashboards/
docs/<economy>/chart_bundles/
```

The current publishing helper copies HTML, JavaScript, and JSON chart-bundle
assets. Do not delete JSON bundles until their role has been checked against
the current renderer, browser code, tests, and published pages.

Publishing is a deliberate release action. Before changing tracked `docs/`,
run publication-readiness checks, inspect the intended economies, and ensure
unrelated working-tree changes are not included.

### Current default-safety warning

The current workflow source has these defaults:

```text
UPDATE_DATA = True
PUBLISH_TO_DOCS = True
INCLUDE_CAPACITY_UNMET_CONVERGENCE = True
```

Therefore a direct workflow invocation can refresh files in `leap_mappings`,
write ignored outputs, modify tracked `docs/`, and attempt the optional
convergence input. The documented operating policy is safer than these source
defaults: ordinary validation should disable data refresh and publication,
and deliberate publication should be a separate reviewed action. This is a
follow-up implementation issue, not something to solve by extracting files.

## 4. Obsolete assumptions not applicable here

| Obsolete assumption | Current state |
|---|---|
| `leap_results_dashboard_workflow.py` is the entrypoint | `common_esto_dashboard_workflow.py` is the entrypoint |
| `codebase/utilities/` contains the active pipeline | Active modules are directly under `codebase/` |
| `leap_utilities` supplies runtime files | `leap_mappings` supplies Common ESTO outputs |
| `data/leap balances exports/<economy>/` is required | No such dashboard input boundary exists |
| `outputs/<economy>/` contains balance-table caches | Current output root is `outputs/common_esto_dashboard/` |
| `config/` can be skipped entirely | `config/common_esto_dashboard/` is required and tracked |
| Old dashboard archives should be selectively extracted | Generated dashboard output should be recreated |
| `leap_mappings` Common ESTO CSVs are the only external runtime files | Refresh and coverage filtering also read upstream mapping/preflight files; optional convergence reads `leap_initialisation` output |
| The source zip is the restoration source | No source zip is required for this repository state |

## 5. Safe implementation order

### Phase 0 — establish a clean review boundary

The checkout currently has pre-existing uncommitted work across production
code, configuration, tests, scripts, and published assets. Before cleanup:

1. Review and classify the existing changes.
2. Do not reset, delete, or overwrite them.
3. Commit or checkpoint intended feature work separately from cleanup.

Cleanup commits must contain only files changed for that cleanup.

### Phase 1 — verify the runtime boundary

Confirm that:

1. `leap_mappings/results/common_esto/` contains the expected generated files.
2. Required upstream mapping/preflight files exist when refresh or coverage
   filtering is enabled.
3. The tracked fixtures load successfully.
4. Configuration paths resolve from `REPO_ROOT`, independently of the current
   working directory.
5. No production code refers to the retired workflow, the
   `relationship_id -> graph_id` model, or legacy ESTO-axis configuration.

### Phase 2 — validate generation before trimming

From the repository root, use the documented Windows Python environment. The
focused tests are safe to run directly:

```powershell
C:\Users\Work\miniconda3\python.exe -m pytest tests\test_common_esto_dashboard.py
```

Before running the full workflow, explicitly confirm the desired values of
`UPDATE_DATA`, `PUBLISH_TO_DOCS`, `INCLUDE_CAPACITY_UNMET_CONVERGENCE`,
`ECONOMIES`, and the input paths in
`codebase/common_esto_dashboard_workflow.py`. A normal review render should
not refresh upstream data or modify tracked `docs/` assets accidentally. After
that explicit review, render and run:

```powershell
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard_workflow.py
C:\Users\Work\miniconda3\python.exe scripts\check_common_esto_dashboard_publish_ready.py
C:\Users\Work\miniconda3\python.exe scripts\analyze_common_esto_dashboard_page_noise.py
```

Confirm the intended economy has an index, chart bundles, and the three
supporting CSVs listed above. For upstream-data changes, also run the
all-economy renderer when `leap_mappings` data is available.

### Phase 3 — audit generated-output duplication

Inspect actual writer and reader paths before removing any generated file.
Classify every candidate as:

- required runtime input for a stage-skip or browser path;
- required human QA/audit output;
- published serving asset; or
- disposable generated output.

Do not infer that a file is dead solely from its name. Confirm write sites,
read sites, manifest references, HTML references, and test coverage.

### Phase 4 — audit tracked `docs/`

Unlike `outputs/`, `docs/` is committed and serves GitHub Pages. Before
trimming it:

1. Compare generated and tracked serving assets.
2. Check every HTML script and asset reference.
3. Remove stale pages only during an intentional publication run.
4. Check for absolute local paths or machine-specific metadata.
5. Run publication-readiness checks after the change.

The `.gitignore` contains a broad JSON allow-rule after the specific
`docs/*/output_manifest.json` ignore rule. If that artifact is generated or
tracked again, move the specific ignore rule after the negation block and
remove only confirmed unwanted tracked artifacts.

### Phase 5 — implement the dashboard backlog

Feature work follows `docs/common_esto_dashboard_plan.md`, not the obsolete
zip assumptions. The current sequence is:

1. Improve aggregate-first navigation on dense Industry and Supply pages.
2. Complete representative-economy review of diagnostic scope pages.
3. Add remaining ranking and warning metrics to the chart manifest.
4. Keep page-status evidence synchronized with reproducible renders.

Sankey diagrams, new bespoke scope pages, automatic publishing after ordinary
runs, and dashboard-owned mapping logic remain deferred unless explicitly
reopened.

## 6. Cleanup rules

- Generated files belong under `outputs/` and should not be committed.
- Published serving assets belong under `docs/` only after deliberate review.
- Do not archive active production modules based only on low commit frequency.
- Before moving a file, check imports, dynamic imports, script references,
  configuration references, tests, and documentation.
- Do not move active configuration or upstream data into `archive/`.
- Do not use the legacy repository as a source for new production code.
- Do not rewrite Git history as routine cleanup; that requires separate
  explicit approval.
- Keep cleanup commits small and verified.

## 7. Success criteria

This repository is in a clean, supportable state when:

1. This document and the operational guide describe the same workflow.
2. The core renderer and focused tests run from the tracked fixture without
   external data; production refreshes use only the documented upstream
   `leap_mappings` boundary.
3. Production dashboard data uses the documented `leap_mappings` boundary;
   optional convergence inputs are separately documented and intentional.
4. Required dashboard and QA outputs are reproducible.
5. Tracked `docs/` assets contain no stale or machine-specific artifacts.
6. Cleanup changes are separated from feature work and pass focused tests,
   rendering checks, page-noise review, and publication-readiness checks.
