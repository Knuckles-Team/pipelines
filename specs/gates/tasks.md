# Tasks — PIPE-GATES

- [x] Publish the machine-readable gate partition, the fast set and the full set, beside the gate standard and bind the workflow contracts to it. Closes PIPE-GATES-R001.
- [x] Add the partition test asserting exact membership and the complement. Closes PIPE-GATES-R001.
- [x] Implement the post-land decision policy: default auto-revert, the 300 s fix-forward task window, the infrastructure-only re-run, and the replayable decision record. Closes PIPE-GATES-R002.
- [x] Add the policy test covering the default decision and each threshold. Closes PIPE-GATES-R002.
- [ ] Bind every blocking gate to the engine tree: reads by path and blob digest, no working copy, verdict equality against a materialized checkout. Closes PIPE-GATES-R003.
- [ ] Add the tree-based contract test on a fixture tree and an identical checkout. Closes PIPE-GATES-R003.
- [x] Regenerate `status.json` with `pipelines-hook spec-status --write`; record executed evidence before advancing any row's state.

- [ ] **PIPE-GATES-R004:** Gate verdicts publish to the engine (rollup).
- [ ] **PIPE-GATES-R004.1:** Wiring.
- [ ] **PIPE-GATES-R004.2:** Hot-path proof.
## Migration waves and the product-name check (R005, R006)

- [ ] **PIPE-GATES-R006:** Changeset migration waves with entry and exit criteria (rollup).
- [ ] **PIPE-GATES-R006.1:** Wave 1: webarchiver.
- [ ] **PIPE-GATES-R006.2:** Wave 2: small connectors.
- [ ] **PIPE-GATES-R006.3:** Wave 3: the remaining connectors.
- [ ] **PIPE-GATES-R006.4:** Wave 4: skills, pipelines and the user interfaces.
- [ ] **PIPE-GATES-R006.5:** Wave 5: the Scion SDK and the harness.
- [ ] **PIPE-GATES-R006.6:** Wave 6: arbora.
- [ ] **PIPE-GATES-R006.7:** Wave 7: Medulla, last.
- [x] **PIPE-GATES-R005:** Spec text names no third-party product.
- [x] Publish the canonical no-legacy-concepts migration gate and retain original detection, scope, historical exclusions, diagnostics and failure semantics. Closes PIPE-GATES-R007.
- [x] Bind PIPE-GATES-R007 to real Git fixtures covering tracked/ignored source, foreign worktrees, ambient Git selectors and nonzero CLI exits.
- [x] Publish the optional lock artifact mirror checker with compatible version and dependency checks. Closes PIPE-GATES-R008.
- [x] Publish the configurable tracked static import checker without adapter exemptions. Closes PIPE-GATES-R009.
- [x] Publish the `connector-name` gate for declared connector fleet names. Closes PIPE-GATES-R010.
- [x] Key the hook cache on pipelines main and skip symlinks in clone snapshots. Closes PIPE-GATES-R011.
- [x] Publish the `connector-graphql` gate, warning by default, for GraphQL declared via the Scion SDK extra. Closes PIPE-GATES-R012.
- [x] Publish the `sdk-conformance` gate, warning by default, for connectors that reimplement a Scion SDK capability. Closes PIPE-GATES-R013.
- [x] Publish the `connector-surface-audit` report of the five connector surfaces and the parent-ontology link. Closes PIPE-GATES-R014.
- [x] Publish the `connector-ontology-map` tool that proposes, reviews and applies parent classes for orphan connector classes. Closes PIPE-GATES-R015.
- [x] Add the `graph-check` subcommand to `connector-ontology-map`: whole-ecosystem ontology reachability, bridging, broken and missing edges, virtual-graph checks and competency questions. Closes PIPE-GATES-R016.
