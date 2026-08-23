from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_executive import ApprovalRequirement, ExpectedResultCategory
from ayyo_safety import (
    ApprovalClass,
    CapabilitySafetyRule,
    HazardClass,
    SafetyDisposition,
    SafetyKernel,
    SafetyPolicy,
)
from ayyo_skill_manager import (
    BindingReason,
    BindingStatus,
    InvalidSkillBindingError,
    InvocationStatus,
    SchemaProperty,
    SkillAvailability,
    SkillInvocation,
    SkillInvocationInvariantError,
    SkillManagerService,
    SkillRegistry,
    SemanticVersion,
    ValueSchema,
    ValueType,
)

from helpers import plan_step, proposal, service, skill


class SafetyBindingTest(unittest.TestCase):
    def bind(self, manager, source_proposal):
        safety_decision = manager.safety_kernel.evaluate(source_proposal)
        selection = manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id=source_proposal.proposed_plan.steps[0].capability_id,
            source_step_id=source_proposal.proposed_plan.steps[0].step_id,
        )
        return manager.bind(source_proposal, safety_decision, selection)

    def test_eligible_safety_decision_creates_pinned_inert_invocation(self) -> None:
        manager = service(skill())
        result = self.bind(manager, proposal((plan_step(),)))
        self.assertEqual(BindingStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF, result.status)
        self.assertEqual((), result.reasons)
        self.assertIsNotNone(result.invocation)
        invocation = result.invocation
        self.assertEqual(InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF, invocation.status)
        self.assertEqual("future.ros.context", invocation.backend_id)
        self.assertEqual({}, invocation.parameters)
        self.assertEqual(
            result.source_safety_decision_id,
            invocation.source_safety_decision_id,
        )
        self.assertEqual(
            f"skill-invocation-{invocation.fingerprint.digest}",
            invocation.invocation_id,
        )

    def test_approval_required_is_preserved_and_never_upgraded(self) -> None:
        approval = ApprovalRequirement("owner-confirmation", "Owner must confirm.")
        definition = skill(
            required_approval_classes=(ApprovalClass.EXECUTIVE_DECLARED,),
        )
        manager = service(definition)
        source = proposal((plan_step(required_approvals=(approval,)),))
        result = self.bind(manager, source)
        self.assertEqual(BindingStatus.EXTERNAL_APPROVAL_REQUIRED, result.status)
        self.assertEqual((BindingReason.SAFETY_APPROVAL_REQUIRED,), result.reasons)
        self.assertEqual(
            InvocationStatus.EXTERNAL_APPROVAL_REQUIRED,
            result.invocation.status,
        )
        self.assertTrue(result.invocation.required_approvals)
        self.assertTrue(
            all(
                item.approval_class is ApprovalClass.EXECUTIVE_DECLARED
                for item in result.invocation.required_approvals
            )
        )

    def test_blocked_safety_decision_never_creates_invocation(self) -> None:
        definition = skill(safety_classification=HazardClass.EMERGENCY_SAFETY_CRITICAL)
        manager = service(definition)
        source = proposal((plan_step(),))
        safety_decision = manager.safety_kernel.evaluate(source)
        self.assertEqual(SafetyDisposition.BLOCKED, safety_decision.disposition)
        selection = manager.registry.selection(
            skill_id=definition.skill_id,
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        result = manager.bind(source, safety_decision, selection)
        self.assertEqual(BindingStatus.INELIGIBLE, result.status)
        self.assertEqual((BindingReason.SAFETY_BLOCKED,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_deferred_safety_decision_never_creates_invocation(self) -> None:
        definition = skill(
            safety_classification=HazardClass.PHYSICAL_MOVEMENT,
            expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
        )
        manager = service(definition)
        source = proposal(
            (
                plan_step(
                    expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
                ),
            )
        )
        result = self.bind(manager, source)
        self.assertEqual(BindingStatus.INELIGIBLE, result.status)
        self.assertEqual((BindingReason.SAFETY_DEFERRED,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_changed_proposal_makes_safety_decision_stale(self) -> None:
        manager = service(skill())
        original = proposal((plan_step(parameters={}),))
        decision = manager.safety_kernel.evaluate(original)
        changed = proposal((plan_step(parameters={"changed": True}),))
        selection = manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        result = manager.bind(changed, decision, selection)
        self.assertEqual(BindingStatus.INELIGIBLE, result.status)
        self.assertEqual((BindingReason.SAFETY_DECISION_STALE,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_forged_safety_decision_content_is_rejected(self) -> None:
        manager = service(skill())
        source = proposal((plan_step(),))
        decision = manager.safety_kernel.evaluate(source)
        object.__setattr__(decision, "disposition", SafetyDisposition.BLOCKED)
        selection = manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        with self.assertRaisesRegex(InvalidSkillBindingError, "fresh policy"):
            manager.bind(source, decision, selection)

    def test_stale_registry_selection_is_ineligible(self) -> None:
        first_manager = service(skill())
        changed_manager = service(skill(availability=SkillAvailability.DISABLED))
        source = proposal((plan_step(),))
        decision = changed_manager.safety_kernel.evaluate(source)
        old_selection = first_manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        result = changed_manager.bind(source, decision, old_selection)
        self.assertEqual((BindingReason.REGISTRY_SELECTION_STALE,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_stale_selection_capability_is_ineligible_not_an_exception(self) -> None:
        old_manager = service(skill(capability_ids=("context.inspect", "context.read")))
        new_manager = service(skill(capability_ids=("context.inspect",)))
        source = proposal((plan_step(),))
        decision = new_manager.safety_kernel.evaluate(source)
        old_selection = old_manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id="context.read",
            source_step_id="step-1",
        )
        result = new_manager.bind(source, decision, old_selection)
        self.assertEqual((BindingReason.REGISTRY_SELECTION_STALE,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_unavailable_skill_is_ineligible(self) -> None:
        manager = service(skill(availability=SkillAvailability.DEGRADED))
        result = self.bind(manager, proposal((plan_step(),)))
        self.assertIn(BindingReason.SKILL_UNAVAILABLE, result.reasons)
        self.assertIsNone(result.invocation)

    def test_parameter_mismatch_is_ineligible(self) -> None:
        input_schema = ValueSchema(
            ValueType.OBJECT,
            properties=(
                SchemaProperty("key", ValueSchema(ValueType.STRING)),
            ),
        )
        manager = service(skill(input_schema=input_schema))
        result = self.bind(manager, proposal((plan_step(parameters={}),)))
        self.assertEqual((BindingReason.PARAMETERS_INCOMPATIBLE,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_expected_result_and_safety_classification_mismatch_fail_closed(self) -> None:
        definition = skill(expected_result=ExpectedResultCategory.PROPOSED_STATE_CHANGE)
        manager = service(definition)
        source = proposal((plan_step(expected_result=ExpectedResultCategory.INFORMATION),))
        result = self.bind(manager, source)
        self.assertIn(BindingReason.EXPECTED_RESULT_INCOMPATIBLE, result.reasons)
        self.assertIsNone(result.invocation)

        classification_manager = service(
            skill(),
            hazard_class=HazardClass.INTERNAL_NON_ACTUATING,
        )
        result = self.bind(classification_manager, proposal((plan_step(),)))
        self.assertIn(
            BindingReason.SAFETY_CLASSIFICATION_INCOMPATIBLE,
            result.reasons,
        )
        self.assertIsNone(result.invocation)

    def test_missing_required_approval_class_is_incompatible(self) -> None:
        manager = service(
            skill(required_approval_classes=(ApprovalClass.PRIVILEGED_HIGH_IMPACT,))
        )
        result = self.bind(manager, proposal((plan_step(),)))
        self.assertIn(
            BindingReason.APPROVAL_REQUIREMENTS_INCOMPATIBLE,
            result.reasons,
        )
        self.assertIsNone(result.invocation)

    def test_approval_on_another_step_cannot_satisfy_selected_skill(self) -> None:
        approval = ApprovalRequirement("owner-confirmation", "Owner must confirm.")
        definition = skill(
            required_approval_classes=(ApprovalClass.EXECUTIVE_DECLARED,),
        )
        registry = SkillRegistry(
            version=SemanticVersion("1.0.0"),
            skills=(definition,),
        )
        kernel = SafetyKernel(
            SafetyPolicy(
                capability_rules=(
                    CapabilitySafetyRule(
                        capability_id="context.inspect",
                        hazard_class=HazardClass.INFORMATIONAL_READ_ONLY,
                    ),
                    CapabilitySafetyRule(
                        capability_id="context.other",
                        hazard_class=HazardClass.INFORMATIONAL_READ_ONLY,
                    ),
                )
            )
        )
        manager = SkillManagerService(registry, kernel)
        source = proposal(
            (
                plan_step(step_id="step-1"),
                plan_step(
                    step_id="step-2",
                    capability_id="context.other",
                    required_approvals=(approval,),
                ),
            )
        )
        decision = kernel.evaluate(source)
        selection = registry.selection(
            skill_id=definition.skill_id,
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        result = manager.bind(source, decision, selection)
        self.assertIn(
            BindingReason.APPROVAL_REQUIREMENTS_INCOMPATIBLE,
            result.reasons,
        )
        self.assertIsNone(result.invocation)

    def test_invocation_parameters_are_immutable_defensive_data(self) -> None:
        input_schema = ValueSchema(
            ValueType.OBJECT,
            properties=(
                SchemaProperty(
                    "nested",
                    ValueSchema(ValueType.OBJECT, allow_additional_properties=True),
                ),
            ),
        )
        manager = service(skill(input_schema=input_schema))
        result = self.bind(
            manager,
            proposal((plan_step(parameters={"nested": {"values": [1]}}),)),
        )
        returned = result.invocation.parameters
        returned["nested"]["values"].append(2)
        self.assertEqual({"nested": {"values": [1]}}, result.invocation.parameters)
        with self.assertRaises(FrozenInstanceError):
            result.invocation.backend_id = "changed"

    def test_equivalent_inputs_produce_identical_invocation(self) -> None:
        input_schema = ValueSchema(ValueType.OBJECT, allow_additional_properties=True)
        manager = service(skill(input_schema=input_schema))
        left = self.bind(
            manager,
            proposal((plan_step(parameters={"z": 2, "a": {"b": 1}}),)),
        )
        right = self.bind(
            manager,
            proposal((plan_step(parameters={"a": {"b": 1}, "z": 2}),)),
        )
        self.assertEqual(left.invocation.fingerprint, right.invocation.fingerprint)
        self.assertEqual(left.invocation.invocation_id, right.invocation.invocation_id)

    def test_public_invocation_rejects_a_mismatched_skill_contract(self) -> None:
        manager = service(skill())
        source = proposal((plan_step(),))
        result = self.bind(manager, source)
        invocation = result.invocation
        mismatched_skill = skill(skill_id="context.inspect.alternate")
        with self.assertRaisesRegex(
            SkillInvocationInvariantError,
            "does not match",
        ):
            SkillInvocation(
                status=invocation.status,
                selection=invocation.selection,
                skill_definition=mismatched_skill,
                parameters=invocation.parameters,
                context_references=invocation.context_references,
                required_approvals=invocation.required_approvals,
                source_request_id=invocation.source_request_id,
                source_executive_decision_id=invocation.source_executive_decision_id,
                source_executive_fingerprint=invocation.source_executive_fingerprint,
                source_safety_decision_id=invocation.source_safety_decision_id,
                source_safety_fingerprint=invocation.source_safety_fingerprint,
                source_proposal_fingerprint=invocation.source_proposal_fingerprint,
                source_policy_fingerprint=invocation.source_policy_fingerprint,
                source_policy_version=invocation.source_policy_version,
            )


if __name__ == "__main__":
    unittest.main()
