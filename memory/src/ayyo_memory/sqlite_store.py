"""SQLite persistence for provenance-aware memory records."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator
from uuid import UUID, uuid4

from .errors import (
    AlreadyRetractedError,
    InvalidCorrectionTargetError,
    InvalidMemoryDataError,
    InvalidRetractionTargetError,
    MemoryNotFoundError,
    MemoryPersistenceError,
    PersistenceConflictError,
    SchemaVersionError,
    StoreClosedError,
)
from .models import (
    JSONValue,
    MemoryConflict,
    MemoryQuery,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    Provenance,
    ProvenanceType,
    validate_nonempty_text,
    validate_utc_datetime,
)
from .sqlite_schema import CURRENT_SCHEMA_VERSION, MIGRATIONS, validate_schema


_CONFLICT_REASON = "different values for the same memory type, subject, and predicate"
_BUSY_TIMEOUT_MILLISECONDS = 5_000
_SQLITE_SYNCHRONOUS_FULL = 2


def _datetime_to_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _canonical_json(value: JSONValue | dict[str, JSONValue]) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class SQLiteMemoryStore:
    """Durable SQLite store with explicit schema and transaction boundaries."""

    def __init__(
        self,
        database_path: str | os.PathLike[str],
        *,
        create_parent: bool = False,
    ) -> None:
        path = Path(database_path)
        if path.exists() and path.is_dir():
            raise InvalidMemoryDataError("database_path must identify a file")
        if not path.parent.exists():
            if not create_parent:
                raise FileNotFoundError(path.parent)
            path.parent.mkdir(parents=True, exist_ok=True)

        self._database_path = path
        self._connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                path,
                isolation_level=None,
                timeout=5.0,
                autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
            )
            connection.row_factory = sqlite3.Row
            self._connection = connection
            self._configure_connection()
            self.migrate()
        except BaseException:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            raise

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def schema_version(self) -> int:
        row = self._require_connection().execute(
            "SELECT MAX(version) AS version FROM schema_versions"
        ).fetchone()
        if row is None or row["version"] is None:
            raise SchemaVersionError("database has no schema version")
        return int(row["version"])

    @property
    def foreign_keys_enabled(self) -> bool:
        row = self._require_connection().execute("PRAGMA foreign_keys").fetchone()
        return row is not None and int(row[0]) == 1

    def __enter__(self) -> SQLiteMemoryStore:
        self._require_connection()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def migrate(self) -> None:
        connection = self._require_connection()
        existing_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if existing_tables and "schema_versions" not in existing_tables:
            raise SchemaVersionError("refusing to adopt an unversioned non-empty database")

        with self._transaction():
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_versions ("
                "version INTEGER PRIMARY KEY, "
                "applied_at TEXT NOT NULL)"
            )
            versions = [
                int(row["version"])
                for row in connection.execute(
                    "SELECT version FROM schema_versions ORDER BY version"
                )
            ]
            if versions and versions != list(range(1, versions[-1] + 1)):
                raise SchemaVersionError("schema version history is not contiguous")
            current_version = versions[-1] if versions else 0
            if current_version > CURRENT_SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"database schema {current_version} is newer than supported "
                    f"schema {CURRENT_SCHEMA_VERSION}"
                )
            while current_version < CURRENT_SCHEMA_VERSION:
                next_version = current_version + 1
                migration = MIGRATIONS.get(next_version)
                if migration is None:
                    raise SchemaVersionError(f"no migration exists for schema {next_version}")
                migration(connection)
                connection.execute(
                    "INSERT INTO schema_versions(version, applied_at) VALUES (?, ?)",
                    (next_version, _datetime_to_text(datetime.now(timezone.utc))),
                )
                current_version = next_version
            validate_schema(connection)

    def add_memory(self, record: MemoryRecord) -> MemoryRecord:
        if record.status is not MemoryStatus.ACTIVE or record.supersedes is not None:
            raise InvalidMemoryDataError("new evidence must be an active, initial memory")
        try:
            with self._transaction():
                self._insert_memory(record)
                self._create_unresolved_conflicts(record)
        except sqlite3.IntegrityError as error:
            raise PersistenceConflictError("memory could not be persisted") from error
        return record

    def get_memory(self, memory_id: UUID) -> MemoryRecord | None:
        self._validate_memory_id(memory_id)
        row = self._require_connection().execute(
            "SELECT * FROM memories WHERE memory_id = ?",
            (str(memory_id),),
        ).fetchone()
        return self._memory_from_row(row) if row is not None else None

    def query_memories(self, query: MemoryQuery) -> list[MemoryRecord]:
        conditions: list[str] = []
        parameters: list[str] = []
        if query.memory_type is not None:
            conditions.append("memory_type = ?")
            parameters.append(query.memory_type.value)
        if query.subject is not None:
            conditions.append("subject = ?")
            parameters.append(query.subject)
        if query.predicate is not None:
            conditions.append("predicate = ?")
            parameters.append(query.predicate)
        if query.active_only:
            conditions.append("status = ?")
            parameters.append(MemoryStatus.ACTIVE.value)

        sql = "SELECT * FROM memories"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at ASC, memory_id ASC"
        rows = self._require_connection().execute(sql, parameters).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def correct_memory(
        self,
        target_id: UUID,
        replacement: MemoryRecord,
    ) -> MemoryRecord:
        self._validate_memory_id(target_id)
        if replacement.status is not MemoryStatus.ACTIVE:
            raise InvalidMemoryDataError("a correction replacement must be active")
        if replacement.supersedes != target_id:
            raise InvalidMemoryDataError("replacement must link to its correction target")

        try:
            with self._transaction():
                target = self._require_memory(target_id)
                if target.status is MemoryStatus.RETRACTED:
                    raise AlreadyRetractedError(f"memory {target_id} is retracted")
                if target.status is not MemoryStatus.ACTIVE:
                    raise InvalidCorrectionTargetError(
                        f"memory {target_id} is already superseded"
                    )
                if replacement.created_at < target.created_at:
                    raise InvalidMemoryDataError(
                        "correction timestamp cannot precede the target memory"
                    )
                if (
                    replacement.memory_type,
                    replacement.subject,
                    replacement.predicate,
                ) != (target.memory_type, target.subject, target.predicate):
                    raise InvalidCorrectionTargetError(
                        "a correction must preserve memory type, subject, and predicate"
                    )
                cursor = self._require_connection().execute(
                    "UPDATE memories SET status = ?, status_changed_at = ?, "
                    "status_reason = ? WHERE memory_id = ? AND status = ?",
                    (
                        MemoryStatus.SUPERSEDED.value,
                        _datetime_to_text(replacement.created_at),
                        replacement.revision_reason,
                        str(target_id),
                        MemoryStatus.ACTIVE.value,
                    ),
                )
                if cursor.rowcount != 1:
                    raise InvalidCorrectionTargetError(
                        f"memory {target_id} is no longer active"
                    )
                self._insert_memory(replacement)
                self._resolve_conflicts(
                    target_id,
                    resolved_at=replacement.created_at,
                    resolution_memory_id=replacement.memory_id,
                )
                if _canonical_json(target.value) != _canonical_json(replacement.value):
                    self._insert_conflict(
                        target.memory_id,
                        replacement.memory_id,
                        created_at=replacement.created_at,
                        resolved_at=replacement.created_at,
                        resolution_memory_id=replacement.memory_id,
                    )
                self._create_unresolved_conflicts(replacement)
        except sqlite3.IntegrityError as error:
            raise PersistenceConflictError("correction could not be persisted") from error
        return replacement

    def retract_memory(
        self,
        memory_id: UUID,
        reason: str,
        retracted_at: datetime,
    ) -> MemoryRecord:
        self._validate_memory_id(memory_id)
        validate_nonempty_text(reason, "retraction reason")
        validate_utc_datetime(retracted_at, "retracted_at")
        with self._transaction():
            record = self._require_memory(memory_id)
            if record.status is MemoryStatus.RETRACTED:
                raise AlreadyRetractedError(f"memory {memory_id} is already retracted")
            if record.status is not MemoryStatus.ACTIVE:
                raise InvalidRetractionTargetError(
                    f"memory {memory_id} is already superseded"
                )
            if retracted_at < record.created_at:
                raise InvalidMemoryDataError(
                    "retraction timestamp cannot precede the target memory"
                )
            cursor = self._require_connection().execute(
                "UPDATE memories SET status = ?, status_changed_at = ?, "
                "status_reason = ? WHERE memory_id = ? AND status = ?",
                (
                    MemoryStatus.RETRACTED.value,
                    _datetime_to_text(retracted_at),
                    reason,
                    str(memory_id),
                    MemoryStatus.ACTIVE.value,
                ),
            )
            if cursor.rowcount != 1:
                raise InvalidRetractionTargetError(
                    f"memory {memory_id} is no longer active"
                )
            self._resolve_conflicts(memory_id, resolved_at=retracted_at)
            return self._require_memory(memory_id)

    def get_revision_history(self, memory_id: UUID) -> list[MemoryRecord]:
        self._validate_memory_id(memory_id)
        record = self.get_memory(memory_id)
        if record is None:
            raise MemoryNotFoundError(f"memory {memory_id} was not found")

        seen: set[UUID] = set()
        while record.supersedes is not None:
            if record.memory_id in seen:
                raise MemoryPersistenceError("revision history contains a cycle")
            seen.add(record.memory_id)
            record = self._require_memory(record.supersedes)

        history: list[MemoryRecord] = []
        seen.clear()
        while True:
            if record.memory_id in seen:
                raise MemoryPersistenceError("revision history contains a cycle")
            seen.add(record.memory_id)
            history.append(record)
            row = self._require_connection().execute(
                "SELECT * FROM memories WHERE supersedes_id = ?",
                (str(record.memory_id),),
            ).fetchone()
            if row is None:
                break
            record = self._memory_from_row(row)
        return history

    def list_conflicts(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        include_resolved: bool = False,
    ) -> list[MemoryConflict]:
        conditions: list[str] = []
        parameters: list[str] = []
        if subject is not None:
            validate_nonempty_text(subject, "subject filter")
            conditions.append("left_memory.subject = ?")
            parameters.append(subject)
        if predicate is not None:
            validate_nonempty_text(predicate, "predicate filter")
            conditions.append("left_memory.predicate = ?")
            parameters.append(predicate)
        if not include_resolved:
            conditions.append("conflicts.resolved_at IS NULL")

        sql = (
            "SELECT conflicts.* FROM memory_conflicts AS conflicts "
            "JOIN memories AS left_memory "
            "ON left_memory.memory_id = conflicts.left_memory_id"
        )
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY conflicts.created_at ASC, conflicts.conflict_id ASC"

        rows = self._require_connection().execute(sql, parameters).fetchall()
        conflicts: list[MemoryConflict] = []
        for row in rows:
            left = self._require_memory(UUID(row["left_memory_id"]))
            right = self._require_memory(UUID(row["right_memory_id"]))
            conflicts.append(
                MemoryConflict(
                    conflict_id=UUID(row["conflict_id"]),
                    left_memory=left,
                    right_memory=right,
                    created_at=_datetime_from_text(row["created_at"]),
                    reason=row["reason"],
                    resolved_at=(
                        _datetime_from_text(row["resolved_at"])
                        if row["resolved_at"] is not None
                        else None
                    ),
                    resolution_memory_id=(
                        UUID(row["resolution_memory_id"])
                        if row["resolution_memory_id"] is not None
                        else None
                    ),
                )
            )
        return conflicts

    def _configure_connection(self) -> None:
        connection = self._require_connection()
        if (
            connection.autocommit != sqlite3.LEGACY_TRANSACTION_CONTROL
            or connection.isolation_level is not None
        ):
            raise MemoryPersistenceError(
                "SQLite explicit transaction control is not configured"
            )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MILLISECONDS}")
        journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "wal":
            raise MemoryPersistenceError("SQLite WAL journaling could not be enabled")
        connection.execute("PRAGMA synchronous = FULL")
        if not self.foreign_keys_enabled:
            raise MemoryPersistenceError("SQLite foreign-key enforcement could not be enabled")
        synchronous = connection.execute("PRAGMA synchronous").fetchone()
        if synchronous is None or int(synchronous[0]) != _SQLITE_SYNCHRONOUS_FULL:
            raise MemoryPersistenceError("SQLite FULL synchronization could not be enabled")
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()
        if (
            busy_timeout is None
            or int(busy_timeout[0]) != _BUSY_TIMEOUT_MILLISECONDS
        ):
            raise MemoryPersistenceError("SQLite busy timeout could not be configured")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        connection = self._require_connection()
        if connection.in_transaction:
            raise MemoryPersistenceError("nested store transactions are not supported")
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise MemoryPersistenceError("SQLite transaction could not begin") from error
        try:
            yield
        except BaseException:
            try:
                connection.rollback()
            except sqlite3.Error as rollback_error:
                raise MemoryPersistenceError(
                    "SQLite transaction rollback failed"
                ) from rollback_error
            raise
        else:
            try:
                connection.commit()
            except sqlite3.Error as error:
                try:
                    connection.rollback()
                except sqlite3.Error as rollback_error:
                    raise MemoryPersistenceError(
                        "SQLite transaction commit and rollback both failed"
                    ) from rollback_error
                raise MemoryPersistenceError("SQLite transaction commit failed") from error

    def _insert_memory(self, record: MemoryRecord) -> None:
        self._require_connection().execute(
            "INSERT INTO memories("
            "memory_id, memory_type, subject, predicate, value_json, "
            "provenance_type, provenance_source_id, provenance_details_json, "
            "confidence, observed_at, created_at, status, status_changed_at, "
            "supersedes_id, revision_reason, status_reason, metadata_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(record.memory_id),
                record.memory_type.value,
                record.subject,
                record.predicate,
                _canonical_json(record.value),
                record.provenance.provenance_type.value,
                record.provenance.source_id,
                _canonical_json(dict(record.provenance.details)),
                record.confidence,
                _datetime_to_text(record.observed_at),
                _datetime_to_text(record.created_at),
                record.status.value,
                _datetime_to_text(record.status_changed_at),
                str(record.supersedes) if record.supersedes is not None else None,
                record.revision_reason,
                record.status_reason,
                _canonical_json(dict(record.metadata)),
            ),
        )

    def _create_unresolved_conflicts(self, record: MemoryRecord) -> None:
        value_json = _canonical_json(record.value)
        rows = self._require_connection().execute(
            "SELECT memory_id, value_json FROM memories "
            "WHERE memory_type = ? AND subject = ? AND predicate = ? "
            "AND status = ? AND memory_id != ? "
            "ORDER BY created_at ASC, memory_id ASC",
            (
                record.memory_type.value,
                record.subject,
                record.predicate,
                MemoryStatus.ACTIVE.value,
                str(record.memory_id),
            ),
        ).fetchall()
        for row in rows:
            if row["value_json"] != value_json:
                self._insert_conflict(
                    UUID(row["memory_id"]),
                    record.memory_id,
                    created_at=record.created_at,
                )

    def _insert_conflict(
        self,
        first_id: UUID,
        second_id: UUID,
        *,
        created_at: datetime,
        resolved_at: datetime | None = None,
        resolution_memory_id: UUID | None = None,
    ) -> None:
        self._validate_memory_id(first_id)
        self._validate_memory_id(second_id)
        if first_id == second_id:
            raise InvalidMemoryDataError("a memory cannot conflict with itself")
        left_id, right_id = sorted((str(first_id), str(second_id)))
        self._require_connection().execute(
            "INSERT INTO memory_conflicts("
            "conflict_id, left_memory_id, right_memory_id, created_at, reason, "
            "resolved_at, resolution_memory_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                left_id,
                right_id,
                _datetime_to_text(created_at),
                _CONFLICT_REASON,
                _datetime_to_text(resolved_at) if resolved_at is not None else None,
                str(resolution_memory_id) if resolution_memory_id is not None else None,
            ),
        )

    def _resolve_conflicts(
        self,
        memory_id: UUID,
        *,
        resolved_at: datetime,
        resolution_memory_id: UUID | None = None,
    ) -> None:
        self._require_connection().execute(
            "UPDATE memory_conflicts SET resolved_at = ?, resolution_memory_id = ? "
            "WHERE resolved_at IS NULL AND "
            "(left_memory_id = ? OR right_memory_id = ?)",
            (
                _datetime_to_text(resolved_at),
                str(resolution_memory_id) if resolution_memory_id is not None else None,
                str(memory_id),
                str(memory_id),
            ),
        )

    def _require_memory(self, memory_id: UUID) -> MemoryRecord:
        record = self.get_memory(memory_id)
        if record is None:
            raise MemoryNotFoundError(f"memory {memory_id} was not found")
        return record

    @staticmethod
    def _validate_memory_id(memory_id: object) -> None:
        if not isinstance(memory_id, UUID):
            raise InvalidMemoryDataError("memory_id must be a UUID")

    def _memory_from_row(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=UUID(row["memory_id"]),
            memory_type=MemoryType(row["memory_type"]),
            subject=row["subject"],
            predicate=row["predicate"],
            value=json.loads(row["value_json"]),
            provenance=Provenance(
                provenance_type=ProvenanceType(row["provenance_type"]),
                source_id=row["provenance_source_id"],
                details=json.loads(row["provenance_details_json"]),
            ),
            confidence=float(row["confidence"]),
            observed_at=_datetime_from_text(row["observed_at"]),
            created_at=_datetime_from_text(row["created_at"]),
            status=MemoryStatus(row["status"]),
            status_changed_at=_datetime_from_text(row["status_changed_at"]),
            supersedes=(
                UUID(row["supersedes_id"])
                if row["supersedes_id"] is not None
                else None
            ),
            revision_reason=row["revision_reason"],
            status_reason=row["status_reason"],
            metadata=json.loads(row["metadata_json"]),
        )

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise StoreClosedError("memory store is closed")
        return self._connection
