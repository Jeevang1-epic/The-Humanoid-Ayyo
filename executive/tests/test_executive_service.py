import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ayyo_executive import (
    ApprovalRequirement,
    Assumption,
    CapabilityAvailability,
    CapabilityDefinition,
    CapabilityInvocation,
    CapabilityRegistry,
    Constraint,
    ContextRequirement,
    DecisionInvariantError,
    DecisionReason,
    ExecutiveDecisionType,
    ExecutiveRequest,
    ExecutiveService,
    ExpectedResultCategory,
    FailurePolicy,
    InvalidCapabilityParametersError,
    MissingContextPolicy,
    ParameterDefinition,
    ParameterType,
    PlanInvariantError,
    Precondition,
    RequestType,
    RevalidationReason,
    RevalidationStatus,
)
from ayyo_memory import (
    MemoryService,
    MemoryType,
    Provenance,
    ProvenanceType,
    SQLiteMemoryStore,
    StoreClosedError,
)
from ayyo_personal_context import ContextDomain, ContextState, PersonalContextService


OBSERVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class IncrementingClock:
    def __init__(self) -> None:
        self._next = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self._next
        self._next += timedelta(microseconds=1)
        return current


def provenance(source_id="owner.voice"):
    return Provenance(
        ProvenanceType.EXPLICIT_OWNER_STATEMENT,
        source_id,
        {"evidence": "test fixture"},
    )


DRINK_CONTEXT = ContextRequirement(ContextDomain.PREFERENCE, "preferred_drink")


def capability(
    capability_id="test.inspect",
    *,
    availability=CapabilityAvailability.AVAILABLE_FOR_PROPOSAL,
    parameters=(),
    required_context=(),
    required_approvals=(),
    assumptions=(),
    constraints=(),
    preconditions=(),
    expected_result=ExpectedResultCategory.INFORMATION,
):
    return CapabilityDefinition(
        capability_id=capability_id,
        description=f"Inert test contract for {capability_id}",
        availability=availability,
        parameters=parameters,
        required_context=required_context,
        required_approvals=required_approvals,
        assumptions=assumptions,
        constraints=constraints,
        preconditions=preconditions,
        expected_result=expected_result,
        failure_policy=FailurePolicy.STOP_PLAN,
    )


def invocation(
    step_id="step-1",
    *,
    capability_id="test.inspect",
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


class ExecutiveIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = SQLiteMemoryStore(
            Path(self.temporary_directory.name) / "memory.sqlite3"
        )
        self.memory = MemoryService(self.store, clock=IncrementingClock())
        self.context = PersonalContextService(self.memory, owner_subject="owner")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def create_memory(self, **overrides):
        arguments = {
            "memory_type": MemoryType.PREFERENCE,
            "subject": "owner",
            "predicate": "preferred_drink",
            "value": "tea",
            "provenance": provenance(),
            "confidence": 0.9,
            "observed_at": OBSERVED_AT,
            "metadata": {"fixture": "executive"},
        }
        arguments.update(overrides)
        return self.memory.create_memory(**arguments)

    def service(self, *definitions):
        return ExecutiveService(self.context, CapabilityRegistry(tuple(definitions)))

    def test_empty_pct_requests_information_for_required_context(self) -> None:
        executive = self.service(capability(required_context=(DRINK_CONTEXT,)))
        decision = executive.evaluate(request())
        self.assertEqual(
            ExecutiveDecisionType.REQUEST_INFORMATION,
            decision.decision_type,
        )
        self.assertEqual((DecisionReason.MISSING_REQUIRED_CONTEXT,), decision.reason_codes)
        self.assertEqual((DRINK_CONTEXT,), decision.missing_context)
        self.assertEqual((), decision.conflicted_context)
        self.assertIsNone(decision.proposed_plan)
        self.assertEqual(self.context.snapshot_version(), decision.context_snapshot_version)

    def test_unknown_context_can_explicitly_defer(self) -> None:
        executive = self.service(capability(required_context=(DRINK_CONTEXT,)))
        decision = executive.evaluate(
            request(missing_context_policy=MissingContextPolicy.DEFER)
        )
        self.assertEqual(ExecutiveDecisionType.DEFER, decision.decision_type)
        self.assertEqual((DecisionReason.MISSING_REQUIRED_CONTEXT,), decision.reason_codes)

    def test_resolved_context_is_consumed_with_traceable_evidence(self) -> None:
        memory = self.create_memory(value={"drink": "tea", "temperature": "warm"})
        executive = self.service(capability(required_context=(DRINK_CONTEXT,)))
        decision = executive.evaluate(request())
        self.assertEqual(ExecutiveDecisionType.PROPOSE, decision.decision_type)
        reference = decision.context_references[0]
        self.assertEqual(ContextState.RESOLVED, reference.state)
        self.assertEqual((memory.memory_id,), reference.memory_ids)
        self.assertEqual(1, len(reference.value_digests))
        self.assertEqual((DRINK_CONTEXT,), decision.proposed_plan.steps[0].required_context)

    def test_conflicted_context_never_selects_a_winner(self) -> None:
        first = self.create_memory(value="tea", confidence=0.01)
        second = self.create_memory(
            value="coffee",
            confidence=1.0,
            observed_at=OBSERVED_AT + timedelta(days=1),
            provenance=provenance("owner.newer"),
        )
        executive = self.service(capability(required_context=(DRINK_CONTEXT,)))
        decision = executive.evaluate(request())
        self.assertEqual(ExecutiveDecisionType.DEFER, decision.decision_type)
        self.assertIn(DecisionReason.CONFLICTED_REQUIRED_CONTEXT, decision.reason_codes)
        self.assertEqual((DRINK_CONTEXT,), decision.conflicted_context)
        self.assertIsNone(decision.proposed_plan)
        reference = decision.context_references[0]
        self.assertEqual(2, len(reference.value_digests))
        self.assertEqual(
            {first.memory_id, second.memory_id},
            set(reference.memory_ids),
        )
        self.assertTrue(reference.conflict_ids)

    def test_other_owner_context_is_isolated(self) -> None:
        self.create_memory(subject="other-owner", value="coffee")
        executive = self.service(capability(required_context=(DRINK_CONTEXT,)))
        decision = executive.evaluate(request())
        self.assertEqual(ExecutiveDecisionType.REQUEST_INFORMATION, decision.decision_type)
        self.assertEqual(ContextState.UNKNOWN, decision.context_references[0].state)

    def test_unknown_capability_is_rejected_without_a_plan(self) -> None:
        decision = self.service().evaluate(request())
        self.assertEqual(ExecutiveDecisionType.REJECT, decision.decision_type)
        self.assertEqual((DecisionReason.UNKNOWN_CAPABILITY,), decision.reason_codes)
        self.assertIsNone(decision.proposed_plan)

    def test_unknown_capability_preserves_other_fail_closed_blockers(self) -> None:
        structured_request = request(required_context=(DRINK_CONTEXT,))
        decision = self.service().evaluate(structured_request)
        self.assertEqual(ExecutiveDecisionType.REJECT, decision.decision_type)
        self.assertEqual(
            (
                DecisionReason.MISSING_REQUIRED_CONTEXT,
                DecisionReason.UNKNOWN_CAPABILITY,
            ),
            decision.reason_codes,
        )

    def test_supported_but_unimplemented_capability_defers(self) -> None:
        future = capability(
            availability=CapabilityAvailability.UNAVAILABLE,
        )
        decision = self.service(future).evaluate(request())
        self.assertEqual(ExecutiveDecisionType.DEFER, decision.decision_type)
        self.assertIn(DecisionReason.CAPABILITY_UNAVAILABLE, decision.reason_codes)
        self.assertIsNone(decision.proposed_plan)

    def test_malformed_missing_and_extra_parameters_raise_typed_errors(self) -> None:
        contract = capability(
            parameters=(ParameterDefinition("count", ParameterType.INTEGER),)
        )
        executive = self.service(contract)
        invalid = ({}, {"count": "one"}, {"count": 1, "extra": True})
        for parameters in invalid:
            with self.subTest(parameters=parameters), self.assertRaises(
                InvalidCapabilityParametersError
            ):
                executive.evaluate(
                    request(invocations=(invocation(parameters=parameters),))
                )

    def test_approval_requirement_is_metadata_and_never_self_granted(self) -> None:
        approval = ApprovalRequirement(
            "owner-release",
            "A separately authenticated owner must authorize release",
        )
        contract = capability(required_approvals=(approval,))
        decision = self.service(contract).evaluate(request())
        self.assertEqual(ExecutiveDecisionType.REQUEST_APPROVAL, decision.decision_type)
        self.assertEqual((approval,), decision.required_approvals)
        self.assertEqual((approval,), decision.proposed_plan.steps[0].required_approvals)
        self.assertFalse(hasattr(decision, "approved"))
        self.assertFalse(hasattr(approval, "approved"))

    def test_simple_plan_is_declarative_and_defensively_copied(self) -> None:
        contract = capability(
            parameters=(ParameterDefinition("payload", ParameterType.OBJECT),)
        )
        source = {"payload": {"items": [1]}}
        decision = self.service(contract).evaluate(
            request(invocations=(invocation(parameters=source),))
        )
        source["payload"]["items"].append(2)
        returned = decision.proposed_plan.steps[0].parameters
        returned["payload"]["items"].append(3)
        self.assertEqual(
            {"payload": {"items": [1]}},
            decision.proposed_plan.steps[0].parameters,
        )
        self.assertFalse(any(callable(value) for value in decision.proposed_plan.steps))

    def test_multi_step_dependencies_have_deterministic_topological_order(self) -> None:
        inspect = capability("test.inspect")
        combine = capability("test.combine")
        structured_request = request(
            invocations=(
                invocation(
                    "finish",
                    capability_id="test.combine",
                    dependencies=("beta", "alpha"),
                ),
                invocation("beta"),
                invocation("alpha"),
            )
        )
        first = self.service(combine, inspect).evaluate(structured_request)
        second = self.service(inspect, combine).evaluate(structured_request)
        expected = ("alpha", "beta", "finish")
        self.assertEqual(expected, tuple(step.step_id for step in first.proposed_plan.steps))
        self.assertEqual(first.decision_fingerprint, second.decision_fingerprint)
        self.assertEqual(first.decision_id, second.decision_id)

    def test_request_and_capability_metadata_reaches_the_plan(self) -> None:
        request_constraint = Constraint("request-limit", "Request-scoped bound")
        capability_constraint = Constraint("capability-limit", "Capability-scoped bound")
        assumption = Assumption("test-input", "Input was supplied by the test caller")
        precondition = Precondition("input-present", "Structured input is present")
        contract = capability(
            assumptions=(assumption,),
            constraints=(capability_constraint,),
            preconditions=(precondition,),
        )
        decision = self.service(contract).evaluate(
            request(constraints=(request_constraint,))
        )
        self.assertEqual((assumption,), decision.assumptions)
        self.assertEqual(
            (capability_constraint, request_constraint),
            decision.constraints,
        )
        self.assertEqual((precondition,), decision.proposed_plan.steps[0].preconditions)
        self.assertEqual(decision.constraints, decision.proposed_plan.steps[0].constraints)

    def test_aggregate_capability_context_is_bounded(self) -> None:
        first_context = tuple(
            ContextRequirement(ContextDomain.SEMANTIC, f"first-{index}")
            for index in range(65)
        )
        second_context = tuple(
            ContextRequirement(ContextDomain.SEMANTIC, f"second-{index}")
            for index in range(64)
        )
        executive = self.service(
            capability("test.first", required_context=first_context),
            capability("test.second", required_context=second_context),
        )
        structured_request = request(
            invocations=(
                invocation("first", capability_id="test.first"),
                invocation("second", capability_id="test.second"),
            )
        )
        with self.assertRaises(PlanInvariantError):
            executive.evaluate(structured_request)

    def test_equivalent_request_context_and_contract_yield_equivalent_decision(self) -> None:
        self.create_memory()
        contract = capability(required_context=(DRINK_CONTEXT,))
        executive = self.service(contract)
        first = executive.evaluate(request(metadata={"b": 2, "a": 1}))
        second = executive.evaluate(request(metadata={"a": 1, "b": 2}))
        self.assertEqual(first.decision_fingerprint, second.decision_fingerprint)
        self.assertEqual(first.decision_id, second.decision_id)

    def test_revalidation_detects_relevant_context_mutation(self) -> None:
        self.create_memory(value="tea")
        contract = capability(required_context=(DRINK_CONTEXT,))
        executive = self.service(contract)
        structured_request = request()
        decision = executive.evaluate(structured_request)
        self.create_memory(value="coffee", provenance=provenance("owner.second"))
        result = executive.revalidate(decision, structured_request)
        self.assertEqual(RevalidationStatus.STALE, result.status)
        self.assertIn(RevalidationReason.RELEVANT_CONTEXT_CHANGED, result.reasons)
        self.assertNotEqual(result.prior_context_fingerprint, result.current_context_fingerprint)
        with self.assertRaises(DecisionInvariantError):
            dataclasses.replace(result, reasons=())

    def test_unrelated_context_mutation_changes_snapshot_but_not_validity(self) -> None:
        self.create_memory(value="tea")
        contract = capability(required_context=(DRINK_CONTEXT,))
        executive = self.service(contract)
        structured_request = request()
        decision = executive.evaluate(structured_request)
        self.create_memory(
            memory_type=MemoryType.SEMANTIC,
            predicate="unrelated_fact",
            value="unrelated",
        )
        result = executive.revalidate(decision, structured_request)
        self.assertEqual(RevalidationStatus.CURRENT, result.status)
        self.assertEqual((), result.reasons)
        self.assertNotEqual(result.prior_snapshot_version, result.current_snapshot_version)
        self.assertEqual(result.prior_context_fingerprint, result.current_context_fingerprint)

    def test_optional_unknown_context_does_not_block_or_invalidate(self) -> None:
        optional = ContextRequirement(ContextDomain.SEMANTIC, "optional_fact")
        executive = self.service(capability())
        structured_request = request(optional_context=(optional,))
        decision = executive.evaluate(structured_request)
        self.assertEqual(ExecutiveDecisionType.PROPOSE, decision.decision_type)
        self.assertEqual(ContextState.UNKNOWN, decision.context_references[0].state)
        self.create_memory(
            memory_type=MemoryType.SEMANTIC,
            predicate="optional_fact",
            value="now known",
        )
        result = executive.revalidate(decision, structured_request)
        self.assertEqual(RevalidationStatus.CURRENT, result.status)

    def test_revalidation_detects_request_mutation(self) -> None:
        executive = self.service(capability())
        original = request()
        decision = executive.evaluate(original)
        changed = request(objective="A different objective")
        result = executive.revalidate(decision, changed)
        self.assertEqual(RevalidationStatus.STALE, result.status)
        self.assertIn(RevalidationReason.REQUEST_CHANGED, result.reasons)

    def test_revalidation_detects_owner_change_even_with_equivalent_empty_context(self) -> None:
        contract = capability()
        structured_request = request()
        decision = self.service(contract).evaluate(structured_request)
        other_context = PersonalContextService(
            self.memory,
            owner_subject="other-owner",
        )
        result = ExecutiveService(
            other_context,
            CapabilityRegistry((contract,)),
        ).revalidate(decision, structured_request)
        self.assertEqual(RevalidationStatus.STALE, result.status)
        self.assertEqual((RevalidationReason.OWNER_CHANGED,), result.reasons)
        self.assertEqual("owner", result.prior_owner_subject)
        self.assertEqual("other-owner", result.current_owner_subject)

    def test_revalidation_detects_relevant_capability_contract_mutation(self) -> None:
        original_contract = capability()
        structured_request = request()
        decision = self.service(original_contract).evaluate(structured_request)
        changed_contract = CapabilityDefinition(
            capability_id="test.inspect",
            description="A materially changed explicit test contract",
            availability=CapabilityAvailability.AVAILABLE_FOR_PROPOSAL,
            expected_result=ExpectedResultCategory.PROPOSED_STATE_CHANGE,
        )
        result = self.service(changed_contract).revalidate(decision, structured_request)
        self.assertEqual(RevalidationStatus.STALE, result.status)
        self.assertIn(RevalidationReason.CAPABILITY_CONTRACT_CHANGED, result.reasons)

    def test_unrelated_capability_contract_does_not_invalidate(self) -> None:
        relevant = capability()
        structured_request = request()
        decision = self.service(relevant).evaluate(structured_request)
        result = self.service(relevant, capability("test.unrelated")).revalidate(
            decision,
            structured_request,
        )
        self.assertEqual(RevalidationStatus.CURRENT, result.status)

    def test_retracted_context_does_not_reappear(self) -> None:
        memory = self.create_memory()
        self.memory.retract_memory(memory.memory_id, reason="Owner withdrew the fact")
        decision = self.service(
            capability(required_context=(DRINK_CONTEXT,))
        ).evaluate(request())
        self.assertEqual(ExecutiveDecisionType.REQUEST_INFORMATION, decision.decision_type)
        self.assertEqual(ContextState.UNKNOWN, decision.context_references[0].state)

    def test_evaluation_builds_one_snapshot_and_queries_that_snapshot(self) -> None:
        contract = capability(required_context=(DRINK_CONTEXT,))
        executive = self.service(contract)
        with patch.object(
            self.context,
            "build_snapshot",
            wraps=self.context.build_snapshot,
        ) as build_snapshot:
            executive.evaluate(request())
        build_snapshot.assert_called_once_with()

    def test_closed_context_store_propagates_typed_lower_boundary_failure(self) -> None:
        executive = self.service(capability())
        self.store.close()
        with self.assertRaises(StoreClosedError):
            executive.evaluate(request())

    def test_unexpected_dependency_failure_is_not_hidden(self) -> None:
        executive = self.service(capability())
        with patch.object(
            self.context,
            "build_snapshot",
            side_effect=RuntimeError("unexpected dependency failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected dependency failure"):
                executive.evaluate(request())


if __name__ == "__main__":
    unittest.main()
