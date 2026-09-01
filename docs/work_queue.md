# LEAP dashboard work queue and handover plan

## Source-aware aggregate routing fixes — complete

- **DASHQ-072 — source-reconciled transport frontiers and overview routing.**
  Complete 2026-09-01. Transport overview charts replace the compound
  `15.01,15.03-15.06` non-road row with `15.01`, `15.03`, `15.04`, `15.05`
  and `15.06` whenever at least two children are nonzero for that
  source/scenario/year; otherwise the compound remains the fallback. Resolving
  this per year preserves interim placeholder years before detail begins. The
  rule also handles exports whose compound row is a mislabeled partial child
  rather than an additive rollup. Supply now lets observed LEAP `04`/`05`
  detail override stale placeholder metadata, while combined-only bunker data
  still renders one `04-05` placeholder card. Configured electricity-, CHP-
  and heat-plant overview aggregates are promoted to orange Power navigation
  roots when rendered. Verification: all 407 canonical tests pass.

- **DASHQ-071 — conserve detailed Road stacks and select aggregate cards by
  available source detail.** Complete 2026-09-01. Road by-flow grouping now
  preserves distinct detailed leaves that share a display label, so its ESTO
  historical total equals the Road-by-product total. Other demand treats the
  compound `16.03-16.04` range as the parent of `16.03` and `16.04`, selecting
  the detailed frontier (`16.03`, `16.04`, `16.05`) whenever those rows exist.
  Supply renders separate `04`/`05` bunker overview cards only when LEAP has
  separate detail; a combined-only placeholder produces exactly one `04-05`
  overview with the full projection. Verification: all 403 canonical tests
  pass; regenerated PRC and USA bundles reconcile Road totals to floating-point
  tolerance, contain no overlapping Other-demand range, and contain one bunker
  overview key with projection beyond 2022.

## Australia consistency review — investigation in progress

- **DASHQ-069 — reconcile six cross-page regressions before the next candidate.**
  The complete issue ledger, affected artifacts, open hypotheses and acceptance
  criteria are recorded in
  [`2026-08-31_aus_dashboard_consistency_issues.md`](2026-08-31_aus_dashboard_consistency_issues.md).
  Do not apply chart-specific visual patches until the shared row-frontier,
  aggregate-ownership, base-year continuity and sign checks identify the source
  of each discrepancy.

## Current-run LEAP demand representation status — implemented and verified

- **DASHQ-068 — connect configured Overview boundaries to page rendering.**
  Complete 2026-08-31. The final page renderer now applies the existing
  configured Overview ownership after generic hierarchy discovery. Transport
  therefore renders `15 Transport sector`, `15.02 Road`, and the compound
  `15.01,15.03-15.06 Transport non-road` placeholder in Overview. Other demand
  replaces broad flow 16 with exact `16.03-16.05` product and flow views, so
  its 9th Outlook line cannot include Buildings or non-energy demand. The same
  integration also activates the configured complete Power Overview. Focused
  integration tests and an AUS render from the saved comparison parquet verify
  the three Transport cards and two exact Other-demand cards; at 2042 the
  corrected 9th Target Other-demand total is 100.683 PJ rather than the broad
  roughly 890 PJ line.

- **DASHQ-067 — authoritative Road totals over detailed technology coverage.**
  Complete locally 2026-08-31; not deployed. The `15.02 Road — detailed model by technology`
  chart keeps the technology stack, overlays the authoritative `15.02 Road`
  totals for ESTO, LEAP and Ninth, and labels the partial detailed sum as
  technology coverage rather than as a Road total. The configured Road section
  suppresses its redundant product summary. The same correction fixed the
  reversed placeholder prefixes so Road is `15.02` and non-road is
  `15.01,15.03-15.06`. Historical detail now uses the deepest non-overlapping
  LEAP 2022 technology frontier, so the estimated ESTO stack spans 2010–2022
  and reconciles to the authoritative Road total instead of stopping at the
  Freight/Passenger parents. Verification: the full 382-test suite passes and
  the audited detailed AUS production bundle reconciles ESTO and LEAP coverage
  to their parent lines within floating-point tolerance.

- **DASHQ-066 — PRC Power loss ownership and Power-only aggregate label.**
  Complete 2026-08-26. Product-aware special routing sends only `10.02`
  Electricity and Heat to Power in both configured comparison scopes; every
  other `10.02` product remains on Other transformation. Power calls its flow-10
  area card **Power-related losses and own use** without globally renaming the
  Common hierarchy. Guides and DASH-035 document the separate `10.01.01` and
  `10.02` numerical boundaries. Focused routing and label tests are included.

- **DASHQ-064 — interim Power detail suppression.** Active entries in the
  upstream fallback audit now suppress only the matching Power detail cards:
  Electricity interim suppresses electricity-plant cards, CHP interim
  suppresses CHP cards (including Gas, Others, and petroleum-product CHP), and
  Heat plant interim suppresses heat-plant cards. The page-level Power summary
  remains available. Detail returns automatically when its interim branch no
  longer appears as `interim_only_retained` in the rendered period.

- **DASHQ-065 — combined-bunker overview navigation.** The Supply navigation
  now uses the complete `04-05` Common-flow expression when checking whether
  an overview card belongs wholly to Supply. This retains the orange
  International transport chip when a dashboard has only the combined bunker
  boundary, rather than separate 04 and 05 rows.

- **DASHQ-061 — non-additive hierarchy fallback and reconciliation warning.**
  Dashboard aggregate frontiers now retain an observed parent when its published
  child frontier is non-additive for the same source/product series. If an
  affected source publishes only the inconsistent detail rows, the dashboard
  keeps the facts visible and warns that the sector stack does not reconcile to
  Domestic TFC; it never creates a balancing remainder. Production AUS
  regeneration remains required.

- **DASHQ-063 — lightweight Version 1 comparison traces.**
  Version comparison currently renders a complete dashboard for both the old
  and new exports, then adds the old chart traces to the new dashboard. Design
  a trace-only Version 1 render that preserves the same chart keys, source
  selection, units, routing and hierarchy-frontier rules, while skipping old
  HTML pages, manifests, the secondary dashboard scope and other presentation
  outputs. This is an optimisation task, not a mapping shortcut: paired
  comparison output must remain trace-equivalent to the current two-full-
  dashboard workflow before it can replace it. The web app currently estimates
  a Version 1/Version 2 comparison as two dashboard runs, which correctly
  reflects the present full-render workflow. Once this optimisation is proven,
  replace that fixed 2x estimate with a benchmarked comparison estimate: it
  should still be described as two versions, but it need not remain exactly
  twice a standard dashboard run because the trace-only work removes some of
  the second render's presentation cost.

**Snapshot date:** 2026-07-28

**Planning horizon:** four weeks, through 2026-08-24

**Owner repository:** `leap_dashboard`

**Related repositories:** `leap_mappings` (upstream mapping owner),
`leap_initialisation` (sibling consumer), `leap_dashboard_legacy` (frozen
reference)

**Cross-repository index:** `leap_mappings/docs/cross_repository_handover_index.md`

This is the controlling queue for dashboard work and handover preparation. It
was built from repository evidence on 2026-07-28: local `master` versus
`origin/master`, the dirty checkout, every local branch and worktree, recent
commit history, a relative-link check over all tracked Markdown, and direct
inspection of the current upstream mapping artifacts.

## Post-snapshot completion on 2026-08-13

- **Portable/web comparison bases are complete.**
  `render_common_esto_dashboard_variants()` publishes both maintained
  comparison scopes (`ESTO / LEAP / NINTH` and `ESTO / LEAP`) with explicit
  category-basis choices. Focused unit tests and a real portable fixture render
  pass. The web-app source preserves the whole variant bundle when snapshotting,
  publishing, and downloading results. On 2026-08-17 the misleading reduced
  mapping page was removed: portable bundles do not carry the full mapping QA
  contract needed by the production diagnostics renderer and no longer publish
  relationship-count or raw-row substitutes.

## Post-snapshot completion on 2026-08-12

- **DASHQ-062 is in progress.** The broad 09.06 Ninth comparator now uses its
  observed child frontier. Electrolysers green-electricity input is instead
  awaiting the upstream Common ESTO mapping recorded as `MAPQ-055` in
  `leap_mappings`: it must appear as the mapped negative area in the existing
  Hydrogen transformation chart, not as a raw-LEAP-only diagnostic. The
  post-2026-08-21 mapping run and production render remain the verification
  gate.

- Section navigation and matching body sections now sort automatically by the
  natural numeric ESTO code at each hierarchy level. Labels without a leading
  code use alphabetical fallback ordering.
- Distinguish an app build that omitted native-source provenance files from a
  genuinely stale or incomplete supplied map. The guide now avoids implying
  that visible categories are unmapped when no provenance input was provided.

## Post-snapshot completions on 2026-07-28

These later commits supersede the corresponding snapshot rows below:

- **DASHQ-037 is complete in an isolated worktree.** The configurable,
  page-aware guided tour covers the landing page, all chart pages, mapping
  diagnostics, and the full mapping-tree explorer. It uses stable
  renderer-owned targets and keeps editable guide text outside generated HTML.
  A second content pass adds evidence-backed page-specific review guidance,
  sign and boundary tables, a recommended review route, and clearer diagnostic
  interpretation without changing mapping semantics.
  A 2026-08-10 guide refinement merges the header controls into one step,
  explains how comparison scope changes the lowest common category detail,
  builds mapping-backed category-provenance tables for the routed chart pages,
  and reports a mapping-resolved aggregate placeholder both in the guide and
  at the top of every affected page. The redundant
  **Charts containing** control is hidden while card-level dataset membership
  remains available.
  A later Industry-guide pass moves the comparison-basis explanation directly
  after the header controls, simplifies the shared correction wording, anchors
  placeholder guidance to the yellow page warning, and removes the unused
  chart-sorting controls.
  A Refining and Other-transformation pass explains LEAP auxiliary fuel use,
  removes redundant review cards, and defines conversion, transfers, network
  losses, and energy-sector own use in plain language. Hierarchy parents now
  open with source-safe aggregate summaries on every page; this restores the
  Gas processing and Coal transformation totals without adding parent and
  child rows together.
  A later Power pass applies the same yellow placeholder terminology when the
  upstream fallback audit shows that retained LEAP values come from interim
  power branches, and names those branches in both the page note and guide.
  A Supply pass keeps marine (`04`) and aviation (`05`) bunkers separate and
  removes their combined `04-05` parent from that page. USA LEAP aviation and
  marine remain unavailable because the current source provides only the
  combined `All demand aggregated/International transport` placeholder; the
  separate mappings are ready for Air and Shipping data when supplied.
  A 2026-08-11 correction removes the duplicate secondary International
  transport page and its navigation entry. Bunker rows remain owned by Supply
  and the signed combined `04-05` row remains in the overview supply total.

- **DASHQ-003 and DASHQ-004 are complete in the current documentation
  checkout.** `docs/handover_mapping_diagnostics.md` now retains the original
  doubling diagnosis as dated incident evidence while clearly recording the
  fix, verified replacement artifact identity counts, and completed prompt.
  It no longer instructs readers to execute a prompt absent from mappings
  `master`.
- **DASHQ-006 is `complete_unpushed`.** The producer and strict opt-in consumer
  halves of `common_esto_output_contract_v1` are on the two local `master`
  branches. Dashboard commits `3b4608c`, `e12029b`, `8bac7d5`, and `71826b1`
  cover loading, provenance, remaining maintained readers, and real-data
  equivalence. The recorded `20USA`/`02BD` comparison produced 390 charts and
  3,427 traces with equal manifests, page assignments, sign summaries, and
  normalized series. Readiness passed with zero page-noise flags.
- **DASHQ-025 is `complete_unpushed`.** Commit `b125425` suppresses empty area
  figures and closes the earlier empty-transfers implementation blocker for
  the verified scope.
- The `codex/output-contract-phase-2` worktree is now a
  `superseded_cleanup` candidate, not the authoritative implementation.
- The next operational gate is DASHQ-007: publish the first QA-successful v1
  generation from mappings, select it explicitly, and repeat representative
  and all-economy readiness checks. Existing mapping result files predate the
  integrated contract.
- **DASHQ-026 is complete in the current checkout.** Energy-balance TFC/TFEC
  comparison lines now prefer declared top-level flows instead of summing
  overlapping hierarchy views. The supply-detail charts also draw LEAP TFC
  from the aggregate flow when sector detail is unavailable.
- **DASHQ-027 is complete in the current checkout.** Aggregate-backed Industry,
  Buildings, Transport, and Other demand pages remain visible until detailed
  LEAP demand replaces the placeholders. The combined Other-sector/non-energy
  placeholder routes to Other demand without changing exact code-17 routing;
  aggregate-only Bunkers remains hidden.
- **The two-run Common ESTO v1 production soak is complete in isolated
  worktrees.** Run 1 passed on 2026-07-28. Run 2 passed on 2026-08-03 against
  mapping run `common_esto_20260803T053714732123Z` and dashboard commit
  `8ad51dc`: 21/21 economies, 10,212 charts, 978,809 visible rows, empty
  stderr, and publication readiness all passed. Seven page-noise flags were
  retained and reproduced exactly from the same-generation legacy input; they
  are not contract-reader regressions. The compact contract can now be
  considered for default selection in a separate reviewed change. DASHQ-007
  remains `partial` because its clean-code/artifact provenance requirement and
  the dashboard's current uncommitted changes are separate gates.

## Post-snapshot active design work on 2026-08-08

- **DASHQ-037 is `complete_on_master`.** The approved page-root routing and
  dataset-presence filter contract is documented in
  [`dashboard_page_routing_and_chart_visibility.md`](dashboard_page_routing_and_chart_visibility.md).
  Ordinary pages should own configured highest-level flow roots, nested roots
  should resolve by most-specific match, and exceptional categories should use
  exact documented `routing_special_cases`. The migration must preserve exact
  code-boundary matching (`14` must not match `5.14`), keep exact code 17
  independent of the combined Other/non-energy placeholder, and render every
  page through one builder. The restored chart filter derives membership from
  final figure traces, preserves selections on pages with no matches, explains
  the empty state, and covers the temporary aggregate-placeholder Industry/LEAP
  case. The Common-category-basis selector now renders the configured
  `esto_leap_ninth` and `esto_leap` roots, preserves page and economy context,
  and keeps chart-filter preferences per scope. Configured source buttons stay
  available on zero-match pages and empty chart groups are hidden. This rule
  will naturally retain detailed Industry charts once their final figures
  contain LEAP traces. Flow 13 remains intentionally disabled until non-energy
  use can be separated from aggregated Other-sector LEAP demand. Verification:
  68 focused dashboard tests and 165 repository tests pass; isolated ordinary
  and batch workflows each render 501 three-way plus 494 two-way fixture charts;
  production USA renders 533 three-way plus 524 two-way charts with no
  manifest/bundle mismatch or unexpected source traces; publication readiness
  passes across 22 roots; and page-noise retains five prior flags plus the
  expected dense two-way USA Industry review flag.

- **DASHQ-038 is `complete_on_master`.** Shared chart chrome explicitly keeps
  Plotly legends enabled when scenario or dataset filtering leaves only one
  visible trace, so the remaining line or area still identifies itself. This
  changes presentation only; trace data and filtering are unchanged.

- **DASHQ-039 is `complete_on_master`.** Signed stacked-area categories that
  cross zero are split into linked positive and negative trace fragments. They
  now stack from the correct baseline in every year while retaining one colour,
  one legend item and grouped legend toggling.

- **DASHQ-040 is `complete_on_master`.** The Energy balance overview separates
  demand and supply composition into named sections. Demand charts retain only
  TFC totals; supply charts retain only available-supply totals, with no
  cross-side comparison overlays.

- **DASHQ-041 is `complete_on_master`.** A generated overview card whose
  source-specific frontiers resolve to one logical flow boundary inherits that
  boundary's real common label. When both forms exist, the boundary-adjusted
  `(including own use)` label is preferred; multi-category prefix cards retain
  aggregate label discovery.

- **DASHQ-042 is `complete_on_master`.** Signed stacked-area charts preserve
  gross positive and negative contributions before aggregating their displayed
  product or flow category, preventing transformation inputs and outputs from
  cancelling into a misleadingly small area. Section-level flow charts are
  suppressed when only one effective flow remains and the product companion
  already shows the same signed envelope.

- **DASHQ-043 is `complete_unpushed`.** Refining is published from the inclusive
  `09.07 Oil refineries (including own use)` comparison boundary. The exact
  non-inclusive row is excluded from page construction while the page retains
  the concise name **Refining**.

- **DASHQ-044 is `complete_unpushed`.** Optional `LEAP ... minus ...` diagnostic
  traces are absent from ordinary chart legends. Difference series remain in
  the chart manifest for ranking and audit diagnostics.

- **DASHQ-045 is `complete_unpushed`.** Other transformation now presents
  inclusive process-level cards rather than unclear cross-page `09`/`10`
  totals. Residual other own use, transmission/distribution losses and
  transfers remain separately aggregated, with absorbed own use determined
  from upstream component and non-expanding-rollup contributor metadata. Its
  restored Overview uses separate boundary-driven summaries and the same
  multi-flow-versus-single-flow rule as Refining.

- **DASHQ-046 is `complete_unpushed`.** Stacked-area category frontiers now use
  the union of nonzero historical and projected categories. Historical-only
  fuels remain visible through the base year, so each historical stack
  reconciles exactly to its total line. Russia Industry verifies the fix for
  refinery gas in 2010–2017 and Biogas in 2022.

- **DASHQ-047 is `paused` pending the global LEAP export cutover.** Once every
  economy exports Non-energy as its own demand branch, update the upstream
  Common ESTO mappings so that the separate branch maps to exact flow `17
  Non-energy use` and the Other-demand aggregate maps only to `16.03-16.05`,
  with no flow-17 component. Then route exact flow 17 to an Industry-page
  **Non-energy use** section, remove the standalone Non-energy page, and update
  the Industry guide to explain that grouping. Activation requires one
  generation of the comparison fact, source-to-Common map, and ESTO-to-Common
  map from the same upstream run; the no-split QA must remain empty and TFC,
  TFEC, emissions, page-frontier, and all-economy publication checks must pass.
  Do not activate this during a mixed economy-by-economy rollout and do not
  split the existing combined Other/non-energy value in the dashboard.

- **DASHQ-048 is `implemented_pending_production_rerun`.** Supply treats Stock
  changes (`06`) and Statistical discrepancy (`11`) as base-year balancing
  diagnostics and renders each available flow as a grouped fuel bar chart
  instead of a projection line or area. The mapping fix enables both flows in
  the upstream `esto_leap` scope, and the default dashboard now reads that
  declared scope for these charts while retaining `esto_leap_ninth` for its
  ordinary Supply series. Charts state that they compare ESTO and LEAP only;
  missing 9th Outlook rows are not treated as zero. The Statistical discrepancy
  chart multiplies LEAP values by `-1` at display time to align its sign with
  ESTO, without changing upstream values or applying an absolute-value transform.
  Complete the production mapping and dashboard rerun before marking this item
  verified.

- **DASHQ-049 is `complete_on_master`.** Every anchor context matched by the
  active upstream exception set is omitted from the default paired-tree issue
  queue. A collapsed classification selector retains the same paired cards,
  related economy evidence, review fields, and source-review candidates for
  audit without mixing known exceptions back into unresolved issues.
- **DASHQ-050 is `complete_on_master`.** The four former ESTO flow-tree cards
  reduced to one mapped 2022 China component,
  `10.01.01 Electricity, CHP and heat plants / 02.07 Coal tar` (-0.060290 PJ),
  which the previous Common ESTO build pruned because it applied one global
  latest year (2023, where the component is zero). The raw
  ESTO hierarchy reconciles and the published structural map includes the
  component, so this is neither source non-additivity nor a general 10.x-to-09.x
  boundary-adjustment failure. The approved upstream policy now retains a
  mapped pair when it is non-zero in the endpoint year of any maintained ESTO
  vintage, without treating all historical years as relevant or adding another
  displayed ESTO source. Mapping run `common_esto_20260816T062433503628Z`
  retained the component; the regenerated page has zero ESTO flow issue cards,
  and no exception was added.

- **DASHQ-051 is `complete_on_master`.** The Energy balance overview now shows
  paired signed composition charts for the complete transformation boundary:
  all flow-09 sectors, transfers (08), energy-sector own use (10.01), and
  transmission/distribution losses (10.02), by flow and by fuel. Gross positive
  and negative contributions remain separate while comparison lines show the
  signed net. A comparison basis without projected detail retains ESTO
  historical composition through the base year rather than showing blank area
  charts. China LEAP+ESTO is the production acceptance case.

- **DASHQ-054 is `complete_on_master`.** P3-01 confirms that Coke ovens and
  Blast furnaces follow the existing Gas works and refinery presentation
  contract: mapping outputs retain detailed component identities, while
  ordinary dashboard charts select only the upstream inclusive own-use leaf.
  The existing metadata-driven selector already implemented the rule; focused
  regression coverage now protects both coal-transformation cases.

Do not mark an item complete because a handover note or prompt says it is
complete. Several statements in `docs/handover_mapping_diagnostics.md` were
checked against git and the artifacts on disk during this audit and did not
hold. Completion requires the change to be committed on the intended branch,
verified, and either present on `master` or explicitly recorded as a clean,
ready-to-integrate worktree.

## Status definitions

Shared vocabulary with `leap_mappings/docs/work_queue.md`, plus `doc_stale`.

| Status | Meaning |
|---|---|
| `complete_on_master` | Implemented, verified, committed, and reachable from local `master`. |
| `complete_unpushed` | Complete on local `master`, but not yet present on `origin/master`. |
| `complete_in_worktree` | Clean, committed work exists on another branch and still needs integration or an explicit decision not to integrate. |
| `partial_uncommitted` | Material work exists only as uncommitted changes or an unfinished draft. |
| `partial` | Some committed implementation exists, but the acceptance criteria are not complete. |
| `doc_stale` | The code or data is in a good state, but tracked documentation still describes a superseded state and will mislead a new owner. |
| `paused` | Work is intentionally preserved but should not resume until its stated gate is met. |
| `not_started` | No implementation evidence was found. |
| `human_decision` | Progress depends on a semantic or policy choice that should not be guessed. |
| `superseded_cleanup` | The work is complete or superseded; only archival or branch/worktree cleanup remains. |

## Repository state at the snapshot

- Local `master` is at `3327764` and is **55 commits ahead of `origin/master`**,
  zero behind. `.git/FETCH_HEAD` is dated 2026-07-24, so the remote comparison
  is itself four days stale and should be re-fetched before any push decision.
- The main checkout was modified **during this audit** by a concurrent working
  session. At 12:06 it held one modified file
  (`codebase/common_esto_dashboard_mapping_diagnostics.py`, +69/-9); by 12:19 it
  held two (+681/-21, adding `tests/test_mapping_diagnostics_page.py`). Treat the
  dirty-checkout figures here as a 2026-07-28 12:19 reading and re-verify before
  acting. See "Concurrent session" below.
- **No Python process was running** when this snapshot was taken (only two
  `conda-script.py shell.powershell activate base` shims).
- Three local branches and three worktrees exist. Two branches are already fully
  merged into `master`; one worktree holds uncommitted work that exists nowhere
  else.
- `leap_mappings` local `master` is 4 commits ahead of its remote;
  `leap_initialisation` local `master` is 142 commits ahead of its remote. Those
  gaps are cross-repository handover risks. This queue does not authorize
  pushing any repository.

## Concurrent session (2026-07-28)

A second working session operated across all three repositories while this audit
ran. It committed `leap_mappings` `5bb66f0` ("docs: verify handover audit and add
cross-repository index") at 12:13, created
`leap_initialisation/docs/documentation_audit_20260728.md`, and is actively
implementing in this repository's diagnostics renderer and its tests.

Its output is **complementary to, not a duplicate of, this queue**: it produced
the cross-repository index and a deep `leap_initialisation` documentation audit;
this queue and audit cover `leap_dashboard`, which previously had neither, plus
git/worktree state and the schedule. Before acting on any item here, re-read
`git status` — the dirty-checkout readings in this file are timestamped, and one
of them moved during the audit itself.

The cross-repository index is canonical at
`leap_mappings/docs/cross_repository_handover_index.md`. Do not create a second
one here. Two verified risks recorded below are **not** in that index and should
be folded into it: the at-risk uncommitted worktree diff (DASHQ-001) and the
absent off-machine copy of `leap_dashboard_legacy` (DASHQ-015).

## Branch and worktree reconciliation

| Branch / worktree | Evidence on 2026-07-28 | Classification | Required action |
|---|---|---|---|
| `master` (main checkout) | 55 commits ahead of `origin/master`; one modified file wired into its caller but untested | `complete_unpushed` plus `partial_uncommitted` | Separate the 55 completed commits from the uncommitted diagnostics draft. Review and push only through the user's normal repository process. |
| `codex/output-contract-phase-2` at `C:\Users\Work\github\worktrees\leap_dashboard_output_contract` | Clean; 3 commits ahead, 0 behind `master` (`fac436d`, `71d9971`, `4207d9b`) | `complete_in_worktree` | Integrate with the matching `leap_mappings` branch of the same name. See DASHQ-006 — these are two halves of one contract and must not be landed independently. |
| `claude/nz-leap-9th-discrepancies-b9c5b1` at `.claude/worktrees/nz-leap-9th-discrepancies-b9c5b1` | Branch is **fully merged** into `master`, but the worktree is 53 commits behind and holds **26 lines of uncommitted work** in `common_esto_dashboard_renderer.py` and `tests/test_common_esto_dashboard.py` | `partial_uncommitted` (at risk) | Highest-risk item in this repo. Recover the diff before touching the worktree — see DASHQ-001. |
| `claude/mapping-diagnostics-health-report` (`e73e94b`) | No worktree; `git merge-base --is-ancestor` confirms it is fully contained in `master` | `superseded_cleanup` | Delete the stale branch through the normal safe cleanup process. No content is lost. |

## Documentation claims checked against evidence

These were verified during this audit. Each is a correction to tracked
documentation, not a new opinion.

1. **The ordinary-ESTO doubling is fixed; the handover note says it is not.**
   `docs/handover_mapping_diagnostics.md` states under "Confirmed: current
   artifacts double every ordinary-ESTO rollup value" that the defect "is not
   fixed" and that
   `esto_extended_results_exact_rows.csv.gz` "contains 840,378 rows carrying
   `source_system = ESTO`". Read directly on 2026-07-28, that artifact contains
   **5,320,932 rows, 100% `ESTO_EXTENDED`, and zero rows carrying `ESTO`**;
   `esto_results_exact_rows.csv.gz` is **100% `ESTO`** across 5,445,678 rows.
   The artifacts were rebuilt at 2026-07-27 21:52–22:02, roughly 7.5 hours
   *after* fix commit `eb3a293` (14:14). The section is stale. See DASHQ-003.
2. **A cross-repository link in the handover note points at a file that does not
   exist on `leap_mappings` `master`.** The note instructs readers to execute
   `leap_mappings/docs/prompts/rebuild_esto_rollup_source_identity_prompt.md`.
   That file is tracked **only** on the unmerged branch
   `claude/mapping-diagnostics-dashboard-a55009`. A colleague working from a
   clean `leap_mappings` checkout cannot find it. See DASHQ-004.
3. **The "superseded code" provenance banner is still correct, but for a new
   reason.** The newest mapping artifact is dated 2026-07-27 22:02, while
   `leap_mappings` `master` has two later commits touching `codebase/`:
   `2e39cca` (2026-07-27 23:04) and `34858fe` (2026-07-28 00:55). The banner no
   longer indicates the doubling defect; it indicates the artifacts predate the
   compressed-output and branch-tab-reading changes. See DASHQ-007.
4. **The defensive skipped-anchor rendering is still not implemented on the
   diagnostics page.** The note records it as a required follow-up. In
   `common_esto_dashboard_mapping_diagnostics.py:1156` the "Failed anchor checks"
   tile still counts only `status == "failed"`, so a fully skipped validation run
   would render as `0` failures. The rule exists in the health report but was not
   adopted by the diagnostics page. See DASHQ-008.
5. **`eb3a293` is genuinely on `leap_mappings` `master`.** This part of the note
   is accurate and needs no change.
6. **No broken relative Markdown links were found** in this repository's 14
   tracked Markdown files.

## Prioritized queue

Dates are target windows for handover planning, not promises that semantic
decisions can be made without review.

| ID | Priority | Target | Status | Depends on | Work item | Evidence and completion test |
|---|---|---|---|---|---|---|
| DASHQ-038 | P1 | 2026-08-10 | `complete_on_master` | none | Remove the production mapping-tree explorer page and make failed NINTH/LEAP anchor cards show the tested child frontier | The production workflow no longer renders or links `mapping_tree_explorer.html`; the standalone script remains available for manual investigation. Paired diagnostic cards now constrain component evidence by source system and show only child-frontier rows, explicitly identifying excluded parent mappings and unmapped children. Focused diagnostics tests pass, and the shared APEC diagnostics plus 16RUS dashboard were regenerated. |
| DASHQ-049 | P1 | 2026-08-11 | `complete_on_master` | DASHQ-038 | Separate exception-set matches from the default paired-tree issue queue | Every `known_data_quality_exception` context is hidden from the default NINTH/LEAP/ESTO issue trees and retained in a collapsed `exception_issue_class` selector using the same paired cards and evidence drill-down. Focused diagnostics tests and the regenerated shared diagnostics page verify the split. |
| DASHQ-050 | P1 | 2026-08-16 | `complete_on_master` | `leap_mappings` MAPQ-048 | Resolve four duplicate ESTO flow-tree failures caused by one pruned historical coal-tar component | Run `common_esto_20260816T062433503628Z` retained the component using per-dataset/per-vintage endpoint relevance. All ten mapped scope/source totals remained 100% conserved; 141 dashboard tests passed; the regenerated diagnostics page has zero ESTO flow issue cards and no new exception. USA/Brunei smoke renders wrote 1,361 charts, publication readiness passed all 42 roots, and page-noise reported zero flags. |
| DASHQ-051 | P0 | 2026-08-12 | `complete_on_master` | DASHQ-040, DASHQ-042 | Add the complete transformation boundary to Energy balance overview and retain historical detail in aggregate-only two-way demand views | Implemented paired flow/fuel charts for 09, 08, 10.01 and 10.02 using non-overlapping frontiers and gross signed stacks. LEAP+ESTO demand views now keep ESTO historical areas when no detailed projection source is available. Verification: 112 dashboard tests pass; regenerated China three-way/two-way bundles contain both transformation charts, flow 09 has positive and negative fragments, all four required roots are present, and Reference demand areas are non-empty. |
| DASHQ-052 | P0 | 2026-08-12 | `superseded_by_DASHQ-056` | DASHQ-051 | Show transformation leaf flows in the Energy balance overview | The deepest-code rule was implemented and verified, then superseded after Australia exposed that mapping-owned NON_EXPANDING comparison rollups are terminal even when raw ESTO has deeper codes. See DASHQ-056. |
| DASHQ-053 | P1 | 2026-08-12 | `complete_on_master` | none | Align public dashboard filenames with page names | Energy balance overview now uses `energy_balance_overview.html` and Other demand uses `other_demand.html`; internal data keys and bundle names remain stable. Generated redirects preserve old `total_demand.html` and `others.html` links. Verification: 117 dashboard tests pass. |
| DASHQ-053 | P0 | 2026-08-12 | `complete_on_master` | 9th Outlook Russia convention | Use 2021 as the 9th Outlook base year for Russia only | Russia's 9th projection comparison begins in 2022. ESTO, LEAP, and every other economy retain their existing base-year rules. |
| DASHQ-054 | P1 | 2026-08-16 | `complete_on_master` | `leap_mappings` MAPQ-046 / P3-01 | Apply the inclusive Coke ovens and Blast furnaces comparison frontier | The existing metadata-driven Other transformation selector retains `09.08.01/02 (including own use)` while suppressing the parallel plain rows and absorbed `10.01.05/07` own-use rows. Mapping diagnostics retain all component evidence. Focused regression coverage verifies the Coke ovens and Blast furnaces cases beside the established Gas works behavior. |
| DASHQ-055 | P2 | 2026-08-16 | `inventory_complete_no_code_only_candidate` | Initialisation queue [44], mapping MAPQ-047 | Migrate machine-only dashboard intermediates to typed columnar storage | The repository inventory found no repo-owned pickle producer or disposable server cache: renderer staging tables are generated contract copies, while JSON/HTML bundles and manifests/readiness reports are browser- or human-facing. The 3,845,371-row Common ESTO CSV.gz contract benchmark in `leap_mappings` measured 55,241,694 bytes versus 19,672,130 bytes for Parquet+Zstandard, full reads of 6.627 versus 1.370 seconds, four-column reads of 6.132 versus 0.993 seconds, and economy filters of 7.689 versus 0.254 seconds with exact equivalence. Retain the current CSV.gz contract until its producer, delta, dashboard, review, portable-runtime, tests, manifests and baselines move atomically to a versioned replacement. Preserve browser-facing JSON/HTML and human-readable reports. |
| DASHQ-056 | P0 | 2026-08-17 | `complete_on_master` | DASHQ-052 | Keep mapping-owned transformation rollups continuous across the base year | Plain/inclusive suppression is scoped to the same source, scenario, economy, comparison scope and product. The by-flow selector uses deepest uncovered nodes but treats the most specific mapping-owned NON_EXPANDING rollups as terminal leaves, preventing a broad nested subtotal from replacing its declared descendants. An LNG historical-coverage warning follows every chart whose rows contain `09.06.02` or a descendant, including flow, product and individual-fuel views. All 157 focused dashboard/guide tests pass. A fresh 460-chart 01AUS three-way render shows one `09.06.02 (including own use)` legend category spanning 2010-2060 in both scenarios, with no broad `09`, `.01`, or `.02` traces. Publication readiness passed and page-noise reported zero flags. |
| DASHQ-057 | P1 | 2026-08-17 | `complete_in_worktree` | none | Show LEAP Unmet Requirements on the Energy balance overview | Read the upstream raw LEAP results extract without adding Unmet Requirements to the Common ESTO balance-flow mapping. Resolve its fuel axis through the published scope-specific Common ESTO source map, graph shortages (positive) and surpluses (negative) by fuel and scenario, preserve unknown fuels as audited visible categories, and write the resolved rows to the dashboard supporting files. |
| DASHQ-058 | P2 | 2026-08-20 | `not_started` | shadow-estimation review capability | Retain and compare versioned LEAP net-total lines | Extend the chart-series contract so explicitly selected LEAP result exports can appear as distinct, provenance-labelled net-total traces on the existing dashboard figures. This is independent of estimation testing: every version must resolve through the same reviewed Common ESTO mapping run, comparison scope, signed boundary, and chart frontier before it can be compared. Default dashboard output remains unchanged; version traces are opt-in diagnostic series. Do not persist a dashboard-owned expected-values dataset or reimplement mapping/rollup logic. |
| DASHQ-059 | P1 | 2026-08-20 | `in_progress` | `leap_initialisation` estimation methods; DASHQ-058 | Agentic estimation-method chart review using dashboard figures | Maintain the active instruction pack and isolated renderer-backed review prototype. The agent must discover documented methods, run read-only comparisons against selected LEAP exports, preserve provenance, treat transformation own-use and placeholders explicitly, and withhold unsafe comparisons. Current design evidence: full-horizon (`2023`–`2060`) AUS refinery mismatch and hydrogen `audit_pass` reviews render one composite dashboard-native chart per boundary: LEAP Target fuel stack, LEAP Target total, and a provenance-labelled expected-output line. Before calculation, classify each process from the exact active mapping and workflow: source boundary, capacity basis, output/own-use ownership, auxiliary denominator, and safe formula. The refinery deliverable-capacity gross-up is a recorded refinery-specific result, not a transformation default; it reproduced 2023 9th net within `0.017 PJ`, while the remaining LEAP gap is a separate diagnostic. Use ESTO only when the maintained comparator supplies it; do not create an expected-values fact dataset or alter normal dashboard output. The initial visual reference is evidence of the desired question, not an implementation to copy. |
| DASHQ-060 | P1 | 2026-08-20 | `complete_on_master` | `leap_mappings` Common ESTO rollups; DASHQ-056, DASHQ-059 | Include LNG demand-side own use in LEAP inclusive gas-processing boundaries | Mapping-side fix completed in `leap_mappings`: both LEAP inclusive rollups include `Demand\Other loss and own use\Liquefaction and regasification plants` with multiplier `-1`. The dashboard's generated intermediate chart frontier now prefers an observed mapping-owned NON_EXPANDING boundary instead of descending past it to transformation-only children. Regression coverage and a production AUS rerender verify the inclusive `09.06.02` values: natural gas `-4528.757899`, LNG `+4220.411097`, electricity `-28.073591`, net `-336.420393 PJ`, matching the 9th Target total. |
| DASHQ-061 | P1 | 2026-08-20 | `not_started` | `leap_initialisation` transformation seed; DASHQ-059 | Remove Coke-oven and Blast-furnace projected Historical Production override | Restore one projection rule for all transformation modules: Historical Production is historical/base-year only and explicitly zero in Reference/Target years. Retire `FIXED_PROJECTED_HISTORICAL_PRODUCTION_SECTORS` after reproducing the former AUS 2023 Coke/Blast redispatch cases and diagnosing their actual controlling boundary (demand, trade, capacity, process shares, mapping, or balance constraint). Do not preserve source output by copying it into Historical Production. Add regressions that every module has zero projected Historical Production and that the diagnosed controls, rather than a production pin, explain the affected LEAP results. Rerun the selected LEAP case and regenerate the relevant dashboard/shadow evidence. |
| DASHQ-062 | P0 | 2026-08-21 | `complete_on_master` | DASHQ-060; emissions-factor contract | Restrict estimated emissions to combustion rather than all negative transformation inputs | The emissions boundary now uses final demand, negative power/CHP/heat-plant inputs under `09.01`/`09.02`, and separately reported `10.01` energy-sector own use. It excludes conversion feedstocks (including refining, LNG/gas processing, coal transformation, petrochemicals and hydrogen), positive outputs, transfers and `10.02` losses. The boundary is governed by `config/common_esto_dashboard/esto_emissions_flow_policy.csv`, which exactly covers all 116 original ESTO flows with an inclusion flag and rationale; every current Common ESTO flow expression resolves to its longest original ancestor and mixed rollups fail closed. This removes exact/inclusive/own-use overlap and the AUS 2023 LNG feedstock overstatement. A production AUS rerender reduces the 2023 Target comparison from LEAP/9th `493.357/752.340` to `205.257/208.806 Mt CO2e`; the remaining `3.549 Mt` reflects explicit power and own-use source differences. Dedicated regressions cover LNG, refining, coke ovens, petrochemicals, hydrogen, transfers, losses, extended-code inheritance and mixed aggregates; all 303 repository tests pass. |
| DASHQ-062 | P0 | 2026-08-21 | `implemented_pending_production_rerun` | DASHQ-040; `leap_mappings` MAPQ-053 | Preserve ESTO history in all-economy Extended renders | The batch renderer now selects `ESTO_EXTENDED` as the historical comparison source exactly as the single-economy and portable workflows do. This prevents Extended history from being misclassified as a projection and clipped to the 2022 base year, and restores historical stacked-area inputs. A source-level regression protects the batch path; 19 raw-input and portable-dashboard tests pass. Production dashboard regeneration remains intentionally pending the separately requested mapping rerun. |
| DASHQ-063 | P1 | 2026-08-21 | `deferred_until_after_2026-08-21` | `leap_initialisation` LEAP resource configuration | Diagnose Australia domestic-resource dispatch for Industrial waste and Other sources | The current AUS baseline seed already writes the 9th production trajectories to `Resources\\Secondary\\Industrial waste` and `Resources\\Secondary\\Other sources` as `Maximum Production`; this is not a Common ESTO mapping or missing-seed-row issue. Yet the recalculated LEAP results show zero Production and calculated Imports. After the 21 August work, inspect the live LEAP configuration and recalculated model for these two resource branches: domestic-production availability/cost/priority, import availability/cost/priority, and any resource dispatch or branch settings that make a maximum a ceiling rather than selected output. Confirm the imported seed is the reviewed 20260821 artifact, record the controlling setting, then decide whether the model should prefer domestic production or whether the dashboard should explicitly document the import substitution. Do not change mappings or seed trajectories until that model-level finding is established. |
| DASHQ-064 | P0 | next baseline-seed check | `deferred_until_next_seed_check` | `leap_initialisation` Australia baseline seed and LEAP recalculation | Verify Australia non-energy demand is present in the recalculated LEAP results and restores the 2022 domestic-TFC handover | The reviewed dashboard export has no `All demand aggregated/Non Energy Use` rows for `01_AUS`; this makes LEAP domestic TFC `3,107.565 PJ`, exactly `201.959 PJ` below ESTO/9th (`3,309.524 PJ`). The current reviewed seed workbook already writes the missing branch at `201.959 PJ` in 2022 (Ethane, natural gas, petroleum coke, other products, lubricants, LPG and kerosene). At the next baseline-seed check, confirm that workbook is imported, recalculate and export LEAP, then verify the raw branch is present, LEAP domestic TFC is `3,309.524 PJ` to normal rounding, and the 2022 chart line matches the ESTO stack. International-transport bunkers remain modelled and are excluded only from the domestic-TFC comparison boundary; do not remove their demand from LEAP. |
| DASHQ-065 | P1 | next baseline-seed and mapping check | `deferred_until_next_seed_check` | `leap_mappings` MAPQ-055; `leap_initialisation` hydrogen seed | Show electrolysers' green-electricity input as a signed area on the existing Hydrogen transformation chart | Add the reviewed Common ESTO mapping for 9th `17_x_green_electricity` and LEAP `Hydrogen transformation/Electrolysers × Electricity for hydrogen`, retaining it as a distinct green-electricity product rather than ordinary electricity. After the next seed/model export and mapping run, verify it appears as the negative electricity-input area alongside ammonia, e-fuel and hydrogen outputs; both 9th and LEAP totals must reconcile at the same boundary. Exclude electricity-for-hydrogen import rows: they are not electrolysers' process input and must not enter the chart or mapped comparison total. |
| DASHQ-066 | P2 | 2026-08-22 | `deferred_by_user` | Template-economy dashboard release | Browser acceptance test for portable dashboard archives | After the current all-template-economy dashboard render is complete and the extracted review folders are placed in Downloads, exercise the established web-app archive workflow: load each archive, confirm its extracted dashboard is available, and record any archive or page-load failures. Deferred at the user's request on 2026-08-22; do not run this browser step as part of the current render. |
| DASHQ-067 | P1 | 2026-08-31 | `complete_unpushed` | Common ESTO hierarchy contract | Pair useful first- and second-level aggregate charts by product and by flow | Aggregate cards are emitted only when at least two immediate child flows are non-zero, except for configured boundary summaries such as non-energy, imports, exports, refining and energy-balance totals. Power owns six Overview cards: paired product/flow summaries for generation, power-related losses and own use, and own use. Duplicate lower-page ownership is suppressed. The audited AUS outputs contain 269 placeholder charts and 532 detailed charts; the full 382-test suite passes. |
| DASHQ-068 | P0 | 2026-08-31 | `complete_unpushed` | DASHQ-067; reviewed detailed-demand allocation prototype | Preserve authoritative ESTO totals while estimating historical context for genuine detailed demand branches | LEAP base-year product shares are applied component by component only where genuine detail exists, using the deepest non-overlapping flow frontier. Estimated ESTO children conserve every historical product/year parent, explicit zero shares remain zero, missing denominators become visible Unallocated rows, and parent totals remain authoritative lines. Placeholder branches and aggregate non-energy ownership are unchanged. The audited detailed AUS Road bundle retains 2010–2022 ESTO history and reconciles ESTO/LEAP technology coverage to parent totals within floating-point tolerance; 382 tests pass. |
| DASHQ-069 | P0 | 2026-08-31 | `complete_unpushed` | DASHQ-067; AUS-CONSIST-012 to 014; upstream AUS export rebuild | Keep Transport pairs together, remove overlapping Other-demand frontiers, and constrain detailed Buildings aggregates | Transport reserves the Road companion cell only in placeholder mode. Other demand deduplicates compound-boundary fallback rows before residual calculation; both rendered stacks conserve their authoritative totals to floating-point tolerance and contain no negative residual. Detailed Buildings has exactly the requested Buildings and Services product/flow pairs. The corrected upstream mapping restores the 2022 Buildings identity to 781.606486 PJ. Verification: 395-test full suite, 240-test renderer suite and 11 focused current-code tests pass; regenerated placeholder/detailed candidates contain 270/519 charts; in-app browser QA passed Transport, Other demand and Buildings. |
| DASHQ-070 | P0 | 2026-08-31 | `complete_unpushed` | AUS-CONSIST-015; corrected AUS fixture | Resolve remaining detailed Services and Transport non-road boundary allocations | The source-authoritative fixture now carries Services smoothly from 305.755578 PJ in 2022 to 310.026122 PJ in 2023, introduces Datacentres at 10.458753 PJ in 2023, and reconciles the Buildings parent at 781.606486/791.524737 PJ. Detailed non-road is 216.679872 PJ in 2022 versus ESTO Extended 216.679815 PJ and 236.401763 PJ in 2023. Bunkers remain separate and signed correctly. The final 522-chart detailed candidate was numerically audited and visually checked in the in-app browser. |
| DASHQ-071 | P0 | 2026-09-01 | `complete_on_master` | DASHQ-068 to 070; PRC and USA detailed fixtures | Conserve Road child stacks and route compound Other-demand and bunker cards by source availability | Preserve same-labelled Road detail leaves after child grouping; use a range-aware non-overlapping frontier for `16.03-16.04`; suppress individual `04`/`05` cards when LEAP has only combined `04-05`. Verification: 403 canonical tests; regenerated PRC/USA bundles have exact Road product/flow agreement, `16.03`/`16.04`/`16.05` only, and one projected combined bunker overview. |
| DASHQ-037 | P1 | 2026-08-08 | `complete_in_worktree` | none | Add an interactive guide to every dashboard page | Complete in `codex/dashboard-guided-tour`: a top-right Guide button opens keyboard-accessible, page-aware walkthroughs on the index, every chart page, mapping diagnostics, and the full mapping-tree explorer. Content is editable in `guide_config.json`; stable targets are generated with each page. The content pass adds page-specific boundaries and review prompts for every configured chart page, rich sign/method tables, a recommended landing-page route, and evidence-led diagnostics wording. Verification: all 163 tests pass; the tracked USA fixture renders 579 charts; every rendered HTML page contains the launcher and representative page-specific content; publication readiness passes; page-noise reports zero flags; browser QA confirms landing and Power tables, correct 7-of-10 insertion, reachable controls, and chart lazy loading. |
| DASHQ-030 | P0 | 2026-08-03 | `complete_on_master` | none | Prevent detached common aggregates from stacking with their components | Done in `746bcc7`. Aggregate charts now select one observation-specific common-code frontier even when the broad row is not flagged NON_EXPANDING. The USA Other demand production bundle contains only `16.03-16.05,17`; a source without that row retains `16.03-16.04` and `16.05`. Verification: 47 focused tests pass, fixture and production USA renders completed, required bundles/manifests exist, publication readiness passes, and page-noise flags are unrelated existing density/suppression findings. |
| DASHQ-031 | P0 | 2026-08-03 | `complete_on_master` | none | Include every compound-range endpoint in overview-card scopes | Done in `6142240`. Range-aware subtree closure removes the incomplete `16.01`-derived Buildings card while retaining the valid all-Buildings and Residential views. Verification: 48 focused tests pass; the production USA render contains 520 charts and its all-Buildings frontier includes Ninth Commercial plus Residential; publication readiness passes and page-noise findings are unrelated. |
| DASHQ-032 | P0 | 2026-08-03 | `complete_on_master` | DASHQ-030, DASHQ-031 | Keep detached frontiers local to their chart and restore transformation pages | Implemented and verified. Detached compound suppression now runs after page routing and only on flows; explicit NON_EXPANDING product rules are unchanged. Mixed-depth compounds use every endpoint when selecting overview levels. USA Power and Refining again contain all five dataset totals; the 2060 Transfers LEAP Target total is restored from the erroneous 8,601 PJ to the source-consistent 2,134 PJ; the broad transformation overview is no longer gas-only. Verification: 51 dashboard tests pass, the production USA render writes 676 charts, publication readiness passes, and the six page-noise flags are pre-existing unrelated findings. |
| DASHQ-033 | P0 | 2026-08-03 | `complete_on_master` | — | Show LEAP and Ninth base-year values when available | Implemented. Aggregate totals and individual flow-product lines now begin at the base year rather than the following year, preserving visible calibration gaps against ESTO while hiding earlier model backcasts. The stacked historical/projection handoff is unchanged. Verification: 52 dashboard tests pass; the production USA render writes 676 charts and its Power overview plus an electricity-plants detail chart begin every available LEAP/Ninth line at 2022; publication readiness passes; six unrelated page-noise flags remain. |
| DASHQ-034 | P0 | 2026-08-03 | `complete_on_master` | — | Remove standalone refinery own use from dashboard comparisons | Implemented. The upstream `09.07 Oil refineries (including own use)` NON_EXPANDING rollup already provides the correct LEAP/ESTO/Ninth boundary, so dashboard flow exclusions now remove redundant `10.01.11 Oil refineries`. Verification: 53 dashboard tests pass; the production USA render writes 660 charts and its Refining page has one overview card with no `10.01.11` chip, detail group, bundle trace, or manifest row; publication readiness passes; six unrelated page-noise flags remain. |
| DASHQ-035 | P0 | 2026-08-03 | `complete_on_master` | DASHQ-034 | Keep aggregate frontiers stable when rolled values cancel to zero | Implemented. Common-row frontier selection now uses comparison scope, source, economy, and scenario across the full series rather than selecting independently by year. Exact-zero rolled rows therefore remain zero instead of falling back to overlapping detail. Verification: 54 dashboard tests pass; the production USA render writes 660 charts; the Ninth Target Refining total is `-3,605.34 PJ` in 2027 and has no artificial `624 PJ` saw-tooth; publication readiness passes; the same six unrelated page-noise flags remain. |
| DASHQ-036 | P0 | 2026-08-03 | `complete_on_master` | DASHQ-029 | Require LEAP coverage for aggregate-placeholder demand overview cards | Implemented. Buildings, Industry, Transport, and Other-demand overview area cards now require the selected frontier to contain LEAP; ESTO/Ninth-only child categories remain available as detail groups. Verification: 55 dashboard tests pass; the production USA render writes 656 charts and removes `16.02`, `14.01`, `14.02`, and `14.03` only from Overview; the four broad demand cards and child detail groups remain; publication readiness passes; page-noise flags improve from six to five because USA Industry is no longer over-dense. |
| DASHQ-001 | P0 | 2026-07-28 | ✅ `complete_on_master` | — | Recover at-risk uncommitted renderer work | **Done 2026-07-28 in `f514b1f`.** The uncommitted fix to `_apply_total_series_chrome` and its test were replayed onto current `master`. Verified still needed (master retained the `" total"` guard) and verified safe: no collision between source names and the authoritative 104-flow / 75-product label universe. Stacked traces are now skipped explicitly so the invariant is enforced, not assumed, with an added regression test. Evidence: 30 tests pass; a real 20USA render shows 8 comparison lines that the old guard missed now stably coloured. The worktree may now be removed under DASHQ-014. |
| DASHQ-002 | P0 | 2026-07-28 to 2026-07-30 | `partial_uncommitted` | — | Land or park the diagnostics structural-flag overlay | **Under active development by another session — coordinate before touching.** As first read, the change added `structural_flags` (`DUPLICATE_FLOW_CODE`, `ORPHAN_PARENT`) and per-node anchor-validation counts to `_rollup_graph_data`, with the caller at line 1058 passing `validation=stage` and `economy=economy`. It has since grown to +681/-21 across the renderer and `tests/test_mapping_diagnostics_page.py`, so test coverage is now being added. Complete when it is committed with its tests passing, or moved to a named branch. Do not combine it with DASHQ-001 in one commit. |
| DASHQ-027 | P0 | 2026-08-03 | `verified_uncommitted` | DASHQ-002 | Commit the diagnostics rollup-catalogue source fix | The verified fix removes the hierarchy-contract override of mapping-owned `rollup_edges.csv`, so Electricity plants, CHP plants, and Heat plants all receive their registered `EXPANDING` badges and the erroneous contract-derived `CHP plants → Coal CHP` boundary is absent. Commit `codebase/common_esto_dashboard_mapping_diagnostics.py` and `tests/test_mapping_diagnostics_rollup_source.py` as one scoped checkpoint after coordinating the overlapping DASHQ-002 edits. Before committing, confirm the regenerated shared diagnostics page still contains all three plant rollup IDs. Verification already completed on 2026-08-03: 14 diagnostics tests and 42 dashboard tests passed, publication readiness passed for all rendered economies, and page-noise analysis reported zero flags. |
| DASHQ-003 | P0 | 2026-07-28 to 2026-07-30 | ✅ `complete_on_master` | DASHQ-007 | Correct the stale doubling section in the handover note | **Done in `1d309c3`.** The handover retains the diagnosis as dated incident evidence and records the fixed run and measured replacement identity counts. No tracked document presents current ordinary ESTO as doubled. |
| DASHQ-004 | P0 | 2026-07-28 to 2026-07-30 | ✅ `complete_on_master` | `leap_mappings` MAPQ-001 | Fix the broken cross-repository prompt reference | **Done in `1d309c3` and this documentation reconciliation.** The handover labels the mappings prompt complete and absent from `master`; the active dashboard prompt now points to the retained handover evidence rather than instructing readers to open the absent file. |
| DASHQ-005 | P0 | 2026-07-29 to 2026-08-03 | `complete_unpushed` | — | Reconcile local `master` with `origin/master` | 55 local commits are absent from the remote and the last fetch was 2026-07-24. Re-fetch, confirm zero divergence, then review and push through the user's normal process. Complete when the intended remote contains them or the handover explicitly records why it does not. This is the single largest "work exists only on one laptop" risk in this repository. |
| DASHQ-006 | P0 | 2026-07-30 to 2026-08-03 | ✅ `complete_unpushed` | `leap_mappings` MAPQ-003 | Integrate the Common ESTO output contract, both halves together | Producer and strict opt-in consumer implementations are integrated on both local `master` branches. Dashboard commits `3b4608c`, `e12029b`, `8bac7d5`, and `71826b1` cover loading, provenance, maintained readers, and representative real-data equivalence. DASHQ-007 remains the operational gate for a newly published v1 generation and all-economy checks. |
| DASHQ-007 | P1 | 2026-08-03 to 2026-08-07 | `partial` | `leap_mappings` MAPQ-005 | Re-render from a clean mapping baseline | Artifacts on disk predate two `leap_mappings` `codebase/` commits. Once the upstream clean baseline exists, re-render the diagnostics page and the all-economy batch, and confirm the provenance banner drops to informational. Complete when a dated render references a mapping run ID whose code and artifacts agree. |
| DASHQ-008 | P1 | 2026-08-03 to 2026-08-07 | `partial` | DASHQ-007 | Adopt the health-report reporting rules on the diagnostics page | Implement in `common_esto_dashboard_mapping_diagnostics.py`: render `skipped` as "not validated" and never as a pass; call a QA file clean only when it exists and is empty; never sum anchor counts across overlapping comparison scopes. Complete when a synthetic all-skipped validation input renders a prominent "not validated" state instead of `Failed anchor checks: 0`, covered by a test. |
| DASHQ-009 | P1 | 2026-08-05 to 2026-08-17 | `superseded_by_current_diagnostics` | DASHQ-008 | Execute the anchor-validation section rebuild | The original brief is archived at `docs/archive/anchor_validation_section_rebuild_prompt.md`. Current diagnostics now group source-parent boundaries with nested evidence, distinguish exception classes, and are covered by focused renderer tests; do not restart the old brief. Re-scope any remaining presentation issue from current output. |
| DASHQ-010 | P1 | 2026-08-05 to 2026-08-12 | ✅ `complete_on_master` | — | Create the prompt archive this repo's AGENTS.md already requires | **Done in the exhaustive documentation reconciliation.** `docs/archive/README.md` defines the workflow and preserves completed/superseded planning records. The active anchor-validation prompt remains correctly under `docs/prompts/` until its related implementation and tests are complete. |
| DASHQ-011 | P1 | 2026-08-05 to 2026-08-12 | `partial` | DASHQ-003 | Write the dashboard handover set | **Documentation written 2026-07-28:** `docs/handover/dashboard_pipeline_guide.md` and `dashboard_pipeline_agent_guide.md` now cover the upstream boundary, input compatibility, preprocessing, routing/rendering, outputs, destructive toggles, tests, readiness/page-noise gates, and publication. Root README links the set. Remaining gate: render `20_USA` from a clean checkout during DASHQ-017 and correct any undocumented dependency. |
| DASHQ-012 | P2 | 2026-08-10 to 2026-08-17 | `complete_on_master` | DASHQ-007 | Refresh page-status evidence | Refreshed 2026-08-13 from the current four-source output: all 21 economies and both maintained comparison bases rendered (15,166 charts), readiness passed for all 42 roots, and page-noise analysis produced 418 summary rows with zero flags. `docs/common_esto_dashboard_page_status.md` records the current USA page counts and names the render/manifest evidence. This operational success is not asserted as semantic review of every comparison. |
| DASHQ-013 | P2 | 2026-08-10 to 2026-08-17 | `complete_on_master` | DASHQ-007 | Improve aggregate-first navigation on dense pages | Reopened by user request on 2026-08-11. Navigation now reproduces visible Common ESTO flow nodes rather than page names or renderer-only groups, with one row per effective tree level: orange level 1, green level 2, blue level 3, and purple level 4+. Visible siblings are alphabetized within each level by their display name, ignoring the leading ESTO code, and the matching body sections use the same order. Leaves keep their actual level colour, and sections whose container is omitted promote their shallowest visible node to level 2. Parent pills still target the non-overlapping summaries introduced in `810d3b1`; suppression, manifests, and dataset filtering are unchanged. |
| DASHQ-014 | P2 | 2026-08-12 to 2026-08-19 | `superseded_cleanup` | DASHQ-001 | Clean up merged branches and stale worktrees | Delete `claude/mapping-diagnostics-health-report` (fully merged) and remove the `nz-leap-9th-discrepancies-b9c5b1` worktree **only after** DASHQ-001 recovers its uncommitted diff. Complete when every remaining branch and worktree has an explicit disposition and named owner. |
| DASHQ-015 | P2 | 2026-08-12 to 2026-08-19 | `human_decision` | — | Decide the fate of the frozen legacy repository | `leap_dashboard_legacy` has **no GitHub remote** — its `origin` is the local path `C:\Users\Work\github\leap_dashboard`, and its `legacy-reference` branch is 2 commits ahead of that local origin. The frozen visual-comparison reference this repo's `AGENTS.md` depends on therefore exists on one machine only. Decide: publish it, fold the needed comparison evidence into this repo's docs, or accept and record the loss risk. |
| DASHQ-016 | P2 | 2026-08-12 to 2026-08-19 | ✅ `complete_on_master` | — | Normalize document placement | **Done in the exhaustive documentation reconciliation.** The completed record is preserved at `docs/archive/repository_cleanup_plan_20260722.md`, with a historical-status banner and updated navigation. |
| DASHQ-018 | P2 | 2026-08-10 to 2026-08-17 | `human_decision` | DASHQ-007 | Complete the diagnostic comparison-scope page review | Both LEAP-vs-9th pages stay diagnostic and disabled by default until: rendered for representative large, medium, and small economies; row coverage and source/scenario completeness checked; sparse or repeated slices identified; confirmed the page answers a modeller question the default three-way pages do not; page-status documentation updated with economy-specific evidence; and publication-readiness passed with the intended default page list. Complete when each page has a dated enable/disable decision with rationale. |
| DASHQ-019 | P2 | 2026-08-10 to 2026-08-17 | `complete_in_worktree` | DASHQ-007 | Complete chart-manifest ranking metrics | Implemented on `codex/dashboard-manifest-ranking`. The manifest now records stable per-page default order, model/comparison magnitude, maximum annual absolute and usable-denominator percentage differences, non-zero year count, opposite-sign count, and explicit warning tokens. Comparison pairing remains ESTO through the base year and NINTH thereafter; comparison magnitudes below 1 PJ are excluded from percentage ranking and flagged. Focused missing, sparse/small-denominator, suppressed, and normal tests pass; the full dashboard suite passes (256 tests). |
| DASHQ-020 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: structural compilation health | Add concise counts and conditional tables for `qa_ambiguous_structural.csv` and `qa_unresolved_structural.csv`, showing conflicting/cyclic/duplicate states as clean only when their files prove it (exists-and-empty; missing is "unknown"). |
| DASHQ-021 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: non-expanding rollup integrity | Expose violations from `qa_common_esto_non_expanding_frontier_check.csv` only — not every successful check. |
| DASHQ-022 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: material non-zero mapping gaps | Rank `leap_missing_esto_absent_nonzero_pairs_actionable.csv` by absolute value and affected economies/years rather than showing an unranked coverage list. Note explicitly that LEAP aggregate branches are expected to have no direct ESTO pair. |
| DASHQ-023 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: candidate readiness | Display review-only, non-workbook candidates with their evidence and destination sheet. The dashboard must never add candidates to the workbook. |
| DASHQ-024 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: crosswalk target conflicts and duplicate mappings | Classify intentional versus accidental duplicates first; do not present all raw duplicate rows as errors. |
| DASHQ-025 | P1 | 2026-08-03 to 2026-08-10 | ✅ `complete_unpushed` | DASHQ-007 | Resolve the publication blocker on empty transfers charts | **Done in `b125425`.** Empty area figures are suppressed. The recorded `20USA`/`02BD` legacy-versus-contract equivalence run passed readiness and page-noise checks; DASHQ-007 must repeat the gates for a newly published all-economy generation. |
| DASHQ-017 | P0 | 2026-08-18 to 2026-08-24 | `not_started` | all above | Run the clean-checkout handover rehearsal | A colleague or clean agent session follows the runbook from a fresh checkout of all three repositories, records every missing assumption, and renders one economy end to end. Complete when the rehearsal succeeds without undocumented local knowledge and the queue is frozen with owner, risk, next action, and last-verified date on every remaining item. |

| DASHQ-037 | P2 | 2026-08-17 | `complete_on_master` | — | Add a colleague-facing dashboard colour workbook round trip | Added a macro-free Excel editor with four focused sheets (`START HERE`, `Products`, `Flows`, and `Other categories`), one combined category code/name column, and one visibly filled editable colour cell. Products and Flows expose `SYNC_WITH_JSON` plus automatic `EXISTS_IN_JSON`. Exact matches use `colors.json`; other opted-in rows use mapping-owned OKLab component averages, including declared transformation-plus-own-use boundaries, and leaf rows without components retain their current colour rather than receiving NA. `FALSE` preserves a manual workbook override, and Other categories is always workbook-owned. Every dashboard run validates both sources, regenerates Common ESTO rollups, and refreshes the workbook only when needed. Verification: all 284 tests passed; the USA fixture rendered 941 charts; publication readiness passed; page-noise reported zero flags; Excel opened the workbook without repair. |
| DASHQ-038 | P1 | 2026-08-18 | `complete_on_master` | — | Keep non-zero ESTO Extended categories visible and label Transport overviews precisely | ESTO Extended comparison bases now disable only the ordinary 1 PJ magnitude suppression, so LEAP-only non-zero detailed categories remain visible while empty figures are still omitted. Incomplete mapped overview nodes retain their precise Common ESTO label; the AUS Transport overview therefore distinguishes `15 Transport sector`, `15.01,15.03-15.06 Transport non-road`, and `15.02 Road`. Verification: 131 focused dashboard tests pass. End-to-end AUS runs passed with both the 1708 level-4 TGT export and the 1808 reduced-detail TGT export; the latter generated all four comparison bases, passed publication readiness, produced 13 pages per basis with zero broken links, missing chart keys, or active zero-magnitude charts, kept international bunkers on Supply, and preserved all road aggregate totals exactly. |
| DASHQ-039 | P2 | 2026-08-18 | `complete_on_master` | DASHQ-038 | Explain comparison-basis safety and ESTO Extended in the in-app guide | The Common-category guide step now explains that reported aggregates are never disaggregated using assumed shares; LEAP and ESTO are instead aggregated to the 9th Outlook level when its projection allocation is unknown. It identifies ESTO Extended as a structural basis that adds children below selected ordinary ESTO leaves so LEAP detail can appear without inventing historical ESTO values, and explains why the two-way Extended basis can be more detailed than the three-way basis. |
| DASHQ-040 | P1 | 2026-08-18 | `complete_on_master` | DASHQ-039, `leap_mappings` MAPQ-051 | Make Extended bases primary without changing ESTO history | `ESTO_EXTENDED|historical` now renders as ESTO Historical; Extended+LEAP+Ninth is the unsuffixed default and Extended+LEAP is second, while ordinary three-way and two-way variants remain under explicit verification suffixes. The guide states that both bases reuse the same published ESTO history. Verification: 142 focused dashboard tests and 32 guide tests pass; AUS 1808 generated all four bases (1,975 charts), publication readiness passed, page-noise flags were zero, and 49,877 overlapping ordinary/Extended historical rows reconciled exactly (maximum difference 0.0 PJ). Mixed coverage passed with detailed Road alongside Buildings, Industry, Other sector, Transport non-road, and International transport placeholders; International transport remained off the Transport page. |
| DASHQ-041 | P0 | 2026-08-31 | `complete_on_master` | DASHQ-007, `leap_mappings` ESTO-Extended bunker provenance | Reconcile aggregate-card consistency in AUS detailed and placeholder candidates | Page-specific product/flow pairing, active-placeholder suppression, Other-demand Ninth combined-child selection, Power interim-audit discovery, transformation/refining Overview ownership, and combined/separate bunker presentation are implemented and recorded in `docs/2026-08-31_aus_dashboard_consistency_issues.md`. Verification: 392 tests pass; regenerated placeholder/detailed AUS candidates contain 270/522 charts; browser QA confirmed the corrected Other-demand envelope and Overview layout; render-level assertions confirmed zero forced spacers on Energy balance, Emissions, Supply and placeholder aggregate-only demand pages. The renderer applies the canonical negative withdrawal sign to detailed 04/05 Supply charts without mutating the comparison fact; upstream ESTO-Extended provenance remains a named dependency. |
| DASHQ-042 | P1 | 2026-08-31 | `in_progress` | DASHQ-041, upstream AUS fixture owner | Remove redundant combined bunker presentation and audit detailed non-road/Power inputs | Placeholder Supply shows exactly one combined 04-05 Overview product card because its marine/aviation split is unavailable; detailed Supply removes the combined parent and shows separate 04 and 05 cards. Source audit found that non-road incorrectly subtracts 51.012955 PJ of already-separated international activity in 2023. Both power workbooks contain only retained Electricity/CHP interim branches, not genuine plant detail. Upstream correction and fixture regeneration remain in progress; no dashboard-side data adjustment is permitted. |
| DASHQ-043 | P1 | 2026-09-01 | `complete_on_master` | DASHQ-041 | Present a verified single-child Other-demand projection at its deepest known flow | The 9th Outlook publishes AUS projected agriculture/fishing only at combined `16.03-16.04`, but ESTO history proves `16.03 Agriculture` equals that compound for every fuel through 2022 (maximum difference 0.00 PJ). The Other-demand flow overview now relabels the unchanged projected values as `16.03 Agriculture` for AUS. The generic path remains evidence-guarded and other economies retain the compound unless exactly one observed child reconciles; no values or totals are split or altered. Verification: 13 focused Other-demand tests and the full 401-test dashboard suite pass, including the allocated-parent-code case found by release rendering. |

## Deferred by decision — not queue items

These are deliberately out of scope. They are recorded here so they are not
rediscovered as gaps, and they are not scheduled. Reopening any of them is a
decision, not a backlog pull.

| Work | Why deferred | Gate for reopening |
|---|---|---|
| Sankey diagrams | The repo holds a disabled configuration scaffold, a draft routing table, routing QA, and `docs/common_esto_sankey_balance_routing_design.md` — but no enabled production Sankey. A Sankey needs a routing layer the comparison data does not supply. | All of: deterministic source-to-target routes agreed; signed input/output/loss/stock-change treatment explicit; overlap and double-counting checks passing; reconciliation checks defining acceptable node imbalances; route coverage reviewed across representative economies. **The dashboard must not infer physical links dynamically or use AI to invent runtime routes.** Link widths may use absolute values only if signed values stay available in hover text and QA outputs. |
| Automatic publishing after ordinary runs | The copy mechanism exists, but the manual publication gate is preferred. | Publication moves to a CI job with an explicit approval step, a clean source revision, artifact review, and rollback. |
| Additional bespoke scope pages | Transport, buildings, and other source-specific pages wait until the two existing diagnostic pages establish a repeatable review pattern. | DASHQ-018 produces that pattern. Any bespoke page must use existing Common ESTO membership and configuration rules and introduce no dashboard-owned mapping logic. |
| Dashboard-owned mapping logic | Forbidden by `AGENTS.md`. Mapping remains owned by `leap_mappings`. | Never — this is an ownership boundary, not a deferral. |

## Four-week handover sequence

### Week 1: 2026-07-28 to 2026-08-03

- ✅ Recover the at-risk uncommitted renderer diff (DASHQ-001) — done in `f514b1f`.
- Resolve the dirty checkout (DASHQ-002).
- Correct the two misleading documentation claims (DASHQ-003, DASHQ-004).
- Re-fetch and reconcile the 55-commit remote gap (DASHQ-005).
- Land the output contract jointly with `leap_mappings` (DASHQ-006).

### Week 2: 2026-08-04 to 2026-08-10

- Re-render from the upstream clean baseline (DASHQ-007).
- Adopt the health-report reporting rules on the diagnostics page (DASHQ-008).
- Start the anchor-validation section rebuild (DASHQ-009).
- Create `docs/archive/` and begin prompt archival (DASHQ-010).
- Draft the dashboard handover set (DASHQ-011).

### Week 3: 2026-08-11 to 2026-08-17

- Finish the handover set and page-status refresh (DASHQ-011, DASHQ-012).
- Work or explicitly defer the feature backlog: dense-page navigation
  (DASHQ-013), the diagnostic-page enable/disable decision (DASHQ-018), and
  manifest ranking metrics (DASHQ-019).
- Add the five mapping-diagnostics sections (DASHQ-020 to DASHQ-024) as capacity
  allows; these are the first items to descope if Week 3 is tight.
- Clean up merged branches and stale worktrees (DASHQ-014).
- Make the legacy-repository decision (DASHQ-015) and normalize doc placement
  (DASHQ-016).

### Week 4: 2026-08-18 to 2026-08-24

- Perform the clean-checkout handover rehearsal (DASHQ-017).
- Fix the documentation gaps the rehearsal exposes.
- Freeze a final dated queue and known-risks list.
- Ensure every unmerged branch, stale worktree, and unpushed commit has an
  explicit disposition and named owner.

## Queue maintenance rules

1. Update the evidence column whenever a status changes, and re-date the
   snapshot header.
2. Cite the commit, worktree, run ID, artifact measurement, or human decision
   that supports each status.
3. Never carry an old prompt's row counts or failure counts forward into a new
   baseline without re-measuring. This audit found two documented counts that no
   longer held.
4. Move completed prompts to `docs/archive/`; keep `docs/prompts/` limited to
   active or pending work.
5. Keep cross-repository items here only when the dependency affects dashboard
   presentation or handover. Mapping semantics belong in
   `leap_mappings/docs/work_queue.md`.
6. At the end of each week, record what moved to `complete_on_master`, what is
   blocked, and what must be descoped before handover.
