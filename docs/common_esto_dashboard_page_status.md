# Common ESTO Dashboard Page Status

Last reviewed: 2026-06-28 using the upstream `20_USA` output and the existing
21-economy page-noise report.

## Summary

The default Common ESTO dashboard pages are production-facing for the current
static generator. Scope-specific LEAP-vs-9th pages remain diagnostic and are
hidden by default until their rows are reviewed with more complete economy data.

## Default Pages

These pages are enabled by default and are suitable for normal dashboard review:

| Page key | Status | Current chart count | Notes |
|---|---:|---:|---|
| `total_demand` | Production-facing | 2 | High-level demand/supply aggregate checks. |
| `supply` | Production-facing | 211 | Broad supply review; requires aggregate-first navigation because of its density. |
| `bunkers` | Production-facing | 27 | Bunker rows use the configured negative-value sign semantics. |
| `power` | Production-facing | 138 | Power output and related power-sector rows. |
| `other_transformation` | Production-facing | 88 | Includes the Transfers section; useful for transformation QA. |
| `refining` | Production-facing | 52 | Oil refining rows and related own-use rows. |
| `industry` | Production-facing | 219 | Largest default page; requires aggregate-first navigation and stronger sections. |
| `transport` | Production-facing | 42 | Domestic transport final energy demand. |
| `buildings` | Production-facing | 24 | Residential, commercial/public, and visible datacentre rows. |
| `others` | Production-facing | 30 | Other final demand outside buildings/industry/transport. |
| `non_energy` | Production-facing | 17 | Non-energy use rows. |

The current upstream render writes 850 chart manifest rows for `20_USA` from
19,103 visible input rows. The older tracked fixture wrote 860 rows; that count
is historical and must not be used as the current page baseline.

## Page-noise Review

The existing 21-economy analysis flags 23 economy/page pairs. Eight have a high
chart count, 15 have a high suppressed share, and three have many sparse
one-row charts; some pages have more than one reason.

The eight high-count flags are Industry for Australia, China, Korea, Russia,
Chinese Taipei, and the USA, plus Supply for Canada and the USA. This is a real
navigation problem, not a suppression-threshold problem. Industry and Supply
should gain aggregate-first navigation and stronger configuration-driven
sections while retaining every detailed chart and manifest row.

High suppressed-share flags remain QA prompts. They do not justify increasing
the confirmed 1 PJ threshold. Sparse one-row flags on USA Industry, Supply, and
Transport require content review during the grouping work.

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
2. Confirm `outputs/common_esto_dashboard/20USA/supporting_files/chart_manifest.csv`
   has no unexpected diagnostic pages.
3. Open `outputs/common_esto_dashboard/20USA/dashboards/index.html` and inspect
   the largest pages for noisy or redundant sections.
4. Keep `PUBLISH_TO_DOCS = False` unless deliberately copying serving assets to
   `docs/`; automatic publishing after ordinary runs is not the production
   policy.
