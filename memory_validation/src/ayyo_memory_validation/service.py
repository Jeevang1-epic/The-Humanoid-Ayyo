"""Read-only evaluation and explicit application over the public Memory OS API."""

from __future__ import annotations

from ayyo_memory import (
    JSONValue,
    MemoryConflict,
    MemoryNotFoundError,
    MemoryRecord,
    MemoryService,
    MemoryStatus,
)

from .errors import (
    CandidateValidationError,
    DecisionNotApplicableError,
    PolicyInvariantError,
    StaleDecisionError,
)
from .models import (
    POLICY_VERSION,
    VALIDATION_METADATA_KEY,
    ApplicationResult,
    CandidateEvidence,
    DecisionType,
    NormalizedCandidate,
    NormalizedIdentity,
    ValidationDecision,
)
from .normalization import canonicalize_json, normalize_identity_text
from .policy import DeterministicValidationPolicy


class MemoryValidationService:
    """Deterministically evaluate evidence and explicitly apply allowed decisions."""

    def __init__(
        self,
        memory_service: MemoryService,
        *,
        policy: DeterministicValidationPolicy | None = None,
    ) -> None:
        if not isinstance(memory_service, MemoryService):
            raise CandidateValidationError("memory_service must be a MemoryService")
        if policy is not None and not isinstance(
            policy,
            DeterministicValidationPolicy,
        ):
            raise CandidateValidationError(
                "policy must be a DeterministicValidationPolicy"
            )
        self._memory_service = memory_service
        self._policy = policy or DeterministicValidationPolicy()

    def normalize(self, candidate: CandidateEvidence) -> NormalizedCandidate:
        if not isinstance(candidate, CandidateEvidence):
            raise CandidateValidationError("candidate must be CandidateEvidence")
        identity = NormalizedIdentity(
            memory_type=candidate.memory_type,
            subject=normalize_identity_text(candidate.subject, field_name="subject"),
            predicate=normalize_identity_text(
                candidate.predicate,
                field_name="predicate",
            ),
        )
        return NormalizedCandidate(
            candidate=candidate,
            identity=identity,
            canonical_value=candidate.canonical_value,
        )

    def evaluate(self, candidate: CandidateEvidence) -> ValidationDecision:
        normalized = self.normalize(candidate)
        active_memories = self._active_memories(normalized.identity)
        conflicts = self._active_conflicts(normalized.identity)
        correction_target: MemoryRecord | None = None
        correction_target_missing = False
        revision_history: tuple[MemoryRecord, ...] = ()

        if candidate.correction_target_id is not None:
            try:
                correction_target = self._memory_service.get_memory(
                    candidate.correction_target_id
                )
            except MemoryNotFoundError:
                correction_target_missing = True
            if (
                correction_target is not None
                and correction_target.status is not MemoryStatus.ACTIVE
            ):
                revision_history = tuple(
                    self._memory_service.get_revision_history(
                        correction_target.memory_id
                    )
                )

        return self._policy.evaluate(
            normalized,
            active_memories=active_memories,
            conflicts=conflicts,
            correction_target=correction_target,
            correction_target_missing=correction_target_missing,
            revision_history=revision_history,
        )

    def apply(self, decision: ValidationDecision) -> ApplicationResult:
        if not isinstance(decision, ValidationDecision):
            raise DecisionNotApplicableError("apply requires a ValidationDecision")
        current = self.evaluate(decision.candidate)
        if current != decision:
            if (
                decision.persistence_permitted
                and current.decision_type is DecisionType.EXACT_DUPLICATE
            ):
                return ApplicationResult(
                    decision=current,
                    mutation_applied=False,
                    memory=self._require_active_duplicate(current),
                )
            raise StaleDecisionError(
                "active memory state changed after this decision was evaluated"
            )

        if current.decision_type is DecisionType.EXACT_DUPLICATE:
            return ApplicationResult(
                decision=current,
                mutation_applied=False,
                memory=self._require_active_duplicate(current),
            )
        if not current.persistence_permitted:
            raise DecisionNotApplicableError(
                f"decision {current.decision_type.value} does not permit persistence"
            )

        candidate = current.candidate
        metadata = self._persistence_metadata(current)
        if current.decision_type in {
            DecisionType.ACCEPT_NEW,
            DecisionType.CONFLICT_REVIEW,
        }:
            memory = self._memory_service.create_memory(
                memory_type=current.normalized_identity.memory_type,
                subject=current.normalized_identity.subject,
                predicate=current.normalized_identity.predicate,
                value=candidate.value,
                provenance=candidate.provenance,
                confidence=candidate.confidence,
                observed_at=candidate.observed_at,
                metadata=metadata,
            )
        elif current.decision_type is DecisionType.APPLY_CORRECTION:
            if (
                candidate.correction_target_id is None
                or candidate.correction_reason is None
            ):
                raise PolicyInvariantError("correction decision lost correction intent")
            memory = self._memory_service.correct_memory(
                candidate.correction_target_id,
                value=candidate.value,
                provenance=candidate.provenance,
                confidence=candidate.confidence,
                observed_at=candidate.observed_at,
                reason=candidate.correction_reason,
                metadata=metadata,
            )
        else:
            raise PolicyInvariantError(
                f"unsupported mutating decision {current.decision_type.value}"
            )
        return ApplicationResult(
            decision=current,
            mutation_applied=True,
            memory=memory,
        )

    def _active_memories(
        self,
        identity: NormalizedIdentity,
    ) -> tuple[MemoryRecord, ...]:
        records = self._memory_service.query_memories(
            memory_type=identity.memory_type,
            active_only=True,
        )
        relevant = [
            record
            for record in records
            if self._policy.identity_for_record(record) == identity
        ]
        return tuple(sorted(relevant, key=lambda record: str(record.memory_id)))

    def _active_conflicts(
        self,
        identity: NormalizedIdentity,
    ) -> tuple[MemoryConflict, ...]:
        conflicts = self._memory_service.list_conflicts(include_resolved=False)
        relevant = [
            conflict
            for conflict in conflicts
            if self._policy.identity_for_record(conflict.left_memory) == identity
            and self._policy.identity_for_record(conflict.right_memory) == identity
        ]
        return tuple(sorted(relevant, key=lambda conflict: str(conflict.conflict_id)))

    def _require_active_duplicate(
        self,
        decision: ValidationDecision,
    ) -> MemoryRecord:
        for memory_id in decision.relevant_memory_ids:
            memory = self._memory_service.get_memory(memory_id)
            if (
                memory.status is MemoryStatus.ACTIVE
                and self._policy.identity_for_record(memory)
                == decision.normalized_identity
                and canonicalize_json(memory.value)
                == decision.candidate.canonical_value
            ):
                return memory
        raise PolicyInvariantError(
            "duplicate decision has no equivalent active memory"
        )

    @staticmethod
    def _persistence_metadata(
        decision: ValidationDecision,
    ) -> dict[str, JSONValue]:
        candidate = decision.candidate
        metadata = candidate.metadata
        metadata[VALIDATION_METADATA_KEY] = {
            "decision": decision.decision_type.value,
            "normalized_predicate": decision.normalized_identity.predicate,
            "normalized_subject": decision.normalized_identity.subject,
            "original_predicate": candidate.predicate,
            "original_subject": candidate.subject,
            "policy_version": POLICY_VERSION,
            "reason_code": decision.reason_code.value,
        }
        return metadata
