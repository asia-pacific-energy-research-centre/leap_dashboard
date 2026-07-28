# Documentation audit — leap_dashboard — 2026-07-28

## Scope and method

This audit covers all **14 tracked Markdown files** found by
`git ls-files '*.md'` in `leap_dashboard`. None are currently under an archive
directory, because this repository has no `docs/archive/` directory at all.

Each file's stated purpose and status was compared with:

- local `master` (`3327764`), `origin/master`, and recent commit history;
- the dirty checkout and all three local branches and worktrees;
- the current `leap_mappings` artifacts on disk, read directly;
- this repository's own `AGENTS.md` rules on layout and prompt archival;
- a relative-link check across every tracked Markdown file.

This is a classification pass. It is not permission to archive or rewrite files
that overlap the unintegrated `codex/output-contract-phase-2` worktree.

## Main findings

1. **`docs/handover_mapping_diagnostics.md` contains two claims that no longer
   hold**, and it is the document a new owner is most likely to read first. Its
   "Confirmed: current artifacts double every ordinary-ESTO rollup value"
   section states the defect "is not fixed" and cites 840,378 wrongly-identified
   rows. Measured on 2026-07-28, the artifact holds **5,320,932 rows, 100%
   `ESTO_EXTENDED`, zero wrong**. It also directs readers to
   `leap_mappings/docs/prompts/rebuild_esto_rollup_source_identity_prompt.md`,
   which is tracked **only on an unmerged branch** and is absent from a clean
   `leap_mappings` checkout. Both are queued as DASHQ-003 and DASHQ-004.
2. **The prompt-archival workflow required by `AGENTS.md` cannot be followed
   here.** `AGENTS.md` instructs agents to move completed prompts from
   `docs/prompts/` into `docs/archive/`, citing the `leap_mappings` pattern.
   `docs/archive/` does not exist. Queued as DASHQ-010.
3. **There is no repository-level work queue or handover index.** Backlog
   material is spread across `docs/future_dashboard_backlog.md`,
   `docs/common_esto_dashboard_plan.md`, the follow-up list inside
   `docs/handover_mapping_diagnostics.md`, and `zip_extraction_plan.md`. This
   audit adds `docs/work_queue.md` as the single controlling queue; the other
   four remain as source material and must not be maintained as parallel
   backlogs.
4. **Three planning documents are reconciled to dates that predate a month of
   work.** `common_esto_dashboard_plan.md` and
   `common_esto_dashboard_page_status.md` are both stamped 2026-06-28;
   `workflow_inventory.md` is stamped 2026-07-07. Roughly 25 commits landed
   between 2026-07-26 and 2026-07-28 alone, including the entire rollup-graph
   and diagnostics-page surface. Their stamps are honest, but a reader will
   mistake them for current.
5. **`zip_extraction_plan.md` is the only narrative document at the repository
   root.** Every other one lives under `docs/`. Queued as DASHQ-016.
6. **No broken relative links were found.** The link check across all 14 files
   returned nothing. The one genuine cross-repository breakage is finding 1
   above, which a relative-link check cannot see.
7. **The decision log is well formed and should be the model for the others.**
   `docs/special_rules_and_design_decisions.md` already defines `DASH-###` and
   cross-repository `CROSS-###` IDs with single authoritative ownership. The
   cross-repository index adopts that convention rather than inventing another.

## Active-file disposition

| File | Classification | Action |
|---|---|---|
| `AGENTS.md` | Canonical instructions | Keep. Accurate on scope, upstream boundary, and validation steps. Its prompt-archival rule becomes followable only after DASHQ-010. |
| `README.md` | Repository entry point | Keep. Add a link to `docs/work_queue.md` and the cross-repository index once DASHQ-011 settles the handover structure. |
| `docs/work_queue.md` | **New** controlling queue | Created by this audit. This is the single backlog of record for the repository. |
| `docs/documentation_audit_20260728.md` | **New** this file | Dated classification pass. Supersedes ad-hoc doc status notes. |
| `docs/handover_mapping_diagnostics.md` | Handover-critical, partly stale | Keep — it is the richest technical handover material in the repo. Correct the two claims in findings 1 under DASHQ-003/DASHQ-004, keeping the original diagnosis as clearly labelled history. Its five-item "Follow-up dashboard backlog" should be represented in the queue rather than maintained separately. |
| `docs/common_esto_dashboard_guide.md` | Canonical run/usage guide | Keep. Last touched 2026-07-27 and broadly current. Re-verify its run commands during the DASHQ-017 rehearsal. |
| `docs/common_esto_dashboard_plan.md` | Authoritative plan, stale stamp | Keep, but re-reconcile. "Last reconciled: 2026-06-28" predates the rollup-graph, diagnostics-page, health-report, and compressed-intermediate work. Re-date it or mark the pre-July content as historical under DASHQ-011. |
| `docs/common_esto_dashboard_page_status.md` | Evidence document, stale | Keep. Refresh from a reproducible render under DASHQ-012; the current counts describe a 2026-06-28 dataset. Do not let it describe obsolete fixture structure as current. |
| `docs/future_dashboard_backlog.md` | Deferred feature backlog | Keep as the detailed acceptance criteria for DASHQ-012 and DASHQ-013. Point its header at `docs/work_queue.md` so it is not read as a second controlling queue. |
| `docs/special_rules_and_design_decisions.md` | Canonical decision log | Keep. Add any decision arising from DASHQ-006 (output contract) and DASHQ-015 (legacy repository). Cross-repository entries stay single-owned. |
| `docs/workflow_inventory.md` | Navigation reference, stale stamp | Keep; re-audit after the output-contract worktree is integrated, since that changes which readers are production surface. |
| `docs/common_esto_dashboard_visual_review.md` | Presentation-only review method | Keep. Short, scoped, and still accurate. |
| `docs/common_esto_sankey_balance_routing_design.md` | Design for deliberately disabled work | Keep as-is. Correctly labelled scaffolded-and-disabled, and `future_dashboard_backlog.md` lists Sankey work as out of scope. No action. |
| `docs/legacy_dashboard_comparison_notes.md` | Reference notes on the frozen repo | Keep, but its value depends on DASHQ-015: the repository it describes exists on one machine only, with no GitHub remote. |
| `docs/prompts/anchor_validation_section_rebuild_prompt.md` | Active prompt, not started | Keep in `docs/prompts/`. Execute as DASHQ-009, then archive under DASHQ-010. |
| `zip_extraction_plan.md` | Completed hygiene record, misplaced | Move under `docs/` (DASHQ-016). Its "Last reconciled: 2026-07-22" content is a completed checkpoint record, not live work — archive it once `docs/archive/` exists. |

## Missing handover material

The following do not exist anywhere in this repository and are queued:

- a start-here guide for a new owner (DASHQ-011);
- a render runbook covering the fixture render, the all-economy batch, and the
  publication-readiness and page-noise scripts (DASHQ-011);
- a stated data contract for what the dashboard consumes from `leap_mappings`
  — currently implicit in code and prose (covered by the cross-repository index);
- `docs/archive/` and any archived prompt (DASHQ-010).

## Documentation cleanup sequence

1. Correct the two misleading claims in `docs/handover_mapping_diagnostics.md`
   before anyone acts on them (DASHQ-003, DASHQ-004).
2. Point `future_dashboard_backlog.md` and the handover note's follow-up list at
   `docs/work_queue.md` so there is one controlling backlog.
3. Create `docs/archive/` and move `zip_extraction_plan.md` into `docs/`.
4. Re-reconcile the three stale-stamped planning documents against a current
   render, after the clean upstream baseline exists.
5. Write the start-here guide and render runbook, then test them from a clean
   checkout in the Week 4 rehearsal.
6. Archive completed prompts in the same commit that records their completion.
