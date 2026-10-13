# Shared validation design

One CLI command loads a strict TOML policy, validates prerequisites, then runs
each unique published gate once in an isolated subprocess. Version 1 admits
only root-hygiene, gitignore-convergence, and sprawl. These gates read local
source and Git state. They have no dependency installation or network step.

The runner uses its existing Python environment. It refuses unavailable Git
or process-group support. Each child has a deadline within the remaining run
budget. On timeout or interruption, the runner terminates its process group.
Evidence goes into a fresh private directory, outside the checkout by default.

Required outcomes determine the exit code: 2 for unavailable or timed out, 1
for findings, and 0 for completed clean checks. Advisory findings remain in
the report and summary. A passive Git event is reported as inactive, not as a
validation pass. Dry-run reports the validated plan without running gates.

No Git hooks are installed by this command. The published hook has explicit
commit, push, and manual stages; consumers keep their reviewed stage policy.
No post-merge, post-checkout, or post-rewrite validation is registered.

AU's initial adoption removes its copied gitignore checker. The shared gate
retains its required patterns and tracked build-output checks, and additionally
checks nested caches. AU moves its existing hand-authored KISS configuration to
the canonical `.config/kiss.toml` without changing its thresholds. The consumer
records the replaced hook ID and retained acceptance in its policy and spec.
