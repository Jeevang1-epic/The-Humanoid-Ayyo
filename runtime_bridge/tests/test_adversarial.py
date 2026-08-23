from __future__ import annotations

import unittest

from ayyo_skill_manager import (
    ConcurrencyPolicy,
    ResourceAccess,
    ResourceRequirement,
    SchemaProperty,
    SemanticVersion,
    SkillBindingResult,
    ValueSchema,
    ValueType,
)

from ayyo_runtime_bridge import (
    InvalidRosEndpointError,
    InvalidRuntimeBindingError,
    InvalidRuntimeRegistryError,
    RosEndpointAvailability,
    RuntimeBridge,
    RuntimeEligibility,
    RuntimeEndpointBinding,
    RuntimeEndpointRegistry,
    RuntimeReason,
)

from helpers import endpoint, proposal, runtime_registry, skill, skill_binding


class RuntimeAdversarialTest(unittest.TestCase):
    def test_changed_parameters_are_stale_not_reused(self) -> None:
        schema = ValueSchema(
            ValueType.OBJECT,
            properties=(
                SchemaProperty("query", ValueSchema(ValueType.STRING)),
            ),
        )
        definition = skill(input_schema=schema)
        original = skill_binding(
            definition,
            source_proposal=proposal(parameters={"query": "first"}),
        )
        changed = skill_binding(
            definition,
            source_proposal=proposal(parameters={"query": "second"}),
        )
        bridge = RuntimeBridge(runtime_registry(definition))
        stale = bridge.revalidate(bridge.evaluate(original), changed)
        self.assertIs(RuntimeEligibility.STALE, stale.status)
        self.assertIn(RuntimeReason.UPSTREAM_BINDING_CHANGED, stale.reasons)

    def test_cross_step_substitution_is_stale(self) -> None:
        definition = skill()
        first = skill_binding(
            definition,
            source_proposal=proposal(step_id="step-1"),
        )
        second = skill_binding(
            definition,
            source_proposal=proposal(step_id="step-2"),
        )
        bridge = RuntimeBridge(runtime_registry(definition))
        prior = bridge.evaluate(first)
        stale = bridge.revalidate(prior, second)
        self.assertIs(RuntimeEligibility.STALE, stale.status)
        self.assertIn(RuntimeReason.UPSTREAM_BINDING_CHANGED, stale.reasons)
        self.assertNotEqual(
            first.invocation.selection.source_step_id,
            second.invocation.selection.source_step_id,
        )

    def test_cross_skill_substitution_is_rejected(self) -> None:
        registered = skill()
        substituted = skill(skill_id="context.inspect.substitute")
        bridge = RuntimeBridge(runtime_registry(registered))
        decision = bridge.evaluate(skill_binding(substituted))
        self.assertIs(RuntimeEligibility.REJECTED, decision.status)
        self.assertEqual((RuntimeReason.ENDPOINT_NOT_REGISTERED,), decision.reasons)

    def test_unknown_backend_is_rejected(self) -> None:
        registered = skill()
        unknown_backend = skill(backend_id="future.ros.unknown")
        decision = RuntimeBridge(runtime_registry(registered)).evaluate(
            skill_binding(unknown_backend)
        )
        self.assertIs(RuntimeEligibility.REJECTED, decision.status)
        self.assertEqual((RuntimeReason.ENDPOINT_NOT_REGISTERED,), decision.reasons)

    def test_capability_substitution_fails_invocation_integrity(self) -> None:
        definition = skill(capability_ids=("context.inspect", "context.read"))
        result = skill_binding(definition)
        object.__setattr__(
            result.invocation.selection,
            "capability_id",
            "context.read",
        )
        with self.assertRaisesRegex(InvalidRuntimeBindingError, "selection"):
            RuntimeBridge(runtime_registry(definition)).evaluate(result)

    def test_mismatched_invocation_and_binding_result_fail_integrity(self) -> None:
        first = skill_binding(skill())
        second = skill_binding(skill(skill_id="context.inspect.substitute"))
        forged = SkillBindingResult(
            status=first.status,
            reasons=first.reasons,
            selection=first.selection,
            source_safety_decision_id=first.source_safety_decision_id,
            invocation=first.invocation,
        )
        object.__setattr__(forged, "invocation", second.invocation)
        with self.assertRaisesRegex(InvalidRuntimeBindingError, "integrity"):
            RuntimeBridge(runtime_registry(skill())).evaluate(forged)

    def test_changed_policy_identity_fails_invocation_integrity(self) -> None:
        definition = skill()
        result = skill_binding(definition)
        object.__setattr__(
            result.invocation,
            "source_policy_version",
            "ayyo.safety.policy.v2",
        )
        with self.assertRaisesRegex(InvalidRuntimeBindingError, "fingerprint is stale"):
            RuntimeBridge(runtime_registry(definition)).evaluate(result)

    def test_changed_required_context_fails_invocation_integrity(self) -> None:
        definition = skill()
        result = skill_binding(definition)
        object.__setattr__(result.invocation, "context_references", (object(),))
        with self.assertRaisesRegex(InvalidRuntimeBindingError, "integrity"):
            RuntimeBridge(runtime_registry(definition)).evaluate(result)

    def test_cyclic_parameter_tampering_fails_typed(self) -> None:
        definition = skill()
        result = skill_binding(definition)
        cyclic: dict[str, object] = {}
        cyclic["cycle"] = cyclic
        object.__setattr__(result.invocation, "_parameters", cyclic)
        with self.assertRaisesRegex(InvalidRuntimeBindingError, "integrity"):
            RuntimeBridge(runtime_registry(definition)).evaluate(result)

    def test_forged_semantic_versions_are_reconstructed(self) -> None:
        forged = SemanticVersion("1.0.0")
        object.__setattr__(forged, "value", "01.0.0")
        with self.assertRaisesRegex(InvalidRuntimeRegistryError, "version"):
            RuntimeEndpointRegistry(version=forged, bindings=())

    def test_forged_schema_is_reconstructed_at_endpoint_boundary(self) -> None:
        definition = skill()
        forged_schema = ValueSchema(ValueType.OBJECT)
        object.__setattr__(forged_schema, "nullable", True)
        with self.assertRaises(InvalidRosEndpointError):
            type(endpoint(definition))(
                endpoint_id="context.inspect.forged",
                backend_id=definition.backend_id,
                package_name="ayyo_interfaces",
                interface_name="InspectContext",
                endpoint_name="inspect_context",
                namespace="/ayyo/runtime",
                request_schema=forged_schema,
                response_schema=definition.output_schema,
                timeout_ms=1_000,
                availability=RosEndpointAvailability.AVAILABLE,
            )

    def test_unknown_endpoint_contract_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(InvalidRuntimeRegistryError, "ROS endpoint"):
            RuntimeEndpointBinding(
                skill_definition=skill(),
                capability_id="context.inspect",
                endpoint=object(),
            )

    def test_resources_and_concurrency_are_retained_not_scheduled(self) -> None:
        resource = ResourceRequirement("context.store", ResourceAccess.SHARED)
        definition = skill(
            required_resources=(resource,),
            concurrency_policy=ConcurrencyPolicy.RESOURCE_GOVERNED,
        )
        decision = RuntimeBridge(runtime_registry(definition)).evaluate(
            skill_binding(definition)
        )
        self.assertIs(RuntimeEligibility.ELIGIBLE, decision.status)
        self.assertEqual((resource,), decision.request.invocation.required_resources)
        self.assertIs(
            ConcurrencyPolicy.RESOURCE_GOVERNED,
            decision.request.invocation.concurrency_policy,
        )

    def test_endpoint_availability_change_alters_registry_identity(self) -> None:
        definition = skill()
        available = runtime_registry(definition)
        disabled = runtime_registry(
            definition,
            contract=endpoint(
                definition,
                availability=RosEndpointAvailability.DISABLED,
            ),
        )
        self.assertNotEqual(available.fingerprint, disabled.fingerprint)


if __name__ == "__main__":
    unittest.main()
