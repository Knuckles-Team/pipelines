"""Verify source-build prerequisite reports against the exact archive metadata."""
from __future__ import annotations

from urllib.parse import urlsplit


def package(guard, item: dict, context: dict) -> tuple[str, dict]:
    data = item["metadata"]
    name = guard.canonicalize_name(data["name"])
    guard.require(not item.get("is_direct", False), "source build prerequisite is a direct source")
    download = item["download_info"]
    url = urlsplit(download["url"])
    guard.require(url.scheme == "https" and url.hostname == "files.pythonhosted.org"
                  and url.port in (None, 443) and url.username is None and url.password is None,
                  "source build prerequisite is not public")
    guard.require(url.path.endswith(".whl"), "source build prerequisite is not a wheel")
    digest = download["archive_info"]["hashes"].get("sha256", "")
    guard.require(bool(guard.re.fullmatch(r"[0-9a-f]{64}", digest)), "source build prerequisite hash missing")
    guard.require(guard.Version(context["environment"]["python_full_version"])
                  in guard.SpecifierSet(data.get("requires_python", "")), "source prerequisite interpreter mismatch")
    for raw in data.get("requires_dist", []):
        guard.require(guard.Requirement(raw).url is None, "transitive direct source build prerequisite")
    if name == "pip":
        guard.require(data["version"] == guard.sibling("bootstrap").PIN["version"], "source build replaces pinned resolver")
    return name, data


def validate(guard, requirements: list[str], report: dict | None, context: dict) -> None:
    if not requirements:
        guard.require(report is None, "unexpected prerequisite proof for dependency-free source backend")
        return
    guard.require(isinstance(report, dict), "source build prerequisite proof is missing")
    guard.require(report.get("version") == "1", "source build prerequisite report unsupported")
    guard.require(report.get("pip_version") == guard.sibling("bootstrap").PIN["version"], "source build resolver changed")
    guard.require(report.get("environment") == context["environment"], "source build marker context changed")
    guard.require(isinstance(report.get("install"), list), "source build install report missing")
    packages = {}
    for item in report["install"]:
        name, metadata = package(guard, item, context)
        guard.require(name not in packages, "duplicate source build prerequisite")
        packages[name] = metadata
    for raw in requirements:
        requirement = guard.Requirement(raw)
        guard.require(requirement.url is None, "declared source build prerequisite is a direct source")
        if requirement.marker and not requirement.marker.evaluate({**context["environment"], "extra": ""}):
            continue
        name = guard.canonicalize_name(requirement.name)
        guard.require(name in packages, "source build prerequisite absent from public proof")
        guard.require(guard.Version(packages[name]["version"]) in requirement.specifier, "source build prerequisite version mismatch")
        for extra in {"", *requirement.extras}:
            guard.check_closure(packages, name, "base", context["environment"], root_extra=extra)
