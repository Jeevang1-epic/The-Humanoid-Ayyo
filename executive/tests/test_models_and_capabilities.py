import dataclasses
import unittest

from ayyo_executive import (
    ApprovalRequirement,
    CapabilityAvailability,
    CapabilityDefinition,
    CapabilityInvocation,
    CapabilityRegistry,
    Constraint,
    ContextReference,
    ContextRequirement,
    DecisionInvariantError,
    DecisionReason,
    ExecutiveDecision,
    ExecutiveDecisionType,
    ExecutiveRequest,
    ExpectedResultCategory,
    FailurePolicy,
    InvalidCapabilityDefinitionError,
    InvalidCapabilityParametersError,
    InvalidRequestError,
    MAX_CONTEXT_REQUIREMENTS,
    MAX_PLAN_STEPS,
    ParameterDefinition,
    ParameterType,
    Plan,
    PlanInvariantError,
    PlanStep,
    RequestType,
)
from ayyo_executive.json_value import MAX_JSON_DEPTH, MAX_JSON_NODES
from ayyo_personal_context import (
    ContextDomain,
    ContextSnapshotVersion,
    ContextState,
)


def invocation(
    step_id: str = "step-1",
    *,
    capability_id: str = "test.inspect",
    parameters=None,
    dependencies=(),
):
    return CapabilityInvocation(
        step_id=step_id,
        capability_id=capability_id,
        parameters={} if parameters is None else parameters,
        dependencies=dependencies,
    )


def request(*, invocations=None, **overrides):
    arguments = {
        "request_id": "request-1",
        "objective": "Inspect structured test data",
        "request_type": RequestType.INFORMATION,
        "invocations": (invocation(),) if invocations is None else invocations,
    }
    arguments.update(overrides)
    return ExecutiveRequest(**arguments)


def definition(
    capability_id: str = "test.inspect",
    *,
    availability=CapabilityAvailability.AVAILABLE_FOR_PROPOSAL,
    parameters=(),
    **overrides,
):
    arguments = {
        "capability_id": capability_id,
        "description": "Test-only inert inspection contract",
        "availability": availability,
        "parameters": parameters,
        "expected_result": ExpectedResultCategory.INFORMATION,
        "failure_policy": FailurePolicy.STOP_PLAN,
    }
    arguments.update(overrides)
    return CapabilityDefinition(**arguments)


def plan_step(step_id="step-1", *, dependencies=()):
    return PlanStep(
        step_id=step_id,
        capability_id="test.inspect",
        parameters={},
        dependencies=dependencies,
        preconditions=(),
        required_context=(),
        required_approvals=(),
        constraints=(),
        expected_result=ExpectedResultCategory.INFORMATION,
        failure_policy=FailurePolicy.STOP_PLAN,
    )


class RequestModelTest(unittest.TestCase):
    def test_decision_vocabulary_contains_no_execute_or_safe_outcome(self) -> None:
        self.assertEqual(
            {"propose", "request_information", "request_approval", "defer", "reject"},
            {value.value for value in ExecutiveDecisionType},
        )

    def test_nested_json_is_defensively_copied_at_input_and_output(self) -> None:
        parameters = {"nested": {"items": ["first"]}}
        metadata = {"labels": ["initial"]}
        constraint_parameters = {"limit": {"values": [1]}}
        item = invocation(parameters=parameters)
        structured_request = request(
            invocations=(item,),
            metadata=metadata,
            constraints=(
                Constraint("bounded", "Keep values bounded", constraint_parameters),
            ),
        )

        parameters["nested"]["items"].append("caller mutation")
        metadata["labels"].append("caller mutation")
        constraint_parameters["limit"]["values"].append(2)
        returned_parameters = item.parameters
        returned_parameters["nested"]["items"].append("output mutation")
        returned_metadata = structured_request.metadata
        returned_metadata["labels"].append("output mutation")

        self.assertEqual({"nested": {"items": ["first"]}}, item.parameters)
        self.assertEqual({"labels": ["initial"]}, structured_request.metadata)
        self.assertEqual(
            {"limit": {"values": [1]}},
            structured_request.constraints[0].parameters,
        )

    def test_equivalent_unicode_and_dictionary_order_have_same_fingerprint(self) -> None:
        left = request(
            metadata={"z": "ಕಾಫಿ ☕", "a": {"b": 2, "a": 1}},
            invocations=(invocation(parameters={"é": "Café", "a": 1}),),
        )
        right = request(
            metadata={"a": {"a": 1, "b": 2}, "z": "ಕಾಫಿ ☕"},
            invocations=(invocation(parameters={"a": 1, "é": "Café"}),),
        )
        self.assertEqual(left.fingerprint, right.fingerprint)

    def test_non_json_values_non_string_keys_and_non_finite_numbers_fail(self) -> None:
        invalid_values = (
            {"value": object()},
            {1: "not a string key"},
            {"value": float("inf")},
            {"value": ("tuple",)},
            {"value": lambda: None},
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(InvalidRequestError):
                invocation(parameters=value)

    def test_invalid_unicode_and_oversized_integers_fail_as_typed_input(self) -> None:
        with self.assertRaisesRegex(InvalidRequestError, "invalid Unicode"):
            request(objective="invalid-\ud800")
        with self.assertRaisesRegex(InvalidRequestError, "oversized integer"):
            invocation(parameters={"value": 1 << 13_001})

    def test_cyclic_caller_structures_fail_without_recursion_error(self) -> None:
        cyclic_list = []
        cyclic_list.append(cyclic_list)
        cyclic_dict = {}
        cyclic_dict["self"] = cyclic_dict
        for value in ({"value": cyclic_list}, cyclic_dict):
            with self.subTest(kind=type(value)), self.assertRaises(InvalidRequestError):
                invocation(parameters=value)

    def test_deep_and_large_json_are_bounded(self) -> None:
        deep = 0
        for _ in range(MAX_JSON_DEPTH + 1):
            deep = [deep]
        with self.assertRaisesRegex(InvalidRequestError, "level limit"):
            invocation(parameters={"value": deep})
        with self.assertRaisesRegex(InvalidRequestError, "node limit"):
            invocation(parameters={"value": [None] * MAX_JSON_NODES})

    def test_request_rejects_empty_and_oversized_invocation_sets(self) -> None:
        with self.assertRaises(InvalidRequestError):
            request(invocations=())
        too_many = tuple(invocation(f"step-{index}") for index in range(MAX_PLAN_STEPS + 1))
        with self.assertRaisesRegex(InvalidRequestError, "cannot exceed"):
            request(invocations=too_many)

    def test_request_rejects_duplicate_missing_cyclic_and_self_dependencies(self) -> None:
        cases = (
            (invocation("same"), invocation("same")),
            (invocation("one", dependencies=("missing",)),),
            (
                invocation("one", dependencies=("two",)),
                invocation("two", dependencies=("one",)),
            ),
        )
        for invocations in cases:
            with self.subTest(invocations=invocations), self.assertRaises(InvalidRequestError):
                request(invocations=invocations)
        with self.assertRaises(InvalidRequestError):
            invocation("self", dependencies=("self",))

    def test_context_is_canonical_unique_disjoint_and_bounded(self) -> None:
        context = ContextRequirement(ContextDomain.PREFERENCE, "drink")
        with self.assertRaises(InvalidRequestError):
            request(required_context=(context, context))
        with self.assertRaises(InvalidRequestError):
            request(required_context=(context,), optional_context=(context,))
        requirements = tuple(
            ContextRequirement(ContextDomain.SEMANTIC, f"key-{index}")
            for index in range(MAX_CONTEXT_REQUIREMENTS + 1)
        )
        with self.assertRaises(InvalidRequestError):
            request(required_context=requirements)


class CapabilityContractTest(unittest.TestCase):
    def test_empty_registry_has_no_fake_capabilities(self) -> None:
        registry = CapabilityRegistry()
        self.assertEqual((), registry.definitions)
        self.assertEqual(
            CapabilityAvailability.UNKNOWN,
            registry.availability("not.registered"),
        )

    def test_availability_distinguishes_unavailable_and_available_for_proposal(self) -> None:
        unavailable = definition(
            "test.future",
            availability=CapabilityAvailability.UNAVAILABLE,
        )
        available = definition("test.inspect")
        registry = CapabilityRegistry((unavailable, available))
        self.assertFalse(unavailable.currently_implemented)
        self.assertTrue(available.currently_implemented)
        self.assertEqual(
            CapabilityAvailability.UNAVAILABLE,
            registry.availability("test.future"),
        )

    def test_unknown_cannot_be_registered_and_duplicate_ids_fail(self) -> None:
        with self.assertRaises(InvalidCapabilityDefinitionError):
            definition(availability=CapabilityAvailability.UNKNOWN)
        with self.assertRaises(InvalidCapabilityDefinitionError):
            CapabilityRegistry((definition(), definition()))

    def test_parameter_contract_rejects_missing_extra_and_wrong_types(self) -> None:
        contract = definition(
            parameters=(
                ParameterDefinition("count", ParameterType.INTEGER),
                ParameterDefinition("enabled", ParameterType.BOOLEAN),
                ParameterDefinition("note", ParameterType.STRING, required=False),
            )
        )
        registry = CapabilityRegistry((contract,))
        registry.validate_parameters(contract, {"count": 1, "enabled": True})
        invalid = (
            {"count": 1},
            {"count": 1, "enabled": True, "extra": 3},
            {"count": "1", "enabled": True},
        )
        for parameters in invalid:
            with self.subTest(parameters=parameters), self.assertRaises(
                InvalidCapabilityParametersError
            ):
                registry.validate_parameters(contract, parameters)
        with self.assertRaises(InvalidCapabilityParametersError):
            registry.validate_parameters(contract, {"count": object(), "enabled": True})
        with self.assertRaises(InvalidCapabilityParametersError):
            registry.validate_parameters(
                contract,
                {1: "invalid key", "count": 1, "enabled": True},
            )

    def test_boolean_and_integer_are_not_interchangeable(self) -> None:
        contract = definition(
            parameters=(
                ParameterDefinition("integer", ParameterType.INTEGER),
                ParameterDefinition("boolean", ParameterType.BOOLEAN),
            )
        )
        registry = CapabilityRegistry((contract,))
        with self.assertRaises(InvalidCapabilityParametersError):
            registry.validate_parameters(contract, {"integer": True, "boolean": False})
        with self.assertRaises(InvalidCapabilityParametersError):
            registry.validate_parameters(contract, {"integer": 1, "boolean": 0})

    def test_relevant_capability_fingerprint_ignores_unrelated_registry_entries(self) -> None:
        relevant = definition()
        first = CapabilityRegistry((relevant,))
        second = CapabilityRegistry((relevant, definition("test.unrelated")))
        self.assertEqual(
            first.fingerprint_for(("test.inspect",)),
            second.fingerprint_for(("test.inspect",)),
        )

    def test_registry_and_definition_are_immutable(self) -> None:
        contract = definition()
        registry = CapabilityRegistry((contract,))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            contract.description = "changed"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            registry._definitions = ()


class PlanAndDecisionInvariantTest(unittest.TestCase):
    def test_plan_topologically_orders_independent_ready_steps_by_id(self) -> None:
        result = Plan(
            (
                plan_step("finish", dependencies=("alpha", "beta")),
                plan_step("beta"),
                plan_step("alpha"),
            )
        )
        self.assertEqual(("alpha", "beta", "finish"), tuple(step.step_id for step in result.steps))

    def test_plan_rejects_duplicate_missing_cycle_self_and_duplicate_dependency(self) -> None:
        invalid_plans = (
            (plan_step("same"), plan_step("same")),
            (plan_step("one", dependencies=("missing",)),),
            (plan_step("one", dependencies=("two",)), plan_step("two", dependencies=("one",))),
        )
        for steps in invalid_plans:
            with self.subTest(steps=steps), self.assertRaises(PlanInvariantError):
                Plan(steps)
        with self.assertRaises(PlanInvariantError):
            plan_step("self", dependencies=("self",))
        with self.assertRaises(PlanInvariantError):
            plan_step("one", dependencies=("two", "two"))

    def test_plan_rejects_hidden_executable_payload(self) -> None:
        with self.assertRaises(PlanInvariantError):
            PlanStep(
                step_id="step",
                capability_id="test.inspect",
                parameters={"callback": lambda: None},
                dependencies=(),
                preconditions=(),
                required_context=(),
                required_approvals=(),
                constraints=(),
                expected_result=ExpectedResultCategory.INFORMATION,
                failure_policy=FailurePolicy.STOP_PLAN,
            )

    def test_decision_constructor_rejects_impossible_type_reason_and_plan_shapes(self) -> None:
        structured_request = request()
        registry = CapabilityRegistry((definition(),))
        base = {
            "request_id": structured_request.request_id,
            "owner_subject": "owner",
            "decision_type": ExecutiveDecisionType.PROPOSE,
            "reason_codes": (DecisionReason.READY_FOR_SAFETY_REVIEW,),
            "explanation": "A proposal for later review.",
            "context_snapshot_version": ContextSnapshotVersion("0" * 64),
            "request_fingerprint": structured_request.fingerprint,
            "capability_contract_fingerprint": registry.fingerprint_for(("test.inspect",)),
            "context_references": (),
            "assumptions": (),
            "required_capabilities": ("test.inspect",),
            "required_approvals": (),
            "constraints": (),
            "proposed_plan": Plan((plan_step(),)),
        }
        ExecutiveDecision(**base)
        invalid = dict(base)
        invalid["reason_codes"] = (DecisionReason.UNKNOWN_CAPABILITY,)
        with self.assertRaises(DecisionInvariantError):
            ExecutiveDecision(**invalid)
        invalid = dict(base)
        invalid["decision_type"] = ExecutiveDecisionType.REJECT
        invalid["reason_codes"] = (DecisionReason.UNKNOWN_CAPABILITY,)
        with self.assertRaises(DecisionInvariantError):
            ExecutiveDecision(**invalid)

    def test_request_information_cannot_carry_a_plan(self) -> None:
        structured_request = request()
        registry = CapabilityRegistry((definition(),))
        reference = ContextReference(
            requirement=ContextRequirement(ContextDomain.PREFERENCE, "drink"),
            required=True,
            state=ContextState.UNKNOWN,
            value_digests=(),
            memory_ids=(),
            conflict_ids=(),
        )
        with self.assertRaises(DecisionInvariantError):
            ExecutiveDecision(
                request_id="request-1",
                owner_subject="owner",
                decision_type=ExecutiveDecisionType.REQUEST_INFORMATION,
                reason_codes=(DecisionReason.MISSING_REQUIRED_CONTEXT,),
                explanation="More information is required.",
                context_snapshot_version=ContextSnapshotVersion("0" * 64),
                request_fingerprint=structured_request.fingerprint,
                capability_contract_fingerprint=registry.fingerprint_for(("test.inspect",)),
                context_references=(reference,),
                assumptions=(),
                required_capabilities=("test.inspect",),
                required_approvals=(),
                constraints=(),
                proposed_plan=Plan((plan_step(),)),
            )

    def test_decision_rejects_duplicate_required_and_optional_context_roles(self) -> None:
        structured_request = request()
        registry = CapabilityRegistry((definition(),))
        requirement = ContextRequirement(ContextDomain.PREFERENCE, "drink")
        references = tuple(
            ContextReference(
                requirement=requirement,
                required=required,
                state=ContextState.UNKNOWN,
                value_digests=(),
                memory_ids=(),
                conflict_ids=(),
            )
            for required in (True, False)
        )
        with self.assertRaises(DecisionInvariantError):
            ExecutiveDecision(
                request_id="request-1",
                owner_subject="owner",
                decision_type=ExecutiveDecisionType.REQUEST_INFORMATION,
                reason_codes=(DecisionReason.MISSING_REQUIRED_CONTEXT,),
                explanation="More information is required.",
                context_snapshot_version=ContextSnapshotVersion("0" * 64),
                request_fingerprint=structured_request.fingerprint,
                capability_contract_fingerprint=registry.fingerprint_for(("test.inspect",)),
                context_references=references,
                assumptions=(),
                required_capabilities=("test.inspect",),
                required_approvals=(),
                constraints=(),
                proposed_plan=None,
            )


if __name__ == "__main__":
    unittest.main()
