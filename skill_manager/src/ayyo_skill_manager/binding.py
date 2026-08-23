"""Fail-closed binding of Safety-reviewed proposals to inert skill contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ayyo_executive import (
    ContextReference,
    ExecutiveDecision,
    ExpectedResultCategory,
    Fingerprint as ExecutiveFingerprint,
    FingerprintKind as ExecutiveFingerprintKind,
)
from ayyo_safety import (
    ApprovalClass,
    HazardClass,
    SafetyApprovalRequirement,
    SafetyDecision,
    SafetyDisposition,
    SafetyFingerprint,
    SafetyFingerprintKind,
    SafetyKernel,
    SafetyKernelError,
    SafetyRevalidationStatus,
)

from .canonical import JSONValue, copy_json
from .errors import (
    InvalidSkillBindingError,
    InvalidSkillParametersError,
    SkillInvocationInvariantError,
)
from .models import (
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    ResourceRequirement,
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillFingerprint,
    SkillFingerprintKind,
    SkillLifecycle,
    fingerprint_document,
    validate_identifier,
)
from .parameters import validate_parameters
from .registry import SkillRegistry
from .schema import ValueSchema, schema_document


class BindingStatus(StrEnum):
    ELIGIBLE_FOR_RUNTIME_HANDOFF = "eligible_for_runtime_handoff"
    EXTERNAL_APPROVAL_REQUIRED = "external_approval_required"
    INELIGIBLE = "ineligible"


class BindingReason(StrEnum):
    SAFETY_DECISION_STALE = "safety_decision_stale"
    REGISTRY_SELECTION_STALE = "registry_selection_stale"
    SAFETY_BLOCKED = "safety_blocked"
    SAFETY_DEFERRED = "safety_deferred"
    SKILL_UNAVAILABLE = "skill_unavailable"
    CAPABILITY_INCOMPATIBLE = "capability_incompatible"
    PARAMETERS_INCOMPATIBLE = "parameters_incompatible"
    CONTEXT_INCOMPATIBLE = "context_incompatible"
    EXPECTED_RESULT_INCOMPATIBLE = "expected_result_incompatible"
    SAFETY_CLASSIFICATION_INCOMPATIBLE = "safety_classification_incompatible"
    APPROVAL_REQUIREMENTS_INCOMPATIBLE = "approval_requirements_incompatible"
    SAFETY_APPROVAL_REQUIRED = "safety_approval_required"


@dataclass(frozen=True, slots=True, init=False)
class SkillSelection:
    """A registry-pinned request to bind one proposal step to one skill."""

    skill_id: str
    skill_version: SemanticVersion
    skill_fingerprint: SkillFingerprint
    capability_id: str
    source_step_id: str
    registry_version: SemanticVersion
    registry_fingerprint: SkillFingerprint
    fingerprint: SkillFingerprint

    def __init__(
        self,
        *,
        skill_id: str,
        skill_version: SemanticVersion,
        skill_fingerprint: SkillFingerprint,
        capability_id: str,
        source_step_id: str,
        registry_version: SemanticVersion,
        registry_fingerprint: SkillFingerprint,
    ) -> None:
        for value, field_name in (
            (skill_id, "selection skill_id"),
            (capability_id, "selection capability_id"),
            (source_step_id, "selection source_step_id"),
        ):
            validate_identifier(
                value,
                field_name=field_name,
                error_type=SkillInvocationInvariantError,
            )
        if not isinstance(skill_version, SemanticVersion) or not isinstance(
            registry_version, SemanticVersion
        ):
            raise SkillInvocationInvariantError(
                "selection versions must be SemanticVersion objects"
            )
        for value, kind, field_name in (
            (skill_fingerprint, SkillFingerprintKind.SKILL, "skill fingerprint"),
            (
                registry_fingerprint,
                SkillFingerprintKind.REGISTRY,
                "registry fingerprint",
            ),
        ):
            if not isinstance(value, SkillFingerprint) or value.kind is not kind:
                raise SkillInvocationInvariantError(
                    f"selection {field_name} is invalid"
                )
        document: dict[str, JSONValue] = {
            "capability_id": capability_id,
            "registry_fingerprint": str(registry_fingerprint),
            "registry_version": str(registry_version),
            "schema": "ayyo.skill-manager.selection.v1",
            "skill_fingerprint": str(skill_fingerprint),
            "skill_id": skill_id,
            "skill_version": str(skill_version),
            "source_step_id": source_step_id,
        }
        object.__setattr__(self, "skill_id", skill_id)
        object.__setattr__(self, "skill_version", skill_version)
        object.__setattr__(self, "skill_fingerprint", skill_fingerprint)
        object.__setattr__(self, "capability_id", capability_id)
        object.__setattr__(self, "source_step_id", source_step_id)
        object.__setattr__(self, "registry_version", registry_version)
        object.__setattr__(self, "registry_fingerprint", registry_fingerprint)
        object.__setattr__(
            self,
            "fingerprint",
            fingerprint_document(
                SkillFingerprintKind.SELECTION,
                document,
                error_type=SkillInvocationInvariantError,
            ),
        )


class InvocationStatus(StrEnum):
    ELIGIBLE_FOR_RUNTIME_HANDOFF = "eligible_for_runtime_handoff"
    EXTERNAL_APPROVAL_REQUIRED = "external_approval_required"


def _context_document(reference: ContextReference) -> dict[str, JSONValue]:
    return {
        "conflict_ids": [str(item) for item in reference.conflict_ids],
        "domain": reference.requirement.domain.value,
        "memory_ids": [str(item) for item in reference.memory_ids],
        "predicate": reference.requirement.predicate,
        "required": reference.required,
        "state": reference.state.value,
        "value_digests": list(reference.value_digests),
    }


def _approval_document(
    approval: SafetyApprovalRequirement,
) -> dict[str, JSONValue]:
    return {
        "affected_step_id": approval.affected_step_id,
        "approval_class": approval.approval_class.value,
        "description": approval.description,
        "requirement_id": approval.requirement_id,
        "source": approval.source.value,
    }


@dataclass(frozen=True, slots=True, init=False)
class SkillInvocation:
    """An inert, fully pinned request for a future runtime bridge."""

    invocation_id: str
    status: InvocationStatus
    selection: SkillSelection
    skill_definition: SkillDefinition
    backend_id: str
    expected_result: ExpectedResultCategory
    output_schema: ValueSchema
    context_references: tuple[ContextReference, ...]
    required_resources: tuple[ResourceRequirement, ...]
    required_approvals: tuple[SafetyApprovalRequirement, ...]
    safety_classification: HazardClass
    timeout_ms: int
    concurrency_policy: ConcurrencyPolicy
    idempotency: IdempotencyClass
    failure_semantics: FailureSemantics
    lifecycle: SkillLifecycle
    source_request_id: str
    source_executive_decision_id: str
    source_executive_fingerprint: ExecutiveFingerprint
    source_safety_decision_id: str
    source_safety_fingerprint: SafetyFingerprint
    source_proposal_fingerprint: SafetyFingerprint
    source_policy_fingerprint: SafetyFingerprint
    source_policy_version: str
    fingerprint: SkillFingerprint
    _parameters: JSONValue = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        status: InvocationStatus,
        selection: SkillSelection,
        skill_definition: SkillDefinition,
        parameters: dict[str, JSONValue],
        context_references: tuple[ContextReference, ...],
        required_approvals: tuple[SafetyApprovalRequirement, ...],
        source_request_id: str,
        source_executive_decision_id: str,
        source_executive_fingerprint: ExecutiveFingerprint,
        source_safety_decision_id: str,
        source_safety_fingerprint: SafetyFingerprint,
        source_proposal_fingerprint: SafetyFingerprint,
        source_policy_fingerprint: SafetyFingerprint,
        source_policy_version: str,
    ) -> None:
        if not isinstance(status, InvocationStatus):
            raise SkillInvocationInvariantError("invocation status is invalid")
        if type(selection) is not SkillSelection:
            raise SkillInvocationInvariantError("invocation selection is invalid")
        if type(skill_definition) is not SkillDefinition:
            raise SkillInvocationInvariantError("invocation skill definition is invalid")
        if (
            selection.skill_id != skill_definition.skill_id
            or selection.skill_version != skill_definition.version
            or selection.skill_fingerprint != skill_definition.fingerprint
            or selection.capability_id not in skill_definition.capability_ids
        ):
            raise SkillInvocationInvariantError(
                "invocation selection does not match its skill definition"
            )
        try:
            parameter_copy = validate_parameters(
                skill_definition.input_schema,
                parameters,
            )
        except InvalidSkillParametersError as error:
            raise SkillInvocationInvariantError(
                "invocation parameters do not match the skill definition"
            ) from error
        if not isinstance(context_references, tuple) or not all(
            type(item) is ContextReference for item in context_references
        ):
            raise SkillInvocationInvariantError("invocation context references are invalid")
        context_references = tuple(
            sorted(
                context_references,
                key=lambda item: (
                    item.requirement.domain.value,
                    item.requirement.predicate,
                ),
            )
        )
        context_keys = tuple(item.requirement for item in context_references)
        if len(context_keys) != len(set(context_keys)):
            raise SkillInvocationInvariantError("invocation context references must be unique")
        if any(not item.required for item in context_references):
            raise SkillInvocationInvariantError("invocation context references must be required")
        if set(context_keys) != set(skill_definition.required_context):
            raise SkillInvocationInvariantError(
                "invocation context does not match the skill definition"
            )
        if not isinstance(required_approvals, tuple) or not all(
            isinstance(item, SafetyApprovalRequirement) for item in required_approvals
        ):
            raise SkillInvocationInvariantError("invocation approvals are invalid")
        approval_keys = tuple(
            (
                item.affected_step_id,
                item.source.value,
                item.approval_class.value,
                item.requirement_id,
            )
            for item in required_approvals
        )
        if approval_keys != tuple(sorted(set(approval_keys))):
            raise SkillInvocationInvariantError("invocation approvals must be unique and ordered")
        if status is InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF and required_approvals:
            raise SkillInvocationInvariantError("eligible invocation cannot retain approvals")
        if status is InvocationStatus.EXTERNAL_APPROVAL_REQUIRED and not required_approvals:
            raise SkillInvocationInvariantError("approval-gated invocation requires approvals")
        selected_approval_classes = {
            item.approval_class
            for item in required_approvals
            if item.affected_step_id == selection.source_step_id
        }
        if not set(skill_definition.required_approval_classes).issubset(
            selected_approval_classes
        ):
            raise SkillInvocationInvariantError(
                "invocation approvals do not satisfy the selected skill step"
            )
        for value, field_name in (
            (source_request_id, "source_request_id"),
            (source_executive_decision_id, "source_executive_decision_id"),
            (source_safety_decision_id, "source_safety_decision_id"),
        ):
            if type(value) is not str or not value:
                raise SkillInvocationInvariantError(f"invocation {field_name} is invalid")
        if (
            not isinstance(source_executive_fingerprint, ExecutiveFingerprint)
            or source_executive_fingerprint.kind is not ExecutiveFingerprintKind.DECISION
        ):
            raise SkillInvocationInvariantError("source Executive fingerprint is invalid")
        for value, kind, field_name in (
            (source_safety_fingerprint, SafetyFingerprintKind.DECISION, "Safety decision"),
            (source_proposal_fingerprint, SafetyFingerprintKind.PROPOSAL, "proposal"),
            (source_policy_fingerprint, SafetyFingerprintKind.POLICY, "policy"),
        ):
            if not isinstance(value, SafetyFingerprint) or value.kind is not kind:
                raise SkillInvocationInvariantError(f"source {field_name} fingerprint is invalid")
        if type(source_policy_version) is not str or not source_policy_version:
            raise SkillInvocationInvariantError("source policy version is invalid")
        document: dict[str, JSONValue] = {
            "backend_id": skill_definition.backend_id,
            "concurrency_policy": skill_definition.concurrency_policy.value,
            "context_references": [_context_document(item) for item in context_references],
            "expected_result": skill_definition.expected_result.value,
            "failure_semantics": skill_definition.failure_semantics.value,
            "idempotency": skill_definition.idempotency.value,
            "lifecycle": skill_definition.lifecycle.value,
            "output_schema": schema_document(skill_definition.output_schema),
            "parameters": parameter_copy,
            "required_approvals": [_approval_document(item) for item in required_approvals],
            "required_resources": [
                {"access": item.access.value, "resource_id": item.resource_id}
                for item in skill_definition.required_resources
            ],
            "safety_classification": skill_definition.safety_classification.value,
            "schema": "ayyo.skill-manager.invocation.v1",
            "selection_fingerprint": str(selection.fingerprint),
            "source_executive_decision_id": source_executive_decision_id,
            "source_executive_fingerprint": str(source_executive_fingerprint),
            "source_policy_fingerprint": str(source_policy_fingerprint),
            "source_policy_version": source_policy_version,
            "source_proposal_fingerprint": str(source_proposal_fingerprint),
            "source_request_id": source_request_id,
            "source_safety_decision_id": source_safety_decision_id,
            "source_safety_fingerprint": str(source_safety_fingerprint),
            "status": status.value,
            "timeout_ms": skill_definition.timeout_ms,
        }
        fingerprint = fingerprint_document(
            SkillFingerprintKind.INVOCATION,
            document,
            error_type=SkillInvocationInvariantError,
        )
        object.__setattr__(self, "invocation_id", f"skill-invocation-{fingerprint.digest}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "selection", selection)
        object.__setattr__(self, "skill_definition", skill_definition)
        object.__setattr__(self, "backend_id", skill_definition.backend_id)
        object.__setattr__(self, "_parameters", parameter_copy)
        object.__setattr__(self, "expected_result", skill_definition.expected_result)
        object.__setattr__(self, "output_schema", skill_definition.output_schema)
        object.__setattr__(self, "context_references", context_references)
        object.__setattr__(self, "required_resources", skill_definition.required_resources)
        object.__setattr__(self, "required_approvals", required_approvals)
        object.__setattr__(self, "safety_classification", skill_definition.safety_classification)
        object.__setattr__(self, "timeout_ms", skill_definition.timeout_ms)
        object.__setattr__(self, "concurrency_policy", skill_definition.concurrency_policy)
        object.__setattr__(self, "idempotency", skill_definition.idempotency)
        object.__setattr__(self, "failure_semantics", skill_definition.failure_semantics)
        object.__setattr__(self, "lifecycle", skill_definition.lifecycle)
        object.__setattr__(self, "source_request_id", source_request_id)
        object.__setattr__(self, "source_executive_decision_id", source_executive_decision_id)
        object.__setattr__(self, "source_executive_fingerprint", source_executive_fingerprint)
        object.__setattr__(self, "source_safety_decision_id", source_safety_decision_id)
        object.__setattr__(self, "source_safety_fingerprint", source_safety_fingerprint)
        object.__setattr__(self, "source_proposal_fingerprint", source_proposal_fingerprint)
        object.__setattr__(self, "source_policy_fingerprint", source_policy_fingerprint)
        object.__setattr__(self, "source_policy_version", source_policy_version)
        object.__setattr__(self, "fingerprint", fingerprint)

    @property
    def parameters(self) -> dict[str, JSONValue]:
        copied = copy_json(self._parameters, field_name="invocation parameters")
        assert isinstance(copied, dict)
        return copied


@dataclass(frozen=True, slots=True)
class SkillBindingResult:
    status: BindingStatus
    reasons: tuple[BindingReason, ...]
    selection: SkillSelection
    source_safety_decision_id: str
    invocation: SkillInvocation | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, BindingStatus):
            raise SkillInvocationInvariantError("binding result status is invalid")
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, BindingReason) for item in self.reasons
        ):
            raise SkillInvocationInvariantError("binding result reasons are invalid")
        rank = {reason: index for index, reason in enumerate(BindingReason)}
        if self.reasons != tuple(sorted(set(self.reasons), key=rank.get)):
            raise SkillInvocationInvariantError("binding reasons must be unique and ordered")
        if type(self.selection) is not SkillSelection:
            raise SkillInvocationInvariantError("binding selection is invalid")
        if type(self.source_safety_decision_id) is not str or not self.source_safety_decision_id:
            raise SkillInvocationInvariantError("binding Safety decision ID is invalid")
        if self.status is BindingStatus.INELIGIBLE:
            if self.invocation is not None or not self.reasons:
                raise SkillInvocationInvariantError(
                    "ineligible binding requires reasons and no invocation"
                )
            return
        if type(self.invocation) is not SkillInvocation:
            raise SkillInvocationInvariantError("eligible binding requires an invocation")
        expected = (
            InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
            if self.status is BindingStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
            else InvocationStatus.EXTERNAL_APPROVAL_REQUIRED
        )
        if self.invocation.status is not expected:
            raise SkillInvocationInvariantError("binding and invocation statuses disagree")
        if self.invocation.selection != self.selection:
            raise SkillInvocationInvariantError("binding and invocation selections disagree")
        if self.invocation.source_safety_decision_id != self.source_safety_decision_id:
            raise SkillInvocationInvariantError(
                "binding and invocation Safety decision IDs disagree"
            )
        if self.status is BindingStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF and self.reasons:
            raise SkillInvocationInvariantError("eligible binding cannot carry blockers")
        if self.status is BindingStatus.EXTERNAL_APPROVAL_REQUIRED and self.reasons != (
            BindingReason.SAFETY_APPROVAL_REQUIRED,
        ):
            raise SkillInvocationInvariantError(
                "approval-required binding must retain its explicit reason"
            )


def _ordered_reasons(reasons: set[BindingReason]) -> tuple[BindingReason, ...]:
    return tuple(reason for reason in BindingReason if reason in reasons)


@dataclass(frozen=True, slots=True)
class SkillManagerService:
    """Pure contract binder. It exposes no runtime or actuation operation."""

    registry: SkillRegistry
    safety_kernel: SafetyKernel

    def __post_init__(self) -> None:
        if type(self.registry) is not SkillRegistry:
            raise InvalidSkillBindingError("service requires an immutable SkillRegistry")
        if type(self.safety_kernel) is not SafetyKernel:
            raise InvalidSkillBindingError("service requires the public SafetyKernel")

    def bind(
        self,
        proposal: ExecutiveDecision,
        safety_decision: SafetyDecision,
        selection: SkillSelection,
    ) -> SkillBindingResult:
        if type(selection) is not SkillSelection:
            raise InvalidSkillBindingError("binding requires a SkillSelection")
        if type(safety_decision) is not SafetyDecision:
            raise InvalidSkillBindingError("binding requires a SafetyDecision")
        try:
            revalidation = self.safety_kernel.revalidate(safety_decision, proposal)
        except SafetyKernelError as error:
            raise InvalidSkillBindingError(
                "Safety-reviewed proposal could not be revalidated"
            ) from error
        if revalidation.status is SafetyRevalidationStatus.STALE:
            return self._ineligible(
                selection,
                safety_decision,
                {BindingReason.SAFETY_DECISION_STALE},
            )
        try:
            rebuilt_safety_decision = self.safety_kernel.evaluate(proposal)
        except SafetyKernelError as error:
            raise InvalidSkillBindingError(
                "Safety-reviewed proposal failed integrity evaluation"
            ) from error
        if rebuilt_safety_decision != safety_decision:
            raise InvalidSkillBindingError(
                "Safety decision content does not match a fresh policy evaluation"
            )
        skill = self.registry.resolve(selection.skill_id)
        if skill is None:
            return self._ineligible(
                selection,
                safety_decision,
                {BindingReason.REGISTRY_SELECTION_STALE},
            )
        if (
            selection.registry_version != self.registry.version
            or selection.registry_fingerprint != self.registry.fingerprint
            or selection.skill_version != skill.version
            or selection.skill_fingerprint != skill.fingerprint
            or selection.capability_id not in skill.capability_ids
        ):
            return self._ineligible(
                selection,
                safety_decision,
                {BindingReason.REGISTRY_SELECTION_STALE},
            )
        current_selection = self.registry.selection(
            skill_id=skill.skill_id,
            capability_id=selection.capability_id,
            source_step_id=selection.source_step_id,
        )
        if current_selection != selection:
            return self._ineligible(
                selection,
                safety_decision,
                {BindingReason.REGISTRY_SELECTION_STALE},
            )
        if safety_decision.disposition is SafetyDisposition.BLOCKED:
            return self._ineligible(
                selection,
                safety_decision,
                {BindingReason.SAFETY_BLOCKED},
            )
        if safety_decision.disposition is SafetyDisposition.DEFERRED:
            return self._ineligible(
                selection,
                safety_decision,
                {BindingReason.SAFETY_DEFERRED},
            )
        assert proposal.proposed_plan is not None
        step = next(
            (item for item in proposal.proposed_plan.steps if item.step_id == selection.source_step_id),
            None,
        )
        safety_step = next(
            (item for item in safety_decision.step_decisions if item.step_id == selection.source_step_id),
            None,
        )
        reasons: set[BindingReason] = set()
        if step is None or safety_step is None or step.capability_id != selection.capability_id:
            reasons.add(BindingReason.CAPABILITY_INCOMPATIBLE)
        if selection.capability_id not in skill.capability_ids:
            reasons.add(BindingReason.CAPABILITY_INCOMPATIBLE)
        if skill.availability is not SkillAvailability.AVAILABLE:
            reasons.add(BindingReason.SKILL_UNAVAILABLE)
        if step is not None:
            try:
                parameters = validate_parameters(skill.input_schema, step.parameters)
            except InvalidSkillParametersError:
                reasons.add(BindingReason.PARAMETERS_INCOMPATIBLE)
                parameters = {}
            if tuple(step.required_context) != skill.required_context:
                reasons.add(BindingReason.CONTEXT_INCOMPATIBLE)
            if step.expected_result is not skill.expected_result:
                reasons.add(BindingReason.EXPECTED_RESULT_INCOMPATIBLE)
        else:
            parameters = {}
        if safety_step is not None and safety_step.hazard_class is not skill.safety_classification:
            reasons.add(BindingReason.SAFETY_CLASSIFICATION_INCOMPATIBLE)
        safety_approval_classes = {
            item.approval_class
            for item in safety_decision.required_approvals
            if item.affected_step_id == selection.source_step_id
        }
        if not set(skill.required_approval_classes).issubset(safety_approval_classes):
            reasons.add(BindingReason.APPROVAL_REQUIREMENTS_INCOMPATIBLE)
        if reasons:
            return self._ineligible(selection, safety_decision, reasons)
        context_requirements = set(skill.required_context)
        context_references = tuple(
            item
            for item in proposal.context_references
            if item.required and item.requirement in context_requirements
        )
        if {item.requirement for item in context_references} != context_requirements:
            return self._ineligible(
                selection,
                safety_decision,
                {BindingReason.CONTEXT_INCOMPATIBLE},
            )
        approval_required = (
            safety_decision.disposition
            is SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED
        )
        invocation_status = (
            InvocationStatus.EXTERNAL_APPROVAL_REQUIRED
            if approval_required
            else InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
        )
        result_status = (
            BindingStatus.EXTERNAL_APPROVAL_REQUIRED
            if approval_required
            else BindingStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
        )
        invocation = SkillInvocation(
            status=invocation_status,
            selection=selection,
            skill_definition=skill,
            parameters=parameters,
            context_references=context_references,
            required_approvals=safety_decision.required_approvals,
            source_request_id=safety_decision.source_request_id,
            source_executive_decision_id=safety_decision.source_decision_id,
            source_executive_fingerprint=safety_decision.source_decision_fingerprint,
            source_safety_decision_id=safety_decision.decision_id,
            source_safety_fingerprint=safety_decision.decision_fingerprint,
            source_proposal_fingerprint=safety_decision.proposal_fingerprint,
            source_policy_fingerprint=safety_decision.policy_fingerprint,
            source_policy_version=safety_decision.policy_version,
        )
        return SkillBindingResult(
            status=result_status,
            reasons=(BindingReason.SAFETY_APPROVAL_REQUIRED,) if approval_required else (),
            selection=selection,
            source_safety_decision_id=safety_decision.decision_id,
            invocation=invocation,
        )

    @staticmethod
    def _ineligible(
        selection: SkillSelection,
        safety_decision: SafetyDecision,
        reasons: set[BindingReason],
    ) -> SkillBindingResult:
        return SkillBindingResult(
            status=BindingStatus.INELIGIBLE,
            reasons=_ordered_reasons(reasons),
            selection=selection,
            source_safety_decision_id=safety_decision.decision_id,
            invocation=None,
        )
