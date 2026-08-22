"""Domain-facing API for creating, revising, and retrieving memories."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .errors import (
    AlreadyRetractedError,
    InvalidCorrectionTargetError,
    InvalidMemoryDataError,
    InvalidProvenanceError,
    MemoryNotFoundError,
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
from .store import MemoryStore


_CORRECTION_PROVENANCE_TYPES = frozenset(
    {
        ProvenanceType.EXPLICIT_OWNER_STATEMENT,
        ProvenanceType.TRUSTED_MANUAL_IMPORT,
    }
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryService:
    """Validated application API above a replaceable persistence store."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._store = store
        self._clock = clock
        self._id_factory = id_factory

    def create_memory(
        self,
        *,
        memory_type: MemoryType,
        subject: str,
        predicate: str,
        value: JSONValue,
        provenance: Provenance,
        confidence: float,
        observed_at: datetime,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> MemoryRecord:
        created_at = self._current_time()
        record = MemoryRecord(
            memory_id=self._next_id(),
            memory_type=memory_type,
            subject=subject,
            predicate=predicate,
            value=value,
            provenance=provenance,
            confidence=confidence,
            observed_at=observed_at,
            created_at=created_at,
            status=MemoryStatus.ACTIVE,
            status_changed_at=created_at,
            metadata={} if metadata is None else metadata,
        )
        return self._store.add_memory(record)

    def get_memory(self, memory_id: UUID) -> MemoryRecord:
        self._validate_memory_id(memory_id)
        record = self._store.get_memory(memory_id)
        if record is None:
            raise MemoryNotFoundError(f"memory {memory_id} was not found")
        return record

    def query_memories(
        self,
        *,
        memory_type: MemoryType | None = None,
        subject: str | None = None,
        predicate: str | None = None,
        active_only: bool = True,
    ) -> list[MemoryRecord]:
        return self._store.query_memories(
            MemoryQuery(
                memory_type=memory_type,
                subject=subject,
                predicate=predicate,
                active_only=active_only,
            )
        )

    def correct_memory(
        self,
        memory_id: UUID,
        *,
        value: JSONValue,
        provenance: Provenance,
        confidence: float,
        observed_at: datetime,
        reason: str,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> MemoryRecord:
        target = self.get_memory(memory_id)
        if target.status is MemoryStatus.RETRACTED:
            raise AlreadyRetractedError(f"memory {memory_id} is retracted")
        if target.status is not MemoryStatus.ACTIVE:
            raise InvalidCorrectionTargetError(
                f"memory {memory_id} is already superseded"
            )
        if not isinstance(provenance, Provenance):
            raise InvalidProvenanceError("provenance is required")
        if provenance.provenance_type not in _CORRECTION_PROVENANCE_TYPES:
            raise InvalidProvenanceError(
                "corrections require an explicit owner statement or trusted manual import"
            )
        validate_nonempty_text(reason, "correction reason")
        created_at = self._current_time()
        replacement = MemoryRecord(
            memory_id=self._next_id(),
            memory_type=target.memory_type,
            subject=target.subject,
            predicate=target.predicate,
            value=value,
            provenance=provenance,
            confidence=confidence,
            observed_at=observed_at,
            created_at=created_at,
            status=MemoryStatus.ACTIVE,
            status_changed_at=created_at,
            supersedes=target.memory_id,
            revision_reason=reason,
            metadata=target.metadata if metadata is None else metadata,
        )
        return self._store.correct_memory(target.memory_id, replacement)

    def retract_memory(self, memory_id: UUID, *, reason: str) -> MemoryRecord:
        self._validate_memory_id(memory_id)
        validate_nonempty_text(reason, "retraction reason")
        return self._store.retract_memory(memory_id, reason, self._current_time())

    def get_revision_history(self, memory_id: UUID) -> list[MemoryRecord]:
        self._validate_memory_id(memory_id)
        return self._store.get_revision_history(memory_id)

    def list_conflicts(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        include_resolved: bool = False,
    ) -> list[MemoryConflict]:
        if not isinstance(include_resolved, bool):
            raise InvalidMemoryDataError("include_resolved must be a boolean")
        return self._store.list_conflicts(
            subject=subject,
            predicate=predicate,
            include_resolved=include_resolved,
        )

    def _current_time(self) -> datetime:
        current_time = self._clock()
        validate_utc_datetime(current_time, "clock result")
        return current_time

    def _next_id(self) -> UUID:
        memory_id = self._id_factory()
        self._validate_memory_id(memory_id)
        return memory_id

    @staticmethod
    def _validate_memory_id(memory_id: object) -> None:
        if not isinstance(memory_id, UUID):
            raise InvalidMemoryDataError("memory_id must be a UUID")
