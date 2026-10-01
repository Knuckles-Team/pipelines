# Architecture — PIPE-IDENTITY-001

## Existing wiring

`pipelines_hooks/cli.py` is the single entry point: `pipelines-hook <gate>` resolves `gate` through
the `GATES` dict to a module exposing `main(argv) -> int`, and `run_gate` maps a missing
prerequisite (`Unavailable`) to a fail-closed exit in CI or a visible local skip, and any other
unrunnable state (`CannotRun`) to exit 2. `.pre-commit-hooks.yaml` declares the hook IDs this
repository exports to every consumer; `.config/pre-commit.yaml` is how `pipelines` runs those same
IDs on itself, with `default_install_hook_types: [pre-commit, pre-push]` and per-hook `stages:` lists
choosing which installed hook type(s) a gate runs under. `.github/workflows/ci.yml` runs the
commit-stage hooks with `pre-commit run --all-files`, then re-runs the `pre-push` and `manual` stage
hooks with `--hook-stage manual`, so CI independently repeats whatever stage a contributor's local
hook might have skipped or bypassed. `pipelines_hooks/privacy/identity_catalog.py` and
`pipelines_hooks/privacy/gate.py` are the closest existing precedent for this shape: a bounded,
versioned external JSON file of identity strings, loaded by a dedicated loader that raises on a
malformed or oversized file, consumed by a gate that fails closed in CI and skips with a remedy
locally. `pipelines_hooks/core/gitenv.py` provides `run_git`/`git_text` with every ambient `GIT_*`
environment variable stripped, so a gate reads the repository git itself resolved rather than an
inherited selector. Build a new, dedicated gate on these seams; do not extend the unrelated
tracked-content privacy scanner, whose job is finding identity strings leaked into file bodies, not
verifying the identity a commit was made under.

## Allowlist configuration

Define a bounded, versioned configuration format naming permitted identities as explicit
`{name, email}` pairs (no wildcards, no regular expressions), modeled on the
`{"version": ..., "identities": [...]}` shape `identity_catalog.py` already validates: a strict
schema check, a size ceiling, and a hard rejection of anything malformed rather than a narrowed
scan. Resolve the configuration path through `pipelines_hooks/core/settings.py`'s single
environment-reading module, so the path a gate reads is visible alongside every other declared
setting, and support a fleet-shared default location of the same kind `tracked-privacy` already
resolves its catalog from. A repository may instead keep a repository-local configuration file
tracked in its own tree; the choice is the open decision in `spec.md` and does not change the
validation or enforcement logic.

## Commit-time check

Add a `commit-identity` gate module beside the existing `pipelines_hooks/privacy` and
`pipelines_hooks/security` packages, registered in `cli.py`'s `GATES` dict and declared in
`.pre-commit-hooks.yaml` at the default (`pre-commit`) stage, matching how `tracked-privacy` is
wired. Resolve the identity git itself assigned to the commit being made, not an ambient
environment variable, using `run_git`/`git_text` so the ambient-selector class of bug `gitenv.py`
already guards against cannot recur here. Compare the resolved author and committer name/email
pairs against the loaded allowlist and reject with the specific failing field named, never with the
full configured allowlist printed back.

## Push-time check

Register the same gate module under a `stages: [pre-push, manual]` entry (the pattern the existing
`*-census` hooks already use in `.config/pre-commit.yaml`) so pre-push re-walks every commit in the
range about to leave the local repository — not only the tip — through the identical allowlist
check. A commit made with a bypassed or skipped commit-time hook is still caught here, because the
push-time stage inspects the full outgoing range independently.

## CI re-verification

No separate implementation: `.github/workflows/ci.yml` already runs the commit-stage hooks across
the whole checkout and then re-runs the `pre-push`/`manual` stage hooks with
`pre-commit run --hook-stage manual`. Registering `commit-identity` at both stages is sufficient for
CI to independently repeat the same check against the full incoming range, exactly as it already
does for every other gate in this repository.

## Failure behavior

Follow the existing `Unavailable`/`CannotRun` contract: a missing or unreadable allowlist
configuration raises `Unavailable` with a remedy naming the install/config command, which `cli.py`
turns into a fail-closed exit 2 in CI and a printed local skip otherwise; a malformed configuration
(bad schema, oversized file) raises `CannotRun`, which is always exit 2, since that is a defect in
the input rather than an absent optional prerequisite. Reuse `pipelines_hooks/core/settings.py`'s
`KNOWN_SETTINGS` registration for any new environment variable this gate reads, so the env-sprawl
gate continues to hold.

## Quality and release gates

Apply the repository's own configured gates to the new module and its `.pre-commit-hooks.yaml`/
`.config/pre-commit.yaml` entries: `complexity-staged`/`complexity-census` (CCCC 10/15),
`kiss-staged`/`kiss-census`, `dupehound-changed`, `jscpd-differential`/`jscpd-census`,
`tracked-privacy`, `supply-chain`, and the repository's `pytest` suite. Reuse `gitenv.py` and
`core/errors.py` rather than re-implementing git access or exit-code mapping.
