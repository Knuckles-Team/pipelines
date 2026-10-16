"""The neutral package-author gate accepts the PyPI-valid role address."""

from pathlib import Path

from pipelines_hooks.privacy.classify import author_metadata_lines


def _lines(email: str) -> list[int]:
    text = f'[[project.authors]]\nname = "Repository Maintainers"\nemail = "{email}"\n'
    return author_metadata_lines(Path("pyproject.toml"), text.splitlines())


def test_role_address_and_placeholder_are_neutral() -> None:
    assert _lines("maintainers@knuckles.team") == []
    assert _lines("maintainers@example.invalid") == []


def test_other_addresses_are_flagged() -> None:
    assert _lines("someone@knuckles.team") == [3]
    assert _lines("person@gmail.com") == [3]
