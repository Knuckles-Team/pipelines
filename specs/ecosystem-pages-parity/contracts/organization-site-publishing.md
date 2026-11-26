# Organization site publishing seam

Consumer: pipelines PIPE-PAGES-R056.3
Consumer: pipelines PIPE-PAGES-R057.3
Provider: .github ORG-FRONT-R010.1
Provider: .github ORG-FRONT-R010.2
Provider: .github ORG-FRONT-R010.3

## Wire shape

- The site workflow checks out `releases/` and `scripts/architecture_explorer` from the pipelines default branch.
- `build.py --mode github --page <site>/architecture/index.html` writes `export/rows.json` and `export/rows.md` beside the page.
- `rows.json` holds `{schema, built_at, heads, view, digest, rows[]}`. Each row holds the fields of `ExportRow` (PIPE-PAGES-R057.1).

## Refusal codes

- `unsafe-path`: a row path is absolute or holds `..`. The build exits 1.
- `export-row-missing`: a scanned row has no export entry. The build exits 1.
- `release-manifest-invalid`: a manifest has a malformed phase. The build exits 1.
- A missing `releases/` directory fails a GitHub-mode build.

## Authoritative types

`ExportRow` of `PIPE-PAGES-R057.1` in `scripts/architecture_explorer`. The `.github` repository keeps no second row type.

## Test vectors

`tests/test_architecture_explorer.py` holds the vectors on the pipelines side: an unsafe path, a missing export entry and a malformed release manifest. The organization site workflow of `ORG-FRONT-R010.1` checks the written `rows.json` against the same fields.
