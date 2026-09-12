from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import math

import pytest

from ayyo_manipulation_planning import (
    ExecutionDisposition,
    ManipulationPlanEvidence,
    ManipulationPlanningRequest,
    MoveItCollisionProof,
    PlanEvidenceStatus,
    deterministic_joint_interpolation,
    evaluate_manipulation_plan,
    make_joint_goal,
)
from ayyo_manipulation_trajectory import (
    PhysicalValidationStatus,
    TrajectoryConstructionRequest,
    TrajectoryEvidenceStatus,
    TrajectoryFailureCode,
    TrajectoryPoint,
    TrajectoryTimingConfiguration,
    TrajectoryValidationError,
    canonical_manipulation_trajectory_artifact_json,
    construct_deterministic_trajectory,
    create_trajectory_evidence,
    verify_trajectory,
    verify_trajectory_evidence,
    verify_trajectory_request,
)


def test_constructs_exact_bounded_velocity_scaled_timing(stage9b_bundle) -> None:
    trajectory = stage9b_bundle["trajectory"]
    request = stage9b_bundle["trajectory_request"]
    catalog = stage9b_bundle["catalog"]
    group = stage9b_bundle["group"]
    configuration = stage9b_bundle["timing"]

    assert trajectory.point_count == len(stage9b_bundle["waypoints"])
    assert trajectory.point_count <= configuration.maximum_points
    assert trajectory.duration <= configuration.maximum_duration
    assert trajectory.joint_names == group.joint_names
    assert trajectory.points[0].time_from_start == 0.0
    assert all(
        after.time_from_start > before.time_from_start
        for before, after in zip(trajectory.points, trajectory.points[1:])
    )
    velocities = {
        joint.joint_name: joint.velocity for joint in catalog.chain_joints
    }
    for before, after in zip(trajectory.points, trajectory.points[1:]):
        duration = after.time_from_start - before.time_from_start
        assert duration >= configuration.minimum_segment_duration
        for old, new in zip(before.positions, after.positions, strict=True):
            observed = abs(new.position - old.position) / duration
            assert observed <= (
                velocities[new.joint_name] * configuration.velocity_limit_scale
            ) + 1e-12
    assert tuple(point.positions for point in trajectory.points) == tuple(
        waypoint.positions
        for waypoint in request.stage9a_decision.plan_evidence.waypoints
    )


def test_construction_is_duplicate_run_deterministic(stage9b_bundle) -> None:
    request = stage9b_bundle["trajectory_request"]
    first = construct_deterministic_trajectory(request)
    second = construct_deterministic_trajectory(request)
    assert first == second
    assert first.trajectory_id == second.trajectory_id
    assert canonical_manipulation_trajectory_artifact_json(first) == (
        canonical_manipulation_trajectory_artifact_json(second)
    )


def test_positive_evidence_is_explicitly_not_executed(stage9b_bundle) -> None:
    evidence = stage9b_bundle["trajectory_evidence"]
    assert evidence.status is (
        TrajectoryEvidenceStatus.TRAJECTORY_CONSTRUCTED_FOR_REVIEW
    )
    assert evidence.execution_disposition is ExecutionDisposition.NOT_EXECUTED
    assert evidence.physical_validation is PhysicalValidationStatus.ABSENT
    assert evidence.joint_limits_checked
    assert evidence.timing_constraints_checked


def test_models_and_nested_sequences_are_immutable(stage9b_bundle) -> None:
    trajectory = stage9b_bundle["trajectory"]
    with pytest.raises(FrozenInstanceError):
        trajectory.duration = 1.0
    with pytest.raises(TypeError):
        trajectory.points[0] = trajectory.points[-1]
    with pytest.raises(FrozenInstanceError):
        trajectory.points[0].positions[0].position = 0.5


@pytest.mark.parametrize(
    ("kwargs", "code"),
    (
        ({"velocity_limit_scale": 0.0}, TrajectoryFailureCode.TIMING_CONFIGURATION),
        ({"velocity_limit_scale": 0.2500001}, TrajectoryFailureCode.TIMING_CONFIGURATION),
        ({"velocity_limit_scale": math.nan}, TrajectoryFailureCode.NONFINITE_VALUE),
        ({"velocity_limit_scale": math.inf}, TrajectoryFailureCode.NONFINITE_VALUE),
        ({"minimum_segment_duration": 0.0001}, TrajectoryFailureCode.TIMING_CONFIGURATION),
        ({"maximum_duration": 301.0}, TrajectoryFailureCode.TIMING_CONFIGURATION),
        ({"maximum_points": 1}, TrajectoryFailureCode.RESOURCE_LIMIT),
        ({"maximum_points": 130}, TrajectoryFailureCode.RESOURCE_LIMIT),
        ({"maximum_points": True}, TrajectoryFailureCode.RESOURCE_LIMIT),
    ),
)
def test_pathological_timing_configuration_fails_closed(kwargs, code) -> None:
    with pytest.raises(TrajectoryValidationError) as caught:
        TrajectoryTimingConfiguration(**kwargs)
    assert caught.value.code is code


def test_maximum_duration_is_checked_before_timestamp_growth(stage9a_bundle) -> None:
    request = TrajectoryConstructionRequest(
        stage9a_decision=stage9a_bundle["decision"],
        timing_configuration=TrajectoryTimingConfiguration(maximum_duration=0.05),
    )
    with pytest.raises(TrajectoryValidationError) as caught:
        construct_deterministic_trajectory(request)
    assert caught.value.code is TrajectoryFailureCode.RESOURCE_LIMIT


def test_configuration_identity_changes_trajectory_identity(stage9a_bundle) -> None:
    first_request = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.25),
    )
    second_request = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.2),
    )
    first = construct_deterministic_trajectory(first_request)
    second = construct_deterministic_trajectory(second_request)
    assert first_request.trajectory_request_id != second_request.trajectory_request_id
    assert first.trajectory_id != second.trajectory_id
    assert first.points != second.points


def test_cross_composed_request_and_trajectory_fail(stage9a_bundle) -> None:
    request_a = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.25),
    )
    request_b = TrajectoryConstructionRequest(
        stage9a_bundle["decision"],
        TrajectoryTimingConfiguration(velocity_limit_scale=0.2),
    )
    trajectory_a = construct_deterministic_trajectory(request_a)
    with pytest.raises(TrajectoryValidationError) as caught:
        create_trajectory_evidence(request_b, trajectory_a)
    assert caught.value.code is TrajectoryFailureCode.EVIDENCE_MISMATCH


@pytest.mark.parametrize("mutation", ("timestamp", "position", "reorder", "delete", "duplicate"))
def test_trajectory_point_mutations_fail(stage9b_bundle, mutation: str) -> None:
    trajectory = stage9b_bundle["trajectory"]
    points = list(trajectory.points)
    if mutation == "timestamp":
        points[1] = replace(points[1], time_from_start=points[1].time_from_start + 0.01)
    elif mutation == "position":
        positions = list(points[1].positions)
        positions[0] = replace(positions[0], position=positions[0].position + 0.01)
        points[1] = replace(points[1], positions=tuple(positions))
    elif mutation == "reorder":
        points[1], points[2] = points[2], points[1]
    elif mutation == "delete":
        del points[1]
    else:
        points.insert(1, points[1])
    with pytest.raises(TrajectoryValidationError):
        replace(trajectory, points=tuple(points))


def test_post_construction_mutation_is_not_publishable(stage9b_bundle) -> None:
    tampered = copy.deepcopy(stage9b_bundle["trajectory_evidence"])
    object.__setattr__(tampered.trajectory.points[1], "time_from_start", 999.0)
    assert not verify_trajectory(tampered.trajectory)
    assert not verify_trajectory_evidence(tampered)
    with pytest.raises(Exception):
        canonical_manipulation_trajectory_artifact_json(tampered)


def test_stage9a_nested_mutation_is_rejected_before_construction(stage9b_bundle) -> None:
    tampered_decision = copy.deepcopy(stage9b_bundle["decision"])
    object.__setattr__(tampered_decision.request.group, "joint_names", tuple(reversed(
        tampered_decision.request.group.joint_names
    )))
    with pytest.raises(TrajectoryValidationError) as caught:
        TrajectoryConstructionRequest(
            tampered_decision,
            TrajectoryTimingConfiguration(),
        )
    assert caught.value.code is TrajectoryFailureCode.UPSTREAM_INTEGRITY


def test_stage9a_rejection_cannot_be_rehash_wrapped(stage9b_bundle) -> None:
    tampered = copy.deepcopy(stage9b_bundle["decision"])
    object.__setattr__(tampered, "disposition", "rejected")
    with pytest.raises(TrajectoryValidationError):
        TrajectoryConstructionRequest(tampered, TrajectoryTimingConfiguration())
    assert not verify_trajectory_request(
        object.__new__(TrajectoryConstructionRequest)
    )


def test_valid_stage9a_duplicate_waypoint_fails_as_zero_movement(stage9a_bundle) -> None:
    original = stage9a_bundle["request"]
    start_values = tuple(item.position for item in original.start_state.positions)
    request9a = ManipulationPlanningRequest(
        robot_model=original.robot_model,
        joint_catalog=original.joint_catalog,
        group=original.group,
        collision_model=original.collision_model,
        start_state=original.start_state,
        goal=make_joint_goal(original.group, original.joint_catalog, start_values),
        scene=original.scene,
        planner_configuration=original.planner_configuration,
    )
    waypoints = deterministic_joint_interpolation(request9a)
    proof = MoveItCollisionProof(
        request_id=request9a.request_id,
        request_fingerprint=request9a.request_fingerprint,
        collision_model_id=request9a.collision_model.collision_model_id,
        collision_model_fingerprint=request9a.collision_model.collision_model_fingerprint,
        planner_configuration_id=request9a.planner_configuration.configuration_id,
        planner_configuration_fingerprint=request9a.planner_configuration.configuration_fingerprint,
        robot_description_content_fingerprint=(
            request9a.collision_model.robot_description_content_fingerprint
        ),
        srdf_content_fingerprint=request9a.collision_model.srdf_content_fingerprint,
        disabled_collision_pairs=request9a.collision_model.disabled_collision_pairs,
        backend_version="moveit-2.12.4",
        joint_names=request9a.group.joint_names,
        waypoints=waypoints,
        collision_objects=request9a.scene.collision_objects,
        self_collision_free=(True,) * len(waypoints),
        environment_collision_free=(True,) * len(waypoints),
        limits_match_reviewed=True,
        goal_obstacle_collision_reported=True,
        execution_disposition=ExecutionDisposition.NOT_EXECUTED,
    )
    evidence = ManipulationPlanEvidence(
        request=request9a,
        status=PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED,
        collision_proof=proof,
        backend_version="moveit-2.12.4",
        planner_seed=0,
        waypoints=waypoints,
        checked_collision_object_ids=("review-box",),
        colliding_object_ids=(),
        self_collision_checked=True,
        environment_collision_checked=True,
        execution_disposition=ExecutionDisposition.NOT_EXECUTED,
    )
    request = TrajectoryConstructionRequest(
        evaluate_manipulation_plan(request9a, evidence),
        TrajectoryTimingConfiguration(),
    )
    with pytest.raises(TrajectoryValidationError) as caught:
        construct_deterministic_trajectory(request)
    assert caught.value.code is TrajectoryFailureCode.ZERO_MOVEMENT_SEGMENT
