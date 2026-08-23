"""Small read-only service over the public Memory OS API."""

from __future__ import annotations

from ayyo_memory import MemoryService

from .errors import PersonalContextValidationError
from .models import (
    ContextDomain,
    ContextQueryResult,
    ContextSnapshotVersion,
    PersonalContextSnapshot,
    validate_owner_subject,
)
from .projector import PersonalContextProjector


class PersonalContextService:
    """Build deterministic context for one explicitly configured owner subject."""

    def __init__(
        self,
        memory_service: MemoryService,
        *,
        owner_subject: str,
    ) -> None:
        if not isinstance(memory_service, MemoryService):
            raise PersonalContextValidationError(
                "memory_service must be a MemoryService"
            )
        validate_owner_subject(owner_subject)
        self._memory_service = memory_service
        self._owner_subject = owner_subject
        self._projector = PersonalContextProjector()

    @property
    def owner_subject(self) -> str:
        return self._owner_subject

    def build_snapshot(self) -> PersonalContextSnapshot:
        active_memories = tuple(
            self._memory_service.query_memories(
                subject=self._owner_subject,
                active_only=True,
            )
        )
        unresolved_conflicts = tuple(
            self._memory_service.list_conflicts(
                subject=self._owner_subject,
                include_resolved=False,
            )
        )
        return self._projector.project(
            self._owner_subject,
            active_memories=active_memories,
            unresolved_conflicts=unresolved_conflicts,
        )

    def get_context(
        self,
        domain: ContextDomain,
        predicate: str,
    ) -> ContextQueryResult:
        return self.build_snapshot().get_context(domain, predicate)

    def snapshot_version(self) -> ContextSnapshotVersion:
        return self.build_snapshot().version
