# Common ESTO Dashboard Page Status

Last reviewed: 2026-06-25 using the refreshed `20_USA` fixture.

## Summary

The default Common ESTO dashboard pages are production-facing for the current
static generator. Scope-specific LEAP-vs-9th pages remain diagnostic and are
hidden by default until their rows are reviewed with more complete economy data.

## Default Pages

These pages are enabled by default and are suitable for normal dashboard review:

| Page key | Status | Current chart count | Notes |
|---|---:|---:|---|
| `total_demand` | Production-facing | 2 | High-level demand/supply aggregate checks. |
| `supply` | Production-facing | 212 | Broad supply review; suppressed low-value products are expected. |
| `bunkers` | Production-facing | 27 | Bunker rows use the configured negative-value sign semantics. |
| `power` | Production-facing | 139 | Power output and related power-sector rows. |
| `other_transformation` | Production-facing | 86 | Includes the Transfers section; useful for transformation QA. |
| `refining` | Production-facing | 53 | Oil refining rows and related own-use rows. |
| `industry` | Production-facing | 228 | Largest default page; useful but dense. |
| `transport` | Production-facing | 42 | Domestic transport final energy demand. |
| `buildings` | Production-facing | 24 | Residential, commercial/public, and visible datacentre rows. |
| `others` | Production-facing | 30 | Other final demand outside buildings/industry/transport. |
| `non_energy` | Production-facing | 17 | Non-energy use rows. |

The default render currently writes 860 chart manifest rows for `20_USA`.

## Diagnostic Pages

These pages are defined in `config/common_esto_dashboard/common_esto_dashboard_template.json`
but hidden by default through `scope_specific_pages.enabled = false`.

| Page key | Status | Review finding |
|---|---|---|
| `transport_leap_vs_ninth` | Diagnostic | The fixture produced 30 charts, but many are sparse alternate-scope slices rather than a balanced production page. |
| `datacentres_leap_vs_ninth` | Diagnostic | The fixture produced only two charts from a single datacentre electricity row, so it is not useful as default navigation. |

Enable these pages only for focused review runs. Do not publish them by default
until chart density, row coverage, and modeller usefulness have been reviewed
with broader economy data.

## Review Checks

Before publishing a Common ESTO dashboard:

1. Run `scripts/check_common_esto_dashboard_publish_ready.py`.
2. Confirm `outputs/common_esto_dashboard/20USA/supporting_files/chart_manifest.csv`
   has no unexpected diagnostic pages.
3. Open `outputs/common_esto_dashboard/20USA/dashboards/index.html` and inspect
   the largest pages for noisy or redundant sections.
4. Keep `PUBLISH_TO_DOCS = False` unless deliberately copying serving assets to
   `docs/`.
