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
from ayyo_executive import (
    DecisionReason,
    ExecutiveDecision,
    ExecutiveDecisionType,
    ExecutiveError,
    ExpectedResultCategory,
    FailurePolicy,
    Plan,
    PlanStep,
)
from ayyo_safety import (
    CapabilitySafetyRule,
    HazardClass,
    SafetyDecision,
    SafetyKernel,
    SafetyKernelError,
    SafetyPolicy,
    SafetyRevalidationStatus,
)
from ayyo_skill_manager import (
    BindingStatus,
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    InvocationStatus,
    SkillAvailability,
    SkillBindingResult,
    SkillDefinition,
    SkillInvocation,
    SkillLifecycle,
    SkillManagerError,
    SkillManagerService,
    SkillRegistry,
    SkillSelection,
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
    SAFETY_CLASSIFICATION_MISMATCH = "safety_classification_mismatch"
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
        AssertionError,
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
    try:
        velocities = tuple(
            velocity_by_name[name] for name in planning_request.group.joint_names
        )
    except KeyError as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "reviewed joint velocities do not cover the exact group",
        ) from error
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


def trajectory_safety_review_parameters(
    evidence: TrajectoryEvidence,
) -> dict[str, str]:
    """Return the closed parameter document binding Safety to one trajectory."""

    if not verify_trajectory_evidence(evidence):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "Safety parameters require verified trajectory evidence",
        )
    request = evidence.request
    trajectory = evidence.trajectory
    return {
        "candidate_path_fingerprint": request.candidate_path_fingerprint,
        "candidate_path_id": request.candidate_path_id,
        "collision_proof_fingerprint": request.collision_proof_fingerprint,
        "collision_proof_id": request.collision_proof_id,
        "execution_disposition": evidence.execution_disposition.value,
        "physical_validation": evidence.physical_validation.value,
        "stage9a_decision_fingerprint": request.stage9a_decision_fingerprint,
        "stage9a_decision_id": request.stage9a_decision_id,
        "stage9a_evidence_fingerprint": request.stage9a_evidence_fingerprint,
        "stage9a_evidence_id": request.stage9a_evidence_id,
        "stage9a_request_fingerprint": request.stage9a_request_fingerprint,
        "stage9a_request_id": request.stage9a_request_id,
        "trajectory_evidence_fingerprint": evidence.trajectory_evidence_fingerprint,
        "trajectory_evidence_id": evidence.trajectory_evidence_id,
        "trajectory_fingerprint": trajectory.trajectory_fingerprint,
        "trajectory_id": trajectory.trajectory_id,
        "trajectory_request_fingerprint": request.trajectory_request_fingerprint,
        "trajectory_request_id": request.trajectory_request_id,
    }


def _validate_exact_proposal(
    evidence: TrajectoryEvidence,
    proposal: ExecutiveDecision,
) -> None:
    if type(proposal) is not ExecutiveDecision:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety review requires an immutable Executive decision",
        )
    try:
        plan = proposal.proposed_plan
    except AttributeError as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Executive proposal failed its immutable public contract",
        ) from error
    if type(plan) is not Plan:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety review proposal must contain one exact trajectory-review step",
        )
    try:
        if len(plan.steps) != 1:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "Safety review proposal must contain one exact trajectory-review step",
            )
        step = plan.steps[0]
    except (AttributeError, IndexError, TypeError) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety review proposal plan failed its immutable public contract",
        ) from error
    if type(step) is not PlanStep:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Executive proposal is not the closed non-actuating trajectory-review contract",
        )
    try:
        invalid = (
            proposal.request_id != evidence.trajectory_evidence_id
            or proposal.decision_type is not ExecutiveDecisionType.PROPOSE
            or proposal.reason_codes != (DecisionReason.READY_FOR_SAFETY_REVIEW,)
            or proposal.context_references
            or proposal.assumptions
            or proposal.required_capabilities != (SAFETY_REVIEW_CAPABILITY_ID,)
            or proposal.required_approvals
            or proposal.constraints
            or step.step_id != SAFETY_REVIEW_STEP_ID
            or step.capability_id != SAFETY_REVIEW_CAPABILITY_ID
            or step.parameters != trajectory_safety_review_parameters(evidence)
            or step.dependencies
            or step.preconditions
            or step.required_context
            or step.required_approvals
            or step.constraints
            or step.expected_result is not ExpectedResultCategory.INFORMATION
            or step.failure_policy is not FailurePolicy.STOP_PLAN
        )
    except (
        AssertionError,
        AttributeError,
        ExecutiveError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Executive proposal failed closed during trajectory-review reconstruction",
        ) from error
    if invalid:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Executive proposal is not the closed non-actuating trajectory-review contract",
        )


def _validated_safety_kernel(kernel: object) -> SafetyKernel:
    """Reconstruct the complete Safety policy before trusting its identity."""

    if type(kernel) is not SafetyKernel:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety eligibility requires the exact public Safety kernel",
        )
    try:
        policy = kernel.policy
        if (
            type(policy) is not SafetyPolicy
            or type(policy.capability_rules) is not tuple
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "authoritative Safety policy failed its public contract",
            )
        if any(
            type(rule) is not CapabilitySafetyRule
            for rule in policy.capability_rules
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "authoritative Safety capability rules failed their public contracts",
            )
        rebuilt_policy = SafetyPolicy(
            capability_rules=tuple(
                CapabilitySafetyRule(
                    capability_id=rule.capability_id,
                    hazard_class=rule.hazard_class,
                    required_precondition_ids=rule.required_precondition_ids,
                    required_constraint_ids=rule.required_constraint_ids,
                )
                for rule in policy.capability_rules
            )
        )
        rebuilt_kernel = SafetyKernel(rebuilt_policy)
        if rebuilt_kernel != kernel:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "authoritative Safety policy content does not match its derived identity",
            )
    except TrajectoryValidationError:
        raise
    except (
        AssertionError,
        AttributeError,
        SafetyKernelError,
        TypeError,
        ValueError,
    ) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "authoritative Safety policy could not be reconstructed exactly",
        ) from error
    return rebuilt_kernel


def _validated_safety_context(
    evidence: TrajectoryEvidence,
    proposal: ExecutiveDecision,
    safety_decision: SafetyDecision,
    kernel: SafetyKernel,
) -> tuple[ReviewedSafetyDisposition, ReviewedHazardClass]:
    if not verify_trajectory_evidence(evidence):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.UPSTREAM_INTEGRITY,
            "Safety eligibility requires verified trajectory evidence",
        )
    if type(safety_decision) is not SafetyDecision:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety eligibility requires exact public Safety contracts",
        )
    rebuilt_kernel = _validated_safety_kernel(kernel)
    _validate_exact_proposal(evidence, proposal)
    try:
        revalidation = rebuilt_kernel.revalidate(safety_decision, proposal)
        rebuilt = rebuilt_kernel.evaluate(proposal)
        invalid = (
            revalidation.status is not SafetyRevalidationStatus.CURRENT
            or rebuilt != safety_decision
            or safety_decision.source_decision_id != proposal.decision_id
            or safety_decision.source_request_id != evidence.trajectory_evidence_id
            or len(safety_decision.step_decisions) != 1
        )
    except (
        AssertionError,
        AttributeError,
        ExecutiveError,
        IndexError,
        KeyError,
        SafetyKernelError,
        TypeError,
        ValueError,
    ) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety evidence could not be independently revalidated",
        ) from error
    if invalid:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety evidence is stale, substituted, or not reproducible",
        )
    step = safety_decision.step_decisions[0]
    if (
        step.step_id != SAFETY_REVIEW_STEP_ID
        or step.capability_id != SAFETY_REVIEW_CAPABILITY_ID
    ):
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety step does not bind the trajectory-review capability",
        )
    try:
        disposition = ReviewedSafetyDisposition(safety_decision.disposition.value)
    except (AttributeError, ValueError) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SAFETY_MISMATCH,
            "Safety disposition is not a reviewed Stage 9B classification",
        ) from error
    hazard = (
        ReviewedHazardClass.INTERNAL_NON_ACTUATING
        if step.hazard_class is HazardClass.INTERNAL_NON_ACTUATING
        else ReviewedHazardClass.OTHER
    )
    return disposition, hazard


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
    source_proposal: ExecutiveDecision | None = field(default=None, repr=False)
    source_safety_decision: SafetyDecision | None = field(default=None, repr=False)
    source_safety_kernel: SafetyKernel | None = field(default=None, repr=False)
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
        disposition, hazard = _validated_safety_context(
            self.trajectory_evidence,
            self.source_proposal,
            self.source_safety_decision,
            self.source_safety_kernel,
        )
        expected_reference = SafetyEligibilityReference(
            source_executive_decision_id=self.source_proposal.decision_id,
            source_executive_decision_fingerprint=str(
                self.source_proposal.decision_fingerprint
            ),
            source_safety_decision_id=self.source_safety_decision.decision_id,
            source_safety_decision_fingerprint=str(
                self.source_safety_decision.decision_fingerprint
            ),
            source_proposal_fingerprint=str(
                self.source_safety_decision.proposal_fingerprint
            ),
            source_policy_version=self.source_safety_decision.policy_version,
            source_policy_fingerprint=str(
                self.source_safety_decision.policy_fingerprint
            ),
            source_step_id=SAFETY_REVIEW_STEP_ID,
            capability_id=SAFETY_REVIEW_CAPABILITY_ID,
            safety_disposition=disposition,
            hazard_class=hazard,
            trajectory_binding_fingerprint=trajectory_review_binding_fingerprint(
                self.trajectory_evidence
            ),
        )
        if self.safety_reference != expected_reference:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.EVIDENCE_MISMATCH,
                "Safety reference does not match its authoritative trajectory review",
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
            disposition is ReviewedSafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM
            and hazard is ReviewedHazardClass.INTERNAL_NON_ACTUATING
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
                    SafetyEligibilityReason.SAFETY_CLASSIFICATION_MISMATCH,
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
            source_proposal=value.source_proposal,
            source_safety_decision=value.source_safety_decision,
            source_safety_kernel=value.source_safety_kernel,
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


def _rebuilt_skill_definition(skill: object) -> SkillDefinition:
    if type(skill) is not SkillDefinition:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "authoritative Skill definition failed its public contract",
        )
    try:
        rebuilt = SkillDefinition(
            skill_id=skill.skill_id,
            version=skill.version,
            name=skill.name,
            description=skill.description,
            capability_ids=skill.capability_ids,
            backend_id=skill.backend_id,
            input_schema=skill.input_schema,
            output_schema=skill.output_schema,
            required_context=skill.required_context,
            required_resources=skill.required_resources,
            required_approval_classes=skill.required_approval_classes,
            safety_classification=skill.safety_classification,
            expected_result=skill.expected_result,
            timeout_ms=skill.timeout_ms,
            concurrency_policy=skill.concurrency_policy,
            idempotency=skill.idempotency,
            failure_semantics=skill.failure_semantics,
            availability=skill.availability,
            lifecycle=skill.lifecycle,
            metadata=skill.metadata,
        )
        if rebuilt != skill or rebuilt.fingerprint != skill.fingerprint:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SKILL_MISMATCH,
                "authoritative Skill declaration does not match its derived identity",
            )
    except TrajectoryValidationError:
        raise
    except (
        AssertionError,
        AttributeError,
        SkillManagerError,
        TypeError,
        ValueError,
    ) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "authoritative Skill declaration could not be reconstructed exactly",
        ) from error
    return rebuilt


def _validated_skill_manager(manager: object) -> SkillManagerService:
    """Reconstruct the complete registry before trusting selections from it."""

    if type(manager) is not SkillManagerService:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "handoff eligibility requires the exact public Skill Manager service",
        )
    try:
        registry = manager.registry
        if type(registry) is not SkillRegistry or type(registry.skills) is not tuple:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SKILL_MISMATCH,
                "authoritative Skill registry failed its public contract",
            )
        rebuilt_registry = SkillRegistry(
            version=registry.version,
            skills=tuple(_rebuilt_skill_definition(skill) for skill in registry.skills),
        )
        rebuilt_manager = SkillManagerService(
            registry=rebuilt_registry,
            safety_kernel=_validated_safety_kernel(manager.safety_kernel),
        )
        if rebuilt_manager != manager:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SKILL_MISMATCH,
                "authoritative Skill registry content does not match its derived identity",
            )
    except TrajectoryValidationError:
        raise
    except (
        AssertionError,
        AttributeError,
        SkillManagerError,
        TypeError,
        ValueError,
    ) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "authoritative Skill registry could not be reconstructed exactly",
        ) from error
    return rebuilt_manager


def _validated_skill_binding_context(
    safety_result: TrajectorySafetyEligibilityResult,
    binding_result: SkillBindingResult,
    manager: SkillManagerService,
) -> tuple[SkillBindingResult, SkillInvocation | None, bool]:
    """Rebuild the complete inert Skill binding from authoritative inputs."""

    if type(binding_result) is not SkillBindingResult:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "handoff eligibility requires exact public Skill Manager contracts",
        )
    rebuilt_manager = _validated_skill_manager(manager)
    try:
        selection = binding_result.selection
        binding_status = binding_result.status
        proposal = safety_result.source_proposal
        safety_decision = safety_result.source_safety_decision
        if rebuilt_manager.safety_kernel != safety_result.source_safety_kernel:
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SAFETY_MISMATCH,
                "Skill Manager Safety policy differs from the reviewed Safety result",
            )
    except AttributeError as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill binding failed its immutable public contract",
        ) from error
    if type(selection) is not SkillSelection:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill binding selection failed its immutable public contract",
        )
    try:
        skill = rebuilt_manager.registry.resolve(selection.skill_id)
        current_selection = rebuilt_manager.registry.selection(
            skill_id=selection.skill_id,
            capability_id=selection.capability_id,
            source_step_id=selection.source_step_id,
        )
    except (
        AssertionError,
        AttributeError,
        SkillManagerError,
        TypeError,
        ValueError,
    ) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill binding registry evidence could not be revalidated",
        ) from error
    try:
        invalid_lineage = (
            current_selection != selection
            or skill is None
            or binding_result.source_safety_decision_id != safety_decision.decision_id
            or selection.capability_id != SAFETY_REVIEW_CAPABILITY_ID
            or selection.source_step_id != SAFETY_REVIEW_STEP_ID
        )
    except AttributeError as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill binding lineage is malformed",
        ) from error
    if invalid_lineage:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill binding is stale, substituted, or cross-composed",
        )

    expected_parameters = trajectory_safety_review_parameters(
        safety_result.trajectory_evidence
    )
    reconstruct_positive = (
        binding_status is BindingStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
    )
    try:
        invocation = binding_result.invocation
        rebuilt_invocation = None
        if invocation is not None:
            if type(invocation) is not SkillInvocation:
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.SKILL_MISMATCH,
                    "Skill invocation failed its immutable public contract",
                )
            rebuilt_invocation = SkillInvocation(
                status=(
                    InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
                    if reconstruct_positive
                    else invocation.status
                ),
                selection=current_selection,
                skill_definition=skill,
                parameters=(
                    expected_parameters
                    if reconstruct_positive
                    else invocation.parameters
                ),
                context_references=(
                    () if reconstruct_positive else invocation.context_references
                ),
                required_approvals=(
                    () if reconstruct_positive else invocation.required_approvals
                ),
                source_request_id=(
                    safety_result.trajectory_evidence.trajectory_evidence_id
                    if reconstruct_positive
                    else invocation.source_request_id
                ),
                source_executive_decision_id=(
                    proposal.decision_id
                    if reconstruct_positive
                    else invocation.source_executive_decision_id
                ),
                source_executive_fingerprint=(
                    proposal.decision_fingerprint
                    if reconstruct_positive
                    else invocation.source_executive_fingerprint
                ),
                source_safety_decision_id=(
                    safety_decision.decision_id
                    if reconstruct_positive
                    else invocation.source_safety_decision_id
                ),
                source_safety_fingerprint=(
                    safety_decision.decision_fingerprint
                    if reconstruct_positive
                    else invocation.source_safety_fingerprint
                ),
                source_proposal_fingerprint=(
                    safety_decision.proposal_fingerprint
                    if reconstruct_positive
                    else invocation.source_proposal_fingerprint
                ),
                source_policy_fingerprint=(
                    safety_decision.policy_fingerprint
                    if reconstruct_positive
                    else invocation.source_policy_fingerprint
                ),
                source_policy_version=(
                    safety_decision.policy_version
                    if reconstruct_positive
                    else invocation.source_policy_version
                ),
            )
        rebuilt_binding = SkillBindingResult(
            status=(
                BindingStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
                if reconstruct_positive
                else binding_status
            ),
            reasons=() if reconstruct_positive else binding_result.reasons,
            selection=current_selection,
            source_safety_decision_id=(
                safety_decision.decision_id
                if reconstruct_positive
                else binding_result.source_safety_decision_id
            ),
            invocation=rebuilt_invocation,
        )
        if (
            rebuilt_binding != binding_result
            or rebuilt_invocation != invocation
            or (
                invocation is not None
                and rebuilt_invocation.parameters != invocation.parameters
            )
        ):
            raise TrajectoryValidationError(
                TrajectoryFailureCode.SKILL_MISMATCH,
                "Skill invocation content or derived identity was modified",
            )
    except TrajectoryValidationError:
        raise
    except (
        AssertionError,
        AttributeError,
        ExecutiveError,
        KeyError,
        SafetyKernelError,
        SkillManagerError,
        TypeError,
        ValueError,
    ) as error:
        raise TrajectoryValidationError(
            TrajectoryFailureCode.SKILL_MISMATCH,
            "Skill invocation could not be reconstructed exactly",
        ) from error

    eligible = (
        rebuilt_binding.status is BindingStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
        and not rebuilt_binding.reasons
        and rebuilt_invocation is not None
        and rebuilt_invocation.status is InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF
        and rebuilt_invocation.skill_definition == skill
        and rebuilt_invocation.selection == selection
        and skill.availability is SkillAvailability.AVAILABLE
        and skill.lifecycle is SkillLifecycle.VALIDATED
        and not skill.required_context
        and not skill.required_resources
        and not skill.required_approval_classes
        and skill.concurrency_policy is ConcurrencyPolicy.PARALLEL
        and skill.idempotency is IdempotencyClass.IDEMPOTENT
        and skill.failure_semantics is FailureSemantics.NON_RETRYABLE
        and rebuilt_invocation.parameters == expected_parameters
        and not rebuilt_invocation.context_references
        and not rebuilt_invocation.required_resources
        and not rebuilt_invocation.required_approvals
        and rebuilt_invocation.backend_id == FUTURE_SKILL_BACKEND_ID
        and rebuilt_invocation.expected_result is ExpectedResultCategory.INFORMATION
        and rebuilt_invocation.safety_classification
        is HazardClass.INTERNAL_NON_ACTUATING
        and rebuilt_invocation.source_request_id
        == safety_result.trajectory_evidence.trajectory_evidence_id
        and rebuilt_invocation.source_executive_decision_id == proposal.decision_id
        and rebuilt_invocation.source_safety_decision_id == safety_decision.decision_id
        and str(rebuilt_invocation.source_executive_fingerprint)
        == safety_result.safety_reference.source_executive_decision_fingerprint
        and str(rebuilt_invocation.source_safety_fingerprint)
        == safety_result.safety_reference.source_safety_decision_fingerprint
        and str(rebuilt_invocation.source_proposal_fingerprint)
        == safety_result.safety_reference.source_proposal_fingerprint
        and str(rebuilt_invocation.source_policy_fingerprint)
        == safety_result.safety_reference.source_policy_fingerprint
        and rebuilt_invocation.source_policy_version
        == safety_result.safety_reference.source_policy_version
    )
    return rebuilt_binding, rebuilt_invocation, eligible


@dataclass(frozen=True, slots=True)
class ExecutionHandoffEligibilityDecision:
    safety_result: TrajectorySafetyEligibilityResult
    status: HandoffEligibilityStatus
    reasons: tuple[HandoffEligibilityReason, ...]
    skill_handoff_reference: SkillRuntimeHandoffReference | None
    source_skill_binding: SkillBindingResult | None = field(default=None, repr=False)
    source_skill_manager: SkillManagerService | None = field(default=None, repr=False)
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
        rebuilt_binding, rebuilt_invocation, skill_eligible = (
            _validated_skill_binding_context(
                self.safety_result,
                self.source_skill_binding,
                self.source_skill_manager,
            )
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
                or not skill_eligible
                or rebuilt_invocation is None
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
            expected_reference = SkillRuntimeHandoffReference(
                source_safety_result_id=self.safety_result.safety_result_id,
                source_safety_result_fingerprint=(
                    self.safety_result.safety_result_fingerprint
                ),
                source_safety_decision_id=(
                    self.safety_result.source_safety_decision.decision_id
                ),
                source_safety_decision_fingerprint=str(
                    self.safety_result.source_safety_decision.decision_fingerprint
                ),
                source_step_id=SAFETY_REVIEW_STEP_ID,
                capability_id=SAFETY_REVIEW_CAPABILITY_ID,
                skill_id=rebuilt_invocation.skill_definition.skill_id,
                skill_version=str(rebuilt_invocation.skill_definition.version),
                skill_fingerprint=str(rebuilt_invocation.skill_definition.fingerprint),
                selection_fingerprint=str(rebuilt_binding.selection.fingerprint),
                invocation_id=rebuilt_invocation.invocation_id,
                invocation_fingerprint=str(rebuilt_invocation.fingerprint),
                backend_id=rebuilt_invocation.backend_id,
                trajectory_binding_fingerprint=trajectory_review_binding_fingerprint(
                    self.safety_result.trajectory_evidence
                ),
            )
            if (
                self.skill_handoff_reference != expected_reference
            ):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.EVIDENCE_MISMATCH,
                    "Skill handoff reference differs from its authoritative binding",
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
            if (
                reasons == (HandoffEligibilityReason.SAFETY_INELIGIBLE,)
                and self.safety_result.status
                is SafetyEligibilityStatus.TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW
            ) or (
                reasons == (HandoffEligibilityReason.SKILL_MANAGER_INELIGIBLE,)
                and (
                    self.safety_result.status
                    is not SafetyEligibilityStatus.TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW
                    or skill_eligible
                )
            ):
                raise TrajectoryValidationError(
                    TrajectoryFailureCode.SKILL_MISMATCH,
                    "ineligible handoff reason contradicts authoritative evidence",
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
            source_skill_binding=value.source_skill_binding,
            source_skill_manager=value.source_skill_manager,
            runtime_endpoint_state=value.runtime_endpoint_state,
            future_runtime_contract_id=value.future_runtime_contract_id,
            execution_disposition=value.execution_disposition,
            physical_validation=value.physical_validation,
        ),
    )
