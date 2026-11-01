# Quickstart — PIPE-CONNSPEC

Show the generated status and the spec gates working in this repository.

1. Compute the status: `uv run pipelines-hook spec-status`. It prints the leaf-row tally and fails only when a `status.json` is tracked.
2. Check the decomposition: `uv run pipelines-hook spec-decomposition`.
3. Run the proof of the hot-path rows: `uv run pytest tests/hooks/test_engine_state.py::test_generator_and_engine_agree` (PIPE-CONNSPEC-R009.2, planned until `engine_state.py` exists) and `uv run pytest tests/hooks/test_spec_status.py`.
4. Check one connector child row: `uv run pytest tests/test_connector_consumer_r102.py` (PIPE-CONNSPEC-R102.4).
