# Dashboard page routing and chart visibility

**Status:** Implemented. TFEC flow 13 and detailed upstream LEAP demand remain
separate deferred data-boundary items, as documented below.

This document defines how Common ESTO categories belong to dashboard pages and
how users filter charts by the datasets actually shown. It is a presentation
contract only. `leap_mappings` remains the owner of comparison scopes, common
categories, component membership, hierarchy, and rollups.

## Core model

The dashboard declares:

1. the pages it wants;
2. the highest-level Common ESTO flow categories owned by each ordinary page;
3. a small set of explicit routing special cases for categories that the
   ordinary roots cannot classify correctly; and
4. separate rules for whether a page or chart is visible.

For an ordinary page, the selected comparison scope supplies the categories
below its configured roots. The dashboard must not reproduce upstream mapping
logic, split a common category, or maintain a second hand-written list of every
descendant.

Example:

```text
Industry owns root 14
  -> 14 Industry
  -> 14.01 Mining
  -> 14.02 Construction
  -> 14.03 Manufacturing
  -> 14.03.01 Iron and steel
  -> any other available descendants of 14 in the selected scope
```

This allows `esto_leap_ninth` and `esto_leap` to retain the same conceptual
pages while displaying the category detail each scope can safely express.

## Prefix matching is hierarchical, not substring matching

A configured root matches only the exact code or a descendant beginning with
the root followed by a hierarchy separator (`.`). Root `14` therefore behaves
as follows:

| Candidate code | Matches root `14` |
|---|---|
| `14` | Yes |
| `14.01` | Yes |
| `14.03.01` | Yes |
| `5.14` | No |
| `05.14` | No |
| `114` | No |
| `14A` | No |

The current low-level `code_matches_prefix` function already uses exact equality
or `code.startswith(prefix + ".")`, so it has this boundary behavior. The
systematic routing implementation must preserve it and add direct regression
tests for exact, descendant, embedded, similarly numbered, range, and compound
codes.

Primary page-root routing should read code-bearing fields such as
`common_flow_code` and `component_flow_code`. Display names and label keywords
may generate warnings or support a temporary compatibility check, but they
should not silently override an otherwise valid code-based assignment.

## Most-specific-root ownership

Some page roots are nested. Broad transformation root `09` contains the more
specific Power and Refining roots. Instead of relying on manually spaced
priority numbers, ordinary routing should choose the deepest matching root.

```text
Configured roots
  Power:               09.01, 09.02
  Refining:            09.07
  Other transformation: 09

09.01.03 matches 09 and 09.01 -> Power owns it
09.07.01 matches 09 and 09.07 -> Refining owns it
09.06.02 matches only 09      -> Other transformation owns it
```

The required result is deterministic:

1. find every configured root that is an ancestor of the category code;
2. choose the deepest/most-specific match;
3. report an unassigned category when there is no match; and
4. fail validation when equally specific roots on different pages match.

For a compound category, resolve each component. If every component resolves
to the same page, that page owns the category. If components resolve to
different pages, the category is ambiguous and requires an explicit special
case; it must not be claimed merely because one page rule happened to run first.

## Routing special cases

`routing_special_cases` is the deliberate exception mechanism. It is not
limited to categories crossing page roots. It covers a category that:

- matches no ordinary page root;
- resolves to more than one page;
- needs a temporary presentation destination;
- must be excluded from ordinary pages because a reviewed inclusive boundary
  already represents it; or
- has another documented reason not to follow ordinary root ownership.

Each case must have a stable identifier, an exact or otherwise unambiguous
selector, an action, a reason, and a temporary/permanent status. Broad label
keywords are not sufficient identity for a special case.

Illustrative shape:

```json
{
  "case_id": "combined_other_and_non_energy_placeholder",
  "match": {
    "common_flow_code_exact": "16.03-16.05,17"
  },
  "action": "route",
  "page_key": "others",
  "temporary": true,
  "reason": "LEAP currently reports Other sector and non-energy as one inseparable aggregate."
}
```

The combined placeholder must not consume an independently available exact
`17 Non-energy use` row. Exact `17` remains owned by the Non-energy page and
that page should become available when the selected scope/economy has usable
standalone data. The temporary combined placeholder remains on Other demand
until upstream detail can replace it.

The routing audit must distinguish ordinary, special-case, ambiguous,
unassigned, and deliberately excluded categories. No retained category may
disappear silently.

## Ordinary and bespoke pages

Each page has exactly one builder type:

```text
generic             hierarchy-driven sector page
energy_balance      configured balance identities and comparisons
emissions           derived emissions presentation
external_diagnostic separately generated supporting page
```

A bespoke page must not also pass through the generic builder. This prevents
one page and bundle from being rendered twice and keeps `chart_manifest.csv`
consistent with the final chart bundle.

Energy-balance identities are configured separately from ordinary page roots.
Flow `13 Total final energy consumption` is intentionally unavailable for the
current presentation: non-energy use cannot yet be extracted from the
aggregated Other-sector LEAP demand category and subtracted reliably. It must
be recorded as temporarily disabled with that reason, rather than listed as an
active overview flow and then removed by an unrelated global exclusion. Flow
13 can be enabled after that upstream boundary becomes separable and the TFEC
calculation is validated.

## Common-category-basis selector

The top-right **Common categories** selector changes the upstream comparison
scope that defines the common flow and product categories. Its initial
configuration lives under `comparison_scope_selector` in
`common_esto_dashboard_template.json`:

- `esto_leap_ninth` renders LEAP + ESTO + Ninth and retains the established
  economy output key, such as `20USA`;
- `esto_leap` renders LEAP + ESTO under the configured sibling key, such as
  `20USA__esto_leap`.

Each option declares its scope, display label, source systems, and output
suffix. Adding another mapping-owned comparison scope therefore requires one
configuration entry rather than new page-routing code. Every scope is rendered
as a complete static dashboard so switching category basis preserves the
current page. Economy switching preserves the active scope suffix.

Each variant writes `supporting_files/comparison_scope_selection.json`, carries
`comparison_scope` in its chart manifest and routing summary, and is included
by the ordinary publication-readiness and page-noise scanners. The default
scope keeps the old URLs; alternate scopes never overwrite it.

## Dataset-presence chart filter

**Current UI status (2026-08-10): hidden.** The comparison-scope selector is
the useful dataset-related control for ordinary review, so the additional
**Charts containing** chooser is not rendered. Chart cards still carry dataset
membership and the filtering implementation remains available if a reviewed
use case justifies restoring it.

The dataset-presence filter answers a different question from the comparison-
scope selector:

- **Comparison scope / Common categories:** which datasets define the common
  category system used to build the pages.
- **Charts containing:** which already-built chart cards remain visible because
  they actually display the selected source datasets.

The intended user rule is conjunctive: when LEAP is selected, hide every chart
that does not show LEAP; when LEAP and ESTO are both selected, retain only
charts showing both. While Industry still uses an aggregate demand placeholder,
the broad `14 Industry` chart may show LEAP while detailed ESTO or Ninth-only
categories are hidden. This is transitional, not an enduring Industry rule:
once detailed LEAP Industry categories are available, every detailed chart
that actually contains a LEAP trace must remain visible under the LEAP filter.

### Dormant implementation

The renderer hides this control with `SHOW_DATASET_FILTER = False`. When
enabled, it:

- derives each card's comma-separated `data-datasets` membership from the
  final Plotly figure's non-empty traces and `layout.meta.trace_meta`;
- keeps the stored dashboard-wide selection when the current page has no
  matching source button or chart;
- applies conjunctive matching when more than one dataset is selected;
- reports the visible and total chart counts;
- explains a zero-result page and provides a one-click Clear action; and
- exposes accessible pressed states and a live status message.

This keeps the filter tied to displayed traces after frontier selection and
fallback, rather than to all input rows considered by a chart builder.

### Target filter contract

Chart dataset membership must be derived from the final Plotly figure's actual
source traces, preferably its existing `layout.meta.trace_meta`, after frontier
selection, suppression, and source fallback. A source counts as displayed only
when the final chart contains a corresponding non-empty trace; the renderer's
raw input dataframe is not sufficient authority.

The selection is a dashboard-wide preference within one comparison scope and
must survive page and economy navigation. Preferences are stored separately by
scope and restored when the user returns to that category basis. Every
configured source option for the active scope remains selectable even when the
current page has no matching chart. In that case the page says, for example:

```text
No charts on Industry show LEAP for this economy and category basis.
Clear the chart filter to show all charts.
```

The filter must:

- keep a card only when it contains every selected dataset;
- distinguish missing traces from zero-valued or suppressed data according to
  one documented rule;
- hide empty chart groups or mark them as having no matches;
- show the visible and total chart counts;
- provide a one-click reset;
- use accessible pressed states and labels; and
- remain visually and semantically distinct from the Common-category-basis
  selector.

## Systematic migration sequence

1. Add routing tests for boundary-safe prefix matching and compound codes.
2. Represent page ownership as configured roots and implement most-specific
   matching.
3. Add exact routing special cases and an explicit routing audit output.
4. Separate ordinary routing, page visibility, and bespoke page inputs.
5. Ensure every page has exactly one builder and validate equality between
   unsuppressed manifest rows and loadable bundle charts. Suppressed manifest
   rows remain as intentional coverage/QA records and have no bundle entry.
6. Record flow 13 as temporarily disabled with its upstream dependency.
7. Derive chart dataset membership from final figure traces.
8. Restore the chart filter with persistent selections, an empty state, and
   focused temporary-placeholder Industry/LEAP tests.
9. Run both `esto_leap_ninth` and `esto_leap` through routing, rendering,
   publication-readiness, and page-noise checks before enabling the new scope
   selector. **Implemented:** both ordinary and all-economy workflows render
   every configured scope and the readiness/noise scripts discover both roots.

## Required validation

Completion requires automated checks that:

- `14` matches `14` and `14.*`, but not `5.14`, `05.14`, or `114`;
- the most-specific root wins for Power, Refining, and Other transformation;
- exact `17` remains independent of the combined Other/non-energy placeholder;
- every retained row is ordinary, special-case, bespoke-page, ambiguous,
  unassigned, or deliberately excluded, with no silent loss;
- a bespoke page is rendered once;
- unsuppressed manifest chart keys and final bundle keys match in both
  directions, while every bundle-absent manifest row is explicitly suppressed;
- every `data-datasets` value equals the datasets represented by final chart
  traces;
- while the aggregate placeholder is in use, selecting LEAP hides
  ESTO/Ninth-only Industry detail while retaining the available LEAP-backed
  `14 Industry` chart;
- when detailed LEAP Industry rows become available, charts containing their
  final LEAP traces remain visible without any Industry-specific exception;
- a selected dataset remains selected on pages with zero matches; and
- the filter behaves consistently in both initial comparison scopes.
