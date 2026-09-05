"""Caller-triggered bounded discovery over retained Working Memory evidence."""

from __future__ import annotations

from hashlib import sha256

from ayyo_memory import MemoryType
from ayyo_memory_validation import canonicalize_json
from ayyo_working_memory import (
    WorkingMemory,
    WorkingMemoryClockRegressionError,
    WorkingMemoryConfigurationError,
)
from ayyo_world_model import (
    MAX_JSON_COLLECTION,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_JSON_TEXT,
    MAX_OBSERVATION_TIME_NS,
    ObservationClock,
    ObservationIdentityError,
    SemanticEvidenceKind,
    SemanticEvidenceObservation,
    WorldModelValidationError,
    rebuild_observation,
)

from .discovery_models import (
    CANDIDATE_DISCOVERY_POLICY_ID,
    CANDIDATE_DISCOVERY_POLICY_VERSION,
    MAX_CANDIDATE_DISCOVERY_AGGREGATE_CHARACTERS,
    MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS,
    MAX_CANDIDATE_DISCOVERY_EVIDENCE,
    MAX_CANDIDATE_DISCOVERY_PROPOSALS,
    MAX_CANDIDATE_DISCOVERY_REASONS,
    CandidateDiscoveryDiagnostic,
    CandidateDiscoveryOutcome,
    CandidateDiscoveryProposal,
    CandidateDiscoveryReason,
    CandidateDiscoveryResult,
    candidate_discovery_proposal_identity,
    candidate_discovery_result_identity,
    discovery_request_document,
    ordered_discovery_reasons,
)
from .errors import CandidateDiscoveryError, ConsolidationRequestError
from .models import (
    MAX_CONSOLIDATION_IDENTITY_TEXT,
    MAX_CONSOLIDATION_METADATA_FIELDS,
    ConsolidationRequest,
    EvidenceReference,
)
from .service import _semantic_source_chain_is_exact, _utc_from_system_time


_POLICY_DOCUMENT = {
    "bounds": {
        "aggregate_characters": MAX_CANDIDATE_DISCOVERY_AGGREGATE_CHARACTERS,
        "diagnostics": MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS,
        "evidence_envelopes": MAX_CANDIDATE_DISCOVERY_EVIDENCE,
        "identity_text": MAX_CONSOLIDATION_IDENTITY_TEXT,
        "json_collection": MAX_JSON_COLLECTION,
        "json_depth": MAX_JSON_DEPTH,
        "json_nodes": MAX_JSON_NODES,
        "json_text": MAX_JSON_TEXT,
        "metadata_fields": MAX_CONSOLIDATION_METADATA_FIELDS,
        "proposals": MAX_CANDIDATE_DISCOVERY_PROPOSALS,
        "reasons": MAX_CANDIDATE_DISCOVERY_REASONS,
    },
    "clock": ObservationClock.ROS_SYSTEM_TIME.value,
    "confidence": "required_without_synthesis_including_zero",
    "deduplication": "exact_proposal_identity_only",
    "downstream_invocation": "caller_only",
    "memory_type": MemoryType.EPISODIC.value,
    "policy_id": CANDIDATE_DISCOVERY_POLICY_ID,
    "policy_version": CANDIDATE_DISCOVERY_POLICY_VERSION,
    "propositions": {
        SemanticEvidenceKind.OBJECT.value: "observed_anonymous_object",
        SemanticEvidenceKind.PERSON.value: "observed_anonymous_person",
    },
    "source": "currently_retained_working_memory_evidence",
}
CANDIDATE_DISCOVERY_POLICY_FINGERPRINT = (
    "memory-candidate-discovery-policy-sha256-"
    + sha256(canonicalize_json(_POLICY_DOCUMENT).encode("utf-8")).hexdigest()
)


class BoundedMemoryCandidateDiscoveryPolicy:
    """Stateless v1 policy for explicit, read-only proposal discovery."""

    __slots__ = ()

    @property
    def policy_id(self) -> str:
        return CANDIDATE_DISCOVERY_POLICY_ID

    @property
    def policy_version(self) -> int:
        return CANDIDATE_DISCOVERY_POLICY_VERSION

    @property
    def policy_fingerprint(self) -> str:
        return CANDIDATE_DISCOVERY_POLICY_FINGERPRINT

    def discover(
        self,
        working_memory: WorkingMemory,
        *,
        now_ns: int,
    ) -> CandidateDiscoveryResult:
        """Discover exact requests without staging or invoking later layers."""

        if type(working_memory) is not WorkingMemory:
            raise CandidateDiscoveryError(
                "discovery requires an exact WorkingMemory instance"
            )
        if type(now_ns) is not int or not 0 <= now_ns <= MAX_OBSERVATION_TIME_NS:
            return _result(
                diagnostics=(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.INVALID_DISCOVERY_TIME
                    ),
                ),
                retained_count=0,
                inspected_count=0,
                forced_outcome=CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE,
            )

        config = working_memory.config
        try:
            envelopes = working_memory.recent_evidence(now_ns=now_ns)
        except WorkingMemoryClockRegressionError:
            return _result(
                diagnostics=(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.SOURCE_CLOCK_REGRESSION
                    ),
                ),
                retained_count=0,
                inspected_count=0,
                forced_outcome=CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE,
            )
        except (
            ObservationIdentityError,
            WorkingMemoryConfigurationError,
            WorldModelValidationError,
        ):
            return _result(
                diagnostics=(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.INVALID_RETAINED_EVIDENCE
                    ),
                ),
                retained_count=0,
                inspected_count=0,
                forced_outcome=CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE,
            )

        retained_count = len(envelopes)
        if retained_count > MAX_CANDIDATE_DISCOVERY_EVIDENCE:
            return _result(
                diagnostics=(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.RESOURCE_LIMIT_REACHED
                    ),
                ),
                retained_count=retained_count,
                inspected_count=0,
                resource_limited=True,
            )
        try:
            retained = tuple(
                sorted(
                    (
                        rebuild_observation(envelope.observation)
                        for envelope in envelopes
                    ),
                    key=lambda observation: (
                        observation.observed_at_ns,
                        observation.observation_id,
                        str(observation.fingerprint),
                    ),
                )
            )
        except (ObservationIdentityError, WorldModelValidationError):
            return _result(
                diagnostics=(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.INVALID_RETAINED_EVIDENCE
                    ),
                ),
                retained_count=retained_count,
                inspected_count=retained_count,
                forced_outcome=CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE,
            )

        if len({item.observation_id for item in retained}) != len(retained):
            return _result(
                diagnostics=(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.INVALID_RETAINED_EVIDENCE
                    ),
                ),
                retained_count=retained_count,
                inspected_count=retained_count,
                forced_outcome=CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE,
            )
        if config.source_clock is not ObservationClock.ROS_SYSTEM_TIME:
            return _result(
                diagnostics=(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.UNSUPPORTED_CLOCK
                    ),
                ),
                retained_count=retained_count,
                inspected_count=retained_count,
                forced_outcome=CandidateDiscoveryOutcome.DISCOVERY_INELIGIBLE,
            )
        if not retained:
            return _result(
                diagnostics=(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.NO_RETAINED_EVIDENCE
                    ),
                ),
                retained_count=0,
                inspected_count=0,
            )

        proposals: dict[str, CandidateDiscoveryProposal] = {}
        diagnostics: list[CandidateDiscoveryDiagnostic] = []
        for observation in retained:
            common_reason = _common_ineligibility_reason(
                observation,
                config=config,
                now_ns=now_ns,
            )
            if common_reason is not None:
                diagnostics.append(
                    CandidateDiscoveryDiagnostic(
                        common_reason,
                        evidence_id=observation.observation_id,
                    )
                )
                continue
            if type(observation) is not SemanticEvidenceObservation:
                diagnostics.append(
                    CandidateDiscoveryDiagnostic(
                        CandidateDiscoveryReason.UNSUPPORTED_EVIDENCE_KIND,
                        evidence_id=observation.observation_id,
                    )
                )
                continue
            for item in observation.items:
                item_id = item.source_semantic_observation_id
                if not _semantic_source_chain_is_exact(
                    observation,
                    item,
                    retained,
                ):
                    diagnostics.append(
                        CandidateDiscoveryDiagnostic(
                            CandidateDiscoveryReason.INVALID_SOURCE_CHAIN,
                            evidence_id=observation.observation_id,
                            semantic_item_id=item_id,
                        )
                    )
                    continue
                if item.confidence is None:
                    diagnostics.append(
                        CandidateDiscoveryDiagnostic(
                            CandidateDiscoveryReason.MISSING_REQUIRED_CONFIDENCE,
                            evidence_id=observation.observation_id,
                            semantic_item_id=item_id,
                        )
                    )
                    continue
                try:
                    proposal = _anonymous_semantic_proposal(observation, item)
                except (CandidateDiscoveryError, ConsolidationRequestError):
                    diagnostics.append(
                        CandidateDiscoveryDiagnostic(
                            CandidateDiscoveryReason.PROPOSITION_NOT_SAFELY_DERIVABLE,
                            evidence_id=observation.observation_id,
                            semantic_item_id=item_id,
                        )
                    )
                    continue
                proposals.setdefault(proposal.proposal_id, proposal)

        return _result(
            proposals=tuple(proposals.values()),
            diagnostics=tuple(diagnostics),
            retained_count=retained_count,
            inspected_count=retained_count,
        )


def _common_ineligibility_reason(
    observation,
    *,
    config,
    now_ns: int,
) -> CandidateDiscoveryReason | None:
    if observation.robot_id != config.robot_id:
        return CandidateDiscoveryReason.WRONG_ROBOT
    if (
        observation.provenance not in config.allowed_provenance
        or observation.provenance.clock is not config.source_clock
    ):
        return CandidateDiscoveryReason.PROVENANCE_NOT_ALLOWED
    if observation.observed_at_ns > now_ns:
        return CandidateDiscoveryReason.EVIDENCE_TIME_IN_FUTURE
    if now_ns - observation.observed_at_ns > config.freshness_ns:
        return CandidateDiscoveryReason.EVIDENCE_STALE
    if _utc_from_system_time(observation.observed_at_ns) is None:
        return CandidateDiscoveryReason.TIMESTAMP_NOT_UTC_CONVERTIBLE
    return None


def _anonymous_semantic_proposal(
    observation: SemanticEvidenceObservation,
    item,
) -> CandidateDiscoveryProposal:
    value: dict[str, object] = {
        "anonymous": True,
        "kind": item.kind.value,
        "region": item.region.document(),
    }
    if item.kind is SemanticEvidenceKind.OBJECT:
        value["category"] = item.category
    request = ConsolidationRequest(
        robot_id=observation.robot_id,
        memory_type=MemoryType.EPISODIC,
        subject=observation.robot_id,
        predicate=f"observed_anonymous_{item.kind.value}",
        value=value,
        supporting_evidence=(
            EvidenceReference(
                observation_id=observation.observation_id,
                observation_fingerprint=str(observation.fingerprint),
                source_id=observation.provenance.source_id,
                semantic_item_id=item.source_semantic_observation_id,
            ),
        ),
        metadata={},
    )
    proposal_id = candidate_discovery_proposal_identity(
        request,
        policy_fingerprint=CANDIDATE_DISCOVERY_POLICY_FINGERPRINT,
    )
    return CandidateDiscoveryProposal(
        policy_id=CANDIDATE_DISCOVERY_POLICY_ID,
        policy_version=CANDIDATE_DISCOVERY_POLICY_VERSION,
        policy_fingerprint=CANDIDATE_DISCOVERY_POLICY_FINGERPRINT,
        proposal_id=proposal_id,
        request=request,
    )


def _result(
    *,
    proposals: tuple[CandidateDiscoveryProposal, ...] = (),
    diagnostics: tuple[CandidateDiscoveryDiagnostic, ...] = (),
    retained_count: int,
    inspected_count: int,
    forced_outcome: CandidateDiscoveryOutcome | None = None,
    resource_limited: bool = False,
) -> CandidateDiscoveryResult:
    canonical_proposals = tuple(sorted(proposals, key=lambda item: item.proposal_id))
    if len(canonical_proposals) > MAX_CANDIDATE_DISCOVERY_PROPOSALS:
        canonical_proposals = canonical_proposals[
            :MAX_CANDIDATE_DISCOVERY_PROPOSALS
        ]
        resource_limited = True

    canonical_diagnostics = tuple(sorted(set(diagnostics), key=_diagnostic_key))
    if len(canonical_diagnostics) > MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS:
        resource_limited = True
    if resource_limited:
        canonical_diagnostics = _with_resource_diagnostic(canonical_diagnostics)

    if (
        _aggregate_characters(canonical_proposals, canonical_diagnostics)
        > MAX_CANDIDATE_DISCOVERY_AGGREGATE_CHARACTERS
    ):
        resource_limited = True
        canonical_diagnostics = _with_resource_diagnostic(canonical_diagnostics)

    while (
        _aggregate_characters(canonical_proposals, canonical_diagnostics)
        > MAX_CANDIDATE_DISCOVERY_AGGREGATE_CHARACTERS
    ):
        resource_limited = True
        if canonical_diagnostics:
            non_resource = tuple(
                item
                for item in canonical_diagnostics
                if item.reason is not CandidateDiscoveryReason.RESOURCE_LIMIT_REACHED
            )
            if non_resource:
                victim = non_resource[-1]
                canonical_diagnostics = tuple(
                    item for item in canonical_diagnostics if item != victim
                )
                continue
        if canonical_proposals:
            canonical_proposals = canonical_proposals[:-1]
            continue
        break

    reasons = {item.reason for item in canonical_diagnostics}
    if canonical_proposals:
        reasons.add(CandidateDiscoveryReason.DISCOVERABLE)
    canonical_reasons = ordered_discovery_reasons(reasons)
    if resource_limited:
        outcome = CandidateDiscoveryOutcome.RESOURCE_LIMIT_REACHED
    elif forced_outcome is not None:
        outcome = forced_outcome
    elif canonical_proposals:
        outcome = CandidateDiscoveryOutcome.PROPOSALS_DISCOVERED
    else:
        outcome = CandidateDiscoveryOutcome.NO_DISCOVERABLE_PROPOSALS
    discovery_id = candidate_discovery_result_identity(
        policy_fingerprint=CANDIDATE_DISCOVERY_POLICY_FINGERPRINT,
        outcome=outcome,
        reasons=canonical_reasons,
        proposals=canonical_proposals,
        diagnostics=canonical_diagnostics,
        retained_evidence_count=retained_count,
        inspected_evidence_count=inspected_count,
    )
    return CandidateDiscoveryResult(
        policy_id=CANDIDATE_DISCOVERY_POLICY_ID,
        policy_version=CANDIDATE_DISCOVERY_POLICY_VERSION,
        policy_fingerprint=CANDIDATE_DISCOVERY_POLICY_FINGERPRINT,
        discovery_id=discovery_id,
        outcome=outcome,
        reasons=canonical_reasons,
        proposals=canonical_proposals,
        diagnostics=canonical_diagnostics,
        retained_evidence_count=retained_count,
        inspected_evidence_count=inspected_count,
    )


def _aggregate_characters(
    proposals: tuple[CandidateDiscoveryProposal, ...],
    diagnostics: tuple[CandidateDiscoveryDiagnostic, ...],
) -> int:
    document = {
        "diagnostics": [
            {
                "evidence_id": item.evidence_id,
                "reason": item.reason.value,
                "semantic_item_id": item.semantic_item_id,
            }
            for item in diagnostics
        ],
        "policy_fingerprint": CANDIDATE_DISCOVERY_POLICY_FINGERPRINT,
        "policy_id": CANDIDATE_DISCOVERY_POLICY_ID,
        "proposals": [
            {
                "proposal_id": item.proposal_id,
                "request": discovery_request_document(item.request),
            }
            for item in proposals
        ],
        "schema": "ayyo.memory-candidate-discovery-resource.v1",
    }
    return len(canonicalize_json(document))


def _with_resource_diagnostic(
    diagnostics: tuple[CandidateDiscoveryDiagnostic, ...],
) -> tuple[CandidateDiscoveryDiagnostic, ...]:
    resource = CandidateDiscoveryDiagnostic(
        CandidateDiscoveryReason.RESOURCE_LIMIT_REACHED
    )
    non_resource = tuple(
        item
        for item in sorted(set(diagnostics), key=_diagnostic_key)
        if item.reason is not CandidateDiscoveryReason.RESOURCE_LIMIT_REACHED
    )[: MAX_CANDIDATE_DISCOVERY_DIAGNOSTICS - 1]
    return tuple(sorted((resource, *non_resource), key=_diagnostic_key))


def _diagnostic_key(
    diagnostic: CandidateDiscoveryDiagnostic,
) -> tuple[str, str, str]:
    return (
        "" if diagnostic.evidence_id is None else diagnostic.evidence_id,
        "" if diagnostic.semantic_item_id is None else diagnostic.semantic_item_id,
        diagnostic.reason.value,
    )
