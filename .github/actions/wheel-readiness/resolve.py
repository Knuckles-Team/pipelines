"""Constrain pip's resolver transport before it inspects any candidate.

Executed only with an isolated interpreter in a disposable venv. The pip
interfaces used here are checked by offline integration tests; missing interfaces
are fatal. Never use this module as a general-purpose package installer.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pip._internal.cli.main import main
from pip._internal.network.session import PipSession
from pip._internal.operations.prepare import RequirementPreparer

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


def constrain(root: Path) -> None:
    request = PipSession.request
    prepare = RequirementPreparer.prepare_linked_requirement

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
        if link is None or not link.is_wheel or req.editable:
            raise ValueError("release resolution requires non-editable wheels")
        if link.is_file:
            path = Path(unquote(urlsplit(link.url).path)).resolve()
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


if __name__ == "__main__":
    import sys

    constrain(Path(os.environ["READINESS_ROOT_WHEEL"]).resolve())
    raise SystemExit(main(sys.argv[1:]))
