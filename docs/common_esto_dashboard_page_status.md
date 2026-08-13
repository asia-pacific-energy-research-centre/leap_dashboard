# Common ESTO Dashboard Page Status

Last evidence review: 2026-08-13 using the current four-source Common ESTO
output and a fresh 21-economy, two-comparison-basis render.

## Summary

The default Common ESTO dashboard pages are production-facing for the current
static generator. Scope-specific LEAP-vs-9th pages remain diagnostic and are
hidden by default until their rows are reviewed with more complete economy data.

## Default Pages

These pages are enabled by default and are suitable for normal dashboard review:

| Page key | Status | 20USA chart count | Notes |
|---|---:|---:|---|
| `total_demand` | Production-facing | 8 | Energy-balance overview and summary aggregate checks. |
| `supply` | Production-facing | 85 | Broad supply review with aggregate-first navigation. |
| `power` | Production-facing | 54 | Power output and related power-sector rows. |
| `other_transformation` | Production-facing | 66 | Other transformation processes and transfers. |
| `refining` | Production-facing | 20 | Oil refining rows and the inclusive own-use boundary. |
| `industry` | Production-facing | 150 | Largest current USA page; detailed charts remain available below its overview. |
| `transport` | Production-facing | 46 | Domestic transport final energy demand. |
| `buildings` | Production-facing | 32 | Residential, commercial/public, and visible datacentre rows. |
| `others` | Production-facing | 43 | Other demand, including the separately routed non-energy section. |
| `emissions` | Production-facing | 2 | Configured combustion-emissions summary charts. |

The current `20USA` render writes 1,035 charts across both maintained bases:
529 for `esto_leap` and 506 for `esto_leap_ninth`. Its default three-way chart
manifest contains 506 rows (the 10 page counts above). Across all 21 economies,
the batch wrote 15,166 charts. `render_summary.csv`, each economy's
`chart_manifest.csv`, and `page_assignment_summary.csv` are the count sources.

## Page-noise Review

The 2026-08-13 page-noise analysis inspected 418 economy/page rows and reported
zero flags. Large trees, suppressed candidates, and sparse one-row charts remain
recorded in `page_noise_summary.csv`; the current policy treats them as review
metrics rather than automatic warnings. Publication readiness passed for all
42 rendered roots (21 economies times two maintained comparison bases).

## Diagnostic Pages

These pages are defined in `config/common_esto_dashboard/common_esto_dashboard_template.json`
but hidden by default through `scope_specific_pages.enabled = false`.

| Page key | Status | Review finding |
|---|---|---|
| `transport_leap_vs_ninth` | Diagnostic, keep disabled | The diagnostic USA render produced 30 charts, but many are sparse alternate-scope slices rather than a balanced production page. |
| `datacentres_leap_vs_ninth` | Diagnostic, keep disabled | The diagnostic USA render produced only two charts from a single datacentre electricity row, so it is not useful as default navigation. |

Enable these pages only for focused review runs. The current decision is to
keep both out of default navigation and publication until chart density, row
coverage, and modeller usefulness have been reviewed across representative
large, medium, and small economies.

## Review Checks

Before publishing a Common ESTO dashboard:

1. Run `scripts/check_common_esto_dashboard_publish_ready.py`.
2. Confirm each maintained basis has no unexpected diagnostic page in its
   `supporting_files/chart_manifest.csv`.
3. Open `outputs/common_esto_dashboard/20USA/dashboards/index.html` and inspect
   the largest pages for noisy or redundant sections.
4. Keep `PUBLISH_TO_DOCS = False` unless deliberately copying serving assets to
   `docs/`; automatic publishing after ordinary runs is not the production
   policy.
