"""Versioned SQLite schema definitions for the Memory OS core."""

import sqlite3
from typing import Callable, Final

from .errors import SchemaVersionError


CURRENT_SCHEMA_VERSION: Final = 1

_REQUIRED_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "schema_versions": ("version", "applied_at"),
    "memories": (
        "memory_id",
        "memory_type",
        "subject",
        "predicate",
        "value_json",
        "provenance_type",
        "provenance_source_id",
        "provenance_details_json",
        "confidence",
        "observed_at",
        "created_at",
        "status",
        "status_changed_at",
        "supersedes_id",
        "revision_reason",
        "status_reason",
        "metadata_json",
    ),
    "memory_conflicts": (
        "conflict_id",
        "left_memory_id",
        "right_memory_id",
        "created_at",
        "reason",
        "resolved_at",
        "resolution_memory_id",
    ),
}

_REQUIRED_INDEXES: Final[frozenset[str]] = frozenset(
    {
        "idx_memories_supersedes",
        "idx_memories_type_status_order",
        "idx_memories_key_status_order",
        "idx_memories_subject_order",
        "idx_conflicts_left_resolution",
        "idx_conflicts_right_resolution",
    }
)

_REQUIRED_FOREIGN_KEYS: Final[frozenset[tuple[str, str, str]]] = frozenset(
    {
        ("memories", "supersedes_id", "memory_id"),
        ("memories", "left_memory_id", "memory_id"),
        ("memories", "right_memory_id", "memory_id"),
        ("memories", "resolution_memory_id", "memory_id"),
    }
)


def _migrate_to_version_1(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE memories ("
        "memory_id TEXT PRIMARY KEY, "
        "memory_type TEXT NOT NULL, "
        "subject TEXT NOT NULL, "
        "predicate TEXT NOT NULL, "
        "value_json TEXT NOT NULL, "
        "provenance_type TEXT NOT NULL, "
        "provenance_source_id TEXT NOT NULL, "
        "provenance_details_json TEXT NOT NULL, "
        "confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0), "
        "observed_at TEXT NOT NULL, "
        "created_at TEXT NOT NULL, "
        "status TEXT NOT NULL CHECK (status IN ('active', 'superseded', 'retracted')), "
        "status_changed_at TEXT NOT NULL, "
        "supersedes_id TEXT REFERENCES memories(memory_id) ON DELETE RESTRICT, "
        "revision_reason TEXT, "
        "status_reason TEXT, "
        "metadata_json TEXT NOT NULL, "
        "CHECK ((supersedes_id IS NULL AND revision_reason IS NULL) OR "
        "(supersedes_id IS NOT NULL AND length(trim(revision_reason)) > 0)), "
        "CHECK ((status = 'active' AND status_reason IS NULL) OR "
        "(status IN ('superseded', 'retracted') AND "
        "length(trim(status_reason)) > 0))"
        ")"
    )
    connection.execute(
        "CREATE UNIQUE INDEX idx_memories_supersedes "
        "ON memories(supersedes_id) WHERE supersedes_id IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX idx_memories_type_status_order "
        "ON memories(memory_type, status, created_at, memory_id)"
    )
    connection.execute(
        "CREATE INDEX idx_memories_key_status_order "
        "ON memories(memory_type, subject, predicate, status, created_at, memory_id)"
    )
    connection.execute(
        "CREATE INDEX idx_memories_subject_order "
        "ON memories(subject, status, created_at, memory_id)"
    )
    connection.execute(
        "CREATE TABLE memory_conflicts ("
        "conflict_id TEXT PRIMARY KEY, "
        "left_memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE RESTRICT, "
        "right_memory_id TEXT NOT NULL REFERENCES memories(memory_id) ON DELETE RESTRICT, "
        "created_at TEXT NOT NULL, "
        "reason TEXT NOT NULL, "
        "resolved_at TEXT, "
        "resolution_memory_id TEXT REFERENCES memories(memory_id) ON DELETE RESTRICT, "
        "UNIQUE(left_memory_id, right_memory_id), "
        "CHECK (left_memory_id < right_memory_id), "
        "CHECK (resolution_memory_id IS NULL OR resolved_at IS NOT NULL)"
        ")"
    )
    connection.execute(
        "CREATE INDEX idx_conflicts_left_resolution "
        "ON memory_conflicts(left_memory_id, resolved_at, created_at)"
    )
    connection.execute(
        "CREATE INDEX idx_conflicts_right_resolution "
        "ON memory_conflicts(right_memory_id, resolved_at, created_at)"
    )


MIGRATIONS: Final[dict[int, Callable[[sqlite3.Connection], None]]] = {
    1: _migrate_to_version_1,
}


def validate_schema(connection: sqlite3.Connection) -> None:
    """Fail closed when recorded schema history does not match schema version 1."""

    for table_name, expected_columns in _REQUIRED_COLUMNS.items():
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        actual_columns = tuple(str(row[1]) for row in rows)
        if actual_columns != expected_columns:
            raise SchemaVersionError(
                f"schema version {CURRENT_SCHEMA_VERSION} has an invalid {table_name} table"
            )

    actual_indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    if not _REQUIRED_INDEXES.issubset(actual_indexes):
        raise SchemaVersionError(
            f"schema version {CURRENT_SCHEMA_VERSION} is missing required indexes"
        )

    actual_foreign_keys: set[tuple[str, str, str]] = set()
    for table_name in ("memories", "memory_conflicts"):
        for row in connection.execute(f"PRAGMA foreign_key_list({table_name})"):
            actual_foreign_keys.add((str(row[2]), str(row[3]), str(row[4])))
    if not _REQUIRED_FOREIGN_KEYS.issubset(actual_foreign_keys):
        raise SchemaVersionError(
            f"schema version {CURRENT_SCHEMA_VERSION} is missing required foreign keys"
        )
