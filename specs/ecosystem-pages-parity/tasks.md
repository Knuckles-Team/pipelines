# Tasks — PIPE-PAGES

- [ ] Review public consumer declaration and receipt schema with full commits, content sources, and owner links.
- [ ] Refactor existing parity script to use exact fetched commits and shared theme enumeration, removing fixed names and worktree fallback.
- [ ] Add strict dirty/untracked, missing-ref, traversal, and mismatch refusal with asset-specific diagnostics.
- [ ] Produce deterministic JSON verification fields and readable Pages summary; retain historical links.
- [ ] Bind parity only to shared theme/navigation promotion; update workflow contract without a live gate on unrelated PRs.
- [ ] Add P-1–P-5 and N-1–N-6 tests; validate YAML, schema, CCCC, jscpd, Dupehound, KISS, and Pages contract.
- [ ] Publish from exact commits, collect consumer/served-site evidence, and update delivery and acceptance separately.

No task above cites a `requirements.md` ID by name. PIPE-PAGES-R001 (repository switcher sync) is
closed by tasks 1-4 above (declared fleet, exact parity, release receipt). PIPE-PAGES-R007 and
PIPE-PAGES-R011 (ecosystem flow diagram, present-tense home page) are already `LANDED` per
`status.json` with merged-head evidence and need no new task.
- [ ] Build or confirm the remaining documentation-site content requirements not covered above:
      layered navigation from overview to reference, present-tense wording with an accessible
      embedded quick start, one progressively disclosed skill-graph content corpus, architecture and
      API-contract reference pages generated from their registries, generated/gate-checked artifacts
      rehomed out of the legacy docs directory, and HTML/CSS architecture views with no ASCII or
      Mermaid diagrams. Closes PIPE-PAGES-R002, PIPE-PAGES-R003, PIPE-PAGES-R004, PIPE-PAGES-R005,
      PIPE-PAGES-R006, PIPE-PAGES-R008, PIPE-PAGES-R009, PIPE-PAGES-R010.
