from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_executive import ApprovalRequirement
from ayyo_executive import ExpectedResultCategory
from ayyo_safety import ApprovalClass, HazardClass
from ayyo_skill_manager import (
    BindingReason,
    BindingStatus,
    SemanticVersion,
    SkillAvailability,
    SkillBindingResult,
)

from ayyo_runtime_bridge import (
    RosEndpointAvailability,
    RuntimeBridge,
    RuntimeEndpointRegistry,
    RuntimeEligibility,
    RuntimeReason,
)

from helpers import endpoint, proposal, runtime_registry, skill, skill_binding


def ineligible_like(result, reason: BindingReason) -> SkillBindingResult:
    return SkillBindingResult(
        status=BindingStatus.INELIGIBLE,
        reasons=(reason,),
        selection=result.selection,
        source_safety_decision_id=result.source_safety_decision_id,
        invocation=None,
    )


class RuntimeEligibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = skill()
        self.binding = skill_binding(self.definition)
        self.bridge = RuntimeBridge(runtime_registry(self.definition))

    def test_eligible_decision_is_deterministic_and_side_effect_free(self) -> None:
        first = self.bridge.evaluate(self.binding)
        second = self.bridge.evaluate(self.binding)
        self.assertEqual(first, second)
        self.assertIs(RuntimeEligibility.ELIGIBLE, first.status)
        self.assertEqual((), first.reasons)
        self.assertIsNotNone(first.request)
        self.assertEqual(
            f"runtime-decision-{first.fingerprint.digest}",
            first.decision_id,
        )
        with self.assertRaises(FrozenInstanceError):
            first.status = RuntimeEligibility.REJECTED

    def test_blocked_deferred_and_stale_are_never_upgraded(self) -> None:
        cases = (
            (
                BindingReason.SAFETY_BLOCKED,
                RuntimeEligibility.BLOCKED,
                RuntimeReason.UPSTREAM_BLOCKED,
            ),
            (
                BindingReason.SAFETY_DEFERRED,
                RuntimeEligibility.DEFERRED,
                RuntimeReason.UPSTREAM_DEFERRED,
            ),
            (
                BindingReason.SAFETY_DECISION_STALE,
                RuntimeEligibility.STALE,
                RuntimeReason.UPSTREAM_STALE,
            ),
        )
        for binding_reason, status, runtime_reason in cases:
            with self.subTest(binding_reason=binding_reason):
                decision = self.bridge.evaluate(
                    ineligible_like(self.binding, binding_reason)
                )
                self.assertIs(status, decision.status)
                self.assertIn(runtime_reason, decision.reasons)
                self.assertIsNone(decision.request)

        blocked_definition = skill(
            safety_classification=HazardClass.EMERGENCY_SAFETY_CRITICAL,
        )
        blocked_binding = skill_binding(blocked_definition)
        blocked = RuntimeBridge(
            RuntimeEndpointRegistry(
                version=SemanticVersion("1.0.0"),
                bindings=(),
            )
        ).evaluate(blocked_binding)
        self.assertIs(RuntimeEligibility.BLOCKED, blocked.status)

        deferred_definition = skill(
            safety_classification=HazardClass.PHYSICAL_MOVEMENT,
            expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
        )
        deferred_binding = skill_binding(
            deferred_definition,
            source_proposal=proposal(
                expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
            ),
        )
        deferred = RuntimeBridge(
            RuntimeEndpointRegistry(
                version=SemanticVersion("1.0.0"),
                bindings=(),
            )
        ).evaluate(deferred_binding)
        self.assertIs(RuntimeEligibility.DEFERRED, deferred.status)

    def test_approval_required_is_preserved_without_a_runtime_request(self) -> None:
        definition = skill(
            required_approval_classes=(ApprovalClass.EXECUTIVE_DECLARED,),
        )
        approval = ApprovalRequirement(
            "owner-confirmation",
            "Owner confirmation remains externally unverified.",
        )
        binding = skill_binding(
            definition,
            source_proposal=proposal(required_approvals=(approval,)),
        )
        decision = RuntimeBridge(runtime_registry(definition)).evaluate(binding)
        self.assertIs(RuntimeEligibility.APPROVAL_REQUIRED, decision.status)
        self.assertEqual(
            (RuntimeReason.UPSTREAM_APPROVAL_REQUIRED,),
            decision.reasons,
        )
        self.assertIsNone(decision.request)

    def test_unknown_and_unavailable_endpoints_fail_closed(self) -> None:
        empty = RuntimeBridge(
            type(self.bridge.registry)(
                version=SemanticVersion("2.0.0"),
                bindings=(),
            )
        )
        rejected = empty.evaluate(self.binding)
        self.assertIs(RuntimeEligibility.REJECTED, rejected.status)
        self.assertEqual((RuntimeReason.ENDPOINT_NOT_REGISTERED,), rejected.reasons)

        unavailable_endpoint = endpoint(
            self.definition,
            availability=RosEndpointAvailability.UNAVAILABLE,
        )
        unavailable = RuntimeBridge(
            runtime_registry(self.definition, contract=unavailable_endpoint)
        ).evaluate(self.binding)
        self.assertIs(RuntimeEligibility.UNAVAILABLE, unavailable.status)
        self.assertEqual((RuntimeReason.ENDPOINT_UNAVAILABLE,), unavailable.reasons)
        self.assertIsNone(unavailable.request)

        unavailable_skill = skill(availability=SkillAvailability.UNAVAILABLE)
        unavailable_binding = skill_binding(unavailable_skill)
        unavailable_from_skill = empty.evaluate(unavailable_binding)
        self.assertIs(RuntimeEligibility.UNAVAILABLE, unavailable_from_skill.status)
        self.assertEqual(
            (RuntimeReason.SKILL_UNAVAILABLE,),
            unavailable_from_skill.reasons,
        )

    def test_changed_endpoint_or_registry_makes_prior_decision_stale(self) -> None:
        prior = self.bridge.evaluate(self.binding)
        changed_endpoint = endpoint(self.definition, endpoint_name="inspect_context_v2")
        changed_bridge = RuntimeBridge(
            runtime_registry(
                self.definition,
                contract=changed_endpoint,
                version="2.0.0",
            )
        )
        stale = changed_bridge.revalidate(prior, self.binding)
        self.assertIs(RuntimeEligibility.STALE, stale.status)
        self.assertIn(RuntimeReason.RUNTIME_REGISTRY_CHANGED, stale.reasons)
        self.assertIn(RuntimeReason.ENDPOINT_CHANGED, stale.reasons)
        self.assertIsNone(stale.request)

    def test_changed_upstream_request_makes_prior_decision_stale(self) -> None:
        prior = self.bridge.evaluate(self.binding)
        changed = skill_binding(
            self.definition,
            source_proposal=proposal(request_id="request-2"),
        )
        stale = self.bridge.revalidate(prior, changed)
        self.assertIs(RuntimeEligibility.STALE, stale.status)
        self.assertIn(RuntimeReason.UPSTREAM_BINDING_CHANGED, stale.reasons)
        self.assertIsNone(stale.request)

    def test_current_decision_revalidates_idempotently(self) -> None:
        prior = self.bridge.evaluate(self.binding)
        self.assertIs(prior, self.bridge.revalidate(prior, self.binding))


if __name__ == "__main__":
    unittest.main()
