"""Render the one slot configuration for each runtime (PIPE-GATES-R071).

``render_runtime`` is the single entry; one renderer per runtime sits behind
it. Every runtime gets the same image and the same cache budget. Kubernetes
(the default) is a runner scale set with a per-node local persistent volume
that scales to zero when idle and up on queued jobs. Docker Compose and
rootless Podman (quadlet units) run the image directly; the SSH mode renders
the plain host settings. A runtime that needs a value the shared file does
not hold fails and names the field.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import yaml

from pipelines_hooks.ci.warm_slots.config import RUNTIMES, Pool, SlotConfig
from pipelines_hooks.core.errors import CannotRun

#: Fields each runtime needs beyond the always-required image and cache root.
REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "kubernetes": ("namespace", "repository_url", "pool.node"),
    "compose": ("repository_url",),
    "podman": ("repository_url",),
    "ssh": ("pool.host",),
}
CACHE_MOUNT = "/cache"


def _require(config: SlotConfig, runtime: str) -> None:
    if not config.definition.image:
        raise CannotRun("warm slots: image.reference is required to render any runtime")
    for field in REQUIRED_FIELDS[runtime]:
        if field.startswith("pool."):
            name = field.removeprefix("pool.")
            for pool in config.pools:
                if not getattr(pool, name):
                    raise CannotRun(f"warm slots: {runtime} needs {field} and pool {pool.name} does not hold it")
        elif not getattr(config, field):
            raise CannotRun(f"warm slots: {runtime} needs {field} and the shared file does not hold it")
    for pool in config.pools:
        if not pool.cache_root:
            raise CannotRun(f"warm slots: {runtime} needs pool.cache_root and pool {pool.name} does not hold it")


def _cache_environment(pool: Pool, root: str = CACHE_MOUNT) -> dict[str, str]:
    return {
        "CARGO_TARGET_DIR": f"{root}/target",
        "SCCACHE_DIR": f"{root}/sccache",
        "SCCACHE_CACHE_SIZE": f"{pool.cache_budget_gb}G",
        "WARM_SLOT_CACHE_BUDGET_GB": str(pool.cache_budget_gb),
    }


def _yaml(documents: list[dict[str, object]]) -> str:
    return "---\n".join(yaml.safe_dump(document, sort_keys=True) for document in documents)


def _kubernetes(config: SlotConfig) -> dict[str, str]:
    files: dict[str, str] = {}
    for pool in config.pools:
        claim = f"warm-slot-{pool.name}-cache"
        storage = f"{pool.cache_budget_gb}Gi"
        selector = {"kubernetes.io/hostname": pool.node}
        documents: list[dict[str, object]] = [
            {
                "apiVersion": "storage.k8s.io/v1",
                "kind": "StorageClass",
                "metadata": {"name": "warm-slot-local"},
                "provisioner": "kubernetes.io/no-provisioner",
                "volumeBindingMode": "WaitForFirstConsumer",
            },
            {
                "apiVersion": "v1",
                "kind": "PersistentVolume",
                "metadata": {"name": claim},
                "spec": {
                    "capacity": {"storage": storage},
                    "accessModes": ["ReadWriteOnce"],
                    "storageClassName": "warm-slot-local",
                    "local": {"path": pool.cache_root},
                    "nodeAffinity": {
                        "required": {
                            "nodeSelectorTerms": [
                                {
                                    "matchExpressions": [
                                        {"key": "kubernetes.io/hostname", "operator": "In", "values": [pool.node]}
                                    ]
                                }
                            ]
                        }
                    },
                },
            },
            {
                "apiVersion": "v1",
                "kind": "PersistentVolumeClaim",
                "metadata": {"name": claim, "namespace": config.namespace},
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "storageClassName": "warm-slot-local",
                    "resources": {"requests": {"storage": storage}},
                },
            },
        ]
        values = {
            "githubConfigUrl": config.repository_url,
            "runnerScaleSetName": f"{config.runner_label}-{pool.name}",
            "minRunners": 0,
            "maxRunners": pool.slots,
            "template": {
                "spec": {
                    "nodeSelector": selector,
                    "containers": [
                        {
                            "name": "runner",
                            "image": config.definition.image,
                            "env": [
                                {"name": key, "value": value} for key, value in sorted(_cache_environment(pool).items())
                            ],
                            "volumeMounts": [{"name": "cache", "mountPath": CACHE_MOUNT}],
                        }
                    ],
                    "volumes": [{"name": "cache", "persistentVolumeClaim": {"claimName": claim}}],
                }
            },
        }
        files[f"kubernetes/{pool.name}-volume.yaml"] = _yaml(documents)
        files[f"kubernetes/{pool.name}-runner-set-values.yaml"] = yaml.safe_dump(values, sort_keys=True)
    return files


def _compose(config: SlotConfig) -> dict[str, str]:
    files = {}
    for pool in config.pools:
        services = {
            f"slot-{pool.name}-{number}": {
                "image": config.definition.image,
                "restart": "unless-stopped",
                "environment": {**_cache_environment(pool), "REPOSITORY_URL": config.repository_url},
                "volumes": [f"{pool.cache_root}/slot-{number}:{CACHE_MOUNT}"],
            }
            for number in range(1, pool.slots + 1)
        }
        files[f"compose/{pool.name}.yaml"] = yaml.safe_dump({"services": services}, sort_keys=True)
    return files


def _podman(config: SlotConfig) -> dict[str, str]:
    files = {}
    for pool in config.pools:
        for number in range(1, pool.slots + 1):
            environment = {**_cache_environment(pool), "REPOSITORY_URL": config.repository_url}
            lines = [
                "[Unit]",
                f"Description=Warm build slot {pool.name}-{number}",
                "",
                "[Container]",
                f"Image={config.definition.image}",
                f"Volume={pool.cache_root}/slot-{number}:{CACHE_MOUNT}:Z",
                *(f"Environment={key}={value}" for key, value in sorted(environment.items())),
                "",
                "[Service]",
                "Restart=always",
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
            files[f"podman/warm-slot-{pool.name}-{number}.container"] = "\n".join(lines)
    return files


def _ssh(config: SlotConfig) -> dict[str, str]:
    files = {}
    for pool in config.pools:
        settings = {
            "WARM_SLOT_IMAGE": config.definition.image,
            "WARM_SLOT_HOST": pool.host,
            "WARM_SLOT_COUNT": str(pool.slots),
            "WARM_SLOT_CACHE_ROOT": pool.cache_root,
            "WARM_SLOT_AUTO_SELECT": "true" if pool.auto_select else "false",
            **_cache_environment(pool, pool.cache_root),
        }
        files[f"ssh/{pool.name}.env"] = "".join(f"{key}={value}\n" for key, value in sorted(settings.items()))
    return files


_RENDERERS: Mapping[str, Callable[[SlotConfig], dict[str, str]]] = {
    "kubernetes": _kubernetes,
    "compose": _compose,
    "podman": _podman,
    "ssh": _ssh,
}


def render_runtime(config: SlotConfig, runtime: str | None = None) -> dict[str, str]:
    """The files of one runtime, by relative path. ``runtime`` defaults to the configured one."""
    chosen = runtime or config.runtime
    if chosen not in RUNTIMES:
        raise CannotRun(f"warm slots: runtime {chosen!r} is not one of {', '.join(RUNTIMES)}")
    _require(config, chosen)
    return _RENDERERS[chosen](config)
