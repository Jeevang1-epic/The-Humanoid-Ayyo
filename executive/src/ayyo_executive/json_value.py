"""Bounded deterministic handling for Executive-owned JSON data."""

from __future__ import annotations

import json
import math
from typing import TypeAlias

from .errors import ExecutiveValidationError


JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

MAX_JSON_DEPTH = 256
MAX_JSON_NODES = 10_000
MAX_JSON_CHARACTERS = 4_000_000
MAX_JSON_INTEGER_BITS = 13_000


class _JSONToken:
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def validate_json(
    value: object,
    *,
    field_name: str,
    error_type: type[ExecutiveValidationError] = ExecutiveValidationError,
) -> None:
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
        if node_count > MAX_JSON_NODES:
            raise error_type(f"{field_name} exceeds the {MAX_JSON_NODES}-node limit")
        if depth > MAX_JSON_DEPTH:
            raise error_type(f"{field_name} exceeds the {MAX_JSON_DEPTH}-level limit")
        if isinstance(current, str):
            character_count += len(current)
            if character_count > MAX_JSON_CHARACTERS:
                raise error_type(
                    f"{field_name} exceeds the character limit"
                )
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as error:
                raise error_type(
                    f"{field_name} cannot contain invalid Unicode"
                ) from error
            continue
        if current is None or isinstance(current, bool):
            continue
        if isinstance(current, int):
            if current.bit_length() > MAX_JSON_INTEGER_BITS:
                raise error_type(f"{field_name} contains an oversized integer")
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise error_type(f"{field_name} cannot contain non-finite numbers")
            continue
        if isinstance(current, list):
            if len(current) > MAX_JSON_NODES - node_count:
                raise error_type(
                    f"{field_name} exceeds the {MAX_JSON_NODES}-node limit"
                )
            identity = id(current)
            if identity in active_containers:
                raise error_type(f"{field_name} cannot contain reference cycles")
            active_containers.add(identity)
            stack.append((current, depth, True))
            stack.extend((item, depth + 1, False) for item in reversed(current))
            continue
        if isinstance(current, dict):
            if len(current) > MAX_JSON_NODES - node_count:
                raise error_type(
                    f"{field_name} exceeds the {MAX_JSON_NODES}-node limit"
                )
            identity = id(current)
            if identity in active_containers:
                raise error_type(f"{field_name} cannot contain reference cycles")
            if not all(isinstance(key, str) for key in current):
                raise error_type(f"{field_name} object keys must be strings")
            for key in current:
                character_count += len(key)
                if character_count > MAX_JSON_CHARACTERS:
                    raise error_type(
                        f"{field_name} exceeds the character limit"
                    )
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as error:
                    raise error_type(
                        f"{field_name} cannot contain invalid Unicode keys"
                    ) from error
            active_containers.add(identity)
            stack.append((current, depth, True))
            stack.extend(
                (item, depth + 1, False)
                for item in reversed(tuple(current.values()))
            )
            continue
        raise error_type(f"{field_name} must contain only JSON-compatible values")


def canonicalize_json(
    value: object,
    *,
    field_name: str = "value",
    error_type: type[ExecutiveValidationError] = ExecutiveValidationError,
) -> str:
    validate_json(value, field_name=field_name, error_type=error_type)
    fragments: list[str] = []
    stack: list[object] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, _JSONToken):
            fragments.append(current.text)
        elif current is None or isinstance(current, (str, bool, int, float)):
            fragments.append(
                json.dumps(
                    current,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        elif isinstance(current, list):
            stack.append(_JSONToken("]"))
            for index in range(len(current) - 1, -1, -1):
                stack.append(current[index])
                if index:
                    stack.append(_JSONToken(","))
            stack.append(_JSONToken("["))
        else:
            items = sorted(current.items())
            stack.append(_JSONToken("}"))
            for index in range(len(items) - 1, -1, -1):
                key, item = items[index]
                stack.append(item)
                stack.append(_JSONToken(":"))
                stack.append(
                    _JSONToken(
                        json.dumps(
                            key,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                )
                if index:
                    stack.append(_JSONToken(","))
            stack.append(_JSONToken("{"))
    return "".join(fragments)


def copy_json(
    value: object,
    *,
    field_name: str = "value",
    error_type: type[ExecutiveValidationError] = ExecutiveValidationError,
) -> JSONValue:
    validate_json(value, field_name=field_name, error_type=error_type)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value

    root: JSONValue = [] if isinstance(value, list) else {}
    stack: list[tuple[list[JSONValue] | dict[str, JSONValue], list | dict]] = [
        (root, value)
    ]
    while stack:
        target, source = stack.pop()
        if isinstance(source, list):
            assert isinstance(target, list)
            for item in source:
                if isinstance(item, list):
                    child_list: list[JSONValue] = []
                    target.append(child_list)
                    stack.append((child_list, item))
                elif isinstance(item, dict):
                    child_dict: dict[str, JSONValue] = {}
                    target.append(child_dict)
                    stack.append((child_dict, item))
                else:
                    target.append(item)
        else:
            assert isinstance(target, dict)
            for key, item in source.items():
                if isinstance(item, list):
                    child_list = []
                    target[key] = child_list
                    stack.append((child_list, item))
                elif isinstance(item, dict):
                    child_dict = {}
                    target[key] = child_dict
                    stack.append((child_dict, item))
                else:
                    target[key] = item
    return root
