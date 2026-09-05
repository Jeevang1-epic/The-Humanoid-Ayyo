"""Immutable public contracts for explicit evidence-backed candidate staging."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import json
import math

from ayyo_memory import JSONValue, MemoryType
from ayyo_memory_validation import CandidateEvidence, canonicalize_json
from ayyo_world_model import (
    MAX_INTEGER_BITS,
    MAX_JSON_CHARACTERS,
    MAX_JSON_COLLECTION,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_JSON_TEXT,
)

from .errors import ConsolidationRequestError


MEMORY_CONSOLIDATION_SCHEMA_VERSION = 1
MAX_SUPPORTING_EVIDENCE_COUNT = 1
MAX_CONSOLIDATION_METADATA_FIELDS = 16
MAX_CONSOLIDATION_IDENTITY_TEXT = 256
MAX_STAGING_DETAIL_TEXT = 512


class CandidateStagingStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"


class CandidateStagingReason(StrEnum):
    ELIGIBLE = "eligible"
    EVIDENCE_NOT_FOUND = "evidence_not_found"
    EVIDENCE_STALE = "evidence_stale"
    EVIDENCE_TIME_IN_FUTURE = "evidence_time_in_future"
    ROBOT_MISMATCH = "robot_mismatch"
    SOURCE_MISMATCH = "source_mismatch"
    UNSUPPORTED_CLOCK = "unsupported_clock"
    TIMESTAMP_NOT_UTC_CONVERTIBLE = "timestamp_not_utc_convertible"
    MISSING_REQUIRED_CONFIDENCE = "missing_required_confidence"
    PROVENANCE_NOT_ALLOWED = "provenance_not_allowed"
    MEMORY_TYPE_NOT_ALLOWED = "memory_type_not_allowed"
    SEMANTIC_CLAIM_EXCEEDS_EVIDENCE = "semantic_claim_exceeds_evidence"
    SOURCE_CLOCK_REGRESSION = "source_clock_regression"
    INVALID_STAGING_TIME = "invalid_staging_time"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Exact caller-selected reference to retained Working Memory evidence."""

    observation_id: str
    observation_fingerprint: str
    source_id: str
    semantic_item_id: str | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.observation_id, "observation_id"),
            (self.observation_fingerprint, "observation_fingerprint"),
            (self.source_id, "source_id"),
        ):
            _bounded_exact_text(value, field_name)
        if self.semantic_item_id is not None:
            _bounded_exact_text(self.semantic_item_id, "semantic_item_id")


@dataclass(frozen=True, slots=True, init=False)
class ConsolidationRequest:
    """A caller-proposed memory proposition bound to exact temporary evidence.

    The request intentionally has no timestamp, provenance, confidence, or
    correction fields. Those values are derived from retained evidence, or the
    request is rejected by the staging bridge.
    """

    robot_id: str
    memory_type: MemoryType
    subject: str
    predicate: str
    supporting_evidence: tuple[EvidenceReference, ...]
    _value_json: str = field(repr=False)
    _metadata_json: str = field(repr=False)

    def __init__(
        self,
        *,
        robot_id: str,
        memory_type: MemoryType,
        subject: str,
        predicate: str,
        value: JSONValue,
        supporting_evidence: Sequence[EvidenceReference],
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> None:
        _bounded_exact_text(robot_id, "robot_id")
        _bounded_exact_text(subject, "subject")
        _bounded_exact_text(predicate, "predicate")
        if not isinstance(memory_type, MemoryType):
            raise ConsolidationRequestError("memory_type must be a MemoryType")
        if not isinstance(supporting_evidence, (list, tuple)):
            raise ConsolidationRequestError(
                "supporting_evidence must be a bounded list or tuple"
            )
        references = tuple(supporting_evidence)
        if (
            not references
            or len(references) > MAX_SUPPORTING_EVIDENCE_COUNT
            or any(type(item) is not EvidenceReference for item in references)
        ):
            raise ConsolidationRequestError(
                "v1 requires exactly one typed supporting evidence reference"
            )
        candidate_metadata: Mapping[str, JSONValue] = (
            {} if metadata is None else metadata
        )
        if not isinstance(candidate_metadata, Mapping):
            raise ConsolidationRequestError("metadata must be a mapping")
        materialized_metadata = dict(candidate_metadata)
        if len(materialized_metadata) > MAX_CONSOLIDATION_METADATA_FIELDS:
            raise ConsolidationRequestError("metadata field count exceeds its bound")

        value_json, value_text = _bounded_json(value, "value")
        metadata_json, metadata_text = _bounded_json(
            materialized_metadata,
            "metadata",
        )
        if value_text + metadata_text > MAX_JSON_CHARACTERS:
            raise ConsolidationRequestError(
                "aggregate request text exceeds its bound"
            )

        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "memory_type", memory_type)
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "predicate", predicate)
        object.__setattr__(self, "supporting_evidence", references)
        object.__setattr__(self, "_value_json", value_json)
        object.__setattr__(self, "_metadata_json", metadata_json)

    @property
    def value(self) -> JSONValue:
        return json.loads(self._value_json)

    @property
    def metadata(self) -> dict[str, JSONValue]:
        return json.loads(self._metadata_json)


@dataclass(frozen=True, slots=True)
class CandidateStagingResult:
    """Typed, auditable result of one explicit candidate-staging attempt."""

    status: CandidateStagingStatus
    reason: CandidateStagingReason
    candidate: CandidateEvidence | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, CandidateStagingStatus):
            raise ConsolidationRequestError("staging status must be typed")
        if not isinstance(self.reason, CandidateStagingReason):
            raise ConsolidationRequestError("staging reason must be typed")
        if type(self.detail) is not str or len(self.detail) > MAX_STAGING_DETAIL_TEXT:
            raise ConsolidationRequestError("staging detail exceeds its text bound")
        if self.status is CandidateStagingStatus.ELIGIBLE:
            if (
                self.reason is not CandidateStagingReason.ELIGIBLE
                or type(self.candidate) is not CandidateEvidence
            ):
                raise ConsolidationRequestError(
                    "eligible result requires an eligible CandidateEvidence"
                )
        elif (
            self.reason is CandidateStagingReason.ELIGIBLE
            or self.candidate is not None
        ):
            raise ConsolidationRequestError(
                "ineligible result cannot contain a candidate"
            )


def _bounded_exact_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_CONSOLIDATION_IDENTITY_TEXT
    ):
        raise ConsolidationRequestError(
            f"{field_name} must be non-empty bounded exact text"
        )
    return value


def _bounded_json(value: object, field_name: str) -> tuple[str, int]:
    stack: list[tuple[object, int, bool]] = [(value, 1, False)]
    active: set[int] = set()
    node_count = 0
    text_count = 0

    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(current))
            continue
        node_count += 1
        if node_count > MAX_JSON_NODES:
            raise ConsolidationRequestError(f"{field_name} node count exceeds its bound")
        if depth > MAX_JSON_DEPTH:
            raise ConsolidationRequestError(f"{field_name} depth exceeds its bound")
        if current is None or isinstance(current, (bool, float)):
            if isinstance(current, float) and not math.isfinite(current):
                raise ConsolidationRequestError(
                    f"{field_name} cannot contain non-finite numbers"
                )
            continue
        if isinstance(current, int):
            if current.bit_length() > MAX_INTEGER_BITS:
                raise ConsolidationRequestError(
                    f"{field_name} integer exceeds its bit bound"
                )
            continue
        if isinstance(current, str):
            if len(current) > MAX_JSON_TEXT:
                raise ConsolidationRequestError(
                    f"{field_name} text exceeds its per-value bound"
                )
            text_count += len(current)
            continue
        if isinstance(current, (list, dict)):
            if len(current) > MAX_JSON_COLLECTION:
                raise ConsolidationRequestError(
                    f"{field_name} collection exceeds its bound"
                )
            identity = id(current)
            if identity in active:
                raise ConsolidationRequestError(
                    f"{field_name} cannot contain reference cycles"
                )
            active.add(identity)
            stack.append((current, depth, True))
            if isinstance(current, dict):
                for key in current:
                    if not isinstance(key, str):
                        raise ConsolidationRequestError(
                            f"{field_name} object keys must be strings"
                        )
                    if len(key) > MAX_JSON_TEXT:
                        raise ConsolidationRequestError(
                            f"{field_name} key exceeds its text bound"
                        )
                    text_count += len(key)
                children = tuple(current.values())
            else:
                children = tuple(current)
            stack.extend((item, depth + 1, False) for item in reversed(children))
            continue
        raise ConsolidationRequestError(
            f"{field_name} must contain only JSON-compatible values"
        )

    if text_count > MAX_JSON_CHARACTERS:
        raise ConsolidationRequestError(f"{field_name} aggregate text exceeds its bound")
    try:
        canonical = canonicalize_json(value)
    except ValueError as error:
        raise ConsolidationRequestError(
            f"{field_name} cannot be represented as deterministic JSON"
        ) from error
    if len(canonical) > MAX_JSON_CHARACTERS:
        raise ConsolidationRequestError(
            f"{field_name} serialized JSON exceeds its bound"
        )
    return canonical, text_count
