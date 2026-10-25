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

Meristem's initial adoption removes its copied gitignore checker. The shared gate
retains its required patterns and tracked build-output checks, and additionally
checks nested caches. Meristem moves its existing hand-authored KISS configuration to
the canonical `.config/kiss.toml` without changing its thresholds. The consumer
records the replaced hook ID and retained acceptance in its policy and spec.

### 2026-10-17: Approved privacy provenance boundary

The privacy gate separates Git display names from strict local identifiers.
Only a display name with no independent strict source uses contextual matching.
Context includes author/account fields, explicit authored-by statements and parenthesized role labels.
Other identity sources and the prohibited catalog retain unconditional matching.
This permits product references without a product allowlist.
A bare personal name outside attribution can pass when only Git supplied that name.
The user approved this tradeoff before implementation.
