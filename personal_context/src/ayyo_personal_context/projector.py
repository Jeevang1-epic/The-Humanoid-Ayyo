"""Pure deterministic projection from public Memory OS records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from itertools import combinations
from uuid import UUID

from ayyo_memory import MemoryConflict, MemoryRecord, MemoryStatus, MemoryType

from .errors import InconsistentSourceStateError
from .json_value import canonicalize_json
from .models import (
    ContextDomain,
    ContextEntry,
    ContextIdentity,
    ContextState,
    ContextValue,
    EvidenceReference,
    PersonalContextSnapshot,
    compute_snapshot_version,
    validate_owner_subject,
)


_DOMAIN_BY_MEMORY_TYPE = {
    MemoryType.SEMANTIC: ContextDomain.SEMANTIC,
    MemoryType.PREFERENCE: ContextDomain.PREFERENCE,
    MemoryType.SOCIAL: ContextDomain.SOCIAL,
    MemoryType.SPATIAL: ContextDomain.SPATIAL,
    MemoryType.PROCEDURAL: ContextDomain.PROCEDURAL,
}


def _identity_for(record: MemoryRecord) -> ContextIdentity:
    return ContextIdentity(
        domain=_DOMAIN_BY_MEMORY_TYPE[record.memory_type],
        subject=record.subject,
        predicate=record.predicate,
    )


def _record_signature(record: MemoryRecord) -> tuple[object, ...]:
    return (
        record.memory_id,
        record.memory_type,
        record.subject,
        record.predicate,
        canonicalize_json(record.value, field_name="memory value"),
        record.provenance.provenance_type,
        record.provenance.source_id,
        canonicalize_json(
            dict(record.provenance.details),
            field_name="memory provenance details",
        ),
        float(record.confidence),
        record.observed_at,
        record.created_at,
        record.status,
        record.status_changed_at,
        record.supersedes,
        record.revision_reason,
        record.status_reason,
        canonicalize_json(dict(record.metadata), field_name="memory metadata"),
    )


class PersonalContextProjector:
    """Project a coherent pair of Memory OS reads without side effects."""

    def project(
        self,
        owner_subject: str,
        *,
        active_memories: Sequence[MemoryRecord],
        unresolved_conflicts: Sequence[MemoryConflict],
    ) -> PersonalContextSnapshot:
        validate_owner_subject(owner_subject)
        if not isinstance(active_memories, Sequence):
            raise InconsistentSourceStateError(
                "active memory state must be a sequence"
            )
        if not isinstance(unresolved_conflicts, Sequence):
            raise InconsistentSourceStateError("conflict state must be a sequence")

        relevant_memories = self._validated_memories(owner_subject, active_memories)
        active_by_id = {record.memory_id: record for record in relevant_memories}
        conflicts = self._validated_conflicts(
            owner_subject,
            unresolved_conflicts,
            active_by_id=active_by_id,
        )
        self._require_complete_conflicts(relevant_memories, conflicts)
        entries = self._build_entries(relevant_memories, conflicts)
        return PersonalContextSnapshot(
            owner_subject=owner_subject,
            entries=entries,
            version=compute_snapshot_version(owner_subject, entries),
        )

    @staticmethod
    def _validated_memories(
        owner_subject: str,
        active_memories: Sequence[MemoryRecord],
    ) -> tuple[MemoryRecord, ...]:
        relevant: list[MemoryRecord] = []
        seen_ids: set[UUID] = set()
        for record in active_memories:
            if not isinstance(record, MemoryRecord):
                raise InconsistentSourceStateError(
                    "active memory state contains a non-memory record"
                )
            if record.subject != owner_subject:
                raise InconsistentSourceStateError(
                    "owner-filtered memory state contains another subject"
                )
            if record.status is not MemoryStatus.ACTIVE:
                raise InconsistentSourceStateError(
                    "active memory state contains an inactive record"
                )
            if record.memory_id in seen_ids:
                raise InconsistentSourceStateError(
                    "active memory state contains duplicate memory IDs"
                )
            seen_ids.add(record.memory_id)
            if record.memory_type not in _DOMAIN_BY_MEMORY_TYPE:
                continue
            relevant.append(record)
        return tuple(sorted(relevant, key=lambda record: str(record.memory_id)))

    @staticmethod
    def _validated_conflicts(
        owner_subject: str,
        unresolved_conflicts: Sequence[MemoryConflict],
        *,
        active_by_id: dict[UUID, MemoryRecord],
    ) -> tuple[MemoryConflict, ...]:
        relevant: list[MemoryConflict] = []
        conflict_ids: set[UUID] = set()
        memory_pairs: set[frozenset[UUID]] = set()
        for conflict in unresolved_conflicts:
            if not isinstance(conflict, MemoryConflict):
                raise InconsistentSourceStateError(
                    "conflict state contains a non-conflict record"
                )
            left = conflict.left_memory
            right = conflict.right_memory
            if left.subject != owner_subject or right.subject != owner_subject:
                raise InconsistentSourceStateError(
                    "owner-filtered conflict state contains another subject"
                )
            left_supported = left.memory_type in _DOMAIN_BY_MEMORY_TYPE
            right_supported = right.memory_type in _DOMAIN_BY_MEMORY_TYPE
            if not left_supported and not right_supported:
                continue
            if not left_supported or not right_supported:
                raise InconsistentSourceStateError(
                    "conflict crosses supported and excluded context domains"
                )
            if conflict.resolved_at is not None:
                raise InconsistentSourceStateError(
                    "unresolved conflict state contains a resolved conflict"
                )
            if left.status is not MemoryStatus.ACTIVE or right.status is not MemoryStatus.ACTIVE:
                raise InconsistentSourceStateError(
                    "unresolved conflict references inactive memory"
                )
            if (
                left.memory_type,
                left.subject,
                left.predicate,
            ) != (
                right.memory_type,
                right.subject,
                right.predicate,
            ):
                raise InconsistentSourceStateError(
                    "unresolved conflict changes exact Memory OS identity"
                )
            if canonicalize_json(left.value) == canonicalize_json(right.value):
                raise InconsistentSourceStateError(
                    "unresolved conflict contains equivalent values"
                )
            pair = frozenset((left.memory_id, right.memory_id))
            if conflict.conflict_id in conflict_ids or pair in memory_pairs:
                raise InconsistentSourceStateError(
                    "conflict state contains duplicate identities or pairs"
                )
            if not pair.issubset(active_by_id):
                raise InconsistentSourceStateError(
                    "unresolved conflict is absent from active memory state"
                )
            if (
                _record_signature(active_by_id[left.memory_id])
                != _record_signature(left)
                or _record_signature(active_by_id[right.memory_id])
                != _record_signature(right)
            ):
                raise InconsistentSourceStateError(
                    "conflict snapshots do not match active memory state"
                )
            conflict_ids.add(conflict.conflict_id)
            memory_pairs.add(pair)
            relevant.append(conflict)
        return tuple(sorted(relevant, key=lambda item: str(item.conflict_id)))

    @staticmethod
    def _require_complete_conflicts(
        active_memories: tuple[MemoryRecord, ...],
        conflicts: tuple[MemoryConflict, ...],
    ) -> None:
        expected_pairs = {
            frozenset((left.memory_id, right.memory_id))
            for left, right in combinations(active_memories, 2)
            if (
                left.memory_type,
                left.subject,
                left.predicate,
            )
            == (
                right.memory_type,
                right.subject,
                right.predicate,
            )
            and canonicalize_json(left.value) != canonicalize_json(right.value)
        }
        actual_pairs = {
            frozenset(
                (conflict.left_memory.memory_id, conflict.right_memory.memory_id)
            )
            for conflict in conflicts
        }
        if actual_pairs != expected_pairs:
            raise InconsistentSourceStateError(
                "unresolved conflicts do not match active contradictory evidence"
            )

    @staticmethod
    def _build_entries(
        active_memories: tuple[MemoryRecord, ...],
        conflicts: tuple[MemoryConflict, ...],
    ) -> tuple[ContextEntry, ...]:
        records_by_identity: dict[ContextIdentity, list[MemoryRecord]] = defaultdict(list)
        for record in active_memories:
            records_by_identity[_identity_for(record)].append(record)

        conflicts_by_identity: dict[ContextIdentity, list[UUID]] = defaultdict(list)
        for conflict in conflicts:
            conflicts_by_identity[_identity_for(conflict.left_memory)].append(
                conflict.conflict_id
            )

        entries: list[ContextEntry] = []
        for identity, records in records_by_identity.items():
            records_by_value: dict[str, list[MemoryRecord]] = defaultdict(list)
            for record in records:
                records_by_value[canonicalize_json(record.value)].append(record)
            values = tuple(
                ContextValue(
                    value=value_records[0].value,
                    evidence=tuple(
                        sorted(
                            (
                                EvidenceReference(
                                    memory_id=record.memory_id,
                                    provenance_type=record.provenance.provenance_type,
                                    provenance_source_id=record.provenance.source_id,
                                    provenance_details=dict(record.provenance.details),
                                    metadata=dict(record.metadata),
                                    confidence=record.confidence,
                                    observed_at=record.observed_at,
                                    recorded_at=record.created_at,
                                    supersedes=record.supersedes,
                                    revision_reason=record.revision_reason,
                                )
                                for record in value_records
                            ),
                            key=lambda reference: str(reference.memory_id),
                        )
                    ),
                )
                for _, value_records in sorted(records_by_value.items())
            )
            conflict_ids = tuple(sorted(conflicts_by_identity[identity], key=str))
            entries.append(
                ContextEntry(
                    identity=identity,
                    state=(
                        ContextState.RESOLVED
                        if len(values) == 1
                        else ContextState.CONFLICTED
                    ),
                    values=values,
                    conflict_ids=conflict_ids,
                )
            )
        return tuple(
            sorted(
                entries,
                key=lambda entry: (
                    entry.identity.domain.value,
                    entry.identity.subject,
                    entry.identity.predicate,
                ),
            )
        )
