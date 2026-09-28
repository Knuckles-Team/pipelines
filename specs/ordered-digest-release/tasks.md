# Tasks — PIPE-EH-247

1. Agree public candidate schema and integrity mechanism; document deployment-owner handoff fields.
2. Implement strict candidate, digest, source, and dependency validation before publication effects.
3. Add deterministic topological order, exact-revision qualification, and stage receipts using existing actions.
4. Bind source verification and registry digests to builds; emit idempotent versioned handoff.
5. Check declared consumer manifest references without editing those manifests.
6. Add P-1–P-5 and N-1–N-6 fixture/workflow tests; run YAML, pytest, CCCC, jscpd, Dupehound, and KISS.
7. Execute reviewed release, link hosted CI/digest receipts, obtain deployment evidence, update delivery and acceptance independently.
