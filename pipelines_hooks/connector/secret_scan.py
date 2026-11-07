"""Static scans of the secret-fields gate: response models, JSON schemas and recorded outputs.

A secret-named field is one whose name ends in a credential word (``token``,
``secret``, ``password``, ``api_key``, ``private_key``, ``credentials``,
``connection_string``, ...), as in ``runners_token`` or ``webhook_secret``; a
name that continues past the word describes something else
(``token_expires_at``, ``api_key_env``), and a flag about it
(``has_password``) is not a secret.

A field is marked when it cannot carry the value in a served response:

- a model field typed ``SecretStr``, ``SecretBytes`` or a ``Redacted``/``SecretBearing``
  type, or declared with ``Field(exclude=True)`` or a ``json_schema_extra`` that holds
  ``x-redacted`` or ``x-secret-bearing``;
- a schema property with ``"x-redacted": true``, ``"x-secret-bearing": true`` or
  ``"writeOnly": true``.

``x-secret-bearing`` is the annotation of a tool that returns a newly minted
secret once. Input models (``*Settings``, ``*Config``, ``*Credentials``,
``*Request``, ``*Params``, ``*Input``, ``*Args``, ``BaseSettings``, and modules
named ``*input*``, ``*request*`` or ``*params*``) are not responses and are not
scanned.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

_WORDS = (
    r"token|secret|password|passwd|passphrase|api_?key|apikey|private_?key|access_?key|secret_?key"
    r"|client_?secret|credentials?|connection_?string|dsn|auth_?header|cookie|session_?key"
)
#: The credential word is the last word of the name (``runners_token``,
#: ``apiKey``, ``connection_string``), optionally followed by a value suffix;
#: a word followed by anything else describes something else
#: (``token_expires_at``, ``api_key_env``, ``resource_access_token_events``).
SECRET_NAME = re.compile(rf"(?:^|[_.\-]|(?<=[a-z])(?=[A-Z]))(?i:{_WORDS})(?:[_\-]?(?i:value|plaintext|raw))?[0-9]*$")
#: Tokens that are cursors or coordination handles, not credentials.
NON_CREDENTIAL = re.compile(
    r"(?i)(continuation|page|next_?page|pagination|cursor|fencing|cancellation|sync|resume)_?token$"
)
#: Prefixes of a flag about the credential (``has_password``, ``isTokenSet``).
FLAG_PREFIX = re.compile(r"^(?i:has|is|requires|uses|needs|supports|prevent|require)(?:_|[A-Z])")
INPUT_SUFFIXES = ("Settings", "Config", "Configuration", "Credentials", "Request", "Params", "Input", "Args")
MODEL_BASES = frozenset({"BaseModel", "TypedDict", "RootModel"})
MARKED_TYPES = re.compile(r"SecretStr|SecretBytes|Redacted|SecretBearing")
SCHEMA_MARKS = ("x-redacted", "x-secret-bearing", "writeOnly")
#: Value shapes of live credentials; a recorded output holding one leaks it.
VALUE_PATTERNS = (
    ("gitlab-token", re.compile(r"\bgl(pat|rt|ptt|dt|ft|soat|oas|cbt|imt|agent)-[A-Za-z0-9_\-]{16,}")),
    ("gitlab-runner-registration", re.compile(r"\bGR1348941[A-Za-z0-9_\-]{16,}")),
    ("github-token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("aws-access-key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("api-secret-key", re.compile(r"\bsk-[A-Za-z0-9_\-]{24,}")),
)
PLACEHOLDERS = re.compile(
    r"(?i)^(|\*+|x+|redacted|<redacted>|\[redacted\]|\*\*\*redacted\*\*\*|null|none|changeme|example.*|<.*>|\$\{.*\})$"
)


@dataclass(frozen=True)
class Leak:
    """One finding: where, which code, and what (never the value)."""

    file: str
    line: int
    code: str
    detail: str

    def render(self) -> str:
        return f"{self.file}:{self.line} {self.code} {self.detail}"


def is_secret_name(name: str) -> bool:
    return bool(SECRET_NAME.search(name)) and not FLAG_PREFIX.match(name) and not NON_CREDENTIAL.search(name)


def _base_names(node: ast.ClassDef) -> set[str]:
    return {ast.unparse(base).split(".")[-1].split("[")[0] for base in node.bases}


def _is_response_model(node: ast.ClassDef, models: set[str]) -> bool:
    if node.name.startswith("_") or node.name.endswith(INPUT_SUFFIXES) or "BaseSettings" in _base_names(node):
        return False
    dataclass_like = any("dataclass" in ast.unparse(d) for d in node.decorator_list)
    return dataclass_like or bool(_base_names(node) & (MODEL_BASES | models))


def _marked(stmt: ast.AnnAssign) -> bool:
    if MARKED_TYPES.search(ast.unparse(stmt.annotation)):
        return True
    value = stmt.value
    if not isinstance(value, ast.Call):
        return False
    for keyword in value.keywords:
        text = ast.unparse(keyword.value)
        if keyword.arg == "exclude" and text == "True":
            return True
        if keyword.arg == "json_schema_extra" and any(mark in text for mark in SCHEMA_MARKS):
            return True
    return False


def model_leaks(path: str, source: str) -> list[Leak]:
    """Secret-named fields of response models that are not marked."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    models = {node.name for node in classes if _base_names(node) & MODEL_BASES}
    found: list[Leak] = []
    for node in classes:
        if not _is_response_model(node, models):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                if is_secret_name(name) and not _marked(stmt):
                    found.append(Leak(path, stmt.lineno, "SF-MODEL-FIELD", f"{node.name}.{name}"))
    return found


def _schema_properties(schema: Any, trail: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(schema, dict):
        for name, sub in (schema.get("properties") or {}).items():
            if isinstance(sub, dict):
                yield f"{trail}{name}", sub
                yield from _schema_properties(sub, f"{trail}{name}.")
        for key in ("items", "additionalProperties"):
            yield from _schema_properties(schema.get(key), trail)
        for key in ("$defs", "definitions"):
            for sub in (schema.get(key) or {}).values():
                yield from _schema_properties(sub, trail)
        for key in ("anyOf", "oneOf", "allOf"):
            for sub in schema.get(key) or []:
                yield from _schema_properties(sub, trail)
    elif isinstance(schema, list):
        for sub in schema:
            yield from _schema_properties(sub, trail)


def schema_leaks(path: str, schema: Any, code: str = "SF-SCHEMA-FIELD") -> list[Leak]:
    """Secret-named schema properties without a redaction or secret-bearing mark."""
    return [
        Leak(path, 1, code, trail)
        for trail, prop in _schema_properties(schema)
        if is_secret_name(trail.rsplit(".", 1)[-1]) and not any(prop.get(mark) is True for mark in SCHEMA_MARKS)
    ]


def _json_values(data: Any, key: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(data, dict):
        for name, value in data.items():
            yield from _json_values(value, str(name))
    elif isinstance(data, list):
        for value in data:
            yield from _json_values(value, key)
    elif isinstance(data, str):
        yield key, data


def recorded_leaks(path: str, text: str) -> list[Leak]:
    """Credential-shaped values, and filled secret-named keys, in a recorded output."""
    found = [
        Leak(path, text.count("\n", 0, match.start()) + 1, "SF-RECORDED-VALUE", kind)
        for kind, pattern in VALUE_PATTERNS
        for match in pattern.finditer(text)
    ]
    if path.endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError:
            return found
        found += [
            Leak(path, 1, "SF-RECORDED-FIELD", key)
            for key, value in _json_values(data)
            if is_secret_name(key) and not PLACEHOLDERS.match(value.strip())
        ]
    return found
