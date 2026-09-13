"""Shared, repository-agnostic pre-commit quality gates.

Every gate is one module exposing ``main(argv) -> int`` and is reached through
the single ``pipelines-hook <gate>`` console script (:mod:`pipelines_hooks.cli`).
Exit codes are uniform: 0 clean, 1 findings, 2 the gate could not run.
"""
