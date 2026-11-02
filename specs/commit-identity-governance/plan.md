# PIPE-IDENTITY — Implementation plan

Governing spec: [spec.md](spec.md). Rows: [requirements.md](requirements.md).

## Summary

This plan serves the rows of `PIPE-IDENTITY`. Two gates, `commit-identity` and `commit-identity-range`, compare the author and committer of a commit, or of every commit in a range, with a configured allowlist. Both gates run in the `secrets` group at commit and push time and in CI. The delivery platform acts under one allowlist entry, either the owner's account or a service account, and the gates give that entry no exemption. The design reuses the bounded loader pattern of the identity catalog under `pipelines_hooks/privacy/` and the sanitized git helpers of `pipelines_hooks/core/gitenv.py`.

## Technical Context

- **Language/Version**: Python 3.14 (floor 3.12)
- **Primary Dependencies**: The `pipelines_hooks` package and git; no network access.
- **Storage**: N/A. The allowlist is a JSON file: packaged default, tracked file or env-named path.
- **Testing**: pytest under `tests/hooks/` with disposable fixture git repositories and synthetic `*.invalid` identities.
- **Target Platform**: Developer machines and Linux CI runners
- **Project Type**: Library and command-line hooks
- **Performance Goals**: N/A. The commit check adds one `git var` call and the range check adds one `git log` call.
- **Constraints**: The gates print only the failing field. No ambient `GIT_*` selector decides which repository is read. An absent or malformed allowlist never passes.
- **Scale/Scope**: The seven child rows of `PIPE-IDENTITY-R001`.

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
pipelines_hooks/identity/allowlist.py              existing: load, validate, resolve the allowlist
pipelines_hooks/identity/fleet-default-allowlist.json  existing: packaged fleet default
pipelines_hooks/identity/resolve.py                existing: pending and range identities
pipelines_hooks/identity/commit_gate.py            existing: commit-identity
pipelines_hooks/identity/range_gate.py             existing: commit-identity-range
pipelines_hooks/identity/fork_exemption.py         existing: fork pull request exemption
pipelines_hooks/cli.py                             existing: GATES table and the secrets group
tests/hooks/test_identity_range.py                 existing: two tests added for PIPE-IDENTITY-R001.1
```

## Phase 0: Research

No unknowns; no research.md.

## Phase 1: Design

### Existing wiring

`pipelines_hooks/cli.py` is the single entry point. `pipelines-hook <gate>` resolves the gate through the `GATES` table to a module with `main(argv) -> int`. The `secrets` group in `GROUPS` runs `commit-identity` and `commit-identity-range` with the other secret checks. `run_gate` maps a missing prerequisite (`Unavailable`) to a fail-closed exit 2 in CI or a visible local skip, and any other unrunnable state (`CannotRun`) to exit 2. `.config/pre-commit.yaml` runs the `secrets` hook at the commit and push stages of this repository, and consumers get the same ids through `.pre-commit-hooks.yaml`. The range member runs only when `PRE_COMMIT_FROM_REF` is set, which the gates workflow exports for a pull request. `pipelines_hooks/privacy/identity_catalog.py` is the precedent for a bounded, versioned identity file with a strict loader. `pipelines_hooks/core/gitenv.py` strips every ambient `GIT_*` variable, so a gate reads the repository git itself resolved. The tracked-content privacy scanner is not extended: it finds identity strings in file bodies, not the identity a commit was made under.

### Allowlist configuration

The file is `{"version": ..., "identities": [...]}` with explicit `{name, email}` pairs. It has a strict schema check, a size ceiling and a hard rejection of anything malformed. `pipelines_hooks/identity/allowlist.py` resolves the path in this order: the `--allowlist` argument, then `COMMIT_IDENTITY_ALLOWLIST`, then a tracked `<root>/.config/commit-identity-allowlist.json`, then the fleet default packaged as `pipelines_hooks/identity/fleet-default-allowlist.json` and declared in `[tool.setuptools.package-data]`. The packaged default names the sanctioned fleet identities. Outside contributors are not listed; their fork pull requests are exempt instead. The environment read goes through `pipelines_hooks/core/settings.py`. An explicit path that does not exist raises `Unavailable`; a present but malformed file raises `CannotRun`.

### Commit-time check

`commit_gate.main` reads the identity git assigned to the commit being made with `pending_identity`, compares author and committer with `matches`, and prints only the failing field. With nothing staged it passes.

### Push-time and CI checks

`range_gate.main` checks `is_fork_pull_request` first. A pull request whose head repository differs from its base repository is exempt, and the gate returns before it loads the allowlist. A push, a same-repository pull request, a local run or an unreadable event payload is checked. The gate lists every commit of the range with `range_identities` and compares each author and committer. The CI run repeats this over the incoming range, so a skipped local hook never lets an off-list identity through.

### Platform identity

The delivery platform commits under one allowlist entry: the owner's account or a service account. Choosing between them edits the allowlist file and no code. `matches` compares name and email exactly and treats every entry alike, and neither gate branches on which entry matched. The owner's approval on the head commit gates every merge and is enforced by the owners of `ARBORA-OPS-R896.10`; this plan adds no approval logic. Every gate stays required, which `PIPE-GATES-R016.116.2` proves for the CI workflows.

### Failure behavior

A missing explicit allowlist raises `Unavailable` with a remedy, which `cli.py` turns into exit 2 in CI and a printed skip locally. A malformed file raises `CannotRun` and always exits 2, because the input is defective. A new environment variable is registered in `KNOWN_SETTINGS` so the environment-sprawl gate holds.

## Phase 2: Task approach

tasks.md carries one numbered task line for each child row. The allowlist task comes first, then the commit-time check, the range check, the failure behavior, the wiring and the hot-path proof. The platform identity task comes last because it adds tests only. No task runs in parallel.

## Complexity Tracking

none

## Build contract

Each row names its test. The pre-commit and pre-push hooks and the pull request gates of this repository apply: `complexity-staged` and `complexity-census` (cyclomatic 10, cognitive 15), `kiss-staged` and `kiss-census`, `dupehound-changed`, `jscpd-differential`, `tracked-privacy`, `supply-chain` and the pytest suite. No row uses a suppression or a ratchet. Reuse `gitenv.py` and `core/errors.py` instead of new git access or exit-code mapping.

## Production caller chain

- Commit time: the `secrets` hook (`.config/pre-commit.yaml:53`) runs `run_group` (`pipelines_hooks/cli.py:121`), then `commit_gate.main` (`pipelines_hooks/identity/commit_gate.py:31`), then `resolved_allowlist` (`pipelines_hooks/identity/allowlist.py:101`).
- Push time and CI: the same group runs `range_gate.main` (`pipelines_hooks/identity/range_gate.py:37`) when `PRE_COMMIT_FROM_REF` is set, then `range_identities` (`pipelines_hooks/identity/resolve.py:45`).
- Platform identity: an allowlist entry read by `configured_path` (`pipelines_hooks/identity/allowlist.py:86`); no obsolete path remains to delete.

## Cross-repo seams

- `ARBORA-OPS-R896.10` binds the owner approval receipt to the head commit; this spec gives the platform identity no way around it.
