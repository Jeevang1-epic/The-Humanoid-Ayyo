"""Pure reviewed policy for selecting already-staged memory candidates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from hashlib import sha256
import math

from ayyo_memory import MemoryType, ProvenanceType
from ayyo_memory_validation import (
    CandidateEvidence,
    canonicalize_json,
    normalize_identity_text,
)
from ayyo_world_model import (
    MAX_INTEGER_BITS,
    MAX_JSON_COLLECTION,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_JSON_TEXT,
)

from .errors import CandidateSelectionError
from .models import (
    MEMORY_CONSOLIDATION_SCHEMA_VERSION,
    MAX_CONSOLIDATION_IDENTITY_TEXT,
    MAX_CONSOLIDATION_METADATA_FIELDS,
    CandidateStagingReason,
    CandidateStagingStatus,
)
from .selection_models import (
    CANDIDATE_SELECTION_POLICY_ID,
    CANDIDATE_SELECTION_POLICY_VERSION,
    MAX_CANDIDATE_SELECTION_AGGREGATE_CHARACTERS,
    MAX_CANDIDATE_SELECTION_COUNT,
    MAX_CANDIDATE_SELECTION_REASONS,
    MIN_REVIEW_CONFIDENCE,
    CandidateReviewItem,
    CandidateSelectionDecision,
    CandidateSelectionItemDecision,
    CandidateSelectionOutcome,
    CandidateSelectionReason,
    ordered_selection_reasons,
)


_SUPPORTED_MEMORY_TYPES = frozenset(
    {
        MemoryType.EPISODIC,
        MemoryType.SEMANTIC,
        MemoryType.PREFERENCE,
        MemoryType.SOCIAL,
        MemoryType.SPATIAL,
        MemoryType.FAILURE,
    }
)

_PROVENANCE_BY_MEMORY_TYPE = {
    MemoryType.EPISODIC: frozenset(
        {
            ProvenanceType.DIRECT_OBSERVATION,
            ProvenanceType.EXPLICIT_OWNER_STATEMENT,
            ProvenanceType.SYSTEM_EVENT,
            ProvenanceType.TRUSTED_MANUAL_IMPORT,
        }
    ),
    MemoryType.SEMANTIC: frozenset(
        {
            ProvenanceType.DIRECT_OBSERVATION,
            ProvenanceType.EXPLICIT_OWNER_STATEMENT,
            ProvenanceType.TRUSTED_MANUAL_IMPORT,
        }
    ),
    MemoryType.PREFERENCE: frozenset(
        {
            ProvenanceType.EXPLICIT_OWNER_STATEMENT,
            ProvenanceType.TRUSTED_MANUAL_IMPORT,
        }
    ),
    MemoryType.SOCIAL: frozenset(
        {
            ProvenanceType.EXPLICIT_OWNER_STATEMENT,
            ProvenanceType.TRUSTED_MANUAL_IMPORT,
        }
    ),
    MemoryType.SPATIAL: frozenset(
        {
            ProvenanceType.DIRECT_OBSERVATION,
            ProvenanceType.TRUSTED_MANUAL_IMPORT,
        }
    ),
    MemoryType.FAILURE: frozenset(
        {
            ProvenanceType.DIRECT_OBSERVATION,
            ProvenanceType.SYSTEM_EVENT,
            ProvenanceType.TRUSTED_MANUAL_IMPORT,
        }
    ),
}

_POLICY_DOCUMENT = {
    "anonymous_semantic_behavior": "exact_anonymous_episodic_claim_only",
    "bounds": {
        "aggregate_characters": MAX_CANDIDATE_SELECTION_AGGREGATE_CHARACTERS,
        "candidate_count": MAX_CANDIDATE_SELECTION_COUNT,
        "identity_text": MAX_CONSOLIDATION_IDENTITY_TEXT,
        "json_collection": MAX_JSON_COLLECTION,
        "json_depth": MAX_JSON_DEPTH,
        "json_nodes": MAX_JSON_NODES,
        "json_text": MAX_JSON_TEXT,
        "metadata_fields": MAX_CONSOLIDATION_METADATA_FIELDS,
        "reason_count": MAX_CANDIDATE_SELECTION_REASONS,
    },
    "conflicting_candidate_behavior": "defer_all_candidates",
    "correction_behavior": "reject_selection",
    "derived_inference_behavior": "defer_for_confirmation",
    "direct_observation_behavior": {
        "requires_exact_eligible_staging": True,
        "selection_memory_type": MemoryType.EPISODIC.value,
        "selection_subject": "source_robot_id",
    },
    "duplicate_candidate_behavior": "defer_collapsed_candidate",
    "duplicate_proposition_behavior": "defer_all_candidates",
    "minimum_review_confidence": MIN_REVIEW_CONFIDENCE,
    "policy_id": CANDIDATE_SELECTION_POLICY_ID,
    "policy_version": CANDIDATE_SELECTION_POLICY_VERSION,
    "provenance_by_memory_type": {
        memory_type.value: sorted(item.value for item in provenances)
        for memory_type, provenances in sorted(
            _PROVENANCE_BY_MEMORY_TYPE.items(),
            key=lambda item: item[0].value,
        )
    },
}
CANDIDATE_SELECTION_POLICY_FINGERPRINT = (
    "candidate-selection-policy-sha256-"
    + sha256(canonicalize_json(_POLICY_DOCUMENT).encode("utf-8")).hexdigest()
)


class ReviewedMemoryCandidateSelectionPolicy:
    """Versioned stateless policy that selects candidates only for review."""

    __slots__ = ()

    @property
    def policy_id(self) -> str:
        return CANDIDATE_SELECTION_POLICY_ID

    @property
    def policy_version(self) -> int:
        return CANDIDATE_SELECTION_POLICY_VERSION

    @property
    def policy_fingerprint(self) -> str:
        return CANDIDATE_SELECTION_POLICY_FINGERPRINT

    def select(
        self,
        candidates: Sequence[CandidateReviewItem],
    ) -> CandidateSelectionDecision:
        """Return a deterministic review disposition without side effects."""
        if not isinstance(candidates, (list, tuple)):
            raise CandidateSelectionError("candidates must be a bounded list or tuple")
        input_count = len(candidates)
        if not input_count:
            return self._batch_rejection(
                input_count=0,
                reason=CandidateSelectionReason.INSUFFICIENT_EVIDENCE,
            )
        if input_count > MAX_CANDIDATE_SELECTION_COUNT:
            return self._batch_rejection(
                input_count=input_count,
                reason=CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,
            )
        items = tuple(candidates)
        if any(type(item) is not CandidateReviewItem for item in items):
            raise CandidateSelectionError("all candidates must be CandidateReviewItem")

        prepared = []
        aggregate_characters = 0
        for item in items:
            within_bounds, content_characters = _candidate_within_bounds(
                item.candidate
            )
            candidate_id = candidate_identity(item.candidate)
            aggregate_characters += content_characters
            outcome, reasons = self._base_outcome(item, within_bounds=within_bounds)
            prepared.append(
                {
                    "candidate_id": candidate_id,
                    "item": item,
                    "outcome": outcome,
                    "reasons": set(reasons),
                }
            )
        if aggregate_characters > MAX_CANDIDATE_SELECTION_AGGREGATE_CHARACTERS:
            return self._batch_rejection(
                input_count=len(items),
                reason=CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,
            )

        by_candidate_id = defaultdict(list)
        for prepared_item in prepared:
            by_candidate_id[prepared_item["candidate_id"]].append(prepared_item)

        unique = []
        for candidate_id in sorted(by_candidate_id):
            occurrences = by_candidate_id[candidate_id]
            representative = occurrences[0]
            representative["occurrence_count"] = len(occurrences)
            if len(occurrences) > 1:
                representative["outcome"] = _worst_outcome(
                    item["outcome"] for item in occurrences
                )
                representative["reasons"] = {
                    reason
                    for item in occurrences
                    for reason in item["reasons"]
                    if reason is not CandidateSelectionReason.ELIGIBLE_FOR_REVIEW
                }
                _defer_unless_rejected(
                    representative,
                    CandidateSelectionReason.DUPLICATE_CANDIDATE,
                )
            unique.append(representative)

        by_proposition = defaultdict(list)
        by_identity = defaultdict(list)
        for prepared_item in unique:
            candidate = prepared_item["item"].candidate
            identity = (
                candidate.memory_type.value,
                normalize_identity_text(candidate.subject, field_name="subject"),
                normalize_identity_text(candidate.predicate, field_name="predicate"),
            )
            by_identity[identity].append(prepared_item)
            by_proposition[(identity, candidate.canonical_value)].append(prepared_item)

        for proposition_items in by_proposition.values():
            if len(proposition_items) > 1:
                for prepared_item in proposition_items:
                    _defer_unless_rejected(
                        prepared_item,
                        CandidateSelectionReason.DUPLICATE_PROPOSITION,
                    )
        for identity_items in by_identity.values():
            if len({item["item"].candidate.canonical_value for item in identity_items}) > 1:
                for prepared_item in identity_items:
                    _defer_unless_rejected(
                        prepared_item,
                        CandidateSelectionReason.CONFLICTING_CANDIDATE,
                    )

        decisions = tuple(
            CandidateSelectionItemDecision(
                candidate_id=item["candidate_id"],
                candidate=item["item"].candidate,
                outcome=item["outcome"],
                reasons=ordered_selection_reasons(item["reasons"]),
                occurrence_count=item["occurrence_count"],
            )
            for item in unique
        )
        batch_outcome = _batch_outcome(decisions)
        batch_reasons = ordered_selection_reasons(
            reason
            for decision in decisions
            for reason in decision.reasons
            if (
                batch_outcome is CandidateSelectionOutcome.SELECT_FOR_REVIEW
                or reason is not CandidateSelectionReason.ELIGIBLE_FOR_REVIEW
            )
        )
        return _selection_decision(
            outcome=batch_outcome,
            reasons=batch_reasons,
            items=decisions,
            input_count=len(items),
        )

    def _base_outcome(
        self,
        item: CandidateReviewItem,
        *,
        within_bounds: bool,
    ) -> tuple[CandidateSelectionOutcome, tuple[CandidateSelectionReason, ...]]:
        candidate = item.candidate
        provenance = candidate.provenance
        if not within_bounds:
            return (
                CandidateSelectionOutcome.REJECT_SELECTION,
                (CandidateSelectionReason.RESOURCE_LIMIT_EXCEEDED,),
            )
        if not isinstance(candidate.memory_type, MemoryType) or (
            candidate.memory_type not in _SUPPORTED_MEMORY_TYPES
        ):
            return (
                CandidateSelectionOutcome.REJECT_SELECTION,
                (CandidateSelectionReason.UNSUPPORTED_MEMORY_TYPE,),
            )
        if (
            candidate.correction_target_id is not None
            or candidate.correction_reason is not None
        ):
            return (
                CandidateSelectionOutcome.REJECT_SELECTION,
                (CandidateSelectionReason.CORRECTION_NOT_ALLOWED,),
            )
        if not isinstance(provenance.provenance_type, ProvenanceType):
            return (
                CandidateSelectionOutcome.REJECT_SELECTION,
                (CandidateSelectionReason.UNSUPPORTED_PROVENANCE,),
            )
        if (
            isinstance(candidate.confidence, bool)
            or not isinstance(candidate.confidence, (int, float))
            or not math.isfinite(candidate.confidence)
        ):
            return (
                CandidateSelectionOutcome.REJECT_SELECTION,
                (CandidateSelectionReason.MISSING_REQUIRED_CONFIDENCE,),
            )
        if provenance.provenance_type is ProvenanceType.DIRECT_OBSERVATION:
            if not _has_exact_staging_eligibility(item):
                return (
                    CandidateSelectionOutcome.REJECT_SELECTION,
                    (CandidateSelectionReason.SOURCE_ELIGIBILITY_REQUIRED,),
                )
            if not _anonymous_semantic_claim_is_bounded(candidate):
                return (
                    CandidateSelectionOutcome.REJECT_SELECTION,
                    (CandidateSelectionReason.SEMANTIC_CLAIM_EXCEEDS_EVIDENCE,),
                )
        if provenance.provenance_type is ProvenanceType.DERIVED_INFERENCE:
            reason = (
                CandidateSelectionReason.OWNER_CONFIRMATION_REQUIRED
                if candidate.memory_type in {MemoryType.PREFERENCE, MemoryType.SOCIAL}
                else CandidateSelectionReason.PROVENANCE_REQUIRES_CONFIRMATION
            )
            return CandidateSelectionOutcome.DEFER, (reason,)
        if provenance.provenance_type not in _PROVENANCE_BY_MEMORY_TYPE[
            candidate.memory_type
        ]:
            return (
                CandidateSelectionOutcome.REJECT_SELECTION,
                (CandidateSelectionReason.PROVENANCE_NOT_ALLOWED_FOR_MEMORY_TYPE,),
            )
        if candidate.confidence < MIN_REVIEW_CONFIDENCE:
            return (
                CandidateSelectionOutcome.DEFER,
                (CandidateSelectionReason.LOW_CONFIDENCE_FOR_POLICY,),
            )
        if (
            provenance.provenance_type is ProvenanceType.DIRECT_OBSERVATION
            and (
                candidate.memory_type is not MemoryType.EPISODIC
                or candidate.subject
                != candidate.provenance.details.get("robot_id")
            )
        ):
            return (
                CandidateSelectionOutcome.DEFER,
                (CandidateSelectionReason.DIRECT_OBSERVATION_REQUIRES_CONFIRMATION,),
            )
        return (
            CandidateSelectionOutcome.SELECT_FOR_REVIEW,
            (CandidateSelectionReason.ELIGIBLE_FOR_REVIEW,),
        )

    def _batch_rejection(
        self,
        *,
        input_count: int,
        reason: CandidateSelectionReason,
    ) -> CandidateSelectionDecision:
        return _selection_decision(
            outcome=CandidateSelectionOutcome.REJECT_SELECTION,
            reasons=(reason,),
            items=(),
            input_count=input_count,
        )


def candidate_identity(candidate: CandidateEvidence) -> str:
    """Return the deterministic content identity of one immutable candidate."""
    if type(candidate) is not CandidateEvidence:
        raise CandidateSelectionError("candidate identity requires CandidateEvidence")
    provenance = candidate.provenance
    document = {
        "confidence": candidate.confidence,
        "correction_reason": candidate.correction_reason,
        "correction_target_id": (
            None
            if candidate.correction_target_id is None
            else str(candidate.correction_target_id)
        ),
        "memory_type": candidate.memory_type.value,
        "metadata": candidate.metadata,
        "observed_at": candidate.observed_at.isoformat(timespec="microseconds"),
        "predicate": candidate.predicate,
        "provenance": {
            "details": dict(provenance.details),
            "provenance_type": provenance.provenance_type.value,
            "source_id": provenance.source_id,
        },
        "schema": "ayyo.memory-candidate.v1",
        "subject": candidate.subject,
        "value": candidate.value,
    }
    return "memory-candidate-sha256-" + sha256(
        canonicalize_json(document).encode("utf-8")
    ).hexdigest()


def _has_exact_staging_eligibility(item: CandidateReviewItem) -> bool:
    result = item.staging_result
    details = item.candidate.provenance.details
    return (
        result is not None
        and result.status is CandidateStagingStatus.ELIGIBLE
        and result.reason is CandidateStagingReason.ELIGIBLE
        and result.candidate == item.candidate
        and details.get("bridge_schema_version")
        == MEMORY_CONSOLIDATION_SCHEMA_VERSION
        and type(details.get("robot_id")) is str
        and type(details.get("source_observation_id")) is str
        and type(details.get("source_observation_fingerprint")) is str
        and type(details.get("source_provenance")) is dict
    )


def _anonymous_semantic_claim_is_bounded(candidate: CandidateEvidence) -> bool:
    details = candidate.provenance.details
    kind = details.get("semantic_evidence_kind")
    if kind is None:
        return True
    if kind not in {"person", "object"}:
        return False
    value = candidate.value
    if type(value) is not dict:
        return False
    expected_keys = {"anonymous", "kind", "region"}
    if kind == "object":
        expected_keys.add("category")
    return (
        candidate.memory_type is MemoryType.EPISODIC
        and candidate.subject == details.get("robot_id")
        and candidate.predicate == f"observed_anonymous_{kind}"
        and set(value) == expected_keys
        and value.get("anonymous") is True
        and value.get("kind") == kind
        and type(value.get("region")) is dict
        and (
            kind == "person"
            or (
                type(value.get("category")) is str
                and bool(value.get("category"))
            )
        )
        and candidate.provenance.source_id == details.get("semantic_item_id")
        and type(details.get("source_detection_id")) is str
    )


def _candidate_within_bounds(candidate: CandidateEvidence) -> tuple[bool, int]:
    provenance = candidate.provenance
    if any(
        type(value) is not str
        or not value
        or len(value) > MAX_CONSOLIDATION_IDENTITY_TEXT
        for value in (
            candidate.subject,
            candidate.predicate,
            provenance.source_id,
        )
    ):
        return False, 0
    if (
        candidate.correction_reason is not None
        and (
            type(candidate.correction_reason) is not str
            or len(candidate.correction_reason) > MAX_JSON_TEXT
        )
    ):
        return False, 0
    metadata = candidate.metadata
    if len(metadata) > MAX_CONSOLIDATION_METADATA_FIELDS:
        return False, 0
    try:
        measurements = tuple(
            _json_measure(value)
            for value in (candidate.value, metadata, dict(provenance.details))
        )
    except CandidateSelectionError:
        return False, 0
    nodes = sum(item[0] for item in measurements)
    characters = (
        sum(item[1] + item[2] for item in measurements)
        + len(candidate.subject)
        + len(candidate.predicate)
        + len(provenance.source_id)
        + (
            0
            if candidate.correction_reason is None
            else len(candidate.correction_reason)
        )
    )
    return nodes <= MAX_JSON_NODES, characters


def _json_measure(value: object) -> tuple[int, int, int]:
    stack: list[tuple[object, int, bool]] = [(value, 1, False)]
    active: set[int] = set()
    nodes = 0
    text = 0
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(current))
            continue
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise CandidateSelectionError("candidate JSON exceeds structural bounds")
        if current is None or isinstance(current, bool):
            continue
        if isinstance(current, int):
            if current.bit_length() > MAX_INTEGER_BITS:
                raise CandidateSelectionError("candidate integer exceeds its bound")
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise CandidateSelectionError("candidate contains non-finite number")
            continue
        if isinstance(current, str):
            if len(current) > MAX_JSON_TEXT:
                raise CandidateSelectionError("candidate text exceeds its bound")
            text += len(current)
            continue
        if isinstance(current, (list, dict)):
            if len(current) > MAX_JSON_COLLECTION:
                raise CandidateSelectionError("candidate collection exceeds its bound")
            identity = id(current)
            if identity in active:
                raise CandidateSelectionError("candidate contains a reference cycle")
            active.add(identity)
            stack.append((current, depth, True))
            if isinstance(current, dict):
                if any(type(key) is not str for key in current):
                    raise CandidateSelectionError("candidate object key is not text")
                if any(len(key) > MAX_JSON_TEXT for key in current):
                    raise CandidateSelectionError("candidate key exceeds its bound")
                text += sum(len(key) for key in current)
                children = tuple(current.values())
            else:
                children = tuple(current)
            stack.extend((child, depth + 1, False) for child in reversed(children))
            continue
        raise CandidateSelectionError("candidate contains non-JSON data")
    canonical = canonicalize_json(value)
    return nodes, text, len(canonical)


def _defer_unless_rejected(prepared_item, reason: CandidateSelectionReason) -> None:
    if prepared_item["outcome"] is not CandidateSelectionOutcome.REJECT_SELECTION:
        prepared_item["outcome"] = CandidateSelectionOutcome.DEFER
    prepared_item["reasons"].discard(CandidateSelectionReason.ELIGIBLE_FOR_REVIEW)
    prepared_item["reasons"].add(reason)


def _batch_outcome(
    items: tuple[CandidateSelectionItemDecision, ...],
) -> CandidateSelectionOutcome:
    return _worst_outcome(item.outcome for item in items)


def _worst_outcome(outcomes) -> CandidateSelectionOutcome:
    return max(
        outcomes,
        key=lambda outcome: {
            CandidateSelectionOutcome.SELECT_FOR_REVIEW: 0,
            CandidateSelectionOutcome.DEFER: 1,
            CandidateSelectionOutcome.REJECT_SELECTION: 2,
        }[outcome],
    )


def _selection_decision(
    *,
    outcome: CandidateSelectionOutcome,
    reasons: tuple[CandidateSelectionReason, ...],
    items: tuple[CandidateSelectionItemDecision, ...],
    input_count: int,
) -> CandidateSelectionDecision:
    canonical_items = tuple(sorted(items, key=lambda item: item.candidate_id))
    document = {
        "input_candidate_count": input_count,
        "items": [
            {
                "candidate_id": item.candidate_id,
                "occurrence_count": item.occurrence_count,
                "outcome": item.outcome.value,
                "reasons": [reason.value for reason in item.reasons],
            }
            for item in canonical_items
        ],
        "outcome": outcome.value,
        "policy_fingerprint": CANDIDATE_SELECTION_POLICY_FINGERPRINT,
        "policy_id": CANDIDATE_SELECTION_POLICY_ID,
        "policy_version": CANDIDATE_SELECTION_POLICY_VERSION,
        "reasons": [reason.value for reason in reasons],
        "schema": "ayyo.memory-candidate-selection.v1",
    }
    selection_id = "candidate-selection-sha256-" + sha256(
        canonicalize_json(document).encode("utf-8")
    ).hexdigest()
    return CandidateSelectionDecision(
        policy_id=CANDIDATE_SELECTION_POLICY_ID,
        policy_version=CANDIDATE_SELECTION_POLICY_VERSION,
        policy_fingerprint=CANDIDATE_SELECTION_POLICY_FINGERPRINT,
        selection_id=selection_id,
        outcome=outcome,
        reasons=ordered_selection_reasons(reasons),
        items=canonical_items,
        input_candidate_count=input_count,
    )
