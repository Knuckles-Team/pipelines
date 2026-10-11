# PIPE-IDENTITY requirements

| ID | Requirement | Verification |
|---|---|---|
| `PIPE-IDENTITY-R001` | **Commit author identity is restricted to an allowlist.** pipelines enforces an author-identity allowlist in its pre-commit, pre-push, and CI checks, rejecting any commit whose author or committer name and email pair does not match one of a configured set of permitted identities. | Verified by a negative test that a commit with an identity outside the configured allowlist is rejected by the hook and by the CI check. |
