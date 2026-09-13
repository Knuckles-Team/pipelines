"""ci-gate-replica: replay every workflow under .github/workflows/ locally.

It PARSES the workflow files instead of hand-copying their steps (a copied step
list drifts silently). Every step is classified: a ``run:`` step in an
EXECUTABLE job runs verbatim; environment-setup and artifact-transfer actions
are silent no-ops; anything else -- and every step of a skip-reasoned job -- is
reported loudly as NOT VALIDATED LOCALLY, never counted as a pass.

The anti-drift guarantee (``--consistency-check``): every workflow file must be
registered in ``[tool.pipelines_hooks.ci_replica.workflows]`` and every job
classified as executable or skip-reasoned; a new, renamed or removed workflow
or job fails. So does a ``.cargo/config.toml`` external build binary that no
workflow ever installs.
"""
