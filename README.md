# pipelines
Version: 2.0.2

All GitHub Action Workflows


```yaml
name: Build|Upload|Release Python Package

on:
  push:
    branches:
      - 'main'

jobs:
  publish:
    uses: Knuckles-Team/pipelines/.github/workflows/python_pipeline.yml@main
    secrets:
      PYPI_API_TOKEN: ${{ secrets.PYPI_API_TOKEN }}
```

## Shared pre-commit hooks

`.pre-commit-hooks.yaml` publishes the fleet's repository-agnostic quality gates
(package `pipelines_hooks`, console script `pipelines-hook <gate>`). Every
repository-specific input lives in the consumer's `pyproject.toml`, never in the
hook code. Exit codes are uniform: 0 clean, 1 findings, 2 the gate could not run.

```yaml
- repo: https://github.com/Knuckles-Team/pipelines
  rev: <full commit SHA>
  hooks:
  - id: complexity-staged
  - id: kiss-census
    stages: [pre-push, manual]
```

```toml
[tool.pipelines_hooks]
packages = ["my_package"]                    # package-scoped gates and KISS/census scope

[tool.pipelines_hooks.complexity]
census_paths = ["my_package"]                # default: packages

[tool.pipelines_hooks.kiss]
paths = ["my_package"]                       # default: packages

[tool.pipelines_hooks.env_sprawl]
allow_files = ["my_package/config.py"]       # the only module that reads the environment

[tool.pipelines_hooks.stdout_writes]
served_paths = ["my_package"]                # the stdio JSON-RPC surface

[tool.pipelines_hooks.stubs]
declared_seams = { "my_package/sink.py" = ["PENDING_CONSTANT"] }

[tool.pipelines_hooks.ci_replica.workflows."release.yml"]
blocking = true
executable_jobs = ["gates"]
skip_reasons = { publish = "tag-gated publishing never runs locally" }
```

| Hook | Checks | Inputs |
|---|---|---|
| `complexity-staged` / `complexity-census` | cccc 1.6.0: no new or worsened function over cyclomatic 10 / cognitive 15; census at absolute zero outside the Rust exhaustive-dispatch terms of acceptance | `complexity.census_paths` |
| `kiss-staged` / `kiss-census` | KISS 0.4.10 with the repository's `.kiss/kiss.toml`; staged findings narrowed to the diff; census enforces every finding and orphan modules | `kiss.paths`, `.kiss/kiss.toml` |
| `dupehound-changed` | dupehound 0.1.2 structural whole-function clones in changed source; rot-detecting `dupehound-distinct.toml` register | `--base-ref`, register file |
| `jscpd-differential` / `jscpd-census` | jscpd 5.0.16 new clone pairs on the merged tree; tracked-tree census (advisory) | `--base-ref` |
| `scanner-versions` | the four native scanners at their pinned versions | tool names |
| `secret-history` | credential shapes in the unpublished commit range | `--base`, `--text-file`, `--self-check` |
| `security-sanitizer` | unmasked secrets and root garbage | none |
| `tracked-privacy` | host paths, local identities, internal endpoints, catalog identities | `--identity-catalog` |
| `dependency-audit` | OSV advisories against `.security-audit-allow.txt` | lock path |
| `supply-chain` | pinned actions, hook revisions, images, dependency sources, credential material | root, `--fleet-root`, snapshot mode |
| `root-hygiene` | every root entry declared with a reason in `.repo-layout.toml` (`[dirs]`, `[files]`, `[dotfiles]`) | `.repo-layout.toml` |
| `gitignore-convergence` | the fleet-shared REQUIRED ignore set; no tracked build output | none |
| `sprawl`, `pre-commit-patch-safety`, `mermaid` | versioned clones and merge artifacts; live patches in the pre-commit cache; Mermaid syntax | `--patch-dir`, files |
| `no-stub`, `stubs` | stub markers, unmarked `NotImplementedError`, stub bodies, deferred-work comments | `stubs.declared_seams` |
| `swallowed-errors`, `event-loop-blocking` | census plus diff-scoped enforcement of added cause-dropping handlers and blocking calls in async code | `packages` |
| `import-cycles`, `env-sprawl`, `stdout-writes` | eager import cycles; bare environment reads; stdout writes in a served surface | `packages`, `env_sprawl.allow_files`, `stdout_writes.served_paths` |
| `ci-gate-replica-consistency` / `ci-gate-replica` | every workflow job classified; replay executable jobs locally | `ci_replica` |

Native scanners must already be installed; hooks never install tools.
