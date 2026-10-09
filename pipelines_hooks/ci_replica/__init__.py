"""CI-shaped gates: logic a hosted workflow's own job needs, not a pre-commit stage.

``pr-test-scope`` maps a pull request's diff to the tests it could plausibly
break, so a caller's gates job can run that subset on ``pull_request`` and
reserve the full suite for `push` to main and release tags.
"""
