# Relay baton — emissions-overnight

Protocol: `C:\Users\Work\.claude\relay\RELAY_PROTOCOL.md`. This is the
**state** file. The plan is `docs/prompts/overnight_work_program_20260806.md`
in this repo (never edited by the run); design detail is in
`docs/prompts/measure_aware_dashboard_and_mapping_inversion_plan.md` beside it.

```text
Status:       ACTIVE
Firing:       000             # kickoff session, not a firing
Heartbeat:    2026-08-07T00:20+09:00
Started:      2026-08-07T00:20+09:00
Repo:         C:\Users\Work\github\leap_dashboard\.claude\worktrees\dashboard-emissions-page-5c4fbd
Branch:       claude/dashboard-emissions-page-5c4fbd
Plan:         docs\prompts\overnight_work_program_20260806.md
Session id:   local_dcec7536-985e-49c0-8b15-b788512259d0
Transcript:   C:\Users\Work\.claude\projects\C--Users-Work-github-leap-dashboard--claude-worktrees-relay-emissions-overnight-4c8e22\dcec7536-985e-49c0-8b15-b788512259d0.jsonl
Previous id:  none            # this is kickoff
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

- [ ] W0 — guard rails: T0 determinism guard, T1 baselines for 20USA + 02BD,
      committed. **Hard prerequisite — do not start W1+ until W0 baselines
      are committed.**
- [ ] W1 — investigation only, gates nothing: explain the 3,347 unmapped LEAP
      links (real values or not). Does not block W6.
- [ ] W2 — Phase 0 code prep: switch to `common_esto_rows.csv`, add explicit
      factor-config path arg. Invariants must hold.
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

**Next: W0** — nothing has started yet.

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
