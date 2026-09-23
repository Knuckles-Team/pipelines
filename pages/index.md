# Skill Graph

One progressively disclosed corpus of the Knuckles agent ecosystem's concepts, components, and man pages, generated from each repo's own registries and documentation nav (RF-ADR-009 D1) — never hand-authored.

- [Concepts](concepts.md) — level 1, 243 nodes across 7 repos.
- [Components](components.md) — level 2, 247 nodes, each documented by a man page.
- [`corpus.jsonld`](corpus.jsonld) — the full machine corpus (256 man pages), consumable by agents directly over HTTP once this site is published; JSON-LD with `@id` IRIs under `http://knuckles.team/kg#`, the same namespace Epistemic Graph's own ontology uses.

See [Ecosystem glossary](glossary.md) for the shared vocabulary this corpus's repo and concept names draw from.

!!! note "Not the same thing as `skills/skill-graphs`"
    `agent-utilities`' `docs/guides/skill-graph-migration.md` and the `skills/skill-graphs` repository name a **different** artifact: ~74 distilled third-party documentation knowledge-graphs (AWS, Django, Postgres, …) for Pydantic AI agents. This corpus is the RF-ADR-009 D1 documentation-architecture corpus for the ecosystem's own five core repos plus the two satellite UIs — unrelated data, coincidentally similar name.
