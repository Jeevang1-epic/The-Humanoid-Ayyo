"""Deterministic Runtime Bridge eligibility decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ayyo_skill_manager import (
    BindingReason,
    BindingStatus,
    SkillBindingResult,
    SkillInvocation,
    SkillFingerprint,
    SkillManagerError,
    SkillSelection,
)

from .binding import RuntimeRequest, bind_runtime_request, rebuild_invocation, rebuild_registry
from .canonical import JSONValue
from .endpoints import RosEndpointAvailability
from .errors import (
    InvalidRuntimeBindingError,
    InvalidRuntimeContractError,
    StaleRuntimeDecisionError,
)
from .models import RuntimeFingerprint, RuntimeFingerprintKind, fingerprint_document
from .registry import RuntimeEndpointRegistry


class RuntimeEligibility(StrEnum):
    ELIGIBLE = "eligible"
    APPROVAL_REQUIRED = "approval_required"
    DEFERRED = "deferred"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


class RuntimeReason(StrEnum):
    UPSTREAM_APPROVAL_REQUIRED = "upstream_approval_required"
    UPSTREAM_BLOCKED = "upstream_blocked"
    UPSTREAM_DEFERRED = "upstream_deferred"
    UPSTREAM_STALE = "upstream_stale"
    UPSTREAM_INELIGIBLE = "upstream_ineligible"
    SKILL_UNAVAILABLE = "skill_unavailable"
    ENDPOINT_NOT_REGISTERED = "endpoint_not_registered"
    ENDPOINT_UNAVAILABLE = "endpoint_unavailable"
    SKILL_FINGERPRINT_MISMATCH = "skill_fingerprint_mismatch"
    RUNTIME_REGISTRY_CHANGED = "runtime_registry_changed"
    UPSTREAM_BINDING_CHANGED = "upstream_binding_changed"
    ENDPOINT_CHANGED = "endpoint_changed"


def _ordered_reasons(reasons: set[RuntimeReason]) -> tuple[RuntimeReason, ...]:
    return tuple(reason for reason in RuntimeReason if reason in reasons)


def _rebuild_selection(selection: SkillSelection) -> SkillSelection:
    try:
        rebuilt = SkillSelection(
            skill_id=selection.skill_id,
            skill_version=selection.skill_version,
            skill_fingerprint=selection.skill_fingerprint,
            capability_id=selection.capability_id,
            source_step_id=selection.source_step_id,
            registry_version=selection.registry_version,
            registry_fingerprint=selection.registry_fingerprint,
        )
    except SkillManagerError as error:
        raise InvalidRuntimeBindingError(
            "Skill binding selection failed integrity review"
        ) from error
    if rebuilt != selection:
        raise InvalidRuntimeBindingError("Skill binding selection fingerprint is stale")
    return rebuilt


def rebuild_binding_result(binding_result: object) -> SkillBindingResult:
    """Validate the public Skill Manager result without private imports."""

    if type(binding_result) is not SkillBindingResult:
        raise InvalidRuntimeBindingError(
            "runtime evaluation requires a public SkillBindingResult"
        )
    selection = _rebuild_selection(binding_result.selection)
    invocation: SkillInvocation | None = None
    if binding_result.invocation is not None:
        invocation = rebuild_invocation(binding_result.invocation)
    try:
        rebuilt = SkillBindingResult(
            status=binding_result.status,
            reasons=binding_result.reasons,
            selection=selection,
            source_safety_decision_id=binding_result.source_safety_decision_id,
            invocation=invocation,
        )
    except SkillManagerError as error:
        raise InvalidRuntimeBindingError(
            "Skill binding result failed integrity review"
        ) from error
    if rebuilt != binding_result:
        raise InvalidRuntimeBindingError("Skill binding result is internally inconsistent")
    return rebuilt


@dataclass(frozen=True, slots=True, init=False)
class RuntimeDecision:
    """A pure runtime compatibility decision; only ELIGIBLE carries a request."""

    decision_id: str
    status: RuntimeEligibility
    reasons: tuple[RuntimeReason, ...]
    source_binding_status: BindingStatus
    source_selection_fingerprint: SkillFingerprint
    source_safety_decision_id: str
    source_invocation_fingerprint: SkillFingerprint | None
    runtime_registry_fingerprint: RuntimeFingerprint
    request: RuntimeRequest | None
    fingerprint: RuntimeFingerprint

    def __init__(
        self,
        *,
        status: RuntimeEligibility,
        reasons: tuple[RuntimeReason, ...],
        binding_result: SkillBindingResult,
        runtime_registry_fingerprint: RuntimeFingerprint,
        request: RuntimeRequest | None,
    ) -> None:
        binding_result = rebuild_binding_result(binding_result)
        if not isinstance(status, RuntimeEligibility):
            raise InvalidRuntimeContractError("runtime eligibility status is invalid")
        if not isinstance(reasons, tuple) or not all(
            isinstance(item, RuntimeReason) for item in reasons
        ):
            raise InvalidRuntimeContractError("runtime decision reasons are invalid")
        if reasons != _ordered_reasons(set(reasons)):
            raise InvalidRuntimeContractError(
                "runtime decision reasons must be unique and canonically ordered"
            )
        if type(binding_result) is not SkillBindingResult:
            raise InvalidRuntimeContractError("runtime decision binding result is invalid")
        if (
            not isinstance(runtime_registry_fingerprint, RuntimeFingerprint)
            or runtime_registry_fingerprint.kind is not RuntimeFingerprintKind.REGISTRY
        ):
            raise InvalidRuntimeContractError(
                "runtime decision registry fingerprint is invalid"
            )
        if status is RuntimeEligibility.ELIGIBLE:
            if not isinstance(request, RuntimeRequest) or reasons:
                raise InvalidRuntimeContractError(
                    "eligible runtime decision requires one unblocked request"
                )
            rebuilt_request = RuntimeRequest(
                invocation=request.invocation,
                endpoint_binding=request.endpoint_binding,
                runtime_registry_version=request.runtime_registry_version,
                runtime_registry_fingerprint=request.runtime_registry_fingerprint,
            )
            if (
                rebuilt_request != request
                or rebuilt_request.request_fields != request.request_fields
            ):
                raise InvalidRuntimeContractError(
                    "runtime request fingerprint is stale"
                )
            request = rebuilt_request
        elif request is not None or not reasons:
            raise InvalidRuntimeContractError(
                "ineligible runtime decision requires reasons and no request"
            )
        required_reason = {
            RuntimeEligibility.APPROVAL_REQUIRED: RuntimeReason.UPSTREAM_APPROVAL_REQUIRED,
            RuntimeEligibility.DEFERRED: RuntimeReason.UPSTREAM_DEFERRED,
            RuntimeEligibility.BLOCKED: RuntimeReason.UPSTREAM_BLOCKED,
            RuntimeEligibility.STALE: RuntimeReason.UPSTREAM_STALE,
            RuntimeEligibility.UNAVAILABLE: RuntimeReason.ENDPOINT_UNAVAILABLE,
        }.get(status)
        if required_reason is not None and required_reason not in reasons:
            if not (
                status is RuntimeEligibility.UNAVAILABLE
                and RuntimeReason.SKILL_UNAVAILABLE in reasons
            ):
                raise InvalidRuntimeContractError(
                    f"{status.value} decision lacks its required typed reason"
                )
        if (
            status is RuntimeEligibility.APPROVAL_REQUIRED
            and binding_result.status is not BindingStatus.EXTERNAL_APPROVAL_REQUIRED
        ):
            raise InvalidRuntimeContractError(
                "approval-required runtime decision must preserve its upstream status"
            )
        if status is RuntimeEligibility.BLOCKED and (
            binding_result.status is not BindingStatus.INELIGIBLE
            or BindingReason.SAFETY_BLOCKED not in binding_result.reasons
        ):
            raise InvalidRuntimeContractError(
                "blocked runtime decision must preserve an upstream Safety block"
            )
        if status is RuntimeEligibility.DEFERRED and (
            binding_result.status is not BindingStatus.INELIGIBLE
            or BindingReason.SAFETY_DEFERRED not in binding_result.reasons
        ):
            raise InvalidRuntimeContractError(
                "deferred runtime decision must preserve upstream Safety deferral"
            )
        invocation_fingerprint = (
            None
            if binding_result.invocation is None
            else binding_result.invocation.fingerprint
        )
        document: dict[str, JSONValue] = {
            "reasons": [reason.value for reason in reasons],
            "request_fingerprint": (
                None if request is None else str(request.fingerprint)
            ),
            "runtime_registry_fingerprint": str(runtime_registry_fingerprint),
            "schema": "ayyo.runtime-bridge.decision.v1",
            "source_binding_status": binding_result.status.value,
            "source_invocation_fingerprint": (
                None if invocation_fingerprint is None else str(invocation_fingerprint)
            ),
            "source_safety_decision_id": binding_result.source_safety_decision_id,
            "source_selection_fingerprint": str(binding_result.selection.fingerprint),
            "status": status.value,
        }
        fingerprint = fingerprint_document(
            RuntimeFingerprintKind.DECISION,
            document,
            error_type=InvalidRuntimeContractError,
        )
        object.__setattr__(self, "decision_id", f"runtime-decision-{fingerprint.digest}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "source_binding_status", binding_result.status)
        object.__setattr__(
            self,
            "source_selection_fingerprint",
            binding_result.selection.fingerprint,
        )
        object.__setattr__(
            self,
            "source_safety_decision_id",
            binding_result.source_safety_decision_id,
        )
        object.__setattr__(self, "source_invocation_fingerprint", invocation_fingerprint)
        object.__setattr__(self, "runtime_registry_fingerprint", runtime_registry_fingerprint)
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "fingerprint", fingerprint)


@dataclass(frozen=True, slots=True)
class RuntimeBridge:
    """Pure deterministic evaluator for the current runtime endpoint allowlist."""

    registry: RuntimeEndpointRegistry

    def __post_init__(self) -> None:
        rebuild_registry(self.registry)

    def evaluate(self, binding_result: SkillBindingResult) -> RuntimeDecision:
        current_binding = rebuild_binding_result(binding_result)
        current_registry = rebuild_registry(self.registry)
        if current_binding.status is BindingStatus.INELIGIBLE:
            reason_map = {
                BindingReason.SAFETY_BLOCKED: (
                    RuntimeEligibility.BLOCKED,
                    RuntimeReason.UPSTREAM_BLOCKED,
                ),
                BindingReason.SAFETY_DEFERRED: (
                    RuntimeEligibility.DEFERRED,
                    RuntimeReason.UPSTREAM_DEFERRED,
                ),
                BindingReason.SAFETY_DECISION_STALE: (
                    RuntimeEligibility.STALE,
                    RuntimeReason.UPSTREAM_STALE,
                ),
                BindingReason.REGISTRY_SELECTION_STALE: (
                    RuntimeEligibility.STALE,
                    RuntimeReason.UPSTREAM_STALE,
                ),
                BindingReason.SKILL_UNAVAILABLE: (
                    RuntimeEligibility.UNAVAILABLE,
                    RuntimeReason.SKILL_UNAVAILABLE,
                ),
            }
            mapped = [
                reason_map[reason]
                for reason in current_binding.reasons
                if reason in reason_map
            ]
            if mapped:
                rank = {
                    RuntimeEligibility.REJECTED: 0,
                    RuntimeEligibility.UNAVAILABLE: 1,
                    RuntimeEligibility.STALE: 2,
                    RuntimeEligibility.APPROVAL_REQUIRED: 3,
                    RuntimeEligibility.DEFERRED: 4,
                    RuntimeEligibility.BLOCKED: 5,
                    RuntimeEligibility.ELIGIBLE: -1,
                }
                status = max((item[0] for item in mapped), key=rank.get)
                reasons = {item[1] for item in mapped}
            else:
                status = RuntimeEligibility.REJECTED
                reasons = {RuntimeReason.UPSTREAM_INELIGIBLE}
            return RuntimeDecision(
                status=status,
                reasons=_ordered_reasons(reasons),
                binding_result=current_binding,
                runtime_registry_fingerprint=current_registry.fingerprint,
                request=None,
            )
        if current_binding.status is BindingStatus.EXTERNAL_APPROVAL_REQUIRED:
            return RuntimeDecision(
                status=RuntimeEligibility.APPROVAL_REQUIRED,
                reasons=(RuntimeReason.UPSTREAM_APPROVAL_REQUIRED,),
                binding_result=current_binding,
                runtime_registry_fingerprint=current_registry.fingerprint,
                request=None,
            )
        assert current_binding.invocation is not None
        invocation = current_binding.invocation
        endpoint_binding = current_registry.resolve(
            skill_id=invocation.selection.skill_id,
            skill_version=invocation.selection.skill_version,
            capability_id=invocation.selection.capability_id,
            backend_id=invocation.backend_id,
        )
        if endpoint_binding is None:
            return RuntimeDecision(
                status=RuntimeEligibility.REJECTED,
                reasons=(RuntimeReason.ENDPOINT_NOT_REGISTERED,),
                binding_result=current_binding,
                runtime_registry_fingerprint=current_registry.fingerprint,
                request=None,
            )
        if endpoint_binding.skill_fingerprint != invocation.selection.skill_fingerprint:
            return RuntimeDecision(
                status=RuntimeEligibility.STALE,
                reasons=(RuntimeReason.UPSTREAM_STALE, RuntimeReason.SKILL_FINGERPRINT_MISMATCH),
                binding_result=current_binding,
                runtime_registry_fingerprint=current_registry.fingerprint,
                request=None,
            )
        if endpoint_binding.endpoint.availability is not RosEndpointAvailability.AVAILABLE:
            return RuntimeDecision(
                status=RuntimeEligibility.UNAVAILABLE,
                reasons=(RuntimeReason.ENDPOINT_UNAVAILABLE,),
                binding_result=current_binding,
                runtime_registry_fingerprint=current_registry.fingerprint,
                request=None,
            )
        request = bind_runtime_request(invocation, current_registry)
        return RuntimeDecision(
            status=RuntimeEligibility.ELIGIBLE,
            reasons=(),
            binding_result=current_binding,
            runtime_registry_fingerprint=current_registry.fingerprint,
            request=request,
        )

    def revalidate(
        self,
        prior_decision: RuntimeDecision,
        current_binding: SkillBindingResult,
    ) -> RuntimeDecision:
        """Return the prior decision if current, otherwise a typed stale decision."""

        if type(prior_decision) is not RuntimeDecision:
            raise InvalidRuntimeContractError(
                "runtime revalidation requires a RuntimeDecision"
            )
        current = self.evaluate(current_binding)
        if current == prior_decision:
            return prior_decision
        reasons = {RuntimeReason.UPSTREAM_STALE}
        if current.runtime_registry_fingerprint != prior_decision.runtime_registry_fingerprint:
            reasons.add(RuntimeReason.RUNTIME_REGISTRY_CHANGED)
        if (
            current.source_selection_fingerprint
            != prior_decision.source_selection_fingerprint
            or current.source_safety_decision_id
            != prior_decision.source_safety_decision_id
            or current.source_invocation_fingerprint
            != prior_decision.source_invocation_fingerprint
        ):
            reasons.add(RuntimeReason.UPSTREAM_BINDING_CHANGED)
        prior_endpoint = (
            None
            if prior_decision.request is None
            else prior_decision.request.endpoint_binding.endpoint.fingerprint
        )
        current_endpoint = (
            None
            if current.request is None
            else current.request.endpoint_binding.endpoint.fingerprint
        )
        if prior_endpoint != current_endpoint:
            reasons.add(RuntimeReason.ENDPOINT_CHANGED)
        return RuntimeDecision(
            status=RuntimeEligibility.STALE,
            reasons=_ordered_reasons(reasons),
            binding_result=rebuild_binding_result(current_binding),
            runtime_registry_fingerprint=current.runtime_registry_fingerprint,
            request=None,
        )

    def assert_current(
        self,
        prior_decision: RuntimeDecision,
        current_binding: SkillBindingResult,
    ) -> RuntimeDecision:
        """Return a current decision or raise a typed stale-decision failure."""

        result = self.revalidate(prior_decision, current_binding)
        if result.status is RuntimeEligibility.STALE:
            raise StaleRuntimeDecisionError(
                "runtime eligibility decision no longer matches current bound state"
            )
        return result
