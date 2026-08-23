from __future__ import annotations

from ayyo_executive import (
    ApprovalRequirement,
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
    ApprovalClass,
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
    ResourceRequirement,
    SkillAvailability,
    SkillDefinition,
    SkillLifecycle,
    SkillManagerService,
    SkillRegistry,
    ValueSchema,
    ValueType,
)

from ayyo_runtime_bridge import (
    RosEndpointAvailability,
    RosServiceEndpoint,
    RuntimeEndpointBinding,
    RuntimeEndpointRegistry,
)


REQUEST_FINGERPRINT = Fingerprint(FingerprintKind.REQUEST, "1" * 64)
CAPABILITY_FINGERPRINT = Fingerprint(FingerprintKind.CAPABILITY_CONTRACT, "2" * 64)
SNAPSHOT_VERSION = ContextSnapshotVersion("3" * 64)


def skill(
    *,
    skill_id: str = "context.inspect.primary",
    version: str = "1.0.0",
    backend_id: str = "future.ros.context",
    capability_ids: tuple[str, ...] = ("context.inspect",),
    input_schema: ValueSchema | None = None,
    output_schema: ValueSchema | None = None,
    required_approval_classes: tuple[ApprovalClass, ...] = (),
    required_resources: tuple[ResourceRequirement, ...] = (),
    concurrency_policy: ConcurrencyPolicy = ConcurrencyPolicy.PARALLEL,
    safety_classification: HazardClass = HazardClass.INFORMATIONAL_READ_ONLY,
    expected_result: ExpectedResultCategory = ExpectedResultCategory.INFORMATION,
    availability: SkillAvailability = SkillAvailability.AVAILABLE,
) -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        version=SemanticVersion(version),
        name="Primary inspection skill",
        description="A deterministic inert runtime-bound test contract.",
        capability_ids=capability_ids,
        backend_id=backend_id,
        input_schema=input_schema or ValueSchema(ValueType.OBJECT),
        output_schema=output_schema or ValueSchema(ValueType.OBJECT),
        required_approval_classes=required_approval_classes,
        required_resources=required_resources,
        safety_classification=safety_classification,
        expected_result=expected_result,
        timeout_ms=1_000,
        concurrency_policy=concurrency_policy,
        idempotency=IdempotencyClass.IDEMPOTENT,
        failure_semantics=FailureSemantics.NON_RETRYABLE,
        availability=availability,
        lifecycle=SkillLifecycle.VALIDATED,
    )


def endpoint(
    definition: SkillDefinition,
    *,
    endpoint_id: str = "context.inspect.service",
    endpoint_name: str = "inspect_context",
    namespace: str = "/ayyo/runtime",
    availability: RosEndpointAvailability = RosEndpointAvailability.AVAILABLE,
) -> RosServiceEndpoint:
    return RosServiceEndpoint(
        endpoint_id=endpoint_id,
        backend_id=definition.backend_id,
        package_name="ayyo_interfaces",
        interface_name="InspectContext",
        endpoint_name=endpoint_name,
        namespace=namespace,
        request_schema=definition.input_schema,
        response_schema=definition.output_schema,
        timeout_ms=definition.timeout_ms,
        availability=availability,
    )


def proposal(
    *,
    parameters: dict | None = None,
    request_id: str = "request-1",
    step_id: str = "step-1",
    capability_id: str = "context.inspect",
    required_approvals: tuple[ApprovalRequirement, ...] = (),
    expected_result: ExpectedResultCategory = ExpectedResultCategory.INFORMATION,
) -> ExecutiveDecision:
    step = PlanStep(
        step_id=step_id,
        capability_id=capability_id,
        parameters={} if parameters is None else parameters,
        dependencies=(),
        preconditions=(),
        required_context=(),
        required_approvals=required_approvals,
        constraints=(),
        expected_result=expected_result,
        failure_policy=FailurePolicy.STOP_PLAN,
    )
    return ExecutiveDecision(
        request_id=request_id,
        owner_subject="owner",
        decision_type=(
            ExecutiveDecisionType.REQUEST_APPROVAL
            if required_approvals
            else ExecutiveDecisionType.PROPOSE
        ),
        reason_codes=(
            (DecisionReason.APPROVAL_REQUIRED,)
            if required_approvals
            else (DecisionReason.READY_FOR_SAFETY_REVIEW,)
        ),
        explanation="Bind this inert proposal to a runtime test endpoint.",
        context_snapshot_version=SNAPSHOT_VERSION,
        request_fingerprint=REQUEST_FINGERPRINT,
        capability_contract_fingerprint=CAPABILITY_FINGERPRINT,
        context_references=(),
        assumptions=(),
        required_capabilities=(capability_id,),
        required_approvals=required_approvals,
        constraints=(),
        proposed_plan=Plan((step,)),
    )


def skill_binding(
    definition: SkillDefinition,
    *,
    source_proposal: ExecutiveDecision | None = None,
):
    source = source_proposal or proposal(capability_id=definition.capability_ids[0])
    kernel = SafetyKernel(
        SafetyPolicy(
            capability_rules=(
                CapabilitySafetyRule(
                    capability_id=definition.capability_ids[0],
                    hazard_class=definition.safety_classification,
                ),
            )
        )
    )
    skill_registry = SkillRegistry(
        version=SemanticVersion("1.0.0"),
        skills=(definition,),
    )
    manager = SkillManagerService(skill_registry, kernel)
    decision = kernel.evaluate(source)
    selection = skill_registry.selection(
        skill_id=definition.skill_id,
        capability_id=definition.capability_ids[0],
        source_step_id=source.proposed_plan.steps[0].step_id,
    )
    return manager.bind(source, decision, selection)


def runtime_registry(
    definition: SkillDefinition,
    *,
    contract: RosServiceEndpoint | None = None,
    version: str = "1.0.0",
) -> RuntimeEndpointRegistry:
    endpoint_contract = contract or endpoint(definition)
    binding = RuntimeEndpointBinding(
        skill_definition=definition,
        capability_id=definition.capability_ids[0],
        endpoint=endpoint_contract,
    )
    return RuntimeEndpointRegistry(
        version=SemanticVersion(version),
        bindings=(binding,),
    )
