# LEAP dashboard work queue and handover plan

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

- **DASHQ-048 is `dashboard_ready_upstream_blocked`.** Supply treats Stock
  changes (`06`) and Statistical discrepancy (`11`) as base-year balancing
  diagnostics and renders each available flow as a grouped fuel bar chart
  instead of a projection line or area. The current upstream Common ESTO fact
  contains no flow-06 or flow-11 rows for any economy, so the production USA
  page cannot display these charts yet. `leap_mappings` must publish valid
  Common rows first; the dashboard must not reconstruct them directly from
  native ESTO or LEAP data. The current LEAP-to-ESTO lineage also contains no
  USA observations for either flow.

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
| DASHQ-009 | P1 | 2026-08-05 to 2026-08-12 | `not_started` | DASHQ-008 | Execute the anchor-validation section rebuild | Run `docs/prompts/anchor_validation_section_rebuild_prompt.md`: one source parent boundary is one check, with fuels and years nested as filterable evidence. The prompt states it changes no mapping semantics and no `leap_mappings` artifact — hold it to that. Complete when the prompt's own acceptance criteria are met and the prompt is archived per DASHQ-010. |
| DASHQ-010 | P1 | 2026-08-05 to 2026-08-12 | ✅ `complete_on_master` | — | Create the prompt archive this repo's AGENTS.md already requires | **Done in the exhaustive documentation reconciliation.** `docs/archive/README.md` defines the workflow and preserves completed/superseded planning records. The active anchor-validation prompt remains correctly under `docs/prompts/` until its related implementation and tests are complete. |
| DASHQ-011 | P1 | 2026-08-05 to 2026-08-12 | `partial` | DASHQ-003 | Write the dashboard handover set | **Documentation written 2026-07-28:** `docs/handover/dashboard_pipeline_guide.md` and `dashboard_pipeline_agent_guide.md` now cover the upstream boundary, input compatibility, preprocessing, routing/rendering, outputs, destructive toggles, tests, readiness/page-noise gates, and publication. Root README links the set. Remaining gate: render `20_USA` from a clean checkout during DASHQ-017 and correct any undocumented dependency. |
| DASHQ-012 | P2 | 2026-08-10 to 2026-08-17 | `doc_stale` | DASHQ-007 | Refresh page-status evidence | `docs/common_esto_dashboard_page_status.md` was last touched 2026-06-28 and predates a month of rendering changes. After a reproducible upstream refresh, regenerate the all-economy dashboards, page-noise outputs, and publication checks **together**, then record the render input boundary and review date and separate production from diagnostic pages. Complete when every stated chart count has a corresponding render or manifest source. A successful render alone is not evidence that comparison semantics are correct. |
| DASHQ-013 | P2 | 2026-08-10 to 2026-08-17 | `closed_by_design` | DASHQ-007 | Improve aggregate-first navigation on dense pages | Closed by design on 2026-08-09. Large chart trees, high suppressed-candidate shares, and sparse one-row charts are accepted dashboard outcomes. Their counts remain in `page_noise_summary.csv`, but the `high_chart_count`, `high_suppressed_share`, and `many_sparse_one_row_charts` warning diagnostics are disabled. Detailed charts, the 1 PJ generation-time suppression rule, manifests, and dataset filtering are unchanged. |
| DASHQ-014 | P2 | 2026-08-12 to 2026-08-19 | `superseded_cleanup` | DASHQ-001 | Clean up merged branches and stale worktrees | Delete `claude/mapping-diagnostics-health-report` (fully merged) and remove the `nz-leap-9th-discrepancies-b9c5b1` worktree **only after** DASHQ-001 recovers its uncommitted diff. Complete when every remaining branch and worktree has an explicit disposition and named owner. |
| DASHQ-015 | P2 | 2026-08-12 to 2026-08-19 | `human_decision` | — | Decide the fate of the frozen legacy repository | `leap_dashboard_legacy` has **no GitHub remote** — its `origin` is the local path `C:\Users\Work\github\leap_dashboard`, and its `legacy-reference` branch is 2 commits ahead of that local origin. The frozen visual-comparison reference this repo's `AGENTS.md` depends on therefore exists on one machine only. Decide: publish it, fold the needed comparison evidence into this repo's docs, or accept and record the loss risk. |
| DASHQ-016 | P2 | 2026-08-12 to 2026-08-19 | ✅ `complete_on_master` | — | Normalize document placement | **Done in the exhaustive documentation reconciliation.** The completed record is preserved at `docs/archive/repository_cleanup_plan_20260722.md`, with a historical-status banner and updated navigation. |
| DASHQ-018 | P2 | 2026-08-10 to 2026-08-17 | `human_decision` | DASHQ-007 | Complete the diagnostic comparison-scope page review | Both LEAP-vs-9th pages stay diagnostic and disabled by default until: rendered for representative large, medium, and small economies; row coverage and source/scenario completeness checked; sparse or repeated slices identified; confirmed the page answers a modeller question the default three-way pages do not; page-status documentation updated with economy-specific evidence; and publication-readiness passed with the intended default page list. Complete when each page has a dated enable/disable decision with rationale. |
| DASHQ-019 | P2 | 2026-08-10 to 2026-08-17 | `not_started` | DASHQ-007 | Complete chart-manifest ranking metrics | Sorting works with `total_abs_value`, `abs_diff`, and `pct_diff`, but the audit record is incomplete. Add `default_order`, `model_abs_value`, `comparison_abs_value`, `max_annual_absolute_difference`, `max_annual_percentage_difference`, `non_zero_year_count`, `unexpected_sign_count`, `ranking_warning` — without changing the historical/projection comparison pairing. Small comparison denominators must be flagged rather than allowed to produce misleading percentage rankings. Keep metrics pre-computed so the browser only changes display order. Complete when tests cover missing, sparse, suppressed, and normal chart cases. |
| DASHQ-020 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: structural compilation health | Add concise counts and conditional tables for `qa_ambiguous_structural.csv` and `qa_unresolved_structural.csv`, showing conflicting/cyclic/duplicate states as clean only when their files prove it (exists-and-empty; missing is "unknown"). |
| DASHQ-021 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: non-expanding rollup integrity | Expose violations from `qa_common_esto_non_expanding_frontier_check.csv` only — not every successful check. |
| DASHQ-022 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: material non-zero mapping gaps | Rank `leap_missing_esto_absent_nonzero_pairs_actionable.csv` by absolute value and affected economies/years rather than showing an unranked coverage list. Note explicitly that LEAP aggregate branches are expected to have no direct ESTO pair. |
| DASHQ-023 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: candidate readiness | Display review-only, non-workbook candidates with their evidence and destination sheet. The dashboard must never add candidates to the workbook. |
| DASHQ-024 | P2 | 2026-08-12 to 2026-08-19 | `not_started` | DASHQ-008 | Diagnostics: crosswalk target conflicts and duplicate mappings | Classify intentional versus accidental duplicates first; do not present all raw duplicate rows as errors. |
| DASHQ-025 | P1 | 2026-08-03 to 2026-08-10 | ✅ `complete_unpushed` | DASHQ-007 | Resolve the publication blocker on empty transfers charts | **Done in `b125425`.** Empty area figures are suppressed. The recorded `20USA`/`02BD` legacy-versus-contract equivalence run passed readiness and page-noise checks; DASHQ-007 must repeat the gates for a newly published all-economy generation. |
| DASHQ-017 | P0 | 2026-08-18 to 2026-08-24 | `not_started` | all above | Run the clean-checkout handover rehearsal | A colleague or clean agent session follows the runbook from a fresh checkout of all three repositories, records every missing assumption, and renders one economy end to end. Complete when the rehearsal succeeds without undocumented local knowledge and the queue is frozen with owner, risk, next action, and last-verified date on every remaining item. |

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
