"""Pure deterministic policy over normalized candidates and Memory OS records."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from ayyo_memory import MemoryConflict, MemoryRecord, MemoryStatus

from .errors import PolicyInvariantError
from .models import (
    POLICY_VERSION,
    DecisionMetadataValue,
    DecisionReason,
    DecisionType,
    NormalizedCandidate,
    NormalizedIdentity,
    ValidationDecision,
    _CORRECTION_AUTHORITY_TYPES,
)
from .normalization import canonicalize_json, normalize_identity_text


class DeterministicValidationPolicy:
    """Policy version 1 with no model, network, or persistence dependency."""

    def evaluate(
        self,
        normalized: NormalizedCandidate,
        *,
        active_memories: Sequence[MemoryRecord],
        conflicts: Sequence[MemoryConflict],
        correction_target: MemoryRecord | None = None,
        correction_target_missing: bool = False,
        revision_history: Sequence[MemoryRecord] = (),
    ) -> ValidationDecision:
        self._validate_context(normalized, active_memories, conflicts)
        candidate = normalized.candidate
        self._validate_correction_context(
            normalized,
            correction_target=correction_target,
            correction_target_missing=correction_target_missing,
            revision_history=revision_history,
        )
        exact_memories = tuple(
            record
            for record in active_memories
            if canonicalize_json(record.value) == normalized.canonical_value
        )
        variant_count = sum(
            1
            for record in active_memories
            if (record.subject, record.predicate)
            != (normalized.identity.subject, normalized.identity.predicate)
        )
        conflict_ids = self._sorted_ids(
            conflict.conflict_id for conflict in conflicts
        )

        if candidate.correction_target_id is not None:
            return self._evaluate_correction(
                normalized,
                active_memories=active_memories,
                exact_memories=exact_memories,
                conflicts=conflicts,
                correction_target=correction_target,
                correction_target_missing=correction_target_missing,
                revision_history=revision_history,
                variant_count=variant_count,
            )

        relevant_ids = self._sorted_ids(
            record.memory_id for record in active_memories
        )
        if exact_memories:
            reason = (
                DecisionReason.EXACT_VALUE_ACTIVE_WITH_CONFLICTS
                if conflict_ids
                else DecisionReason.EXACT_VALUE_ALREADY_ACTIVE
            )
            return self._decision(
                normalized,
                decision_type=DecisionType.EXACT_DUPLICATE,
                reason=reason,
                relevant_ids=relevant_ids,
                conflict_ids=conflict_ids,
                persistence_permitted=False,
                active_count=len(active_memories),
                exact_count=len(exact_memories),
                variant_count=variant_count,
            )
        if active_memories:
            reason = DecisionReason.DIFFERENT_ACTIVE_VALUE
            persistence_permitted = True
            if variant_count:
                reason = DecisionReason.CANONICAL_IDENTITY_VARIANT_REQUIRES_REVIEW
                persistence_permitted = False
            return self._decision(
                normalized,
                decision_type=DecisionType.CONFLICT_REVIEW,
                reason=reason,
                relevant_ids=relevant_ids,
                conflict_ids=conflict_ids,
                persistence_permitted=persistence_permitted,
                active_count=len(active_memories),
                exact_count=0,
                variant_count=variant_count,
            )
        return self._decision(
            normalized,
            decision_type=DecisionType.ACCEPT_NEW,
            reason=DecisionReason.NO_ACTIVE_MEMORY,
            relevant_ids=(),
            conflict_ids=(),
            persistence_permitted=True,
            active_count=0,
            exact_count=0,
            variant_count=0,
        )

    def _evaluate_correction(
        self,
        normalized: NormalizedCandidate,
        *,
        active_memories: Sequence[MemoryRecord],
        exact_memories: Sequence[MemoryRecord],
        conflicts: Sequence[MemoryConflict],
        correction_target: MemoryRecord | None,
        correction_target_missing: bool,
        revision_history: Sequence[MemoryRecord],
        variant_count: int,
    ) -> ValidationDecision:
        candidate = normalized.candidate
        active_ids = [record.memory_id for record in active_memories]
        conflict_ids = self._sorted_ids(
            conflict.conflict_id for conflict in conflicts
        )
        if correction_target_missing:
            return self._decision(
                normalized,
                decision_type=DecisionType.REJECT,
                reason=DecisionReason.CORRECTION_TARGET_NOT_FOUND,
                relevant_ids=self._sorted_ids(active_ids),
                conflict_ids=conflict_ids,
                persistence_permitted=False,
                active_count=len(active_memories),
                exact_count=len(exact_memories),
                variant_count=variant_count,
            )
        if correction_target is None:
            raise PolicyInvariantError("correction target state is missing")

        relevant_ids = self._sorted_ids((*active_ids, correction_target.memory_id))
        if candidate.provenance.provenance_type not in _CORRECTION_AUTHORITY_TYPES:
            return self._decision(
                normalized,
                decision_type=DecisionType.REJECT,
                reason=DecisionReason.CORRECTION_AUTHORITY_FORBIDDEN,
                relevant_ids=relevant_ids,
                conflict_ids=conflict_ids,
                persistence_permitted=False,
                active_count=len(active_memories),
                exact_count=len(exact_memories),
                variant_count=variant_count,
            )

        target_identity = self.identity_for_record(correction_target)
        if target_identity != normalized.identity:
            return self._decision(
                normalized,
                decision_type=DecisionType.REJECT,
                reason=DecisionReason.CORRECTION_IDENTITY_MISMATCH,
                relevant_ids=relevant_ids,
                conflict_ids=conflict_ids,
                persistence_permitted=False,
                active_count=len(active_memories),
                exact_count=len(exact_memories),
                variant_count=variant_count,
            )

        if correction_target.status is not MemoryStatus.ACTIVE:
            if revision_history:
                tip = revision_history[-1]
                tip_matches = (
                    tip.status is MemoryStatus.ACTIVE
                    and self.identity_for_record(tip) == normalized.identity
                    and canonicalize_json(tip.value) == normalized.canonical_value
                )
                if tip_matches:
                    relevant_ids = self._sorted_ids(
                        (*active_ids, correction_target.memory_id, tip.memory_id)
                    )
                    return self._decision(
                        normalized,
                        decision_type=DecisionType.EXACT_DUPLICATE,
                        reason=DecisionReason.CORRECTION_ALREADY_APPLIED,
                        relevant_ids=relevant_ids,
                        conflict_ids=conflict_ids,
                        persistence_permitted=False,
                        active_count=len(active_memories),
                        exact_count=max(1, len(exact_memories)),
                        variant_count=variant_count,
                    )
            return self._decision(
                normalized,
                decision_type=DecisionType.REJECT,
                reason=DecisionReason.CORRECTION_TARGET_NOT_ACTIVE,
                relevant_ids=relevant_ids,
                conflict_ids=conflict_ids,
                persistence_permitted=False,
                active_count=len(active_memories),
                exact_count=len(exact_memories),
                variant_count=variant_count,
            )

        if correction_target.memory_id not in active_ids:
            raise PolicyInvariantError(
                "active correction target is absent from canonical identity state"
            )
        if variant_count:
            return self._decision(
                normalized,
                decision_type=DecisionType.CONFLICT_REVIEW,
                reason=DecisionReason.CANONICAL_IDENTITY_VARIANT_REQUIRES_REVIEW,
                relevant_ids=relevant_ids,
                conflict_ids=conflict_ids,
                persistence_permitted=False,
                active_count=len(active_memories),
                exact_count=len(exact_memories),
                variant_count=variant_count,
            )
        if canonicalize_json(correction_target.value) == normalized.canonical_value:
            reason = (
                DecisionReason.EXACT_VALUE_ACTIVE_WITH_CONFLICTS
                if conflict_ids
                else DecisionReason.EXACT_VALUE_ALREADY_ACTIVE
            )
            return self._decision(
                normalized,
                decision_type=DecisionType.EXACT_DUPLICATE,
                reason=reason,
                relevant_ids=relevant_ids,
                conflict_ids=conflict_ids,
                persistence_permitted=False,
                active_count=len(active_memories),
                exact_count=max(1, len(exact_memories)),
                variant_count=0,
            )
        return self._decision(
            normalized,
            decision_type=DecisionType.APPLY_CORRECTION,
            reason=DecisionReason.EXPLICIT_CORRECTION_ALLOWED,
            relevant_ids=relevant_ids,
            conflict_ids=conflict_ids,
            persistence_permitted=True,
            active_count=len(active_memories),
            exact_count=len(exact_memories),
            variant_count=0,
        )

    @staticmethod
    def identity_for_record(record: MemoryRecord) -> NormalizedIdentity:
        if not isinstance(record, MemoryRecord):
            raise PolicyInvariantError("policy state contains a non-memory record")
        return NormalizedIdentity(
            memory_type=record.memory_type,
            subject=normalize_identity_text(record.subject, field_name="stored subject"),
            predicate=normalize_identity_text(
                record.predicate,
                field_name="stored predicate",
            ),
        )

    def _validate_context(
        self,
        normalized: NormalizedCandidate,
        active_memories: Sequence[MemoryRecord],
        conflicts: Sequence[MemoryConflict],
    ) -> None:
        if not isinstance(normalized, NormalizedCandidate):
            raise PolicyInvariantError("policy requires a normalized candidate")
        if not isinstance(active_memories, Sequence):
            raise PolicyInvariantError("policy active state must be a sequence")
        if not isinstance(conflicts, Sequence):
            raise PolicyInvariantError("policy conflict state must be a sequence")
        active_by_id: dict[UUID, MemoryRecord] = {}
        for record in active_memories:
            if not isinstance(record, MemoryRecord):
                raise PolicyInvariantError("policy state contains a non-memory record")
            if record.status is not MemoryStatus.ACTIVE:
                raise PolicyInvariantError("policy active state contains history")
            if self.identity_for_record(record) != normalized.identity:
                raise PolicyInvariantError("policy state contains an unrelated memory")
            if record.memory_id in active_by_id:
                raise PolicyInvariantError("policy active state contains duplicate IDs")
            active_by_id[record.memory_id] = record
        conflict_ids: set[UUID] = set()
        actual_pairs: set[frozenset[UUID]] = set()
        for conflict in conflicts:
            if not isinstance(conflict, MemoryConflict):
                raise PolicyInvariantError("policy conflict state is malformed")
            if conflict.resolved_at is not None:
                raise PolicyInvariantError("policy conflict state contains history")
            if (
                self.identity_for_record(conflict.left_memory) != normalized.identity
                or self.identity_for_record(conflict.right_memory)
                != normalized.identity
            ):
                raise PolicyInvariantError("policy state contains an unrelated conflict")
            if (
                conflict.left_memory.status is not MemoryStatus.ACTIVE
                or conflict.right_memory.status is not MemoryStatus.ACTIVE
            ):
                raise PolicyInvariantError(
                    "unresolved conflict references inactive memory"
                )
            pair = frozenset(
                {
                    conflict.left_memory.memory_id,
                    conflict.right_memory.memory_id,
                }
            )
            if not pair.issubset(active_by_id):
                raise PolicyInvariantError(
                    "policy conflict state is absent from active state"
                )
            if (
                active_by_id[conflict.left_memory.memory_id]
                != conflict.left_memory
                or active_by_id[conflict.right_memory.memory_id]
                != conflict.right_memory
            ):
                raise PolicyInvariantError(
                    "policy conflict state does not match active snapshots"
                )
            if conflict.conflict_id in conflict_ids or pair in actual_pairs:
                raise PolicyInvariantError("policy conflict state contains duplicates")
            if canonicalize_json(conflict.left_memory.value) == canonicalize_json(
                conflict.right_memory.value
            ):
                raise PolicyInvariantError(
                    "unresolved conflict contains equivalent values"
                )
            conflict_ids.add(conflict.conflict_id)
            actual_pairs.add(pair)

        active_records = tuple(active_by_id.values())
        expected_pairs = {
            frozenset({left.memory_id, right.memory_id})
            for index, left in enumerate(active_records)
            for right in active_records[index + 1 :]
            if (
                (left.memory_type, left.subject, left.predicate)
                == (right.memory_type, right.subject, right.predicate)
                and canonicalize_json(left.value) != canonicalize_json(right.value)
            )
        }
        if actual_pairs != expected_pairs:
            raise PolicyInvariantError(
                "policy conflict state does not match active contradictory evidence"
            )

    def _validate_correction_context(
        self,
        normalized: NormalizedCandidate,
        *,
        correction_target: MemoryRecord | None,
        correction_target_missing: bool,
        revision_history: Sequence[MemoryRecord],
    ) -> None:
        candidate = normalized.candidate
        if not isinstance(correction_target_missing, bool):
            raise PolicyInvariantError("correction target state flag must be a boolean")
        if not isinstance(revision_history, Sequence):
            raise PolicyInvariantError("revision history must be a sequence")
        if candidate.correction_target_id is None:
            if correction_target is not None or correction_target_missing:
                raise PolicyInvariantError("unexpected correction target state")
            if revision_history:
                raise PolicyInvariantError("unexpected correction revision history")
            return
        if correction_target_missing:
            if correction_target is not None:
                raise PolicyInvariantError("missing correction target cannot be present")
            if revision_history:
                raise PolicyInvariantError("missing correction target cannot have history")
            return
        if not isinstance(correction_target, MemoryRecord):
            raise PolicyInvariantError("correction target state is missing")
        if candidate.correction_target_id != correction_target.memory_id:
            raise PolicyInvariantError("correction target does not match candidate intent")
        if correction_target.status is MemoryStatus.ACTIVE:
            if revision_history:
                raise PolicyInvariantError("active correction target cannot have history")
            return
        if not revision_history:
            raise PolicyInvariantError("inactive correction target requires history")

        history_ids: set[UUID] = set()
        previous: MemoryRecord | None = None
        target_in_history = False
        target_snapshot_matches = False
        target_identity = self.identity_for_record(correction_target)
        for record in revision_history:
            if not isinstance(record, MemoryRecord):
                raise PolicyInvariantError("revision history contains a non-memory record")
            if record.memory_id in history_ids:
                raise PolicyInvariantError("revision history contains duplicate IDs")
            if previous is None:
                if record.supersedes is not None:
                    raise PolicyInvariantError("revision history does not start at its root")
            elif record.supersedes != previous.memory_id:
                raise PolicyInvariantError("revision history is not a contiguous chain")
            if self.identity_for_record(record) != target_identity:
                raise PolicyInvariantError("revision history changes logical identity")
            if record.memory_id == correction_target.memory_id:
                target_in_history = True
                target_snapshot_matches = record == correction_target
            history_ids.add(record.memory_id)
            previous = record
        if not target_in_history or not target_snapshot_matches:
            raise PolicyInvariantError(
                "revision history does not contain the correction target snapshot"
            )
        if any(
            record.status is not MemoryStatus.SUPERSEDED
            for record in revision_history[:-1]
        ):
            raise PolicyInvariantError("revision history has an active intermediate record")
        if revision_history[-1].status is MemoryStatus.SUPERSEDED:
            raise PolicyInvariantError("revision history has no terminal record")

    @staticmethod
    def _sorted_ids(values: Iterable[UUID]) -> tuple[UUID, ...]:
        return tuple(sorted(set(values), key=str))

    @staticmethod
    def _decision(
        normalized: NormalizedCandidate,
        *,
        decision_type: DecisionType,
        reason: DecisionReason,
        relevant_ids: tuple[UUID, ...],
        conflict_ids: tuple[UUID, ...],
        persistence_permitted: bool,
        active_count: int,
        exact_count: int,
        variant_count: int,
    ) -> ValidationDecision:
        candidate = normalized.candidate
        metadata: dict[str, DecisionMetadataValue] = {
            "active_memory_count": active_count,
            "correction_requested": candidate.correction_target_id is not None,
            "exact_duplicate_count": exact_count,
            "identity_was_normalized": (
                candidate.subject != normalized.identity.subject
                or candidate.predicate != normalized.identity.predicate
            ),
            "policy_version": POLICY_VERSION,
            "storage_identity_variant_count": variant_count,
        }
        return ValidationDecision(
            decision_type=decision_type,
            reason_code=reason,
            normalized_identity=normalized.identity,
            candidate=candidate,
            relevant_memory_ids=relevant_ids,
            conflict_ids=conflict_ids,
            persistence_permitted=persistence_permitted,
            explanatory_metadata=tuple(sorted(metadata.items())),
        )
