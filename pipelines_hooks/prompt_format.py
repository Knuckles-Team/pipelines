"""Fail-closed validation for canonical prompt JSON on disk.

The prompt files consumed by the agent plane are JSON documents, but their
semantic contract is a Pydantic model.  This module keeps those two concerns
together: input is parsed with duplicate-key and non-finite-number checks,
validated by :class:`PromptDiskDocument`, and written with one deterministic
UTF-8 representation.  ``difference_oracle`` compares validated documents,
so whitespace and object-key order do not appear as semantic changes.

The R094 identifiers below are a dependency boundary, not a claim that this
repository owns graph export, import, or repository write-back.  A snapshot
retains the identity, revision, schema-pin, payload, and provenance fields
exported by those producers so a consumer can compare the exact bytes and
their semantic content without dropping fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from pipelines_hooks.core.paths import relative_to_root


GATE_ID = "prompt-format"
FORMAT_VERSION = "1.0"
MAX_PROMPT_BYTES = 2 * 1024 * 1024
MAX_PROMPT_DEPTH = 64
MAX_PROMPT_NODES = 65_536
# Numeric values are kept exact, but an unbounded Decimal exponent or integer
# coefficient would make canonical expansion allocate without regard to the
# document byte cap.  These limits are checked on the JSON lexeme before the
# stdlib converts it, and again on values supplied by Python callers.
MAX_PROMPT_NUMBER_DIGITS = 4_096
MAX_PROMPT_NUMBER_EXPONENT = 4_096
MAX_PROMPT_INTEGER_BITS = int(MAX_PROMPT_NUMBER_DIGITS * math.log2(10)) + 1

# R094.2-.7 are the graph producers/consumers named by PIPE-PAGES-R035.3.
# Keeping the complete range here makes the dependency visible to callers and
# prevents a serializer test from silently covering only one producer.
R094_WIRING_REQUIREMENTS: tuple[str, ...] = tuple(f"EG-TYPED-PACKS-R094.{n}" for n in range(2, 8))

_RETIRED_TOP_LEVEL_KEYS = frozenset({"content", "input"})
_RETIRED_OPTIMIZER_KEYS = frozenset({"few_shot_examples", "optimized_instruction"})


class PromptFormatError(ValueError):
    """A prompt cannot be trusted as a canonical disk document."""


class PromptPathError(RuntimeError):
    """A CLI input path cannot be proven to stay inside its repository root."""


class _PermissiveSection(BaseModel):
    """Typed common fields with lossless extension fields."""

    model_config = ConfigDict(extra="allow", strict=True)


class PromptMetadata(_PermissiveSection):
    description: str | None = None
    topic: str | None = None
    tone: str | None = None
    style: str | None = None
    audience: str | None = None


class PromptIdentity(_PermissiveSection):
    role: str | None = None
    goal: str | None = None
    personality: list[str] | None = None


class PromptInstructions(_PermissiveSection):
    core_directive: str | None = None
    responsibilities: list[str] | None = None
    capabilities: dict[str, list[str]] | None = None
    workflow: list[str] | None = None
    quality_checklist: list[str] | None = None
    methodology: str | None = None
    output_format: str | None = None


class PromptDiskDocument(BaseModel):
    """Pydantic representation of the canonical prompt JSON document.

    ``extra='allow'`` is intentional.  R094 exports can add identity,
    revision, schema-pin, payload, and provenance fields; validation must type
    the known prompt sections without erasing an admitted extension field.
    ``serialize_prompt`` emits only fields that were present, apart from the
    two canonical defaults (``type`` and ``schema_version``).
    """

    task: str = Field(min_length=1, max_length=4096)
    type: Literal["prompt"] = "prompt"
    schema_version: str = FORMAT_VERSION
    metadata: PromptMetadata | None = None
    identity: PromptIdentity | None = None
    instructions: PromptInstructions | None = None
    version: str | None = None
    prompt_version: str | None = None
    source: str | None = None
    topic: str | None = None
    platform: str | None = None
    tone: str | None = None
    style: str | None = None
    length: str | None = None
    audience: str | None = None
    goal: str | None = None
    description: str | None = None
    structure: dict[str, Any] | None = None
    constraints: list[str] | None = None
    deliverables: list[str] | None = None
    output_format: str | None = None
    visual_style: str | None = None
    language: str | None = None
    tools: list[str] | None = None
    engineering_rules: dict[str, Any] | None = None
    rules: list[str] | dict[str, list[str]] | None = None
    program_compiled_state: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow", strict=True, validate_assignment=True)

    @field_validator("task")
    @classmethod
    def _task_has_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task must contain non-whitespace text")
        if len(value.encode("utf-8")) > 4096:
            raise ValueError("task exceeds the 4096-byte limit")
        return value

    @field_validator("schema_version")
    @classmethod
    def _schema_is_present(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("schema_version must contain non-whitespace text")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_retired_shapes(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        retired = _RETIRED_TOP_LEVEL_KEYS.intersection(value)
        optimizer = _RETIRED_OPTIMIZER_KEYS.intersection(value)
        foreign_compiled = any(
            str(key).endswith("_compiled_state") and key != "program_compiled_state" for key in value
        )
        if retired:
            names = ", ".join(sorted(retired))
            raise ValueError(f"retired prompt body key(s) are forbidden: {names}")
        if optimizer or foreign_compiled:
            raise ValueError("raw persisted optimizer artifacts are forbidden")
        return value


# ``PromptBlueprint`` is the name used by the graph-facing contract.  Keep an
# alias rather than introducing a second model with a potentially divergent
# serializer.
PromptBlueprint = PromptDiskDocument


@dataclass(frozen=True)
class PromptDifference:
    """One JSON-Pointer-addressed semantic change."""

    path: str
    kind: Literal["added", "removed", "changed"]
    before: Any = None
    after: Any = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe evidence row without rounding Decimal values."""

        return {
            "path": self.path,
            "kind": self.kind,
            "before": _evidence_value(self.before),
            "after": _evidence_value(self.after),
        }


@dataclass(frozen=True)
class PromptSnapshot:
    """Canonical bytes and digest retained for an exact evidence receipt."""

    document: PromptDiskDocument
    canonical_bytes: bytes
    sha256: str
    producer_requirements: tuple[str, ...] = R094_WIRING_REQUIREMENTS

    @property
    def digest(self) -> str:
        """Compatibility spelling for callers that call hashes ``digest``."""

        return self.sha256


def _duplicate_key_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PromptFormatError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> Any:
    raise PromptFormatError(f"non-finite JSON number is forbidden: {value}")


def _check_integer_bounds(value: int) -> None:
    """Refuse integer values before formatting can invoke a huge conversion."""

    # ``int.bit_length`` works for negative values without making an absolute
    # copy.  It is a cheap conservative check before ``str(int)`` below.
    if value.bit_length() > MAX_PROMPT_INTEGER_BITS:
        raise PromptFormatError(f"JSON integer exceeds the {MAX_PROMPT_NUMBER_DIGITS}-digit limit")


def _bounded_decimal_parts(value: Decimal) -> tuple[int, tuple[int, ...], int]:
    """Return exact, context-independent Decimal parts after applying bounds."""

    if not value.is_finite():
        raise PromptFormatError("non-finite Decimal is forbidden")
    sign, digits, raw_exponent = value.as_tuple()
    if not isinstance(raw_exponent, int):
        raise PromptFormatError("Decimal exponent must be an integer")
    if len(digits) > MAX_PROMPT_NUMBER_DIGITS:
        raise PromptFormatError(f"Decimal coefficient exceeds the {MAX_PROMPT_NUMBER_DIGITS}-digit limit")
    if abs(raw_exponent) > MAX_PROMPT_NUMBER_EXPONENT:
        raise PromptFormatError(f"Decimal exponent exceeds the +/-{MAX_PROMPT_NUMBER_EXPONENT} limit")

    # ``Decimal.normalize`` uses the process context precision and can round a
    # perfectly valid 100-digit exact value.  Strip lexical trailing zeroes
    # directly from the tuple instead, preserving all significant digits.
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
    normalized_digits = digits[:end]
    normalized_exponent = raw_exponent + len(digits) - end
    if abs(normalized_exponent) > MAX_PROMPT_NUMBER_EXPONENT:
        raise PromptFormatError(f"Decimal exponent exceeds the +/-{MAX_PROMPT_NUMBER_EXPONENT} limit")
    expanded_digits = len(normalized_digits) + abs(normalized_exponent)
    if expanded_digits > MAX_PROMPT_NUMBER_DIGITS:
        raise PromptFormatError(f"Decimal expansion exceeds the {MAX_PROMPT_NUMBER_DIGITS}-digit limit")
    return sign, normalized_digits, normalized_exponent


def _check_decimal_bounds(value: Decimal) -> None:
    """Refuse Decimal coefficients/exponents before canonical zero expansion."""

    _bounded_decimal_parts(value)


def _parse_integer(value: str) -> int:
    """Parse a JSON integer with a typed refusal for oversized input."""

    sign = 1 if value[:1] in {"+", "-"} else 0
    if len(value) - sign > MAX_PROMPT_NUMBER_DIGITS:
        raise PromptFormatError(f"JSON integer exceeds the {MAX_PROMPT_NUMBER_DIGITS}-digit limit")
    try:
        return int(value)
    except (OverflowError, ValueError) as exc:
        raise PromptFormatError(f"invalid JSON integer: {exc}") from exc


def _parse_decimal(value: str) -> Decimal:
    """Parse a JSON decimal after bounding coefficient and exponent lexemes."""

    marker = value.find("e")
    upper_marker = value.find("E")
    if marker < 0 or (upper_marker >= 0 and upper_marker < marker):
        marker = upper_marker
    mantissa_end = marker if marker >= 0 else len(value)
    sign = 1 if value[:1] in {"+", "-"} else 0
    decimal_point = value.find(".", sign, mantissa_end)
    significant_digits = mantissa_end - sign - (1 if decimal_point >= 0 else 0)
    if significant_digits > MAX_PROMPT_NUMBER_DIGITS:
        raise PromptFormatError(f"Decimal coefficient exceeds the {MAX_PROMPT_NUMBER_DIGITS}-digit limit")

    if marker >= 0:
        exponent_start = marker + 1
        exponent_sign = value[exponent_start : exponent_start + 1]
        magnitude_start = exponent_start + (1 if exponent_sign in {"+", "-"} else 0)
        first_nonzero = magnitude_start
        while first_nonzero < len(value) and value[first_nonzero] == "0":
            first_nonzero += 1
        exponent_digits = len(value) - first_nonzero
        if exponent_digits > len(str(MAX_PROMPT_NUMBER_EXPONENT)):
            raise PromptFormatError(f"Decimal exponent exceeds the +/-{MAX_PROMPT_NUMBER_EXPONENT} limit")
        try:
            magnitude = int(value[first_nonzero:] or "0")
        except (OverflowError, ValueError) as exc:
            raise PromptFormatError(f"invalid Decimal exponent: {exc}") from exc
        exponent = -magnitude if exponent_sign == "-" else magnitude
        if abs(exponent) > MAX_PROMPT_NUMBER_EXPONENT:
            raise PromptFormatError(f"Decimal exponent exceeds the +/-{MAX_PROMPT_NUMBER_EXPONENT} limit")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise PromptFormatError(f"invalid JSON decimal: {exc}") from exc
    _check_decimal_bounds(result)
    return result


def _check_tree(value: Any, *, depth: int = 1, nodes: list[int] | None = None) -> None:
    """Enforce the bounded JSON tree admitted by the prompt contract."""

    count = nodes if nodes is not None else [0]
    count[0] += 1
    if count[0] > MAX_PROMPT_NODES:
        raise PromptFormatError(f"prompt JSON exceeds the {MAX_PROMPT_NODES}-node limit")
    if isinstance(value, (dict, list)):
        if depth > MAX_PROMPT_DEPTH:
            raise PromptFormatError(f"prompt JSON exceeds the depth-{MAX_PROMPT_DEPTH} limit")
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise PromptFormatError("JSON object keys must be strings")
                if any(0xD800 <= ord(char) <= 0xDFFF for char in key):
                    raise PromptFormatError("invalid Unicode surrogate in JSON object key")
                _check_tree(child, depth=depth + 1, nodes=count)
        else:
            for child in value:
                _check_tree(child, depth=depth + 1, nodes=count)
    elif isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise PromptFormatError("invalid Unicode surrogate in JSON string")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise PromptFormatError("non-finite JSON number is forbidden")
    elif isinstance(value, int) and not isinstance(value, bool):
        _check_integer_bounds(value)
    elif isinstance(value, Decimal):
        _check_decimal_bounds(value)
    elif not isinstance(value, (str, bool, type(None))):
        raise PromptFormatError(f"unsupported JSON value: {type(value).__name__}")


def _parse_json_bytes(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_PROMPT_BYTES:
        raise PromptFormatError(f"prompt JSON exceeds the {MAX_PROMPT_BYTES}-byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PromptFormatError(f"prompt JSON is not valid UTF-8: {exc}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_key_object,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_decimal,
            parse_int=_parse_integer,
        )
    except PromptFormatError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise PromptFormatError(f"malformed prompt JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PromptFormatError("prompt JSON root must be an object")
    _check_tree(value)
    return value


def _validate_document_data(data: Mapping[str, Any]) -> None:
    required = ("task", "type", "schema_version", "instructions")
    missing = [name for name in required if name not in data]
    if missing:
        raise PromptFormatError(f"prompt JSON is missing required key(s): {', '.join(missing)}")
    if data.get("type") != "prompt":
        raise PromptFormatError("prompt JSON 'type' must be 'prompt'")
    task = data.get("task")
    if not isinstance(task, str) or not task.strip():
        raise PromptFormatError("prompt JSON 'task' must contain text")
    if len(task.encode("utf-8")) > 4096:
        raise PromptFormatError("prompt JSON 'task' exceeds the 4096-byte limit")
    schema = data.get("schema_version")
    if not isinstance(schema, str) or not schema.strip():
        raise PromptFormatError("prompt JSON 'schema_version' must contain text")
    instructions = data.get("instructions")
    if not isinstance(instructions, Mapping) or not instructions:
        raise PromptFormatError("prompt JSON must provide a non-empty 'instructions' object")
    if not any(value not in (None, "", [], {}) for value in instructions.values()):
        raise PromptFormatError("prompt JSON instructions do not contain a renderable body")


def validate_prompt(data: Mapping[str, Any]) -> PromptDiskDocument:
    """Validate one decoded prompt and return its Pydantic model."""

    if not isinstance(data, Mapping):
        raise PromptFormatError("prompt JSON root must be an object")
    _check_tree(dict(data))
    try:
        model = PromptDiskDocument.model_validate(data)
    except ValidationError as exc:
        raise PromptFormatError(f"prompt Pydantic validation failed: {exc}") from exc
    _validate_document_data(data)
    return model


def load_prompt(source: bytes | bytearray | str | Path | Mapping[str, Any]) -> PromptDiskDocument:
    """Load and validate a prompt from bytes, a path, or a decoded mapping."""

    if isinstance(source, Mapping):
        return validate_prompt(source)
    if isinstance(source, Path):
        try:
            raw = source.read_bytes()
        except OSError as exc:
            raise PromptFormatError(f"cannot read prompt {source}: {exc}") from exc
    elif isinstance(source, str):
        raw = source.encode("utf-8")
    elif isinstance(source, (bytes, bytearray)):
        raw = bytes(source)
    else:
        raise TypeError(f"unsupported prompt source: {type(source).__name__}")
    return validate_prompt(_parse_json_bytes(raw))


def _model_data(model: PromptDiskDocument) -> dict[str, Any]:
    data = model.model_dump(mode="python", exclude_unset=True, exclude_none=False)
    # Pydantic defaults are intentionally emitted even when a caller built the
    # model directly rather than loading a file.
    data.setdefault("type", "prompt")
    data.setdefault("schema_version", FORMAT_VERSION)
    _validate_document_data(data)
    _check_tree(data)
    return data


def _decimal_text(value: Decimal) -> str:
    _check_decimal_bounds(value)
    if value.is_zero():
        return "0"
    sign, digits, exponent = _bounded_decimal_parts(value)
    coefficient = "".join(str(digit) for digit in digits) or "0"
    if exponent >= 0:
        text = coefficient + ("0" * exponent)
    else:
        split = len(coefficient) + exponent
        if split <= 0:
            text = "0." + ("0" * -split) + coefficient
        else:
            text = coefficient[:split] + "." + coefficient[split:]
        text = text.rstrip("0").rstrip(".")
    return ("-" if sign else "") + text


def _evidence_value(value: Any) -> Any:
    """Convert exact numeric evidence to a JSON-safe lexical value."""

    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, Mapping):
        return {str(key): _evidence_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_evidence_value(child) for child in value]
    return value


def _json_number(value: Any) -> str:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        _check_integer_bounds(value)
        try:
            text = str(value)
        except ValueError as exc:
            raise PromptFormatError(f"invalid JSON integer: {exc}") from exc
        if len(text.lstrip("+-")) > MAX_PROMPT_NUMBER_DIGITS:
            raise PromptFormatError(f"JSON integer exceeds the {MAX_PROMPT_NUMBER_DIGITS}-digit limit")
        return text
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PromptFormatError("non-finite JSON number is forbidden")
        return _decimal_text(Decimal(str(value)))
    raise PromptFormatError(f"unsupported numeric value: {type(value).__name__}")


def _canonical_json(value: Any, *, level: int = 0) -> str:
    indent = "  " * level
    child_indent = "  " * (level + 1)
    if value is None:
        return "null"
    if isinstance(value, (bool, int, float, Decimal)):
        return _json_number(value)
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise PromptFormatError("invalid Unicode surrogate in JSON string")
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise PromptFormatError("JSON object keys must be strings")
        if not value:
            return "{}"
        rows = []
        for key in sorted(value):
            rows.append(
                f"{child_indent}{json.dumps(key, ensure_ascii=False)}: {_canonical_json(value[key], level=level + 1)}"
            )
        return "{\n" + ",\n".join(rows) + f"\n{indent}}}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return "[]"
        rows = [f"{child_indent}{_canonical_json(child, level=level + 1)}" for child in value]
        return "[\n" + ",\n".join(rows) + f"\n{indent}]"
    raise PromptFormatError(f"unsupported JSON value: {type(value).__name__}")


def serialize_prompt(prompt: PromptDiskDocument | Mapping[str, Any]) -> bytes:
    """Return the one canonical pretty-printed UTF-8 representation."""

    model = prompt if isinstance(prompt, PromptDiskDocument) else validate_prompt(prompt)
    data = _model_data(model)
    result = (_canonical_json(data) + "\n").encode("utf-8")
    if len(result) > MAX_PROMPT_BYTES:
        raise PromptFormatError(f"canonical prompt exceeds the {MAX_PROMPT_BYTES}-byte limit")
    return result


def canonicalize_prompt(source: bytes | bytearray | str | Path | Mapping[str, Any]) -> bytes:
    """Parse a prompt and return canonical bytes without changing semantics."""

    return serialize_prompt(load_prompt(source))


# Stable names for consumers that use parse/serialize terminology rather than
# the repository's load/canonicalize wording.
parse_prompt = load_prompt
canonical_prompt_bytes = serialize_prompt


def snapshot_prompt(source: bytes | bytearray | str | Path | Mapping[str, Any]) -> PromptSnapshot:
    """Capture canonical bytes, digest, and the declared R094 dependency set."""

    document = load_prompt(source)
    canonical = serialize_prompt(document)
    return PromptSnapshot(document, canonical, hashlib.sha256(canonical).hexdigest())


def _coerce_for_difference(value: Any) -> Any:
    if isinstance(value, PromptSnapshot):
        return _model_data(value.document)
    if isinstance(value, PromptDiskDocument):
        return _model_data(value)
    if isinstance(value, Mapping):
        return _model_data(validate_prompt(value))
    if isinstance(value, (bytes, bytearray, str, Path)):
        return _model_data(load_prompt(value))
    raise TypeError(f"unsupported prompt comparison value: {type(value).__name__}")


def _semantic_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        sign, digits, exponent = _bounded_decimal_parts(value)
        return Decimal((sign, digits, exponent))
    if isinstance(value, float):
        return Decimal(str(value)).normalize()
    if isinstance(value, Mapping):
        return {str(key): _semantic_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_semantic_value(child) for child in value]
    return value


def _pointer(path: str, key: str | int) -> str:
    escaped = str(key).replace("~", "~0").replace("/", "~1")
    return f"{path}/{escaped}"


def _differences(before: Any, after: Any, path: str) -> list[PromptDifference]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        rows: list[PromptDifference] = []
        keys = sorted(set(before) | set(after))
        for key in keys:
            child_path = _pointer(path, key)
            if key not in before:
                rows.append(PromptDifference(child_path, "added", None, after[key]))
            elif key not in after:
                rows.append(PromptDifference(child_path, "removed", before[key], None))
            else:
                rows.extend(_differences(before[key], after[key], child_path))
        return rows
    if isinstance(before, list) and isinstance(after, list):
        rows = []
        for index in range(max(len(before), len(after))):
            child_path = _pointer(path, index)
            if index >= len(before):
                rows.append(PromptDifference(child_path, "added", None, after[index]))
            elif index >= len(after):
                rows.append(PromptDifference(child_path, "removed", before[index], None))
            else:
                rows.extend(_differences(before[index], after[index], child_path))
        return rows
    if _semantic_value(before) != _semantic_value(after) or type(before) is not type(after):
        # JSON numbers are values rather than spelling variants; Decimal and
        # float are normalized above, while bool remains distinct from int.
        numeric = isinstance(before, (int, float, Decimal)) and not isinstance(before, bool)
        numeric = numeric and isinstance(after, (int, float, Decimal)) and not isinstance(after, bool)
        if not (numeric and _semantic_value(before) == _semantic_value(after)):
            return [PromptDifference(path or "/", "changed", before, after)]
    return []


def difference_oracle(before: Any, after: Any) -> list[PromptDifference]:
    """Return exact semantic changes addressed by JSON Pointer paths."""

    left = _coerce_for_difference(before)
    right = _coerce_for_difference(after)
    return _differences(left, right, "")


# Short aliases make the published gate easy to consume without duplicating
# an alternative implementation or changing the exact oracle semantics.
prompt_difference = difference_oracle
diff_prompts = difference_oracle
difference = difference_oracle


def _validate_prompt_path(root: Path, candidate: Path) -> Path:
    """Prove an input path stays in ``root`` before any file open.

    ``relative_to_root`` is the repository-wide containment check; the
    lexical segment check and ancestor walk add the prompt gate's stronger
    rule that traversal spelling and symlink ancestors are refused even when
    they happen to resolve back inside the root.
    """

    base = root.resolve(strict=False)
    path = candidate if candidate.is_absolute() else base / candidate
    try:
        relative = path.relative_to(base)
    except ValueError as exc:
        raise PromptPathError(f"prompt path escapes repository root: {candidate}") from exc
    if any(part in {".", ".."} for part in relative.parts):
        raise PromptPathError(f"prompt path contains traversal: {candidate}")
    current = base
    for part in relative.parts:
        current /= part
        try:
            is_link = current.is_symlink()
        except OSError as exc:
            raise PromptPathError(f"cannot inspect prompt path {candidate}: {exc}") from exc
        if is_link:
            raise PromptPathError(f"prompt path contains a symlink ancestor: {candidate}")
    try:
        relative_to_root(path, base)
    except (OSError, ValueError) as exc:
        raise PromptPathError(f"prompt path escapes repository root: {candidate}") from exc
    return path


def _discover_prompt_files(root: Path) -> list[Path]:
    directories = {root / "prompts", root / "agent_utilities" / "prompts"}
    directories.update(root.glob("*/prompts"))
    files: set[Path] = set()
    for directory in sorted(directories):
        directory = _validate_prompt_path(root, directory)
        if directory.is_dir():
            files.update(
                _validate_prompt_path(root, path)
                for path in directory.rglob("*.json")
                if path.is_file() and not path.is_symlink()
            )
    return sorted(files)


def _explicit_prompt_files(root: Path, paths: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        candidate = path if path.is_absolute() else root / path
        candidate = _validate_prompt_path(root, candidate)
        if candidate.is_dir():
            files.extend(
                _validate_prompt_path(root, child)
                for child in sorted(candidate.rglob("*.json"))
                if child.is_file() and not child.is_symlink()
            )
        else:
            files.append(candidate)
    return files


def main(argv: list[str] | None = None) -> int:
    """Run the installed prompt-format hook; return 1 for findings, 2 for setup errors."""

    parser = argparse.ArgumentParser(prog=GATE_ID, description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="prompt JSON files or directories")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if not root.is_dir():
            raise PromptPathError(f"prompt repository root is not a directory: {root}")
        files = _explicit_prompt_files(root, args.paths) if args.paths else _discover_prompt_files(root)
    except PromptPathError as exc:
        print(f"Prompt format gate: CANNOT RUN: {exc}", file=sys.stderr)
        return 2
    if not files:
        print("Prompt format gate: no prompt JSON files found.")
        return 0

    failures = 0
    cannot_run = 0
    for path in files:
        try:
            safe_path = _validate_prompt_path(root, path)
            raw = safe_path.read_bytes()
            snapshot = snapshot_prompt(raw)
            if raw != snapshot.canonical_bytes:
                print(f"FAIL {path}: bytes are not canonical; rewrite with serialize_prompt")
                failures += 1
                continue
            if difference_oracle(snapshot.document, load_prompt(snapshot.canonical_bytes)):
                print(f"FAIL {path}: semantic roundtrip changed the validated document")
                failures += 1
                continue
            print(f"OK   {path} sha256={snapshot.sha256}")
        except PromptPathError as exc:
            print(f"CANNOT RUN {path}: {exc}", file=sys.stderr)
            cannot_run += 1
        except FileNotFoundError:
            print(f"CANNOT RUN {path}: prompt file does not exist", file=sys.stderr)
            cannot_run += 1
        except (OSError, PromptFormatError, TypeError) as exc:
            print(f"FAIL {path}: {exc}", file=sys.stderr)
            failures += 1
    if cannot_run:
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
