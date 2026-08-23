from __future__ import annotations

from dataclasses import FrozenInstanceError
import math
import subprocess
import unittest
from unittest.mock import patch
from uuid import UUID

from ayyo_executive import (
    ApprovalRequirement,
    Assumption,
    Constraint,
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
    Precondition,
)
from ayyo_personal_context import (
    ContextDomain,
    ContextSnapshotVersion,
    ContextState,
)
from ayyo_safety import (
    SAFETY_POLICY_VERSION,
    ApprovalClass,
    CapabilitySafetyRule,
    HazardClass,
    InvalidSafetyPolicyError,
    InvalidSafetyProposalError,
    SafetyDecisionInvariantError,
    SafetyDisposition,
    SafetyKernel,
    SafetyPlanInvariantError,
    SafetyPolicy,
    SafetyReason,
    SafetyRevalidationReason,
    SafetyRevalidationStatus,
    SafetyStepDecision,
    StaleSafetyDecisionError,
)


REQUEST_FINGERPRINT = Fingerprint(FingerprintKind.REQUEST, "1" * 64)
CAPABILITY_FINGERPRINT = Fingerprint(
    FingerprintKind.CAPABILITY_CONTRACT,
    "2" * 64,
)
SNAPSHOT_VERSION = ContextSnapshotVersion("3" * 64)


def plan_step(
    step_id: str = "step-1",
    *,
    capability_id: str = "test.inspect",
    parameters: dict | None = None,
    dependencies: tuple[str, ...] = (),
    preconditions: tuple[Precondition, ...] = (),
    required_context: tuple[ContextRequirement, ...] = (),
    required_approvals: tuple[ApprovalRequirement, ...] = (),
    constraints: tuple[Constraint, ...] = (),
    expected_result: ExpectedResultCategory = ExpectedResultCategory.INFORMATION,
) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        capability_id=capability_id,
        parameters={} if parameters is None else parameters,
        dependencies=dependencies,
        preconditions=preconditions,
        required_context=required_context,
        required_approvals=required_approvals,
        constraints=constraints,
        expected_result=expected_result,
        failure_policy=FailurePolicy.STOP_PLAN,
    )


def proposal(
    steps: tuple[PlanStep, ...],
    *,
    context_references: tuple[ContextReference, ...] = (),
    assumptions: tuple[Assumption, ...] = (),
    request_id: str = "request-1",
) -> ExecutiveDecision:
    approvals_by_id = {
        approval.approval_id: approval
        for step in steps
        for approval in step.required_approvals
    }
    constraints_by_id = {
        constraint.constraint_id: constraint
        for step in steps
        for constraint in step.constraints
    }
    approvals = tuple(
        approvals_by_id[key] for key in sorted(approvals_by_id)
    )
    constraints = tuple(
        constraints_by_id[key] for key in sorted(constraints_by_id)
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
        explanation="Evaluate this inert plan for downstream consideration.",
        context_snapshot_version=SNAPSHOT_VERSION,
        request_fingerprint=REQUEST_FINGERPRINT,
        capability_contract_fingerprint=CAPABILITY_FINGERPRINT,
        context_references=context_references,
        assumptions=assumptions,
        required_capabilities=tuple(
            sorted({step.capability_id for step in steps})
        ),
        required_approvals=approvals,
        constraints=constraints,
        proposed_plan=Plan(steps),
    )


def rule(
    capability_id: str,
    hazard_class: HazardClass,
    *,
    required_precondition_ids: tuple[str, ...] = (),
    required_constraint_ids: tuple[str, ...] = (),
) -> CapabilitySafetyRule:
    return CapabilitySafetyRule(
        capability_id=capability_id,
        hazard_class=hazard_class,
        required_precondition_ids=required_precondition_ids,
        required_constraint_ids=required_constraint_ids,
    )


def kernel(*rules: CapabilitySafetyRule) -> SafetyKernel:
    return SafetyKernel(SafetyPolicy(capability_rules=rules))


class SafetyPolicyBehaviorTest(unittest.TestCase):
    def test_all_hazard_classes_have_explicit_conservative_behavior(self) -> None:
        cases = (
            (
                HazardClass.INFORMATIONAL_READ_ONLY,
                ExpectedResultCategory.INFORMATION,
                SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
            ),
            (
                HazardClass.INTERNAL_NON_ACTUATING,
                ExpectedResultCategory.PROPOSED_STATE_CHANGE,
                SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
            ),
            (
                HazardClass.EXTERNAL_DIGITAL_EFFECT,
                ExpectedResultCategory.PROPOSED_COMMUNICATION,
                SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
            ),
            (
                HazardClass.PHYSICAL_MOVEMENT,
                ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
                SafetyDisposition.DEFERRED,
            ),
            (
                HazardClass.PHYSICAL_CONTACT,
                ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
                SafetyDisposition.DEFERRED,
            ),
            (
                HazardClass.PRIVILEGED_HIGH_IMPACT,
                ExpectedResultCategory.PROPOSED_STATE_CHANGE,
                SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
            ),
            (
                HazardClass.EMERGENCY_SAFETY_CRITICAL,
                ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
                SafetyDisposition.BLOCKED,
            ),
        )
        for index, (hazard, expected, disposition) in enumerate(cases):
            capability_id = f"test.capability-{index}"
            with self.subTest(hazard=hazard):
                decision = kernel(rule(capability_id, hazard)).evaluate(
                    proposal(
                        (
                            plan_step(
                                capability_id=capability_id,
                                expected_result=expected,
                            ),
                        )
                    )
                )
                self.assertEqual(disposition, decision.disposition)

    def test_unknown_capability_is_blocked_with_typed_reason(self) -> None:
        decision = kernel().evaluate(proposal((plan_step(),)))
        self.assertEqual(SafetyDisposition.BLOCKED, decision.disposition)
        self.assertEqual(HazardClass.UNCLASSIFIED, decision.step_decisions[0].hazard_class)
        self.assertIn(SafetyReason.UNKNOWN_CAPABILITY_CLASS, decision.reason_codes)
        self.assertTrue(
            all(isinstance(reason, SafetyReason) for reason in decision.reason_codes)
        )

    def test_conflicting_expected_result_blocks(self) -> None:
        decision = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY)
        ).evaluate(
            proposal(
                (
                    plan_step(
                        expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT
                    ),
                )
            )
        )
        self.assertEqual(SafetyDisposition.BLOCKED, decision.disposition)
        self.assertIn(
            SafetyReason.CAPABILITY_DECLARATION_CONFLICT,
            decision.reason_codes,
        )

    def test_required_safety_metadata_must_be_explicit(self) -> None:
        safety = kernel(
            rule(
                "test.inspect",
                HazardClass.INFORMATIONAL_READ_ONLY,
                required_precondition_ids=("robot-stationary",),
                required_constraint_ids=("owner-scope",),
            )
        )
        missing = safety.evaluate(proposal((plan_step(),)))
        self.assertEqual(SafetyDisposition.BLOCKED, missing.disposition)
        self.assertIn(
            SafetyReason.REQUIRED_SAFETY_METADATA_MISSING,
            missing.reason_codes,
        )
        self.assertEqual(2, len(missing.unresolved_prerequisites))

        complete_step = plan_step(
            preconditions=(
                Precondition("robot-stationary", "The robot is stationary."),
            ),
            constraints=(
                Constraint("owner-scope", "Limit processing to the owner."),
            ),
        )
        complete = safety.evaluate(proposal((complete_step,)))
        self.assertEqual(
            SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
            complete.disposition,
        )

    def test_assumptions_defer_until_explicitly_verified_downstream(self) -> None:
        decision = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY)
        ).evaluate(
            proposal(
                (plan_step(),),
                assumptions=(
                    Assumption("input-current", "Input data is current."),
                ),
            )
        )
        self.assertEqual(SafetyDisposition.DEFERRED, decision.disposition)
        self.assertIn(SafetyReason.UNVERIFIED_ASSUMPTION, decision.reason_codes)
        self.assertEqual("input-current", decision.unresolved_prerequisites[0].prerequisite_id)

    def test_maximum_assumptions_and_physical_prerequisite_remain_representable(self) -> None:
        assumptions = tuple(
            Assumption(
                f"assumption-{index:03d}",
                "This maximum-size assumption remains unverified.",
            )
            for index in range(128)
        )
        decision = kernel(
            rule("test.move", HazardClass.PHYSICAL_MOVEMENT)
        ).evaluate(
            proposal(
                (
                    plan_step(
                        capability_id="test.move",
                        expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
                    ),
                ),
                assumptions=assumptions,
            )
        )
        self.assertEqual(SafetyDisposition.DEFERRED, decision.disposition)
        self.assertEqual(129, len(decision.unresolved_prerequisites))

    def test_mixed_risk_plan_aggregates_to_most_restrictive_step(self) -> None:
        steps = (
            plan_step("inspect", capability_id="test.inspect"),
            plan_step(
                "communicate",
                capability_id="test.communicate",
                expected_result=ExpectedResultCategory.PROPOSED_COMMUNICATION,
            ),
            plan_step(
                "emergency",
                capability_id="test.emergency",
                expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
            ),
        )
        decision = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY),
            rule("test.communicate", HazardClass.EXTERNAL_DIGITAL_EFFECT),
            rule("test.emergency", HazardClass.EMERGENCY_SAFETY_CRITICAL),
        ).evaluate(proposal(steps))
        self.assertEqual(SafetyDisposition.BLOCKED, decision.disposition)
        self.assertEqual(
            {
                SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
                SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
                SafetyDisposition.BLOCKED,
            },
            {step.disposition for step in decision.step_decisions},
        )

    def test_hazard_disposition_cannot_be_weakened_in_public_model(self) -> None:
        with self.assertRaises(SafetyDecisionInvariantError):
            SafetyStepDecision(
                step_id="step-1",
                capability_id="test.emergency",
                hazard_class=HazardClass.EMERGENCY_SAFETY_CRITICAL,
                disposition=SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
                reason_codes=(SafetyReason.EMERGENCY_OPERATION_BLOCKED,),
                triggering_policy_rules=(
                    "hazard.emergency-safety-critical",
                ),
            )


class ApprovalBoundaryTest(unittest.TestCase):
    def test_external_effect_requires_policy_approval(self) -> None:
        decision = kernel(
            rule("test.send", HazardClass.EXTERNAL_DIGITAL_EFFECT)
        ).evaluate(
            proposal(
                (
                    plan_step(
                        capability_id="test.send",
                        expected_result=ExpectedResultCategory.PROPOSED_COMMUNICATION,
                    ),
                )
            )
        )
        self.assertEqual(
            SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
            decision.disposition,
        )
        self.assertEqual(
            ApprovalClass.EXTERNAL_DIGITAL_ACTION,
            decision.required_approvals[0].approval_class,
        )

    def test_executive_approval_is_retained_as_unverified(self) -> None:
        approval = ApprovalRequirement(
            "owner-consent",
            "The owner must approve this proposal externally.",
        )
        decision = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY)
        ).evaluate(
            proposal(
                (
                    plan_step(
                        parameters={"approved": True},
                        required_approvals=(approval,),
                    ),
                )
            )
        )
        self.assertEqual(
            SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
            decision.disposition,
        )
        self.assertIn(
            SafetyReason.EXECUTIVE_APPROVAL_UNVERIFIED,
            decision.reason_codes,
        )
        self.assertEqual("owner-consent", decision.required_approvals[0].requirement_id)

    def test_claimed_approval_boolean_cannot_bypass_physical_policy(self) -> None:
        decision = kernel(
            rule("test.move", HazardClass.PHYSICAL_MOVEMENT)
        ).evaluate(
            proposal(
                (
                    plan_step(
                        capability_id="test.move",
                        parameters={"approved": True, "is_safe": True},
                        expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
                    ),
                )
            )
        )
        self.assertEqual(SafetyDisposition.DEFERRED, decision.disposition)
        self.assertEqual(
            "motion-safety-evaluation",
            decision.unresolved_prerequisites[0].prerequisite_id,
        )


class DeterminismAndImmutabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.safety = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY)
        )

    def test_identical_input_produces_identical_decision(self) -> None:
        executive = proposal((plan_step(parameters={"b": 2, "a": [1]}),))
        first = self.safety.evaluate(executive)
        second = self.safety.evaluate(executive)
        self.assertEqual(first, second)
        self.assertEqual(first.decision_id, second.decision_id)
        self.assertEqual(first.decision_fingerprint, second.decision_fingerprint)

    def test_independent_step_input_order_is_not_semantic(self) -> None:
        first_step = plan_step("a")
        second_step = plan_step("b")
        forward = self.safety.evaluate(proposal((first_step, second_step)))
        reverse = self.safety.evaluate(proposal((second_step, first_step)))
        self.assertEqual(forward, reverse)

    def test_evaluation_does_not_mutate_executive_input(self) -> None:
        parameters = {"items": ["one", {"nested": True}]}
        executive = proposal((plan_step(parameters=parameters),))
        before = executive.proposed_plan.steps[0].parameters
        self.safety.evaluate(executive)
        self.assertEqual(before, executive.proposed_plan.steps[0].parameters)
        self.assertEqual(parameters, executive.proposed_plan.steps[0].parameters)

    def test_caller_mutation_after_plan_construction_does_not_leak(self) -> None:
        parameters = {"items": ["original"]}
        executive = proposal((plan_step(parameters=parameters),))
        initial = self.safety.evaluate(executive)
        parameters["items"].append("mutated")
        returned = executive.proposed_plan.steps[0].parameters
        returned["items"].append("also-mutated")
        self.assertEqual(
            SafetyRevalidationStatus.CURRENT,
            self.safety.revalidate(initial, executive).status,
        )

    def test_policy_and_decisions_are_frozen(self) -> None:
        executive = proposal((plan_step(),))
        decision = self.safety.evaluate(executive)
        with self.assertRaises(FrozenInstanceError):
            self.safety.policy.version = "changed"
        with self.assertRaises(FrozenInstanceError):
            decision.disposition = SafetyDisposition.BLOCKED
        with self.assertRaises(AttributeError):
            self.safety.policy.capability_rules.append("invalid")
        with self.assertRaises(TypeError):
            self.safety.policy._capability_index["test.other"] = rule(
                "test.other",
                HazardClass.INFORMATIONAL_READ_ONLY,
            )

    def test_policy_input_order_is_canonical(self) -> None:
        first = SafetyPolicy(
            capability_rules=(
                rule("test.z", HazardClass.INTERNAL_NON_ACTUATING),
                rule("test.a", HazardClass.INFORMATIONAL_READ_ONLY),
            )
        )
        second = SafetyPolicy(
            capability_rules=(
                rule("test.a", HazardClass.INFORMATIONAL_READ_ONLY),
                rule("test.z", HazardClass.INTERNAL_NON_ACTUATING),
            )
        )
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.capability_rules, second.capability_rules)

    def test_policy_version_is_bound_into_decision_identity(self) -> None:
        executive = proposal((plan_step(),))
        decision = self.safety.evaluate(executive)
        self.assertEqual(SAFETY_POLICY_VERSION, decision.policy_version)
        self.assertEqual(self.safety.policy.fingerprint, decision.policy_fingerprint)
        expanded_policy = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY),
            rule("test.unused", HazardClass.INTERNAL_NON_ACTUATING),
        )
        expanded_decision = expanded_policy.evaluate(executive)
        self.assertNotEqual(decision.policy_fingerprint, expanded_decision.policy_fingerprint)
        self.assertNotEqual(decision.decision_fingerprint, expanded_decision.decision_fingerprint)

    def test_json_scalar_types_and_unicode_remain_distinct(self) -> None:
        values = (
            True,
            1,
            1.0,
            "é",
            "e\u0301",
            " spaced ",
            "spaced",
        )
        fingerprints = {
            self.safety.evaluate(
                proposal((plan_step(parameters={"value": value}),))
            ).proposal_fingerprint
            for value in values
        }
        self.assertEqual(len(values), len(fingerprints))

    def test_nested_json_and_unicode_are_deterministic(self) -> None:
        parameters = {
            "message": "安全 🤖",
            "nested": [{"β": [1, 2.5, False, None]}],
        }
        first = self.safety.evaluate(proposal((plan_step(parameters=parameters),)))
        reordered = {
            "nested": [{"β": [1, 2.5, False, None]}],
            "message": "安全 🤖",
        }
        second = self.safety.evaluate(proposal((plan_step(parameters=reordered),)))
        self.assertEqual(first, second)


class StalenessProtectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.safety = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY),
            rule("test.second", HazardClass.INTERNAL_NON_ACTUATING),
        )

    def test_post_evaluation_parameter_tampering_is_stale(self) -> None:
        executive = proposal((plan_step(parameters={"value": "before"}),))
        decision = self.safety.evaluate(executive)
        object.__setattr__(
            executive.proposed_plan.steps[0],
            "_parameters",
            {"value": "after"},
        )
        result = self.safety.revalidate(decision, executive)
        self.assertEqual(SafetyRevalidationStatus.STALE, result.status)
        self.assertEqual(
            (SafetyRevalidationReason.PROPOSAL_CHANGED,),
            result.reasons,
        )
        with self.assertRaises(StaleSafetyDecisionError):
            result.assert_current()

    def test_pre_evaluation_tampering_breaks_executive_fingerprint_integrity(self) -> None:
        executive = proposal((plan_step(parameters={"value": "before"}),))
        object.__setattr__(
            executive.proposed_plan.steps[0],
            "_parameters",
            {"value": "after"},
        )
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(executive)

        context_fingerprint_tamper = proposal((plan_step(),))
        object.__setattr__(
            context_fingerprint_tamper,
            "relevant_context_fingerprint",
            Fingerprint(FingerprintKind.RELEVANT_CONTEXT, "9" * 64),
        )
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(context_fingerprint_tamper)

    def test_executive_explanation_tampering_is_stale(self) -> None:
        executive = proposal((plan_step(),))
        decision = self.safety.evaluate(executive)
        object.__setattr__(
            executive,
            "explanation",
            "This explanation was changed after safety evaluation.",
        )
        self.assertEqual(
            SafetyRevalidationStatus.STALE,
            self.safety.revalidate(decision, executive).status,
        )

    def test_dependency_change_is_stale_even_when_graph_remains_valid(self) -> None:
        steps = (
            plan_step("a"),
            plan_step(
                "b",
                capability_id="test.second",
                dependencies=("a",),
                expected_result=ExpectedResultCategory.PROPOSED_STATE_CHANGE,
            ),
        )
        executive = proposal(steps)
        decision = self.safety.evaluate(executive)
        object.__setattr__(executive.proposed_plan.steps[1], "dependencies", ())
        self.assertEqual(
            SafetyRevalidationStatus.STALE,
            self.safety.revalidate(decision, executive).status,
        )

    def test_policy_evolution_marks_prior_decision_stale(self) -> None:
        executive = proposal((plan_step(),))
        decision = self.safety.evaluate(executive)
        changed = kernel(
            rule("test.inspect", HazardClass.INTERNAL_NON_ACTUATING),
            rule("test.second", HazardClass.INTERNAL_NON_ACTUATING),
        )
        result = changed.revalidate(decision, executive)
        self.assertEqual(SafetyRevalidationStatus.STALE, result.status)
        self.assertEqual((SafetyRevalidationReason.POLICY_CHANGED,), result.reasons)

    def test_changed_context_approval_and_constraint_change_identity(self) -> None:
        requirement = ContextRequirement(ContextDomain.SPATIAL, "robot_pose")
        memory_id = UUID("00000000-0000-0000-0000-000000000001")
        reference = ContextReference(
            requirement=requirement,
            required=True,
            state=ContextState.RESOLVED,
            value_digests=("4" * 64,),
            memory_ids=(memory_id,),
            conflict_ids=(),
        )
        constraint = Constraint("scope", "Use only owner data.", {"scope": "owner"})
        approval = ApprovalRequirement("review", "An external review is required.")
        original = proposal(
            (
                plan_step(
                    required_context=(requirement,),
                    required_approvals=(approval,),
                    constraints=(constraint,),
                ),
            ),
            context_references=(reference,),
        )
        prior = self.safety.evaluate(original)

        changed_reference = ContextReference(
            requirement=requirement,
            required=True,
            state=ContextState.RESOLVED,
            value_digests=("5" * 64,),
            memory_ids=(memory_id,),
            conflict_ids=(),
        )
        changed_constraint = Constraint(
            "scope",
            "Use only owner data.",
            {"scope": "owner", "strict": True},
        )
        changed_approval = ApprovalRequirement(
            "review",
            "A newly scoped external review is required.",
        )
        changed = proposal(
            (
                plan_step(
                    required_context=(requirement,),
                    required_approvals=(changed_approval,),
                    constraints=(changed_constraint,),
                ),
            ),
            context_references=(changed_reference,),
        )
        self.assertEqual(
            SafetyRevalidationStatus.STALE,
            self.safety.revalidate(prior, changed).status,
        )


class PlanInvariantAdversarialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.safety = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY)
        )

    def test_duplicate_step_ids_are_rejected_at_safety_boundary(self) -> None:
        executive = proposal((plan_step("one"), plan_step("two")))
        first = executive.proposed_plan.steps[0]
        object.__setattr__(executive.proposed_plan, "steps", (first, first))
        with self.assertRaises(SafetyPlanInvariantError):
            self.safety.evaluate(executive)

    def test_missing_dependency_is_rejected_at_safety_boundary(self) -> None:
        executive = proposal((plan_step(),))
        object.__setattr__(
            executive.proposed_plan.steps[0],
            "dependencies",
            ("absent",),
        )
        with self.assertRaises(SafetyPlanInvariantError):
            self.safety.evaluate(executive)

    def test_dependency_cycle_is_rejected_at_safety_boundary(self) -> None:
        executive = proposal(
            (
                plan_step("one"),
                plan_step("two", dependencies=("one",)),
            )
        )
        object.__setattr__(executive.proposed_plan.steps[0], "dependencies", ("two",))
        with self.assertRaises(SafetyPlanInvariantError):
            self.safety.evaluate(executive)

    def test_empty_and_oversized_plans_are_rejected(self) -> None:
        empty = proposal((plan_step(),))
        object.__setattr__(empty.proposed_plan, "steps", ())
        with self.assertRaises(SafetyPlanInvariantError):
            self.safety.evaluate(empty)

        oversized = proposal((plan_step(),))
        object.__setattr__(
            oversized.proposed_plan,
            "steps",
            tuple(plan_step(f"step-{index}") for index in range(65)),
        )
        with self.assertRaises(SafetyPlanInvariantError):
            self.safety.evaluate(oversized)

    def test_large_valid_plan_is_deterministic(self) -> None:
        steps = tuple(plan_step(f"step-{index:02d}") for index in range(64))
        executive = proposal(tuple(reversed(steps)))
        first = self.safety.evaluate(executive)
        second = self.safety.evaluate(executive)
        self.assertEqual(64, len(first.step_decisions))
        self.assertEqual(first, second)

    def test_large_missing_policy_metadata_produces_a_blocked_decision(self) -> None:
        precondition_ids = tuple(
            f"required-{index:03d}" for index in range(128)
        )
        safety = kernel(
            rule(
                "test.inspect",
                HazardClass.INFORMATIONAL_READ_ONLY,
                required_precondition_ids=precondition_ids,
            )
        )
        executive = proposal(
            tuple(plan_step(f"step-{index:02d}") for index in range(64))
        )
        decision = safety.evaluate(executive)
        self.assertEqual(SafetyDisposition.BLOCKED, decision.disposition)
        self.assertEqual(64 * 128, len(decision.unresolved_prerequisites))

    def test_impossible_global_relationships_are_rejected(self) -> None:
        executive = proposal((plan_step(),))
        object.__setattr__(
            executive,
            "constraints",
            (Constraint("hidden", "A hidden global constraint."),),
        )
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(executive)

        approval = ApprovalRequirement("review", "External review is required.")
        approval_mismatch = proposal(
            (plan_step(required_approvals=(approval,)),)
        )
        object.__setattr__(approval_mismatch, "required_approvals", ())
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(approval_mismatch)

    def test_conflicting_required_and_optional_context_roles_are_rejected(self) -> None:
        requirement = ContextRequirement(ContextDomain.SPATIAL, "robot_pose")
        reference_arguments = {
            "requirement": requirement,
            "state": ContextState.RESOLVED,
            "value_digests": ("4" * 64,),
            "memory_ids": (
                UUID("00000000-0000-0000-0000-000000000001"),
            ),
            "conflict_ids": (),
        }
        required = ContextReference(required=True, **reference_arguments)
        optional = ContextReference(required=False, **reference_arguments)
        executive = proposal(
            (plan_step(required_context=(requirement,)),),
            context_references=(required,),
        )
        object.__setattr__(
            executive,
            "context_references",
            (required, optional),
        )
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(executive)

    def test_malformed_capability_is_rejected_not_classified(self) -> None:
        executive = proposal((plan_step(),))
        object.__setattr__(executive.proposed_plan.steps[0], "capability_id", "")
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(executive)

    def test_non_executive_and_incomplete_executive_inputs_are_rejected(self) -> None:
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(object())
        incomplete = object.__new__(ExecutiveDecision)
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(incomplete)

        requirement = ContextRequirement(ContextDomain.SEMANTIC, "missing_fact")
        reference = ContextReference(
            requirement=requirement,
            required=True,
            state=ContextState.UNKNOWN,
            value_digests=(),
            memory_ids=(),
            conflict_ids=(),
        )
        information_request = ExecutiveDecision(
            request_id="request-information",
            owner_subject="owner",
            decision_type=ExecutiveDecisionType.REQUEST_INFORMATION,
            reason_codes=(DecisionReason.MISSING_REQUIRED_CONTEXT,),
            explanation="More context is required before planning.",
            context_snapshot_version=SNAPSHOT_VERSION,
            request_fingerprint=REQUEST_FINGERPRINT,
            capability_contract_fingerprint=CAPABILITY_FINGERPRINT,
            context_references=(reference,),
            assumptions=(),
            required_capabilities=("test.inspect",),
            required_approvals=(),
            constraints=(),
            proposed_plan=None,
        )
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(information_request)


class StructuredDataAdversarialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.safety = kernel(
            rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY)
        )

    def _tampered_parameters_fail(self, value: object) -> None:
        executive = proposal((plan_step(),))
        object.__setattr__(executive.proposed_plan.steps[0], "_parameters", value)
        with self.assertRaises(InvalidSafetyProposalError):
            self.safety.evaluate(executive)

    def test_cyclic_and_extremely_deep_json_are_rejected(self) -> None:
        cyclic: list = []
        cyclic.append(cyclic)
        self._tampered_parameters_fail({"cycle": cyclic})

        root: list = []
        current = root
        for _ in range(300):
            child: list = []
            current.append(child)
            current = child
        self._tampered_parameters_fail({"deep": root})

    def test_unsupported_objects_and_non_string_keys_are_rejected(self) -> None:
        self._tampered_parameters_fail({"callback": lambda: None})
        self._tampered_parameters_fail({1: "non-string key"})

    def test_non_finite_numbers_are_rejected(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                self._tampered_parameters_fail({"value": value})

    def test_empty_and_long_policy_identifiers_are_rejected(self) -> None:
        for capability_id in ("", " leading", "x" * 257):
            with self.subTest(capability_id=capability_id):
                with self.assertRaises(InvalidSafetyPolicyError):
                    rule(capability_id, HazardClass.INFORMATIONAL_READ_ONLY)

    def test_maximum_executive_capability_identifier_remains_supported(self) -> None:
        capability_id = "x" * 256
        decision = kernel(
            rule(capability_id, HazardClass.INFORMATIONAL_READ_ONLY)
        ).evaluate(
            proposal((plan_step(capability_id=capability_id),))
        )
        self.assertEqual(
            SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
            decision.disposition,
        )
        self.assertIn(
            f"capability.{capability_id}",
            decision.step_decisions[0].triggering_policy_rules,
        )

    def test_unclassified_policy_rule_is_rejected(self) -> None:
        with self.assertRaises(InvalidSafetyPolicyError):
            rule("test.unknown", HazardClass.UNCLASSIFIED)

    def test_duplicate_policy_capabilities_are_rejected(self) -> None:
        duplicate = rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY)
        with self.assertRaises(InvalidSafetyPolicyError):
            SafetyPolicy(capability_rules=(duplicate, duplicate))

    def test_invalid_policy_and_kernel_public_inputs_are_rejected(self) -> None:
        with self.assertRaises(InvalidSafetyPolicyError):
            SafetyPolicy(capability_rules=[])
        with self.assertRaises(InvalidSafetyPolicyError):
            SafetyKernel(policy=object())


class NoExecutionBehaviorTest(unittest.TestCase):
    def test_evaluation_never_invokes_process_or_action_hooks(self) -> None:
        safety = kernel(rule("test.inspect", HazardClass.INFORMATIONAL_READ_ONLY))
        executive = proposal(
            (
                plan_step(
                    parameters={
                        "command": ["robot", "move"],
                        "callback_name": "execute",
                    }
                ),
            )
        )
        with patch.object(subprocess, "run") as process_run:
            decision = safety.evaluate(executive)
        process_run.assert_not_called()
        self.assertEqual(
            SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
            decision.disposition,
        )
        self.assertNotIn("execute", dir(safety))
        self.assertNotIn("actuate", dir(safety))


if __name__ == "__main__":
    unittest.main()
