# Relay baton — emissions-overnight

Protocol: `C:\Users\Work\.claude\relay\RELAY_PROTOCOL.md`. This is the
**state** file. The plan is `docs/prompts/overnight_work_program_20260806.md`
in this repo (never edited by the run); design detail is in
`docs/prompts/measure_aware_dashboard_and_mapping_inversion_plan.md` beside it.

```text
Status:       ACTIVE
Firing:       002             # interactive takeover, not a scheduled firing
Heartbeat:    2026-08-07T02:26+09:00
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
- [ ] W2 — Phase 0 code prep: switch to `common_esto_rows.csv`, add explicit
      factor-config path arg. Invariants must hold. Code edited, verification
      render in progress.
- [ ] W3 — main event: measure/unit columns, gate energy-balance machinery to
      `measure == energy`, pair comparisons on `(source_system, measure)`.
      Verify against T1 baselines — energy charts identical.
- [ ] W4 — frontier parenthood onto the hierarchy contract; write T6 first
      (assert retained tuple *set*, not totals).
- [ ] W5 — Phase B: move factor resolution into `leap_mappings`
      (branch `claude/common-esto-mapping-docs`). T5 gate: resolution CSV
      content-identical after the move.
- [ ] W6 — Phase C map + importable merger (D4) + D3 CSVs, in `leap_mappings`
      on `claude/common-esto-mapping-docs`. Zero fan-out assertion.
- [ ] D1 — rendered dashboard output, 20USA + 02BD, emissions page. Depends
      W2–W5.
- [ ] D2 — local Gradio app proof, screenshot. Depends W2, W5, Phase 0 file
      list. Hand-stage files if the manifest can't be satisfied — do not
      merge, do not deploy.
- [ ] D3 — legible mapping CSVs + README. Part of W6.
- [ ] D4 — importable merger with docstring, worked example, test. Part of
      W6.

**Next: W2** — code edited (common_esto_dashboard_emissions.py +
emissions_factor_sets.json), verification render running.

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

## 6. Log — append only

| Time | Firing | Item | Status | Commit | Note |
|---|---|---|---|---|---|
| 2026-08-07T00:20+09:00 | s000 (kickoff) | — | start | — | Baton created, plan read in full, recurring task about to be armed. `leap_mappings` tree has one pre-existing uncommitted doc edit (see Traps) — not touched. `leap_dashboard` worktree tree clean. Next set to W0. |
| 2026-08-07T00:43+09:00 | s001 (this firing) | — | stand-down | — | Fired 6 min after scheduled 00:37 (not late). No lock file present, but baton `Heartbeat:` (00:20) is under 30 min old at firing time → predecessor treated as alive per protocol §3 (any-of test). Kickoff session (s000) may still be finishing setup (arming the recurring task) per its own last log line. Standing down without touching the tree; did not take the lock. Next firing in 6h will re-check liveness. |
| 2026-08-07T01:49+09:00 | s002 (interactive takeover) | — | start | f196f33 (prev) | Maintainer confirmed via chat that s000 was not running (transcript static since 00:27, ~82 min silence, no lock, no new commits) and instructed: "if it isn't running in 1hr just do the planned project yourself." Took the lock, updated baton header to this session. Proceeding to W0 per plan §"Next: W0". This is an interactive session, not a scheduled firing — will keep working through the plan rather than standing down after one item, per maintainer's request. |
| 2026-08-07T02:26+09:00 | s002 | W0 | done | e9987e9, 17e2974 | T0 determinism guard (scripts/check_common_esto_dashboard_determinism.py) PASS on first run for 20USA, no fallback needed. T1 baselines captured for 20USA and 02BD (scripts/capture_common_esto_baseline.py) — chart_manifest, emissions_by_sector_and_fuel, emissions_factor_resolution (54 rows, matches T5's stated expectation), page_assignment_summary, page_inventory (T7), bundle_fingerprint_t3 (T3, decodes Plotly base64 bdata). 20USA 2022 ESTO/NINTH emissions = 3442.60161 -> rounds to invariant's stated 3,443 Mt CO2e; LEAP not present as a separate source_system label in this CSV (structural, not a discrepancy — not investigated further, out of W0 scope). Worked around the known render_full_mapping_tree_explorer.py worktree bug via a runtime monkeypatch in both scripts (not touching the out-of-scope file). |
| 2026-08-07T02:26+09:00 | s002 | W1 | done | (not committed — outputs/ gitignored) | 3,347 unmapped LEAP structural links (dedup by relationship_id, matches plan exactly) traced: 388 links / 376 unique (source_flow,source_product) pairs carry real nonzero LEAP values (~52.3M abs, all economies/years/scenarios). 275 of those are expected aggregate/rollup/primary-supply nodes (Total Primary Supply, All demand aggregated/*, *interim, Production/Imports/Exports) whose children are what actually gets mapped — correct exclusion, not a gap. 101 pairs (~5.78M abs) look leaf-level (Oil Refining/Oil Refining x 13 products, Other loss and own use/*, Hydrogen transformation, Gas works plants) and are flagged for review before W6 ships the map, not resolved tonight. Full finding: outputs/overnight_20260806/w1_finding_unmapped_leap_links.md; full coverage CSV (3,347 rows, carries_real_value flag + category): outputs/overnight_20260806/w1_unmapped_leap_links_coverage.csv. Does not block W6 per plan. |
| 2026-08-07T02:26+09:00 | s002 | W2 | in progress | uncommitted | Switched load_esto_to_common_map (+ emissions_page_enabled's existence check + build_emissions_page's default mapping_sources key) from esto_to_common_esto_map.csv to common_esto_rows.csv, and updated config/common_esto_dashboard/emissions_factor_sets.json's mapping_sources.esto_to_common_map to match (same 10,682 rows, verified set-identical per plan). Added factor_config_path optional argument to emissions_page_enabled and build_emissions_page (bypasses REPO_ROOT resolution when given an absolute path, additive/default-None so no caller breaks) — the portable-layout ask from Phase 0 step 2. tests/test_emissions_page.py (10 tests, uses its own fixture paths, doesn't touch the default) passed already. Verification render of 20USA vs T1 baseline running in background (bczg780r1); will run pytest tests -q after. |
