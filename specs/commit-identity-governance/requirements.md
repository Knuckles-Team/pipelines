# PIPE-IDENTITY-001 requirements

Every requirement this specification owns, with the proof that closes it. Delivery state and
public evidence for each ID are recorded in [`status.json`](status.json); this file defines what
each ID means. The design is in [`spec.md`](spec.md) and [`plan.md`](plan.md), the test contract
in [`test-spec.md`](test-spec.md), and the work order in [`tasks.md`](tasks.md).

| ID | Requirement | Verification |
|---|---|---|
| `PIPE-IDENTITY-R001` | **Commit author identity is restricted to an allowlist.** pipelines enforces an author-identity allowlist in its pre-commit, pre-push, and CI checks, rejecting any commit whose author or committer name and email pair does not match one of a configured set of permitted identities. | Verified by a negative test that a commit with an identity outside the configured allowlist is rejected by the hook and by the CI check. |
