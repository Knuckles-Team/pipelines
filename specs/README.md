# Pipelines specifications

This directory is the public build contract for pipeline-owned Graph OS ecosystem work. Each feature has `spec.md` (outcome), `plan.md` (architecture), `test-spec.md` (proof), and `tasks.md` (work order). `requirements.md` defines every requirement ID the spec owns. `status.json` records delivery and acceptance. It carries a `requirements` array, one entry per requirement ID, with its own `delivery_state` and evidence. Start from [_template](_template/). A proposed spec does not claim its behavior has landed.

| Spec | Requirement | Owner boundary | Delivery | Acceptance |
|---|---|---|---|---|
| [ecosystem-pages-parity](ecosystem-pages-parity/spec.md) | PIPE-PAGES-R001 | Shared Pages parity and release receipt | SPECIFIED | NOT_AUDITED |
| [ordered-digest-release](ordered-digest-release/spec.md) | PIPE-RELEASE-R001 | Shared CI/release orchestration | SPECIFIED | NOT_AUDITED |
| [commit-identity-governance](commit-identity-governance/spec.md) | PIPE-IDENTITY-R001 | Commit author/committer identity allowlist enforcement | SPECIFIED | NOT_AUDITED |
| [connector-spec-delivery](connector-spec-delivery/spec.md) | PIPE-CONNSPEC-R001 | Spec-delivery standard and per-connector rollout | SPECIFIED | NOT_AUDITED |

`SPECIFIED` means ready for implementation. `BUILDING`, `BUILT`, and `LANDED` distinguish work in progress, source produced, and an exact merged revision. `CLOSED`, `DEFERRED`, and `REJECTED` are explicit dispositions. `UNKNOWN` means no exact audit established delivery. `NOT_AUDITED`, `PENDING`, `ACCEPTED`, and `FAILED` describe the separate acceptance result. Only a public merged revision supports `LANDED`; only recorded tests, consumer, and release receipts support `ACCEPTED`. A requirement counts as delivered only once a merged-head commit on the default branch demonstrates it, per its `requirements` entry in `status.json`.

These specs follow GitHub Spec Kit's specify, plan, and tasks lifecycle and add explicit test and status artifacts. The [constitution](../.specify/memory/constitution.md) governs contributions. Each cross-repository owner retains a self-contained local spec. Contributors can use [spec-generator](https://github.com/Knuckles-Team/universal-skills/tree/main/universal_skills/development/spec-generator), [spec-verifier](https://github.com/Knuckles-Team/universal-skills/tree/main/universal_skills/development/spec-verifier), and [graph-os-development](https://github.com/Knuckles-Team/graph-os/blob/main/graph_os/skills/graph-os-development/SKILL.md).

Run `python scripts/check_public_specs.py` to validate local structure, status, ownership, links, and private-reference exclusions without network or a live environment.
