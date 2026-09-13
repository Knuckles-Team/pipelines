"""Find the delimiter that balances an opener, comment- and string-aware."""

from __future__ import annotations

from dataclasses import dataclass

from pipelines_hooks.rust.mask import CHAR_LITERAL, RustLexError


@dataclass
class _Scan:
    """Scanner state for one balanced-span search."""

    source: str
    opener: str
    closer: str
    state: str = "code"
    depth: int = 0
    block_depth: int = 0

    def pair(self, index: int) -> str:
        return self.source[index : index + 2]

    def code_step(self, index: int) -> tuple[int, int | None]:
        """``(skip, closing_index)`` for one character in code state."""
        token, char = self.pair(index), self.source[index]
        if token in ("//", "/*"):
            self.state = "line-comment" if token == "//" else "block-comment"
            self.block_depth = int(token == "/*")
            return 1, None
        if char == '"':
            self.state = "string"
            return 0, None
        if char == "'":
            literal = CHAR_LITERAL.match(self.source, index)
            return (0 if literal is None else literal.end() - index - 1), None
        if char == self.opener:
            self.depth += 1
        elif char == self.closer:
            self.depth -= 1
            return 0, (index if self.depth == 0 else None)
        return 0, None

    def block_step(self, index: int) -> int:
        token = self.pair(index)
        if token == "/*":
            self.block_depth += 1
            return 1
        if token == "*/":
            self.block_depth -= 1
            self.state = "code" if self.block_depth == 0 else self.state
            return 1
        return 0

    def non_code_step(self, index: int) -> int:
        """The skip for one character inside a comment or string."""
        char = self.source[index]
        if self.state == "line-comment":
            self.state = "code" if char == "\n" else self.state
            return 0
        if self.state == "block-comment":
            return self.block_step(index)
        if char == "\\":
            return 1
        self.state = "code" if char == '"' else self.state
        return 0


def balanced_span_from(source: str, start: int, *, opener: str, closer: str) -> int:
    """Index of the ``closer`` that balances the ``opener`` at ``start``."""
    if start < 0 or start >= len(source) or source[start] != opener:
        raise RustLexError(f"expected {opener!r} at position {start}")
    scan = _Scan(source, opener, closer)
    index = start
    while index < len(source):
        if scan.state == "code":
            skip, closing = scan.code_step(index)
            if closing is not None:
                return closing
        else:
            skip = scan.non_code_step(index)
        index += skip + 1
    raise RustLexError(f"unterminated balanced block starting at position {start}")
