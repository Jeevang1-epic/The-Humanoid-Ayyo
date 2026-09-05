"""Explicit, read-only staging from retained evidence to CandidateEvidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ayyo_memory import MemoryType, Provenance, ProvenanceType
from ayyo_memory_validation import CandidateEvidence, CandidateValidationError
from ayyo_working_memory import (
    WorkingMemory,
    WorkingMemoryClockRegressionError,
)
from ayyo_world_model import (
    MAX_OBSERVATION_TIME_NS,
    ObservationClock,
    ObservationIdentityError,
    SemanticEvidenceItem,
    SemanticEvidenceKind,
    SemanticEvidenceObservation,
    VisualFrameObservation,
    VisualInterpretationObservation,
    VisualSemanticCategory,
    WorldModelValidationError,
    rebuild_observation,
    visual_evaluation_reference_sha256,
)

from .errors import ConsolidationRequestError
from .models import (
    MEMORY_CONSOLIDATION_SCHEMA_VERSION,
    CandidateStagingReason,
    CandidateStagingResult,
    CandidateStagingStatus,
    ConsolidationRequest,
    EvidenceReference,
)


_OBSERVATIONAL_MEMORY_TYPES = frozenset(
    {
        MemoryType.EPISODIC,
        MemoryType.SEMANTIC,
        MemoryType.SPATIAL,
        MemoryType.FAILURE,
    }
)
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class WorkingMemoryCandidateBridge:
    """Stateless staging over one explicit Working Memory evidence selection.

    This API intentionally exposes no scan, evaluate, apply, persistence,
    correction, scheduling, or background operation.
    """

    __slots__ = ("_working_memory",)

    def __init__(self, working_memory: WorkingMemory) -> None:
        if type(working_memory) is not WorkingMemory:
            raise ConsolidationRequestError(
                "bridge requires an exact WorkingMemory instance"
            )
        self._working_memory = working_memory

    def stage(
        self,
        request: ConsolidationRequest,
        *,
        now_ns: int,
    ) -> CandidateStagingResult:
        """Stage one immutable candidate without evaluating or persisting it."""
        if type(request) is not ConsolidationRequest:
            raise ConsolidationRequestError(
                "stage requires a ConsolidationRequest"
            )
        if type(now_ns) is not int or not 0 <= now_ns <= MAX_OBSERVATION_TIME_NS:
            return _ineligible(
                CandidateStagingReason.INVALID_STAGING_TIME,
                "staging time must be non-negative source-clock nanoseconds",
            )
        config = self._working_memory.config
        if request.robot_id != config.robot_id:
            return _ineligible(
                CandidateStagingReason.ROBOT_MISMATCH,
                "request robot identity differs from Working Memory",
            )
        if request.memory_type not in _OBSERVATIONAL_MEMORY_TYPES:
            return _ineligible(
                CandidateStagingReason.MEMORY_TYPE_NOT_ALLOWED,
                "direct observations cannot stage preference, social, or procedural memory",
            )

        try:
            envelopes = self._working_memory.recent_evidence(now_ns=now_ns)
        except WorkingMemoryClockRegressionError:
            return _ineligible(
                CandidateStagingReason.SOURCE_CLOCK_REGRESSION,
                "Working Memory source clock regressed; reset is required",
            )
        except (ObservationIdentityError, WorldModelValidationError):
            return _ineligible(
                CandidateStagingReason.SOURCE_MISMATCH,
                "retained evidence failed immutable identity validation",
            )
        try:
            retained = tuple(
                rebuild_observation(envelope.observation)
                for envelope in envelopes
            )
        except (ObservationIdentityError, WorldModelValidationError):
            return _ineligible(
                CandidateStagingReason.SOURCE_MISMATCH,
                "retained evidence failed immutable identity validation",
            )

        reference = request.supporting_evidence[0]
        matches = tuple(
            observation
            for observation in retained
            if observation.observation_id == reference.observation_id
        )
        if not matches:
            return _ineligible(
                CandidateStagingReason.EVIDENCE_NOT_FOUND,
                "selected evidence is not retained in the current Working Memory epoch",
            )
        if len(matches) != 1:
            return _ineligible(
                CandidateStagingReason.SOURCE_MISMATCH,
                "selected evidence identity is not unique in retained evidence",
            )
        observation = matches[0]
        if str(observation.fingerprint) != reference.observation_fingerprint:
            return _ineligible(
                CandidateStagingReason.SOURCE_MISMATCH,
                "selected evidence fingerprint does not match retained content",
            )
        if observation.robot_id != config.robot_id:
            return _ineligible(
                CandidateStagingReason.ROBOT_MISMATCH,
                "retained evidence robot identity differs from Working Memory",
            )
        if (
            observation.provenance not in config.allowed_provenance
            or observation.provenance.clock is not config.source_clock
        ):
            return _ineligible(
                CandidateStagingReason.PROVENANCE_NOT_ALLOWED,
                "retained evidence provenance no longer matches Working Memory policy",
            )
        if observation.provenance.source_id != reference.source_id:
            return _ineligible(
                CandidateStagingReason.SOURCE_MISMATCH,
                "selected provenance source does not match retained evidence",
            )
        if config.source_clock is not ObservationClock.ROS_SYSTEM_TIME:
            return _ineligible(
                CandidateStagingReason.UNSUPPORTED_CLOCK,
                "only reviewed ROS system time is eligible for UTC staging",
            )
        if observation.observed_at_ns > now_ns:
            return _ineligible(
                CandidateStagingReason.EVIDENCE_TIME_IN_FUTURE,
                "future-dated evidence cannot enter durable-memory validation",
            )
        if now_ns - observation.observed_at_ns > config.freshness_ns:
            return _ineligible(
                CandidateStagingReason.EVIDENCE_STALE,
                "v1 stages only currently fresh evidence",
            )
        observed_at = _utc_from_system_time(observation.observed_at_ns)
        if observed_at is None:
            return _ineligible(
                CandidateStagingReason.TIMESTAMP_NOT_UTC_CONVERTIBLE,
                "source nanoseconds are not exactly representable as UTC",
            )

        if type(observation) is SemanticEvidenceObservation:
            selected = _semantic_item(observation, reference)
            if selected is None:
                return _ineligible(
                    CandidateStagingReason.SOURCE_MISMATCH,
                    "semantic evidence item does not match the retained source chain",
                )
            if not _semantic_source_chain_is_exact(observation, selected, retained):
                return _ineligible(
                    CandidateStagingReason.SOURCE_MISMATCH,
                    "semantic frame, interpretation, or detection source chain is unavailable",
                )
            if selected.confidence is None:
                return _ineligible(
                    CandidateStagingReason.MISSING_REQUIRED_CONFIDENCE,
                    "selected semantic evidence has no reviewed confidence",
                )
            if not _anonymous_semantic_claim_matches(request, selected):
                return _ineligible(
                    CandidateStagingReason.SEMANTIC_CLAIM_EXCEEDS_EVIDENCE,
                    "anonymous semantic evidence supports only its exact episodic observation",
                )
            confidence = selected.confidence
            provenance_source_id = selected.source_semantic_observation_id
            provenance_details = _semantic_provenance_details(
                observation,
                selected,
            )
        else:
            if reference.semantic_item_id is not None:
                return _ineligible(
                    CandidateStagingReason.SOURCE_MISMATCH,
                    "non-semantic evidence cannot select a semantic item",
                )
            confidence = getattr(observation, "confidence", None)
            if confidence is None:
                return _ineligible(
                    CandidateStagingReason.MISSING_REQUIRED_CONFIDENCE,
                    "selected evidence has no reviewed candidate confidence",
                )
            provenance_source_id = observation.observation_id
            provenance_details = _observation_provenance_details(observation)

        try:
            candidate = CandidateEvidence(
                memory_type=request.memory_type,
                subject=request.subject,
                predicate=request.predicate,
                value=request.value,
                provenance=Provenance(
                    provenance_type=ProvenanceType.DIRECT_OBSERVATION,
                    source_id=provenance_source_id,
                    details=provenance_details,
                ),
                confidence=confidence,
                observed_at=observed_at,
                metadata=request.metadata,
                correction_target_id=None,
                correction_reason=None,
            )
        except (CandidateValidationError, ValueError):
            return _ineligible(
                CandidateStagingReason.SOURCE_MISMATCH,
                "candidate construction rejected the derived evidence contract",
            )
        return CandidateStagingResult(
            status=CandidateStagingStatus.ELIGIBLE,
            reason=CandidateStagingReason.ELIGIBLE,
            candidate=candidate,
            detail="fresh retained evidence staged for explicit validation",
        )


def _utc_from_system_time(observed_at_ns: int) -> datetime | None:
    if observed_at_ns % 1_000:
        return None
    try:
        return _UTC_EPOCH + timedelta(microseconds=observed_at_ns // 1_000)
    except OverflowError:
        return None


def _semantic_item(
    observation: SemanticEvidenceObservation,
    reference: EvidenceReference,
) -> SemanticEvidenceItem | None:
    if reference.semantic_item_id is None:
        return None
    matches = tuple(
        item
        for item in observation.items
        if item.source_semantic_observation_id == reference.semantic_item_id
    )
    return matches[0] if len(matches) == 1 else None


def _semantic_source_chain_is_exact(
    observation: SemanticEvidenceObservation,
    item: SemanticEvidenceItem,
    retained,
) -> bool:
    frames = tuple(
        candidate
        for candidate in retained
        if candidate.observation_id == observation.source_visual_observation_id
    )
    interpretations = tuple(
        candidate
        for candidate in retained
        if candidate.observation_id
        == observation.source_interpretation_observation_id
    )
    if (
        len(frames) != 1
        or type(frames[0]) is not VisualFrameObservation
        or len(interpretations) != 1
        or type(interpretations[0]) is not VisualInterpretationObservation
    ):
        return False
    frame = frames[0]
    interpretation = interpretations[0]
    if not (
        frame.fingerprint == observation.source_visual_fingerprint
        and frame.robot_id == observation.robot_id
        and frame.sensor == observation.sensor
        and frame.observed_at_ns == observation.observed_at_ns
        and frame.provenance == observation.provenance
        and interpretation.fingerprint
        == observation.source_interpretation_fingerprint
        and interpretation.source_visual_observation_id == frame.observation_id
        and interpretation.source_visual_fingerprint == frame.fingerprint
        and interpretation.robot_id == observation.robot_id
        and interpretation.sensor == observation.sensor
        and interpretation.reference_frame_id == observation.reference_frame_id
        and interpretation.observed_at_ns == observation.observed_at_ns
        and interpretation.result_at_ns == observation.result_at_ns
        and interpretation.producer == observation.producer
        and interpretation.provenance == observation.provenance
        and interpretation.availability == observation.availability
        and visual_evaluation_reference_sha256(
            interpretation.evaluation_reference
        )
        == observation.evaluation_reference_sha256
    ):
        return False
    detections = tuple(
        detection
        for detection in interpretation.detections
        if detection.detection_id == item.source_detection_id
    )
    if len(detections) != 1:
        return False
    detection = detections[0]
    expected_kind = (
        SemanticEvidenceKind.PERSON
        if detection.category is VisualSemanticCategory.PERSON
        else SemanticEvidenceKind.OBJECT
    )
    return (
        detection.category
        in {VisualSemanticCategory.PERSON, VisualSemanticCategory.OBJECT}
        and item.kind is expected_kind
        and item.region == detection.region
        and item.confidence == detection.confidence
        and (
            item.category is None
            if item.kind is SemanticEvidenceKind.PERSON
            else item.category == detection.label
        )
    )


def _anonymous_semantic_claim_matches(
    request: ConsolidationRequest,
    item: SemanticEvidenceItem,
) -> bool:
    expected_value: dict[str, object] = {
        "anonymous": True,
        "kind": item.kind.value,
        "region": item.region.document(),
    }
    if item.kind is SemanticEvidenceKind.OBJECT:
        expected_value["category"] = item.category
    return (
        request.memory_type is MemoryType.EPISODIC
        and request.subject == request.robot_id
        and request.predicate == f"observed_anonymous_{item.kind.value}"
        and request.value == expected_value
    )


def _observation_provenance_details(observation) -> dict[str, object]:
    details: dict[str, object] = {
        "bridge_schema_version": MEMORY_CONSOLIDATION_SCHEMA_VERSION,
        "robot_id": observation.robot_id,
        "source_observation_fingerprint": str(observation.fingerprint),
        "source_observation_id": observation.observation_id,
        "source_observed_at_ns": observation.observed_at_ns,
        "source_provenance": observation.provenance.document(),
    }
    sensor = getattr(observation, "sensor", None)
    if sensor is not None:
        details["sensor"] = sensor.document()
    reference_frame_id = getattr(observation, "reference_frame_id", None)
    if reference_frame_id is not None:
        details["reference_frame_id"] = reference_frame_id
    return details


def _semantic_provenance_details(
    observation: SemanticEvidenceObservation,
    item: SemanticEvidenceItem,
) -> dict[str, object]:
    details = _observation_provenance_details(observation)
    details.update(
        {
            "evaluation_reference_sha256": (
                observation.evaluation_reference_sha256
            ),
            "producer": observation.producer.document(),
            "result_at_ns": observation.result_at_ns,
            "semantic_evidence_kind": item.kind.value,
            "semantic_item_id": item.source_semantic_observation_id,
            "source_detection_id": item.source_detection_id,
            "source_interpretation_fingerprint": str(
                observation.source_interpretation_fingerprint
            ),
            "source_interpretation_observation_id": (
                observation.source_interpretation_observation_id
            ),
            "source_visual_fingerprint": str(
                observation.source_visual_fingerprint
            ),
            "source_visual_observation_id": (
                observation.source_visual_observation_id
            ),
        }
    )
    return details


def _ineligible(
    reason: CandidateStagingReason,
    detail: str,
) -> CandidateStagingResult:
    return CandidateStagingResult(
        status=CandidateStagingStatus.INELIGIBLE,
        reason=reason,
        detail=detail,
    )
