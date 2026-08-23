from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_executive import ExpectedResultCategory
from ayyo_safety import HazardClass
from ayyo_skill_manager import (
    BindingReason,
    BindingStatus,
    InvalidSchemaError,
    InvocationStatus,
    MAX_SCHEMA_DEPTH,
    SchemaProperty,
    SkillBindingResult,
    SkillInvocationInvariantError,
    ValueSchema,
    ValueType,
)

from helpers import plan_step, proposal, service, skill


class AdversarialInvariantTest(unittest.TestCase):
    def test_forged_cyclic_schema_is_rejected_at_skill_boundary(self) -> None:
        cyclic = ValueSchema(ValueType.OBJECT)
        property_definition = SchemaProperty("self", cyclic)
        object.__setattr__(cyclic, "properties", (property_definition,))
        with self.assertRaisesRegex(InvalidSchemaError, "cycles"):
            skill(input_schema=cyclic)

    def test_excessively_deep_schema_is_rejected_at_skill_boundary(self) -> None:
        nested = ValueSchema(ValueType.STRING)
        for index in range(MAX_SCHEMA_DEPTH + 1):
            nested = ValueSchema(
                ValueType.OBJECT,
                properties=(SchemaProperty(f"level-{index}", nested),),
            )
        with self.assertRaisesRegex(InvalidSchemaError, "depth limit"):
            skill(input_schema=nested)

    def test_shared_noncyclic_schema_is_accepted(self) -> None:
        shared = ValueSchema(ValueType.STRING)
        definition = skill(
            input_schema=ValueSchema(
                ValueType.OBJECT,
                properties=(
                    SchemaProperty("first", shared),
                    SchemaProperty("second", shared),
                ),
            )
        )
        self.assertIs(definition.input_schema.properties[0].schema, shared)
        self.assertIs(definition.input_schema.properties[1].schema, shared)

    def test_capability_selection_mismatch_never_creates_invocation(self) -> None:
        definition = skill(capability_ids=("context.inspect", "context.read"))
        manager = service(definition)
        source = proposal((plan_step(capability_id="context.inspect"),))
        decision = manager.safety_kernel.evaluate(source)
        selection = manager.registry.selection(
            skill_id=definition.skill_id,
            capability_id="context.read",
            source_step_id="step-1",
        )
        result = manager.bind(source, decision, selection)
        self.assertEqual(BindingStatus.INELIGIBLE, result.status)
        self.assertEqual((BindingReason.CAPABILITY_INCOMPATIBLE,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_context_contract_mismatch_never_creates_invocation(self) -> None:
        from ayyo_executive import ContextRequirement
        from ayyo_personal_context import ContextDomain

        required = ContextRequirement(ContextDomain.SEMANTIC, "profile")
        manager = service(skill(required_context=(required,)))
        source = proposal((plan_step(),))
        result = manager.bind(
            source,
            manager.safety_kernel.evaluate(source),
            manager.registry.selection(
                skill_id="context.inspect.primary",
                capability_id="context.inspect",
                source_step_id="step-1",
            ),
        )
        self.assertEqual((BindingReason.CONTEXT_INCOMPATIBLE,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_claimed_approval_parameter_cannot_bypass_physical_deferral(self) -> None:
        definition = skill(
            input_schema=ValueSchema(
                ValueType.OBJECT,
                allow_additional_properties=True,
            ),
            safety_classification=HazardClass.PHYSICAL_MOVEMENT,
            expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
        )
        manager = service(definition)
        source = proposal(
            (
                plan_step(
                    parameters={"approved": True, "is_safe": True},
                    expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
                ),
            )
        )
        decision = manager.safety_kernel.evaluate(source)
        selection = manager.registry.selection(
            skill_id=definition.skill_id,
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        result = manager.bind(source, decision, selection)
        self.assertEqual((BindingReason.SAFETY_DEFERRED,), result.reasons)
        self.assertIsNone(result.invocation)

    def test_ineligible_result_cannot_hide_an_invocation(self) -> None:
        manager = service(skill())
        source = proposal((plan_step(),))
        decision = manager.safety_kernel.evaluate(source)
        selection = manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        valid = manager.bind(source, decision, selection)
        with self.assertRaises(SkillInvocationInvariantError):
            SkillBindingResult(
                status=BindingStatus.INELIGIBLE,
                reasons=(BindingReason.SAFETY_BLOCKED,),
                selection=selection,
                source_safety_decision_id=decision.decision_id,
                invocation=valid.invocation,
            )

    def test_approval_result_cannot_claim_eligible_invocation_status(self) -> None:
        manager = service(skill())
        source = proposal((plan_step(),))
        decision = manager.safety_kernel.evaluate(source)
        selection = manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        valid = manager.bind(source, decision, selection)
        self.assertEqual(
            InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF,
            valid.invocation.status,
        )
        with self.assertRaises(SkillInvocationInvariantError):
            SkillBindingResult(
                status=BindingStatus.EXTERNAL_APPROVAL_REQUIRED,
                reasons=(BindingReason.SAFETY_APPROVAL_REQUIRED,),
                selection=selection,
                source_safety_decision_id=decision.decision_id,
                invocation=valid.invocation,
            )

    def test_selection_and_result_are_immutable(self) -> None:
        manager = service(skill())
        source = proposal((plan_step(),))
        decision = manager.safety_kernel.evaluate(source)
        selection = manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        result = manager.bind(source, decision, selection)
        with self.assertRaises(FrozenInstanceError):
            selection.capability_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            result.status = BindingStatus.INELIGIBLE

    def test_relevant_upstream_identity_changes_invocation_fingerprint(self) -> None:
        manager = service(skill())
        first = proposal((plan_step(),), request_id="request-1")
        second = proposal((plan_step(),), request_id="request-2")
        selection = manager.registry.selection(
            skill_id="context.inspect.primary",
            capability_id="context.inspect",
            source_step_id="step-1",
        )
        first_result = manager.bind(
            first,
            manager.safety_kernel.evaluate(first),
            selection,
        )
        second_result = manager.bind(
            second,
            manager.safety_kernel.evaluate(second),
            selection,
        )
        self.assertNotEqual(
            first_result.invocation.fingerprint,
            second_result.invocation.fingerprint,
        )


if __name__ == "__main__":
    unittest.main()
