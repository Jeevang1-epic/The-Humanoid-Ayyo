"""Persistence contract for the Memory OS core."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from .models import MemoryConflict, MemoryQuery, MemoryRecord


class MemoryStore(Protocol):
    def add_memory(self, record: MemoryRecord) -> MemoryRecord: ...

    def get_memory(self, memory_id: UUID) -> MemoryRecord | None: ...

    def query_memories(self, query: MemoryQuery) -> list[MemoryRecord]: ...

    def correct_memory(
        self,
        target_id: UUID,
        replacement: MemoryRecord,
    ) -> MemoryRecord: ...

    def retract_memory(
        self,
        memory_id: UUID,
        reason: str,
        retracted_at: datetime,
    ) -> MemoryRecord: ...

    def get_revision_history(self, memory_id: UUID) -> list[MemoryRecord]: ...

    def list_conflicts(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        include_resolved: bool = False,
    ) -> list[MemoryConflict]: ...

    def close(self) -> None: ...
