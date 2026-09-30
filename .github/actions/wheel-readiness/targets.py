"""Closed target set for the existing Maturin publication matrix."""
from __future__ import annotations

import re

TARGETS = {
    "linux-x86_64": ("linux", {"x86_64"}),
    "linux-aarch64": ("linux", {"aarch64"}),
    "macos-aarch64": ("darwin", {"arm64", "aarch64"}),
    "windows-x86_64": ("win32", {"amd64", "x86_64"}),
}


def validate(target: str, context: dict) -> None:
    if target not in TARGETS:
        raise ValueError("unknown release target")
    expected_os, machines = TARGETS[target]
    interpreter = context["interpreter"]
    environment = context["environment"]
    if interpreter["platform"] != expected_os or interpreter["machine"].lower() not in machines:
        raise ValueError("proof was not produced on the declared target")
    if interpreter["implementation"] != "CPython" or not interpreter["version"].startswith("3.13."):
        raise ValueError("target proof requires CPython 3.13")
    expected = {
        "sys_platform": expected_os,
        "platform_machine": interpreter["machine"],
        "platform_python_implementation": interpreter["implementation"],
        "implementation_name": "cpython",
        "implementation_version": interpreter["version"],
        "os_name": "nt" if expected_os == "win32" else "posix",
        "platform_system": {"linux": "Linux", "darwin": "Darwin", "win32": "Windows"}[expected_os],
        "python_full_version": interpreter["version"],
        "python_version": "3.13",
    }
    if any(environment.get(key) != value for key, value in expected.items()):
        raise ValueError("target marker environment disagrees with interpreter")
    if not context["tags"] or len(context["tags"]) != len(set(context["tags"])):
        raise ValueError("target wheel compatibility tags missing or duplicated")

    validate_tags(target, context["tags"])


def validate_tags(target: str, tags: list[str]) -> None:
    suffixes = {
        "linux-x86_64": r"(?:manylinux(?:_\d+_\d+|1|2010|2014)|linux)_x86_64",
        "linux-aarch64": r"(?:manylinux(?:_\d+_\d+|2014)|linux)_aarch64",
        "macos-aarch64": r"macosx_\d+_\d+_(?:arm64|universal2)",
        "windows-x86_64": r"win_amd64",
    }
    for tag in tags:
        parts = tag.split("-")
        if len(parts) != 3:
            raise ValueError("invalid native compatibility tag")
        implementation, abi, platform = parts
        if platform != "any" and not re.fullmatch(suffixes[target], platform):
            raise ValueError("compatibility tag belongs to another target")
        if platform == "any" and abi != "none":
            raise ValueError("platform-independent tag has a native ABI")
        validate_interpreter_tag(implementation, abi)


def validate_interpreter_tag(implementation: str, abi: str) -> None:
    if implementation == "py3":
        valid = abi == "none"
    elif re.fullmatch(r"py3\d+", implementation):
        valid = int(implementation[2:]) <= 313 and abi == "none"
    elif implementation == "cp313":
        valid = abi in {"cp313", "abi3", "none"}
    elif re.fullmatch(r"cp3\d+", implementation):
        valid = 32 <= int(implementation[2:]) < 313 and abi == "abi3"
    else:
        valid = False
    if not valid:
        raise ValueError("compatibility tag disagrees with CPython 3.13 proof")
