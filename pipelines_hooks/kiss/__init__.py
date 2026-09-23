"""KISS 0.4.10 gates: diff-scoped staged gate and enforced census.

KISS has two dangerous defaults: bare ``kiss check`` writes a self-calibrating
``.kissconfig``, and a multi-path ``check`` reports a false clean. Every run
here therefore passes ``--config .config/kiss.toml`` and exactly ONE path.
"""
