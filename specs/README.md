# Pipelines specifications

These specs follow the ecosystem [spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): one owning spec per capability, extend an existing spec before creating one, audits and reviews land in the owning spec, one ID and title form, one file set. The `spec-standard` gate enforces it.

This directory is the public build contract for pipeline-owned Graph OS ecosystem work. Each feature has `spec.md` (outcome), `plan.md` (architecture), `test-spec.md` (proof), and `tasks.md` (work order). `requirements.md` defines every requirement ID the spec owns. `status.json` is generated and records the state. It carries a `requirements` array, one entry per requirement ID, with its own `delivery_state` and evidence. Start from [_template](_template/). A proposed spec does not claim its behavior has landed.

| Spec | Requirement | Owner boundary |
|---|---|---|
| [ecosystem-pages-parity](ecosystem-pages-parity/spec.md) | PIPE-PAGES-R001 | Shared Pages parity and release receipt |
| [ordered-digest-release](ordered-digest-release/spec.md) | PIPE-RELEASE-R001 | Shared CI/release orchestration |
| [commit-identity-governance](commit-identity-governance/spec.md) | PIPE-IDENTITY-R001 | Commit author/committer identity allowlist enforcement |
| [connector-spec-delivery](connector-spec-delivery/spec.md) | PIPE-CONNSPEC-R001 | Spec-delivery standard and per-connector rollout |

States are `SPECIFIED`, `LANDED`, and `VERIFIED`; see the [spec standard](../reference/spec-standard.md#states).

These specs follow GitHub Spec Kit's specify, plan, and tasks lifecycle and add explicit test and status artifacts. The [constitution](../.specify/memory/constitution.md) governs contributions. Each cross-repository owner retains a self-contained local spec. Contributors can use [spec-generator](https://github.com/Knuckles-Team/universal-skills/tree/main/universal_skills/development/spec-generator), [spec-verifier](https://github.com/Knuckles-Team/universal-skills/tree/main/universal_skills/development/spec-verifier), and [graph-os-development](https://github.com/Knuckles-Team/graph-os/blob/main/graph_os/skills/graph-os-development/SKILL.md).

Run `python scripts/check_public_specs.py` to validate local structure, status, ownership, links, and private-reference exclusions without network or a live environment.

- [`PIPE-IDENTITY`](commit-identity-governance/spec.md) — Commit author identity governance
- [`PIPE-CONNSPEC`](connector-spec-delivery/spec.md) — Connector spec-delivery rollout
- [`PIPE-PAGES`](ecosystem-pages-parity/spec.md) — Ecosystem Pages parity and release receipt
- [`PIPE-RELEASE`](ordered-digest-release/spec.md) — Dependency-ordered digest release orchestration
