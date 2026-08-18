# Pages agent-readiness delivery

This reusable workflow provides the static Pages half of the documentation
delivery contract (`CONCEPT:ECO-4.DOCS-DELIVERY`). It keeps the existing Pages
build unchanged unless a caller explicitly sets
`agent_readiness_enabled: true`.

When enabled, the workflow requires the caller to have already generated the
canonical universal-skills artifacts:

- `agent-readiness-manifest.json` — generator version, applicability,
  operator-supplied Content Signals, generated outputs, and source provenance;
- `markdown-mirror-manifest.json` — the `mkdocs-static/v2` source/digest map,
  including each canonical URL and its explicit `/index.md` fallback; and
- `docs/agent-readiness.schema.json` plus `docs/agent-readiness.json` — the
  versioned input authority and its explicit applicability policy.

`scripts/pages_readiness.py` validates those exact artifacts, re-hashes every
declared source, rejects traversal/symlink/hardlink/private capability
references, and checks generated-output bounds. It then copies source Markdown
to each declared fallback. Only after all mirrors exist does it add Markdown
alternate links to the corresponding HTML, emit bounded `robots.txt` and
`sitemap.xml`, and write `.nojekyll` so Pages serves the static `.md` files.

Existing HTML `noindex` and deprecated markers are retained. Such pages remain
available as explicit fallbacks but are omitted from the generated sitemap.
No Content Signals are inferred: `policy: unset` emits no signal, while an
`operator-reviewed` policy is checked against the canonical manifest and is
not widened by this workflow. Negotiated `Accept: text/markdown` responses,
RFC 8288 headers, cache variants, and security headers belong to the separately
owned edge route; GitHub Pages receives only static assets here.

The helper has `build`, `check`, and `tck` modes. `build` is deterministic and
atomic; `check`/`tck` are read-only and require a current artifact tree. The
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
      agent_readiness_enabled: true
      readiness_input: docs/agent-readiness.json
      readiness_schema: docs/agent-readiness.schema.json
      readiness_manifest: agent-readiness-manifest.json
      markdown_manifest: markdown-mirror-manifest.json
```

The default is deliberately `false`. A caller that opts in but omits, has
stale digests, or supplies malformed manifests fails closed before upload. No
caller command string is accepted: the only executable is this repository-owned
helper.
