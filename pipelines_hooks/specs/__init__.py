"""Spec-status lifecycle gates: landing-commit trailers and their requirement IDs.

:mod:`pipelines_hooks.specs.trailers` implements the PR-only checks of
``plans/refactor/reconciliation-20261006/SPEC-STATUS-LIFECYCLE.md`` section 6
(items 3-5): a product-path change must carry a ``Spec:`` trailer, every
trailered ID must be a real ``specs/*/requirements.md`` row, and every real ID
must already have a bound test in the tree. ``status.json`` generation and the
decomposition checks (items 1-2) are owned elsewhere.
"""
