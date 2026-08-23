"""Deterministic, non-recursive handling for JSON-compatible values."""

from __future__ import annotations

import json
import math

from ayyo_memory import JSONValue

from .errors import ContextInvariantError


def _validate_json_tree(value: object, *, field_name: str) -> None:
    stack: list[tuple[object, bool]] = [(value, False)]
    active_containers: set[int] = set()

    while stack:
        current, leaving = stack.pop()
        if leaving:
            active_containers.remove(id(current))
            continue
        if current is None or isinstance(current, (str, bool, int)):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ContextInvariantError(
                    f"{field_name} cannot contain non-finite numbers"
                )
            continue
        if isinstance(current, list):
            identity = id(current)
            if identity in active_containers:
                raise ContextInvariantError(
                    f"{field_name} cannot contain reference cycles"
                )
            active_containers.add(identity)
            stack.append((current, True))
            stack.extend((item, False) for item in reversed(current))
            continue
        if isinstance(current, dict):
            identity = id(current)
            if identity in active_containers:
                raise ContextInvariantError(
                    f"{field_name} cannot contain reference cycles"
                )
            if not all(isinstance(key, str) for key in current):
                raise ContextInvariantError(
                    f"{field_name} object keys must be strings"
                )
            active_containers.add(identity)
            stack.append((current, True))
            stack.extend((item, False) for item in reversed(tuple(current.values())))
            continue
        raise ContextInvariantError(
            f"{field_name} must contain only JSON-compatible values"
        )


def canonicalize_json(value: object, *, field_name: str = "value") -> str:
    """Encode JSON deterministically without a recursion-depth dependency."""

    _validate_json_tree(value, field_name=field_name)
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


class _JSONToken:
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def copy_json(value: object, *, field_name: str = "value") -> JSONValue:
    """Return an independent JSON tree, including for deeply nested inputs."""

    _validate_json_tree(value, field_name=field_name)
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
