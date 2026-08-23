from __future__ import annotations

from ayyo_executive import (
    ApprovalRequirement,
    ContextReference,
    ContextRequirement,
    DecisionReason,
    ExecutiveDecision,
    ExecutiveDecisionType,
    ExpectedResultCategory,
    FailurePolicy,
    Fingerprint,
    FingerprintKind,
    Plan,
    PlanStep,
)
from ayyo_personal_context import ContextSnapshotVersion
from ayyo_safety import (
    CapabilitySafetyRule,
    HazardClass,
    SafetyKernel,
    SafetyPolicy,
)
from ayyo_skill_manager import (
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillLifecycle,
    SkillManagerService,
    SkillRegistry,
    ValueSchema,
    ValueType,
)


REQUEST_FINGERPRINT = Fingerprint(FingerprintKind.REQUEST, "1" * 64)
CAPABILITY_FINGERPRINT = Fingerprint(
    FingerprintKind.CAPABILITY_CONTRACT,
    "2" * 64,
)
SNAPSHOT_VERSION = ContextSnapshotVersion("3" * 64)


def plan_step(
    *,
    step_id: str = "step-1",
    capability_id: str = "context.inspect",
    parameters: dict | None = None,
    required_context: tuple[ContextRequirement, ...] = (),
    required_approvals: tuple[ApprovalRequirement, ...] = (),
    expected_result: ExpectedResultCategory = ExpectedResultCategory.INFORMATION,
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        capability_id=capability_id,
        parameters={} if parameters is None else parameters,
        dependencies=(),
        preconditions=(),
        required_context=required_context,
        required_approvals=required_approvals,
        constraints=(),
        expected_result=expected_result,
        failure_policy=FailurePolicy.STOP_PLAN,
    )


def proposal(
    steps: tuple[PlanStep, ...],
    *,
    context_references: tuple[ContextReference, ...] = (),
    request_id: str = "request-1",
) -> ExecutiveDecision:
    approvals = tuple(
        sorted(
            {
                approval.approval_id: approval
                for step in steps
                for approval in step.required_approvals
            }.values(),
            key=lambda item: item.approval_id,
        )
    )
    decision_type = (
        ExecutiveDecisionType.REQUEST_APPROVAL
        if approvals
        else ExecutiveDecisionType.PROPOSE
    )
    reason = (
        DecisionReason.APPROVAL_REQUIRED
        if approvals
        else DecisionReason.READY_FOR_SAFETY_REVIEW
    )
    return ExecutiveDecision(
        request_id=request_id,
        owner_subject="owner",
        decision_type=decision_type,
        reason_codes=(reason,),
        explanation="Bind this inert test proposal to a declarative skill.",
        context_snapshot_version=SNAPSHOT_VERSION,
        request_fingerprint=REQUEST_FINGERPRINT,
        capability_contract_fingerprint=CAPABILITY_FINGERPRINT,
        context_references=context_references,
        assumptions=(),
        required_capabilities=tuple(sorted({step.capability_id for step in steps})),
        required_approvals=approvals,
        constraints=(),
        proposed_plan=Plan(steps),
    )


def skill(
    *,
    skill_id: str = "context.inspect.primary",
    capability_ids: tuple[str, ...] = ("context.inspect",),
    input_schema: ValueSchema | None = None,
    required_context: tuple[ContextRequirement, ...] = (),
    required_approval_classes=(),
    safety_classification: HazardClass = HazardClass.INFORMATIONAL_READ_ONLY,
    expected_result: ExpectedResultCategory = ExpectedResultCategory.INFORMATION,
    availability: SkillAvailability = SkillAvailability.AVAILABLE,
) -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        version=SemanticVersion("1.0.0"),
        name="Primary inspection skill",
        description="A deterministic inert contract used only by tests.",
        capability_ids=capability_ids,
        backend_id="future.ros.context",
        input_schema=input_schema or ValueSchema(ValueType.OBJECT),
        output_schema=ValueSchema(ValueType.OBJECT),
        required_context=required_context,
        required_approval_classes=required_approval_classes,
        safety_classification=safety_classification,
        expected_result=expected_result,
        timeout_ms=1_000,
        concurrency_policy=ConcurrencyPolicy.PARALLEL,
        idempotency=IdempotencyClass.IDEMPOTENT,
        failure_semantics=FailureSemantics.NON_RETRYABLE,
        availability=availability,
        lifecycle=SkillLifecycle.VALIDATED,
    )


def service(
    definition: SkillDefinition,
    *,
    hazard_class: HazardClass | None = None,
) -> SkillManagerService:
    classification = hazard_class or definition.safety_classification
    kernel = SafetyKernel(
        SafetyPolicy(
            capability_rules=tuple(
                CapabilitySafetyRule(
                    capability_id=capability_id,
                    hazard_class=classification,
                )
                for capability_id in definition.capability_ids
            )
        )
    )
    registry = SkillRegistry(
        version=SemanticVersion("1.0.0"),
        skills=(definition,),
    )
    return SkillManagerService(registry, kernel)
