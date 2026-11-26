"""One slot configuration renders for every runtime (PIPE-GATES-R071)."""

from __future__ import annotations

import pytest
import yaml
from pipelines_hooks.ci.warm_slots.render import render_runtime
from pipelines_hooks.cli import run_gate
from pipelines_hooks.core.errors import CannotRun

from tests.hooks.warm_slot_fixtures import CONFIG_TEXT, config

RUNTIMES = ("kubernetes", "compose", "podman", "ssh")
IMAGE = "registry.example.invalid/warm-slot:1.96.0-py3.14"


@pytest.mark.spec("PIPE-GATES-R071")
def test_one_config_renders_all_four_runtimes() -> None:
    rendered = {runtime: render_runtime(config(), runtime) for runtime in RUNTIMES}
    assert set(rendered["kubernetes"]) == {
        "kubernetes/alpha-volume.yaml",
        "kubernetes/alpha-runner-set-values.yaml",
        "kubernetes/beta-volume.yaml",
        "kubernetes/beta-runner-set-values.yaml",
    }
    assert set(rendered["compose"]) == {"compose/alpha.yaml", "compose/beta.yaml"}
    assert len(rendered["podman"]) == 3  # two alpha slots and one beta slot
    assert set(rendered["ssh"]) == {"ssh/alpha.env", "ssh/beta.env"}
    assert render_runtime(config()) == rendered["kubernetes"]  # the default runtime


@pytest.mark.spec("PIPE-GATES-R071")
def test_every_runtime_uses_the_same_image_and_cache_budget() -> None:
    for runtime in RUNTIMES:
        for path, text in render_runtime(config(), runtime).items():
            if path.endswith("-volume.yaml"):
                continue
            assert IMAGE in text or runtime == "ssh" or "values" in path, path
            pool_budget = "200" if "alpha" in path else "120"
            assert f"{pool_budget}G" in text or f"={pool_budget}" in text or f"'{pool_budget}'" in text, (runtime, path)
    ssh = render_runtime(config(), "ssh")["ssh/alpha.env"]
    assert f"WARM_SLOT_IMAGE={IMAGE}" in ssh and "WARM_SLOT_AUTO_SELECT=true" in ssh and "WARM_SLOT_COUNT=2" in ssh
    compose = yaml.safe_load(render_runtime(config(), "compose")["compose/alpha.yaml"])
    assert {service["image"] for service in compose["services"].values()} == {IMAGE}
    volume_docs = list(yaml.safe_load_all(render_runtime(config(), "kubernetes")["kubernetes/alpha-volume.yaml"]))
    assert {doc["spec"]["capacity"]["storage"] for doc in volume_docs if doc["kind"] == "PersistentVolume"} == {"200Gi"}


@pytest.mark.spec("PIPE-GATES-R071")
def test_the_kubernetes_set_scales_to_zero_when_idle(tmp_path, capsys) -> None:
    values = yaml.safe_load(render_runtime(config(), "kubernetes")["kubernetes/alpha-runner-set-values.yaml"])
    assert values["minRunners"] == 0 and values["maxRunners"] == 2
    assert values["template"]["spec"]["nodeSelector"] == {"kubernetes.io/hostname": "node-a"}
    volume = yaml.safe_load_all(render_runtime(config(), "kubernetes")["kubernetes/alpha-volume.yaml"])
    persistent = next(doc for doc in volume if doc["kind"] == "PersistentVolume")
    assert persistent["spec"]["local"]["path"] == "/var/lib/warm-slots/alpha"
    # A runtime that needs a value the shared file does not hold names the field.
    with pytest.raises(CannotRun, match=r"kubernetes needs namespace"):
        render_runtime(config(CONFIG_TEXT.replace('namespace = "ci"\n', "")), "kubernetes")
    with pytest.raises(CannotRun, match=r"ssh needs pool\.host and pool beta"):
        render_runtime(config(CONFIG_TEXT.replace('host = "beta.example.invalid"\n', "")), "ssh")
    with pytest.raises(CannotRun, match="not one of"):
        render_runtime(config(), "nomad")
    # The command renders into a directory.
    path = tmp_path / "slots.toml"
    path.write_text(CONFIG_TEXT, encoding="utf-8")
    assert (
        run_gate("warm-slots", ["render", "--config", str(path), "--runtime", "ssh", "--out", str(tmp_path / "out")])
        == 0
    )
    assert (tmp_path / "out" / "ssh" / "alpha.env").is_file()
    assert run_gate("warm-slots", ["render", "--config", str(path), "--runtime", "nomad"]) == 2
