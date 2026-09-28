# Architecture — PIPE-EH-428

## Existing wiring

`scripts/sync_mkdocs_theme.py` defines shared assets and check mode. `.github/workflows/pages_pipeline.yml` checks out the caller and immutable workflow revision, validates `content_source`, checks theme assets, builds MkDocs, and publishes. `scripts/check_five_repo_parity.py` and `pages/parity.md` are a snapshot implementation with five fixed names and local-worktree assumptions; migrate their comparison/rendering logic rather than adding a second checker. `tests/test_pages_pipeline_contract.py` and `tests/test_pages_readiness.py` are existing test seams.

## Input and provenance

Use a tracked, schema-validated declaration of public GitHub repositories and full commit IDs. Resolve every declaration to a clean fetched tree at its exact commit, including the pipeline source revision. Fail closed on missing ref, duplicate repository, dirty or untracked overlay, missing asset, or ambiguous content source. Never silently use local `main` or a remembered worktree. Fetch credentials are read-only and scoped to public source; emit no token or machine path.

## Comparison and publication

Reuse `sync_theme(..., mode="check")` or factor shared asset enumeration used by both workflow and receipt generator. Hash exact asset bytes and record each match/mismatch. Separate deterministic verification data from generation time so repeated exact-input runs match. Publish JSON and a concise HTML/Markdown summary through the existing Pages workflow after verification. Preserve historical receipts by commit link; changing current fleet input does not upgrade old evidence.

## Integration boundary

The generic workflow accepts a versioned declaration or receipt artifact; consumers opt in and pin its SHA. Tests use disposable Git fixtures or fetched public commits, never a live cluster. Only theme/navigation promotion consumes parity. The organization entrypoint may link the summary but owns its own site assembly. No new fleet runtime or parallel policy database.

## Failure, compatibility, security, and quality

Fetch failure means unverified. Reject traversal, symlink escape, malformed revision, extra declaration fields, and out-of-tree asset names. Keep schema versioned; old local-worktree snapshots remain historical rather than current exact-ref proof. New consumers opt in; removal requires a reviewed declaration change. Use `complexity-staged`/`complexity-census` (CCCC 10/15), `jscpd-differential` plus advisory census, `dupehound-changed`, and `kiss-staged`/`kiss-census` with `.config/kiss.toml`; run workflow YAML and contract tests. Reuse existing parser/theme/Pages wiring to satisfy KISS.
