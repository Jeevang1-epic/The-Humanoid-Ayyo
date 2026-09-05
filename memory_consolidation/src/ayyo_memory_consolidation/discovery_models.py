"""Immutable contracts for bounded memory-candidate discovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import math

from ayyo_memory import MemoryType
from ayyo_memory_validation import canonicalize_json
from ayyo_working_memory import MAX_RECENT_EVIDENCE_CAPACITY
from ayyo_world_model import MAX_JSON_CHARACTERS, MAX_VISUAL_LABEL_LENGTH

from .errors import CandidateDiscoveryError
from .models import (
    MAX_CONSOLIDATION_IDENTITY_TEXT,
    ConsolidationRequest,
)


CANDIDATE_DISCOVERY_POLICY_ID = "ayyo.memory-candidate-discovery.v1"
CANDIDATE_DISCOVERY_POLICY_VERSION = 1
MAX_CANDIDATE_DISCOVERY_EVIDENCE = 64
MAX_CANDIDATE_DISCOVERY_PROPOSALS = 32
MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS = 64
MAX_CANDIDATE_DISCOVERY_REASONS = 16
MAX_CANDIDATE_DISCOVERY_AGGREGATE_CHARACTERS = MAX_JSON_CHARACTERS


class CandidateDiscoveryOutcome(StrEnum):
    """Overall disposition of one explicit discovery call."""

    PROPOSALS_DISCOVERED = "proposals_discovered"
    NO_DISCOVERABLE_PROPOSALS = "no_discoverable_proposals"
    DISCOVERY_INELIGIBLE = "discovery_ineligible"
    RESOURCE_LIMIT_REACHED = "resource_limit_reached"


class CandidateDiscoveryReason(StrEnum):
    """Stable public reasons for discovery output and bounded omissions."""

    DISCOVERABLE = "discoverable"
    NO_RETAINED_EVIDENCE = "no_retained_evidence"
    UNSUPPORTED_EVIDENCE_KIND = "unsupported_evidence_kind"
    MISSING_REQUIRED_CONFIDENCE = "missing_required_confidence"
    UNSUPPORTED_CLOCK = "unsupported_clock"
    EVIDENCE_STALE = "evidence_stale"
    EVIDENCE_TIME_IN_FUTURE = "evidence_time_in_future"
    WRONG_ROBOT = "wrong_robot"
    PROVENANCE_NOT_ALLOWED = "provenance_not_allowed"
    INVALID_SOURCE_CHAIN = "invalid_source_chain"
    TIMESTAMP_NOT_UTC_CONVERTIBLE = "timestamp_not_utc_convertible"
    PROPOSITION_NOT_SAFELY_DERIVABLE = "proposition_not_safely_derivable"
    RESOURCE_LIMIT_REACHED = "resource_limit_reached"
    SOURCE_CLOCK_REGRESSION = "source_clock_regression"
    INVALID_DISCOVERY_TIME = "invalid_discovery_time"
    INVALID_RETAINED_EVIDENCE = "invalid_retained_evidence"


_REASON_ORDER = {
    reason: index for index, reason in enumerate(CandidateDiscoveryReason)
}


def ordered_discovery_reasons(reasons) -> tuple[CandidateDiscoveryReason, ...]:
    """Return unique reasons in stable policy-defined order."""

    return tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))


@dataclass(frozen=True, slots=True)
class CandidateDiscoveryDiagnostic:
    """One bounded explanation for omitted or globally ineligible evidence."""

    reason: CandidateDiscoveryReason
    evidence_id: str | None = None
    semantic_item_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.reason, CandidateDiscoveryReason)
            or self.reason is CandidateDiscoveryReason.DISCOVERABLE
        ):
            raise CandidateDiscoveryError("discovery diagnostic reason is invalid")
        _bounded_optional_identity(self.evidence_id, "diagnostic evidence identity")
        _bounded_optional_identity(
            self.semantic_item_id,
            "diagnostic semantic-item identity",
        )
        if self.semantic_item_id is not None and self.evidence_id is None:
            raise CandidateDiscoveryError(
                "semantic-item diagnostic requires its evidence identity"
            )


@dataclass(frozen=True, slots=True)
class CandidateDiscoveryProposal:
    """One exact immutable request proposed by a versioned discovery policy."""

    policy_id: str
    policy_version: int
    policy_fingerprint: str
    proposal_id: str
    request: ConsolidationRequest

    def __post_init__(self) -> None:
        _validate_policy_identity(
            self.policy_id,
            self.policy_version,
            self.policy_fingerprint,
        )
        if type(self.request) is not ConsolidationRequest:
            raise CandidateDiscoveryError(
                "discovery proposal requires a ConsolidationRequest"
            )
        _validate_anonymous_semantic_request(self.request)
        expected_id = candidate_discovery_proposal_identity(
            self.request,
            policy_fingerprint=self.policy_fingerprint,
        )
        if self.proposal_id != expected_id:
            raise CandidateDiscoveryError(
                "discovery proposal identity does not match its exact request"
            )


@dataclass(frozen=True, slots=True)
class CandidateDiscoveryResult:
    """Canonical bounded result of one explicit Working Memory discovery call."""

    policy_id: str
    policy_version: int
    policy_fingerprint: str
    discovery_id: str
    outcome: CandidateDiscoveryOutcome
    reasons: tuple[CandidateDiscoveryReason, ...]
    proposals: tuple[CandidateDiscoveryProposal, ...]
    diagnostics: tuple[CandidateDiscoveryDiagnostic, ...]
    retained_evidence_count: int
    inspected_evidence_count: int

    def __post_init__(self) -> None:
        _validate_policy_identity(
            self.policy_id,
            self.policy_version,
            self.policy_fingerprint,
        )
        _validate_digest_identity(
            self.discovery_id,
            "memory-candidate-discovery-sha256-",
            "discovery identity",
        )
        if not isinstance(self.outcome, CandidateDiscoveryOutcome):
            raise CandidateDiscoveryError("discovery outcome must be typed")
        if (
            type(self.reasons) is not tuple
            or not self.reasons
            or len(self.reasons) > MAX_CANDIDATE_DISCOVERY_REASONS
            or any(
                not isinstance(reason, CandidateDiscoveryReason)
                for reason in self.reasons
            )
            or self.reasons != ordered_discovery_reasons(self.reasons)
        ):
            raise CandidateDiscoveryError(
                "discovery reasons must be bounded, unique, and ordered"
            )
        if (
            type(self.proposals) is not tuple
            or len(self.proposals) > MAX_CANDIDATE_DISCOVERY_PROPOSALS
            or any(
                type(proposal) is not CandidateDiscoveryProposal
                for proposal in self.proposals
            )
            or self.proposals
            != tuple(sorted(self.proposals, key=lambda item: item.proposal_id))
            or len({item.proposal_id for item in self.proposals})
            != len(self.proposals)
        ):
            raise CandidateDiscoveryError(
                "discovery proposals must be bounded, unique, and ordered"
            )
        if any(
            proposal.policy_id != self.policy_id
            or proposal.policy_version != self.policy_version
            or proposal.policy_fingerprint != self.policy_fingerprint
            for proposal in self.proposals
        ):
            raise CandidateDiscoveryError(
                "discovery proposals must retain the result policy identity"
            )
        if (
            type(self.diagnostics) is not tuple
            or len(self.diagnostics) > MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS
            or any(
                type(diagnostic) is not CandidateDiscoveryDiagnostic
                for diagnostic in self.diagnostics
            )
            or self.diagnostics
            != tuple(sorted(set(self.diagnostics), key=_diagnostic_key))
        ):
            raise CandidateDiscoveryError(
                "discovery diagnostics must be bounded, unique, and ordered"
            )
        if (
            type(self.retained_evidence_count) is not int
            or not 0
            <= self.retained_evidence_count
            <= MAX_RECENT_EVIDENCE_CAPACITY
            or type(self.inspected_evidence_count) is not int
            or not 0
            <= self.inspected_evidence_count
            <= min(
                self.retained_evidence_count,
                MAX_CANDIDATE_DISCOVERY_EVIDENCE,
            )
        ):
            raise CandidateDiscoveryError("discovery evidence counts are invalid")
        if bool(self.proposals) != (
            CandidateDiscoveryReason.DISCOVERABLE in self.reasons
        ):
            raise CandidateDiscoveryError(
                "discoverable reason must exactly track proposal presence"
            )
        if (
            self.outcome is CandidateDiscoveryOutcome.PROPOSALS_DISCOVERED
            and (
                not self.proposals
                or CandidateDiscoveryReason.RESOURCE_LIMIT_REACHED
                in self.reasons
            )
        ):
            raise CandidateDiscoveryError("discovered outcome is inconsistent")
        if (
            self.outcome is CandidateDiscoveryOutcome.NO_DISCOVERABLE_PROPOSALS
            and self.proposals
        ):
            raise CandidateDiscoveryError("empty discovery outcome has proposals")
        if (
            self.outcome is CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE
            and self.proposals
        ):
            raise CandidateDiscoveryError("ineligible discovery has proposals")
        if (
            self.outcome is CandidateDiscoveryOutcome.RESOURCE_LIMIT_REACHED
        ) != (
            CandidateDiscoveryReason.RESOURCE_LIMIT_REACHED in self.reasons
        ):
            raise CandidateDiscoveryError(
                "resource-limited outcome must retain its reason"
            )
        expected_reasons = {item.reason for item in self.diagnostics}
        if self.proposals:
            expected_reasons.add(CandidateDiscoveryReason.DISCOVERABLE)
        if set(self.reasons) != expected_reasons:
            raise CandidateDiscoveryError(
                "discovery reasons do not summarize proposals and diagnostics"
            )
        expected_id = candidate_discovery_result_identity(
            policy_fingerprint=self.policy_fingerprint,
            outcome=self.outcome,
            reasons=self.reasons,
            proposals=self.proposals,
            diagnostics=self.diagnostics,
            retained_evidence_count=self.retained_evidence_count,
            inspected_evidence_count=self.inspected_evidence_count,
        )
        if self.discovery_id != expected_id:
            raise CandidateDiscoveryError(
                "discovery identity does not match its canonical result"
            )

    @property
    def proposal_count(self) -> int:
        return len(self.proposals)

    @property
    def requests(self) -> tuple[ConsolidationRequest, ...]:
        return tuple(proposal.request for proposal in self.proposals)


def candidate_discovery_proposal_identity(
    request: ConsolidationRequest,
    *,
    policy_fingerprint: str,
) -> str:
    """Return the canonical identity of one exact proposal and evidence binding."""

    if type(request) is not ConsolidationRequest:
        raise CandidateDiscoveryError(
            "proposal identity requires a ConsolidationRequest"
        )
    _validate_digest_identity(
        policy_fingerprint,
        "memory-candidate-discovery-policy-sha256-",
        "discovery policy fingerprint",
    )
    document = {
        "policy_fingerprint": policy_fingerprint,
        "request": _request_document(request),
        "schema": "ayyo.memory-candidate-discovery-proposal.v1",
    }
    return "memory-candidate-discovery-proposal-sha256-" + sha256(
        canonicalize_json(document).encode("utf-8")
    ).hexdigest()


def candidate_discovery_result_identity(
    *,
    policy_fingerprint: str,
    outcome: CandidateDiscoveryOutcome,
    reasons: tuple[CandidateDiscoveryReason, ...],
    proposals: tuple[CandidateDiscoveryProposal, ...],
    diagnostics: tuple[CandidateDiscoveryDiagnostic, ...],
    retained_evidence_count: int,
    inspected_evidence_count: int,
) -> str:
    """Return the deterministic identity of one complete discovery result."""

    document = {
        "diagnostics": [
            {
                "evidence_id": item.evidence_id,
                "reason": item.reason.value,
                "semantic_item_id": item.semantic_item_id,
            }
            for item in diagnostics
        ],
        "inspected_evidence_count": inspected_evidence_count,
        "outcome": outcome.value,
        "policy_fingerprint": policy_fingerprint,
        "proposals": [item.proposal_id for item in proposals],
        "reasons": [reason.value for reason in reasons],
        "retained_evidence_count": retained_evidence_count,
        "schema": "ayyo.memory-candidate-discovery-result.v1",
    }
    return "memory-candidate-discovery-sha256-" + sha256(
        canonicalize_json(document).encode("utf-8")
    ).hexdigest()


def discovery_request_document(request: ConsolidationRequest) -> dict[str, object]:
    """Return a fresh canonicalizable document for bounded policy accounting."""

    if type(request) is not ConsolidationRequest:
        raise CandidateDiscoveryError("discovery request document requires a request")
    return _request_document(request)


def _request_document(request: ConsolidationRequest) -> dict[str, object]:
    return {
        "memory_type": request.memory_type.value,
        "metadata": request.metadata,
        "predicate": request.predicate,
        "robot_id": request.robot_id,
        "schema": "ayyo.memory-consolidation-request.v1",
        "subject": request.subject,
        "supporting_evidence": [
            {
                "observation_fingerprint": reference.observation_fingerprint,
                "observation_id": reference.observation_id,
                "semantic_item_id": reference.semantic_item_id,
                "source_id": reference.source_id,
            }
            for reference in request.supporting_evidence
        ],
        "value": request.value,
    }


def _validate_anonymous_semantic_request(request: ConsolidationRequest) -> None:
    if (
        request.memory_type is not MemoryType.EPISODIC
        or request.subject != request.robot_id
        or request.metadata
        or len(request.supporting_evidence) != 1
        or request.supporting_evidence[0].semantic_item_id is None
    ):
        raise CandidateDiscoveryError(
            "v1 proposals require exact anonymous episodic semantic evidence"
        )
    value = request.value
    if type(value) is not dict or value.get("anonymous") is not True:
        raise CandidateDiscoveryError("v1 proposal must remain anonymous")
    kind = value.get("kind")
    expected_keys = {"anonymous", "kind", "region"}
    if kind == "object":
        expected_keys.add("category")
    if (
        kind not in {"person", "object"}
        or request.predicate != f"observed_anonymous_{kind}"
        or set(value) != expected_keys
        or not _is_normalized_region(value.get("region"))
    ):
        raise CandidateDiscoveryError(
            "v1 proposal exceeds the exact anonymous semantic schema"
        )
    if kind == "object":
        category = value.get("category")
        if (
            type(category) is not str
            or not category
            or category != category.strip()
            or len(category) > MAX_VISUAL_LABEL_LENGTH
        ):
            raise CandidateDiscoveryError(
                "anonymous object proposal requires its bounded evidence category"
            )


def _is_normalized_region(value: object) -> bool:
    if type(value) is not dict or set(value) != {
        "coordinate_space",
        "x_max",
        "x_min",
        "y_max",
        "y_min",
    }:
        return False
    coordinates = tuple(value[name] for name in ("x_min", "y_min", "x_max", "y_max"))
    return (
        value["coordinate_space"] == "normalized_image"
        and all(
            not isinstance(coordinate, bool)
            and isinstance(coordinate, (int, float))
            and math.isfinite(coordinate)
            for coordinate in coordinates
        )
        and 0.0 <= coordinates[0] < coordinates[2] <= 1.0
        and 0.0 <= coordinates[1] < coordinates[3] <= 1.0
    )


def _validate_policy_identity(
    policy_id: str,
    policy_version: int,
    policy_fingerprint: str,
) -> None:
    if policy_id != CANDIDATE_DISCOVERY_POLICY_ID:
        raise CandidateDiscoveryError("discovery policy identity is invalid")
    if policy_version != CANDIDATE_DISCOVERY_POLICY_VERSION:
        raise CandidateDiscoveryError("discovery policy version is invalid")
    _validate_digest_identity(
        policy_fingerprint,
        "memory-candidate-discovery-policy-sha256-",
        "discovery policy fingerprint",
    )


def _validate_digest_identity(value: object, prefix: str, field_name: str) -> None:
    if (
        type(value) is not str
        or not value.startswith(prefix)
        or len(value) != len(prefix) + 64
        or any(character not in "0123456789abcdef" for character in value[-64:])
    ):
        raise CandidateDiscoveryError(f"{field_name} is malformed")


def _bounded_optional_identity(value: object, field_name: str) -> None:
    if value is None:
        return
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_CONSOLIDATION_IDENTITY_TEXT
    ):
        raise CandidateDiscoveryError(f"{field_name} exceeds its bound")


def _diagnostic_key(
    diagnostic: CandidateDiscoveryDiagnostic,
) -> tuple[str, str, str]:
    return (
        "" if diagnostic.evidence_id is None else diagnostic.evidence_id,
        "" if diagnostic.semantic_item_id is None else diagnostic.semantic_item_id,
        diagnostic.reason.value,
    )
