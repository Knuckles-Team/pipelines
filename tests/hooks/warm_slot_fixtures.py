"""Shared fixtures for the warm slot tests: one configuration, one repository's pins."""

from __future__ import annotations

from pathlib import Path

from pipelines_hooks.ci.warm_slots.config import SlotConfig, parse_config
import tomllib

CONFIG_TEXT = """
runtime = "kubernetes"
namespace = "ci"
repository_url = "https://example.invalid/org/repo"
prime_command = "cargo nextest run --no-run"
jobs_per_slot = 8

[image]
reference = "registry.example.invalid/warm-slot:1.96.0-py3.14"
rust_channel = "1.96.0"
rust_components = ["clippy", "rustfmt"]
python = "3.14"
nextest = "0.9.100"
sccache = "0.10.0"

[[pool]]
name = "alpha"
slots = 2
cache_root = "/var/lib/warm-slots/alpha"
cache_budget_gb = 200
auto_select = true
cache_filesystem = "ext4"
node = "node-a"
host = "alpha.example.invalid"

[[pool]]
name = "beta"
slots = 1
cache_root = "/var/lib/warm-slots/beta"
cache_budget_gb = 120
auto_select = false
cache_filesystem = "xfs"
node = "node-b"
host = "beta.example.invalid"

[budgets]
warm_check_seconds = 60
cold_prime_seconds = 900
pr_wall_seconds = 1200
"""


def config(text: str = CONFIG_TEXT) -> SlotConfig:
    return parse_config(tomllib.loads(text))


def repository(
    root: Path, *, channel: str = "1.96.0", components: str = '["clippy", "rustfmt"]', python: str = "3.14"
) -> Path:
    """A repository root carrying the toolchain pins."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "rust-toolchain.toml").write_text(
        f'[toolchain]\nchannel = "{channel}"\nprofile = "minimal"\ncomponents = {components}\n', encoding="utf-8"
    )
    (root / ".python-version").write_text(f"{python}\n", encoding="utf-8")
    return root
