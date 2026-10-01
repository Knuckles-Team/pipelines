# PIPE-IDENTITY-001 — Commit author identity governance

Status: SPECIFIED. Owner: `pipelines`. Source requirement: PIPE-IDENTITY-R001. Acceptance: NOT_AUDITED.
Every requirement ID this spec owns is defined in [requirements.md](requirements.md); delivery
state and evidence for each ID are recorded in [status.json](status.json).

## Purpose and user stories

A repository maintainer can restrict who is allowed to author or commit changes by configuring a
set of permitted name/email identities, so a misconfigured or unexpected local git identity never
reaches a shared branch unnoticed. A contributor sees the same rule enforced locally, before push,
and again in CI, so a bypassed or disabled local hook can never let a disallowed identity merge
silently.

## Functional requirements

- **FR-1 — Configured allowlist.** Read a versioned, schema-validated configuration of permitted
  author/committer identities (name and email pairs). Reject a malformed or empty configuration
  rather than silently allowing every identity. The configuration carries no secrets and no
  identity outside the declared set is implicitly trusted.
- **FR-2 — Commit-time enforcement.** At commit time, read the identity git itself resolved for the
  commit being made (author name/email and committer name/email) and reject the commit when either
  pair does not match an entry in the configured allowlist, naming which field failed.
- **FR-3 — Push-time enforcement.** Before a push leaves the local repository, re-check every commit
  in the outgoing range against the same configured allowlist, not only the branch tip, and refuse
  the push when any commit in that range fails. A locally disabled or skipped commit-time check
  never lets a disallowed identity reach the remote unexamined.
- **FR-4 — CI re-verification.** Re-run the identity check in CI against the full range introduced by
  a pull request or push, independent of whatever ran on the contributor's machine. CI enforcement
  does not trust a local pass as a substitute for its own verification.
- **FR-5 — Fail-closed diagnostics.** A missing or unreadable allowlist configuration is reported as
  "the check could not run" and blocks in CI; locally it is a visible skip naming the exact command
  that installs or points at the configuration, never a silent pass. No identity value outside the
  reported mismatch is used to broaden what is logged beyond what is needed to name the failing
  field.

## Acceptance scenarios

1. A commit whose author and committer both match an entry in the configured allowlist is accepted
   at commit time, at push time, and in CI.
2. A commit whose author or committer name/email pair matches no entry in the configured allowlist
   is rejected at commit time with the mismatched field named, without revealing other configured
   identities.
3. A commit that was made before the allowlist was enabled, or made with a bypassed local hook, is
   still rejected when it reaches the push-time check or CI, because both check the full outgoing or
   incoming commit range rather than only the branch tip.
4. A missing or malformed allowlist configuration blocks the check in CI (fails closed) and prints a
   local remedy instead of silently passing every identity.

## Interfaces and exclusions

The configuration is a versioned, bounded file naming permitted identities; its exact file location
and ownership (repository-local versus fleet-shared) is the open decision below. This spec governs
only author/committer name and email verification for commits reaching a shared branch; it does not
cover GPG/SSH commit signing, branch protection rules enforced by the hosting platform, or who is
authorized to approve a pull request. Those remain separate controls layered independently of this
check.

## Traceability

| Requirement | Design | Tests | Evidence |
|---|---|---|---|
| FR-1 | [Allowlist configuration](plan.md#allowlist-configuration) | P-1, N-1 | configuration schema check |
| FR-2 | [Commit-time check](plan.md#commit-time-check) | P-2, N-2 | rejected/accepted commit log |
| FR-3 | [Push-time check](plan.md#push-time-check) | P-3, N-3 | rejected push log |
| FR-4 | [CI re-verification](plan.md#ci-re-verification) | P-4, N-4 | CI run result |
| FR-5 | [Failure behavior](plan.md#failure-behavior) | N-5 | fail-closed CI run, local skip message |

## Open decision

Select where the configured allowlist is stored (repository-local versus a fleet-shared location
read the same way the existing tracked-content identity catalog is read) and who may change it,
before activation. Either choice must keep the configuration bounded, versioned, and free of
secrets, and must not let an unreadable configuration silently widen who is accepted.
