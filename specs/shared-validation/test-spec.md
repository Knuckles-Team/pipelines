# Shared validation test contract

`tests/hooks/test_validation.py` exercises real subprocesses and disposable Git
repositories. Fixtures cover clean and bad input, unavailable prerequisites,
advisory findings, duplicate declarations, passive Git events, and bounded
execution. `tests/hooks/test_validation_acceptance.py` preserves the old AU
gitignore acceptance against the existing shared checker.

Tests use local source and installed dependencies. They do not install tools,
contact a remote, or claim that the historical AU pull trigger was reproduced.
Report executed tests separately from ordinary hooks and CI.
