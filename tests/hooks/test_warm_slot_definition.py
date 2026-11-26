"""The warm slot definition check (PIPE-GATES-R070)."""

from __future__ import annotations

import pytest
from pipelines_hooks.ci.warm_slots.definition import DEFAULT_CONFIG, check_definition
from pipelines_hooks.cli import run_gate

from tests.hooks.warm_slot_fixtures import CONFIG_TEXT, config, repository


@pytest.mark.spec("PIPE-GATES-R070")
def test_the_image_matches_the_repository_toolchain_pins(tmp_path) -> None:
    root = repository(tmp_path / "repo")
    assert check_definition(root, config()) == []
    drift = repository(tmp_path / "drift", channel="1.97.0", components='["rustfmt"]', python="3.13")
    findings = check_definition(drift, config())
    assert any("rust channel 1.96.0 differs from the repository pin 1.97.0" in f for f in findings)
    assert any("rust components" in f for f in findings)
    assert any("python 3.14 differs from the repository pin 3.13" in f for f in findings)
    unpinned = CONFIG_TEXT.replace('nextest = "0.9.100"', 'nextest = "latest"')
    assert any("nextest is not pinned" in f for f in check_definition(root, config(unpinned)))


@pytest.mark.spec("PIPE-GATES-R070")
def test_a_cache_path_inside_the_checkout_fails(tmp_path) -> None:
    root = repository(tmp_path / "repo")
    inside = CONFIG_TEXT.replace('"/var/lib/warm-slots/alpha"', f'"{root}/target-cache"')
    findings = check_definition(root, config(inside))
    assert findings == [f"pool alpha: cache path {root}/target-cache sits inside the checkout"]
    relative = CONFIG_TEXT.replace('"/var/lib/warm-slots/beta"', '"cache/beta"')
    assert any("must be absolute" in f for f in check_definition(root, config(relative)))


@pytest.mark.spec("PIPE-GATES-R070")
def test_a_network_filesystem_cache_fails(tmp_path, capsys) -> None:
    root = repository(tmp_path / "repo")
    shared = CONFIG_TEXT.replace('cache_filesystem = "ext4"', 'cache_filesystem = "nfs4"')
    assert check_definition(root, config(shared)) == [
        "pool alpha: cache path /var/lib/warm-slots/alpha is on a network filesystem (nfs4)"
    ]
    undeclared = CONFIG_TEXT.replace('cache_filesystem = "xfs"\n', "")
    assert any("not declared" in f for f in check_definition(root, config(undeclared)))
    (root / ".config").mkdir()
    (root / DEFAULT_CONFIG).write_text(shared, encoding="utf-8")
    assert run_gate("warm-slot-definition", ["--root", str(root)]) == 1
    assert "network filesystem" in capsys.readouterr().out
    (root / DEFAULT_CONFIG).write_text(CONFIG_TEXT, encoding="utf-8")
    assert run_gate("warm-slot-definition", ["--root", str(root)]) == 0
