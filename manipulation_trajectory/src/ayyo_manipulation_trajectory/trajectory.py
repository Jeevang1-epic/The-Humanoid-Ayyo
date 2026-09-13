"""Deterministic, non-executing trajectory construction."""

from __future__ import annotations

from .errors import TrajectoryFailureCode, TrajectoryValidationError
from .models import (
    DeterministicJointTrajectory,
    TrajectoryConstructionRequest,
    TrajectoryEvidence,
    TrajectoryPoint,
    _schedule,
    verify_trajectory,
    verify_trajectory_request,
)


def construct_deterministic_trajectory(
    request: TrajectoryConstructionRequest,
) -> DeterministicJointTrajectory:
    """Construct exact timestamps for a recursively verified Stage 9A path.

    This is a pure calculation.  It exposes no transport, controller, or runtime
    operation and it never changes robot or simulator state.
    """

    if not verify_trajectory_request(request):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "trajectory construction requires a verified request",
        )
    planning_request = request.stage9a_decision.request
    names = planning_request.group.joint_names
    points = tuple(
        TrajectoryPoint(
            point_index=index,
            group_id=planning_request.group.group_id,
            group_fingerprint=planning_request.group.group_fingerprint,
            joint_catalog_id=planning_request.joint_catalog.joint_catalog_id,
            joint_catalog_fingerprint=(
                planning_request.joint_catalog.joint_catalog_fingerprint
            ),
            joint_names=names,
            positions=positions,
            time_from_start=timestamp,
        )
        for index, (timestamp, positions) in enumerate(_schedule(request))
    )
    return DeterministicJointTrajectory(request=request, points=points)


def create_trajectory_evidence(
    request: TrajectoryConstructionRequest,
    trajectory: DeterministicJointTrajectory,
) -> TrajectoryEvidence:
    """Seal an exact deterministic trajectory as pre-execution review evidence."""

    if not verify_trajectory_request(request) or not verify_trajectory(trajectory):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "trajectory evidence requires verified inputs",
        )
    return TrajectoryEvidence(request=request, trajectory=trajectory)
