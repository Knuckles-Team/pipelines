# PIPE-VALIDATION — Implementation plan

Governing spec: [spec.md](spec.md). Rows: [requirements.md](requirements.md).

## Summary

This plan serves the rows of `PIPE-VALIDATION`. The command `pipelines-hook validate` loads a strict policy, runs each declared published gate once in an isolated subprocess and writes a bounded report. The connector standard rows reuse the same hook table. The privacy provenance row refines one gate.

## Technical Context

- **Language/Version**: Python 3.14 (floor 3.12)
- **Primary Dependencies**: The `pipelines_hooks` package, git and the standard library.
- **Storage**: N/A. Evidence goes to a private directory outside the checkout by default.
- **Testing**: pytest under `tests/hooks/` with disposable Git repositories and real subprocesses.
- **Target Platform**: Linux CI runners and developer machines with process-group support
- **Project Type**: Library and command-line hooks
- **Performance Goals**: Each check and the whole run have deadlines declared in the policy; the runner measures and records the duration.
- **Constraints**: No dependency installation, no network step, no Git hook installed by the command.
- **Scale/Scope**: The rows of requirements.md.

## Constitution Check

- **I. One owner per concept**: No departure is recorded in this plan; the rows carry the proof.
- **II. Extend before you create**: No departure is recorded in this plan; the rows carry the proof.
- **III. Specs describe the current state only**: No departure is recorded in this plan; the rows carry the proof.
- **IV. Requirements are neutral and controlled**: No departure is recorded in this plan; the rows carry the proof.
- **V. Hard cutover, no legacy path**: No departure is recorded in this plan; the rows carry the proof.
- **VI. Names carry no version suffix**: No departure is recorded in this plan; the rows carry the proof.
- **VII. One engine, no second database, no sync**: No departure is recorded in this plan; the rows carry the proof.
- **VIII. Ask the graph, not a bespoke operation**: No departure is recorded in this plan; the rows carry the proof.
- **IX. Connectors depend on the SDK and are called through arbora**: No departure is recorded in this plan; the rows carry the proof.
- **X. Every ontology class rolls up to the core**: No departure is recorded in this plan; the rows carry the proof.
- **XI. Code stays small, simple and unduplicated**: No departure is recorded in this plan; the rows carry the proof.
- **XII. No ratchets and no suppressions**: No departure is recorded in this plan; the rows carry the proof.
- **XIII. Zero flakes**: No departure is recorded in this plan; the rows carry the proof.
- **XIV. Compile first, then review**: No departure is recorded in this plan; the rows carry the proof.
- **XV. Python 3.14 standard, 3.12 floor**: No departure is recorded in this plan; the rows carry the proof.
- **XVI. Install and deploy only from published releases**: No departure is recorded in this plan; the rows carry the proof.
- **XVII. Publish the gate's tool before the gate**: No departure is recorded in this plan; the rows carry the proof.
- **XVIII. Landed means reachable**: No departure is recorded in this plan; the rows carry the proof.
- **XIX. A tag push publishes, with no manual approval**: No departure is recorded in this plan; the rows carry the proof.
- **XX. Secrets are never traced or logged**: No departure is recorded in this plan; the rows carry the proof.
- **XXI. Public files stay portable and neutral**: No departure is recorded in this plan; the rows carry the proof.

## Project Structure

```text
pipelines_hooks/validation/policy.py   existing: strict policy loader
pipelines_hooks/validation/runner.py   existing: bounded runner
pipelines_hooks/validation/cli.py      existing: command and report
pipelines_hooks/connector/             existing: connector-standard members
templates/connector/pre-commit-config.yaml  existing: reference connector configuration
tests/hooks/test_validation*.py        existing: validation tests
```

## Phase 0: Research

No unknowns; no research.md.

## Phase 1: Design

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

### Approved privacy provenance boundary (PIPE-VALIDATION-R002)

The privacy gate separates Git display names from strict local identifiers.
Only a display name with no independent strict source uses contextual matching.
Context includes author/account fields, explicit authored-by statements and parenthesized role labels.
Other identity sources and the prohibited catalog retain unconditional matching.
This permits product references without a product allowlist.
A bare personal name outside attribution can pass when only Git supplied that name.
The user approved this tradeoff before implementation.

## Phase 2: Task approach

tasks.md carries one numbered task line for each child row. The strict policy comes first, then the runner and the report, then the connector standard rows and the privacy row. No task runs in parallel.

## Complexity Tracking

none

## Build contract

Each row names its test. The repository pre-commit and pre-push hooks and the pull request gates apply: `complexity-staged` and `complexity-census` (cyclomatic 10, cognitive 15), `kiss-staged`, `dupehound-changed`, `jscpd-differential` and the pytest suite. No row uses a suppression or a ratchet.

## Production caller chain

- Validation: the `validate` hook (`.config/pre-commit.yaml:134`) runs `main` in `pipelines_hooks/validation/cli.py:39`, which calls `load` (`pipelines_hooks/validation/policy.py:71`) and then `run` (`pipelines_hooks/validation/runner.py:97`).
- Connector standard: the `connector-standard` hook runs `main` in `pipelines_hooks/connector/standard.py:12`, which runs each member in `MEMBERS`.
- Privacy provenance: the `secrets` hook runs `tracked-privacy`, whose `main` is `pipelines_hooks/privacy/gate.py:95`.

## Cross-repo seams

none
