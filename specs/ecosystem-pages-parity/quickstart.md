# PIPE-PAGES — Quickstart

The shortest path to see the feature work is to run the served proofs from a checkout of `pipelines`.

## Pages parity and the spec-delivery page

1. Install the test environment: `uv sync`.
2. Run the parity and workflow proofs: `uv run pytest tests/test_pages_fleet_parity.py tests/test_pages_pipeline_contract.py`.
3. Run the spec-delivery page proofs: `uv run pytest tests/test_spec_dashboard_metadata.py tests/test_spec_dashboard_drilldown.py tests/test_spec_dashboard_nav.py`.
4. Generate the page for this checkout: `uv run python scripts/spec_dashboard.py --help` lists the options; the output directory receives `index.html`, `snapshot.json` and `architecture.mmd`.

## Canopy

1. Run the explorer proofs: `uv run pytest tests/test_architecture_explorer.py`.
2. Build the page: `uv run python scripts/architecture_explorer/build.py --help` lists the modes; `main` writes the page, the per-family detail files and `llms.txt`.

## Hooks

1. Run the hook proofs: `uv run pytest tests/hooks`.
2. Run one gate on a repository: `pipelines-hook public-surface --root <repository>`; exit 0 is clean, 1 is a finding, 2 is a gate that cannot run.
