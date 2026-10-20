# Tasks — PIPE-GATES

- [x] Publish the machine-readable gate partition, the fast set and the full set, beside the gate standard and bind the workflow contracts to it. Closes PIPE-GATES-R001.
- [x] Add the partition test asserting exact membership and the complement. Closes PIPE-GATES-R001.
- [x] Implement the post-land decision policy: default auto-revert, the 300 s fix-forward task window, the one free rerun, and the replayable decision record. Closes PIPE-GATES-R002.
- [x] Add the policy test covering the default decision and each threshold. Closes PIPE-GATES-R002.
- [ ] Bind every blocking gate to the engine tree: reads by path and blob digest, no working copy, verdict equality against a materialized checkout. Closes PIPE-GATES-R003.
- [ ] Add the tree-based contract test on a fixture tree and an identical checkout. Closes PIPE-GATES-R003.
- [ ] Regenerate `status.json` with `pipelines-hook spec-status --write`; record executed evidence before advancing any row's state.
