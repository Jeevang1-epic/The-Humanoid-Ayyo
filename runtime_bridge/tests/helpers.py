from __future__ import annotations

from ayyo_executive import ExpectedResultCategory
from ayyo_safety import HazardClass
from ayyo_skill_manager import (
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillLifecycle,
    ValueSchema,
    ValueType,
)

from ayyo_runtime_bridge import RosEndpointAvailability, RosServiceEndpoint


def skill(
    *,
    skill_id: str = "context.inspect.primary",
    version: str = "1.0.0",
    backend_id: str = "future.ros.context",
    capability_ids: tuple[str, ...] = ("context.inspect",),
    input_schema: ValueSchema | None = None,
    output_schema: ValueSchema | None = None,
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
        safety_classification=HazardClass.INFORMATIONAL_READ_ONLY,
        expected_result=ExpectedResultCategory.INFORMATION,
        timeout_ms=1_000,
        concurrency_policy=ConcurrencyPolicy.PARALLEL,
        idempotency=IdempotencyClass.IDEMPOTENT,
        failure_semantics=FailureSemantics.NON_RETRYABLE,
        availability=SkillAvailability.AVAILABLE,
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
