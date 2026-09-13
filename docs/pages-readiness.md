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

The `scripts/pages_readiness.py` entry and its bounded `scripts/readiness/`
package validate those exact artifacts, re-hash every declared source, reject
traversal/symlink/hardlink/private capability references, and check
generated-output bounds. They then copy source Markdown
to each declared fallback and copies the canonical `llms.txt` hierarchy and the
generated `.well-known` discovery documents into the uploaded site. Other
existing `.well-known` files from the strict MkDocs output are retained. Only
after all mirrors exist does it add Markdown alternate links
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

### Site root and output paths

`mkdocs build --site-dir site` always writes the site root at `site/`; GitHub
Pages adds a project page's `/<repository>/` prefix only when it serves the
site. The helper therefore reads `site_url` from the repository's `mkdocs.yml`
(the same value the generator derives every URL from; it is required) and
maps each page with one rule, `site_output_path`: strip the `site_url` base
path, then serve a directory URL from `<path>/index.html`, a `*.html` URL
(`use_directory_urls: false`) from itself, and an `index.md` fallback from
itself. A URL on another origin or outside the base path fails closed. The
same base supplies the `llms.txt` and `sitemap.xml` URLs. This holds for a
project page (`https://<owner>.github.io/<repository>/`), a root user or
organization page (`https://<owner>.github.io/`), and a custom domain.

### One readiness contract with the generator

The TCK accepts exactly what the universal-skills generator
(`agent-package-builder/scripts/agent_readiness.py`) is designed to accept and
emit, with the same error codes:

- **Discovery outputs.** Besides `llms.txt`, `llms-full.txt`,
  `llms-sections/*/llms.txt` and `markdown-mirror-manifest.json`, the
  `generated` list may name only `.well-known/agent-skills.json`,
  `.well-known/mcp-server-card.json` and `.well-known/api-catalog` (never an
  open `.well-known/` directory). `agent-skills.json` must be present exactly
  when `discoverability` and `skills` are both applicable; the server card and
  API catalog may appear only for an applicable MCP/A2A surface that is not
  declared `local` or `in-cluster`. Each must be a bounded, secret-free JSON
  object, and is published into the site.
- **Capability entries.** `api`/`mcp`/`a2a` accept `artifact`, an optional
  public HTTPS `endpoint` and the optional OAuth metadata references
  (`.well-known/oauth-protected-resource`,
  `.well-known/oauth-authorization-server`); a `library` or `docs-only`
  project cannot declare a served capability. A capability artifact may carry
  `http_transport` (MCP only). An applicable `skills` path must contain at
  least one `<skill>/SKILL.md`.
- **Manifest comparison.** The generator records `applicable`, `artifact`,
  `path`, `transport` and `reachability` in `agent-readiness-manifest.json`
  and omits `endpoint`, `service_identity` and OAuth references; the TCK
  compares the manifest against that same projection
  (`normalized_capabilities`).

### Non-public MCP and A2A surfaces

A connector usually serves MCP over stdio or in-cluster HTTP, with no public
endpoint. `mcp` and `a2a` declare that honestly with `transport` and
`reachability`. They are optional; once either is present, both are required
and must agree:

| `reachability` | `transport` | Required | Forbidden |
|---|---|---|---|
| `local` | `stdio` (MCP only) | — | `endpoint`, `service_identity` |
| `in-cluster` | MCP `streamable-http`/`sse`; A2A `jsonrpc`/`http-json`/`grpc` | `service_identity` (a `<service>.<namespace>`-style DNS name, never a URL or address) | `endpoint` |
| `public` | same network transports | a verifiable public HTTPS `endpoint` | `service_identity` |

An MCP surface declaring `streamable-http` or `sse` must be backed by a
capability artifact with `"http_transport": true`. A stdio connector that also
ships skills marks both capabilities applicable, binds MCP to its artifact with
the `stdio`/`local` pair, and names the directory containing its skills.

A declaration without `transport`/`reachability` keeps its earlier meaning: an
optional `endpoint`, validated as public HTTPS when present.

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

Call `.github/workflows/pages_pipeline.yml@<reviewed-sha>` as a reusable
workflow. A repository on the current layout passes `content_source: pages`,
enables the shared theme and agent readiness as needed, and points the two
readiness inputs at `pages/agent-readiness.json` and
`pages/agent-readiness.schema.json`. The generated manifests remain at the
repository root under their canonical names.

A repository still on `docs/` passes `content_source: docs` and points
`readiness_input` and `readiness_schema` at the corresponding files below that
directory.

`shared_theme_enabled` and `agent_readiness_enabled` both default to `false`
and are independent -- a caller may enable either, both, or neither. A caller
that opts into readiness delivery but omits, has stale digests, or supplies
malformed manifests fails closed before upload. No caller command string is
accepted: the only executable is this repository-owned helper.
