"""Closed target set for the existing Maturin publication matrix."""
from __future__ import annotations

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
        "python_full_version": interpreter["version"],
        "python_version": "3.13",
    }
    if any(environment.get(key) != value for key, value in expected.items()):
        raise ValueError("target marker environment disagrees with interpreter")
    if not context["tags"] or len(context["tags"]) != len(set(context["tags"])):
        raise ValueError("target wheel compatibility tags missing or duplicated")
