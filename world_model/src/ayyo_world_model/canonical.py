"""Bounded defensive JSON and canonical SHA-256 helpers."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Mapping, TypeAlias

from .errors import WorldModelFailureCode, WorldModelValidationError


JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 2_048
MAX_JSON_COLLECTION = 256
MAX_JSON_TEXT = 4_096
MAX_JSON_CHARACTERS = 65_536
MAX_INTEGER_BITS = 1_024
MAX_CANONICAL_NODES = 600_000
MAX_CANONICAL_CHARACTERS = 32_000_000


def _fail(detail: str) -> None:
    raise WorldModelValidationError(
        WorldModelFailureCode.MALFORMED_OBSERVATION,
        detail,
    )


def _validate_json(
    value: object,
    *,
    field_name: str,
    maximum_depth: int,
    maximum_nodes: int,
    maximum_collection: int,
    maximum_text: int,
    maximum_characters: int,
) -> None:

    stack: list[tuple[object, int, bool]] = [(value, 0, False)]
    active: set[int] = set()
    nodes = 0
    characters = 0
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(current))
            continue
        nodes += 1
        if nodes > maximum_nodes:
            _fail(f"{field_name} exceeds {maximum_nodes} JSON nodes")
        if depth > maximum_depth:
            _fail(f"{field_name} exceeds JSON depth {maximum_depth}")
        if current is None or type(current) is bool:
            continue
        if type(current) is int:
            if current.bit_length() > MAX_INTEGER_BITS:
                _fail(f"{field_name} contains an oversized integer")
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _fail(f"{field_name} contains a non-finite number")
            continue
        if type(current) is str:
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as error:
                raise WorldModelValidationError(
                    WorldModelFailureCode.MALFORMED_OBSERVATION,
                    f"{field_name} contains invalid Unicode",
                ) from error
            if len(current) > maximum_text:
                _fail(f"{field_name} contains an oversized string")
            characters += len(current)
            if characters > maximum_characters:
                _fail(f"{field_name} exceeds its aggregate text bound")
            continue
        if type(current) not in {list, dict}:
            _fail(f"{field_name} contains an unsupported value")
        identity = id(current)
        if identity in active:
            _fail(f"{field_name} contains a reference cycle")
        if len(current) > maximum_collection:
            _fail(f"{field_name} exceeds collection capacity {maximum_collection}")
        active.add(identity)
        stack.append((current, depth, True))
        if type(current) is list:
            stack.extend((item, depth + 1, False) for item in reversed(current))
        else:
            assert type(current) is dict
            for key in current:
                if type(key) is not str:
                    _fail(f"{field_name} object keys must be strings")
                if len(key) > maximum_text:
                    _fail(f"{field_name} contains an oversized object key")
                characters += len(key)
            stack.extend(
                (item, depth + 1, False)
                for item in reversed(tuple(current.values()))
            )


def validate_json(value: object, *, field_name: str = "value") -> None:
    """Validate an acyclic, resource-bounded ingress JSON tree."""

    _validate_json(
        value,
        field_name=field_name,
        maximum_depth=MAX_JSON_DEPTH,
        maximum_nodes=MAX_JSON_NODES,
        maximum_collection=MAX_JSON_COLLECTION,
        maximum_text=MAX_JSON_TEXT,
        maximum_characters=MAX_JSON_CHARACTERS,
    )


def copy_json(value: object, *, field_name: str = "value") -> JSONValue:
    validate_json(value, field_name=field_name)
    if type(value) not in {list, dict}:
        return value  # type: ignore[return-value]
    root: JSONValue = [] if type(value) is list else {}
    stack: list[tuple[list[JSONValue] | dict[str, JSONValue], list | dict]] = [
        (root, value)  # type: ignore[list-item]
    ]
    while stack:
        target, source = stack.pop()
        if type(source) is list:
            assert type(target) is list
            for item in source:
                if type(item) is list:
                    child: list[JSONValue] = []
                    target.append(child)
                    stack.append((child, item))
                elif type(item) is dict:
                    child_dict: dict[str, JSONValue] = {}
                    target.append(child_dict)
                    stack.append((child_dict, item))
                else:
                    target.append(item)
        else:
            assert type(target) is dict and type(source) is dict
            for key, item in source.items():
                if type(item) is list:
                    child_list: list[JSONValue] = []
                    target[key] = child_list
                    stack.append((child_list, item))
                elif type(item) is dict:
                    child_dict = {}
                    target[key] = child_dict
                    stack.append((child_dict, item))
                else:
                    target[key] = item
    return root


def copy_mapping(
    value: object,
    *,
    field_name: str,
) -> dict[str, JSONValue]:
    if not isinstance(value, Mapping):
        _fail(f"{field_name} must be a mapping")
    copied = copy_json(dict(value), field_name=field_name)
    assert type(copied) is dict
    return copied


def canonical_json(value: JSONValue) -> str:
    # Canonical documents aggregate already-bounded public values. Their limit
    # must represent the maximum valid World Snapshot rather than reapplying a
    # single-observation ingress bound.
    _validate_json(
        value,
        field_name="canonical document",
        maximum_depth=MAX_JSON_DEPTH + 8,
        maximum_nodes=MAX_CANONICAL_NODES,
        maximum_collection=MAX_CANONICAL_NODES,
        maximum_text=MAX_JSON_TEXT,
        maximum_characters=MAX_CANONICAL_CHARACTERS,
    )
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_document(value: JSONValue) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()
