# Common ESTO Dashboard Generator

The production workflow builds the static Common ESTO comparison dashboard from long-form
or wide-form common ESTO comparison data. The frozen predecessor is at
`C:\Users\Work\github\leap_dashboard_legacy`. This implementation does not use
`relationship_id -> graph_id` links or the legacy ESTO-axis mapping pipeline.

## Run

From the repo root:

```powershell
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard_workflow.py
```

Default output:

```text
outputs/common_esto_dashboard/<economy>/dashboards/index.html
```

The workflow currently renders `20_USA` and `02_BD` by default. Set
`COMMON_ESTO_ECONOMIES` for a different reviewed economy set. Focused tests
continue to use the tracked `20_USA` sample fixture.

## Output structure

Each rendered economy is a **self-contained folder** — no server, no build
step, just static files:

```text
outputs/common_esto_dashboard/<economy>/
  dashboards/         one .html page per section (index.html, emissions.html, ...)
  chart_bundles/       one .js + .json pair per page, holding that page's Plotly trace data
  supporting_files/   CSVs and JSON behind the charts (chart_manifest, page_assignment_summary, ...)
```

Every dashboard page is a static HTML file with a `<script src="../chart_bundles/...">`
tag pointing at its data by a **relative path**. That means:

- **A single `.html` file is not portable on its own.** Opening
  `emissions.html` after copying just that one file elsewhere will load the
  page but its charts will not draw — the browser has nothing at
  `../chart_bundles/emissions__charts.js` to fetch. Always copy (or zip) the
  whole `<economy>/` folder — `dashboards/`, `chart_bundles/`, and
  `supporting_files/` together — when handing a rendered dashboard to
  someone outside this checkout.
- `supporting_files/` is not needed to *view* the dashboard (nothing in
  `dashboards/` reads from it), but keep it alongside if the recipient might
  want to check a number behind a chart — see [Publish](#publish) below for
  which subset actually gets served on GitHub Pages.
- The `dashboards/index.html` "About this dashboard" section (rendered by
  `write_index` in `codebase/common_esto_dashboard_renderer.py`) explains
  this same self-containment point to anyone who opens the dashboard without
  ever having read this file.

## Aggregate-only LEAP demand and the Emissions page

Some economies currently contain LEAP demand only in aggregate branches such as
`All demand aggregated/Buildings`, rather than in separately mapped sector
branches. Those rows are valid and remain useful on the **Energy balance
overview**. The Emissions page now uses the same declared TFC total as a
single **LEAP aggregate demand** series when sector detail is unavailable. It
does not copy that total into Buildings, Industry, Transport, or another
sector: doing that would invent an allocation and could count the aggregate
more than once. When lower-level sector detail is present, the page uses its
non-overlapping detail frontier instead. The generated
`supporting_files/emissions_source_selection.csv` records which level was used
for each source and scenario.

### What currently determines “aggregate-only”

The current source of truth is
`leap_mappings/config/all_demand_aggregated_components.json`. It declares
`All demand aggregated` as the upstream aggregate and currently lists
Buildings, Road, Industry, Other sector, Transport non road, and International
transport as components. The mapping preflight resolves this record per
economy and reports branches that do not yet have separately modelled LEAP
detail. It warns if an aggregate and a supposedly detailed component are both
non-zero; it does not silently zero either one.

The dashboard uses that resolved list for page routing: domestic placeholder
pages remain visible where useful, while pages without a usable standalone
mapping stay hidden. The aggregate itself remains in the overview data.
The TFC comparison line uses declared common flow 12 rather than summing every
visible hierarchy row. Flow 13 TFEC is temporarily disabled because non-energy
use cannot yet be separated from aggregated Other-sector LEAP demand; the
dashboard must not substitute an incomplete visible-detail sum. Emissions
follows the declared-total principle with flow 12: detail wins when available,
otherwise the aggregate is shown once as `LEAP aggregate demand`. This is the
current documented mechanism to review or improve upstream; it is not an
emissions allocation model.

## Mapping diagnostics: ESTO Extended

The Mapping diagnostics page uses ordinary ESTO by default. If the supplied
comparison data contains `ESTO_EXTENDED`, select **Include ESTO Extended**
above the sector SVG to make that source available in the Dataset selector.
The control applies to both the rollup-boundary cards and the full-sector SVG.
Turning it off removes Extended from the selector; ordinary and Extended ESTO
values are never added together in a single reconciliation check.

## Inputs

Focused tests use the tracked weekly sample fixture:

```text
tests/fixtures/common_esto_dashboard/common_esto_comparison_data_sample.csv
tests/fixtures/common_esto_dashboard/common_esto_rows.csv
```

The ordinary production workflow reuses existing outputs under
`leap_mappings/results/common_esto/`. Set `COMMON_ESTO_INPUT_DATA_PATH` and
`COMMON_ESTO_ROWS_PATH` to render an explicit fixture or dataset. Update the
tracked fixture when the upstream common ESTO data changes so the sample
remains representative and dashboard regressions are easier to spot.

## Render directly from a LEAP export

For an economy-specific dashboard, use
`codebase/common_esto_dashboard_from_export.py` and set its notebook controls,
or call `render_dashboard_from_leap_export(...)`. This path reads the selected
economy's exports from `leap_initialisation/data/leap balances exports/<economy>`,
delegates to the supported LEAP export parser and mapping chain, and copies the
resulting static dashboard into `outputs/common_esto_dashboard/<economy>/`.
It therefore uses the current export's LEAP values plus the mapping-owned Common
ESTO categories; it does not rely on a cached comparison file that may have no
LEAP rows for that economy. The web app uses this same export-driven path.

To refresh the weekly sample from `leap_mappings/results/common_esto/` and run
the standard checks:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\update_common_esto_dashboard_fixture.py
```

The script copies:

```text
C:\Users\Work\github\leap_mappings\results\common_esto\common_esto_comparison_data.csv
C:\Users\Work\github\leap_mappings\results\common_esto\common_esto_rows.csv
```

into `tests/fixtures/common_esto_dashboard/`, then runs the smoke test and a
full dashboard render. The comparison fixture is written as a compact
long-form single-economy sample for `20_USA`, preserving every source-provided
comparison scope and semantic flow/product combination. If `leap_mappings` is
somewhere else, set `LEAP_MAPPINGS_ROOT` before running the script.

To render every available economy from the upstream common ESTO output:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\render_common_esto_dashboard_all_economies.py
```

This writes one dashboard folder per compact economy code under
`outputs/common_esto_dashboard/` and a compact run summary at:

```text
outputs/common_esto_dashboard/render_summary.csv
```

For quick checks, render a subset:

```powershell
$env:COMMON_ESTO_ECONOMIES = "01AUS,20USA"
C:\Users\Work\miniconda3\python.exe scripts\render_common_esto_dashboard_all_economies.py
```

To rebuild only the summary from existing rendered folders:

```powershell
$env:COMMON_ESTO_RENDER_DASHBOARDS = "0"
C:\Users\Work\miniconda3\python.exe scripts\render_common_esto_dashboard_all_economies.py
```

To flag dense or noisy pages after rendering:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\analyze_common_esto_dashboard_page_noise.py
```

This writes:

```text
outputs/common_esto_dashboard/page_noise_summary.csv
outputs/common_esto_dashboard/page_noise_flags.csv
```

For production or ad hoc runs, override the input paths with environment
variables:

```powershell
$env:COMMON_ESTO_INPUT_DATA_PATH = "C:\path\to\common_esto_comparison_data.csv"
$env:COMMON_ESTO_ROWS_PATH = "C:\path\to\common_esto_rows.csv"
$env:COMMON_ESTO_ECONOMIES = "20_USA"
$env:COMMON_ESTO_COMPARISON_SCOPE = "esto_leap_ninth"
C:\Users\Work\miniconda3\python.exe codebase\common_esto_dashboard_workflow.py
```

## Config

Dashboard config lives in:

```text
config/common_esto_dashboard/common_esto_dashboard_template.json
config/common_esto_dashboard/series_config.json
```

The template controls page assignment, sign semantics, total demand, optional
diagnostic scope-specific pages, and the disabled Sankey scaffold.
Scope-specific pages are disabled by default until their content has been
reviewed for production usefulness; enable `scope_specific_pages.enabled` only
for focused review runs. `series_config.json` controls visible source/scenario
series, labels, economy display text, and the static dashboard switcher.

The approved page-root ownership model, boundary-safe prefix rules,
most-specific-root routing, explicit routing special cases, and the separate
dataset-presence chart-filter contract are defined in
[`dashboard_page_routing_and_chart_visibility.md`](dashboard_page_routing_and_chart_visibility.md).
That document distinguishes the target contract from the current
priority/keyword implementation and is the authority for the systematic
routing migration.

Page status and diagnostic-page review notes are tracked in:

```text
docs/common_esto_dashboard_page_status.md
```

Sankey routing remains disabled. The draft routing table and QA checker are:

```text
config/common_esto_dashboard/sankey_routing_table_draft.csv
scripts/check_common_esto_sankey_routing.py
```

Run the QA checker before enabling any route:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\check_common_esto_sankey_routing.py
```

## Publish

Generated outputs stay under `outputs/` by default and are ignored by git. To
check that the rendered dashboard is ready for manual publication, run:

```powershell
C:\Users\Work\miniconda3\python.exe scripts\check_common_esto_dashboard_publish_ready.py
```

The readiness check scans every rendered economy under
`outputs/common_esto_dashboard/` and validates the pages and Plotly bundles
listed in each economy's chart manifest.

To copy serving assets to GitHub Pages, set
`COMMON_ESTO_PUBLISH_TO_DOCS=1` and rerun the workflow. Use
`COMMON_ESTO_UPDATE_DATA=1` only when intentionally refreshing upstream
inputs. These are opt-in controls so ordinary fixture refreshes and render
checks do not accidentally update `docs/`.
Only `.html` and browser-serving `.js` files are copied to `docs/`; the JSON
bundles remain in `outputs/` for readiness checks and local audit tooling.

## Smoke Tests

Run the Common ESTO smoke tests from the repo root:

```powershell
C:\Users\Work\miniconda3\python.exe -m pytest tests\test_common_esto_dashboard.py
```
