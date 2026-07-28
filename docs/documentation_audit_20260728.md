# Documentation audit - leap_dashboard - 2026-07-28

## Scope and standard

This preservation-first audit reviewed all 19 Markdown files tracked at the
start of the pass and the archive index created by the pass: 20 dispositions in
total. Every file was read in full. Claims were checked against the current
code/config/script inventory, recent Git history, the upstream handover
contracts, the active dirty diff, and relative-link resolution.

The decision standard was:

- keep a current document when it has a distinct operational, design, evidence,
  or handover role;
- update high-confidence stale statements and misleading navigation;
- archive completed or superseded plans when they retain useful rationale;
- merge only when the destination preserves all unique content;
- delete only when a file has no unique information or evidence value.

No document met the deletion standard.

## Result

| Disposition | Count | Meaning |
|---|---:|---|
| Keep as-is | 7 | Distinct role and no high-confidence correction required. |
| Keep and update | 11 | Distinct role retained; current-state, status, or navigation corrections applied. |
| Archive | 2 | No longer live guidance, but preserved for historical evidence and unique checklists. |
| Merge | 0 | Earlier backlog consolidation was already complete. |
| Delete | 0 | Nothing lacked evidence or unique information strongly enough to remove. |

The audit created `docs/archive/`, moved the former
`docs/future_dashboard_backlog.md` and root `zip_extraction_plan.md` there, and
added an archive index. The live backlog remains only in `docs/work_queue.md`.

## High-confidence corrections

1. `README.md` and `docs/common_esto_dashboard_guide.md` said the workflow's
   default economy was only `20_USA`. The current workflow default is
   `["20_USA", "02_BD"]`; the tracked test fixture remains USA-only.
2. `docs/common_esto_dashboard_plan.md` described the June implementation
   boundary. It now records strict opt-in v1 contract support, diagnostics,
   provenance, health-report, and maintained explorer surfaces while retaining
   the June page counts as explicitly dated evidence.
3. `docs/common_esto_dashboard_page_status.md` used the heading "Current chart
   count" for a 2026-06-28 render. The heading and banner now make the evidence
   date explicit; the counts were preserved.
4. `docs/workflow_inventory.md` omitted current diagnostics, provenance,
   contract, fragment, health-report, and tree-explorer surfaces. The inventory
   now distinguishes maintained entry points from the retained older explorer
   prototype.
5. `docs/common_esto_output_contract_migration.md` still presented integrated
   work as a Phase 2 queue. It now separates completed strict opt-in support
   from the remaining clean-generation/all-economy gate in DASHQ-007.
6. The active anchor-validation prompt cited an absent completed mappings
   prompt and described its doubling defect as current. It now records the
   resolved incident and requires counts from the same selected run. The prompt
   remains active because the related renderer/test diff is uncommitted.
7. `docs/work_queue.md` had post-snapshot completion notes that contradicted
   stale status cells for DASHQ-003, DASHQ-004, DASHQ-006, and DASHQ-025. Those
   cells now agree with the evidence. DASHQ-010 and DASHQ-016 record the archive
   and document-placement work completed by this audit.
8. A second editorial pass corrected `AGENTS.md` so the two-economy production
   default is not confused with the USA-only test fixture, and replaced the
   unsupported singular `COMMON_ESTO_ECONOMY` example with
   `COMMON_ESTO_ECONOMIES`.

## Document-by-document disposition

| File | Role/status | Evidence and unique information | Decision and action |
|---|---|---|---|
| `AGENTS.md` | Canonical repository instructions | Defines production boundary, upstream ownership, prompt archival, validation, and safety rules. Its run section incorrectly described the two-economy production default as a USA-fixture render. | **Keep/update:** distinguish the production default from the focused USA test fixture. |
| `README.md` | Repository entry point | Shortest route to run, artifacts, tests, layout, and handover. | **Keep/update:** corrected default economies; linked queue and audit. |
| `docs/common_esto_dashboard_guide.md` | Canonical operating guide | Detailed inputs, fixture refresh, batch render, config, publication, and smoke tests. Commands and paths exist. | **Keep/update:** corrected default economies and environment-variable name while preserving USA fixture guidance. |
| `docs/common_esto_dashboard_page_status.md` | Dated render evidence | Unique June page counts, noise findings, and diagnostic-page review. A reproducible replacement render does not yet exist. | **Keep/update:** label counts as 2026-06-28 evidence; refresh remains DASHQ-012. |
| `docs/common_esto_dashboard_plan.md` | Current-state summary plus build history | Unique production-state narrative and historical build rationale; backlog sections already consolidated. | **Keep/update:** add contract/diagnostics/provenance surfaces and route old backlog link to archive. |
| `docs/common_esto_dashboard_visual_review.md` | Presentation review record | Unique colour, legend, responsive-layout findings and acceptance criteria; planned items remain valid. | **Keep as-is.** |
| `docs/common_esto_output_contract_migration.md` | Contract migration status | Unique strict-selection rules, equivalence evidence, prototype disposition, and metadata-contract limitation. | **Keep/update:** separate integrated work from DASHQ-007 operational gate. |
| `docs/common_esto_sankey_balance_routing_design.md` | Disabled future-design contract | Required route fields and double-counting acceptance criteria remain unique. Config is disabled and all four draft routes are disabled. | **Keep as-is.** |
| `docs/documentation_audit_20260728.md` | Dated exhaustive disposition | Records evidence, corrections, per-file decisions, and retained uncertainties. | **Keep/update:** replaced the earlier 14-file classification pass with this full 20-disposition audit. |
| `docs/archive/README.md` | Archive navigation and policy | Makes the AGENTS prompt/archive workflow usable and prevents archived plans being mistaken for live instructions. | **Keep/update:** created. |
| `docs/archive/future_dashboard_backlog_20260628.md` | Superseded backlog record | Original prioritization and pre-work checklist remain useful; live items already exist in the queue. | **Archive:** moved from `docs/`, fixed links, and added a status banner. |
| `docs/archive/repository_cleanup_plan_20260722.md` | Completed cleanup record | Preserves security, packaging, fixture, publication, CI, and checkpoint evidence from the repository cleanup. | **Archive:** moved from root, updated stale live-navigation statements, retained all findings. |
| `docs/handover/dashboard_pipeline_agent_guide.md` | Current agent runbook | Unique toggles, destructive boundaries, schemas, success artifacts, failure triage, release gates, and handoff evidence. Verified 2026-07-28. | **Keep as-is.** |
| `docs/handover/dashboard_pipeline_guide.md` | Current reader handover | Unique compact pipeline, inputs, semantics, outputs, publication, failures, and observed-run evidence. Verified 2026-07-28. | **Keep as-is.** |
| `docs/handover_mapping_diagnostics.md` | Deep technical handover/history | Richest record of rollup diagnostics, Extended behavior, health report, provenance, explorer, and resolved doubling incident. Current incident language was already corrected in `1d309c3`. | **Keep as-is.** |
| `docs/legacy_dashboard_comparison_notes.md` | Frozen-reference evidence | Unique commit boundary, visual comparison, and reproducibility limits. It correctly locates the retired workflow inside the sibling legacy repository. | **Keep as-is.** |
| `docs/prompts/anchor_validation_section_rebuild_prompt.md` | Active prompt | Objective and acceptance criteria correspond to the current dirty diagnostics renderer/test work. It is not yet implemented, verified, and committed. | **Keep/update:** correct resolved prerequisite; leave in `docs/prompts/` until completion. |
| `docs/special_rules_and_design_decisions.md` | Canonical decision log | DASH-001 through DASH-005 define non-derivable presentation and architecture rules with history and validation. | **Keep as-is.** |
| `docs/work_queue.md` | Single controlling queue | Owns current statuses, dependencies, risks, deferred decisions, and handover schedule. | **Keep/update:** reconcile contradictory status rows and archive/document-placement completions. |
| `docs/workflow_inventory.md` | Current code-surface navigation | Distinguishes runnable workflows, supporting modules, and retained prototypes. | **Keep/update:** reconcile against every current `codebase/` and `scripts/` file. |

## Validation evidence

- Enumerated tracked Markdown with `git ls-files '*.md'`.
- Read all tracked documents completely.
- Checked the current `codebase/`, `scripts/`, `tests/`, and dashboard config
  inventories.
- Confirmed `sankey_diagrams.enabled = false` and all draft routes disabled.
- Compared documentation status claims with recent commits through `1d309c3`.
- Inspected but did not modify the unrelated dirty files
  `codebase/common_esto_dashboard_mapping_diagnostics.py` and
  `tests/test_mapping_diagnostics_page.py`.
- Re-ran relative-link validation after edits; results are recorded in the
  completion report for this audit commit.

## Remaining uncertainties and deliberate non-actions

- Page counts and page-noise findings remain dated until DASHQ-012 produces a
  reproducible all-economy render from a current upstream generation.
- Existing mapping result files predate integrated v1 contract publication.
  DASHQ-007 remains the clean-generation and all-economy release gate.
- The anchor-validation implementation is actively dirty and not part of this
  documentation commit. Its prompt must not be archived until implementation,
  tests, and commit are complete.
- The older tree-explorer prototype is retained because it still has comparison
  value. No code/config deletion was inferred from documentation redundancy.
- The frozen legacy repository remains a local-machine preservation risk under
  DASHQ-015; this audit does not authorize publishing or deleting it.
