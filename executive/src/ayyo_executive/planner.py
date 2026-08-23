"""Deterministic construction of declarative proposal plans."""

from __future__ import annotations

from typing import Callable, TypeVar

from .capabilities import CapabilityDefinition
from .errors import PlanInvariantError
from .models import (
    ApprovalRequirement,
    Assumption,
    Constraint,
    ContextRequirement,
    ExecutiveRequest,
    MAX_CONTEXT_REQUIREMENTS,
    MAX_REQUEST_ITEMS,
    Plan,
    PlanStep,
    _context_key,
)


_T = TypeVar("_T")


def _merge_unique(
    *collections: tuple[_T, ...],
    key: Callable[[_T], object],
    field_name: str,
    max_items: int = MAX_REQUEST_ITEMS,
) -> tuple[_T, ...]:
    merged: dict[object, _T] = {}
    for collection in collections:
        for item in collection:
            item_key = key(item)
            existing = merged.get(item_key)
            if existing is not None and existing != item:
                raise PlanInvariantError(
                    f"conflicting {field_name} definitions for {item_key!r}"
                )
            merged[item_key] = item
    if len(merged) > max_items:
        raise PlanInvariantError(
            f"merged {field_name} exceeds the {max_items}-item limit"
        )
    return tuple(merged[item_key] for item_key in sorted(merged))


class DeclarativePlanner:
    """Turns validated invocations and contracts into inert plan data."""

    __slots__ = ()

    def build_plan(
        self,
        request: ExecutiveRequest,
        definitions: dict[str, CapabilityDefinition],
    ) -> Plan:
        if not isinstance(request, ExecutiveRequest):
            raise PlanInvariantError("planner requires an ExecutiveRequest")
        if not isinstance(definitions, dict) or not all(
            isinstance(key, str) and isinstance(value, CapabilityDefinition)
            for key, value in definitions.items()
        ):
            raise PlanInvariantError(
                "planner definitions must map IDs to CapabilityDefinition objects"
            )
        if set(definitions) != set(request.requested_capabilities):
            raise PlanInvariantError(
                "planner requires exactly the request's capability definitions"
            )

        steps: list[PlanStep] = []
        for invocation in request.invocations:
            definition = definitions[invocation.capability_id]
            required_context = _merge_unique(
                request.required_context,
                definition.required_context,
                key=_context_key,
                field_name="context",
            )
            required_approvals = _merge_unique(
                request.required_approvals,
                definition.required_approvals,
                key=lambda item: item.approval_id,
                field_name="approval",
            )
            constraints = _merge_unique(
                request.constraints,
                definition.constraints,
                key=lambda item: item.constraint_id,
                field_name="constraint",
            )
            steps.append(
                PlanStep(
                    step_id=invocation.step_id,
                    capability_id=invocation.capability_id,
                    parameters=invocation.parameters,
                    dependencies=invocation.dependencies,
                    preconditions=definition.preconditions,
                    required_context=required_context,
                    required_approvals=required_approvals,
                    constraints=constraints,
                    expected_result=definition.expected_result,
                    failure_policy=definition.failure_policy,
                )
            )
        return Plan(tuple(steps))


def merge_context_requirements(
    request: ExecutiveRequest,
    definitions: tuple[CapabilityDefinition, ...],
) -> tuple[ContextRequirement, ...]:
    return _merge_unique(
        request.required_context,
        *(definition.required_context for definition in definitions),
        key=_context_key,
        field_name="context",
        max_items=MAX_CONTEXT_REQUIREMENTS,
    )


def merge_approvals(
    request: ExecutiveRequest,
    definitions: tuple[CapabilityDefinition, ...],
) -> tuple[ApprovalRequirement, ...]:
    return _merge_unique(
        request.required_approvals,
        *(definition.required_approvals for definition in definitions),
        key=lambda item: item.approval_id,
        field_name="approval",
    )


def merge_constraints(
    request: ExecutiveRequest,
    definitions: tuple[CapabilityDefinition, ...],
) -> tuple[Constraint, ...]:
    return _merge_unique(
        request.constraints,
        *(definition.constraints for definition in definitions),
        key=lambda item: item.constraint_id,
        field_name="constraint",
    )


def merge_assumptions(
    request: ExecutiveRequest,
    definitions: tuple[CapabilityDefinition, ...],
) -> tuple[Assumption, ...]:
    return _merge_unique(
        request.assumptions,
        *(definition.assumptions for definition in definitions),
        key=lambda item: item.assumption_id,
        field_name="assumption",
    )
