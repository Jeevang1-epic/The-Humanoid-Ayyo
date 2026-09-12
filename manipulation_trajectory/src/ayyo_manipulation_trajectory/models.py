"""Immutable Stage 9B trajectory and eligibility evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from ayyo_manipulation_planning import (
    ExecutionDisposition,
    JointPosition,
    ManipulationPlanningDecision,
    PlanEvidenceStatus,
    PlanningDecisionReason,
    PlanningDisposition,
    verify_joint_position,
    verify_manipulation_planning_decision,
)

from .canonical import (
    JSONValue,
    MAX_JOINTS,
    MAX_TRAJECTORY_POINTS,
    SCHEMA_VERSION,
    assert_artifact_size,
    bounded_text,
    content_identity,
    finite_float,
    fingerprint,
    identifier,
    semantic_sha256,
    typed_fingerprint,
)
from .errors import TrajectoryFailureCode, TrajectoryValidationError


TIMING_METHOD_ID = "ayyo.deterministic-velocity-scaled-timing.v1"
SAFETY_REVIEW_CAPABILITY_ID = "manipulation.trajectory.simulation-review"
SAFETY_REVIEW_STEP_ID = "trajectory-review"
FUTURE_SKILL_BACKEND_ID = "future.manipulation.simulation-review"
FUTURE_SKILL_ID = "manipulation.trajectory.simulation-review"
FUTURE_RUNTIME_CONTRACT_ID = "future.stage-9c.simulation-trajectory-executor.v1"

TIMING_CONFIGURATION_SCHEMA_ID = "ayyo.manipulation-trajectory.timing-config.v1"
TRAJECTORY_REQUEST_SCHEMA_ID = "ayyo.manipulation-trajectory.request.v1"
TRAJECTORY_POINT_SCHEMA_ID = "ayyo.manipulation-trajectory.point.v1"
TRAJECTORY_SCHEMA_ID = "ayyo.manipulation-trajectory.trajectory.v1"
TRAJECTORY_EVIDENCE_SCHEMA_ID = "ayyo.manipulation-trajectory.evidence.v1"
SAFETY_REFERENCE_SCHEMA_ID = "ayyo.manipulation-trajectory.safety-reference.v1"
SAFETY_RESULT_SCHEMA_ID = "ayyo.manipulation-trajectory.safety-result.v1"
SKILL_HANDOFF_REFERENCE_SCHEMA_ID = (
    "ayyo.manipulation-trajectory.skill-handoff-reference.v1"
)
HANDOFF_DECISION_SCHEMA_ID = "ayyo.manipulation-trajectory.handoff-decision.v1"


class PhysicalValidationStatus(StrEnum):
    ABSENT = "absent"


class TrajectoryEvidenceStatus(StrEnum):
    TRAJECTORY_CONSTRUCTED_FOR_REVIEW = "trajectory_constructed_for_review"


class SafetyEligibilityStatus(StrEnum):
    TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW = (
        "trajectory_eligible_for_simulation_review"
    )
    INELIGIBLE = "ineligible"


class SafetyEligibilityReason(StrEnum):
    INDEPENDENT_SAFETY_ELIGIBLE = "independent_safety_eligible"
    SAFETY_APPROVAL_REQUIRED = "safety_approval_required"
    SAFETY_DEFERRED = "safety_deferred"
    SAFETY_BLOCKED = "safety_blocked"


class ReviewedSafetyDisposition(StrEnum):
    ELIGIBLE_FOR_DOWNSTREAM = "eligible_for_downstream"
    EXTERNAL_APPROVAL_REQUIRED = "external_approval_required"
    DEFERRED = "deferred"
    BLOCKED = "blocked"


class ReviewedHazardClass(StrEnum):
    INTERNAL_NON_ACTUATING = "internal_non_actuating"
    OTHER = "other"


class RuntimeEndpointState(StrEnum):
    NOT_REGISTERED = "not_registered"


class HandoffEligibilityStatus(StrEnum):
    ELIGIBLE_FOR_FUTURE_SIMULATION_HANDOFF_REVIEW = (
        "eligible_for_future_simulation_handoff_review"
    )
    INELIGIBLE = "ineligible"


class HandoffEligibilityReason(StrEnum):
    INDEPENDENT_SAFETY_ELIGIBLE = "independent_safety_eligible"
    SKILL_MANAGER_HANDOFF_ELIGIBLE = "skill_manager_handoff_eligible"
    FUTURE_RUNTIME_REVIEW_REQUIRED = "future_runtime_review_required"
    SAFETY_INELIGIBLE = "safety_ineligible"
    SKILL_MANAGER_INELIGIBLE = "skill_manager_ineligible"


def _schema(schema_id: str) -> dict[str, JSONValue]:
    return {"id": schema_id, "version": SCHEMA_VERSION}


def _enum(value: object, expected: type[StrEnum], field_name: str) -> StrEnum:
    if type(value) is not expected:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must use its closed enum",
        )
    return value


def _verify(instance: object, expected_type: type, builder) -> bool:
    if type(instance) is not expected_type:
        return False
    try:
        return builder() == instance
    except (
        AttributeError,
        ArithmeticError,
        TypeError,
        ValueError,
        TrajectoryValidationError,
    ):
        return False


def _identifier_tuple(
    value: object,
    field_name: str,
    maximum: int,
    *,
    minimum: int = 0,
) -> tuple[str, ...]:
    if type(value) not in {tuple, list}:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a bounded sequence",
        )
    items = tuple(identifier(item, field_name) for item in value)
    if not minimum <= len(items) <= maximum:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its item bound",
        )
    if len(items) != len(set(items)):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} contains duplicates",
        )
    return items


def _upstream_decision(value: object) -> ManipulationPlanningDecision:
    if type(value) is not ManipulationPlanningDecision or not (
        verify_manipulation_planning_decision(value)
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "Stage 9A decision failed recursive integrity verification",
        )
    if (
        value.disposition is not PlanningDisposition.PLAN_AVAILABLE_FOR_REVIEW
        or value.execution_disposition is not ExecutionDisposition.NOT_EXECUTED
        or value.plan_evidence.status
        is not PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED
        or value.plan_evidence.execution_disposition
        is not ExecutionDisposition.NOT_EXECUTED
        or value.plan_evidence.collision_proof is None
        or value.plan_evidence.collision_proof.execution_disposition
        is not ExecutionDisposition.NOT_EXECUTED
        or PlanningDecisionReason.PHYSICAL_VALIDATION_ABSENT not in value.reasons
        or PlanningDecisionReason.EXECUTION_OUT_OF_SCOPE not in value.reasons
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_REJECTED,
            "trajectory construction requires an unexecuted positive Stage 9A review decision",
        )
    return value


@dataclass(frozen=True, slots=True)
class TrajectoryTimingConfiguration:
    velocity_limit_scale: float = 0.25
    minimum_segment_duration: float = 0.05
    maximum_duration: float = 30.0
    maximum_points: int = MAX_TRAJECTORY_POINTS
    schema_id: str = field(init=False, default=TIMING_CONFIGURATION_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    timing_configuration_id: str = field(init=False)
    timing_configuration_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        scale = finite_float(self.velocity_limit_scale, "velocity_limit_scale")
        minimum = finite_float(
            self.minimum_segment_duration,
            "minimum_segment_duration",
        )
        maximum = finite_float(self.maximum_duration, "maximum_duration")
        if not 0.01 <= scale <= 0.25:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.TIMING_CONFIGURATION,
                "velocity scale must remain within [0.01, 0.25]",
            )
        if not 0.001 <= minimum <= 1.0:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.TIMING_CONFIGURATION,
                "minimum segment duration must remain within [0.001, 1.0] seconds",
            )
        if not minimum <= maximum <= 300.0:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.TIMING_CONFIGURATION,
                "maximum duration must be bounded and cover one segment",
            )
        if type(self.maximum_points) is not int or not 2 <= self.maximum_points <= (
            MAX_TRAJECTORY_POINTS
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.RESOURCE_LIMIT,
                "maximum_points must remain within [2, 129]",
            )
        object.__setattr__(self, "velocity_limit_scale", scale)
        object.__setattr__(self, "minimum_segment_duration", minimum)
        object.__setattr__(self, "maximum_duration", maximum)
        document = self._semantic_dict()
        identity, content = content_identity("trajectory-timing-configuration", document)
        object.__setattr__(self, "timing_configuration_id", identity)
        object.__setattr__(self, "timing_configuration_fingerprint", content)
        assert_artifact_size(self.as_dict(), "trajectory timing configuration")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "maximum_duration": self.maximum_duration,
            "maximum_points": self.maximum_points,
            "method_id": TIMING_METHOD_ID,
            "minimum_segment_duration": self.minimum_segment_duration,
            "schema": _schema(self.schema_id),
            "velocity_limit_scale": self.velocity_limit_scale,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "timing_configuration_fingerprint": self.timing_configuration_fingerprint,
            "timing_configuration_id": self.timing_configuration_id,
        }


def verify_timing_configuration(value: object) -> bool:
    return _verify(
        value,
        TrajectoryTimingConfiguration,
        lambda: TrajectoryTimingConfiguration(
            velocity_limit_scale=value.velocity_limit_scale,
            minimum_segment_duration=value.minimum_segment_duration,
            maximum_duration=value.maximum_duration,
            maximum_points=value.maximum_points,
        ),
    )


@dataclass(frozen=True, slots=True)
class TrajectoryConstructionRequest:
    stage9a_decision: ManipulationPlanningDecision
    timing_configuration: TrajectoryTimingConfiguration
    schema_id: str = field(init=False, default=TRAJECTORY_REQUEST_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    robot_model_id: str = field(init=False)
    robot_model_fingerprint: str = field(init=False)
    joint_catalog_id: str = field(init=False)
    joint_catalog_fingerprint: str = field(init=False)
    group_id: str = field(init=False)
    group_fingerprint: str = field(init=False)
    collision_model_id: str = field(init=False)
    collision_model_fingerprint: str = field(init=False)
    stage9a_request_id: str = field(init=False)
    stage9a_request_fingerprint: str = field(init=False)
    candidate_path_id: str = field(init=False)
    candidate_path_fingerprint: str = field(init=False)
    collision_proof_id: str = field(init=False)
    collision_proof_fingerprint: str = field(init=False)
    stage9a_evidence_id: str = field(init=False)
    stage9a_evidence_fingerprint: str = field(init=False)
    stage9a_decision_id: str = field(init=False)
    stage9a_decision_fingerprint: str = field(init=False)
    trajectory_request_id: str = field(init=False)
    trajectory_request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        decision = _upstream_decision(self.stage9a_decision)
        if not verify_timing_configuration(self.timing_configuration):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.TIMING_CONFIGURATION,
                "timing configuration failed integrity verification",
        )
        planning_request = decision.request
        proof = decision.plan_evidence.collision_proof
        if proof is None:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.UPSTREAM_INTEGRITY,
                "positive Stage 9A evidence unexpectedly lacks its collision proof",
            )
        bindings = {
            "robot_model_id": planning_request.robot_model.robot_model_id,
            "robot_model_fingerprint": planning_request.robot_model.robot_model_fingerprint,
            "joint_catalog_id": planning_request.joint_catalog.joint_catalog_id,
            "joint_catalog_fingerprint": planning_request.joint_catalog.joint_catalog_fingerprint,
            "group_id": planning_request.group.group_id,
            "group_fingerprint": planning_request.group.group_fingerprint,
            "collision_model_id": planning_request.collision_model.collision_model_id,
            "collision_model_fingerprint": planning_request.collision_model.collision_model_fingerprint,
            "stage9a_request_id": planning_request.request_id,
            "stage9a_request_fingerprint": planning_request.request_fingerprint,
            "candidate_path_id": proof.candidate_path_id,
            "candidate_path_fingerprint": proof.candidate_path_fingerprint,
            "collision_proof_id": proof.proof_id,
            "collision_proof_fingerprint": proof.proof_fingerprint,
            "stage9a_evidence_id": decision.plan_evidence.plan_evidence_id,
            "stage9a_evidence_fingerprint": decision.plan_evidence.plan_evidence_fingerprint,
            "stage9a_decision_id": decision.decision_id,
            "stage9a_decision_fingerprint": decision.decision_fingerprint,
        }
        for name, value in bindings.items():
            object.__setattr__(self, name, value)
        document = self._semantic_dict()
        identity, content = content_identity("trajectory-construction-request", document)
        object.__setattr__(self, "trajectory_request_id", identity)
        object.__setattr__(self, "trajectory_request_fingerprint", content)
        assert_artifact_size(self.as_dict(), "trajectory construction request")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "candidate_path_fingerprint": self.candidate_path_fingerprint,
            "candidate_path_id": self.candidate_path_id,
            "collision_model_fingerprint": self.collision_model_fingerprint,
            "collision_model_id": self.collision_model_id,
            "collision_proof_fingerprint": self.collision_proof_fingerprint,
            "collision_proof_id": self.collision_proof_id,
            "execution_disposition": ExecutionDisposition.NOT_EXECUTED.value,
            "group_fingerprint": self.group_fingerprint,
            "group_id": self.group_id,
            "joint_catalog_fingerprint": self.joint_catalog_fingerprint,
            "joint_catalog_id": self.joint_catalog_id,
            "physical_validation": PhysicalValidationStatus.ABSENT.value,
            "robot_model_fingerprint": self.robot_model_fingerprint,
            "robot_model_id": self.robot_model_id,
            "schema": _schema(self.schema_id),
            "stage9a_decision": self.stage9a_decision.as_dict(),
            "stage9a_decision_fingerprint": self.stage9a_decision_fingerprint,
            "stage9a_decision_id": self.stage9a_decision_id,
            "stage9a_evidence_fingerprint": self.stage9a_evidence_fingerprint,
            "stage9a_evidence_id": self.stage9a_evidence_id,
            "stage9a_request_fingerprint": self.stage9a_request_fingerprint,
            "stage9a_request_id": self.stage9a_request_id,
            "timing_configuration": self.timing_configuration.as_dict(),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "trajectory_request_fingerprint": self.trajectory_request_fingerprint,
            "trajectory_request_id": self.trajectory_request_id,
        }


def verify_trajectory_request(value: object) -> bool:
    return _verify(
        value,
        TrajectoryConstructionRequest,
        lambda: TrajectoryConstructionRequest(
            stage9a_decision=value.stage9a_decision,
            timing_configuration=value.timing_configuration,
        ),
    )


def _schedule(
    request: TrajectoryConstructionRequest,
) -> tuple[tuple[float, tuple[JointPosition, ...]], ...]:
    if not verify_trajectory_request(request):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "trajectory schedule request failed integrity verification",
        )
    decision = request.stage9a_decision
    planning_request = decision.request
    points = decision.plan_evidence.waypoints
    configuration = request.timing_configuration
    if not 2 <= len(points) <= configuration.maximum_points:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.RESOURCE_LIMIT,
            "candidate path exceeds the trajectory point bound",
        )
    if tuple(item.joint_name for item in points[0].positions) != (
        planning_request.group.joint_names
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.JOINT_ORDER_MISMATCH,
            "candidate path joint order differs from the reviewed group",
        )
    velocity_by_name = {
        joint.joint_name: joint.velocity
        for joint in planning_request.joint_catalog.chain_joints
        if joint.velocity is not None
    }
    velocities = tuple(velocity_by_name[name] for name in planning_request.group.joint_names)
    if any(type(value) is not float or value <= 0.0 for value in velocities):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "reviewed joint velocities are incomplete",
        )
    result: list[tuple[float, tuple[JointPosition, ...]]] = [
        (0.0, points[0].positions)
    ]
    elapsed = 0.0
    previous = points[0]
    planning_request.joint_catalog.validate_positions(previous.positions)
    for current in points[1:]:
        planning_request.joint_catalog.validate_positions(current.positions)
        if tuple(item.joint_name for item in current.positions) != (
            planning_request.group.joint_names
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.JOINT_ORDER_MISMATCH,
                "candidate waypoint joint order differs from the reviewed group",
            )
        deltas = tuple(
            abs(after.position - before.position)
            for before, after in zip(
                previous.positions,
                current.positions,
                strict=True,
            )
        )
        if not any(delta > 0.0 for delta in deltas):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.ZERO_MOVEMENT_SEGMENT,
                "adjacent trajectory points cannot represent a zero-movement segment",
            )
        required_duration = max(
            delta / (velocity * configuration.velocity_limit_scale)
            for delta, velocity in zip(deltas, velocities, strict=True)
        )
        segment_duration = max(
            configuration.minimum_segment_duration,
            required_duration,
        )
        if not isfinite(segment_duration) or segment_duration <= 0.0:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.TIMESTAMP,
                "derived segment duration is not finite and positive",
            )
        if segment_duration > configuration.maximum_duration - elapsed:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.RESOURCE_LIMIT,
                "derived trajectory exceeds maximum_duration",
            )
        elapsed += segment_duration
        if not isfinite(elapsed) or elapsed <= result[-1][0]:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.TIMESTAMP,
                "trajectory timestamps must be finite and strictly increasing",
            )
        result.append((elapsed, current.positions))
        previous = current
    return tuple(result)


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    point_index: int
    group_id: str
    group_fingerprint: str
    joint_catalog_id: str
    joint_catalog_fingerprint: str
    joint_names: tuple[str, ...]
    positions: tuple[JointPosition, ...]
    time_from_start: float
    schema_id: str = field(init=False, default=TRAJECTORY_POINT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    trajectory_point_id: str = field(init=False)
    trajectory_point_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.point_index) is not int or not 0 <= self.point_index < (
            MAX_TRAJECTORY_POINTS
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.RESOURCE_LIMIT,
                "point_index is outside the trajectory bound",
            )
        object.__setattr__(self, "group_id", fingerprint(self.group_id, "group_id"))
        object.__setattr__(
            self,
            "group_fingerprint",
            fingerprint(self.group_fingerprint, "group_fingerprint"),
        )
        object.__setattr__(
            self,
            "joint_catalog_id",
            fingerprint(self.joint_catalog_id, "joint_catalog_id"),
        )
        object.__setattr__(
            self,
            "joint_catalog_fingerprint",
            fingerprint(self.joint_catalog_fingerprint, "joint_catalog_fingerprint"),
        )
        names = _identifier_tuple(
            self.joint_names,
            "joint_names",
            MAX_JOINTS,
            minimum=1,
        )
        if type(self.positions) not in {tuple, list}:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.MALFORMED_ARTIFACT,
                "positions must be a bounded sequence",
            )
        positions = tuple(self.positions)
        if (
            len(positions) != len(names)
            or any(not verify_joint_position(item) for item in positions)
            or tuple(item.joint_name for item in positions) != names
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.JOINT_ORDER_MISMATCH,
                "point positions must cover the exact ordered joint sequence",
            )
        timestamp = finite_float(self.time_from_start, "time_from_start")
        if (self.point_index == 0 and timestamp != 0.0) or (
            self.point_index > 0 and timestamp <= 0.0
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.TIMESTAMP,
                "only point zero may use time_from_start 0.0",
            )
        object.__setattr__(self, "joint_names", names)
        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "time_from_start", timestamp)
        document = self._semantic_dict()
        identity, content = content_identity("trajectory-point", document)
        object.__setattr__(self, "trajectory_point_id", identity)
        object.__setattr__(self, "trajectory_point_fingerprint", content)
        assert_artifact_size(self.as_dict(), "trajectory point")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "group_fingerprint": self.group_fingerprint,
            "group_id": self.group_id,
            "joint_catalog_fingerprint": self.joint_catalog_fingerprint,
            "joint_catalog_id": self.joint_catalog_id,
            "joint_names": list(self.joint_names),
            "point_index": self.point_index,
            "positions": [item.as_dict() for item in self.positions],
            "schema": _schema(self.schema_id),
            "time_from_start": self.time_from_start,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "trajectory_point_fingerprint": self.trajectory_point_fingerprint,
            "trajectory_point_id": self.trajectory_point_id,
        }


def verify_trajectory_point(value: object) -> bool:
    return _verify(
        value,
        TrajectoryPoint,
        lambda: TrajectoryPoint(
            point_index=value.point_index,
            group_id=value.group_id,
            group_fingerprint=value.group_fingerprint,
            joint_catalog_id=value.joint_catalog_id,
            joint_catalog_fingerprint=value.joint_catalog_fingerprint,
            joint_names=value.joint_names,
            positions=value.positions,
            time_from_start=value.time_from_start,
        ),
    )


@dataclass(frozen=True, slots=True)
class DeterministicJointTrajectory:
    request: TrajectoryConstructionRequest
    points: tuple[TrajectoryPoint, ...]
    schema_id: str = field(init=False, default=TRAJECTORY_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    joint_names: tuple[str, ...] = field(init=False)
    point_count: int = field(init=False)
    duration: float = field(init=False)
    trajectory_id: str = field(init=False)
    trajectory_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_trajectory_request(self.request):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.UPSTREAM_INTEGRITY,
                "trajectory request failed integrity verification",
            )
        if type(self.points) not in {tuple, list}:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.MALFORMED_ARTIFACT,
                "trajectory points must be a bounded sequence",
            )
        points = tuple(self.points)
        expected = _schedule(self.request)
        if len(points) != len(expected) or any(
            not verify_trajectory_point(point) for point in points
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.EVIDENCE_MISMATCH,
                "trajectory does not contain the exact bounded point set",
            )
        planning_request = self.request.stage9a_decision.request
        names = planning_request.group.joint_names
        for index, (point, (timestamp, positions)) in enumerate(
            zip(points, expected, strict=True)
        ):
            if (
                point.point_index != index
                or point.group_id != planning_request.group.group_id
                or point.group_fingerprint != planning_request.group.group_fingerprint
                or point.joint_catalog_id
                != planning_request.joint_catalog.joint_catalog_id
                or point.joint_catalog_fingerprint
                != planning_request.joint_catalog.joint_catalog_fingerprint
                or point.joint_names != names
                or point.positions != positions
                or point.time_from_start != timestamp
            ):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.EVIDENCE_MISMATCH,
                    "trajectory point differs from deterministic reviewed timing",
                )
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "joint_names", names)
        object.__setattr__(self, "point_count", len(points))
        object.__setattr__(self, "duration", points[-1].time_from_start)
        document = self._semantic_dict()
        identity, content = content_identity("deterministic-joint-trajectory", document)
        object.__setattr__(self, "trajectory_id", identity)
        object.__setattr__(self, "trajectory_fingerprint", content)
        assert_artifact_size(self.as_dict(), "deterministic joint trajectory")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "candidate_path_fingerprint": self.request.candidate_path_fingerprint,
            "candidate_path_id": self.request.candidate_path_id,
            "duration": self.duration,
            "execution_disposition": ExecutionDisposition.NOT_EXECUTED.value,
            "joint_names": list(self.joint_names),
            "physical_validation": PhysicalValidationStatus.ABSENT.value,
            "point_count": self.point_count,
            "points": [item.as_dict() for item in self.points],
            "request": self.request.as_dict(),
            "schema": _schema(self.schema_id),
            "timing_configuration_fingerprint": (
                self.request.timing_configuration.timing_configuration_fingerprint
            ),
            "timing_configuration_id": (
                self.request.timing_configuration.timing_configuration_id
            ),
            "trajectory_request_fingerprint": self.request.trajectory_request_fingerprint,
            "trajectory_request_id": self.request.trajectory_request_id,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "trajectory_fingerprint": self.trajectory_fingerprint,
            "trajectory_id": self.trajectory_id,
        }


def verify_trajectory(value: object) -> bool:
    return _verify(
        value,
        DeterministicJointTrajectory,
        lambda: DeterministicJointTrajectory(request=value.request, points=value.points),
    )


@dataclass(frozen=True, slots=True)
class TrajectoryEvidence:
    request: TrajectoryConstructionRequest
    trajectory: DeterministicJointTrajectory
    status: TrajectoryEvidenceStatus = (
        TrajectoryEvidenceStatus.TRAJECTORY_CONSTRUCTED_FOR_REVIEW
    )
    joint_limits_checked: bool = True
    timing_constraints_checked: bool = True
    execution_disposition: ExecutionDisposition = ExecutionDisposition.NOT_EXECUTED
    physical_validation: PhysicalValidationStatus = PhysicalValidationStatus.ABSENT
    schema_id: str = field(init=False, default=TRAJECTORY_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    trajectory_evidence_id: str = field(init=False)
    trajectory_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_trajectory_request(self.request) or not verify_trajectory(
            self.trajectory
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.UPSTREAM_INTEGRITY,
                "trajectory evidence contains an invalid request or trajectory",
            )
        if self.trajectory.request != self.request:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.EVIDENCE_MISMATCH,
                "trajectory evidence cross-composes different requests",
            )
        _enum(self.status, TrajectoryEvidenceStatus, "trajectory evidence status")
        if (
            self.status
            is not TrajectoryEvidenceStatus.TRAJECTORY_CONSTRUCTED_FOR_REVIEW
            or type(self.joint_limits_checked) is not bool
            or not self.joint_limits_checked
            or type(self.timing_constraints_checked) is not bool
            or not self.timing_constraints_checked
            or self.execution_disposition is not ExecutionDisposition.NOT_EXECUTED
            or self.physical_validation is not PhysicalValidationStatus.ABSENT
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.EVIDENCE_MISMATCH,
                "trajectory evidence cannot claim execution, physical validation, or unchecked constraints",
            )
        document = self._semantic_dict()
        identity, content = content_identity("trajectory-evidence", document)
        object.__setattr__(self, "trajectory_evidence_id", identity)
        object.__setattr__(self, "trajectory_evidence_fingerprint", content)
        assert_artifact_size(self.as_dict(), "trajectory evidence")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "execution_disposition": self.execution_disposition.value,
            "joint_limits_checked": self.joint_limits_checked,
            "physical_validation": self.physical_validation.value,
            "request": self.request.as_dict(),
            "schema": _schema(self.schema_id),
            "status": self.status.value,
            "timing_constraints_checked": self.timing_constraints_checked,
            "trajectory": self.trajectory.as_dict(),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "trajectory_evidence_fingerprint": self.trajectory_evidence_fingerprint,
            "trajectory_evidence_id": self.trajectory_evidence_id,
        }


def verify_trajectory_evidence(value: object) -> bool:
    return _verify(
        value,
        TrajectoryEvidence,
        lambda: TrajectoryEvidence(
            request=value.request,
            trajectory=value.trajectory,
            status=value.status,
            joint_limits_checked=value.joint_limits_checked,
            timing_constraints_checked=value.timing_constraints_checked,
            execution_disposition=value.execution_disposition,
            physical_validation=value.physical_validation,
        ),
    )


@dataclass(frozen=True, slots=True)
class SafetyEligibilityReference:
    source_executive_decision_id: str
    source_executive_decision_fingerprint: str
    source_safety_decision_id: str
    source_safety_decision_fingerprint: str
    source_proposal_fingerprint: str
    source_policy_version: str
    source_policy_fingerprint: str
    source_step_id: str
    capability_id: str
    safety_disposition: ReviewedSafetyDisposition
    hazard_class: ReviewedHazardClass
    trajectory_binding_fingerprint: str
    schema_id: str = field(init=False, default=SAFETY_REFERENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    safety_reference_id: str = field(init=False)
    safety_reference_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "source_executive_decision_id",
            "source_safety_decision_id",
            "source_step_id",
            "capability_id",
        ):
            object.__setattr__(self, name, identifier(getattr(self, name), name))
        for name in (
            "source_executive_decision_fingerprint",
            "source_safety_decision_fingerprint",
            "source_proposal_fingerprint",
            "source_policy_fingerprint",
        ):
            object.__setattr__(self, name, typed_fingerprint(getattr(self, name), name))
        object.__setattr__(
            self,
            "source_policy_version",
            bounded_text(self.source_policy_version, "source_policy_version"),
        )
        _enum(self.safety_disposition, ReviewedSafetyDisposition, "safety disposition")
        _enum(self.hazard_class, ReviewedHazardClass, "hazard class")
        object.__setattr__(
            self,
            "trajectory_binding_fingerprint",
            fingerprint(
                self.trajectory_binding_fingerprint,
                "trajectory_binding_fingerprint",
            ),
        )
        if self.source_step_id != SAFETY_REVIEW_STEP_ID or self.capability_id != (
            SAFETY_REVIEW_CAPABILITY_ID
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "Safety reference is not for the exact trajectory review capability",
            )
        document = self._semantic_dict()
        identity, content = content_identity("trajectory-safety-reference", document)
        object.__setattr__(self, "safety_reference_id", identity)
        object.__setattr__(self, "safety_reference_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Safety eligibility reference")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "capability_id": self.capability_id,
            "hazard_class": self.hazard_class.value,
            "safety_disposition": self.safety_disposition.value,
            "schema": _schema(self.schema_id),
            "source_executive_decision_fingerprint": self.source_executive_decision_fingerprint,
            "source_executive_decision_id": self.source_executive_decision_id,
            "source_policy_fingerprint": self.source_policy_fingerprint,
            "source_policy_version": self.source_policy_version,
            "source_proposal_fingerprint": self.source_proposal_fingerprint,
            "source_safety_decision_fingerprint": self.source_safety_decision_fingerprint,
            "source_safety_decision_id": self.source_safety_decision_id,
            "source_step_id": self.source_step_id,
            "trajectory_binding_fingerprint": self.trajectory_binding_fingerprint,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "safety_reference_fingerprint": self.safety_reference_fingerprint,
            "safety_reference_id": self.safety_reference_id,
        }


def verify_safety_reference(value: object) -> bool:
    return _verify(
        value,
        SafetyEligibilityReference,
        lambda: SafetyEligibilityReference(
            source_executive_decision_id=value.source_executive_decision_id,
            source_executive_decision_fingerprint=value.source_executive_decision_fingerprint,
            source_safety_decision_id=value.source_safety_decision_id,
            source_safety_decision_fingerprint=value.source_safety_decision_fingerprint,
            source_proposal_fingerprint=value.source_proposal_fingerprint,
            source_policy_version=value.source_policy_version,
            source_policy_fingerprint=value.source_policy_fingerprint,
            source_step_id=value.source_step_id,
            capability_id=value.capability_id,
            safety_disposition=value.safety_disposition,
            hazard_class=value.hazard_class,
            trajectory_binding_fingerprint=value.trajectory_binding_fingerprint,
        ),
    )


@dataclass(frozen=True, slots=True)
class TrajectorySafetyEligibilityResult:
    trajectory_evidence: TrajectoryEvidence
    safety_reference: SafetyEligibilityReference
    status: SafetyEligibilityStatus
    reasons: tuple[SafetyEligibilityReason, ...]
    execution_disposition: ExecutionDisposition = ExecutionDisposition.NOT_EXECUTED
    physical_validation: PhysicalValidationStatus = PhysicalValidationStatus.ABSENT
    schema_id: str = field(init=False, default=SAFETY_RESULT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    safety_result_id: str = field(init=False)
    safety_result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_trajectory_evidence(self.trajectory_evidence) or not (
            verify_safety_reference(self.safety_reference)
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.UPSTREAM_INTEGRITY,
                "Safety eligibility result contains invalid evidence",
            )
        _enum(self.status, SafetyEligibilityStatus, "Safety eligibility status")
        if type(self.reasons) not in {tuple, list} or any(
            type(reason) is not SafetyEligibilityReason for reason in self.reasons
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.MALFORMED_ARTIFACT,
                "Safety eligibility reasons must use the closed enum",
            )
        reasons = tuple(self.reasons)
        rank = {reason: index for index, reason in enumerate(SafetyEligibilityReason)}
        if reasons != tuple(sorted(set(reasons), key=rank.get)) or not reasons:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.MALFORMED_ARTIFACT,
                "Safety eligibility reasons must be unique and ordered",
            )
        eligible = (
            self.safety_reference.safety_disposition
            is ReviewedSafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM
            and self.safety_reference.hazard_class
            is ReviewedHazardClass.INTERNAL_NON_ACTUATING
        )
        if self.safety_reference.trajectory_binding_fingerprint != (
            trajectory_review_binding_fingerprint(self.trajectory_evidence)
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.EVIDENCE_MISMATCH,
                "Safety eligibility reference is bound to a different trajectory lineage",
            )
        if eligible:
            if (
                self.status
                is not SafetyEligibilityStatus.TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW
                or reasons != (SafetyEligibilityReason.INDEPENDENT_SAFETY_ELIGIBLE,)
            ):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.SAFETY_MISMATCH,
                    "eligible Safety evidence has contradictory status or reasons",
                )
        else:
            reason_by_disposition = {
                ReviewedSafetyDisposition.EXTERNAL_APPROVAL_REQUIRED:
                    SafetyEligibilityReason.SAFETY_APPROVAL_REQUIRED,
                ReviewedSafetyDisposition.DEFERRED:
                    SafetyEligibilityReason.SAFETY_DEFERRED,
                ReviewedSafetyDisposition.BLOCKED:
                    SafetyEligibilityReason.SAFETY_BLOCKED,
                ReviewedSafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM:
                    SafetyEligibilityReason.SAFETY_BLOCKED,
            }
            if (
                self.status is not SafetyEligibilityStatus.INELIGIBLE
                or reasons
                != (reason_by_disposition[self.safety_reference.safety_disposition],)
            ):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.SAFETY_MISMATCH,
                    "ineligible Safety evidence has contradictory status or reasons",
                )
        if (
            self.execution_disposition is not ExecutionDisposition.NOT_EXECUTED
            or self.physical_validation is not PhysicalValidationStatus.ABSENT
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "Safety eligibility grants no execution or physical validation",
            )
        object.__setattr__(self, "reasons", reasons)
        document = self._semantic_dict()
        identity, content = content_identity("trajectory-safety-result", document)
        object.__setattr__(self, "safety_result_id", identity)
        object.__setattr__(self, "safety_result_fingerprint", content)
        assert_artifact_size(self.as_dict(), "trajectory Safety eligibility result")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "execution_disposition": self.execution_disposition.value,
            "physical_validation": self.physical_validation.value,
            "reasons": [reason.value for reason in self.reasons],
            "safety_reference": self.safety_reference.as_dict(),
            "schema": _schema(self.schema_id),
            "status": self.status.value,
            "trajectory_evidence": self.trajectory_evidence.as_dict(),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "safety_result_fingerprint": self.safety_result_fingerprint,
            "safety_result_id": self.safety_result_id,
        }


def verify_safety_result(value: object) -> bool:
    return _verify(
        value,
        TrajectorySafetyEligibilityResult,
        lambda: TrajectorySafetyEligibilityResult(
            trajectory_evidence=value.trajectory_evidence,
            safety_reference=value.safety_reference,
            status=value.status,
            reasons=value.reasons,
            execution_disposition=value.execution_disposition,
            physical_validation=value.physical_validation,
        ),
    )


def trajectory_review_binding_fingerprint(evidence: TrajectoryEvidence) -> str:
    if not verify_trajectory_evidence(evidence):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "trajectory evidence failed before handoff binding",
        )
    return semantic_sha256(
        "trajectory-review-binding",
        {
            "candidate_path_fingerprint": evidence.request.candidate_path_fingerprint,
            "candidate_path_id": evidence.request.candidate_path_id,
            "collision_proof_fingerprint": evidence.request.collision_proof_fingerprint,
            "collision_proof_id": evidence.request.collision_proof_id,
            "execution_disposition": evidence.execution_disposition.value,
            "physical_validation": evidence.physical_validation.value,
            "stage9a_decision_fingerprint": evidence.request.stage9a_decision_fingerprint,
            "stage9a_decision_id": evidence.request.stage9a_decision_id,
            "stage9a_evidence_fingerprint": evidence.request.stage9a_evidence_fingerprint,
            "stage9a_evidence_id": evidence.request.stage9a_evidence_id,
            "stage9a_request_fingerprint": evidence.request.stage9a_request_fingerprint,
            "stage9a_request_id": evidence.request.stage9a_request_id,
            "trajectory_evidence_fingerprint": evidence.trajectory_evidence_fingerprint,
            "trajectory_evidence_id": evidence.trajectory_evidence_id,
            "trajectory_fingerprint": evidence.trajectory.trajectory_fingerprint,
            "trajectory_id": evidence.trajectory.trajectory_id,
        },
    )


@dataclass(frozen=True, slots=True)
class SkillRuntimeHandoffReference:
    source_safety_result_id: str
    source_safety_result_fingerprint: str
    source_safety_decision_id: str
    source_safety_decision_fingerprint: str
    source_step_id: str
    capability_id: str
    skill_id: str
    skill_version: str
    skill_fingerprint: str
    selection_fingerprint: str
    invocation_id: str
    invocation_fingerprint: str
    backend_id: str
    trajectory_binding_fingerprint: str
    schema_id: str = field(init=False, default=SKILL_HANDOFF_REFERENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    skill_handoff_reference_id: str = field(init=False)
    skill_handoff_reference_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "source_safety_result_id",
            "source_safety_decision_id",
            "source_step_id",
            "capability_id",
            "skill_id",
            "invocation_id",
            "backend_id",
        ):
            object.__setattr__(self, name, identifier(getattr(self, name), name))
        object.__setattr__(
            self,
            "skill_version",
            bounded_text(self.skill_version, "skill_version", 128),
        )
        object.__setattr__(
            self,
            "source_safety_result_fingerprint",
            fingerprint(
                self.source_safety_result_fingerprint,
                "source_safety_result_fingerprint",
            ),
        )
        for name in (
            "source_safety_decision_fingerprint",
            "skill_fingerprint",
            "selection_fingerprint",
            "invocation_fingerprint",
        ):
            object.__setattr__(self, name, typed_fingerprint(getattr(self, name), name))
        object.__setattr__(
            self,
            "trajectory_binding_fingerprint",
            fingerprint(
                self.trajectory_binding_fingerprint,
                "trajectory_binding_fingerprint",
            ),
        )
        if (
            self.source_step_id != SAFETY_REVIEW_STEP_ID
            or self.capability_id != SAFETY_REVIEW_CAPABILITY_ID
            or self.skill_id != FUTURE_SKILL_ID
            or self.backend_id != FUTURE_SKILL_BACKEND_ID
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SKILL_MISMATCH,
                "Skill handoff reference must target only the exact inert future-review contract",
            )
        document = self._semantic_dict()
        identity, content = content_identity("trajectory-skill-handoff-reference", document)
        object.__setattr__(self, "skill_handoff_reference_id", identity)
        object.__setattr__(self, "skill_handoff_reference_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Skill handoff reference")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "backend_id": self.backend_id,
            "capability_id": self.capability_id,
            "invocation_fingerprint": self.invocation_fingerprint,
            "invocation_id": self.invocation_id,
            "schema": _schema(self.schema_id),
            "selection_fingerprint": self.selection_fingerprint,
            "skill_fingerprint": self.skill_fingerprint,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "source_safety_decision_fingerprint": self.source_safety_decision_fingerprint,
            "source_safety_decision_id": self.source_safety_decision_id,
            "source_safety_result_fingerprint": self.source_safety_result_fingerprint,
            "source_safety_result_id": self.source_safety_result_id,
            "source_step_id": self.source_step_id,
            "trajectory_binding_fingerprint": self.trajectory_binding_fingerprint,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "skill_handoff_reference_fingerprint": self.skill_handoff_reference_fingerprint,
            "skill_handoff_reference_id": self.skill_handoff_reference_id,
        }


def verify_skill_handoff_reference(value: object) -> bool:
    return _verify(
        value,
        SkillRuntimeHandoffReference,
        lambda: SkillRuntimeHandoffReference(
            source_safety_result_id=value.source_safety_result_id,
            source_safety_result_fingerprint=value.source_safety_result_fingerprint,
            source_safety_decision_id=value.source_safety_decision_id,
            source_safety_decision_fingerprint=value.source_safety_decision_fingerprint,
            source_step_id=value.source_step_id,
            capability_id=value.capability_id,
            skill_id=value.skill_id,
            skill_version=value.skill_version,
            skill_fingerprint=value.skill_fingerprint,
            selection_fingerprint=value.selection_fingerprint,
            invocation_id=value.invocation_id,
            invocation_fingerprint=value.invocation_fingerprint,
            backend_id=value.backend_id,
            trajectory_binding_fingerprint=value.trajectory_binding_fingerprint,
        ),
    )


@dataclass(frozen=True, slots=True)
class ExecutionHandoffEligibilityDecision:
    safety_result: TrajectorySafetyEligibilityResult
    status: HandoffEligibilityStatus
    reasons: tuple[HandoffEligibilityReason, ...]
    skill_handoff_reference: SkillRuntimeHandoffReference | None
    runtime_endpoint_state: RuntimeEndpointState = RuntimeEndpointState.NOT_REGISTERED
    future_runtime_contract_id: str = FUTURE_RUNTIME_CONTRACT_ID
    execution_disposition: ExecutionDisposition = ExecutionDisposition.NOT_EXECUTED
    physical_validation: PhysicalValidationStatus = PhysicalValidationStatus.ABSENT
    schema_id: str = field(init=False, default=HANDOFF_DECISION_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    handoff_decision_id: str = field(init=False)
    handoff_decision_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_safety_result(self.safety_result):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.UPSTREAM_INTEGRITY,
                "handoff decision Safety result failed integrity verification",
            )
        _enum(self.status, HandoffEligibilityStatus, "handoff eligibility status")
        _enum(self.runtime_endpoint_state, RuntimeEndpointState, "Runtime endpoint state")
        object.__setattr__(
            self,
            "future_runtime_contract_id",
            identifier(self.future_runtime_contract_id, "future_runtime_contract_id"),
        )
        if (
            self.runtime_endpoint_state is not RuntimeEndpointState.NOT_REGISTERED
            or self.future_runtime_contract_id != FUTURE_RUNTIME_CONTRACT_ID
            or self.execution_disposition is not ExecutionDisposition.NOT_EXECUTED
            or self.physical_validation is not PhysicalValidationStatus.ABSENT
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.RUNTIME_AUTHORITY_FORBIDDEN,
                "Stage 9B cannot register Runtime authority, execute, or claim physical validation",
            )
        if type(self.reasons) not in {tuple, list} or any(
            type(reason) is not HandoffEligibilityReason for reason in self.reasons
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.MALFORMED_ARTIFACT,
                "handoff reasons must use the closed enum",
            )
        reasons = tuple(self.reasons)
        rank = {reason: index for index, reason in enumerate(HandoffEligibilityReason)}
        if reasons != tuple(sorted(set(reasons), key=rank.get)) or not reasons:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.MALFORMED_ARTIFACT,
                "handoff reasons must be unique and ordered",
            )
        positive_reasons = (
            HandoffEligibilityReason.INDEPENDENT_SAFETY_ELIGIBLE,
            HandoffEligibilityReason.SKILL_MANAGER_HANDOFF_ELIGIBLE,
            HandoffEligibilityReason.FUTURE_RUNTIME_REVIEW_REQUIRED,
        )
        if self.status is HandoffEligibilityStatus.ELIGIBLE_FOR_FUTURE_SIMULATION_HANDOFF_REVIEW:
            if (
                self.safety_result.status
                is not SafetyEligibilityStatus.TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW
                or not verify_skill_handoff_reference(self.skill_handoff_reference)
                or reasons != positive_reasons
            ):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.SKILL_MISMATCH,
                    "positive handoff review lacks exact Safety and Skill evidence",
                )
            if self.skill_handoff_reference is None:
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.SKILL_MISMATCH,
                    "positive handoff review lacks a Skill reference",
                )
            if (
                self.skill_handoff_reference.source_safety_result_id
                != self.safety_result.safety_result_id
                or self.skill_handoff_reference.source_safety_result_fingerprint
                != self.safety_result.safety_result_fingerprint
                or self.skill_handoff_reference.source_safety_decision_id
                != self.safety_result.safety_reference.source_safety_decision_id
                or self.skill_handoff_reference.source_safety_decision_fingerprint
                != self.safety_result.safety_reference.source_safety_decision_fingerprint
                or self.skill_handoff_reference.source_step_id != SAFETY_REVIEW_STEP_ID
                or self.skill_handoff_reference.capability_id
                != SAFETY_REVIEW_CAPABILITY_ID
                or self.skill_handoff_reference.trajectory_binding_fingerprint
                != trajectory_review_binding_fingerprint(
                    self.safety_result.trajectory_evidence
                )
            ):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.EVIDENCE_MISMATCH,
                    "Skill handoff reference is for a different Safety result or trajectory",
                )
        else:
            if self.skill_handoff_reference is not None or reasons not in {
                (HandoffEligibilityReason.SAFETY_INELIGIBLE,),
                (HandoffEligibilityReason.SKILL_MANAGER_INELIGIBLE,),
            }:
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.SKILL_MISMATCH,
                    "ineligible handoff decision has contradictory Skill evidence",
                )
        object.__setattr__(self, "reasons", reasons)
        document = self._semantic_dict()
        identity, content = content_identity("trajectory-handoff-decision", document)
        object.__setattr__(self, "handoff_decision_id", identity)
        object.__setattr__(self, "handoff_decision_fingerprint", content)
        assert_artifact_size(self.as_dict(), "execution handoff eligibility decision")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "execution_disposition": self.execution_disposition.value,
            "future_runtime_contract_id": self.future_runtime_contract_id,
            "physical_validation": self.physical_validation.value,
            "reasons": [reason.value for reason in self.reasons],
            "runtime_endpoint_state": self.runtime_endpoint_state.value,
            "safety_result": self.safety_result.as_dict(),
            "schema": _schema(self.schema_id),
            "skill_handoff_reference": (
                None
                if self.skill_handoff_reference is None
                else self.skill_handoff_reference.as_dict()
            ),
            "status": self.status.value,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "handoff_decision_fingerprint": self.handoff_decision_fingerprint,
            "handoff_decision_id": self.handoff_decision_id,
        }


def verify_handoff_decision(value: object) -> bool:
    return _verify(
        value,
        ExecutionHandoffEligibilityDecision,
        lambda: ExecutionHandoffEligibilityDecision(
            safety_result=value.safety_result,
            status=value.status,
            reasons=value.reasons,
            skill_handoff_reference=value.skill_handoff_reference,
            runtime_endpoint_state=value.runtime_endpoint_state,
            future_runtime_contract_id=value.future_runtime_contract_id,
            execution_disposition=value.execution_disposition,
            physical_validation=value.physical_validation,
        ),
    )
