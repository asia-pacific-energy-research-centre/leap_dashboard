# Documentation re-review — 2026-08-17

## Baseline and scope

The previous preservation-first documentation pass was the 28 July commit
cluster ending at `77983f4`. This re-review inventoried every tracked Markdown
file, checked relative links, compared active front doors and workflow
inventories with the current `codebase/`, `scripts/`, configuration and Git
history, and treated dated audits/evidence as history rather than live
instructions.

## Material changes since the baseline

- The dashboard now consumes the manifested Common ESTO parquet generation by
  default. Legacy CSV fixtures remain explicit regression inputs.
- Page routing, chart visibility, hierarchy frontiers, guide content,
  emissions, portable variants, colour-workbook maintenance and mapping
  diagnostics all changed substantially and are already covered by their
  dedicated guides, decision log and dated queue entries.
- The measure-aware/emissions overnight programme completed on 7 August. Its
  two prompts and relay record were incorrectly left on active surfaces.
- The old anchor-section prompt has been overtaken by the current diagnostics
  renderer, exception classification and focused tests.

## Actions

- Refreshed `docs/workflow_inventory.md` with the current entry points,
  supporting modules, colour tools and parquet input contract.
- Clarified the production input in `README.md`.
- Archived the completed emissions programme and superseded anchor prompt, and
  repaired current-document references to them.
- Kept dated render evidence, historical comparison notes and the July audit
  unchanged; they remain useful evidence and are clearly not current queues.

## Validation

- All tracked relative Markdown links resolve after the moves.
- Active prompt material under `docs/prompts/` is empty after completed work
  was archived.
- No production code, configuration, generated dashboard or data artifact was
  changed by this review.
