# Pipelines specification constitution

Status: PROPOSED. Version: 0.1.0. Index: [specs/README.md](../../specs/README.md).

1. **One owner, live wiring.** Extend the reusable workflows, theme sync, readiness, and contract tests. Calling repositories own content and deployment manifests. No second policy authority or disconnected implementation.
2. **Complete public contract.** Each feature identifies outcomes and failure behavior, architecture and interfaces, positive and negative tests, tasks, and owner boundaries in tracked files. Private drafts and local environments are never contributor prerequisites.
3. **Portable evidence.** Inputs are public repository references and published artifacts. A source receipt states exact commits and trees. A release receipt states image digests, consumer references, and observed result. Missing evidence is not success.
4. **Quality and simplicity.** Apply configured CCCC, jscpd, Dupehound, KISS, workflow contract tests, and YAML checks to implementation changes. Reuse existing wiring. Documentation-only contributions do not require live services or unrelated documentation gates.
5. **Separate delivery and acceptance.** `LANDED` requires a merged revision. `ACCEPTED` requires test and consumer/release receipts. Amend this constitution through a reviewed change with impact stated.
