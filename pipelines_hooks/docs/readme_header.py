"""readme-header: every consumer README and served documentation home opens with one header.

Declared in ``.config/readme-header.json``: title, a unique versioned project mark (path, version,
digest, alt text), a concise description, the four ordered navigation links (Documentation,
Capabilities, Interfaces, Status) and the telemetry badge inventory with pinned provenance and an
as-of date.  Scope is classified first, from the full ``host/namespace/repository`` identity of
the ``origin`` remote (or the sole remote), read from local git configuration with no network:
the consumers of the ``REPOS`` registry (``scripts/skill_graph/model.py``) validate normally; only
the policy-pinned provider identity is declared non-applicable (structured skip, exit 0, zero
consumer checks).  An unknown or ambiguous identity is exit 2: a basename or a caller flag never
selects the exception.  ``--site DIR`` also checks a built site's home page.
"""

from __future__ import annotations

import argparse
import ast
import posixpath
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root, run_git
from pipelines_hooks.docs.gate_io import Result, finish, load_json, read, require, safe_path, sha, strict_keys

GATE = "readme-header"
DECLARATION = ".config/readme-header.json"
PROVIDER = "github.com/Knuckles-Team/pipelines"
CONSUMER_NAMESPACE = "github.com/Knuckles-Team"
NAV = ("Documentation", "Capabilities", "Interfaces", "Status")
_PROVENANCE = re.compile(r"^pinned:\S+$")
_IMG = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)")
_LINK = re.compile(r"(?<!!)\[(?P<text>[^\]]+)\]\((?P<target>[^)\s]+)\)")
_REGISTRY_FILE = Path(__file__).resolve().parents[2] / "scripts" / "skill_graph" / "model.py"


@dataclass(frozen=True)
class Badge:
    id: str
    label: str
    provenance: str
    as_of: str


@dataclass(frozen=True)
class ReadmeHeaderContract:
    """Title, versioned mark, description, ordered navigation targets and the telemetry badge inventory."""

    readme: str
    home: str
    title: str
    mark_path: str
    mark_version: str
    mark_digest: str
    mark_alt: str
    description: str
    links: dict[str, str]
    badges: tuple[Badge, ...]


def registry() -> tuple[dict[str, str], str]:
    """The consumer slugs of ``REPOS`` and the registry digest, read from source (never imported)."""
    try:
        source = _REGISTRY_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError) as exc:
        raise CannotRun(f"{GATE}: the consumer registry is unavailable: {exc}") from exc
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and getattr(node.target, "id", "") == "REPOS"
            and isinstance(node.value, ast.Dict)
        ):
            slugs = [k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            return {f"{CONSUMER_NAMESPACE}/{slug}": slug for slug in slugs}, sha(ast.dump(node.value))
    raise CannotRun(f"{GATE}: REPOS is not declared in {_REGISTRY_FILE.name}")


def resolve_identity(root: Path) -> tuple[str, str]:
    """``(host/namespace/repository, source)`` from origin, else the sole remote; no network access."""
    names = run_git(root, ("remote",)).stdout.split()
    if "origin" in names:
        name = "origin"
    elif len(names) == 1:
        name = names[0]
    else:
        raise CannotRun(
            f"{GATE}: the remote identity is unresolved or ambiguous ({len(names)} remotes, none is origin)"
        )
    url = run_git(root, ("config", "--get", f"remote.{name}.url")).stdout.strip()
    match = re.match(r"^(?:[a-z+]+://(?:[^@/]+@)?|[^@/]+@)(?P<host>[^/:]+)[/:](?P<path>[^/]+/[^/]+?)(?:\.git)?/?$", url)
    if match is None:
        raise CannotRun(f"{GATE}: remote {name} has no resolvable host/namespace/repository identity")
    return f"{match['host']}/{match['path']}", f"remote:{name}"


def load_contract(root: Path) -> tuple[ReadmeHeaderContract, str]:
    data, raw = load_json(GATE, root, DECLARATION)
    data = strict_keys(
        GATE,
        DECLARATION,
        data,
        {"schema", "readme", "home", "title", "mark", "description", "links", "badges"},
        {"schema", "readme", "home", "title", "mark", "description", "links", "badges"},
    )
    if data["schema"] != 1:
        raise CannotRun(f"{GATE}: unsupported declaration schema")
    mark = strict_keys(
        GATE, "mark", data["mark"], {"path", "version", "digest", "alt"}, {"path", "version", "digest", "alt"}
    )
    if tuple(data["links"]) != NAV:
        raise CannotRun(f"{GATE}: links must be exactly {list(NAV)} in order")
    badges = []
    for b in data["badges"]:
        b = strict_keys(
            GATE, "badge", b, {"id", "label", "provenance", "as_of"}, {"id", "label", "provenance", "as_of"}
        )
        if not _PROVENANCE.match(b["provenance"]):
            raise CannotRun(f"{GATE}: badge {b['id']} has unknown provenance {b['provenance']!r}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", b["as_of"]):
            raise CannotRun(f"{GATE}: badge {b['id']} carries no status as-of date")
        badges.append(Badge(b["id"], b["label"], b["provenance"], b["as_of"]))
    contract = ReadmeHeaderContract(
        safe_path(GATE, data["readme"]),
        safe_path(GATE, data["home"]),
        data["title"],
        safe_path(GATE, mark["path"]),
        str(mark["version"]),
        mark["digest"],
        mark["alt"],
        data["description"],
        dict(data["links"]),
        tuple(badges),
    )
    return contract, sha(raw)


def render_markdown(contract: ReadmeHeaderContract, *, prefix: str = "") -> str:
    """The shared header for a README (``prefix`` is the relative path from the document to the repository root)."""
    nav = " | ".join(f"[{name}]({prefix}{contract.links[name]})" for name in NAV)
    badges = " ".join(f"![{b.label}](https://badges.invalid/{b.id}.svg)" for b in contract.badges)
    return f"# {contract.title}\n\n![{contract.mark_alt}]({prefix}{contract.mark_path})\n\n{contract.description}\n\n{nav}\n\n{badges}\n"


def _top(text: str) -> list[str]:
    """The header region: everything before the first ``##`` heading."""
    return re.split(r"^## ", text, maxsplit=1, flags=re.M)[0].splitlines()


def check_document(root: Path, path: str, contract: ReadmeHeaderContract, result: Result) -> None:
    raw = require(GATE, root, path).decode("utf-8", errors="replace")
    top = "\n".join(_top(raw))
    prefix = posixpath.relpath(".", posixpath.dirname(path) or ".")
    prefix = "" if prefix == "." else prefix + "/"
    order = [
        m.start()
        for m in (
            re.search(re.escape(f"# {contract.title}"), top),
            _IMG.search(top),
            re.search(re.escape(contract.description), top),
            _LINK.search(top),
        )
        if m
    ]
    if len(order) != 4 or order != sorted(order):
        result.findings.append(f"{path}:1: header must open with title, mark, description and navigation in that order")
    mark = _IMG.search(top)
    if (
        mark is None
        or mark["src"] != prefix + contract.mark_path
        or mark["alt"] != contract.mark_alt
        or not mark["alt"]
    ):
        result.findings.append(
            f"{path}:1: project mark {mark['src'] if mark else None!r} is not the declared mark {prefix + contract.mark_path!r} with its alt text"
        )
    names = [m["text"] for m in _LINK.finditer(top) if m["text"] in NAV]
    if names != list(NAV):
        result.findings.append(f"{path}:1: navigation links are {names}, expected {list(NAV)}")
    for m in _LINK.finditer(top):
        if m["text"] in NAV:
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), m["target"]))
            if m["target"] != prefix + contract.links[m["text"]] or read(root, target) is None:
                result.findings.append(
                    f"{path}:{raw[: raw.find(m[0])].count(chr(10)) + 1}: navigation target {m['target']} for {m['text']} is not the declared, existing page"
                )
    details = re.findall(r"<details.*?</details>", top, re.S)
    for badge in contract.badges:
        shown = [m for m in _IMG.finditer(top) if m["alt"] == badge.label]
        hidden = any(f"![{badge.label}]" in block for block in details)
        result.lines.append(
            f"badge doc={path} id={badge.id} visible={'yes' if shown and not hidden else 'no'} provenance={badge.provenance} as-of={badge.as_of}"
        )
        if not shown or hidden:
            result.findings.append(
                f"{path}:1: telemetry badge {badge.id} is missing from the top badges or hidden in a collapsed section"
            )
    result.lines.append(
        f"header doc={path} order=title,mark,description,navigation destinations={ {n: contract.links[n] for n in NAV} }"
    )


class _Site(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.imgs: list[tuple[str, str, bool]] = []
        self.details = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        self.details += tag == "details"
        if tag == "a" and a.get("data-nav"):
            self.links.append(a["data-nav"] or "")
        if tag == "img":
            self.imgs.append((a.get("alt") or "", a.get("src") or "", self.details > 0))

    def handle_endtag(self, tag: str) -> None:
        self.details -= tag == "details"


def check_site(site: Path, contract: ReadmeHeaderContract, result: Result) -> None:
    index = site / "index.html"
    if not index.is_file():
        raise CannotRun(f"{GATE}: the built site has no index.html")
    parser = _Site()
    parser.feed(index.read_text(encoding="utf-8"))
    if parser.links != list(NAV):
        result.findings.append(f"{index.name}: served navigation is {parser.links}, expected {list(NAV)}")
    if not any(alt == contract.mark_alt and src.endswith(contract.mark_path) for alt, src, _ in parser.imgs):
        result.findings.append(f"{index.name}: served page does not show the declared project mark")
    for badge in contract.badges:
        if not any(alt == badge.label and not hidden for alt, _src, hidden in parser.imgs):
            result.findings.append(f"{index.name}: served telemetry badge {badge.id} is hidden or absent")
    result.lines.append(f"site artifact={sha(index.read_bytes())} navigation={parser.links}")


def check(root: Path, *, site: Path | None = None) -> Result:
    consumers, registry_digest = registry()
    identity, source = resolve_identity(root)
    result = Result()
    if identity == PROVIDER:
        result.lines.append(
            f"readme-header skip reason=provider-not-consumer identity={identity} source={source} "
            f"registry={registry_digest} consumer-checks=0"
        )
        return result
    if identity not in consumers:
        raise CannotRun(f"{GATE}: {identity} is not a known consumer of the registry")
    contract, policy = load_contract(root)
    result.lines.append(
        f"scope consumer={consumers[identity]} identity={identity} source={source} policy={policy} registry={registry_digest}"
    )
    mark = read(root, contract.mark_path)
    if mark is None:
        result.findings.append(f"{contract.mark_path}: the declared project mark is missing")
    elif sha(mark) != contract.mark_digest:
        result.findings.append(
            f"{contract.mark_path}: mark digest {sha(mark)} is not the declared {contract.mark_digest}"
        )
    if f"v{contract.mark_version}" not in contract.mark_path:
        result.findings.append(f"{contract.mark_path}: the mark path carries no version v{contract.mark_version}")
    result.lines.append(
        f"mark path={contract.mark_path} version={contract.mark_version} digest={sha(mark) if mark else 'absent'}"
    )
    for document in (contract.readme, contract.home):
        check_document(root, document, contract, result)
    if site is not None:
        check_site(site, contract, result)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=GATE, description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--site", type=Path, help="also check the home page of a built site")
    parser.add_argument(
        "--provider", action="store_true", help="ignored: scope comes only from the resolved remote identity"
    )
    args = parser.parse_args(argv)
    if args.provider:
        print("readme-header: --provider is ignored; scope is selected only by the resolved remote identity")
    return finish(GATE, "readme header", check(repo_root(args.root), site=args.site))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
