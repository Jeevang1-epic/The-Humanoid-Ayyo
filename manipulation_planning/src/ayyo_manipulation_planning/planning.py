"""Pure deterministic helpers for bounded planning requests and evidence review."""

from __future__ import annotations

from math import ceil

from .errors import PlanningFailureCode, PlanningValidationError
from .models import (
    COLLISION_BACKEND_ID,
    PLANNER_ID,
    ExecutionDisposition,
    JointPosition,
    JointSpaceGoal,
    ManipulationPlanEvidence,
    ManipulationPlanningDecision,
    ManipulationPlanningRequest,
    ManipulatorGroupIdentity,
    ManipulatorJointCatalog,
    ManipulatorJointState,
    PlanEvidenceStatus,
    PlannerConfiguration,
    PlanningDecisionReason,
    PlanningDisposition,
)


def default_planner_configuration() -> PlannerConfiguration:
    return PlannerConfiguration(
        planner_id=PLANNER_ID,
        collision_backend_id=COLLISION_BACKEND_ID,
        interpolation_step=0.05,
        max_waypoints=129,
        deterministic_seed=0,
    )


def make_joint_state(
    group: ManipulatorGroupIdentity,
    catalog: ManipulatorJointCatalog,
    values: tuple[float, ...],
) -> ManipulatorJointState:
    if type(values) is not tuple or len(values) != len(catalog.planning_joint_names):
        raise PlanningValidationError(
            PlanningFailureCode.MISSING_JOINT,
            "state values must cover the exact left-arm joint sequence",
        )
    state = ManipulatorJointState(
        group_id=group.group_id,
        group_fingerprint=group.group_fingerprint,
        joint_catalog_id=catalog.joint_catalog_id,
        joint_catalog_fingerprint=catalog.joint_catalog_fingerprint,
        positions=tuple(
            JointPosition(joint_name=name, position=value)
            for name, value in zip(catalog.planning_joint_names, values, strict=True)
        ),
    )
    catalog.validate_positions(state.positions)
    return state


def make_joint_goal(
    group: ManipulatorGroupIdentity,
    catalog: ManipulatorJointCatalog,
    values: tuple[float, ...],
) -> JointSpaceGoal:
    state = make_joint_state(group, catalog, values)
    return JointSpaceGoal(
        group_id=state.group_id,
        group_fingerprint=state.group_fingerprint,
        joint_catalog_id=state.joint_catalog_id,
        joint_catalog_fingerprint=state.joint_catalog_fingerprint,
        positions=state.positions,
    )


def deterministic_joint_interpolation(
    request: ManipulationPlanningRequest,
) -> tuple[ManipulatorJointState, ...]:
    """Produce bounded candidates for an external MoveIt collision check.

    The samples are not a valid plan by themselves and never execute. Only
    separately supplied, exactly-bound collision evidence may support a
    ``PLAN_AVAILABLE_FOR_REVIEW`` decision.
    """

    start = tuple(item.position for item in request.start_state.positions)
    goal = tuple(item.position for item in request.goal.positions)
    largest_delta = max(
        abs(goal_value - start_value)
        for start_value, goal_value in zip(start, goal, strict=True)
    )
    steps = max(
        1,
        ceil(largest_delta / request.planner_configuration.interpolation_step),
    )
    if steps + 1 > request.planner_configuration.max_waypoints:
        raise PlanningValidationError(
            PlanningFailureCode.RESOURCE_LIMIT,
            "bounded interpolation would exceed max_waypoints",
        )
    waypoints = []
    for index in range(steps + 1):
        fraction = index / steps
        values = tuple(
            float(start_value + ((goal_value - start_value) * fraction))
            for start_value, goal_value in zip(start, goal, strict=True)
        )
        waypoints.append(make_joint_state(request.group, request.joint_catalog, values))
    return tuple(waypoints)


def evaluate_manipulation_plan(
    request: ManipulationPlanningRequest,
    evidence: ManipulationPlanEvidence,
) -> ManipulationPlanningDecision:
    if evidence.request != request:
        raise PlanningValidationError(
            PlanningFailureCode.EVIDENCE_MISMATCH,
            "plan evidence is not bound to the exact planning request",
        )
    reason_by_status = {
        PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED:
            PlanningDecisionReason.COLLISION_FREE_PLAN_EVIDENCE_ACCEPTED,
        PlanEvidenceStatus.START_STATE_COLLISION_REPORTED:
            PlanningDecisionReason.START_STATE_COLLISION,
        PlanEvidenceStatus.GOAL_STATE_COLLISION_REPORTED:
            PlanningDecisionReason.GOAL_STATE_COLLISION,
        PlanEvidenceStatus.PATH_COLLISION_REPORTED:
            PlanningDecisionReason.PATH_COLLISION,
        PlanEvidenceStatus.NO_PLAN_REPORTED:
            PlanningDecisionReason.NO_PLAN_FOUND,
    }
    disposition = (
        PlanningDisposition.PLAN_AVAILABLE_FOR_REVIEW
        if evidence.status is PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED
        else PlanningDisposition.REJECTED
    )
    return ManipulationPlanningDecision(
        request=request,
        plan_evidence=evidence,
        disposition=disposition,
        reasons=(
            reason_by_status[evidence.status],
            PlanningDecisionReason.EXECUTION_OUT_OF_SCOPE,
            PlanningDecisionReason.PHYSICAL_VALIDATION_ABSENT,
        ),
        execution_disposition=ExecutionDisposition.NOT_EXECUTED,
    )
