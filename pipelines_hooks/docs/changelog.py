"""changelog: a versioned, dated, categorized changelog checked offline from one Git snapshot.

The ``changelog-v1`` grammar accepts level-two ``## [version] - YYYY-MM-DD``
headings (a single undated ``## [Unreleased]`` first), level-three categories
(Added, Changed, Deprecated, Removed, Fixed, Security), nonempty bullet entries
(``[Breaking]`` marks an incompatible change) and one reference-style link
definition per section. Policy and document are read from the same Git index
snapshot (the staged tree; equal to ``HEAD`` when nothing is staged), so an
unstaged edit never hides staged text. Syntax is checked only: remote
reachability and the completeness of release notes are reported as unverified.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import blob_bytes, git_text, repo_root

GRAMMAR = "changelog-v1"
POLICY_PATH = ".config/changelog.toml"
CATEGORIES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
RULES = ("version", "date", "category", "entry", "link", "duplicate", "order")
DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_MAX_LINES = 20_000
_POLICY_KEYS = {"path", "grammar", "tag_template", "compare_template", "release_template", "max_bytes", "max_lines"}
_NUM = r"(?:0|[1-9][0-9]*)"
_IDENT = r"[0-9A-Za-z-]+"
_PRE = r"(?:-(?:(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)"
VERSION_RE = re.compile(rf"^{_NUM}\.{_NUM}\.{_NUM}{_PRE}?(?:\+{_IDENT}(?:\.{_IDENT})*)?$")
_HEADING_RE = re.compile(r"^## \[(?P<label>[^\]]+)\](?: - (?P<date>\S+))?\s*$")
_LINK_DEF_RE = re.compile(r"^\[(?P<label>[^\]]+)\]:\s*(?P<url>\S*)\s*$")
_TAIL_COMPARE_RE = re.compile(r"/compare/(?P<previous>[^/\s]+)\.\.\.(?P<current>[^/\s]+)$")
_TAIL_RELEASE_RE = re.compile(r"/releases/tag/(?P<tag>[^/\s]+)$")


@dataclass(frozen=True)
class ChangelogPolicy:
    """The declared document path, grammar, tag syntax, URL templates and parser limits."""

    path: str = "CHANGELOG.md"
    grammar: str = GRAMMAR
    tag_template: str = "v{version}"
    compare_template: str | None = None
    release_template: str | None = None
    max_bytes: int = DEFAULT_MAX_BYTES
    max_lines: int = DEFAULT_MAX_LINES

    def __post_init__(self) -> None:
        if self.grammar != GRAMMAR:
            raise CannotRun(f"changelog: unsupported grammar {self.grammar!r}")
        pure = PurePosixPath(self.path)
        if not self.path or pure.is_absolute() or ".." in pure.parts or "\\" in self.path:
            raise CannotRun(f"changelog: unsafe document path {self.path!r}")
        if "{version}" not in self.tag_template:
            raise CannotRun("changelog: tag_template must contain {version}")
        for name, value, fields in (
            ("compare_template", self.compare_template, ("{previous}", "{current}")),
            ("release_template", self.release_template, ("{tag}",)),
        ):
            if value is not None and (not value.startswith("https://") or any(f not in value for f in fields)):
                raise CannotRun(f"changelog: {name} must be an https URL containing {' and '.join(fields)}")
        for name, limit in (("max_bytes", self.max_bytes), ("max_lines", self.max_lines)):
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise CannotRun(f"changelog: {name} must be a positive integer")

    def tag(self, version: str) -> str:
        return self.tag_template.format(version=version)

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "grammar": self.grammar,
            "tag_template": self.tag_template,
            "compare_template": self.compare_template,
            "release_template": self.release_template,
            "max_bytes": self.max_bytes,
            "max_lines": self.max_lines,
        }


@dataclass(frozen=True)
class ReleaseSection:
    """One ``## [version]`` section bound to its source lines."""

    version: str
    line: int
    date: str | None = None
    categories: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    link: str | None = None
    link_line: int | None = None

    @property
    def unreleased(self) -> bool:
        return self.version == "Unreleased"


@dataclass(frozen=True)
class ChangelogFinding:
    """One located grammar violation; ``rule`` is one of :data:`RULES`."""

    path: str
    line: int
    rule: str
    message: str = ""

    def __post_init__(self) -> None:
        if self.rule not in RULES:
            raise ValueError(f"unknown changelog rule {self.rule!r}; expected one of {', '.join(RULES)}")
        if self.line < 1:
            raise ValueError("a changelog finding needs a positive line")

    def render(self) -> str:
        return f"{self.path}:{self.line} {self.rule} {self.message}".rstrip()


def policy_from_mapping(raw: object) -> ChangelogPolicy:
    """A strict policy: unknown fields and wrong types are refused."""
    if not isinstance(raw, dict):
        raise CannotRun("changelog: policy must be a table")
    if unknown := sorted(str(key) for key in set(raw) - _POLICY_KEYS):
        raise CannotRun(f"changelog: policy has unknown field(s): {', '.join(unknown)}")
    return ChangelogPolicy(**raw)


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _index_bytes(root: Path, rel: str) -> bytes | None:
    return blob_bytes(root, f":{rel}")


def _parse(
    policy: ChangelogPolicy, text: str
) -> tuple[list[ReleaseSection], list[ChangelogFinding], dict[str, tuple[int, str]]]:
    path = policy.path
    findings: list[ChangelogFinding] = []
    sections: list[ReleaseSection] = []
    links: dict[str, tuple[int, str]] = {}
    category: str | None = None
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        link = _LINK_DEF_RE.match(line)
        if link:
            label = link.group("label")
            if label in links:
                findings.append(ChangelogFinding(path, number, "duplicate", f"duplicate link definition [{label}]"))
            else:
                links[label] = (number, link.group("url"))
            continue
        heading = _HEADING_RE.match(line)
        if line.startswith("## "):
            category = None
            if not heading:
                findings.append(
                    ChangelogFinding(path, number, "version", "release heading must be ## [version] - YYYY-MM-DD")
                )
                sections.append(ReleaseSection("?", number))
                continue
            label, date = heading.group("label"), heading.group("date")
            sections.append(ReleaseSection(label, number, date))
            continue
        if line.startswith("### "):
            if not sections:
                findings.append(ChangelogFinding(path, number, "category", "category outside a release section"))
                continue
            category = line[4:].strip()
            if category not in CATEGORIES:
                findings.append(ChangelogFinding(path, number, "category", f"unknown category {category!r}"))
            sections[-1].categories.setdefault(category, [])
            continue
        if not sections or not line.strip() or line.startswith("#"):
            continue
        if re.match(r"^[-*] ", line):
            body = line[2:].strip()
            if not sections or category is None:
                findings.append(ChangelogFinding(path, number, "entry", "entry outside a category"))
            elif not body:
                findings.append(ChangelogFinding(path, number, "entry", "empty entry"))
            elif category in sections[-1].categories:
                sections[-1].categories[category].append((number, body))
        elif not line.startswith((" ", "\t")):
            findings.append(ChangelogFinding(path, number, "entry", "text must be a bullet entry inside a category"))
    return sections, findings, links


def _expected_links(policy: ChangelogPolicy, sections: list[ReleaseSection]) -> dict[str, tuple[str, str] | str]:
    """Each section's declared comparison endpoints (previous, current) or its release tag."""
    released = [s for s in sections if not s.unreleased and VERSION_RE.match(s.version)]
    result: dict[str, tuple[str, str] | str] = {}
    for index, section in enumerate(released):
        previous = released[index + 1] if index + 1 < len(released) else None
        result[section.version] = (
            (policy.tag(previous.version), policy.tag(section.version)) if previous else policy.tag(section.version)
        )
    if released and any(s.unreleased for s in sections):
        result["Unreleased"] = (policy.tag(released[0].version), "HEAD")
    return result


def _link_findings(
    policy: ChangelogPolicy, sections: list[ReleaseSection], links: dict[str, tuple[int, str]]
) -> list[ChangelogFinding]:
    findings: list[ChangelogFinding] = []
    expected = _expected_links(policy, sections)
    for section in sections:
        if section.version == "?":
            continue
        if section.version not in links:
            findings.append(
                ChangelogFinding(policy.path, section.line, "link", f"missing link definition [{section.version}]")
            )
            continue
        line, url = links[section.version]
        want = expected.get(section.version)
        if not url.startswith("https://"):
            findings.append(
                ChangelogFinding(policy.path, line, "link", f"link target for [{section.version}] must be an https URL")
            )
        elif isinstance(want, tuple):
            if policy.compare_template:
                ok = url == policy.compare_template.format(previous=want[0], current=want[1])
            else:
                match = _TAIL_COMPARE_RE.search(url)
                ok = bool(match and (match["previous"], match["current"]) == want)
            if not ok:
                findings.append(
                    ChangelogFinding(
                        policy.path, line, "link", f"[{section.version}] must compare {want[0]}...{want[1]}"
                    )
                )
        elif isinstance(want, str):
            if policy.release_template:
                ok = url == policy.release_template.format(tag=want)
            else:
                match = _TAIL_RELEASE_RE.search(url)
                ok = bool(match and match["tag"] == want)
            if not ok:
                findings.append(
                    ChangelogFinding(policy.path, line, "link", f"[{section.version}] must link the {want} release")
                )
    return findings


def check(
    policy: ChangelogPolicy, text: str
) -> tuple[list[ReleaseSection], list[ChangelogFinding], dict[str, tuple[int, str]]]:
    """Grammar findings for one document; a document without a release anchor is refused."""
    if len(text.splitlines()) > policy.max_lines:
        raise CannotRun(f"changelog: {policy.path} exceeds the {policy.max_lines}-line parser limit")
    sections, findings, links = _parse(policy, text)
    released = [s for s in sections if not s.unreleased]
    if not released:
        line = sections[0].line if sections else 1
        raise CannotRun(
            f"changelog: missing-release-anchor at {policy.path}:{line}: no dated release exists to compare against"
        )
    seen: set[str] = set()
    previous_date: str | None = None
    for index, section in enumerate(sections):
        if section.version in seen:
            findings.append(
                ChangelogFinding(policy.path, section.line, "duplicate", f"duplicate release {section.version}")
            )
        seen.add(section.version)
        if section.unreleased:
            if index != 0:
                findings.append(
                    ChangelogFinding(policy.path, section.line, "order", "Unreleased must be the first section")
                )
            if section.date:
                findings.append(ChangelogFinding(policy.path, section.line, "date", "Unreleased carries no date"))
            continue
        if section.version != "?" and not VERSION_RE.match(section.version):
            findings.append(
                ChangelogFinding(policy.path, section.line, "version", f"invalid version {section.version!r}")
            )
        date_ok = False
        if not section.date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", section.date):
            findings.append(ChangelogFinding(policy.path, section.line, "date", "release needs a YYYY-MM-DD date"))
        else:
            try:
                datetime.date.fromisoformat(section.date)
                date_ok = True
            except ValueError:
                findings.append(
                    ChangelogFinding(policy.path, section.line, "date", f"invalid calendar date {section.date}")
                )
        if date_ok and section.date:
            if previous_date and section.date > previous_date:
                findings.append(ChangelogFinding(policy.path, section.line, "order", "releases must descend by date"))
            previous_date = section.date
        if not any(section.categories.values()):
            findings.append(
                ChangelogFinding(policy.path, section.line, "entry", f"release {section.version} has no entries")
            )
        for name, entries in section.categories.items():
            if not entries:
                findings.append(
                    ChangelogFinding(policy.path, section.line, "entry", f"category {name} is empty; omit it")
                )
    findings.extend(_link_findings(policy, sections, links))
    sections = [
        replace(s, link=links[s.version][1], link_line=links[s.version][0]) if s.version in links else s
        for s in sections
    ]
    return sections, sorted(findings, key=lambda f: (f.path, f.line, f.rule, f.message)), links


def _load_policy(root: Path, policy_path: str) -> tuple[ChangelogPolicy, bytes | None]:
    raw = _index_bytes(root, policy_path)
    if raw is None:
        return ChangelogPolicy(), None
    try:
        return policy_from_mapping(tomllib.loads(raw.decode("utf-8"))), raw
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CannotRun(f"changelog: malformed policy {policy_path}: {exc}") from exc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="changelog", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--policy", default=POLICY_PATH, help="repository-relative policy file (TOML)")
    args = parser.parse_args(argv)
    root = repo_root(args.root)
    policy, policy_raw = _load_policy(root, args.policy)
    document = _index_bytes(root, policy.path)
    if document is None:
        raise CannotRun(f"changelog: declared document {policy.path} is absent from the Git snapshot")
    if len(document) > policy.max_bytes:
        raise CannotRun(f"changelog: {policy.path} exceeds the {policy.max_bytes}-byte parser limit")
    try:
        text = document.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CannotRun(f"changelog: {policy.path} is not valid UTF-8: {exc}") from exc
    sections, findings, links = check(policy, text)
    tree = git_text(root, ("write-tree",), preserve_index=True).strip()
    entries = sum(len(items) for section in sections for items in section.categories.values())
    categories = sum(len(section.categories) for section in sections)
    print(
        f"changelog: snapshot index:{tree}, policy {_sha(policy_raw) if policy_raw else 'default'} "
        f"({policy.grammar}), document {_sha(document)}"
    )
    print(
        f"changelog: checked releases {len(sections)}, categories {categories}, entries {entries}, "
        f"links {sum(1 for s in sections if s.version in links)}"
    )
    expected = _expected_links(policy, sections)
    for section in sections:
        want = expected.get(section.version)
        if isinstance(want, tuple):
            print(f"  link [{section.version}] compares {want[0]}...{want[1]}")
        elif want:
            print(f"  link [{section.version}] release {want}")
    print("changelog: unverified: remote link reachability, completeness of release notes")
    for finding in findings:
        print(f"  {finding.render()}")
    return 1 if findings else 0
