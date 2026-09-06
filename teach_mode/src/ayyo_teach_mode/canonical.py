"""Deterministic JSON and SHA-256 helpers for demonstration evidence."""

from __future__ import annotations

from hashlib import sha256
import json


def canonical_json(document: object) -> str:
    """Return canonical UTF-8-safe JSON for an internally validated document."""
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(',', ':'),
    )


def semantic_sha256(prefix: str, document: object) -> str:
    """Return a namespaced SHA-256 identity over canonical semantic content."""
    digest = sha256(canonical_json(document).encode('utf-8')).hexdigest()
    return f'{prefix}-sha256-{digest}'
