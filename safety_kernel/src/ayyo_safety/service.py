"""Deterministic fail-closed evaluation of inert Executive proposals."""

from __future__ import annotations

from dataclasses import dataclass

from ayyo_executive import ExecutiveDecision, ExpectedResultCategory

from .errors import InvalidSafetyPolicyError, SafetyDecisionInvariantError
from .models import (
    ApprovalClass,
    ApprovalSource,
    HazardClass,
    SafetyApprovalRequirement,
    SafetyDecision,
    SafetyDisposition,
    SafetyPrerequisiteKind,
    SafetyReason,
    SafetyRevalidationReason,
    SafetyRevalidationResult,
    SafetyRevalidationStatus,
    SafetyStepDecision,
    UnresolvedSafetyPrerequisite,
)
from .policy import SafetyPolicy
from .proposal import (
    AssumptionSnapshot,
    PlanStepSnapshot,
    snapshot_proposal,
)


_DISPOSITION_RANK = {
    SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM: 0,
    SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED: 1,
    SafetyDisposition.DEFERRED: 2,
    SafetyDisposition.BLOCKED: 3,
}

_EXPECTED_RESULTS = {
    HazardClass.INFORMATIONAL_READ_ONLY: {
        ExpectedResultCategory.INFORMATION,
    },
    HazardClass.INTERNAL_NON_ACTUATING: {
        ExpectedResultCategory.INFORMATION,
        ExpectedResultCategory.PROPOSED_STATE_CHANGE,
    },
    HazardClass.EXTERNAL_DIGITAL_EFFECT: {
        ExpectedResultCategory.PROPOSED_COMMUNICATION,
        ExpectedResultCategory.PROPOSED_STATE_CHANGE,
    },
    HazardClass.PHYSICAL_MOVEMENT: {
        ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
    },
    HazardClass.PHYSICAL_CONTACT: {
        ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
    },
    HazardClass.PRIVILEGED_HIGH_IMPACT: set(ExpectedResultCategory),
    HazardClass.EMERGENCY_SAFETY_CRITICAL: set(ExpectedResultCategory),
    HazardClass.UNCLASSIFIED: set(),
}


def _stronger(
    left: SafetyDisposition,
    right: SafetyDisposition,
) -> SafetyDisposition:
    return max((left, right), key=_DISPOSITION_RANK.get)


def _ordered_reasons(values: set[SafetyReason]) -> tuple[SafetyReason, ...]:
    return tuple(reason for reason in SafetyReason if reason in values)


@dataclass(frozen=True, slots=True)
class SafetyKernel:
    """Pure policy evaluator. This type intentionally exposes no execution API."""

    policy: SafetyPolicy

    def __post_init__(self) -> None:
        if type(self.policy) is not SafetyPolicy:
            raise InvalidSafetyPolicyError(
                "SafetyKernel requires an immutable SafetyPolicy"
            )

    def evaluate(self, proposal: ExecutiveDecision) -> SafetyDecision:
        """Classify a proposal for downstream consideration without executing it."""

        snapshot = snapshot_proposal(proposal)
        step_decisions = tuple(
            self._evaluate_step(
                step,
                assumptions=(snapshot.assumptions if index == 0 else ()),
            )
            for index, step in enumerate(snapshot.steps)
        )
        return SafetyDecision(
            source_decision_id=snapshot.source_decision_id,
            source_request_id=snapshot.source_request_id,
            owner_subject=snapshot.owner_subject,
            source_decision_fingerprint=snapshot.source_decision_fingerprint,
            policy_version=self.policy.version,
            policy_fingerprint=self.policy.fingerprint,
            proposal_fingerprint=snapshot.fingerprint,
            step_decisions=step_decisions,
        )

    def revalidate(
        self,
        decision: SafetyDecision,
        proposal: ExecutiveDecision,
    ) -> SafetyRevalidationResult:
        """Compare immutable provenance; never refresh or authorize a decision."""

        if type(decision) is not SafetyDecision:
            raise SafetyDecisionInvariantError(
                "revalidation requires a SafetyDecision"
            )
        current = snapshot_proposal(proposal)
        reasons: set[SafetyRevalidationReason] = set()
        if decision.proposal_fingerprint != current.fingerprint:
            reasons.add(SafetyRevalidationReason.PROPOSAL_CHANGED)
        if decision.policy_fingerprint != self.policy.fingerprint:
            reasons.add(SafetyRevalidationReason.POLICY_CHANGED)
        ordered_reasons = tuple(
            reason for reason in SafetyRevalidationReason if reason in reasons
        )
        return SafetyRevalidationResult(
            decision_id=decision.decision_id,
            status=(
                SafetyRevalidationStatus.CURRENT
                if not ordered_reasons
                else SafetyRevalidationStatus.STALE
            ),
            reasons=ordered_reasons,
            prior_proposal_fingerprint=decision.proposal_fingerprint,
            current_proposal_fingerprint=current.fingerprint,
            prior_policy_fingerprint=decision.policy_fingerprint,
            current_policy_fingerprint=self.policy.fingerprint,
        )

    def _evaluate_step(
        self,
        step: PlanStepSnapshot,
        *,
        assumptions: tuple[AssumptionSnapshot, ...],
    ) -> SafetyStepDecision:
        capability_rule = self.policy.capability_rule(step.capability_id)
        hazard_class = (
            HazardClass.UNCLASSIFIED
            if capability_rule is None
            else capability_rule.hazard_class
        )
        hazard_rule = self.policy.hazard_rule(hazard_class)
        disposition = hazard_rule.disposition
        reasons = {hazard_rule.reason}
        policy_rules = {hazard_rule.rule_id}
        approvals: list[SafetyApprovalRequirement] = []
        prerequisites: list[UnresolvedSafetyPrerequisite] = []

        if capability_rule is not None:
            policy_rules.add(capability_rule.rule_id)
            precondition_ids = {
                item.precondition_id for item in step.preconditions
            }
            constraint_ids = {item.constraint_id for item in step.constraints}
            for precondition_id in capability_rule.required_precondition_ids:
                if precondition_id not in precondition_ids:
                    reasons.add(SafetyReason.REQUIRED_SAFETY_METADATA_MISSING)
                    disposition = SafetyDisposition.BLOCKED
                    prerequisites.append(
                        UnresolvedSafetyPrerequisite(
                            kind=SafetyPrerequisiteKind.REQUIRED_PRECONDITION,
                            prerequisite_id=precondition_id,
                            description=(
                                "The capability safety rule requires this explicit "
                                "plan precondition."
                            ),
                            affected_step_id=step.step_id,
                        )
                    )
            for constraint_id in capability_rule.required_constraint_ids:
                if constraint_id not in constraint_ids:
                    reasons.add(SafetyReason.REQUIRED_SAFETY_METADATA_MISSING)
                    disposition = SafetyDisposition.BLOCKED
                    prerequisites.append(
                        UnresolvedSafetyPrerequisite(
                            kind=SafetyPrerequisiteKind.REQUIRED_CONSTRAINT,
                            prerequisite_id=constraint_id,
                            description=(
                                "The capability safety rule requires this explicit "
                                "plan constraint."
                            ),
                            affected_step_id=step.step_id,
                        )
                    )

        if step.expected_result not in _EXPECTED_RESULTS[hazard_class]:
            reasons.add(SafetyReason.CAPABILITY_DECLARATION_CONFLICT)
            disposition = SafetyDisposition.BLOCKED

        if hazard_rule.approval_class is not None:
            approval_id = f"policy.{hazard_rule.approval_class.value}"
            approvals.append(
                SafetyApprovalRequirement(
                    approval_class=hazard_rule.approval_class,
                    source=ApprovalSource.SAFETY_POLICY,
                    requirement_id=approval_id,
                    description=(
                        "External approval is required by the immutable safety "
                        f"policy for {hazard_class.value}."
                    ),
                    affected_step_id=step.step_id,
                )
            )

        for approval in step.required_approvals:
            approvals.append(
                SafetyApprovalRequirement(
                    approval_class=ApprovalClass.EXECUTIVE_DECLARED,
                    source=ApprovalSource.EXECUTIVE,
                    requirement_id=approval.approval_id,
                    description=approval.description,
                    affected_step_id=step.step_id,
                )
            )
            reasons.add(SafetyReason.EXECUTIVE_APPROVAL_UNVERIFIED)

        for prerequisite in hazard_rule.prerequisites:
            prerequisites.append(
                UnresolvedSafetyPrerequisite(
                    kind=prerequisite.kind,
                    prerequisite_id=prerequisite.prerequisite_id,
                    description=prerequisite.description,
                    affected_step_id=step.step_id,
                )
            )

        for assumption in assumptions:
            prerequisites.append(
                UnresolvedSafetyPrerequisite(
                    kind=SafetyPrerequisiteKind.ASSUMPTION_VERIFICATION,
                    prerequisite_id=assumption.assumption_id,
                    description=assumption.description,
                    affected_step_id=step.step_id,
                )
            )
            reasons.add(SafetyReason.UNVERIFIED_ASSUMPTION)

        if disposition is not SafetyDisposition.BLOCKED:
            if prerequisites:
                disposition = _stronger(disposition, SafetyDisposition.DEFERRED)
            elif approvals:
                disposition = _stronger(
                    disposition,
                    SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
                )

        return SafetyStepDecision(
            step_id=step.step_id,
            capability_id=step.capability_id,
            hazard_class=hazard_class,
            disposition=disposition,
            reason_codes=_ordered_reasons(reasons),
            triggering_policy_rules=tuple(sorted(policy_rules)),
            required_approvals=tuple(approvals),
            unresolved_prerequisites=tuple(prerequisites),
        )
