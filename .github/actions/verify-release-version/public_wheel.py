"""Bind a published pure-Python package payload to reviewed container source."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from zipfile import ZipFile

MODULE_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")


def _reviewed_connector_metadata(root: Path) -> tuple[dict[str, object], list[str]]:
    """Read connector identity from the immutable reviewed tree."""
    pyproject = subprocess.check_output(["git", "show", "HEAD:pyproject.toml"], cwd=root, text=False)
    try:
        document = tomllib.loads(pyproject.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError("Reviewed pyproject.toml is not valid UTF-8 TOML") from error
    sources = [
        path
        for path in subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=root, text=True
        ).splitlines()
        if Path(path).name == "connector_sources.py"
    ]
    return document, sources


def _connector_modules(document: dict[str, object], sources: list[str]) -> set[str]:
    points = document.get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
    modules: set[str] = set()
    if isinstance(points, dict):
        for value in points.values():
            if isinstance(value, str):
                candidate = value.split(":", 1)[0].strip()
                if MODULE_RE.fullmatch(candidate):
                    modules.add(candidate)
    for path in sources:
        if Path(path).name == "connector_sources.py":
            candidate = ".".join(Path(path).with_suffix("").parts[:-1])
            if MODULE_RE.fullmatch(candidate):
                modules.add(candidate)
    return modules


def reviewed_identity(root: Path, distribution: str = "", module: str = "") -> dict[str, object]:
    """Resolve a connector's distribution and package module from reviewed HEAD."""
    document, sources = _reviewed_connector_metadata(root)
    project = document.get("project", {})
    points = project.get("entry-points", {}).get("agent_connector_sdk.connector", {})
    connector = (isinstance(points, dict) and bool(points)) or bool(sources)
    if not connector:
        return {"connector": False}
    project_distribution = project.get("name")
    resolved_distribution = distribution or project_distribution
    if not isinstance(resolved_distribution, str) or not resolved_distribution:
        raise ValueError("Connector project metadata has no distribution name")
    if module:
        if not MODULE_RE.fullmatch(module):
            raise ValueError("Package module must be an explicit dotted Python package")
        resolved_module = module
    else:
        modules = _connector_modules(document, sources)
        if len(modules) != 1:
            raise ValueError("Connector package module is ambiguous; pass an explicit module")
        resolved_module = next(iter(modules))
    return {"connector": True, "distribution": resolved_distribution, "module": resolved_module}


def reviewed_target_extra(root: Path, target: str = "mcp") -> str:
    """Resolve the package extra selected by the reviewed renderer target.

    This intentionally shares the provider renderer's metadata selector so a connector
    whose MCP support is supplied by a base dependency can select the bare package.
    ``install_extras`` remains authoritative for an explicit per-target selection.
    """
    if not MODULE_RE.fullmatch(target):
        raise ValueError("Container target must be an explicit stage name")
    document, _ = _reviewed_connector_metadata(root)
    project = document.get("project", {})
    optional = project.get("optional-dependencies", {})
    extras = set(optional) if isinstance(optional, dict) else set()
    table = document.get("tool", {}).get("pipelines", {}).get("container", {})
    if not isinstance(table, dict):
        raise ValueError("Reviewed container metadata is not a table")
    try:
        provider_root = Path(__file__).resolve().parents[3]
        if not (provider_root / "pipelines_hooks" / "connector" / "container.py").is_file():
            raise ValueError("Generated Dockerfile verification requires the provider renderer checkout")
        sys.path.insert(0, str(provider_root))
        from pipelines_hooks.connector.container import target_extra

        extra = target_extra(extras, table, target)
    except (ImportError, KeyError, TypeError) as error:
        raise ValueError("Reviewed container metadata cannot select a target extra") from error
    finally:
        if sys.path and sys.path[0] == str(provider_root):
            sys.path.pop(0)
    return extra or ""


def _source_epoch(root: Path) -> str:
    """Resolve the epoch used by the immutable source publisher."""
    value = os.environ.get("SOURCE_DATE_EPOCH", "")
    if value:
        if not value.isdigit():
            raise ValueError("SOURCE_DATE_EPOCH must be an integer")
        return value
    value = subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], cwd=root, text=True).strip()
    if not value.isdigit():
        raise ValueError("Reviewed source commit has no usable publication epoch")
    return value


def _wheel_payload(wheel: Path, module: str) -> dict[str, bytes]:
    """Read the package boundary emitted by the real publisher."""
    prefix = module.replace(".", "/") + "/"
    with ZipFile(wheel) as archive:
        entries = [name for name in archive.namelist() if name.startswith(prefix) and not name.endswith("/")]
        if len(entries) != len(set(entries)):
            raise ValueError("Reviewed source wheel contains duplicate package entries")
        if not entries:
            raise ValueError("Reviewed source wheel package is empty")
        return {name: archive.read(name) for name in entries}


def _published_payload(root: Path, module: str) -> dict[str, bytes]:
    """Build the immutable reviewed source through the public package boundary.

    The release workflow runs ``uv build`` after connector generation.  Repeating that
    command against a ``git archive HEAD`` checkout makes setuptools/package-data (or any
    other reviewed backend) decide which files are public.  A generated artifact already
    tracked by the source tree is restored after generation so a new caller epoch cannot
    replace historical published bytes.
    """
    document, sources = _reviewed_connector_metadata(root)
    points = document.get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
    connector = (isinstance(points, dict) and bool(points)) or bool(sources)

    provider_root = Path(__file__).resolve().parents[3]
    generator = provider_root / "pipelines_hooks" / "connector" / "generate.py"
    if connector and not generator.is_file():
        raise ValueError("Generated wheel verification requires the provider generator checkout")
    uv = shutil.which("uv")
    if uv is None:
        raise ValueError("Published wheel verification requires the uv publisher")
    prefix = module.replace(".", "/") + "/"
    tracked_files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", prefix], cwd=root, text=True
    ).splitlines()
    if not tracked_files:
        raise ValueError("Reviewed package payload is empty")
    tracked = {name: subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=root) for name in tracked_files}
    epoch = _source_epoch(root)
    with tempfile.TemporaryDirectory(prefix="public-wheel-source-") as directory:
        source = Path(directory)
        archive = subprocess.check_output(["git", "archive", "HEAD"], cwd=root)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(source, filter="data")
        package = source / module.replace(".", "/")
        old_epoch = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = epoch
        try:
            if connector and (package / "ontology" / "mappings" / "source.yaml").is_file():
                sys.path.insert(0, str(provider_root))
                try:
                    from pipelines_hooks.connector import generate

                    generated = generate.generate(source)
                except Exception as error:
                    raise ValueError("Reviewed connector ontology generation failed") from error
                finally:
                    sys.path.pop(0)
                for path, text in generated.items():
                    try:
                        name = path.relative_to(source).as_posix()
                    except ValueError as error:
                        raise ValueError("Generated connector artifact is outside the reviewed source") from error
                    if not name.startswith(prefix):
                        raise ValueError("Generated connector artifact is outside the reviewed package")
                    if name in tracked:
                        path.write_bytes(tracked[name])
                    else:
                        path.write_text(text, encoding="utf-8")

            dist = source / "dist"
            if dist.exists():
                shutil.rmtree(dist)
            result = subprocess.run(
                [uv, "build", "--wheel", "--no-create-gitignore"],
                cwd=source,
                env=os.environ.copy(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()
                raise ValueError(f"Reviewed source wheel build failed: {detail[-1000:]}")
            wheels = sorted(dist.glob("*.whl"))
            if len(wheels) != 1:
                raise ValueError("Reviewed source wheel build must produce exactly one wheel")
            return _wheel_payload(wheels[0], module)
        finally:
            if old_epoch is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = old_epoch


def reviewed_payload(root: Path, module: str) -> dict[str, bytes]:
    if not MODULE_RE.fullmatch(module):
        raise ValueError("Package module must be an explicit dotted Python package")
    return _published_payload(root, module)


def verify_payload(data: bytes, digest: str, expected: dict[str, bytes], module: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Public wheel digest differs from the PyPI receipt")
    prefix = module.replace(".", "/") + "/"
    with ZipFile(io.BytesIO(data)) as wheel:
        entries = [name for name in wheel.namelist() if name.startswith(prefix) and not name.endswith("/")]
        if len(entries) != len(set(entries)) or set(entries) != expected.keys():
            raise ValueError("Public wheel package inventory differs from reviewed source")
        for name in entries:
            if wheel.read(name) != expected[name]:
                raise ValueError(f"Public wheel payload differs from reviewed source: {name}")


def read_public(url: str) -> bytes:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in {"pypi.org", "files.pythonhosted.org"}:
        raise ValueError("Wheel evidence must come from the public PyPI hosts over HTTPS")
    with urlopen(url, timeout=30) as response:
        return response.read()


def _rendered_dockerfile(root: Path) -> str:
    """Render the canonical Dockerfile from the reviewed ``HEAD`` metadata."""
    provider_root = Path(__file__).resolve().parents[3]
    if not (provider_root / "pipelines_hooks" / "connector" / "container.py").is_file():
        raise ValueError("Generated Dockerfile verification requires the provider renderer checkout")
    sys.path.insert(0, str(provider_root))
    try:
        from pipelines_hooks.connector.container import render
    finally:
        sys.path.pop(0)

    with tempfile.TemporaryDirectory(prefix="public-wheel-source-") as directory:
        source = Path(directory)
        pyproject = subprocess.check_output(
            ["git", "show", "HEAD:pyproject.toml"], cwd=root, text=False, stderr=subprocess.DEVNULL
        )
        try:
            document = tomllib.loads(pyproject.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise ValueError("Generated Dockerfile verification requires readable reviewed pyproject.toml") from error
        points = document.get("project", {}).get("entry-points", {}).get("agent_connector_sdk.connector", {})
        tracked_sources = [
            path
            for path in subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=root, text=True
            ).splitlines()
            if Path(path).name == "connector_sources.py"
        ]
        if (not isinstance(points, dict) or not points) and not any(
            Path(path).name == "connector_sources.py" for path in tracked_sources
        ):
            raise ValueError("Generated Dockerfile verification requires a connector identity")
        (source / "pyproject.toml").write_bytes(pyproject)
        return render(source)["Dockerfile"]


def _reviewed_dockerfile(root: Path, dockerfile: str) -> str:
    """Read a tracked Dockerfile or the provider-rendered canonical one."""
    try:
        return subprocess.check_output(
            ["git", "show", f"HEAD:{dockerfile}"], cwd=root, text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as error:
        if dockerfile != "docker/Dockerfile":
            raise ValueError(f"Reviewed Dockerfile is not tracked: {dockerfile}") from error
        return _rendered_dockerfile(root)


def verify_release(root: Path, distribution: str, module: str, dockerfile: str, extras: str) -> dict[str, object]:
    project = tomllib.loads(subprocess.check_output(["git", "show", "HEAD:pyproject.toml"], cwd=root, text=True))[
        "project"
    ]
    if project["name"] != distribution:
        raise ValueError("Explicit distribution differs from reviewed project metadata")
    version = project["version"]
    suffix = f"[{extras}]" if extras else ""
    pin = f"{distribution}{suffix}=={version}"
    docker = _reviewed_dockerfile(root, dockerfile)
    if pin not in shlex.split(docker, comments=True):
        raise ValueError("Dockerfile must pin the reviewed package version")
    expected = reviewed_payload(root, module)
    metadata = json.loads(read_public(f"https://pypi.org/pypi/{distribution}/{version}/json"))
    wheels = [item for item in metadata["urls"] if item["filename"].endswith("-py3-none-any.whl")]
    if len(wheels) != 1:
        raise ValueError("Exactly one public pure-Python wheel is required")
    item = wheels[0]
    digest = item["digests"]["sha256"]
    verify_payload(read_public(item["url"]), digest, expected, module)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    return {
        "package": distribution,
        "module": module,
        "version": version,
        "source_revision": revision,
        "wheel_sha256": digest,
        "verified_payload_files": len(expected),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--distribution", default="")
    parser.add_argument("--module", default="")
    parser.add_argument("--dockerfile", default="docker/Dockerfile")
    parser.add_argument("--extras", default="mcp")
    parser.add_argument("--target", default="mcp")
    parser.add_argument("--resolve-identity", action="store_true")
    parser.add_argument("--resolve-extras", action="store_true")
    args = parser.parse_args()
    if args.resolve_identity:
        print(json.dumps(reviewed_identity(args.root, args.distribution, args.module), sort_keys=True))
        return
    if args.resolve_extras:
        print(reviewed_target_extra(args.root, args.target))
        return
    if not args.distribution or not args.module:
        parser.error("--distribution and --module are required unless --resolve-identity is used")
    print(
        json.dumps(
            verify_release(args.root, args.distribution, args.module, args.dockerfile, args.extras), sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
