# PIPE-VALIDATION requirements

| ID | Requirement | Acceptance |
|---|---|---|
| `PIPE-VALIDATION-R001` | **Bounded shared repository validation.** The validation package runs declared offline checks with structured required and advisory outcomes. | The child requirements below cover the command. |
| `PIPE-VALIDATION-R001.1` | **Strict policy.** `validation/policy.py` rejects unknown keys, duplicate IDs or gates, unsupported gates, missing acceptance mappings, and invalid deadlines before dispatch. | `test_policy_refuses_ambiguous_checks` and `test_policy_accepts_repository_group`. |
| `PIPE-VALIDATION-R001.2` | **Passive events do no work.** `validation/cli.py` returns an explicit inactive result for post-merge, post-checkout, and post-rewrite without loading policy or dispatching checks. | `test_passive_git_event_does_not_dispatch` uses disposable Git repositories and sentinel tools. |
| `PIPE-VALIDATION-R001.3` | **Required checks fail closed.** `validation/runner.py` reports missing prerequisites separately; required failures, unavailable results, and timeouts block. Advisory outcomes remain visible. | `test_required_and_advisory_outcomes` and `test_missing_git_is_unavailable`. |
| `PIPE-VALIDATION-R001.4` | **Bounded execution.** `validation/runner.py` enforces check and run deadlines, terminates its process group, and records measured duration. | `test_deadline_terminates_child_process` and `test_run_budget_marks_remaining_checks`. |
| `PIPE-VALIDATION-R001.5` | **Actionable evidence.** `validation/cli.py` prints grouped concise results and writes a versioned report with check logs, remedies, acceptance IDs, and elapsed time. | `test_summary_matches_evidence` verifies both clean and failed runs. |
| `PIPE-VALIDATION-R001.6` | **Retain AU ignore acceptance.** The shared gitignore checker retains all 16 AU patterns and rejects tracked build, dist, and target families without confusing ordinary source filenames. | `test_au_ignore_acceptance_is_retained` runs real disposable Git fixtures. |
