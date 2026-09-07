"""Deterministic JSON and SHA-256 helpers for learning-evaluation evidence."""

from __future__ import annotations

from hashlib import sha256
import json


def canonical_json(document: object) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(',', ':'),
    )


def semantic_sha256(prefix: str, document: object) -> str:
    digest = sha256(canonical_json(document).encode('utf-8')).hexdigest()
    return f'{prefix}-sha256-{digest}'
