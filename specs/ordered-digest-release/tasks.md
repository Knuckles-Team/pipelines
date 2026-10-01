# Tasks — PIPE-RELEASE-001

- [ ] Agree public candidate schema and integrity mechanism; document deployment-owner handoff fields.
- [ ] Implement strict candidate, digest, source, and dependency validation before publication effects.
- [ ] Add deterministic topological order, exact-revision qualification, and stage receipts using existing actions.
- [ ] Bind source verification and registry digests to builds; emit idempotent versioned handoff.
- [ ] Check declared consumer manifest references without editing those manifests.
- [ ] Add P-1–P-5 and N-1–N-6 fixture/workflow tests; run YAML, pytest, CCCC, jscpd, Dupehound, and KISS.
- [ ] Execute reviewed release, link hosted CI/digest receipts, obtain deployment evidence, update delivery and acceptance independently.

No task above cites a `requirements.md` ID by name. PIPE-RELEASE-R001 (dependency-ordered digest
publication) is closed by tasks 2-4 above (candidate validation, ordered publication, digest
handoff). PIPE-RELEASE-R002 (release tag matches the qualified commit) is closed by task 2 above
(candidate/source/digest validation) together with task 7 (release evidence linking the tag to its
commit).
- [ ] Quote and properly escape every environment value the release build job sources locally
      (including compiler flags such as CFLAGS) so a multi-token value is never misinterpreted as a
      shell command, and verify the build produces byte-identical, reproducible wheels. Closes
      PIPE-RELEASE-R003, which no functional requirement or existing task above covers.
