"""Constrain pip's resolver transport before it inspects any candidate.

Executed only with an isolated interpreter in a disposable venv. The pip
interfaces used here are checked by offline integration tests; missing interfaces
are fatal. Never use this module as a general-purpose package installer.
"""

from __future__ import annotations

import os
import json
import re
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from pip._internal.cli.main import main
from pip._internal.network.session import PipSession
from pip._internal.operations.prepare import RequirementPreparer
from pip._internal.utils.urls import url_to_path

PUBLIC_HOSTS = {"pypi.org", "files.pythonhosted.org"}


def public_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in PUBLIC_HOSTS
        and parsed.port in (None, 443)
        and parsed.username is None
        and parsed.password is None
    )


def local_wheel_path(url: str) -> Path:
    parsed = urlsplit(url)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost") or parsed.query or parsed.fragment:
        raise ValueError("only local file URLs may identify the root wheel")
    # pip owns platform-specific drive decoding; urlsplit().path alone is wrong
    # for file:///C:/ on Windows. Never allow its supported UNC expansion here.
    decoded = url_to_path(url)
    if decoded.startswith(("\\\\", "//")):
        raise ValueError("UNC paths cannot identify the root wheel")
    path = Path(decoded)
    if not path.is_absolute():
        raise ValueError("root wheel URL must be absolute")
    return path.resolve()


def canonicalize_name(name: str) -> str:
    """PEP 503 normalized distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def source_builds() -> frozenset[str]:
    """Exact names the caller's declared allowance may build from source."""
    raw = os.environ.get("READINESS_SOURCE_BUILDS", "")
    return frozenset(canonicalize_name(name) for name in raw.split(",") if name)


def constrain(root: Path | None) -> None:
    request = PipSession.request
    prepare = RequirementPreparer.prepare_linked_requirement
    allowed = source_builds()

    def public_request(self, method, url, *args, **kwargs):
        if not public_url(url):
            raise ValueError("release resolution attempted a non-public URL")
        # Do not allow requests to follow an unchecked Location header.
        kwargs["allow_redirects"] = False
        response = request(self, method, url, *args, **kwargs)
        if 300 <= response.status_code < 400:
            raise ValueError("redirects are not accepted as release evidence")
        return response

    def wheel_only(self, req, *args, **kwargs):
        link = req.link
        sdist_allowed = link is not None and not link.is_wheel and canonicalize_name(req.name or "") in allowed
        if link is None or req.editable or not (link.is_wheel or sdist_allowed):
            raise ValueError("release resolution requires non-editable wheels")
        if sdist_allowed and link.is_file:
            raise ValueError("allowed source builds must come from the public index")
        if link.is_file:
            path = local_wheel_path(link.url)
            if path != root or not req.user_supplied:
                raise ValueError("only the exact root wheel may be local")
        elif not public_url(link.url) or req.is_direct:
            raise ValueError("direct URL or non-public dependency candidate")
        return prepare(self, req, *args, **kwargs)

    def no_editable(*args, **kwargs):
        raise ValueError("editable dependencies cannot prove release readiness")

    RequirementPreparer.prepare_editable_requirement = no_editable
    PipSession.request = public_request
    RequirementPreparer.prepare_linked_requirement = wheel_only


def run(arguments: list[str], root: Path | None) -> int:
    pin = json.loads(Path(__file__).with_name("resolver-pin.json").read_text())
    if version("pip") != pin["version"]:
        raise ValueError("release readiness requires the reviewed resolver version")
    constrain(root)
    return main(arguments)


if __name__ == "__main__":
    import sys

    root = os.environ.get("READINESS_ROOT_WHEEL")
    raise SystemExit(run(sys.argv[1:], Path(root).resolve() if root else None))
