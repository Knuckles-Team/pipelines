# Tasks — PIPE-CONNSPEC

- [ ] Confirm the standard rows PIPE-CONNSPEC-R001 to PIPE-CONNSPEC-R005 against the core implementation.
- [ ] Roll out the four adoption steps to each connector repository, one pull request per connector per step, in the order of `plan.md`.
- [ ] Record each landed child in the generated status and confirm the connector's page publishes.

The per-connector children (PIPE-CONNSPEC-R101.1 and following) are the work order; they are not repeated here.

- [x] Limit new PIPE-CONNSPEC-R001 landing attribution to explicit declarations, with regression tests and preserved legacy receipt validation.

- [ ] PIPE-CONNSPEC-R006: preserve moved retired IDs using shared parsing; run positive and misleading-prose regressions.

- [x] Refuse spec-status generation with incomplete shallow history before any writes; verify legacy and current receipts survive a full-history fetch while reverted and unreachable receipts are rejected.

- [ ] **PIPE-CONNSPEC-R009:** Requirement state read from the engine (rollup).
- [ ] **PIPE-CONNSPEC-R009.1:** Wiring.
- [ ] **PIPE-CONNSPEC-R009.2:** Hot-path proof.

- [ ] PIPE-CONNSPEC-R011: support explicit retired standard-ID aliases with current-row validation, preserved historical evidence and unchanged unknown/unbound trailer refusal.

- [ ] **PIPE-CONNSPEC-R012:** Row-level Depends-on.
- [ ] **PIPE-CONNSPEC-R013:** Priority from competency questions.
- [ ] **PIPE-CONNSPEC-R014:** Generated priority, frontier, and unserved.
- [ ] **PIPE-CONNSPEC-R015:** Derived release bundles.
- [ ] **PIPE-CONNSPEC-R016:** Architecture page delivery views.
