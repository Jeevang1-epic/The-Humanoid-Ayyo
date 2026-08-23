"""Public deterministic Executive Cognition service."""

from __future__ import annotations

from hashlib import sha256

from ayyo_personal_context import (
    ContextState,
    PersonalContextService,
    PersonalContextSnapshot,
)

from .capabilities import (
    CapabilityAvailability,
    CapabilityDefinition,
    CapabilityRegistry,
)
from .errors import DecisionInvariantError, InvalidRequestError
from .models import (
    ContextReference,
    ContextRequirement,
    DecisionReason,
    ExecutiveDecision,
    ExecutiveDecisionType,
    ExecutiveRequest,
    MissingContextPolicy,
    RevalidationReason,
    RevalidationResult,
    RevalidationStatus,
    _context_key,
    relevant_context_fingerprint,
)
from .planner import (
    DeclarativePlanner,
    merge_approvals,
    merge_assumptions,
    merge_constraints,
    merge_context_requirements,
)


_REASON_RANK = {reason: index for index, reason in enumerate(DecisionReason)}
_REVALIDATION_RANK = {
    reason: index for index, reason in enumerate(RevalidationReason)
}


def _ordered_reasons(reasons: set[DecisionReason]) -> tuple[DecisionReason, ...]:
    return tuple(sorted(reasons, key=_REASON_RANK.get))


def _context_reference(
    snapshot: PersonalContextSnapshot,
    requirement: ContextRequirement,
    *,
    required: bool,
) -> ContextReference:
    result = snapshot.get_context(requirement.domain, requirement.predicate)
    if result.state is ContextState.UNKNOWN:
        return ContextReference(
            requirement=requirement,
            required=required,
            state=ContextState.UNKNOWN,
            value_digests=(),
            memory_ids=(),
            conflict_ids=(),
        )
    if result.entry is None:
        raise DecisionInvariantError("known PCT context is missing its entry")
    return ContextReference(
        requirement=requirement,
        required=required,
        state=result.state,
        value_digests=tuple(
            sorted(
                sha256(value.canonical_value.encode("utf-8")).hexdigest()
                for value in result.entry.values
            )
        ),
        memory_ids=tuple(
            sorted(
                (
                    evidence.memory_id
                    for value in result.entry.values
                    for evidence in value.evidence
                ),
                key=str,
            )
        ),
        conflict_ids=result.entry.conflict_ids,
    )


def _references_for(
    snapshot: PersonalContextSnapshot,
    required_context: tuple[ContextRequirement, ...],
    optional_context: tuple[ContextRequirement, ...],
) -> tuple[ContextReference, ...]:
    required_set = set(required_context)
    optional_context = tuple(
        item for item in optional_context if item not in required_set
    )
    references = [
        _context_reference(snapshot, item, required=True)
        for item in required_context
    ]
    references.extend(
        _context_reference(snapshot, item, required=False)
        for item in optional_context
    )
    return tuple(
        sorted(
            references,
            key=lambda item: (
                0 if item.required else 1,
                item.requirement.domain.value,
                item.requirement.predicate,
            ),
        )
    )


class ExecutiveService:
    """Produces inert proposals from structured requests and one PCT snapshot."""

    __slots__ = ("_context_service", "_planner", "_registry")

    def __init__(
        self,
        context_service: PersonalContextService,
        capability_registry: CapabilityRegistry,
    ) -> None:
        if not isinstance(context_service, PersonalContextService):
            raise InvalidRequestError(
                "context_service must be a PersonalContextService"
            )
        if not isinstance(capability_registry, CapabilityRegistry):
            raise InvalidRequestError(
                "capability_registry must be a CapabilityRegistry"
            )
        self._context_service = context_service
        self._registry = capability_registry
        self._planner = DeclarativePlanner()

    @property
    def owner_subject(self) -> str:
        return self._context_service.owner_subject

    def evaluate(self, request: ExecutiveRequest) -> ExecutiveDecision:
        if not isinstance(request, ExecutiveRequest):
            raise InvalidRequestError("evaluate requires an ExecutiveRequest")

        snapshot = self._context_service.build_snapshot()
        if snapshot.owner_subject != self.owner_subject:
            raise DecisionInvariantError(
                "PCT snapshot owner does not match the configured service owner"
            )
        capability_ids = request.requested_capabilities
        capability_fingerprint = self._registry.fingerprint_for(capability_ids)
        definitions: list[CapabilityDefinition] = []
        unknown_capabilities: list[str] = []
        unavailable_capabilities: list[str] = []
        for capability_id in capability_ids:
            definition = self._registry.get(capability_id)
            if definition is None:
                unknown_capabilities.append(capability_id)
                continue
            definitions.append(definition)
            if definition.availability is CapabilityAvailability.UNAVAILABLE:
                unavailable_capabilities.append(capability_id)

        definitions_by_id = {
            definition.capability_id: definition for definition in definitions
        }
        for invocation in request.invocations:
            definition = definitions_by_id.get(invocation.capability_id)
            if definition is not None:
                self._registry.validate_parameters(
                    definition,
                    invocation.parameters,
                )

        definition_tuple = tuple(
            sorted(definitions, key=lambda item: item.capability_id)
        )
        required_context = merge_context_requirements(request, definition_tuple)
        references = _references_for(
            snapshot,
            required_context,
            request.optional_context,
        )
        missing = tuple(
            item.requirement
            for item in references
            if item.required and item.state is ContextState.UNKNOWN
        )
        conflicted = tuple(
            item.requirement
            for item in references
            if item.required and item.state is ContextState.CONFLICTED
        )
        approvals = merge_approvals(request, definition_tuple)
        assumptions = merge_assumptions(request, definition_tuple)
        constraints = merge_constraints(request, definition_tuple)

        reasons: set[DecisionReason] = set()
        proposed_plan = None
        if unknown_capabilities:
            decision_type = ExecutiveDecisionType.REJECT
            reasons.add(DecisionReason.UNKNOWN_CAPABILITY)
            if unavailable_capabilities:
                reasons.add(DecisionReason.CAPABILITY_UNAVAILABLE)
            if missing:
                reasons.add(DecisionReason.MISSING_REQUIRED_CONTEXT)
            if conflicted:
                reasons.add(DecisionReason.CONFLICTED_REQUIRED_CONTEXT)
            explanation = (
                "The request names a capability absent from the explicit registry; "
                "no plan was fabricated."
            )
        elif unavailable_capabilities:
            decision_type = ExecutiveDecisionType.DEFER
            reasons.add(DecisionReason.CAPABILITY_UNAVAILABLE)
            if missing:
                reasons.add(DecisionReason.MISSING_REQUIRED_CONTEXT)
            if conflicted:
                reasons.add(DecisionReason.CONFLICTED_REQUIRED_CONTEXT)
            explanation = (
                "At least one required capability is explicitly unavailable for "
                "proposal, so planning was deferred."
            )
        elif conflicted:
            decision_type = ExecutiveDecisionType.DEFER
            reasons.add(DecisionReason.CONFLICTED_REQUIRED_CONTEXT)
            if missing:
                reasons.add(DecisionReason.MISSING_REQUIRED_CONTEXT)
            explanation = (
                "Required owner context is conflicted; the Executive did not choose "
                "a winning value."
            )
        elif missing:
            reasons.add(DecisionReason.MISSING_REQUIRED_CONTEXT)
            if request.missing_context_policy is MissingContextPolicy.DEFER:
                decision_type = ExecutiveDecisionType.DEFER
                explanation = (
                    "Required owner context is unknown and request policy requires "
                    "deferral."
                )
            else:
                decision_type = ExecutiveDecisionType.REQUEST_INFORMATION
                explanation = (
                    "Required owner context is unknown; additional information is "
                    "required before a proposal can be formed."
                )
        else:
            proposed_plan = self._planner.build_plan(request, definitions_by_id)
            if approvals:
                decision_type = ExecutiveDecisionType.REQUEST_APPROVAL
                reasons.add(DecisionReason.APPROVAL_REQUIRED)
                explanation = (
                    "A declarative plan is available, but its recorded approval "
                    "requirements remain ungranted."
                )
            else:
                decision_type = ExecutiveDecisionType.PROPOSE
                reasons.add(DecisionReason.READY_FOR_SAFETY_REVIEW)
                explanation = (
                    "A deterministic declarative plan is proposed for evaluation by "
                    "later safety and authorization layers."
                )

        return ExecutiveDecision(
            request_id=request.request_id,
            owner_subject=snapshot.owner_subject,
            decision_type=decision_type,
            reason_codes=_ordered_reasons(reasons),
            explanation=explanation,
            context_snapshot_version=snapshot.version,
            request_fingerprint=request.fingerprint,
            capability_contract_fingerprint=capability_fingerprint,
            context_references=references,
            assumptions=assumptions,
            required_capabilities=capability_ids,
            required_approvals=approvals,
            constraints=constraints,
            proposed_plan=proposed_plan,
        )

    def revalidate(
        self,
        decision: ExecutiveDecision,
        request: ExecutiveRequest,
    ) -> RevalidationResult:
        if not isinstance(decision, ExecutiveDecision):
            raise InvalidRequestError("revalidate requires an ExecutiveDecision")
        if not isinstance(request, ExecutiveRequest):
            raise InvalidRequestError("revalidate requires an ExecutiveRequest")

        snapshot = self._context_service.build_snapshot()
        if snapshot.owner_subject != self.owner_subject:
            raise DecisionInvariantError(
                "PCT snapshot owner does not match the configured service owner"
            )
        current_capability_fingerprint = self._registry.fingerprint_for(
            decision.required_capabilities
        )
        prior_required = tuple(
            reference.requirement
            for reference in decision.context_references
            if reference.required
        )
        prior_optional = tuple(
            reference.requirement
            for reference in decision.context_references
            if not reference.required
        )
        current_references = _references_for(
            snapshot,
            prior_required,
            prior_optional,
        )
        current_context_fingerprint = relevant_context_fingerprint(
            current_references
        )
        reasons: set[RevalidationReason] = set()
        if request.fingerprint != decision.request_fingerprint:
            reasons.add(RevalidationReason.REQUEST_CHANGED)
        if snapshot.owner_subject != decision.owner_subject:
            reasons.add(RevalidationReason.OWNER_CHANGED)
        if (
            current_capability_fingerprint
            != decision.capability_contract_fingerprint
        ):
            reasons.add(RevalidationReason.CAPABILITY_CONTRACT_CHANGED)
        if current_context_fingerprint != decision.relevant_context_fingerprint:
            reasons.add(RevalidationReason.RELEVANT_CONTEXT_CHANGED)
        ordered_reasons = tuple(sorted(reasons, key=_REVALIDATION_RANK.get))
        return RevalidationResult(
            decision_id=decision.decision_id,
            status=(
                RevalidationStatus.CURRENT
                if not ordered_reasons
                else RevalidationStatus.STALE
            ),
            reasons=ordered_reasons,
            prior_snapshot_version=decision.context_snapshot_version,
            current_snapshot_version=snapshot.version,
            prior_owner_subject=decision.owner_subject,
            current_owner_subject=snapshot.owner_subject,
            prior_request_fingerprint=decision.request_fingerprint,
            current_request_fingerprint=request.fingerprint,
            prior_capability_fingerprint=(
                decision.capability_contract_fingerprint
            ),
            current_capability_fingerprint=current_capability_fingerprint,
            prior_context_fingerprint=decision.relevant_context_fingerprint,
            current_context_fingerprint=current_context_fingerprint,
        )
