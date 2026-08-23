"""Bounded canonical JSON handling owned by the Runtime Bridge."""

from __future__ import annotations

import json
import math
from typing import TypeAlias

from .errors import RuntimeValidationError


JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

MAX_RUNTIME_JSON_DEPTH = 32
MAX_RUNTIME_JSON_NODES = 4_096
MAX_RUNTIME_JSON_COLLECTION_SIZE = 256
MAX_RUNTIME_JSON_CHARACTERS = 1_000_000
MAX_RUNTIME_JSON_INTEGER_BITS = 1_024


class _Token:
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def validate_json(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception] = RuntimeValidationError,
) -> None:
    """Validate the deliberately bounded v1 JSON value space iteratively."""

    stack: list[tuple[object, int, bool]] = [(value, 0, False)]
    active_containers: set[int] = set()
    node_count = 0
    character_count = 0
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active_containers.remove(id(current))
            continue
        node_count += 1
        if node_count > MAX_RUNTIME_JSON_NODES:
            raise error_type(f"{field_name} exceeds the JSON node limit")
        if depth > MAX_RUNTIME_JSON_DEPTH:
            raise error_type(f"{field_name} exceeds the JSON depth limit")
        if type(current) is str:
            character_count += len(current)
            if character_count > MAX_RUNTIME_JSON_CHARACTERS:
                raise error_type(f"{field_name} exceeds the JSON character limit")
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as error:
                raise error_type(f"{field_name} contains invalid Unicode") from error
            continue
        if current is None or type(current) is bool:
            continue
        if type(current) is int:
            if current.bit_length() > MAX_RUNTIME_JSON_INTEGER_BITS:
                raise error_type(f"{field_name} contains an oversized integer")
            continue
        if type(current) is float:
            if not math.isfinite(current):
                raise error_type(f"{field_name} contains a non-finite number")
            continue
        if type(current) not in {list, dict}:
            raise error_type(
                f"{field_name} must contain only bounded JSON-compatible values"
            )
        if len(current) > MAX_RUNTIME_JSON_COLLECTION_SIZE:
            raise error_type(f"{field_name} exceeds the collection-size limit")
        identity = id(current)
        if identity in active_containers:
            raise error_type(f"{field_name} cannot contain reference cycles")
        active_containers.add(identity)
        stack.append((current, depth, True))
        if type(current) is list:
            stack.extend((item, depth + 1, False) for item in reversed(current))
            continue
        if not all(type(key) is str for key in current):
            raise error_type(f"{field_name} object keys must be strings")
        for key in current:
            character_count += len(key)
            if character_count > MAX_RUNTIME_JSON_CHARACTERS:
                raise error_type(f"{field_name} exceeds the JSON character limit")
            try:
                key.encode("utf-8")
            except UnicodeEncodeError as error:
                raise error_type(
                    f"{field_name} contains invalid Unicode keys"
                ) from error
        stack.extend(
            (item, depth + 1, False)
            for item in reversed(tuple(current.values()))
        )


def copy_json(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception] = RuntimeValidationError,
) -> JSONValue:
    """Validate and defensively copy a bounded JSON value."""

    validate_json(value, field_name=field_name, error_type=error_type)
    if value is None or type(value) in {str, bool, int, float}:
        return value
    root: JSONValue = [] if type(value) is list else {}
    stack: list[tuple[list[JSONValue] | dict[str, JSONValue], list | dict]] = [
        (root, value)
    ]
    while stack:
        target, source = stack.pop()
        if type(source) is list:
            assert isinstance(target, list)
            for item in source:
                if type(item) is list:
                    child_list: list[JSONValue] = []
                    target.append(child_list)
                    stack.append((child_list, item))
                elif type(item) is dict:
                    child_dict: dict[str, JSONValue] = {}
                    target.append(child_dict)
                    stack.append((child_dict, item))
                else:
                    target.append(item)
        else:
            assert isinstance(target, dict)
            for key, item in source.items():
                if type(item) is list:
                    child_list = []
                    target[key] = child_list
                    stack.append((child_list, item))
                elif type(item) is dict:
                    child_dict = {}
                    target[key] = child_dict
                    stack.append((child_dict, item))
                else:
                    target[key] = item
    return root


def canonicalize_json(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception] = RuntimeValidationError,
) -> str:
    """Return stable JSON without depending on mapping insertion order."""

    validate_json(value, field_name=field_name, error_type=error_type)
    fragments: list[str] = []
    stack: list[object] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, _Token):
            fragments.append(current.text)
        elif current is None or type(current) in {str, bool, int, float}:
            fragments.append(
                json.dumps(
                    current,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        elif type(current) is list:
            stack.append(_Token("]"))
            for index in range(len(current) - 1, -1, -1):
                stack.append(current[index])
                if index:
                    stack.append(_Token(","))
            stack.append(_Token("["))
        else:
            items = sorted(current.items())
            stack.append(_Token("}"))
            for index in range(len(items) - 1, -1, -1):
                key, item = items[index]
                stack.append(item)
                stack.append(_Token(":"))
                stack.append(
                    _Token(
                        json.dumps(
                            key,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                )
                if index:
                    stack.append(_Token(","))
            stack.append(_Token("{"))
    return "".join(fragments)
