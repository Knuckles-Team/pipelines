# Pages agent-readiness delivery

This reusable workflow provides the static Pages half of the documentation
delivery contract (`CONCEPT:ECO-4.DOCS-DELIVERY`). It keeps the existing Pages
build unchanged unless a caller explicitly sets `agent_readiness_enabled:
true` and/or `shared_theme_enabled: true`.

## `content_source` — one declared authority, no silent fallback

`content_source` (default `pages`) names the repository's documentation
source directory -- the same thing mkdocs calls `docs_dir`. It only matters
once a caller opts into `shared_theme_enabled` or `agent_readiness_enabled`;
a repository that uses neither keeps building exactly as it does today,
regardless of this default. Once either feature is enabled, the workflow:

- fails loudly if `content_source` is empty or the named directory does not
  exist -- there is no fallback probing between the `pages/` and `docs/`
  layouts;
- fails loudly if the repository's own `mkdocs.yml` already declares a
  `docs_dir` that disagrees with the declared `content_source` -- mkdocs.yml's
  `docs_dir` is the single authority `repository-manager`'s docs-readiness
  tooling reads too (see its `AGENTS.md`), so the two must never diverge.

A repository still on the legacy `docs/` layout that wants either feature
must pass `content_source: docs` explicitly (and, if it also enables
`agent_readiness_enabled`, `readiness_input: docs/agent-readiness.json` and
`readiness_schema: docs/agent-readiness.schema.json` -- see below).

## Shared theme

`shared_theme_enabled: true` makes the caller's `mkdocs.yml` inherit
`templates/mkdocs-theme/base.mkdocs.yml` (Material theme configuration,
markdown extensions, shared `extra.css`) from this repository via mkdocs's
native `INHERIT:` key -- a real recursive config merge, not a text copy. A
repository that enables it keeps only its content manifest (`site_name`,
`site_url`, `nav`, and `docs_dir`/`content_source`); look, structure and
navigation hierarchy come from the one shared file, identically, across every
consumer (EG, the connector SDK, AU, graph-os, and the UIs -- RF-ADR-009
D3/D5). The shared theme deliberately does not enable the `pymdownx`
`mermaid` custom fence: D3 requires HTML/CSS renderings, not diagrams drawn
in Markdown.

When enabled, the workflow requires the caller to have already generated the
canonical universal-skills artifacts:

- `agent-readiness-manifest.json` — generator version, applicability,
  operator-supplied Content Signals, generated outputs, and source provenance;
- `markdown-mirror-manifest.json` — the `mkdocs-static/v2` source/digest map,
  including each canonical URL and its explicit `/index.md` fallback; and
- `<content_source>/agent-readiness.schema.json` plus
  `<content_source>/agent-readiness.json` (default `pages/…`) — the versioned
  input authority and its explicit applicability policy.

`scripts/pages_readiness.py` validates those exact artifacts, re-hashes every
declared source, rejects traversal/symlink/hardlink/private capability
references, and checks generated-output bounds. It then copies source Markdown
to each declared fallback and copies the canonical `llms.txt` hierarchy into
the uploaded site. Existing `.well-known` files from the strict MkDocs output
are retained. Only after all mirrors exist does it add Markdown alternate links
and the non-executable HTML-only `agent-utilities-markdown` directive (pointing
to that page's Markdown alternate and the canonical `llms.txt`) to the
corresponding HTML, emit bounded `robots.txt` and `sitemap.xml`, and write
`.nojekyll` so Pages serves the static `.md` files. The helper preserves an
existing UTF-8 `robots.txt` policy and adds exactly one validated sitemap line;
when no policy exists it emits only the sitemap directive.

Existing HTML `noindex` and deprecated markers are retained. Such pages remain
available as explicit fallbacks but are omitted from the generated sitemap.
No Content Signals are inferred: `policy: unset` emits no signal, while an
`operator-reviewed` policy is checked against the canonical manifest and is
not widened by this workflow. Negotiated `Accept: text/markdown` responses,
RFC 8288 headers, cache variants, and security headers belong to the separately
owned edge route; GitHub Pages receives only static assets here.

The helper has `build`, `check`, and `tck` modes. `build` is deterministic and
atomic; `check`/`tck` are read-only and require a current artifact tree. Every
JSON result identifies `pages-readiness-tck/v1`, `agent-readiness/v1`, and
`mkdocs-static/v2` explicitly. The
workflow checks out its own helper at the exact reusable-workflow commit using
the GitHub `job.workflow_repository`/`job.workflow_sha` identity, and all
third-party actions are immutable SHA references. Results contain only bounded
counts and a manifest digest; source paths, host paths, credentials, and
private URLs are never printed.

## Caller contract

```yaml
jobs:
  pages:
    uses: Knuckles-Team/pipelines/.github/workflows/pages_pipeline.yml@<reviewed-sha>
    with:
      content_source: pages
      shared_theme_enabled: true
      agent_readiness_enabled: true
      readiness_input: pages/agent-readiness.json
      readiness_schema: pages/agent-readiness.schema.json
      readiness_manifest: agent-readiness-manifest.json
      markdown_manifest: markdown-mirror-manifest.json
```

A repository still on `docs/` declares that explicitly instead:

```yaml
    with:
      content_source: docs
      agent_readiness_enabled: true
      readiness_input: docs/agent-readiness.json
      readiness_schema: docs/agent-readiness.schema.json
```

`shared_theme_enabled` and `agent_readiness_enabled` both default to `false`
and are independent -- a caller may enable either, both, or neither. A caller
that opts into readiness delivery but omits, has stale digests, or supplies
malformed manifests fails closed before upload. No caller command string is
accepted: the only executable is this repository-owned helper.
