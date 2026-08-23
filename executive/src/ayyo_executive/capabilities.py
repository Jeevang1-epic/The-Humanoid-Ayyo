"""Immutable capability contracts for proposal construction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from .errors import (
    InvalidCapabilityDefinitionError,
    InvalidCapabilityParametersError,
)
from .json_value import JSONValue, copy_json
from .models import (
    ApprovalRequirement,
    Assumption,
    Constraint,
    ContextRequirement,
    ExpectedResultCategory,
    FailurePolicy,
    Fingerprint,
    FingerprintKind,
    Precondition,
    _approval_document,
    _assumption_document,
    _constraint_document,
    _context_document,
    _context_key,
    _identifier_key,
    _validate_text,
    fingerprint_document,
)


MAX_CAPABILITY_DEFINITIONS = 256
MAX_CAPABILITY_ITEMS = 128


class ParameterType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    JSON = "json"


class CapabilityAvailability(StrEnum):
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    AVAILABLE_FOR_PROPOSAL = "available_for_proposal"


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    name: str
    value_type: ParameterType
    required: bool = True

    def __post_init__(self) -> None:
        _identifier_key(
            self.name,
            field_name="parameter name",
            error_type=InvalidCapabilityDefinitionError,
        )
        if not isinstance(self.value_type, ParameterType):
            raise InvalidCapabilityDefinitionError(
                "parameter value_type must be a ParameterType"
            )
        if not isinstance(self.required, bool):
            raise InvalidCapabilityDefinitionError(
                "parameter required flag must be boolean"
            )


def _ordered_unique(
    values: tuple,
    *,
    item_type: type,
    key,
    field_name: str,
) -> tuple:
    if not isinstance(values, tuple) or not all(
        isinstance(value, item_type) for value in values
    ):
        raise InvalidCapabilityDefinitionError(
            f"{field_name} must contain only {item_type.__name__} objects"
        )
    if len(values) > MAX_CAPABILITY_ITEMS:
        raise InvalidCapabilityDefinitionError(
            f"{field_name} cannot exceed {MAX_CAPABILITY_ITEMS} items"
        )
    ordered = tuple(sorted(values, key=key))
    keys = tuple(key(value) for value in ordered)
    if len(keys) != len(set(keys)):
        raise InvalidCapabilityDefinitionError(f"{field_name} must be unique")
    return ordered


@dataclass(frozen=True, slots=True, init=False)
class CapabilityDefinition:
    capability_id: str
    description: str
    availability: CapabilityAvailability
    parameters: tuple[ParameterDefinition, ...]
    required_context: tuple[ContextRequirement, ...]
    required_approvals: tuple[ApprovalRequirement, ...]
    assumptions: tuple[Assumption, ...]
    preconditions: tuple[Precondition, ...]
    constraints: tuple[Constraint, ...]
    expected_result: ExpectedResultCategory
    failure_policy: FailurePolicy

    def __init__(
        self,
        *,
        capability_id: str,
        description: str,
        availability: CapabilityAvailability,
        parameters: tuple[ParameterDefinition, ...] = (),
        required_context: tuple[ContextRequirement, ...] = (),
        required_approvals: tuple[ApprovalRequirement, ...] = (),
        assumptions: tuple[Assumption, ...] = (),
        preconditions: tuple[Precondition, ...] = (),
        constraints: tuple[Constraint, ...] = (),
        expected_result: ExpectedResultCategory = ExpectedResultCategory.INFORMATION,
        failure_policy: FailurePolicy = FailurePolicy.STOP_PLAN,
    ) -> None:
        _identifier_key(
            capability_id,
            field_name="capability_id",
            error_type=InvalidCapabilityDefinitionError,
        )
        _validate_text(
            description,
            field_name="capability description",
            error_type=InvalidCapabilityDefinitionError,
        )
        if not isinstance(availability, CapabilityAvailability) or availability is (
            CapabilityAvailability.UNKNOWN
        ):
            raise InvalidCapabilityDefinitionError(
                "a registered capability must be unavailable or available for proposal"
            )
        parameters = _ordered_unique(
            parameters,
            item_type=ParameterDefinition,
            key=lambda item: item.name,
            field_name="capability parameters",
        )
        required_context = _ordered_unique(
            required_context,
            item_type=ContextRequirement,
            key=_context_key,
            field_name="capability required_context",
        )
        required_approvals = _ordered_unique(
            required_approvals,
            item_type=ApprovalRequirement,
            key=lambda item: item.approval_id,
            field_name="capability required_approvals",
        )
        assumptions = _ordered_unique(
            assumptions,
            item_type=Assumption,
            key=lambda item: item.assumption_id,
            field_name="capability assumptions",
        )
        preconditions = _ordered_unique(
            preconditions,
            item_type=Precondition,
            key=lambda item: item.precondition_id,
            field_name="capability preconditions",
        )
        constraints = _ordered_unique(
            constraints,
            item_type=Constraint,
            key=lambda item: item.constraint_id,
            field_name="capability constraints",
        )
        if not isinstance(expected_result, ExpectedResultCategory):
            raise InvalidCapabilityDefinitionError(
                "expected_result must be an ExpectedResultCategory"
            )
        if not isinstance(failure_policy, FailurePolicy):
            raise InvalidCapabilityDefinitionError(
                "failure_policy must be a FailurePolicy"
            )
        object.__setattr__(self, "capability_id", capability_id)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "required_context", required_context)
        object.__setattr__(self, "required_approvals", required_approvals)
        object.__setattr__(self, "assumptions", assumptions)
        object.__setattr__(self, "preconditions", preconditions)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "expected_result", expected_result)
        object.__setattr__(self, "failure_policy", failure_policy)

    @property
    def currently_implemented(self) -> bool:
        return self.availability is CapabilityAvailability.AVAILABLE_FOR_PROPOSAL


def _parameter_document(parameter: ParameterDefinition) -> dict[str, JSONValue]:
    return {
        "name": parameter.name,
        "required": parameter.required,
        "value_type": parameter.value_type.value,
    }


def _definition_document(definition: CapabilityDefinition) -> dict[str, JSONValue]:
    return {
        "assumptions": [
            _assumption_document(item) for item in definition.assumptions
        ],
        "availability": definition.availability.value,
        "capability_id": definition.capability_id,
        "constraints": [
            _constraint_document(item) for item in definition.constraints
        ],
        "description": definition.description,
        "expected_result": definition.expected_result.value,
        "failure_policy": definition.failure_policy.value,
        "parameters": [_parameter_document(item) for item in definition.parameters],
        "preconditions": [
            {
                "description": item.description,
                "precondition_id": item.precondition_id,
            }
            for item in definition.preconditions
        ],
        "required_approvals": [
            _approval_document(item) for item in definition.required_approvals
        ],
        "required_context": [
            _context_document(item) for item in definition.required_context
        ],
    }


def _matches_parameter_type(value: JSONValue, value_type: ParameterType) -> bool:
    if value_type is ParameterType.STRING:
        return isinstance(value, str)
    if value_type is ParameterType.INTEGER:
        return type(value) is int
    if value_type is ParameterType.NUMBER:
        return type(value) in {int, float}
    if value_type is ParameterType.BOOLEAN:
        return type(value) is bool
    if value_type is ParameterType.OBJECT:
        return isinstance(value, dict)
    if value_type is ParameterType.ARRAY:
        return isinstance(value, list)
    return True


@dataclass(frozen=True, slots=True, init=False)
class CapabilityRegistry:
    """An immutable set of explicit capability contracts; it executes nothing."""

    _by_id: Mapping[str, CapabilityDefinition]
    _definitions: tuple[CapabilityDefinition, ...]

    def __init__(
        self,
        definitions: tuple[CapabilityDefinition, ...] = (),
    ) -> None:
        if not isinstance(definitions, tuple) or not all(
            isinstance(definition, CapabilityDefinition)
            for definition in definitions
        ):
            raise InvalidCapabilityDefinitionError(
                "registry definitions must be a tuple of CapabilityDefinition objects"
            )
        if len(definitions) > MAX_CAPABILITY_DEFINITIONS:
            raise InvalidCapabilityDefinitionError(
                "registry exceeds the capability definition limit"
            )
        ordered = tuple(sorted(definitions, key=lambda item: item.capability_id))
        identifiers = tuple(item.capability_id for item in ordered)
        if len(identifiers) != len(set(identifiers)):
            raise InvalidCapabilityDefinitionError(
                "registry capability IDs must be unique"
            )
        object.__setattr__(self, "_definitions", ordered)
        object.__setattr__(
            self,
            "_by_id",
            MappingProxyType(
                {definition.capability_id: definition for definition in ordered}
            ),
        )

    @property
    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        return self._definitions

    def get(self, capability_id: str) -> CapabilityDefinition | None:
        _identifier_key(
            capability_id,
            field_name="capability_id",
            error_type=InvalidCapabilityParametersError,
        )
        return self._by_id.get(capability_id)

    def availability(self, capability_id: str) -> CapabilityAvailability:
        definition = self.get(capability_id)
        if definition is None:
            return CapabilityAvailability.UNKNOWN
        return definition.availability

    def validate_parameters(
        self,
        definition: CapabilityDefinition,
        parameters: Mapping[str, JSONValue],
    ) -> None:
        if not isinstance(definition, CapabilityDefinition):
            raise InvalidCapabilityParametersError(
                "parameter validation requires a CapabilityDefinition"
            )
        if not isinstance(parameters, Mapping):
            raise InvalidCapabilityParametersError("parameters must be a mapping")
        copied_parameters = copy_json(
            dict(parameters),
            field_name="capability parameters",
            error_type=InvalidCapabilityParametersError,
        )
        if not isinstance(copied_parameters, dict):
            raise InvalidCapabilityParametersError("parameters must be an object")
        parameters = copied_parameters
        expected = {item.name: item for item in definition.parameters}
        actual = set(parameters)
        unsupported = sorted(actual - set(expected))
        if unsupported:
            raise InvalidCapabilityParametersError(
                f"unsupported parameters for {definition.capability_id}: {unsupported}"
            )
        missing = sorted(
            item.name
            for item in definition.parameters
            if item.required and item.name not in actual
        )
        if missing:
            raise InvalidCapabilityParametersError(
                f"missing parameters for {definition.capability_id}: {missing}"
            )
        for name in sorted(actual):
            value = parameters[name]
            parameter = expected[name]
            if not _matches_parameter_type(value, parameter.value_type):
                raise InvalidCapabilityParametersError(
                    f"parameter {name} for {definition.capability_id} must be "
                    f"{parameter.value_type.value}"
                )

    def fingerprint_for(self, capability_ids: tuple[str, ...]) -> Fingerprint:
        if not isinstance(capability_ids, tuple) or not all(
            isinstance(value, str) for value in capability_ids
        ):
            raise InvalidCapabilityDefinitionError(
                "capability_ids must be a tuple of strings"
            )
        ordered_ids = tuple(sorted(set(capability_ids)))
        if len(ordered_ids) != len(capability_ids):
            raise InvalidCapabilityDefinitionError(
                "capability_ids must be unique"
            )
        entries: list[JSONValue] = []
        for capability_id in ordered_ids:
            _identifier_key(
                capability_id,
                field_name="capability_id",
                error_type=InvalidCapabilityDefinitionError,
            )
            definition = self._by_id.get(capability_id)
            entries.append(
                {"capability_id": capability_id, "availability": "unknown"}
                if definition is None
                else _definition_document(definition)
            )
        return fingerprint_document(
            FingerprintKind.CAPABILITY_CONTRACT,
            {
                "capabilities": entries,
                "schema": "ayyo.executive.capability-contract.v1",
            },
        )
