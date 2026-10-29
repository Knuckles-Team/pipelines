"""spec-prefix-rename: rewrite retired spec ID prefixes to repository-name prefixes.

Deterministic and idempotent codemod for one repository checkout. It rewrites every
requirement ID (``<PREFIX>-...-R<nnn>[.n]*``) whose prefix starts with a retired prefix,
the spec IDs and spec directory names those IDs belong to, and ``spec_id`` fields. It
adds ``"<OLD>-" = "<NEW>-"`` to ``.config/spec-aliases.toml`` only in the repository
that owns the prefix. It never touches git history, released CHANGELOG sections, alias
keys, binary files, lock files or vendored directories. Text such as ``EG-1`` or
``AU-ish`` is not an ID and is left alone.

Usage: ``pipelines-hook spec-prefix-rename [--root DIR] [--repo NAME] [--map OLD=NEW ...] [--only PATH ...] [--dry-run]``
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import Counter
from pathlib import Path

from pipelines_hooks.core.errors import CannotRun
from pipelines_hooks.core.gitenv import repo_root
from pipelines_hooks.specs.repository_identity import remote_owner

#: Retired prefix -> new prefix (both with the trailing hyphen).
DEFAULT_MAP: dict[str, str] = {
    "EG-": "MEDULLA-",
    "AU-": "MERISTEM-",
    "SDK-": "SCION-",
    "WEBUI-": "OVERSTORY-",
    "FIN-UI-": "OVERSTORY-",
    "TUI-": "TUIG-",
    "GENIUSBOT-": "AXIL-",
    "GRAPHOS-": "ARBORA-",
}
#: Prefix -> repository that owns it (the only repository that records the alias).
OWNERS: dict[str, str] = {
    "EG-": "medulla",
    "AU-": "meristem",
    "SDK-": "scion-sdk",
    "WEBUI-": "overstory",
    "FIN-UI-": "overstory",
    "TUI-": "tuig",
    "GENIUSBOT-": "axil",
    "GRAPHOS-": "arbora",
}
ALIAS_FILE = ".config/spec-aliases.toml"
_SKIP_DIRS = frozenset({".git", "node_modules", "vendor", "target", "dist", "build", ".venv", "venv", "__pycache__"})
_SKIP_NAMES = frozenset({"uv.lock", "package-lock.json", "Cargo.lock", "poetry.lock", "pnpm-lock.yaml", "yarn.lock"})
_MAX_BYTES = 8_000_000
_ROW_SUFFIX = re.compile(r"-R[0-9]{3}(?:\.[0-9]+)*$")
_BOUND_L = r"(?<![A-Za-z0-9_\-])"
_BOUND_R = r"(?!(?!-R[0-9]{3})[A-Za-z0-9_\-]|\.[0-9])"
_ALIAS_LINE = re.compile(r'^(\s*"[^"\n]+"\s*=\s*")([^"\n]*)(".*)$')
_UNRELEASED = re.compile(r"^#{1,3}\s*\[?unreleased\]?", re.I)
_HEADING = re.compile(r"^#{1,3}\s")


def _id_regex(prefixes: list[str]) -> re.Pattern[str]:
    alternation = "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True))
    return re.compile(_BOUND_L + rf"(?:{alternation})(?:[A-Z0-9]+-)*R[0-9]{{3}}(?:\.[0-9]+)*" + _BOUND_R)


def _prefix_of(token: str, prefixes: list[str]) -> str:
    return max((p for p in prefixes if token.startswith(p)), key=len)


class Renamer:
    def __init__(
        self, root: Path, mapping: dict[str, str], repo: str | None, dry_run: bool, only: tuple[str, ...] = ()
    ) -> None:
        self.only = only
        self.root = root
        self.mapping = mapping
        self.prefixes = list(mapping)
        self.repo = repo
        self.dry_run = dry_run
        self.id_re = _id_regex(self.prefixes)
        self.counts: Counter[str] = Counter()
        self.changed: list[str] = []
        self.renamed_dirs: list[tuple[str, str]] = []
        self.alias_added: list[str] = []
        self.warnings: list[str] = []
        self.stems: set[str] = set()
        self.bare: set[str] = set()  # spec ID is the bare prefix itself, e.g. FIN-UI-R001
        self._stem_re: re.Pattern[str] | None = None
        self._bare_re: re.Pattern[str] | None = None

    # -- file discovery ---------------------------------------------------
    def files(self) -> list[Path]:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=self.root,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", "surrogateescape")
        result: list[Path] = []
        for name in sorted(filter(None, out.split("\0"))):
            parts = Path(name).parts
            if self.only and not any(name == o or name.startswith(o.rstrip("/") + "/") for o in self.only):
                continue
            if _SKIP_DIRS.intersection(parts) or parts[-1] in _SKIP_NAMES or parts[-1].endswith(".lock"):
                continue
            path = self.root / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_BYTES:
                continue
            result.append(path)
        return result

    @staticmethod
    def read(path: Path) -> str | None:
        data = path.read_bytes()
        if b"\0" in data:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    # -- stems (spec IDs) ---------------------------------------------------
    def collect_stems(self, texts: dict[Path, str]) -> None:
        for path, text in texts.items():
            if path.relative_to(self.root).as_posix() == ALIAS_FILE:
                continue
            for match in self.id_re.finditer(text):
                stem = _ROW_SUFFIX.sub("", match.group(0))
                if any(stem.startswith(p) and len(stem) > len(p) for p in self.prefixes):
                    self.stems.add(stem)
                elif stem + "-" in self.mapping:
                    self.bare.add(stem)
        specs = self.root / "specs"
        if specs.is_dir():
            for child in specs.iterdir():
                if child.is_dir() and child.name.startswith(tuple(self.prefixes)):
                    self.stems.add(child.name)
        if self.stems:
            alternation = "|".join(re.escape(s) for s in sorted(self.stems, key=len, reverse=True))
            self._stem_re = re.compile(_BOUND_L + f"(?:{alternation})" + r"(?![A-Za-z0-9_\-])")
        if self.bare:
            alternation = "|".join(re.escape(s) for s in sorted(self.bare, key=len, reverse=True))
            # Only the unambiguous spec-ID positions: a spec_id field and a spec.md title line.
            self._bare_re = re.compile(rf'("spec_id"\s*:\s*")({alternation})(?=")|(^# )({alternation})(?= )', re.M)

    # -- text rewriting -----------------------------------------------------
    def _swap(self, token: str, count: bool) -> str:
        old = _prefix_of(token, self.prefixes)
        if count:
            self.counts[old] += 1
        return self.mapping[old] + token[len(old) :]

    def _swap_bare(self, match: re.Match[str]) -> str:
        lead, stem = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
        self.counts[stem + "-"] += 1
        return lead + self.mapping[stem + "-"][:-1]

    def rewrite(self, text: str) -> str:
        text = self.id_re.sub(lambda m: self._swap(m.group(0), True), text)
        if self._stem_re is not None:
            text = self._stem_re.sub(lambda m: self._swap(m.group(0), False), text)
        if self._bare_re is not None:
            text = self._bare_re.sub(self._swap_bare, text)
        return text

    def rewrite_changelog(self, text: str) -> str:
        lines = text.split("\n")
        live = False
        for index, line in enumerate(lines):
            if _HEADING.match(line):
                live = bool(_UNRELEASED.match(line))
            elif live:
                lines[index] = self.rewrite(line)
        return "\n".join(lines)

    def rewrite_alias_file(self, text: str) -> str:
        """Alias values follow the new prefixes; keys are never rewritten."""
        out = []
        for line in text.split("\n"):
            match = _ALIAS_LINE.match(line)
            if match and any(match.group(2).startswith(p) for p in self.prefixes):
                old = _prefix_of(match.group(2), self.prefixes)
                self.counts[old] += 1
                line = match.group(1) + self.mapping[old] + match.group(2)[len(old) :] + match.group(3)
            out.append(line)
        return "\n".join(out)

    def owned_prefixes(self) -> list[str]:
        return sorted(p for p, owner in OWNERS.items() if p in self.mapping and owner == self.repo)

    def add_aliases(self, text: str) -> str:
        missing = []
        for old in self.owned_prefixes():
            if re.search(rf'^\s*"{re.escape(old)}"\s*=', text, re.M):
                continue
            missing.append(old)
        if not missing:
            return text
        if text and not text.endswith("\n"):
            text += "\n"
        if not text:
            text = "# Retired spec ID prefixes -> canonical prefix (pipelines spec tooling).\n"
        for old in missing:
            text += f'"{old}" = "{self.mapping[old]}"\n'
            self.alias_added.append(old)
        return text

    # -- driver -------------------------------------------------------------
    def run(self) -> None:
        paths = self.files()
        texts = {p: t for p in paths if (t := self.read(p)) is not None}
        self.collect_stems(texts)
        for path, text in texts.items():
            rel = path.relative_to(self.root).as_posix()
            name = path.name
            if rel == ALIAS_FILE:
                new = self.rewrite_alias_file(text)
            elif name.upper().startswith("CHANGELOG"):
                new = self.rewrite_changelog(text)
            else:
                new = self.rewrite(text)
            if new != text:
                self.changed.append(rel)
                if not self.dry_run:
                    path.write_text(new, encoding="utf-8", newline="")
        self.rename_spec_dirs()
        self.update_alias_file()

    def rename_spec_dirs(self) -> None:
        specs = self.root / "specs"
        if not specs.is_dir():
            return
        for child in sorted(specs.iterdir()):
            if child.is_dir() and any(child.name.startswith(p) for p in self.prefixes):
                new = self._swap(child.name, False)
                target = specs / new
                if target.exists():
                    self.warnings.append(f"specs/{child.name}: target specs/{new} exists; not renamed")
                    continue
                self.renamed_dirs.append((f"specs/{child.name}", f"specs/{new}"))
                if not self.dry_run:
                    child.rename(target)

    def update_alias_file(self) -> None:
        if not self.owned_prefixes():
            return
        path = self.root / ALIAS_FILE
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        new = self.add_aliases(text)
        if new != text:
            if ALIAS_FILE not in self.changed:
                self.changed.append(ALIAS_FILE)
            if not self.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new, encoding="utf-8")

    def validate_aliases(self) -> None:
        from pipelines_hooks.specs.aliases import load_aliases

        try:
            load_aliases(self.root)
        except CannotRun as exc:
            self.warnings.append(f"alias file does not validate after the rename: {exc}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="spec-prefix-rename", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--repo", help="repository name (default: origin remote name, else directory name)")
    parser.add_argument("--map", action="append", default=[], metavar="OLD=NEW", help="override or add a prefix pair")
    parser.add_argument("--only", action="append", default=[], metavar="PATH", help="limit rewriting to these paths")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = _parse_args(argv)
    root = repo_root(arguments.root)
    mapping = dict(DEFAULT_MAP)
    for pair in arguments.map:
        old, _, new = pair.partition("=")
        if not (old.endswith("-") and new.endswith("-")):
            raise CannotRun(f"--map {pair!r}: expected OLD-=NEW- (both ending in '-')")
        mapping[old] = new
    repo = arguments.repo or remote_owner(root) or root.name
    renamer = Renamer(root, mapping, repo, arguments.dry_run, tuple(arguments.only))
    renamer.run()
    if not arguments.dry_run:
        renamer.validate_aliases()
    print(f"spec-prefix-rename: repo={repo}{' (dry run)' if arguments.dry_run else ''}")
    print(f"  files changed: {len(renamer.changed)}")
    for old in sorted(renamer.counts):
        print(f"  {old} -> {mapping[old]}: {renamer.counts[old]} rewritten")
    for src, dst in renamer.renamed_dirs:
        print(f"  renamed {src} -> {dst}")
    for old in renamer.alias_added:
        print(f"  alias added: {old!r} = {mapping[old]!r}")
    for warning in renamer.warnings:
        print(f"  WARN: {warning}")
    return 0
