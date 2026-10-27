"""PIPE-RELEASE-R006.7--R006.8: static version inventory completeness."""

from __future__ import annotations

import pytest

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.release.project_version import (
    VERSION_DISCOVERY_POLICY,
    VERSION_FILE_SELECTOR,
    check_inventory,
    compare_version_inventory,
    discover_version_locations,
    parse_inventory,
    require_complete_version_inventory,
)

VERSION = "1.2.3"
CONFIG = f"""[bumpversion]
current_version = {VERSION}
commit = False
tag = False

[bumpversion:file(metadata):pyproject.toml]
search = version = \"{{current_version}}\"
replace = version = \"{{new_version}}\"

[bumpversion:file(source):pkg/version.py]
search = __version__ = \"{{current_version}}\"
replace = __version__ = \"{{new_version}}\"

[bumpversion:file(documentation):README.md]
search = <!-- project-version: {{current_version}} -->
replace = <!-- project-version: {{new_version}} -->
"""
VERSION_CONFIG = (
    CONFIG
    + f"""
[bumpversion:file(source):VERSION]
selector = {VERSION_FILE_SELECTOR}
search = {{current_version}}
replace = {{new_version}}
"""
)


def _inventory():
    return parse_inventory(CONFIG, config_digest="sha256:config", snapshot="tree:fixture")


def _version_inventory():
    return parse_inventory(VERSION_CONFIG, config_digest="sha256:version-config", snapshot="tree:fixture")


def _contents() -> dict[str, str]:
    return {
        ".config/bumpversion.cfg": CONFIG,
        "pyproject.toml": f'[project]\nname = "fixture"\nversion = "{VERSION}"\n',
        "pkg/version.py": f'__version__ = "{VERSION}"\n',
        "README.md": f"# fixture\n<!-- project-version: {VERSION} -->\n",
        "vendor/VERSION": "9.9.9\n",
        "docs/history.md": "Released 9.9.9 before the current project version.\n",
    }


def _version_contents() -> dict[str, str]:
    contents = _contents()
    contents["VERSION"] = f"{VERSION}\n"
    return contents


# spec: PIPE-RELEASE-R006.7
def test_version_inventory_completeness_model() -> None:
    discovered = discover_version_locations(_contents(), first_party_roots=("pkg",))
    assert VERSION_DISCOVERY_POLICY == "project-version-inventory/v1"
    assert _inventory().policy_version == VERSION_DISCOVERY_POLICY
    assert [(item.role, item.path, item.selector, item.value, item.line) for item in discovered] == [
        ("documentation", "README.md", "documentation.project-version", VERSION, 2),
        ("metadata", "pyproject.toml", "project.version", VERSION, 3),
        ("source", "pkg/version.py", "module.__version__", VERSION, 1),
    ]
    report = compare_version_inventory(_inventory(), discovered)
    assert report.complete
    assert report.unmapped == ()
    assert report.missing == ()
    assert report.selector_mismatch == ()
    assert report.value_mismatch == ()

    owned_inventory = _version_inventory()
    owned_discovered = discover_version_locations(
        _version_contents(), first_party_roots=("pkg",), inventory=owned_inventory
    )
    assert ("source", "VERSION", VERSION_FILE_SELECTOR, VERSION, 1) in [
        (item.role, item.path, item.selector, item.value, item.line) for item in owned_discovered
    ]
    assert all(item.path != "vendor/VERSION" for item in owned_discovered)
    owned_report = compare_version_inventory(owned_inventory, owned_discovered)
    assert owned_report.complete
    assert owned_report.policy_version == VERSION_DISCOVERY_POLICY
    owned_checks = check_inventory(owned_inventory, _version_contents())
    assert [(check.path, check.actual) for check in owned_checks if check.path == "VERSION"] == [("VERSION", VERSION)]


# spec: PIPE-RELEASE-R006.8
def test_version_inventory_completeness_refuses_unmapped_and_dynamic_surfaces() -> None:
    contents = _contents()
    contents["pkg/extra.py"] = '__version__ = "1.2.3"\n'
    discovered = discover_version_locations(contents, first_party_roots=("pkg",))
    report = compare_version_inventory(_inventory(), discovered)
    assert [(item.path, item.line) for item in report.unmapped] == [("pkg/extra.py", 1)]
    with pytest.raises(CannotRun, match=r"unmapped discovered locations \(pkg/extra.py:1\)"):
        require_complete_version_inventory(report)

    mismatched = _contents()
    mismatched["pkg/version.py"] = '__version__ = "9.9.9"\n'
    value_report = compare_version_inventory(
        _inventory(), discover_version_locations(mismatched, first_party_roots=("pkg",))
    )
    assert [(item.path, item.value) for item in value_report.value_mismatch] == [("pkg/version.py", "9.9.9")]
    with pytest.raises(CannotRun, match=r"version-mismatch: discovered values differ"):
        require_complete_version_inventory(value_report)

    dynamic = _contents()
    dynamic["pkg/version.py"] = "from build import version\n__version__ = version()\n"
    with pytest.raises(CannotRun, match="dynamic __version__ assignment"):
        discover_version_locations(dynamic, first_party_roots=("pkg",))

    missing_doc = _contents()
    del missing_doc["README.md"]
    missing = compare_version_inventory(
        _inventory(), discover_version_locations(missing_doc, first_party_roots=("pkg",))
    )
    assert [(item.role, item.path) for item in missing.missing] == [("documentation", "README.md")]
