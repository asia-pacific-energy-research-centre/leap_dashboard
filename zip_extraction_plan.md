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

The current publishing helper copies HTML and browser JavaScript chart-bundle
assets. JSON chart bundles remain in ignored `outputs/` for readiness checks and
local audit tooling; they are not duplicated into tracked `docs/`.

Publishing is a deliberate release action. Before changing tracked `docs/`,
run publication-readiness checks, inspect the intended economies, and ensure
unrelated working-tree changes are not included.

### Current default-safety warning

The workflow now uses these safe ordinary-run defaults:

```text
UPDATE_DATA = False
PUBLISH_TO_DOCS = False
INCLUDE_CAPACITY_UNMET_CONVERGENCE = False
```

Data refresh, tracked-doc publication, and the optional convergence page are
explicit environment-variable opt-ins. The sibling `leap_mappings` root and
convergence CSV also have repository-relative defaults and environment
overrides, so the workflow is portable across checkouts.

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

The deferred work is tracked in `docs/future_dashboard_backlog.md`.

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

## 8. Audit findings and staged action plan

This section records the follow-up repository audit completed on 2026-07-22.
It is separate from the current-state boundary so findings are not mistaken
for completed changes.

### Finding A — tracked browser profile: urgent

`.tmp-edge-profile/` is tracked in Git as 393 files totaling approximately
15.4 MB. It was introduced by commit `157c689` (`aa`) and contains browser
profile state such as cache files, cookie databases, login-data databases,
history, preferences, and session files.

This is not a dashboard input or output. It must not be pushed or retained in
the repository.

Completed action:

1. Stop before pushing the current branch.
2. Confirm that the profile is not needed for any dashboard workflow.
3. Remove it from the working tree and Git tracking using an explicit,
   validated target.
4. Add `.tmp-edge-profile/` to `.gitignore`.
5. Check whether local-only history should be cleaned before publishing.
6. Verify that no other browser/cache artifacts are tracked.

Status: **completed; tracked profile files removed and ignore rule added**.

### Finding B — broken packaging metadata: high priority

`pyproject.toml` declares the unavailable build backend
`setuptools.backends.legacy:build`. `environment.yml` asks pip to install
`pyproject.toml` as if it were a package.

Required action:

1. Change the backend to `setuptools.build_meta`.
2. Change the pip entry to `-e .`.
3. Add an explicit verification command for editable installation.
4. Confirm the installed package/import surface from a clean environment.

Status: **completed; metadata now uses the standard setuptools backend and
editable installs use `-e .`**.

### Finding C — workflow defaults and documentation disagree: high priority

The workflow source now defaults to:

```text
UPDATE_DATA = False
PUBLISH_TO_DOCS = False
INCLUDE_CAPACITY_UNMET_CONVERGENCE = False
```

The README and operating documents describe a safer fixture-first and
manual-publication workflow. The source also hard-codes the main
`leap_mappings` and optional `leap_initialisation` locations.

Completed action:

1. Decide and document the safe ordinary-run defaults.
2. Make publication opt-in and difficult to trigger accidentally.
3. Make data refresh explicit for production runs.
4. Centralize and override the `leap_mappings` root.
5. Make the convergence input optional and configurable.
6. Align `README.md`, `docs/common_esto_dashboard_guide.md`,
   `docs/common_esto_dashboard_plan.md`, and workflow comments.
7. Add tests proving ordinary validation does not publish or refresh.

The implementation and regression test are committed as a separate checkpoint
from browser-profile cleanup and fixture reduction.

Status: **completed; focused suite passes**.

### Finding D — required colour configuration is untracked: high priority

The current uncommitted renderer/test changes require:

```text
config/common_esto_dashboard/code_colors.json
scripts/generate_code_colors.py
```

`code_colors.json` is read by production code and tests but is not present in
the committed tree. A clean clone therefore cannot reproduce the current
working-tree test result.

Required action:

1. Review the generator and generated file against the current colour rules.
2. Decide whether the generated JSON is the canonical committed config.
3. Commit the config and generator with the related colour-system code, or
   provide a deterministic generation step before tests/imports require it.
4. Run the focused test suite from a clean checkout/state.

Status: **completed; config and generator were committed with the colour-system
implementation checkpoint**.

### Finding E — tracked fixture is too large for a lightweight sample: medium

`tests/fixtures/common_esto_dashboard/common_esto_comparison_data_sample.csv`
was approximately 76.5 MB and contained 331,959 rows. The compact replacement
keeps the current upstream scope/source/scenario combinations, all available
semantic flow/product labels, and representative years while staying below
50,000 rows.

Completed action:

1. Inventory which tests require full label and scope coverage.
2. Design a compact fixture preserving the required hierarchy, colours, signs,
   scenarios, scopes, and edge cases.
3. Keep a full upstream snapshot outside the normal tracked fixture path, or
   use an explicitly approved large-file mechanism if the full snapshot is
   required for integration testing.
4. Update fixture-refresh documentation and tests to distinguish regression
   fixtures from full integration data.
5. Compare render manifests and key QA summaries before and after reduction.

The refresh script now performs this reduction from the full upstream output;
the full snapshot used for this migration is archived outside the repository.

Status: **completed; compact fixture render and focused suite pass**.

### Finding F — published bundles duplicate JSON and JavaScript: medium

The renderer writes both `<page>__charts.json` and `<page>__charts.js` from the
same payload. The browser loads JavaScript, while readiness checks and tests
read JSON. The tracked `docs/` chart bundles total approximately 13.6 MB.

Required action:

1. Confirm the browser, readiness checks, tests, and external links that rely
   on each format.
2. Choose one canonical serving format or explicitly separate serving assets
   from QA artifacts.
3. Update writer, publisher, readiness checks, tests, and tracked `docs/`
   assets together.
4. Verify stale bundles are removed and every HTML reference resolves.

Do not delete local JSON bundles from `outputs/`; they remain the canonical
machine-readable input for readiness checks and audit tooling.

Status: **completed; docs publication keeps JS only and local QA retains JSON**.

### Finding G — old ignored dashboard trees remain locally: low risk

The working tree contains ignored legacy-style output trees under:

```text
docs/NZ/
docs/USA/
```

The current published tree uses `docs/02BD/` and `docs/20USA/`. The old trees
contain dashboard outputs, CSVs, XLSX files, and supporting files and are not
part of the current tracked production site.

Required action:

1. Confirm they are not needed for historical comparison.
2. Move them to an explicitly named external archive or remove them locally.
3. Do not alter tracked `docs/02BD/` or `docs/20USA/` as part of this cleanup.

Status: **completed; ignored legacy trees moved to an external local archive**.

### Finding H — missing continuous validation: medium

There is no `.github/` CI workflow. The focused local suite currently passes
29 tests, but the repository has a much larger production surface and no
automated clean-install or publication-parity check.

Required action:

1. Add a lightweight CI job after packaging metadata is repaired.
2. Run focused tests and configuration/import checks in CI.
3. Keep full upstream-data rendering out of routine CI unless its inputs are
   made reproducible and appropriately scoped.
4. Add a separate reviewed publication or artifact-validation job if needed.

Status: **completed; lightweight packaging and focused-test CI workflow added**.

## 9. Execution checkpoints

Changes should be enacted in this order, with one coherent commit per
checkpoint:

1. **Security and repository hygiene:** remove the tracked browser profile,
   add ignore protection, and verify no unrelated files were staged.
2. **Packaging:** repair `pyproject.toml` and `environment.yml`; verify the
   build backend and editable-install metadata.
3. **Colour feature checkpoint:** review and commit the required colour config
   and generator together with the existing uncommitted colour changes.
4. **Workflow safety:** make refresh, publication, and convergence behavior
   explicit, configurable, and consistent with the documentation.
5. **Fixture reduction:** create and validate a compact regression fixture;
   preserve full-data integration coverage separately.
6. **Published-asset optimization:** resolve JSON/JavaScript bundle duplication
   and republish only after readiness checks.
7. **Local archive cleanup:** remove confirmed obsolete ignored output trees.
8. **CI and final documentation:** add clean-install/test automation and
   reconcile all operational documentation.

Each checkpoint must pass focused tests and relevant targeted checks before the
next checkpoint begins. Existing unrelated modifications must remain unstaged
and uncommitted until deliberately assigned to one of these stages.
