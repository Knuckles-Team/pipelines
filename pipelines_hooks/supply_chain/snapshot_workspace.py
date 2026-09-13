"""Read the provider branch of the repository-manager workspace (source-snapshot mode)."""

from __future__ import annotations

import re
import stat
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun

EXPECTED_SNAPSHOT_PROVIDERS = 71
MAX_WORKSPACE_BYTES = 2 * 1024 * 1024
_PROVIDER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_KEY_RE = re.compile(r"^( *)([A-Za-z0-9_-]+):\s*(?:#.*)?$")
_URL_RE = re.compile(r"^( *)-\s+url:\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s#]+))\s*(?:#.*)?$")
_PROVIDER_CONTEXT = ("subdirectories", "agent-packages", "subdirectories", "agents", "repositories")


def _read(workspace: Path) -> str:
    try:
        metadata = workspace.lstat()
        text = workspace.read_text(encoding="utf-8") if stat.S_ISREG(metadata.st_mode) else None
    except (OSError, UnicodeError):
        raise CannotRun("snapshot workspace is unavailable") from None
    if text is None:
        raise CannotRun("snapshot workspace must be a regular file")
    if metadata.st_size > MAX_WORKSPACE_BYTES or len(text.encode("utf-8")) > MAX_WORKSPACE_BYTES:
        raise CannotRun("snapshot workspace exceeds the safe bound")
    return text


def _provider_name(url: str) -> str:
    if len(url) > 2_048 or any(ord(char) < 32 for char in url):
        raise CannotRun("snapshot workspace contains an invalid provider URL")
    name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    if _PROVIDER_NAME_RE.fullmatch(name) is None:
        raise CannotRun("snapshot workspace contains an invalid provider name")
    return name


def _url_under_providers(line: str, stack: list[tuple[int, str]]) -> str | None:
    url = _URL_RE.fullmatch(line)
    if url is None or tuple(value for _, value in stack) != _PROVIDER_CONTEXT:
        return None
    return next(value for value in url.groups()[1:] if value is not None)


def _provider_urls(text: str) -> list[str]:
    """URLs whose enclosing key path is exactly the provider repositories branch."""
    if "\t" in text:
        raise CannotRun("snapshot workspace contains invalid indentation")
    stack: list[tuple[int, str]] = []
    urls = []
    for line in text.splitlines():
        key = _KEY_RE.fullmatch(line)
        if key is not None:
            stack = [entry for entry in stack if entry[0] < len(key.group(1))] + [(len(key.group(1)), key.group(2))]
        elif (url := _url_under_providers(line, stack)) is not None:
            urls.append(url)
    return urls


def workspace_provider_names(workspace: Path) -> tuple[str, ...]:
    """Exactly the declared providers; a wrong count or a duplicate fails closed."""
    providers = [_provider_name(url) for url in _provider_urls(_read(workspace))]
    if len(providers) != EXPECTED_SNAPSHOT_PROVIDERS:
        raise CannotRun("snapshot workspace provider count is not exact")
    if len(providers) != len(set(providers)):
        raise CannotRun("snapshot workspace contains duplicate providers")
    return tuple(sorted(providers))
