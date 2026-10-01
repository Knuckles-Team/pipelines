# Tasks — PIPE-IDENTITY-001

- [ ] Define the bounded, versioned allowlist configuration schema (`{name, email}` pairs) and its
      load/validation module, modeled on `pipelines_hooks/privacy/identity_catalog.py`. Closes FR-1
      (PIPE-IDENTITY-R001).
- [ ] Implement the `commit-identity` gate module resolving the commit's own author/committer
      identity through `pipelines_hooks/core/gitenv.py` and comparing it against the loaded
      allowlist, naming only the failing field on rejection. Closes FR-2 (PIPE-IDENTITY-R001).
- [ ] Register the gate in `pipelines_hooks/cli.py`'s `GATES` dict and in `.pre-commit-hooks.yaml` at
      the default (commit) stage. Closes FR-2 (PIPE-IDENTITY-R001).
- [ ] Add the same gate under a `stages: [pre-push, manual]` entry in `.config/pre-commit.yaml` so
      the full outgoing commit range is re-checked before push. Closes FR-3 (PIPE-IDENTITY-R001).
- [ ] Confirm `.github/workflows/ci.yml`'s existing commit-stage and `--hook-stage manual` runs cover
      the new gate with no additional workflow step, over the full incoming range. Closes FR-4
      (PIPE-IDENTITY-R001).
- [ ] Wire `Unavailable`/`CannotRun` fail-closed behavior for a missing or malformed configuration,
      and register any new environment variable in `pipelines_hooks/core/settings.py`. Closes FR-5
      (PIPE-IDENTITY-R001).
- [ ] Add the P-1–P-4 and N-1–N-5 tests from `test-spec.md` using sanitized fixture git repositories;
      run the repository's YAML parse, pytest, CCCC, jscpd, Dupehound, and KISS gates on the
      implementation, and record evidence before changing `delivery_state` or `acceptance_state` in
      `status.json`.
