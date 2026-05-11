# leap_dashboard

Dashboard generation and publishing for LEAP energy model results.

Takes LEAP balance exports and ESTO/9th projection mappings as inputs and produces
an interactive HTML dashboard published via GitHub Pages.

## Inputs required

- `data/inputs/` — LEAP balance exports (CSV/Excel), placed here but not committed
- `config/leap_mappings.xlsx` — fuel/sector mapping definitions
- `config/leap_comparison_dashboard_template_v2.json` — chart template

## Running the dashboard workflow

```bash
python codebase/dashboard_workflow.py
```

Output HTML is written to `docs/` and committed so GitHub Pages picks it up.

## Viewing the published dashboard

`https://<org>.github.io/leap_dashboard/`

## Structure

```
codebase/               Python source (mirrors leap_utilities layout)
config/                 Templates, mappings, schema files
data/inputs/            Raw LEAP exports (gitignored)
outputs/                Intermediate processing outputs (gitignored)
docs/                   GitHub Pages site root
  dashboards/           Navigation HTML pages
  charts/               Per-node energy balance chart HTML files
  supporting_files/     Audit CSVs and diagnostic outputs
```
