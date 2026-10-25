# Shared validation test contract

`tests/hooks/test_validation.py` exercises real subprocesses and disposable Git
repositories. Fixtures cover clean and bad input, unavailable prerequisites,
advisory findings, duplicate declarations, passive Git events, and bounded
execution. `tests/hooks/test_validation_acceptance.py` preserves the old Meristem
gitignore acceptance against the existing shared checker.

Tests use local source and installed dependencies. They do not install tools,
contact a remote, or claim that the historical Meristem pull trigger was reproduced.
Report executed tests separately from ordinary hooks and CI.

`tests/hooks/test_validation_lifecycle.py` runs both hook registrations through
installed pre-commit without provisioning an environment. It checks advisory
fail, unavailable, and timeout output, and sends real signals to a runner with
a worker and child to verify cleanup and negative signal return codes.

R002 uses `tests/hooks/test_privacy_provenance.py` for CLI and classifier regressions.
Product references pass only for Git-display-name-only candidates.
Attribution, independent strict sources, same-line leaks and prohibited catalog matches fail.
Existing privacy tests retain missing and malformed catalog refusal coverage.

R001.10 to R001.12 use `tests/hooks/test_connector_security_scaffold.py` with disposable Git
repositories: the fuzz and workflow checks write evidence that meets the contract thresholds,
each risky workflow pattern is a finding, the contract takes license additions from `pyproject.toml`
and refuses unknown keys, committed legacy files are findings, and API-to-MCP parity covers
decorated tools, prefixed tools, catalog dispatch, the baseline and the skip case.
