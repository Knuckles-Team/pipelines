# pipelines

![PyPI - Version](https://img.shields.io/pypi/v/pipelines-hooks)
![PyPI - Downloads](https://img.shields.io/pypi/dd/pipelines-hooks)
![PyPI - License](https://img.shields.io/pypi/l/pipelines-hooks)
![PyPI - Wheel](https://img.shields.io/pypi/wheel/pipelines-hooks)
![PyPI - Implementation](https://img.shields.io/pypi/implementation/pipelines-hooks)
![GitHub Repo stars](https://img.shields.io/github/stars/Knuckles-Team/pipelines)
![GitHub forks](https://img.shields.io/github/forks/Knuckles-Team/pipelines)
![GitHub contributors](https://img.shields.io/github/contributors/Knuckles-Team/pipelines)
![GitHub license](https://img.shields.io/github/license/Knuckles-Team/pipelines)
![GitHub last commit (by committer)](https://img.shields.io/github/last-commit/Knuckles-Team/pipelines)
![GitHub pull requests](https://img.shields.io/github/issues-pr/Knuckles-Team/pipelines)
![GitHub closed pull requests](https://img.shields.io/github/issues-pr-closed/Knuckles-Team/pipelines)
![GitHub issues](https://img.shields.io/github/issues/Knuckles-Team/pipelines)
![GitHub top language](https://img.shields.io/github/languages/top/Knuckles-Team/pipelines)
![GitHub language count](https://img.shields.io/github/languages/count/Knuckles-Team/pipelines)
![GitHub repo size](https://img.shields.io/github/repo-size/Knuckles-Team/pipelines)
![GitHub repo file count (file type)](https://img.shields.io/github/directory-file-count/Knuckles-Team/pipelines)

Shared quality gates and reusable GitHub Actions for the Knuckles-Team agent ecosystem. The package keeps policy in each consuming repository while one implementation provides deterministic local checks and release workflows.

## Overview

`pipelines-hooks` is a small Python package with the `pipelines-hook` command. It publishes repository-agnostic pre-commit gates, while reusable workflows provide tested building blocks for Python, native, container, service, desktop, and Pages delivery.

## Key capabilities

- Repository-local TOML configuration with strict unknown-key validation.
- Security, privacy, supply-chain, hygiene, code-shape, clone, and CI-replica gates.
- A public README/AGENTS surface contract for consistent fleet documentation.
- Reusable GitHub workflows pinned by callers to reviewed immutable commits.
- Pages readiness and shared MkDocs theme assets for deeper documentation.

## Documentation

The [Pages site](https://knuckles-team.github.io/pipelines/) contains the navigable reference surface. The [Pages readiness guide](docs/pages-readiness.md) covers generated manifests, content-source configuration, and delivery checks.

The hook catalogue in `.pre-commit-hooks.yaml` is the authoritative list of published hook IDs. Repository-specific configuration and the CI replica contract are described in the Pages reference; the public-surface gate validates their concise entry points without making live HTTP requests.

## Architecture

The `pipelines-hook` entry point dispatches to one gate module. Gate inputs are read from `[tool.pipelines_hooks]` in the consuming repository; the shared implementation never contains a product-specific allowlist. Gates return zero for clean, one for findings, and two when they cannot produce a trustworthy verdict.

File inputs live under `.config/`, never at the repository root: `.config/repo-layout.toml` (root-hygiene allowlist), `.config/kiss.toml` (KISS thresholds), `.config/dupehound-distinct.toml` (reviewed non-clone register) and `.config/security-audit-allow.txt` (risk-acceptance ledger). A copy left at the retired root location fails the gate with exit status two.

Public documentation checks are configured per repository:

```toml
[tool.pipelines_hooks.public_surface]
repository = "Knuckles-Team/example"
distribution = "example"  # omit when the project has no PyPI distribution
pages_url = "https://knuckles-team.github.io/example/"
mcp_server = false
```

Reusable workflows are called by another repository's own GitHub Actions workflow. They run with that caller's checkout, permissions, and secrets. A caller pins first-party workflows to a full commit SHA and third-party actions to reviewed immutable revisions.

## Quick start

Install the hook package, then run the public-surface check from a configured repository:

```bash
python -m pip install pipelines-hooks
pipelines-hook public-surface
```

For one of the reusable gates, configure it in `.config/pre-commit.yaml`, pin this repository to a reviewed full commit SHA, and run:

```bash
pre-commit run -c .config/pre-commit.yaml --all-files
```

The Pages documentation linked above has the complete hook catalogue and workflow-specific setup steps.

## Contributing

Clone the repository, install the locked development environment, and run focused tests before the complete suite:

```bash
uv sync --locked
uv run pytest -q tests/hooks tests/test_pages_readiness.py
uv run pytest -q
pre-commit run -c .config/pre-commit.yaml --all-files
```

Every new hook invariant needs positive and adversarial fixtures. Workflow changes need contract tests for inputs and permissions. Stage only reviewed files and keep generated environment output untracked.

## License

The package is distributed under the license declared by the project metadata. See the repository metadata and published distribution for the applicable terms.
