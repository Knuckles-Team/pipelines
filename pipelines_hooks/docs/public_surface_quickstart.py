"""Require an executable install-and-run path in the README Quick start."""

from __future__ import annotations

import re

_FENCED_CODE = re.compile(r"(?ms)^ {0,3}```[^\n]*\n(.*?)^ {0,3}```[ \t]*$")
_INSTALL_PREFIX = (
    r"^\s*(?:[$>]\s*)?(?:"
    r"python(?:\d+(?:\.\d+)?)?\s+-m\s+pip\s+install|pip\d*\s+install|"
    r"uv\s+(?:sync|pip\s+install|tool\s+install)|uvx\b|"
    r"pipx\s+(?:install|run)|cargo\s+(?:install|build)|"
    r"npm\s+(?:install|ci)|pnpm\s+(?:install|i)|yarn\s+(?:install|add)|"
    r"bun\s+(?:install|add)|git\s+clone|docker\s+(?:pull|build)|"
    r"docker\s+compose\s+(?:build|up)|helm\s+install|kubectl\s+apply|"
    r"brew\s+install|make\s+install)(?:\s|$)"
)
_RUN_PREFIX = (
    r"^\s*(?:[$>]\s*)?(?:"
    r"uv\s+run|uvx\b|python(?:\d+(?:\.\d+)?)?\s+-m\s+(?!pip\b)[A-Za-z_]"
    r"|cargo\s+run|npm\s+run|pnpm\s+(?:run|dev|start)|"
    r"yarn\s+(?:run|dev|start)|bun\s+(?:run|dev|start)|"
    r"docker\s+run|docker\s+compose\s+up|helm\s+install|kubectl\s+apply|"
    r"pre-commit\s+run|pipelines-hook\b|(?:{project})\b)"
)


def _project_pattern(repository: str, distribution: str | None) -> str:
    names = {repository.rsplit("/", 1)[-1].lower()}
    if distribution:
        names.add(distribution.lower())
    tokens = [re.escape(name).replace(r"\-", r"[-_]") for name in sorted(names)]
    return "(?:" + "|".join(tokens) + ")"


def _quick_start_commands(section: str) -> list[str]:
    return [
        line.strip().removeprefix("$ ").removeprefix("> ")
        for block in _FENCED_CODE.findall(section)
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def findings(section: str | None, *, repository: str, distribution: str | None) -> list[str]:
    """Find a missing fenced install or run command in the Quick start section."""
    if section is None:
        return ["README.md must contain one Quick start section"]
    commands = _quick_start_commands(section)
    install_pattern = re.compile(_INSTALL_PREFIX, re.IGNORECASE)
    run_pattern = re.compile(
        _RUN_PREFIX.format(project=_project_pattern(repository, distribution)),
        re.IGNORECASE,
    )
    segments = [
        segment.strip()
        for command in commands
        for segment in re.split(r"\s*(?:&&|;|\|\|)\s*", command)
    ]
    has_install = any(install_pattern.search(segment) for segment in segments)
    has_run = any(run_pattern.search(segment) for segment in segments)
    missing = []
    if not has_install:
        missing.append("an install/setup command")
    if not has_run:
        missing.append("a run command")
    if missing:
        return [
            "README.md Quick start must include a fenced minimal install/run path; missing "
            + " and ".join(missing)
        ]
    return []
