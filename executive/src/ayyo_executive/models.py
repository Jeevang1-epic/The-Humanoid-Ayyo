"""Immutable request, plan, decision, and revalidation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Mapping
from uuid import UUID

from ayyo_personal_context import (
    ContextDomain,
    ContextSnapshotVersion,
    ContextState,
)

from .errors import DecisionInvariantError, InvalidRequestError, PlanInvariantError
from .json_value import JSONValue, canonicalize_json, copy_json


EXECUTIVE_SCHEMA_VERSION = 1
MAX_PLAN_STEPS = 64
MAX_CONTEXT_REQUIREMENTS = 128
MAX_REQUEST_ITEMS = 128
MAX_TEXT_LENGTH = 16_384
MAX_IDENTIFIER_LENGTH = 256


class FingerprintKind(StrEnum):
    REQUEST = "request"
    CAPABILITY_CONTRACT = "capability_contract"
    RELEVANT_CONTEXT = "relevant_context"
    DECISION = "decision"


class RequestType(StrEnum):
    TASK = "task"
    INFORMATION = "information"


class MissingContextPolicy(StrEnum):
    REQUEST_INFORMATION = "request_information"
    DEFER = "defer"


class ExecutiveDecisionType(StrEnum):
    PROPOSE = "propose"
    REQUEST_INFORMATION = "request_information"
    REQUEST_APPROVAL = "request_approval"
    DEFER = "defer"
    REJECT = "reject"


class DecisionReason(StrEnum):
    READY_FOR_SAFETY_REVIEW = "ready_for_safety_review"
    MISSING_REQUIRED_CONTEXT = "missing_required_context"
    CONFLICTED_REQUIRED_CONTEXT = "conflicted_required_context"
    APPROVAL_REQUIRED = "approval_required"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    UNKNOWN_CAPABILITY = "unknown_capability"


class ExpectedResultCategory(StrEnum):
    INFORMATION = "information"
    PROPOSED_STATE_CHANGE = "proposed_state_change"
    PROPOSED_COMMUNICATION = "proposed_communication"
    PROPOSED_PHYSICAL_EFFECT = "proposed_physical_effect"


class FailurePolicy(StrEnum):
    STOP_PLAN = "stop_plan"
    DEFER_DEPENDENTS = "defer_dependents"


class RevalidationStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class RevalidationReason(StrEnum):
    REQUEST_CHANGED = "request_changed"
    OWNER_CHANGED = "owner_changed"
    CAPABILITY_CONTRACT_CHANGED = "capability_contract_changed"
    RELEVANT_CONTEXT_CHANGED = "relevant_context_changed"


def _validate_text(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception],
) -> None:
    if not isinstance(value, str) or not value:
        raise error_type(f"{field_name} must be a non-empty string")
    if len(value) > MAX_TEXT_LENGTH:
        raise error_type(f"{field_name} exceeds the text length limit")
    if not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise error_type(f"{field_name} must not have surrounding whitespace")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise error_type(f"{field_name} contains invalid Unicode") from error


def _identifier_key(value: object, *, field_name: str, error_type: type[Exception]) -> str:
    _validate_text(value, field_name=field_name, error_type=error_type)
    assert isinstance(value, str)
    if len(value) > MAX_IDENTIFIER_LENGTH:
        raise error_type(f"{field_name} exceeds the identifier length limit")
    if not value[0].isalnum() or any(
        not (character.isalnum() or character in {"-", "_", "."})
        for character in value
    ):
        raise error_type(
            f"{field_name} must use letters, numbers, '.', '-', or '_'"
        )
    return value


def _context_key(requirement: ContextRequirement) -> tuple[str, str]:
    return (requirement.domain.value, requirement.predicate)


@dataclass(frozen=True, slots=True)
class Fingerprint:
    kind: FingerprintKind
    digest: str
    algorithm: str = "sha256"
    schema_version: int = EXECUTIVE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FingerprintKind):
            raise DecisionInvariantError("fingerprint kind must be a FingerprintKind")
        if self.algorithm != "sha256":
            raise DecisionInvariantError("fingerprint algorithm must be sha256")
        if self.schema_version != EXECUTIVE_SCHEMA_VERSION:
            raise DecisionInvariantError("fingerprint schema version is unsupported")
        if (
            not isinstance(self.digest, str)
            or len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise DecisionInvariantError(
                "fingerprint digest must be lowercase SHA-256 hexadecimal"
            )

    def __str__(self) -> str:
        return f"{self.kind.value}:{self.algorithm}:{self.digest}"


def fingerprint_document(kind: FingerprintKind, document: JSONValue) -> Fingerprint:
    canonical = canonicalize_json(document, field_name=f"{kind.value} fingerprint")
    return Fingerprint(kind=kind, digest=sha256(canonical.encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True)
class ContextRequirement:
    domain: ContextDomain
    predicate: str

    def __post_init__(self) -> None:
        if not isinstance(self.domain, ContextDomain):
            raise InvalidRequestError("context domain must be a ContextDomain")
        _validate_text(
            self.predicate,
            field_name="context predicate",
            error_type=InvalidRequestError,
        )


@dataclass(frozen=True, slots=True)
class ApprovalRequirement:
    approval_id: str
    description: str

    def __post_init__(self) -> None:
        _identifier_key(
            self.approval_id,
            field_name="approval_id",
            error_type=InvalidRequestError,
        )
        _validate_text(
            self.description,
            field_name="approval description",
            error_type=InvalidRequestError,
        )


@dataclass(frozen=True, slots=True)
class Assumption:
    assumption_id: str
    description: str

    def __post_init__(self) -> None:
        _identifier_key(
            self.assumption_id,
            field_name="assumption_id",
            error_type=InvalidRequestError,
        )
        _validate_text(
            self.description,
            field_name="assumption description",
            error_type=InvalidRequestError,
        )


@dataclass(frozen=True, slots=True)
class Precondition:
    precondition_id: str
    description: str

    def __post_init__(self) -> None:
        _identifier_key(
            self.precondition_id,
            field_name="precondition_id",
            error_type=PlanInvariantError,
        )
        _validate_text(
            self.description,
            field_name="precondition description",
            error_type=PlanInvariantError,
        )


@dataclass(frozen=True, slots=True, init=False)
class Constraint:
    constraint_id: str
    description: str
    _parameters: JSONValue = field(repr=False, compare=False)
    _canonical_parameters: str = field(repr=False)

    def __init__(
        self,
        constraint_id: str,
        description: str,
        parameters: Mapping[str, JSONValue] | None = None,
    ) -> None:
        _identifier_key(
            constraint_id,
            field_name="constraint_id",
            error_type=InvalidRequestError,
        )
        _validate_text(
            description,
            field_name="constraint description",
            error_type=InvalidRequestError,
        )
        source = {} if parameters is None else parameters
        if not isinstance(source, Mapping):
            raise InvalidRequestError("constraint parameters must be a mapping")
        copied = copy_json(
            dict(source),
            field_name="constraint parameters",
            error_type=InvalidRequestError,
        )
        canonical = canonicalize_json(
            copied,
            field_name="constraint parameters",
            error_type=InvalidRequestError,
        )
        object.__setattr__(self, "constraint_id", constraint_id)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "_parameters", copied)
        object.__setattr__(self, "_canonical_parameters", canonical)

    @property
    def parameters(self) -> dict[str, JSONValue]:
        copied = copy_json(self._parameters, field_name="constraint parameters")
        assert isinstance(copied, dict)
        return copied


@dataclass(frozen=True, slots=True, init=False)
class CapabilityInvocation:
    step_id: str
    capability_id: str
    dependencies: tuple[str, ...]
    _parameters: JSONValue = field(repr=False, compare=False)
    _canonical_parameters: str = field(repr=False)

    def __init__(
        self,
        *,
        step_id: str,
        capability_id: str,
        parameters: Mapping[str, JSONValue],
        dependencies: tuple[str, ...] = (),
    ) -> None:
        _identifier_key(step_id, field_name="step_id", error_type=InvalidRequestError)
        _identifier_key(
            capability_id,
            field_name="capability_id",
            error_type=InvalidRequestError,
        )
        if not isinstance(parameters, Mapping):
            raise InvalidRequestError("invocation parameters must be a mapping")
        copied = copy_json(
            dict(parameters),
            field_name="invocation parameters",
            error_type=InvalidRequestError,
        )
        canonical = canonicalize_json(
            copied,
            field_name="invocation parameters",
            error_type=InvalidRequestError,
        )
        if not isinstance(dependencies, tuple) or not all(
            isinstance(dependency, str) for dependency in dependencies
        ):
            raise InvalidRequestError("invocation dependencies must be a tuple of IDs")
        normalized_dependencies = tuple(sorted(set(dependencies)))
        if len(normalized_dependencies) != len(dependencies):
            raise InvalidRequestError("invocation dependencies must be unique")
        for dependency in normalized_dependencies:
            _identifier_key(
                dependency,
                field_name="dependency",
                error_type=InvalidRequestError,
            )
        if step_id in normalized_dependencies:
            raise InvalidRequestError("an invocation cannot depend on itself")
        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "capability_id", capability_id)
        object.__setattr__(self, "dependencies", normalized_dependencies)
        object.__setattr__(self, "_parameters", copied)
        object.__setattr__(self, "_canonical_parameters", canonical)

    @property
    def parameters(self) -> dict[str, JSONValue]:
        copied = copy_json(self._parameters, field_name="invocation parameters")
        assert isinstance(copied, dict)
        return copied


def _validate_dependency_graph(
    step_dependencies: Mapping[str, tuple[str, ...]],
    *,
    error_type: type[Exception],
) -> tuple[str, ...]:
    step_ids = set(step_dependencies)
    for step_id, dependencies in step_dependencies.items():
        missing = set(dependencies) - step_ids
        if missing:
            raise error_type(
                f"step {step_id} references missing dependencies: {sorted(missing)}"
            )
        if step_id in dependencies:
            raise error_type(f"step {step_id} cannot depend on itself")

    dependents: dict[str, list[str]] = {step_id: [] for step_id in step_ids}
    indegree = {
        step_id: len(dependencies)
        for step_id, dependencies in step_dependencies.items()
    }
    for step_id, dependencies in step_dependencies.items():
        for dependency in dependencies:
            dependents[dependency].append(step_id)
    ready = sorted(step_id for step_id, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for dependent in sorted(dependents[current]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort()
    if len(ordered) != len(step_ids):
        raise error_type("step dependencies contain a cycle")
    return tuple(ordered)


def _context_document(requirement: ContextRequirement) -> dict[str, JSONValue]:
    return {"domain": requirement.domain.value, "predicate": requirement.predicate}


def _approval_document(requirement: ApprovalRequirement) -> dict[str, JSONValue]:
    return {
        "approval_id": requirement.approval_id,
        "description": requirement.description,
    }


def _assumption_document(assumption: Assumption) -> dict[str, JSONValue]:
    return {
        "assumption_id": assumption.assumption_id,
        "description": assumption.description,
    }


def _constraint_document(constraint: Constraint) -> dict[str, JSONValue]:
    return {
        "constraint_id": constraint.constraint_id,
        "description": constraint.description,
        "parameters": constraint.parameters,
    }


@dataclass(frozen=True, slots=True, init=False)
class ExecutiveRequest:
    request_id: str
    objective: str
    request_type: RequestType
    invocations: tuple[CapabilityInvocation, ...]
    required_context: tuple[ContextRequirement, ...]
    optional_context: tuple[ContextRequirement, ...]
    constraints: tuple[Constraint, ...]
    required_approvals: tuple[ApprovalRequirement, ...]
    assumptions: tuple[Assumption, ...]
    missing_context_policy: MissingContextPolicy
    fingerprint: Fingerprint
    _metadata: JSONValue = field(repr=False, compare=False)
    _canonical_metadata: str = field(repr=False)

    def __init__(
        self,
        *,
        request_id: str,
        objective: str,
        request_type: RequestType,
        invocations: tuple[CapabilityInvocation, ...],
        required_context: tuple[ContextRequirement, ...] = (),
        optional_context: tuple[ContextRequirement, ...] = (),
        constraints: tuple[Constraint, ...] = (),
        required_approvals: tuple[ApprovalRequirement, ...] = (),
        assumptions: tuple[Assumption, ...] = (),
        missing_context_policy: MissingContextPolicy = (
            MissingContextPolicy.REQUEST_INFORMATION
        ),
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> None:
        _validate_text(
            request_id,
            field_name="request_id",
            error_type=InvalidRequestError,
        )
        _validate_text(
            objective,
            field_name="objective",
            error_type=InvalidRequestError,
        )
        if not isinstance(request_type, RequestType):
            raise InvalidRequestError("request_type must be a RequestType")
        if not isinstance(missing_context_policy, MissingContextPolicy):
            raise InvalidRequestError(
                "missing_context_policy must be a MissingContextPolicy"
            )
        if not isinstance(invocations, tuple) or not all(
            isinstance(invocation, CapabilityInvocation)
            for invocation in invocations
        ):
            raise InvalidRequestError(
                "invocations must be a tuple of CapabilityInvocation objects"
            )
        if not invocations:
            raise InvalidRequestError("a request requires at least one invocation")
        if len(invocations) > MAX_PLAN_STEPS:
            raise InvalidRequestError(
                f"a request cannot exceed {MAX_PLAN_STEPS} invocations"
            )
        invocations = tuple(sorted(invocations, key=lambda item: item.step_id))
        if len({item.step_id for item in invocations}) != len(invocations):
            raise InvalidRequestError("invocation step IDs must be unique")
        _validate_dependency_graph(
            {item.step_id: item.dependencies for item in invocations},
            error_type=InvalidRequestError,
        )
        required_context = self._context_tuple(
            required_context,
            field_name="required_context",
        )
        optional_context = self._context_tuple(
            optional_context,
            field_name="optional_context",
        )
        if set(required_context) & set(optional_context):
            raise InvalidRequestError(
                "a context key cannot be both required and optional"
            )
        if len(required_context) + len(optional_context) > MAX_CONTEXT_REQUIREMENTS:
            raise InvalidRequestError(
                f"a request cannot exceed {MAX_CONTEXT_REQUIREMENTS} context keys"
            )
        constraints = self._typed_tuple(
            constraints,
            item_type=Constraint,
            id_attribute="constraint_id",
            field_name="constraints",
        )
        required_approvals = self._typed_tuple(
            required_approvals,
            item_type=ApprovalRequirement,
            id_attribute="approval_id",
            field_name="required_approvals",
        )
        assumptions = self._typed_tuple(
            assumptions,
            item_type=Assumption,
            id_attribute="assumption_id",
            field_name="assumptions",
        )
        metadata_source = {} if metadata is None else metadata
        if not isinstance(metadata_source, Mapping):
            raise InvalidRequestError("request metadata must be a mapping")
        metadata_copy = copy_json(
            dict(metadata_source),
            field_name="request metadata",
            error_type=InvalidRequestError,
        )
        canonical_metadata = canonicalize_json(
            metadata_copy,
            field_name="request metadata",
            error_type=InvalidRequestError,
        )
        document: dict[str, JSONValue] = {
            "assumptions": [_assumption_document(item) for item in assumptions],
            "constraints": [_constraint_document(item) for item in constraints],
            "invocations": [
                {
                    "capability_id": item.capability_id,
                    "dependencies": list(item.dependencies),
                    "parameters": item.parameters,
                    "step_id": item.step_id,
                }
                for item in invocations
            ],
            "metadata": metadata_copy,
            "missing_context_policy": missing_context_policy.value,
            "objective": objective,
            "optional_context": [
                _context_document(item) for item in optional_context
            ],
            "request_id": request_id,
            "request_type": request_type.value,
            "required_approvals": [
                _approval_document(item) for item in required_approvals
            ],
            "required_context": [
                _context_document(item) for item in required_context
            ],
            "schema": "ayyo.executive.request.v1",
        }
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "request_type", request_type)
        object.__setattr__(self, "invocations", invocations)
        object.__setattr__(self, "required_context", required_context)
        object.__setattr__(self, "optional_context", optional_context)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "required_approvals", required_approvals)
        object.__setattr__(self, "assumptions", assumptions)
        object.__setattr__(self, "missing_context_policy", missing_context_policy)
        object.__setattr__(self, "_metadata", metadata_copy)
        object.__setattr__(self, "_canonical_metadata", canonical_metadata)
        object.__setattr__(
            self,
            "fingerprint",
            fingerprint_document(FingerprintKind.REQUEST, document),
        )

    @staticmethod
    def _context_tuple(
        values: tuple[ContextRequirement, ...],
        *,
        field_name: str,
    ) -> tuple[ContextRequirement, ...]:
        if not isinstance(values, tuple) or not all(
            isinstance(value, ContextRequirement) for value in values
        ):
            raise InvalidRequestError(
                f"{field_name} must be a tuple of ContextRequirement objects"
            )
        if len(values) > MAX_CONTEXT_REQUIREMENTS:
            raise InvalidRequestError(
                f"{field_name} cannot exceed {MAX_CONTEXT_REQUIREMENTS} items"
            )
        result = tuple(sorted(values, key=_context_key))
        if len(result) != len(set(result)):
            raise InvalidRequestError(f"{field_name} must be unique")
        return result

    @staticmethod
    def _typed_tuple(
        values: tuple,
        *,
        item_type: type,
        id_attribute: str,
        field_name: str,
    ) -> tuple:
        if not isinstance(values, tuple) or not all(
            isinstance(value, item_type) for value in values
        ):
            raise InvalidRequestError(
                f"{field_name} must contain only {item_type.__name__} objects"
            )
        if len(values) > MAX_REQUEST_ITEMS:
            raise InvalidRequestError(
                f"{field_name} cannot exceed {MAX_REQUEST_ITEMS} items"
            )
        result = tuple(sorted(values, key=lambda item: getattr(item, id_attribute)))
        identifiers = tuple(getattr(item, id_attribute) for item in result)
        if len(identifiers) != len(set(identifiers)):
            raise InvalidRequestError(f"{field_name} identifiers must be unique")
        return result

    @property
    def metadata(self) -> dict[str, JSONValue]:
        copied = copy_json(self._metadata, field_name="request metadata")
        assert isinstance(copied, dict)
        return copied

    @property
    def requested_capabilities(self) -> tuple[str, ...]:
        return tuple(
            sorted({invocation.capability_id for invocation in self.invocations})
        )


@dataclass(frozen=True, slots=True, init=False)
class PlanStep:
    step_id: str
    capability_id: str
    dependencies: tuple[str, ...]
    preconditions: tuple[Precondition, ...]
    required_context: tuple[ContextRequirement, ...]
    required_approvals: tuple[ApprovalRequirement, ...]
    constraints: tuple[Constraint, ...]
    expected_result: ExpectedResultCategory
    failure_policy: FailurePolicy
    _parameters: JSONValue = field(repr=False, compare=False)
    _canonical_parameters: str = field(repr=False)

    def __init__(
        self,
        *,
        step_id: str,
        capability_id: str,
        parameters: Mapping[str, JSONValue],
        dependencies: tuple[str, ...],
        preconditions: tuple[Precondition, ...],
        required_context: tuple[ContextRequirement, ...],
        required_approvals: tuple[ApprovalRequirement, ...],
        constraints: tuple[Constraint, ...],
        expected_result: ExpectedResultCategory,
        failure_policy: FailurePolicy,
    ) -> None:
        _identifier_key(step_id, field_name="step_id", error_type=PlanInvariantError)
        _identifier_key(
            capability_id,
            field_name="capability_id",
            error_type=PlanInvariantError,
        )
        if not isinstance(parameters, Mapping):
            raise PlanInvariantError("plan step parameters must be a mapping")
        copied = copy_json(
            dict(parameters),
            field_name="plan step parameters",
            error_type=PlanInvariantError,
        )
        canonical = canonicalize_json(
            copied,
            field_name="plan step parameters",
            error_type=PlanInvariantError,
        )
        if not isinstance(dependencies, tuple) or not all(
            isinstance(item, str) for item in dependencies
        ):
            raise PlanInvariantError("step dependencies must be a tuple of IDs")
        normalized_dependencies = tuple(sorted(set(dependencies)))
        if len(normalized_dependencies) != len(dependencies):
            raise PlanInvariantError("step dependencies must be unique")
        dependencies = normalized_dependencies
        if step_id in dependencies:
            raise PlanInvariantError("a plan step cannot depend on itself")
        preconditions = self._tuple(
            preconditions,
            item_type=Precondition,
            key=lambda item: item.precondition_id,
            field_name="preconditions",
        )
        required_context = self._tuple(
            required_context,
            item_type=ContextRequirement,
            key=_context_key,
            field_name="required_context",
        )
        required_approvals = self._tuple(
            required_approvals,
            item_type=ApprovalRequirement,
            key=lambda item: item.approval_id,
            field_name="required_approvals",
        )
        constraints = self._tuple(
            constraints,
            item_type=Constraint,
            key=lambda item: item.constraint_id,
            field_name="constraints",
        )
        if not isinstance(expected_result, ExpectedResultCategory):
            raise PlanInvariantError(
                "expected_result must be an ExpectedResultCategory"
            )
        if not isinstance(failure_policy, FailurePolicy):
            raise PlanInvariantError("failure_policy must be a FailurePolicy")
        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "capability_id", capability_id)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "preconditions", preconditions)
        object.__setattr__(self, "required_context", required_context)
        object.__setattr__(self, "required_approvals", required_approvals)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "expected_result", expected_result)
        object.__setattr__(self, "failure_policy", failure_policy)
        object.__setattr__(self, "_parameters", copied)
        object.__setattr__(self, "_canonical_parameters", canonical)

    @staticmethod
    def _tuple(values: tuple, *, item_type: type, key, field_name: str) -> tuple:
        if not isinstance(values, tuple) or not all(
            isinstance(value, item_type) for value in values
        ):
            raise PlanInvariantError(
                f"{field_name} must contain only {item_type.__name__} objects"
            )
        if len(values) > MAX_REQUEST_ITEMS:
            raise PlanInvariantError(
                f"{field_name} cannot exceed {MAX_REQUEST_ITEMS} items"
            )
        result = tuple(sorted(values, key=key))
        keys = tuple(key(item) for item in result)
        if len(keys) != len(set(keys)):
            raise PlanInvariantError(f"{field_name} must be unique")
        return result

    @property
    def parameters(self) -> dict[str, JSONValue]:
        copied = copy_json(self._parameters, field_name="plan step parameters")
        assert isinstance(copied, dict)
        return copied


@dataclass(frozen=True, slots=True, init=False)
class Plan:
    steps: tuple[PlanStep, ...]

    def __init__(self, steps: tuple[PlanStep, ...]) -> None:
        if not isinstance(steps, tuple) or not all(
            isinstance(step, PlanStep) for step in steps
        ):
            raise PlanInvariantError("plan steps must be a tuple of PlanStep objects")
        if not steps:
            raise PlanInvariantError("a proposed plan requires at least one step")
        if len(steps) > MAX_PLAN_STEPS:
            raise PlanInvariantError(f"a plan cannot exceed {MAX_PLAN_STEPS} steps")
        by_id = {step.step_id: step for step in steps}
        if len(by_id) != len(steps):
            raise PlanInvariantError("plan step IDs must be unique")
        order = _validate_dependency_graph(
            {step.step_id: step.dependencies for step in steps},
            error_type=PlanInvariantError,
        )
        object.__setattr__(self, "steps", tuple(by_id[step_id] for step_id in order))


@dataclass(frozen=True, slots=True)
class ContextReference:
    requirement: ContextRequirement
    required: bool
    state: ContextState
    value_digests: tuple[str, ...]
    memory_ids: tuple[UUID, ...]
    conflict_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, ContextRequirement):
            raise DecisionInvariantError(
                "context reference requires a ContextRequirement"
            )
        if not isinstance(self.required, bool):
            raise DecisionInvariantError("context reference required flag is invalid")
        if not isinstance(self.state, ContextState):
            raise DecisionInvariantError("context reference state is invalid")
        if not isinstance(self.value_digests, tuple) or not all(
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
            for value in self.value_digests
        ):
            raise DecisionInvariantError("context value digests are invalid")
        if self.value_digests != tuple(sorted(set(self.value_digests))):
            raise DecisionInvariantError(
                "context value digests must be unique and sorted"
            )
        for field_name, identifiers in (
            ("memory_ids", self.memory_ids),
            ("conflict_ids", self.conflict_ids),
        ):
            if not isinstance(identifiers, tuple) or not all(
                isinstance(identifier, UUID) for identifier in identifiers
            ):
                raise DecisionInvariantError(f"{field_name} must contain UUIDs")
            if identifiers != tuple(sorted(set(identifiers), key=str)):
                raise DecisionInvariantError(f"{field_name} must be unique and sorted")
        if self.state is ContextState.UNKNOWN and (
            self.value_digests or self.memory_ids or self.conflict_ids
        ):
            raise DecisionInvariantError("unknown context cannot cite evidence")
        if self.state is ContextState.RESOLVED and (
            len(self.value_digests) != 1
            or not self.memory_ids
            or self.conflict_ids
        ):
            raise DecisionInvariantError(
                "resolved context requires one value and supporting evidence"
            )
        if self.state is ContextState.CONFLICTED and (
            len(self.value_digests) < 2
            or len(self.memory_ids) < 2
            or not self.conflict_ids
        ):
            raise DecisionInvariantError(
                "conflicted context requires competing values and conflicts"
            )


def _reference_key(reference: ContextReference) -> tuple[int, str, str]:
    return (
        0 if reference.required else 1,
        reference.requirement.domain.value,
        reference.requirement.predicate,
    )


def _reference_document(reference: ContextReference) -> dict[str, JSONValue]:
    return {
        "conflict_ids": [str(value) for value in reference.conflict_ids],
        "domain": reference.requirement.domain.value,
        "memory_ids": [str(value) for value in reference.memory_ids],
        "predicate": reference.requirement.predicate,
        "required": reference.required,
        "state": reference.state.value,
        "value_digests": list(reference.value_digests),
    }


def relevant_context_fingerprint(
    references: tuple[ContextReference, ...],
) -> Fingerprint:
    required_references = tuple(
        sorted((item for item in references if item.required), key=_reference_key)
    )
    return fingerprint_document(
        FingerprintKind.RELEVANT_CONTEXT,
        {
            "references": [
                _reference_document(reference)
                for reference in required_references
            ],
            "schema": "ayyo.executive.relevant-context.v1",
        },
    )


def _step_document(step: PlanStep) -> dict[str, JSONValue]:
    return {
        "capability_id": step.capability_id,
        "constraints": [_constraint_document(item) for item in step.constraints],
        "dependencies": list(step.dependencies),
        "expected_result": step.expected_result.value,
        "failure_policy": step.failure_policy.value,
        "parameters": step.parameters,
        "preconditions": [
            {
                "description": item.description,
                "precondition_id": item.precondition_id,
            }
            for item in step.preconditions
        ],
        "required_approvals": [
            _approval_document(item) for item in step.required_approvals
        ],
        "required_context": [
            _context_document(item) for item in step.required_context
        ],
        "step_id": step.step_id,
    }


@dataclass(frozen=True, slots=True, init=False)
class ExecutiveDecision:
    decision_id: str
    request_id: str
    owner_subject: str
    decision_type: ExecutiveDecisionType
    reason_codes: tuple[DecisionReason, ...]
    explanation: str
    context_snapshot_version: ContextSnapshotVersion
    request_fingerprint: Fingerprint
    capability_contract_fingerprint: Fingerprint
    relevant_context_fingerprint: Fingerprint
    decision_fingerprint: Fingerprint
    context_references: tuple[ContextReference, ...]
    missing_context: tuple[ContextRequirement, ...]
    conflicted_context: tuple[ContextRequirement, ...]
    assumptions: tuple[Assumption, ...]
    required_capabilities: tuple[str, ...]
    required_approvals: tuple[ApprovalRequirement, ...]
    constraints: tuple[Constraint, ...]
    proposed_plan: Plan | None

    def __init__(
        self,
        *,
        request_id: str,
        owner_subject: str,
        decision_type: ExecutiveDecisionType,
        reason_codes: tuple[DecisionReason, ...],
        explanation: str,
        context_snapshot_version: ContextSnapshotVersion,
        request_fingerprint: Fingerprint,
        capability_contract_fingerprint: Fingerprint,
        context_references: tuple[ContextReference, ...],
        assumptions: tuple[Assumption, ...],
        required_capabilities: tuple[str, ...],
        required_approvals: tuple[ApprovalRequirement, ...],
        constraints: tuple[Constraint, ...],
        proposed_plan: Plan | None,
    ) -> None:
        _validate_text(
            request_id,
            field_name="decision request_id",
            error_type=DecisionInvariantError,
        )
        _validate_text(
            owner_subject,
            field_name="decision owner_subject",
            error_type=DecisionInvariantError,
        )
        if not isinstance(decision_type, ExecutiveDecisionType):
            raise DecisionInvariantError(
                "decision_type must be an ExecutiveDecisionType"
            )
        if not isinstance(reason_codes, tuple) or not reason_codes or not all(
            isinstance(reason, DecisionReason) for reason in reason_codes
        ):
            raise DecisionInvariantError(
                "reason_codes must be a non-empty tuple of DecisionReason values"
            )
        reason_rank = {reason: index for index, reason in enumerate(DecisionReason)}
        if reason_codes != tuple(sorted(set(reason_codes), key=reason_rank.get)):
            raise DecisionInvariantError("reason_codes must be unique and ordered")
        _validate_text(
            explanation,
            field_name="decision explanation",
            error_type=DecisionInvariantError,
        )
        if not isinstance(context_snapshot_version, ContextSnapshotVersion):
            raise DecisionInvariantError(
                "context_snapshot_version must be a ContextSnapshotVersion"
            )
        for fingerprint, kind in (
            (request_fingerprint, FingerprintKind.REQUEST),
            (
                capability_contract_fingerprint,
                FingerprintKind.CAPABILITY_CONTRACT,
            ),
        ):
            if not isinstance(fingerprint, Fingerprint) or fingerprint.kind is not kind:
                raise DecisionInvariantError(f"{kind.value} fingerprint is invalid")
        if not isinstance(context_references, tuple) or not all(
            isinstance(reference, ContextReference)
            for reference in context_references
        ):
            raise DecisionInvariantError(
                "context_references must contain ContextReference objects"
            )
        if len(context_references) > MAX_CONTEXT_REQUIREMENTS:
            raise DecisionInvariantError(
                "context references exceed the executive context limit"
            )
        context_references = tuple(sorted(context_references, key=_reference_key))
        reference_keys = tuple(item.requirement for item in context_references)
        if len(reference_keys) != len(set(reference_keys)):
            raise DecisionInvariantError(
                "a context key cannot appear more than once in a decision"
            )
        missing_context = tuple(
            item.requirement
            for item in context_references
            if item.required and item.state is ContextState.UNKNOWN
        )
        conflicted_context = tuple(
            item.requirement
            for item in context_references
            if item.required and item.state is ContextState.CONFLICTED
        )
        assumptions = self._decision_tuple(
            assumptions,
            item_type=Assumption,
            key=lambda item: item.assumption_id,
            field_name="assumptions",
        )
        required_approvals = self._decision_tuple(
            required_approvals,
            item_type=ApprovalRequirement,
            key=lambda item: item.approval_id,
            field_name="required_approvals",
        )
        constraints = self._decision_tuple(
            constraints,
            item_type=Constraint,
            key=lambda item: item.constraint_id,
            field_name="constraints",
        )
        if not isinstance(required_capabilities, tuple) or not all(
            isinstance(value, str) for value in required_capabilities
        ):
            raise DecisionInvariantError("required_capabilities must be a tuple")
        if len(required_capabilities) > MAX_PLAN_STEPS:
            raise DecisionInvariantError(
                "required_capabilities exceed the executive plan limit"
            )
        for capability_id in required_capabilities:
            _identifier_key(
                capability_id,
                field_name="required capability",
                error_type=DecisionInvariantError,
            )
        normalized_capabilities = tuple(sorted(set(required_capabilities)))
        if len(normalized_capabilities) != len(required_capabilities):
            raise DecisionInvariantError("required_capabilities must be unique")
        required_capabilities = normalized_capabilities
        if not required_capabilities:
            raise DecisionInvariantError("a decision requires capabilities")
        self._validate_shape(
            decision_type,
            reason_codes=reason_codes,
            missing_context=missing_context,
            conflicted_context=conflicted_context,
            required_approvals=required_approvals,
            proposed_plan=proposed_plan,
        )
        if proposed_plan is not None:
            plan_capabilities = {step.capability_id for step in proposed_plan.steps}
            if plan_capabilities != set(required_capabilities):
                raise DecisionInvariantError(
                    "proposed plan capabilities do not match the decision"
                )
            plan_context = {
                requirement
                for step in proposed_plan.steps
                for requirement in step.required_context
            }
            required_context = {
                reference.requirement
                for reference in context_references
                if reference.required
            }
            if not required_context.issubset(plan_context):
                raise DecisionInvariantError(
                    "proposed plan omits required context dependencies"
                )
            plan_approvals = {
                approval
                for step in proposed_plan.steps
                for approval in step.required_approvals
            }
            if plan_approvals != set(required_approvals):
                raise DecisionInvariantError(
                    "proposed plan approvals do not match the decision"
                )
        relevant_fingerprint = relevant_context_fingerprint(context_references)
        document: dict[str, JSONValue] = {
            "assumptions": [_assumption_document(item) for item in assumptions],
            "capability_contract_fingerprint": str(
                capability_contract_fingerprint
            ),
            "conflicted_context": [
                _context_document(item) for item in conflicted_context
            ],
            "constraints": [_constraint_document(item) for item in constraints],
            "decision_type": decision_type.value,
            "explanation": explanation,
            "missing_context": [
                _context_document(item) for item in missing_context
            ],
            "owner_subject": owner_subject,
            "proposed_plan": (
                None
                if proposed_plan is None
                else [_step_document(step) for step in proposed_plan.steps]
            ),
            "reason_codes": [reason.value for reason in reason_codes],
            "relevant_context_fingerprint": str(relevant_fingerprint),
            "request_fingerprint": str(request_fingerprint),
            "request_id": request_id,
            "required_approvals": [
                _approval_document(item) for item in required_approvals
            ],
            "required_capabilities": list(required_capabilities),
            "schema": "ayyo.executive.decision.v1",
        }
        decision_fingerprint = fingerprint_document(
            FingerprintKind.DECISION,
            document,
        )
        object.__setattr__(
            self,
            "decision_id",
            f"decision-{decision_fingerprint.digest}",
        )
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "owner_subject", owner_subject)
        object.__setattr__(self, "decision_type", decision_type)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "explanation", explanation)
        object.__setattr__(self, "context_snapshot_version", context_snapshot_version)
        object.__setattr__(self, "request_fingerprint", request_fingerprint)
        object.__setattr__(
            self,
            "capability_contract_fingerprint",
            capability_contract_fingerprint,
        )
        object.__setattr__(
            self,
            "relevant_context_fingerprint",
            relevant_fingerprint,
        )
        object.__setattr__(self, "decision_fingerprint", decision_fingerprint)
        object.__setattr__(self, "context_references", context_references)
        object.__setattr__(self, "missing_context", missing_context)
        object.__setattr__(self, "conflicted_context", conflicted_context)
        object.__setattr__(self, "assumptions", assumptions)
        object.__setattr__(self, "required_capabilities", required_capabilities)
        object.__setattr__(self, "required_approvals", required_approvals)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "proposed_plan", proposed_plan)

    @staticmethod
    def _decision_tuple(
        values: tuple,
        *,
        item_type: type,
        key,
        field_name: str,
    ) -> tuple:
        if not isinstance(values, tuple) or not all(
            isinstance(value, item_type) for value in values
        ):
            raise DecisionInvariantError(
                f"{field_name} must contain only {item_type.__name__} objects"
            )
        if len(values) > MAX_REQUEST_ITEMS:
            raise DecisionInvariantError(
                f"{field_name} cannot exceed {MAX_REQUEST_ITEMS} items"
            )
        result = tuple(sorted(values, key=key))
        keys = tuple(key(item) for item in result)
        if len(keys) != len(set(keys)):
            raise DecisionInvariantError(f"{field_name} must be unique")
        return result

    @staticmethod
    def _validate_shape(
        decision_type: ExecutiveDecisionType,
        *,
        reason_codes: tuple[DecisionReason, ...],
        missing_context: tuple[ContextRequirement, ...],
        conflicted_context: tuple[ContextRequirement, ...],
        required_approvals: tuple[ApprovalRequirement, ...],
        proposed_plan: Plan | None,
    ) -> None:
        expected_reasons = {
            ExecutiveDecisionType.PROPOSE: {DecisionReason.READY_FOR_SAFETY_REVIEW},
            ExecutiveDecisionType.REQUEST_INFORMATION: {
                DecisionReason.MISSING_REQUIRED_CONTEXT
            },
            ExecutiveDecisionType.REQUEST_APPROVAL: {
                DecisionReason.APPROVAL_REQUIRED
            },
        }
        if (
            decision_type in expected_reasons
            and set(reason_codes) != expected_reasons[decision_type]
        ):
            raise DecisionInvariantError(
                f"{decision_type.value} has incompatible reason codes"
            )
        if decision_type is ExecutiveDecisionType.DEFER:
            allowed = {
                DecisionReason.MISSING_REQUIRED_CONTEXT,
                DecisionReason.CONFLICTED_REQUIRED_CONTEXT,
                DecisionReason.CAPABILITY_UNAVAILABLE,
            }
            if not set(reason_codes).issubset(allowed):
                raise DecisionInvariantError("DEFER has incompatible reason codes")
        if decision_type is ExecutiveDecisionType.REJECT:
            allowed = {
                DecisionReason.UNKNOWN_CAPABILITY,
                DecisionReason.CAPABILITY_UNAVAILABLE,
                DecisionReason.MISSING_REQUIRED_CONTEXT,
                DecisionReason.CONFLICTED_REQUIRED_CONTEXT,
            }
            if (
                DecisionReason.UNKNOWN_CAPABILITY not in reason_codes
                or not set(reason_codes).issubset(allowed)
            ):
                raise DecisionInvariantError("REJECT has incompatible reason codes")
        if (
            (DecisionReason.MISSING_REQUIRED_CONTEXT in reason_codes)
            != bool(missing_context)
        ):
            raise DecisionInvariantError(
                "missing-context reasons must match missing required context"
            )
        if (
            (DecisionReason.CONFLICTED_REQUIRED_CONTEXT in reason_codes)
            != bool(conflicted_context)
        ):
            raise DecisionInvariantError(
                "conflict reasons must match conflicted required context"
            )
        if proposed_plan is not None and not isinstance(proposed_plan, Plan):
            raise DecisionInvariantError("proposed_plan must be a Plan")
        if decision_type is ExecutiveDecisionType.PROPOSE:
            if proposed_plan is None or missing_context or conflicted_context:
                raise DecisionInvariantError(
                    "PROPOSE requires a plan and fully resolved required context"
                )
            if required_approvals:
                raise DecisionInvariantError(
                    "approval-gated proposals must request approval"
                )
        elif decision_type is ExecutiveDecisionType.REQUEST_APPROVAL:
            if proposed_plan is None or not required_approvals:
                raise DecisionInvariantError(
                    "REQUEST_APPROVAL requires a plan and approval requirements"
                )
            if missing_context or conflicted_context:
                raise DecisionInvariantError(
                    "REQUEST_APPROVAL requires resolved context"
                )
        elif decision_type is ExecutiveDecisionType.REQUEST_INFORMATION:
            if proposed_plan is not None or not missing_context or conflicted_context:
                raise DecisionInvariantError(
                    "REQUEST_INFORMATION requires only missing context and no plan"
                )
        elif proposed_plan is not None:
            raise DecisionInvariantError(
                f"{decision_type.value} cannot contain a proposed plan"
            )


@dataclass(frozen=True, slots=True)
class RevalidationResult:
    decision_id: str
    status: RevalidationStatus
    reasons: tuple[RevalidationReason, ...]
    prior_snapshot_version: ContextSnapshotVersion
    current_snapshot_version: ContextSnapshotVersion
    prior_owner_subject: str
    current_owner_subject: str
    prior_request_fingerprint: Fingerprint
    current_request_fingerprint: Fingerprint
    prior_capability_fingerprint: Fingerprint
    current_capability_fingerprint: Fingerprint
    prior_context_fingerprint: Fingerprint
    current_context_fingerprint: Fingerprint

    def __post_init__(self) -> None:
        _validate_text(
            self.decision_id,
            field_name="revalidation decision_id",
            error_type=DecisionInvariantError,
        )
        if not isinstance(self.status, RevalidationStatus):
            raise DecisionInvariantError("revalidation status is invalid")
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(reason, RevalidationReason) for reason in self.reasons
        ):
            raise DecisionInvariantError("revalidation reasons are invalid")
        rank = {reason: index for index, reason in enumerate(RevalidationReason)}
        if self.reasons != tuple(sorted(set(self.reasons), key=rank.get)):
            raise DecisionInvariantError(
                "revalidation reasons must be unique and ordered"
            )
        if (self.status is RevalidationStatus.CURRENT) != (not self.reasons):
            raise DecisionInvariantError(
                "CURRENT revalidation must have no stale reasons"
            )
        if (
            not isinstance(self.prior_snapshot_version, ContextSnapshotVersion)
            or not isinstance(self.current_snapshot_version, ContextSnapshotVersion)
        ):
            raise DecisionInvariantError("revalidation snapshot versions are invalid")
        for value, field_name in (
            (self.prior_owner_subject, "prior_owner_subject"),
            (self.current_owner_subject, "current_owner_subject"),
        ):
            _validate_text(
                value,
                field_name=field_name,
                error_type=DecisionInvariantError,
            )
        for fingerprint, kind in (
            (self.prior_request_fingerprint, FingerprintKind.REQUEST),
            (self.current_request_fingerprint, FingerprintKind.REQUEST),
            (
                self.prior_capability_fingerprint,
                FingerprintKind.CAPABILITY_CONTRACT,
            ),
            (
                self.current_capability_fingerprint,
                FingerprintKind.CAPABILITY_CONTRACT,
            ),
            (self.prior_context_fingerprint, FingerprintKind.RELEVANT_CONTEXT),
            (self.current_context_fingerprint, FingerprintKind.RELEVANT_CONTEXT),
        ):
            if not isinstance(fingerprint, Fingerprint) or fingerprint.kind is not kind:
                raise DecisionInvariantError(
                    f"revalidation {kind.value} fingerprint is invalid"
                )
        expected_reasons: set[RevalidationReason] = set()
        if self.prior_request_fingerprint != self.current_request_fingerprint:
            expected_reasons.add(RevalidationReason.REQUEST_CHANGED)
        if self.prior_owner_subject != self.current_owner_subject:
            expected_reasons.add(RevalidationReason.OWNER_CHANGED)
        if (
            self.prior_capability_fingerprint
            != self.current_capability_fingerprint
        ):
            expected_reasons.add(RevalidationReason.CAPABILITY_CONTRACT_CHANGED)
        if self.prior_context_fingerprint != self.current_context_fingerprint:
            expected_reasons.add(RevalidationReason.RELEVANT_CONTEXT_CHANGED)
        if set(self.reasons) != expected_reasons:
            raise DecisionInvariantError(
                "revalidation reasons do not match the compared sources"
            )
