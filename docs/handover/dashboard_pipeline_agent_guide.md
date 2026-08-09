# Common ESTO dashboard agent guide

**Verified:** 2026-07-28

Read `AGENTS.md`, [`../work_queue.md`](../work_queue.md), and the
[reader guide](dashboard_pipeline_guide.md) first. Read
`leap_mappings/docs/mappings_system.md` before changing assumptions about
scope, hierarchy, membership, rollups, or labels.

## Workflow inventory

| Workflow | Entry | Inputs | Outputs | Mutates upstream? |
|---|---|---|---|---|
| selected-economy render | `codebase/common_esto_dashboard_workflow.py` | Common ESTO values/rows, dashboard config | economy HTML/JS/manifests | no, unless `UPDATE_DATA` |
| all-economy render | `scripts/render_common_esto_dashboard_all_economies.py` | same | 21 economy folders | no by default |
| publication readiness | `scripts/check_common_esto_dashboard_publish_ready.py` | rendered outputs | pass/failure evidence | no |
| page-noise review | `scripts/analyze_common_esto_dashboard_page_noise.py` | manifests/pages | review report | no |
| pipeline health report | `scripts/render_mapping_pipeline_health_report.py` | mappings QA/status | diagnostic report | no |

Key modules:

- `common_esto_dashboard_data.py`;
- `common_esto_dashboard_renderer.py`;
- `common_esto_dashboard_output_layout.py`;
- `common_esto_dashboard_mapping_diagnostics.py`;
- `mapping_pipeline_provenance.py`.

## Required environment

Use `C:\Users\Work\miniconda3\python.exe` and Jupyter/`#%%` cells. The dashboard
does not require LEAP COM.

## Before running

1. `git status --short --branch`.
2. Inspect other dashboard and mapping worktrees/processes.
3. Confirm the mappings input status/run ID and `current_output_file`.
4. Confirm `LEAP_MAPPINGS_ROOT`.
5. Confirm v1-contract or legacy long/wide schema, scope, economy, and year range.
6. Keep upstream refresh and docs publication off unless explicitly required.
7. Record dashboard commit, config state, upstream run ID, and economy scope.

## Environment toggles

| Variable | Safe normal value | Effect |
|---|---|---|
| `COMMON_ESTO_RUN_DASHBOARD_WORKFLOW` | `1` for execution | run on module load |
| `COMMON_ESTO_ECONOMIES` | reviewed compact/underscore list | selected economy outputs |
| `COMMON_ESTO_RENDER_COMPARISON_SCOPE_VARIANTS` | `1` | render every configured Common-category basis |
| `COMMON_ESTO_COMPARISON_SCOPE` | `esto_leap_ninth` | single scope when variant rendering is disabled |
| `COMMON_ESTO_WIDE_FILE_SCOPE` | same when using wide input | avoids cross-scope duplication |
| `COMMON_ESTO_DASHBOARD_OUTPUT_ROOT` | `outputs/common_esto_dashboard` | isolate fixture or review renders from production output |
| `COMMON_ESTO_USE_OUTPUT_CONTRACT` | `0` until an intended v1 generation is selected | `1` strictly selects the v1 manifest with no legacy fallback |
| `COMMON_ESTO_OUTPUT_CONTRACT_PATH` | canonical sibling manifest | optional explicit v1 manifest path |
| `COMMON_ESTO_UPDATE_DATA` | `0` | `1` mutates sibling mapping outputs via fast path |
| `COMMON_ESTO_PUBLISH_TO_DOCS` | `0` | `1` copies/removes published serving files |
| `COMMON_ESTO_INCLUDE_NINTH_PRE_BASE_YEAR_DATA` | `0` | retains 9th historical rows for diagnostic use |
| `COMMON_ESTO_PREFER_EXTENDED_ESTO` | `0` | diagnostic tree/reference preference |
| `COMMON_ESTO_INCLUDE_CAPACITY_UNMET_CONVERGENCE` | `0` | optional initialisation convergence page |

## Jupyter execution

Set environment variables before loading the workflow because its bottom block
runs at import/module execution:

```python
#%%
from pathlib import Path
import os
import runpy

REPO_ROOT = Path(r"C:\Users\Work\github\leap_dashboard")
os.chdir(REPO_ROOT)

os.environ["LEAP_MAPPINGS_ROOT"] = r"C:\Users\Work\github\leap_mappings"
os.environ["COMMON_ESTO_RUN_DASHBOARD_WORKFLOW"] = "1"
os.environ["COMMON_ESTO_ECONOMIES"] = "20_USA"
os.environ["COMMON_ESTO_UPDATE_DATA"] = "0"
os.environ["COMMON_ESTO_PUBLISH_TO_DOCS"] = "0"

WORKFLOW_PATH = REPO_ROOT / "codebase" / "common_esto_dashboard_workflow.py"
RESULTS = runpy.run_path(str(WORKFLOW_PATH), run_name="__main__")

#%%
```

## Input schemas

Long input requires:

```text
comparison_scope, source_system, economy, scenario, year,
common_flow_code, common_flow_name, common_flow_label,
common_product_code, common_product_name, common_product_label, value
```

Additional lineage/rollup fields are preserved where available. Wide input
requires identity fields plus numeric year columns and must select one scope.
Do not pass raw ESTO/9th/LEAP tables.

The explicitly selected v1 contract instead requires:

```text
fact: comparison_scope, source_system, economy, scenario, year,
      common_row_id, value
metadata key: comparison_scope, common_row_id
```

The loader validates manifest version/identity, timezone-aware run timestamp,
member paths, SHA-256 hashes, ordered schemas, unique keys, numeric values, and
complete fact/metadata membership before reconstructing the denormalized
dashboard frame. A selected invalid contract must fail; do not silently unset
the toggle and fall back to legacy data.

## Generated cleanup and idempotency

For each selected economy, `CLEAR_EXISTING_OUTPUTS=True` removes only:

- `dashboards`;
- `chart_bundles`;
- `supporting_files`;

then recreates them. Verify output root and economy before execution.

Rendering the same current input/config is expected to regenerate equivalent
content, but timestamps/metadata change. Compare manifests and page summaries,
not binary HTML alone.

`UPDATE_DATA=1` is not idempotent with a concurrent mapping run. It rewrites
mapping long/wide/status from cached intermediates and omits deep validation.

## Expected success artifacts

For each economy:

- `dashboards/index.html`;
- configured page HTML;
- local JS chart bundles;
- `supporting_files/chart_manifest.csv`;
- page assignment and sign summaries;
- mapping diagnostics page and summary;
- tree explorer;
- dashboard metadata.

No page count is permanently fixed. Use manifest/page summary evidence from
the same render.

## Tests and release checks

```powershell
C:\Users\Work\miniconda3\python.exe -m pytest tests\test_common_esto_dashboard.py
C:\Users\Work\miniconda3\python.exe scripts\check_common_esto_dashboard_publish_ready.py
C:\Users\Work\miniconda3\python.exe scripts\analyze_common_esto_dashboard_page_noise.py
```

Run additional focused tests for loaders, diagnostics, provenance, or page
fragments when those areas change.

Validate:

1. input run/provenance is current;
2. page assignments cover intended rows;
3. suppressed rows remain in the manifest;
4. chart bundles exist and charts contain traces;
5. historical/projection difference pairing is correct;
6. skipped/missing validations are not presented as passes;
7. no dashboard-owned mapping logic was introduced.

## Runtime

Observed on 2026-07-28:

- USA: 451 charts;
- Brunei: 199 charts;
- two-economy workflow: 650 charts;
- all-economy folder timestamps span about one hour.

These are planning observations only.

## Symptoms

| Symptom | First evidence | Fix owner | Unsafe shortcut |
|---|---|---|---|
| loader rejects input | header and schema detection | mappings + dashboard | rename columns in generated CSV |
| duplicate series | comparison scope/source system | consumer or mappings contract | group them away |
| wrong/missing page | page assignment summary | dashboard if routing | alter upstream labels |
| category missing entirely | Common ESTO membership/lineage | mappings | add dashboard mapping |
| empty chart | manifest and filtered source rows | dashboard then mappings | publish HTML |
| stale diagnostics | mapping run ID/mtime/commit | mappings refresh | rerender only |
| `skipped` shown as zero failures | status reason and renderer | dashboard diagnostics | label as pass |
| wrong sign presentation | sign summary/template | dashboard | change source values |

## Publication

Publication is an explicit action:

1. render from a reviewed upstream run;
2. run focused tests;
3. run readiness and page-noise scripts;
4. resolve or record every failure;
5. enable `COMMON_ESTO_PUBLISH_TO_DOCS=1`;
6. review the exact `docs/<economy>` diff;
7. stage only intended serving files.

The former empty-transfers-chart blocker was addressed by `b125425`, and the
recorded `20USA`/`02BD` legacy-versus-contract equivalence run passed readiness
and page-noise checks. Do not generalize that representative proof to a newly
rendered all-economy generation: run the gates again and retain their evidence.

## Stop for human review

Stop before:

- changing mapping membership or hierarchy;
- choosing a new additive frontier;
- enabling a diagnostic scope page for publication;
- suppressing data to make a gate pass;
- publishing with failed/unknown diagnostics;
- running upstream fast refresh or docs publication outside scope.

## Handoff evidence

Record dashboard commit/dirty state, upstream run ID/status/current file,
input/config paths, environment toggles, economy scope, render log, test/gate
results, manifest/page counts, and intentionally unresolved diagnostics.
