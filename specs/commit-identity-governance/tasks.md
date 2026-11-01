# Tasks — PIPE-IDENTITY

- [x] T001 [US1] PIPE-IDENTITY-R001.2 Load, validate and resolve the bounded allowlist, with the packaged fleet default.
- [x] T002 [US1] PIPE-IDENTITY-R001.3 Reject a pending commit whose author or committer is off the allowlist, naming only the field.
- [x] T003 [US1] PIPE-IDENTITY-R001.4 Re-check the whole outgoing or incoming range, and exempt only a fork pull request.
- [x] T004 [US1] PIPE-IDENTITY-R001.5 Fail closed for a missing or malformed allowlist: exit 2 in CI, a visible skip locally.
- [x] T005 [US1] PIPE-IDENTITY-R001.6 Register both gates in `GATES` and run them in the `secrets` group.
- [x] T006 [US1] PIPE-IDENTITY-R001.7 Prove the published command rejects an off-list identity and accepts a clean range.
- [ ] T007 [US2] PIPE-IDENTITY-R001.1 Add the service-identity tests that show the platform identity gets no exemption.
