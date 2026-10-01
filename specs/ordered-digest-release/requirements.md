# PIPE-RELEASE-001 requirements

Every requirement this specification owns, with the proof that closes it. Delivery state and
public evidence for each ID are recorded in [`status.json`](status.json); this file defines what
each ID means. The design is in [`spec.md`](spec.md) and [`plan.md`](plan.md), the test contract
in [`test-spec.md`](test-spec.md), and the work order in [`tasks.md`](tasks.md).

| ID | Requirement | Verification |
|---|---|---|
| `PIPE-RELEASE-R001` | **Pipelines publishes images in dependency order with digest pins.** pipelines builds each repository's container image with an immutable digest pin, pushes repositories to GitHub in dependency order, and awaits hosted CI on each pushed revision before publishing the next stage, stopping before any downstream publication on failure. | Verified by an integration test with three ordered candidates confirming each stage's hosted CI must pass before the next stage publishes, per FR-3. |
| `PIPE-RELEASE-R002` | **Release tags point to the exact qualified commit.** pipelines verifies that a published GitHub release tag points to the exact source commit recorded in the qualified candidate manifest, rejecting any mismatch between the tag, the commit, and the published package artifact. | Verified by a negative test that a tag or artifact whose commit does not match the candidate manifest's recorded commit is rejected, per FR-1. |
| `PIPE-RELEASE-R003` | **Release build job sources environment values safely.** The release workflow's local build job writes and sources environment variables, including compiler flags such as CFLAGS, in a properly quoted form so a multi-token value is never misinterpreted as a shell command, and the build verifies byte-identical, reproducible wheels as part of its checks. | Verified by a build run whose steps complete via the real product build path rather than aborting early from an environment-sourcing error, and whose reproducibility check confirms byte-identical wheels across independent builds. |
