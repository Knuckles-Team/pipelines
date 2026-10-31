# Pipelines constitution

This repository owns the shared gates, pages, release rules and the spec standard.

## Organization standards

- [Spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): one owning spec per capability, computed states, `Spec:` trailers.
- [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md): which repository owns which requirement.
- [Wording standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ste.md): sentences of 20 words or fewer, with `must`, `should`, or `may`.

## Rules of this repository

1. **One owner, live wiring.** Extend the reusable workflows, theme sync, readiness and contract tests. Calling repositories own content and deployment manifests.
2. **Public contract.** A feature states outcomes, failure behavior, interfaces, tests and tasks in tracked files. No private draft is a contributor prerequisite.
3. **Portable evidence.** Inputs are public repository references and published artifacts. Missing evidence is not success.
4. **Publish the tool before the gate.** A gate that a consumer adopts must run from a published release.
5. **Computed state.** A row is `SPECIFIED`, `LANDED`, `VERIFIED` or `RETIRED`. The generator computes it and no file writes it.

Amend this file in a reviewed change. State the impact in the pull request.
