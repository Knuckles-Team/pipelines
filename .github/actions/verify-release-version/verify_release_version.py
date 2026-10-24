"""Early release guard: the tag, the package version and PyPI must agree before any build (PIPE-RELEASE-R002)."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?")
BUMP_FILES = (".bumpversion.cfg", ".config/bumpversion.cfg")
PYPI = "https://pypi.org"


class GuardError(ValueError):
    """A release identity disagreement; the message names the fix."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GuardError("PyPI redirect refused")


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise GuardError(f"cannot read {path}: {error}") from error


def package_identity(root: Path) -> tuple[str, str, str]:
    """Return (name, version, where) as the build will stamp them.

    A static ``[project].version`` wins. A dynamic version is the maturin manifest's
    ``[package].version`` (``[tool.maturin] manifest-path``, default ``Cargo.toml``).
    """
    document = read_toml(root / "pyproject.toml")
    project = document.get("project", {})
    name = project.get("name")
    if not isinstance(name, str) or not name:
        raise GuardError("pyproject.toml has no [project].name")
    version = project.get("version")
    if isinstance(version, str):
        return name, version, "pyproject.toml [project].version"
    if "version" not in project.get("dynamic", []):
        raise GuardError("pyproject.toml has neither a static nor a dynamic [project].version")
    manifest = document.get("tool", {}).get("maturin", {}).get("manifest-path", "Cargo.toml")
    cargo = read_toml(root / manifest).get("package", {}).get("version")
    if not isinstance(cargo, str):
        raise GuardError(f"dynamic version needs a literal [package].version in {manifest}")
    return name, cargo, f"{manifest} [package].version"


def bumpversion_current(root: Path) -> tuple[str, str] | None:
    for relative in BUMP_FILES:
        path = root / relative
        if path.is_file():
            match = re.search(r"^\s*current_version\s*=\s*(\S+)\s*$", path.read_text(encoding="utf-8"), re.M)
            if not match:
                raise GuardError(f"{relative} has no current_version")
            return relative, match.group(1)
    return None


def pypi_has_version(name: str, version: str, base: str = PYPI) -> bool:
    url = f"{base.rstrip('/')}/pypi/{quote(name.lower(), safe='')}/{quote(version, safe='')}/json"
    try:
        with build_opener(NoRedirect()).open(Request(url), timeout=20) as response:
            json.loads(response.read(4 * 1024 * 1024))
        return True
    except HTTPError as error:
        if error.code == 404:
            return False
        raise GuardError(f"PyPI lookup failed (HTTP {error.code}); refusing to release unverified") from error
    except (URLError, TimeoutError, ValueError) as error:
        raise GuardError(f"PyPI lookup failed ({error}); refusing to release unverified") from error


def verify(root: Path, ref: str, pypi_base: str = PYPI, *, lookup=pypi_has_version) -> str:
    name, version, where = package_identity(root)
    if VERSION.fullmatch(version) is None:
        raise GuardError(f"{where} is {version!r}, not a release version")
    if ref.startswith("refs/tags/"):
        tag = ref.removeprefix("refs/tags/")
        if tag != f"v{version}":
            raise GuardError(
                f"tag {tag} does not match package version {version} ({where}) at this commit. Bump the version, "
                f"merge it, and tag the merged commit. If nothing was published, delete the tag and re-tag."
            )
    bump = bumpversion_current(root)
    if bump and bump[1] != version:
        raise GuardError(
            f"{bump[0]} current_version {bump[1]} differs from package version {version} ({where}); "
            f"bump both together with the repository's bump command."
        )
    if lookup(name, version, pypi_base):
        raise GuardError(
            f"{name} {version} is already on PyPI; PyPI never accepts a version twice. "
            f"Bump to the next version, merge it, and tag that commit."
        )
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--ref", default="", help="git ref, for example refs/tags/v1.2.3; a non-tag skips the tag check"
    )
    parser.add_argument("--pypi", default=PYPI)
    arguments = parser.parse_args(argv)
    try:
        version = verify(Path(arguments.root), arguments.ref, arguments.pypi)
    except GuardError as error:
        print(f"::error::Release version blocked: {error}", file=sys.stderr)
        return 1
    print(f"Release version verified: {version} (tag, package, bumpversion agree; not on PyPI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
