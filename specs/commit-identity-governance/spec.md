# PIPE-IDENTITY — Commit author identity governance

Owner: pipelines. Cross-repo IDs: `MEDULLA-SDLC-R019.10`, `ARBORA-OPS-R896.10`.
Public provenance: the [spec standard](../../reference/spec-standard.md) and the [gate standard](../../reference/gate-standard.md).

## Delivery mapping

Component: Commit identity

Depends-on: PIPE-GATES-R016.116.2

Code: ../../pipelines_hooks/identity/allowlist.py ../../pipelines_hooks/identity/commit_gate.py ../../pipelines_hooks/identity/range_gate.py ../../pipelines_hooks/identity/resolve.py ../../pipelines_hooks/identity/fork_exemption.py

## User Scenarios & Testing

### User Story 1 - Only permitted identities reach a shared branch (Priority: P1)

A repository maintainer configures the set of permitted author and committer identities. A contributor sees the same rule locally before the commit, before the push, and again in CI. A bypassed or disabled local hook never lets an unexpected identity merge silently.

**Acceptance Scenarios**:

1. **Given** a commit whose author and committer both match an allowlist entry, **When** the commit-time check, the push-time check and the CI check run, **Then** each accepts it.
2. **Given** a commit whose author or committer matches no allowlist entry, **When** the commit-time check runs, **Then** it rejects the commit, names the mismatched field and reveals no other configured identity.
3. **Given** a commit made with a bypassed local hook, **When** the push-time or CI check inspects the full range, **Then** it rejects the range even when the branch tip matches.
4. **Given** a malformed allowlist, **When** the check runs in CI, **Then** it fails closed with `CANNOT RUN`, and locally it prints the remedy and never passes every identity.

### User Story 2 - The delivery platform has an identity but no exemption (Priority: P2)

The owner runs the autonomous delivery platform under either the owner's account or a dedicated service account. Whichever identity the platform uses, the owner's approval on the head commit gates every merge, and no gate is relaxed for that identity.

**Acceptance Scenarios**:

1. **Given** a service account listed in the allowlist, **When** the platform pushes a range under that account, **Then** the identity check accepts it as it accepts any listed identity.
2. **Given** a service account absent from the allowlist, **When** the platform pushes a range under that account, **Then** the CI check rejects the range.

### Edge Cases

- A pull request from a fork is an external contribution and is exempt from the allowlist; a push, a same-repository pull request and a local run are checked.
- An unreadable or missing event payload counts as not a fork, never as exempt.
- An empty commit range passes with a count of zero.
- With nothing staged, the commit-time check passes.
- An explicit allowlist path that does not exist is `Unavailable`; a present but malformed file is `CannotRun`.

## Requirements

- **FR-001**: Read a versioned, bounded, schema-validated allowlist of `{name, email}` pairs and reject a malformed or empty file. Rows: `PIPE-IDENTITY-R001.2`.
- **FR-002**: At commit time, reject a commit whose author or committer pair is off the allowlist and name the failing field. Rows: `PIPE-IDENTITY-R001.3`.
- **FR-003**: Re-check every commit of the outgoing range before a push, and again in CI, and exempt only a fork pull request. Rows: `PIPE-IDENTITY-R001.4`.
- **FR-004**: Fail closed when the allowlist is missing or malformed: exit 2 in CI, a visible skip with the remedy locally. Rows: `PIPE-IDENTITY-R001.5`.
- **FR-005**: Publish both gates in the `secrets` group and prove the published command end to end. Rows: `PIPE-IDENTITY-R001.6`, `PIPE-IDENTITY-R001.7`.
- **FR-006**: Let the delivery platform act under one configured allowlist identity, the owner's account or a service account, with no exemption from any gate and with the owner's approval gating every merge. Rows: `PIPE-IDENTITY-R001.1`.

## Success Criteria

- **SC-001**: A commit with an off-list identity is rejected at commit time, at push time and in CI. Rows: `PIPE-IDENTITY-R001.3`, `PIPE-IDENTITY-R001.4`.
- **SC-002**: The rejection output names one field and no other configured identity. Rows: `PIPE-IDENTITY-R001.3`.
- **SC-003**: Changing the platform identity changes one allowlist entry and no code. Rows: `PIPE-IDENTITY-R001.1`.

## Assumptions

- The packaged fleet default names the sanctioned fleet identities, and a repository-local file or a path named by `COMMIT_IDENTITY_ALLOWLIST` takes precedence when present.
- The owner's approval on the head commit is enforced by the owners of `ARBORA-OPS-R896.10` and `MEDULLA-SDLC-R019.10`; this spec states only that the identity check grants no bypass.
- Contributions from outside the organization arrive as fork pull requests and are exempt by design.

## Why a new spec

The search covered `specs/gates` and the `secrets` group rows. `PIPE-GATES-R047` and `PIPE-GATES-R048` govern merge and ruleset policy, and `PIPE-GATES-R016.116` governs the single required check. None of them states who may author or commit, so this spec owns that capability alone.

## Scope and interfaces

The allowlist is a versioned, bounded file of permitted identities. One fleet default ships inside the hook package, so every consumer is covered without installing a file of its own. A repository may override it with a tracked file, or point at a shared path through `COMMIT_IDENTITY_ALLOWLIST`, as described in [plan.md](plan.md#allowlist-configuration). This spec governs only author and committer name and email verification for commits that reach a shared branch. Non-goals: GPG and SSH commit signing, branch protection rules enforced by the hosting platform, and who may approve a pull request. Those stay separate controls layered independently of this check.

## Traceability

| Label | Rows | Design section | Test ID | Evidence |
|---|---|---|---|---|
| FR-001 | `PIPE-IDENTITY-R001.2` | [Allowlist configuration](plan.md#allowlist-configuration) | P-1, N-1 | configuration schema check |
| FR-002 | `PIPE-IDENTITY-R001.3` | [Commit-time check](plan.md#commit-time-check) | P-2, N-2 | rejected and accepted commit log |
| FR-003 | `PIPE-IDENTITY-R001.4` | [Push-time and CI checks](plan.md#push-time-and-ci-checks) | P-3, N-3, P-4, N-4 | rejected push log, CI run result |
| FR-004 | `PIPE-IDENTITY-R001.5` | [Failure behavior](plan.md#failure-behavior) | N-5 | fail-closed CI run, local skip message |
| FR-005 | `PIPE-IDENTITY-R001.6`, `PIPE-IDENTITY-R001.7` | [Commit-time check](plan.md#commit-time-check) | P-5 | published command exit codes |
| FR-006 | `PIPE-IDENTITY-R001.1` | [Platform identity](plan.md#platform-identity) | P-6, N-6 | range check over a service identity |

Requirement IDs are defined in [requirements.md](requirements.md).
