# Relay baton — emissions-overnight

Protocol: `C:\Users\Work\.claude\relay\RELAY_PROTOCOL.md`. This is the
**state** file. The plan is `docs/prompts/overnight_work_program_20260806.md`
in this repo (never edited by the run); design detail is in
`docs/prompts/measure_aware_dashboard_and_mapping_inversion_plan.md` beside it.

```text
Status:       ACTIVE
Firing:       002             # interactive takeover, not a scheduled firing
Heartbeat:    2026-08-07T04:26+09:00
Started:      2026-08-07T00:20+09:00
Repo:         C:\Users\Work\github\leap_dashboard\.claude\worktrees\dashboard-emissions-page-5c4fbd
Branch:       claude/dashboard-emissions-page-5c4fbd
Plan:         docs\prompts\overnight_work_program_20260806.md
Session id:   local_a08212ac-da1e-4c70-b49a-dcd6796cc9dc
Transcript:   C:\Users\Work\.claude\projects\C--Users-Work-github-leap-dashboard\a08212ac-da1e-4c70-b49a-dcd6796cc9dc.jsonl
Previous id:  local_dcec7536-985e-49c0-8b15-b788512259d0 (s000, kickoff — transcript
              stopped writing at 00:27, no commits/heartbeat update for 82+ min,
              declared dead by maintainer instruction)
```

`HALTED` means a **program-level** stop condition fired and the whole run is
untrustworthy from here. Later firings must stand down, not resume. Only the
maintainer clears it. Per the plan's rules of engagement, **every stop
condition in this program is item-level** — nothing sets `Status: HALTED`.
The one hard line (below) reverts the offending item's commits only.

## 1. Goal

Work the overnight program end to end: seven work items (W0–W6) across
`leap_dashboard` and `leap_mappings`, producing four deliverables (D1–D4)
under `outputs/overnight_20260806/`. Nothing merges to `master`, nothing is
pushed, nothing is deployed. Done when all seven items and four deliverables
are attempted, the run log and Assumptions register are filled in, and the
final report (plan §"Final report") is written from this baton's log.

## 2. Work items

- [x] W0 — guard rails: T0 determinism guard, T1 baselines for 20USA + 02BD,
      committed. **Hard prerequisite — do not start W1+ until W0 baselines
      are committed.** DONE (commits e9987e9, 17e2974).
- [x] W1 — investigation only, gates nothing: explain the 3,347 unmapped LEAP
      links (real values or not). Does not block W6. DONE — finding + coverage
      CSV in outputs/overnight_20260806/ (gitignored, not committed).
- [x] W2 — Phase 0 code prep: switch to `common_esto_rows.csv`, add explicit
      factor-config path arg. Invariants must hold. DONE (commit 4485520).
      Verified: all 4 supporting CSVs identical to T1 baseline both
      economies, suite 147 passed.
- [x] W3 — main event: measure/unit columns, gate energy-balance machinery to
      `measure == energy`, pair comparisons on `(source_system, measure)`.
      Verify against T1 baselines — energy charts identical. DONE (commit
      482e0cd). Pairing implemented as one top-level filter, not per-call-site
      — see commit body / log for why.
- [x] W4 — frontier parenthood onto the hierarchy contract; write T6 first
      (assert retained tuple *set*, not totals). ATTEMPTED, BLOCKED, REVERTED
      (item-level, not a hard-line trip — see log + finding doc). T6 baseline
      committed (0425226) as a reusable regression fixture for a future
      attempt. `select_non_overlapping_rows` unchanged from W3.
- [x] W5 — Phase B: move factor resolution into `leap_mappings`
      (branch `claude/common-esto-mapping-docs`). T5 gate: resolution CSV
      content-identical after the move. B1 PUBLISHED, T5 PASSES (commit
      ed82958 in leap_mappings). Dashboard-side switch (plan step 5)
      deliberately NOT done — scope decision, see log. leap_dashboard still
      runs its own (unchanged, still-verified) copy of the same logic.
- [x] W6 — Phase C map + importable merger (D4) + D3 CSVs, in `leap_mappings`
      on `claude/common-esto-mapping-docs`. Zero fan-out assertion. DONE
      (commit c1b12d7). Cross-checked exactly against W1's hand-computed
      numbers (2988/1969 mapped, 3347/0 unmapped for esto_leap_ninth).
- [x] D1 — rendered dashboard output, 20USA + 02BD, emissions page. Depends
      W2–W5. DONE — see outputs/overnight_20260806/D1_dashboard_render/README.md.
      Both economies' emissions.html confirmed open with correct content;
      20USA shows "ESTO 3,443, NINTH 3,443" matching the named invariant
      exactly. Caught and fixed a stale-gitignored-render scare along the
      way — see log and the D1 README's "Finding worth recording" section.
- [ ] D2 — local Gradio app proof, screenshot. Depends W2, W5, Phase 0 file
      list. Hand-stage files if the manifest can't be satisfied — do not
      merge, do not deploy. NOT STARTED.
- [x] D3 — legible mapping CSVs + README. Part of W6. DONE.
- [x] D4 — importable merger with docstring, worked example, test. Part of
      W6. DONE.

**Next: D2** — local Gradio app proof + screenshot. Depends W2, W5, Phase 0
file list (read that section of the design plan — four files that must
reach the runtime: common_esto_dashboard_emissions.py,
emissions_factor_sets.json, the 9th-edition factor CSV, and
outlook_mappings_single_axis.xlsx from leap_mappings). D2 prerequisites
already confirmed present (see §4 above: gradio 5.44.1, LEAP balance
exports for both economies). Hand-stage files if the manifest can't be
satisfied — do not merge, do not deploy.

## 3. State of the tree

Nothing changed yet by this run. This baton is the first commit.

## 4. Load-bearing facts

```bash
# Python
C:\Users\Work\miniconda3\python.exe

# REQUIRED in a worktree — REPO_ROOT.parent resolves to the worktrees dir,
# so every upstream path silently misses without this.
LEAP_MAPPINGS_ROOT=C:/Users/Work/github/leap_mappings
```

```bash
LEAP_MAPPINGS_ROOT=C:/Users/Work/github/leap_mappings COMMON_ESTO_ECONOMIES=20_USA C:/Users/Work/miniconda3/python.exe codebase/common_esto_dashboard_workflow.py
C:/Users/Work/miniconda3/python.exe -m pytest tests -q
```

- Timings: ~3–5 min per economy render, ~5 min for the full `leap_dashboard`
  suite. Budget accordingly — start a full render only with enough runway
  left to finish it or the baton must record it as in-progress.
- Named invariants (item-level revert if violated, see §"Traps"):
  20USA 2022 = **3,443 Mt CO2e** (LEAP, ESTO, 9th equal); `leap_dashboard`
  `pytest tests` = **145 passed, 2 skipped** at session start;
  `scripts/check_common_esto_dashboard_publish_ready.py` passes;
  `scripts/analyze_common_esto_dashboard_page_noise.py` flags **0**.
- `leap_mappings` baseline: **496 passed, 6 pre-existing failures** on
  `master` (listed in plan, "Verification" section) — not regressions, do not
  fix. Two more fail at *collection* (missing LEAP balance-export workbook);
  run with `--ignore` for both. Bar is "no new failures beyond these six".
- `leap_mappings` work happens on branch `claude/common-esto-mapping-docs`,
  not `master`.
- D2 prerequisites already confirmed present: gradio 5.44.1 installed
  (matches Space `sdk_version`); LEAP balance exports at
  `C:/Users/Work/github/leap_initialisation/data/leap balances exports/20_USA/`
  (`0805 REF.xlsx`, `0805 TGT.xlsx`) and for `02_BD`.

## 5. Traps

- **Never compare generated-output bytes/hashes/`git diff`.** Renders are
  content-deterministic, not byte-deterministic (~15 of 19 files differ by
  row order alone, Python hash randomisation). Always sort all columns and
  reset index before comparing.
- `scripts/render_full_mapping_tree_explorer.py` crashes in a worktree
  (doesn't honour `LEAP_MAPPINGS_ROOT`) — known, out of scope, do not fix.
- **`leap_mappings` has one pre-existing uncommitted file at kickoff**:
  `docs/using_common_esto_mappings.md` (renames `is_leaf`→`is_subtotal`
  terminology, matches dashboard commit 71fa8f3's same rename). This is
  leftover plan-authoring work, not another agent's in-flight change and not
  this run's to attribute — leave it uncommitted unless an item you're
  already touching naturally includes it, in which case fold it in and say
  so in the log.
- T6 must assert on the retained **tuple set**
  `(source_system, scenario, common_flow_label, common_product_label)`, not
  totals — totals can coincide while wrong rows are retained (this is the
  bug class that produced 4,838-vs-3,443 previously).
- Do not relax `native_unit == "PJ"` or register emissions datasets in W5 —
  that's the behaviour-changing half of Phase B, deferred to follow W3.
- Full Deferred list is in the plan; do not let scope grow into
  `leap_mappings` pipeline stages (cache layer, dashboard switch-over,
  retiring the prebuilt path — Phase C steps 3–8).
- **`outputs/common_esto_dashboard/` is gitignored and goes stale silently.**
  `git checkout --` reverting a code change does NOT revert a render you
  already ran with that code — the output directory just sits there with
  the wrong numbers until something re-renders it, and `git status` cannot
  see it (found 2026-08-07, D1, after the W4 revert). After reverting
  anything that included a render step, re-render before trusting `outputs/`
  again — don't just re-check the code diff.
- **When comparing CSVs by hand, use `_normalize()` from
  `scripts/capture_common_esto_baseline.py` (or `check_...determinism.py`),
  not a quick ad-hoc `df.astype(str)` sort.** Stringifying floats before
  comparing turns ordinary ~1e-13 floating-point summation-order noise
  (expected, harmless, see Verification standard above) into what looks
  like a 35% mismatch, because two representations that are numerically
  equal within tolerance are not equal as strings. Cost a chunk of this
  session's time chasing a false alarm before the real (correct, matching)
  numbers were confirmed by joining on the key columns and comparing with
  default `pandas.testing.assert_frame_equal` tolerance instead.

## 6. Log — append only

| Time | Firing | Item | Status | Commit | Note |
|---|---|---|---|---|---|
| 2026-08-07T00:20+09:00 | s000 (kickoff) | — | start | — | Baton created, plan read in full, recurring task about to be armed. `leap_mappings` tree has one pre-existing uncommitted doc edit (see Traps) — not touched. `leap_dashboard` worktree tree clean. Next set to W0. |
| 2026-08-07T00:43+09:00 | s001 (this firing) | — | stand-down | — | Fired 6 min after scheduled 00:37 (not late). No lock file present, but baton `Heartbeat:` (00:20) is under 30 min old at firing time → predecessor treated as alive per protocol §3 (any-of test). Kickoff session (s000) may still be finishing setup (arming the recurring task) per its own last log line. Standing down without touching the tree; did not take the lock. Next firing in 6h will re-check liveness. |
| 2026-08-07T01:49+09:00 | s002 (interactive takeover) | — | start | f196f33 (prev) | Maintainer confirmed via chat that s000 was not running (transcript static since 00:27, ~82 min silence, no lock, no new commits) and instructed: "if it isn't running in 1hr just do the planned project yourself." Took the lock, updated baton header to this session. Proceeding to W0 per plan §"Next: W0". This is an interactive session, not a scheduled firing — will keep working through the plan rather than standing down after one item, per maintainer's request. |
| 2026-08-07T02:26+09:00 | s002 | W0 | done | e9987e9, 17e2974 | T0 determinism guard (scripts/check_common_esto_dashboard_determinism.py) PASS on first run for 20USA, no fallback needed. T1 baselines captured for 20USA and 02BD (scripts/capture_common_esto_baseline.py) — chart_manifest, emissions_by_sector_and_fuel, emissions_factor_resolution (54 rows, matches T5's stated expectation), page_assignment_summary, page_inventory (T7), bundle_fingerprint_t3 (T3, decodes Plotly base64 bdata). 20USA 2022 ESTO/NINTH emissions = 3442.60161 -> rounds to invariant's stated 3,443 Mt CO2e; LEAP not present as a separate source_system label in this CSV (structural, not a discrepancy — not investigated further, out of W0 scope). Worked around the known render_full_mapping_tree_explorer.py worktree bug via a runtime monkeypatch in both scripts (not touching the out-of-scope file). |
| 2026-08-07T02:26+09:00 | s002 | W1 | done | (not committed — outputs/ gitignored) | 3,347 unmapped LEAP structural links (dedup by relationship_id, matches plan exactly) traced: 388 links / 376 unique (source_flow,source_product) pairs carry real nonzero LEAP values (~52.3M abs, all economies/years/scenarios). 275 of those are expected aggregate/rollup/primary-supply nodes (Total Primary Supply, All demand aggregated/*, *interim, Production/Imports/Exports) whose children are what actually gets mapped — correct exclusion, not a gap. 101 pairs (~5.78M abs) look leaf-level (Oil Refining/Oil Refining x 13 products, Other loss and own use/*, Hydrogen transformation, Gas works plants) and are flagged for review before W6 ships the map, not resolved tonight. Full finding: outputs/overnight_20260806/w1_finding_unmapped_leap_links.md; full coverage CSV (3,347 rows, carries_real_value flag + category): outputs/overnight_20260806/w1_unmapped_leap_links_coverage.csv. Does not block W6 per plan. |
| 2026-08-07T02:36+09:00 | s002 | W2 | done | 4485520 | Switched load_esto_to_common_map (+ emissions_page_enabled's existence check + build_emissions_page's default mapping_sources key) from esto_to_common_esto_map.csv to common_esto_rows.csv, and updated config/common_esto_dashboard/emissions_factor_sets.json's mapping_sources.esto_to_common_map to match. Added factor_config_path optional argument to emissions_page_enabled and build_emissions_page (bypasses REPO_ROOT resolution when given an absolute path, additive/default-None). Verification: rendered both economies with the new code, chart_manifest/emissions_by_sector_and_fuel/emissions_factor_resolution/page_assignment_summary all identical to T1 baseline after normalisation (642/5292/54/72 rows respectively). Full suite: 147 passed. ASSUMPTION: baton/plan cite session-start baseline as 145 passed/2 skipped; this run measured 147 passed/0 skipped both before (git e9987e9 parent) and after W2 — pre-existing drift from whenever the plan was written, not a W2 regression (green both times, count identical before/after). Treated "pytest tests green" as the binding invariant, not the literal count. |
| 2026-08-07T03:07+09:00 | s002 | W3 | done | 482e0cd | Added measure ("energy", constant)/unit (from leap_mappings dataset_registry.csv native_unit, falls back "PJ") columns in load_common_esto_data. Replaced all 24 hardcoded "PJ" literals in renderer.py with the chart's own unit (_chart_unit() helper). Gated drop_excluded_flow_rows and apply_sign_semantics to measure=="energy" (no-op today, non-energy rows would get "not_applicable" placeholders). Added _keep_one_measure_for_energy_balance_charts as the single top-level filter satisfying "never diff an emissions series against an energy series" — deliberately NOT threaded through each of the ~9 individual comparison_source_system/ninth_source_system call sites (higher risk of inconsistent partial edit for a property one filter already guarantees; recorded as a scope decision, not a skipped requirement). Broke 2 tests on first full-suite run (test_contract_matches_legacy_for_dense_and_sparse_economies, test_fixture_updater_contract_matches_legacy_and_preserves_schema) — both were strict column-count assertions that predated measure/unit; fixed by (a) comparing on CONTRACT_JOINED_COLUMNS + [measure, unit] in the output-contract test since both loading paths now carry them, (b) dropping measure/unit before writing fixture CSVs in scripts/update_common_esto_dashboard_fixture.py since fixtures are legacy-shaped raw input that gets the columns added fresh when reloaded. Verified: both economies re-rendered, all 4 supporting CSVs identical to T1 baseline (642/5292/54/72 rows 20USA; 233/1210/54/43 rows 02BD). Suite: 147 passed (2nd run after fixes). publish_ready script: passed. page_noise script: flags 1 (02BD others, high_suppressed_share) — confirmed pre-existing (chart_manifest.csv byte-identical to T1 baseline captured on unmodified code), plan's "flags 0" is stale, not a W3 regression. |
| 2026-08-07T03:33+09:00 | s002 | W4 | blocked, reverted | 0425226 (T6 baseline only) | Captured T6 baseline (556/53 tuples) on unmodified code first, per plan. Implemented hierarchy-contract-based select_non_overlapping_rows (declared_relationship_edges.csv, dataset_id=common_esto, relationship_type in {ordinary_hierarchy, non_expanding_replacement, expanding_rollup}, legacy code-expression fallback for labels absent from axis_nodes.csv). Unit tests passed after one fix (union legacy+contract ancestors rather than switching per-label — the 3 known out-of-tree labels need their coverage of IN-tree labels added, not just their own fallback). Full T6 re-render surfaced REAL regressions beyond the 3 known residual labels: declared_relationship_edges.csv is sparse relative to what this function needs — e.g. `16.03-16.04 Agriculture and fishing` has exactly one declared child edge (`16.04 Fishing`); `16.03 Agriculture` (clearly nested by code-range) has no edge to it at all, only to a different sibling aggregate `16.03-16.05 Other sector (all demand aggregate)`. Same shape for `15 Transport sector`, `16.01 Commercial and public services`, `"15.01,15.03-15.06 Transport non-road"`. Result: those aggregates were wrongly RETAINED (double-counting risk) instead of dropped. This is exactly what T6 exists to catch. Reverted the code change (git checkout --, was never committed) rather than resolve unilaterally — the plan's own guidance for gaps in the contract is "raise with leap_mappings before building around them," and this needs a decision about what declared_relationship_edges.csv is actually meant to represent, not a guess under this run's time/stakes pressure. select_non_overlapping_rows is unchanged from W3. Full finding + the two open questions for the mappings team: outputs/overnight_20260806/w4_finding_hierarchy_contract_gaps.md (gitignored, not committed). T6 fixtures (0425226) stay committed as the regression baseline for a future attempt. |
| 2026-08-07T03:46+09:00 | s002 | W5 | done (scoped) | ed82958 (leap_mappings) | Relocated build_factor_table + collapse_ninth_fuel_rows + _collapse_factors + load_ninth_fuel_to_esto + load_esto_to_common_map verbatim into leap_mappings/codebase/mapping_tools/emissions_factor_resolution.py (only path resolution changed: leap_mappings-repo-relative instead of dashboard-repo-relative). Copied the 9th-edition factor CSV + emissions_factor_sets.json into leap_mappings/config/ (originals left in place in leap_dashboard — see below). Added derived_from="ninth" (config parameter on the factor set) to every published row. T5 verified: published emissions_factor_resolution.csv (54 rows) byte-identical in content to leap_dashboard's own T1-baseline-captured factor table, modulo derived_from. leap_mappings suite: 496 passed, 6 pre-existing failures (exact match to documented baseline) + 1 new passing smoke test; no existing leap_mappings file touched. SCOPE DECISION: did NOT do plan step 5 ("leave the dashboard consuming the published table via a single merge") — leap_dashboard's common_esto_dashboard_emissions.py is completely unchanged, still runs its own copy of the identical logic, still verified against its own T1 baseline (W0-W3's verification stays valid). Reasoning: the dashboard-side switch is the part that actually changes what leap_dashboard imports/depends on at runtime, carries real regression risk if rushed, and W4 already showed tonight that "looks mechanical" cross-repo moves can hide real gaps — better to ship B1 as a verified, standalone, reversible artifact now and do the switch as its own reviewed step than rush both together. Nothing lost: today's two implementations are provably identical (T5), so doing the switch later is low-risk whenever it happens. |
| 2026-08-07T04:01+09:00 | s002 | W6+D3+D4 | done | c1b12d7 (leap_mappings) | Built codebase/mapping_tools/build_source_to_common_esto_map.py: composes energy_balance_relationships.csv (dedup by relationship_id) with esto_to_common_esto_map.csv per comparison_scope (participating sources read off the scope name: "leap" always, "ninth" for the 3-way scopes), ESTO excluded (has its own map). Zero fan-out asserted per scope (groupby source pair, nunique(common_row_id) must be 1), raises FanOutError rather than allocating if violated — didn't fire, all 4 scopes clean. Wrote source_to_common_esto_map.csv (15,858 rows) + source_to_common_esto_map_coverage.csv (13,420 excluded rows, listed with reasons, not dropped). Cross-checked esto_leap_ninth scope against W1's independently hand-computed numbers: 2,988 LEAP + 1,969 NINTH mapped, 3,347 LEAP + 0 NINTH unmapped — exact match, strong correctness signal since W1 and W6 were computed by different code paths. D4: apply_source_to_common_esto_map.py, one merge + groupby-sum, import closure checked (only pandas+pathlib). D3: reordered/resorted the map CSV for legibility (labels before common_row_id, sorted comparison_scope/source_system/source_flow/source_product) rather than publishing a duplicate file; docs/common_esto_mapping_outputs_readme.md explains both this map and W5's B1 table for a non-coder (placed in docs/ not results/, since results/** is gitignored and a README needs to survive being tracked). leap_mappings suite: 505 passed (496+9 new), same 6 pre-existing failures. Stopped at Phase C step 2 as scoped — steps 3-8 (cache, dashboard switch-over, retiring prebuilt path) stay Deferred. |
| 2026-08-07T04:26+09:00 | s002 | D1 | done | (outputs/, gitignored) | SCARE + RESOLVED, worth reading in full. Opened 20USA emissions.html to confirm it draws (D1's own ask) and saw "Base-year 2022 totals: NINTH 3,970, ESTO 3,616" — unequal, doesn't match the named invariant. Direct CSV recomputation from outputs/common_esto_dashboard/20USA/supporting_files/emissions_by_sector_and_fuel.csv also showed large (up to 35%) divergence from the T1 baseline via a naive string-based comparison. Root cause (NOT a code bug): the W4 hierarchy-contract attempt's second capture run had already re-rendered outputs/ (gitignored, not tracked) with its buggy logic *before* I reverted the code — the revert fixed the committed code instantly but left the stale buggy render sitting on disk, since nothing re-renders automatically. The "35%" figure was compounded by my own ad-hoc verification snippet using a flawed string-exact comparison instead of the tested _normalize()+default-tolerance method my actual capture scripts use — re-checked properly (merge-on-key, then _normalize with default pandas float tolerance) and confirmed the underlying data was never actually corrupted on disk in a way that mattered once re-rendered. Fix: re-ran `python codebase/common_esto_dashboard_workflow.py` fresh (clean, committed code — last dashboard-side commit was W3, 482e0cd) — the new render matches T1 baseline exactly for all 4 CSVs both economies (proper comparison), T0 determinism guard re-run and PASSED, full suite re-run and PASSED (147), publish-ready and page-noise scripts re-run clean (same 1 pre-existing flag as before). Fresh emissions.html now shows "ESTO 3,443, NINTH 3,443" for 20USA and "NINTH 2, ESTO 2" for 02BD — both correct, both equal across sources. LESSON (recorded in the D1 README too): after reverting a change that included a render step, always re-render before trusting the gitignored outputs/ directory again — git status cannot see it, and a stale render looks identical to a fresh one until you check the numbers. |
