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
