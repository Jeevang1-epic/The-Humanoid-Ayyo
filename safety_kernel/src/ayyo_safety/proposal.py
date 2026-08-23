"""Safety-owned snapshots of public Executive proposal contracts."""

from __future__ import annotations

from dataclasses import dataclass
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

from .canonical import JSONValue, canonicalize_json, copy_json
from .errors import (
    InvalidSafetyProposalError,
    SafetyKernelError,
    SafetyPlanInvariantError,
)
from .models import SafetyFingerprint, SafetyFingerprintKind, fingerprint_document


MAX_PROPOSAL_STEPS = 64
MAX_PROPOSAL_ITEMS = 128
_CONTEXT_DOMAINS = {
    "preference",
    "procedural",
    "semantic",
    "social",
    "spatial",
}
_CONTEXT_STATES = {"conflicted", "resolved", "unknown"}


def _text(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or not value.strip()
        or value != value.strip()
        or len(value) > 16_384
    ):
        raise InvalidSafetyProposalError(
            f"{field_name} must be bounded non-empty normalized text"
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise InvalidSafetyProposalError(
            f"{field_name} contains invalid Unicode"
        ) from error
    return value


def _identifier(value: object, field_name: str) -> str:
    text = _text(value, field_name)
    if len(text) > 256 or not text[0].isalnum() or any(
        not (character.isalnum() or character in {"-", "_", "."})
        for character in text
    ):
        raise InvalidSafetyProposalError(f"{field_name} is not a valid identifier")
    return text


def _typed_tuple(
    value: object,
    *,
    item_type: type,
    field_name: str,
) -> tuple:
    if not isinstance(value, tuple) or not all(
        type(item) is item_type for item in value
    ):
        raise InvalidSafetyProposalError(
            f"{field_name} must contain public {item_type.__name__} objects"
        )
    if len(value) > MAX_PROPOSAL_ITEMS:
        raise InvalidSafetyProposalError(f"{field_name} exceeds the item limit")
    return value


def _fingerprint(
    value: object,
    *,
    kind: FingerprintKind,
    field_name: str,
) -> Fingerprint:
    if type(value) is not Fingerprint or value.kind is not kind:
        raise InvalidSafetyProposalError(f"{field_name} is invalid")
    if value.algorithm != "sha256" or value.schema_version != 1:
        raise InvalidSafetyProposalError(f"{field_name} is unsupported")
    if (
        len(value.digest) != 64
        or any(character not in "0123456789abcdef" for character in value.digest)
    ):
        raise InvalidSafetyProposalError(f"{field_name} digest is invalid")
    return value


@dataclass(frozen=True, slots=True)
class ApprovalSnapshot:
    approval_id: str
    description: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.approval_id, self.description)

    def document(self) -> dict[str, JSONValue]:
        return {
            "approval_id": self.approval_id,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class AssumptionSnapshot:
    assumption_id: str
    description: str

    def document(self) -> dict[str, JSONValue]:
        return {
            "assumption_id": self.assumption_id,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ConstraintSnapshot:
    constraint_id: str
    description: str
    canonical_parameters: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (
            self.constraint_id,
            self.description,
            self.canonical_parameters,
        )

    def document(self) -> dict[str, JSONValue]:
        return {
            "constraint_id": self.constraint_id,
            "description": self.description,
            "parameters_canonical_json": self.canonical_parameters,
        }


@dataclass(frozen=True, slots=True)
class ContextRequirementSnapshot:
    domain: str
    predicate: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.domain, self.predicate)

    def document(self) -> dict[str, JSONValue]:
        return {"domain": self.domain, "predicate": self.predicate}


@dataclass(frozen=True, slots=True)
class ContextReferenceSnapshot:
    requirement: ContextRequirementSnapshot
    required: bool
    state: str
    value_digests: tuple[str, ...]
    memory_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]

    @property
    def key(self) -> tuple[int, str, str]:
        return (
            0 if self.required else 1,
            self.requirement.domain,
            self.requirement.predicate,
        )

    def document(self) -> dict[str, JSONValue]:
        return {
            "conflict_ids": list(self.conflict_ids),
            "domain": self.requirement.domain,
            "memory_ids": list(self.memory_ids),
            "predicate": self.requirement.predicate,
            "required": self.required,
            "state": self.state,
            "value_digests": list(self.value_digests),
        }


@dataclass(frozen=True, slots=True)
class PreconditionSnapshot:
    precondition_id: str
    description: str

    def document(self) -> dict[str, JSONValue]:
        return {
            "description": self.description,
            "precondition_id": self.precondition_id,
        }


@dataclass(frozen=True, slots=True)
class PlanStepSnapshot:
    step_id: str
    capability_id: str
    canonical_parameters: str
    dependencies: tuple[str, ...]
    preconditions: tuple[PreconditionSnapshot, ...]
    required_context: tuple[ContextRequirementSnapshot, ...]
    required_approvals: tuple[ApprovalSnapshot, ...]
    constraints: tuple[ConstraintSnapshot, ...]
    expected_result: ExpectedResultCategory
    failure_policy: FailurePolicy

    def document(self) -> dict[str, JSONValue]:
        return {
            "capability_id": self.capability_id,
            "constraints": [item.document() for item in self.constraints],
            "dependencies": list(self.dependencies),
            "expected_result": self.expected_result.value,
            "failure_policy": self.failure_policy.value,
            "parameters_canonical_json": self.canonical_parameters,
            "preconditions": [item.document() for item in self.preconditions],
            "required_approvals": [
                item.document() for item in self.required_approvals
            ],
            "required_context": [
                item.document() for item in self.required_context
            ],
            "step_id": self.step_id,
        }


@dataclass(frozen=True, slots=True)
class SafetyProposalSnapshot:
    source_decision_id: str
    source_request_id: str
    owner_subject: str
    source_decision_fingerprint: Fingerprint
    context_snapshot_version: str
    steps: tuple[PlanStepSnapshot, ...]
    context_references: tuple[ContextReferenceSnapshot, ...]
    assumptions: tuple[AssumptionSnapshot, ...]
    fingerprint: SafetyFingerprint


def _snapshot_approval(value: ApprovalRequirement) -> ApprovalSnapshot:
    return ApprovalSnapshot(
        approval_id=_identifier(value.approval_id, "approval_id"),
        description=_text(value.description, "approval description"),
    )


def _snapshot_assumption(value: Assumption) -> AssumptionSnapshot:
    return AssumptionSnapshot(
        assumption_id=_identifier(value.assumption_id, "assumption_id"),
        description=_text(value.description, "assumption description"),
    )


def _snapshot_constraint(value: Constraint) -> ConstraintSnapshot:
    parameters = copy_json(
        value.parameters,
        field_name="constraint parameters",
        error_type=InvalidSafetyProposalError,
    )
    if not isinstance(parameters, dict):
        raise InvalidSafetyProposalError(
            "constraint parameters must be a JSON object"
        )
    return ConstraintSnapshot(
        constraint_id=_identifier(value.constraint_id, "constraint_id"),
        description=_text(value.description, "constraint description"),
        canonical_parameters=canonicalize_json(
            parameters,
            field_name="constraint parameters",
            error_type=InvalidSafetyProposalError,
        ),
    )


def _snapshot_context_requirement(
    value: ContextRequirement,
) -> ContextRequirementSnapshot:
    domain = getattr(value.domain, "value", None)
    if domain not in _CONTEXT_DOMAINS:
        raise InvalidSafetyProposalError("context domain is invalid")
    return ContextRequirementSnapshot(
        domain=domain,
        predicate=_text(value.predicate, "context predicate"),
    )


def _snapshot_context_reference(
    value: ContextReference,
) -> ContextReferenceSnapshot:
    if type(value.requirement) is not ContextRequirement:
        raise InvalidSafetyProposalError(
            "context reference requirement must be a ContextRequirement"
        )
    if type(value.required) is not bool:
        raise InvalidSafetyProposalError("context required flag must be boolean")
    state = getattr(value.state, "value", None)
    if state not in _CONTEXT_STATES:
        raise InvalidSafetyProposalError("context state is invalid")
    if not isinstance(value.value_digests, tuple) or not all(
        isinstance(item, str)
        and len(item) == 64
        and all(character in "0123456789abcdef" for character in item)
        for item in value.value_digests
    ):
        raise InvalidSafetyProposalError("context value digests are invalid")
    if value.value_digests != tuple(sorted(set(value.value_digests))):
        raise InvalidSafetyProposalError(
            "context value digests must be unique and ordered"
        )
    identifier_sets: list[tuple[str, ...]] = []
    for field_name, identifiers in (
        ("memory IDs", value.memory_ids),
        ("conflict IDs", value.conflict_ids),
    ):
        if not isinstance(identifiers, tuple) or not all(
            type(identifier) is UUID for identifier in identifiers
        ):
            raise InvalidSafetyProposalError(f"context {field_name} are invalid")
        strings = tuple(str(identifier) for identifier in identifiers)
        if strings != tuple(sorted(set(strings))):
            raise InvalidSafetyProposalError(
                f"context {field_name} must be unique and ordered"
            )
        identifier_sets.append(strings)
    memory_ids, conflict_ids = identifier_sets
    if state == "unknown" and (
        value.value_digests or memory_ids or conflict_ids
    ):
        raise InvalidSafetyProposalError("unknown context cannot cite evidence")
    if state == "resolved" and (
        len(value.value_digests) != 1 or not memory_ids or conflict_ids
    ):
        raise InvalidSafetyProposalError(
            "resolved context must cite one value and supporting evidence"
        )
    if state == "conflicted" and (
        len(value.value_digests) < 2
        or len(memory_ids) < 2
        or not conflict_ids
    ):
        raise InvalidSafetyProposalError(
            "conflicted context must cite competing evidence and conflicts"
        )
    return ContextReferenceSnapshot(
        requirement=_snapshot_context_requirement(value.requirement),
        required=value.required,
        state=state,
        value_digests=value.value_digests,
        memory_ids=memory_ids,
        conflict_ids=conflict_ids,
    )


def _unique_ordered(
    values: tuple,
    *,
    key,
    field_name: str,
) -> tuple:
    keys = tuple(key(value) for value in values)
    if len(keys) != len(set(keys)):
        raise InvalidSafetyProposalError(f"{field_name} must be unique")
    return tuple(sorted(values, key=key))


def _snapshot_step(value: PlanStep) -> PlanStepSnapshot:
    step_id = _identifier(value.step_id, "step_id")
    capability_id = _identifier(value.capability_id, "capability_id")
    parameters = copy_json(
        value.parameters,
        field_name="plan step parameters",
        error_type=InvalidSafetyProposalError,
    )
    if not isinstance(parameters, dict):
        raise InvalidSafetyProposalError("plan step parameters must be a JSON object")
    if not isinstance(value.dependencies, tuple) or not all(
        isinstance(item, str) for item in value.dependencies
    ):
        raise SafetyPlanInvariantError("step dependencies must be a tuple of IDs")
    dependencies = tuple(
        _identifier(item, "step dependency") for item in value.dependencies
    )
    if dependencies != tuple(sorted(set(dependencies))):
        raise SafetyPlanInvariantError(
            "step dependencies must be unique and ordered"
        )
    if step_id in dependencies:
        raise SafetyPlanInvariantError("a plan step cannot depend on itself")
    preconditions = tuple(
        PreconditionSnapshot(
            precondition_id=_identifier(
                item.precondition_id,
                "precondition_id",
            ),
            description=_text(item.description, "precondition description"),
        )
        for item in _typed_tuple(
            value.preconditions,
            item_type=Precondition,
            field_name="preconditions",
        )
    )
    preconditions = _unique_ordered(
        preconditions,
        key=lambda item: item.precondition_id,
        field_name="preconditions",
    )
    contexts = tuple(
        _snapshot_context_requirement(item)
        for item in _typed_tuple(
            value.required_context,
            item_type=ContextRequirement,
            field_name="required context",
        )
    )
    contexts = _unique_ordered(
        contexts,
        key=lambda item: item.key,
        field_name="required context",
    )
    approvals = tuple(
        _snapshot_approval(item)
        for item in _typed_tuple(
            value.required_approvals,
            item_type=ApprovalRequirement,
            field_name="required approvals",
        )
    )
    approvals = _unique_ordered(
        approvals,
        key=lambda item: item.approval_id,
        field_name="required approvals",
    )
    constraints = tuple(
        _snapshot_constraint(item)
        for item in _typed_tuple(
            value.constraints,
            item_type=Constraint,
            field_name="constraints",
        )
    )
    constraints = _unique_ordered(
        constraints,
        key=lambda item: item.constraint_id,
        field_name="constraints",
    )
    if type(value.expected_result) is not ExpectedResultCategory:
        raise InvalidSafetyProposalError("expected result category is invalid")
    if type(value.failure_policy) is not FailurePolicy:
        raise InvalidSafetyProposalError("failure policy is invalid")
    return PlanStepSnapshot(
        step_id=step_id,
        capability_id=capability_id,
        canonical_parameters=canonicalize_json(
            parameters,
            field_name="plan step parameters",
            error_type=InvalidSafetyProposalError,
        ),
        dependencies=dependencies,
        preconditions=preconditions,
        required_context=contexts,
        required_approvals=approvals,
        constraints=constraints,
        expected_result=value.expected_result,
        failure_policy=value.failure_policy,
    )


def _topological_steps(
    steps: tuple[PlanStepSnapshot, ...],
) -> tuple[PlanStepSnapshot, ...]:
    by_id = {step.step_id: step for step in steps}
    if len(by_id) != len(steps):
        raise SafetyPlanInvariantError("plan step IDs must be unique")
    missing = {
        dependency
        for step in steps
        for dependency in step.dependencies
        if dependency not in by_id
    }
    if missing:
        raise SafetyPlanInvariantError(
            f"plan references missing dependencies: {sorted(missing)}"
        )
    remaining = {step_id: set(step.dependencies) for step_id, step in by_id.items()}
    ordered: list[PlanStepSnapshot] = []
    while remaining:
        ready = sorted(
            step_id for step_id, dependencies in remaining.items() if not dependencies
        )
        if not ready:
            raise SafetyPlanInvariantError("plan dependency graph contains a cycle")
        for step_id in ready:
            ordered.append(by_id[step_id])
            del remaining[step_id]
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return tuple(ordered)


def snapshot_proposal(proposal: ExecutiveDecision) -> SafetyProposalSnapshot:
    """Copy and independently validate one public Executive proposal."""

    try:
        if type(proposal) is not ExecutiveDecision:
            raise InvalidSafetyProposalError(
                "proposal must be an ExecutiveDecision"
            )
        if type(proposal.decision_type) is not ExecutiveDecisionType or (
            proposal.decision_type not in {
                ExecutiveDecisionType.PROPOSE,
                ExecutiveDecisionType.REQUEST_APPROVAL,
            }
        ):
            raise InvalidSafetyProposalError(
                "Safety Kernel evaluates only proposals with plans"
            )
        expected_reasons = {
            ExecutiveDecisionType.PROPOSE: (DecisionReason.READY_FOR_SAFETY_REVIEW,),
            ExecutiveDecisionType.REQUEST_APPROVAL: (
                DecisionReason.APPROVAL_REQUIRED,
            ),
        }
        _typed_tuple(
            proposal.reason_codes,
            item_type=DecisionReason,
            field_name="decision reasons",
        )
        if proposal.reason_codes != expected_reasons[proposal.decision_type]:
            raise InvalidSafetyProposalError(
                "proposal decision type and reason codes are inconsistent"
            )
        if type(proposal.proposed_plan) is not Plan:
            raise InvalidSafetyProposalError("proposal must contain a public Plan")
        raw_steps = proposal.proposed_plan.steps
        if not isinstance(raw_steps, tuple) or not all(
            type(step) is PlanStep for step in raw_steps
        ):
            raise SafetyPlanInvariantError(
                "plan must contain public PlanStep objects"
            )
        if not raw_steps or len(raw_steps) > MAX_PROPOSAL_STEPS:
            raise SafetyPlanInvariantError(
                "plan must contain between 1 and 64 steps"
            )
        steps = _topological_steps(tuple(_snapshot_step(step) for step in raw_steps))
        context_references = tuple(
            _snapshot_context_reference(reference)
            for reference in _typed_tuple(
                proposal.context_references,
                item_type=ContextReference,
                field_name="context references",
            )
        )
        context_references = _unique_ordered(
            context_references,
            key=lambda item: item.key,
            field_name="context references",
        )
        missing_context = tuple(
            _snapshot_context_requirement(item)
            for item in _typed_tuple(
                proposal.missing_context,
                item_type=ContextRequirement,
                field_name="missing context",
            )
        )
        conflicted_context = tuple(
            _snapshot_context_requirement(item)
            for item in _typed_tuple(
                proposal.conflicted_context,
                item_type=ContextRequirement,
                field_name="conflicted context",
            )
        )
        derived_missing = tuple(
            item.requirement
            for item in context_references
            if item.required and item.state == "unknown"
        )
        derived_conflicted = tuple(
            item.requirement
            for item in context_references
            if item.required and item.state == "conflicted"
        )
        if (
            missing_context != derived_missing
            or conflicted_context != derived_conflicted
        ):
            raise InvalidSafetyProposalError(
                "decision missing/conflicted context fields are inconsistent"
            )
        assumptions = tuple(
            _snapshot_assumption(item)
            for item in _typed_tuple(
                proposal.assumptions,
                item_type=Assumption,
                field_name="assumptions",
            )
        )
        assumptions = _unique_ordered(
            assumptions,
            key=lambda item: item.assumption_id,
            field_name="assumptions",
        )
        decision_approvals = tuple(
            _snapshot_approval(item)
            for item in _typed_tuple(
                proposal.required_approvals,
                item_type=ApprovalRequirement,
                field_name="decision approvals",
            )
        )
        decision_approvals = _unique_ordered(
            decision_approvals,
            key=lambda item: item.approval_id,
            field_name="decision approvals",
        )
        decision_constraints = tuple(
            _snapshot_constraint(item)
            for item in _typed_tuple(
                proposal.constraints,
                item_type=Constraint,
                field_name="decision constraints",
            )
        )
        decision_constraints = _unique_ordered(
            decision_constraints,
            key=lambda item: item.constraint_id,
            field_name="decision constraints",
        )
        if not isinstance(proposal.required_capabilities, tuple) or not all(
            isinstance(item, str) for item in proposal.required_capabilities
        ):
            raise InvalidSafetyProposalError(
                "required capabilities must be a tuple"
            )
        capabilities = tuple(
            _identifier(item, "required capability")
            for item in proposal.required_capabilities
        )
        if capabilities != tuple(sorted(set(capabilities))) or not capabilities:
            raise InvalidSafetyProposalError(
                "required capabilities must be non-empty, unique, and ordered"
            )
        if set(capabilities) != {step.capability_id for step in steps}:
            raise InvalidSafetyProposalError(
                "plan capabilities do not exactly match the decision"
            )
        step_approvals = {item.key for step in steps for item in step.required_approvals}
        if step_approvals != {item.key for item in decision_approvals}:
            raise InvalidSafetyProposalError(
                "plan approvals do not exactly match the decision"
            )
        if (
            proposal.decision_type is ExecutiveDecisionType.PROPOSE
            and decision_approvals
        ) or (
            proposal.decision_type is ExecutiveDecisionType.REQUEST_APPROVAL
            and not decision_approvals
        ):
            raise InvalidSafetyProposalError(
                "decision type and approval requirements are inconsistent"
            )
        step_constraints = {
            item.key for step in steps for item in step.constraints
        }
        if step_constraints != {item.key for item in decision_constraints}:
            raise InvalidSafetyProposalError(
                "plan constraints do not exactly match the decision"
            )
        step_context = {
            item.key for step in steps for item in step.required_context
        }
        required_context = {
            item.requirement.key
            for item in context_references
            if item.required
        }
        if step_context != required_context:
            raise InvalidSafetyProposalError(
                "plan context dependencies do not exactly match required references"
            )
        if any(
            reference.required and reference.state != "resolved"
            for reference in context_references
        ):
            raise InvalidSafetyProposalError(
                "an executable proposal cannot contain unresolved required context"
            )
        decision_fingerprint = _fingerprint(
            proposal.decision_fingerprint,
            kind=FingerprintKind.DECISION,
            field_name="decision fingerprint",
        )
        _fingerprint(
            proposal.request_fingerprint,
            kind=FingerprintKind.REQUEST,
            field_name="request fingerprint",
        )
        _fingerprint(
            proposal.capability_contract_fingerprint,
            kind=FingerprintKind.CAPABILITY_CONTRACT,
            field_name="capability contract fingerprint",
        )
        _fingerprint(
            proposal.relevant_context_fingerprint,
            kind=FingerprintKind.RELEVANT_CONTEXT,
            field_name="relevant context fingerprint",
        )
        source_decision_id = _text(proposal.decision_id, "decision_id")
        if source_decision_id != f"decision-{decision_fingerprint.digest}":
            raise InvalidSafetyProposalError(
                "decision ID does not match its declared fingerprint"
            )
        source_request_id = _text(proposal.request_id, "request_id")
        owner_subject = _text(proposal.owner_subject, "owner_subject")
        _text(proposal.explanation, "decision explanation")
        snapshot_version = proposal.context_snapshot_version
        snapshot_digest = getattr(snapshot_version, "digest", None)
        if (
            getattr(snapshot_version, "algorithm", None) != "sha256"
            or getattr(snapshot_version, "schema_version", None) != 1
            or not isinstance(snapshot_digest, str)
            or len(snapshot_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in snapshot_digest
            )
        ):
            raise InvalidSafetyProposalError(
                "context snapshot version is invalid"
            )
        context_snapshot_version = f"sha256:{snapshot_digest}"
        document: dict[str, JSONValue] = {
            "assumptions": [item.document() for item in assumptions],
            "capability_contract_fingerprint": str(
                proposal.capability_contract_fingerprint
            ),
            "context_references": [
                item.document() for item in context_references
            ],
            "context_snapshot_version": context_snapshot_version,
            "decision_type": proposal.decision_type.value,
            "owner_subject": owner_subject,
            "request_fingerprint": str(proposal.request_fingerprint),
            "schema": "ayyo.safety.proposal.v1",
            "source_decision_fingerprint": str(decision_fingerprint),
            "source_decision_id": source_decision_id,
            "source_request_id": source_request_id,
            "steps": [step.document() for step in steps],
        }
        proposal_fingerprint = fingerprint_document(
            SafetyFingerprintKind.PROPOSAL,
            document,
        )
        return SafetyProposalSnapshot(
            source_decision_id=source_decision_id,
            source_request_id=source_request_id,
            owner_subject=owner_subject,
            source_decision_fingerprint=decision_fingerprint,
            context_snapshot_version=context_snapshot_version,
            steps=steps,
            context_references=context_references,
            assumptions=assumptions,
            fingerprint=proposal_fingerprint,
        )
    except SafetyKernelError:
        raise
    except Exception as error:
        raise InvalidSafetyProposalError(
            "proposal could not be safely inspected"
        ) from error
