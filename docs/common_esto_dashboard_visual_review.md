# Common ESTO dashboard visual review

## Scope

This review is strictly presentation-only. It must not alter source rows,
calculations, page assignment, comparison scope, values, or chart membership.

## Review method

1. Render the dashboard from the normal workflow.
2. Open each published page in Chromium at a 1920 px desktop viewport, allowing
   Plotly's lazy-loaded charts to render.
3. Inspect the overview plus Power, Refining, Other transformation, Supply, and
   Unassigned pages. Repeat at a narrow viewport before layout changes.
4. Check the visual result alongside the existing page-noise and publication
   readiness checks. These checks are complementary: they identify density and
   file problems, while screenshots reveal hierarchy, contrast, wrapping, and
   wasted space.

## Findings and plan

| Priority | Finding | Presentation-only response | Status |
| --- | --- | --- | --- |
| High | Plotly assigns colours by trace position. As a result, ESTO, LEAP, and 9th total lines can change colour between charts with different product counts. | Apply fixed colour-blind-friendly colours to totals: ESTO blue, LEAP vermillion, 9th green; retain existing line/marker semantics. | Implemented |
| High | Dense product legends compete with the chart and visually blend into the page. | Use a slightly smaller legend font, a subtle translucent panel, clear border, and Plotly's standard click/double-click isolation behaviour. | Implemented |
| High | At tablet widths, two chart columns leave Plotly areas and legends too narrow; the header timestamp can clip. | Switch dashboard grids to one column at 900 px and allow the timestamp to wrap beneath the economy context. | Implemented |
| Medium | Product stacks can contain more categories than any categorical palette can uniquely and accessibly distinguish. | Keep current data and trace membership. Trial a muted categorical palette only after reviewing representative large and small economies; do not imply product meaning through colour alone. | Planned |
| Medium | Large legends still occupy substantial vertical space on Supply and Unassigned charts. | Test a compact responsive legend strategy (including an optional chart-level product selector) only if it preserves access to every existing trace. | Planned |
| Medium | Header controls are dense at desktop widths and need a narrow-screen review. | Capture 1280 px and 768 px screenshots; adjust only flex wrapping, spacing, and control sizing if controls overlap or clip. | Planned |
| Low | Some pages have a generous gap between their section chips and first chart row. | Measure after the responsive review and reduce whitespace only where it does not make the header harder to scan. | Planned |

## Acceptance criteria for future visual changes

- The same source/scenario total has the same colour in every chart.
- Legends remain readable and do not overlap titles, axes, or data.
- Charts retain every current trace, value, page, and source/scenario toggle.
- Desktop and narrow-screen screenshots show no clipped controls, timestamps,
  or horizontal overflow.
- Focused dashboard tests, a normal render, page-noise analysis, and
  publication-readiness checks pass.
