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

Shared quality gates and reusable GitHub Actions for the Knuckles-Team agent
ecosystem. The package keeps policy in each consuming repository while one
implementation provides deterministic local checks and release workflows.

## Overview

`pipelines-hooks` is a small Python package with the `pipelines-hook` command.
It publishes repository-agnostic pre-commit gates, while the reusable workflows
provide tested building blocks for Python, native, container, service, desktop,
and Pages delivery.

## Key capabilities

- Repository-local TOML configuration with strict unknown-key validation.
- Security, privacy, supply-chain, hygiene, code-shape, clone, and CI-replica gates.
- A public README/AGENTS surface contract for consistent fleet documentation.
- Reusable GitHub workflows pinned by callers to reviewed immutable commits.
- Pages readiness and shared MkDocs theme assets for deeper documentation.

## Installation

Install the hook package in the environment used by pre-commit:

```bash
pip install pipelines-hooks
```

The native scanners used by some gates are installed by the consuming
repository or its CI image; the hooks never install tools during a check.

## Quick start

Add the published hook catalogue to `.pre-commit-config.yaml` and pin it to a
reviewed commit:

```yaml
- repo: https://github.com/Knuckles-Team/pipelines
  rev: <full commit SHA>
  hooks:
  - id: public-surface
  - id: security-sanitizer
  - id: supply-chain
```

Run the same checks locally and in CI:

```bash
pre-commit run --all-files
pipelines-hook public-surface
```

The public documentation gate is configured alongside the other shared hooks:

```toml
[tool.pipelines_hooks.public_surface]
repository = "Knuckles-Team/example"
distribution = "example"  # omit for a non-PyPI repository
pages_url = "https://knuckles-team.github.io/example/"
mcp_server = false
```

## Architecture

The `pipelines-hook` entry point dispatches to one gate module. Gate inputs are
read from `[tool.pipelines_hooks]` in the consuming repository; the shared
implementation never contains a repository-specific allowlist. Every gate
returns zero for clean, one for findings, and two when it cannot produce a
trustworthy verdict.

Reusable workflows are called by a repository's own GitHub Actions workflow.
They run with that caller's checkout, permissions, and secrets. A caller pins
each first-party workflow to a full commit SHA and keeps third-party actions
SHA-pinned as well.

## Documentation

The [Pages documentation](https://knuckles-team.github.io/pipelines/) contains
the navigable reference surface. The [Pages readiness guide](docs/pages-readiness.md)
covers the generated manifests, content-source contract, and delivery checks.

The hook catalogue in `.pre-commit-hooks.yaml` is the authoritative list of
published hook IDs. The command-line help lists the same registry:

```bash
pipelines-hook
```

## Development

Clone the repository, install the locked development environment, and run the
focused tests before the complete suite:

```bash
uv sync --locked
uv run pytest -q tests/hooks tests/test_pages_readiness.py
uv run pytest -q
```

Changes to a gate include positive and adversarial fixtures. Changes to a
workflow include a contract test for its inputs and permissions. Run
`pre-commit run --all-files` before submitting a change.

## License

The package is distributed under the license declared by the project metadata.
See the repository metadata and published distribution for the applicable
terms.
