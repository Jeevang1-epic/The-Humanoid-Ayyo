"""Immutable observations and projected embodied world-state records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
import re
from typing import Mapping, TypeAlias

from .canonical import JSONValue, copy_json, copy_mapping, sha256_document
from .errors import (
    ObservationIdentityError,
    SnapshotIdentityError,
    WorldModelFailureCode,
    WorldModelValidationError,
)


WORLD_MODEL_SCHEMA_VERSION = 1
AYYO_ROBOT_ID = "ayyo.robot.v1"
MAX_OBSERVATION_ITEMS = 128
MAX_ENVIRONMENT_ENTITIES = 256
MAX_OBSERVATION_TIME_NS = (1 << 63) - 1
MAX_SENSOR_IDENTITIES = 32
QUATERNION_NORM_TOLERANCE = 1e-6

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_FRAME = re.compile(r"^[A-Za-z][A-Za-z0-9_/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _invalid(code: WorldModelFailureCode, detail: str) -> None:
    raise WorldModelValidationError(code, detail)


def canonical_identifier(value: object, field_name: str, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _IDENTIFIER.fullmatch(value) is None
    ):
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must be a bounded lowercase ASCII identifier",
        )
    return value


def _frame_id(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 256
        or _FRAME.fullmatch(value) is None
        or "//" in value
        or value.endswith("/")
    ):
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} is not a bounded canonical frame identifier",
        )
    return value


def _finite(value: object, field_name: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must be a finite real number",
        )
    return float(value)


def _vector(
    value: object,
    field_name: str,
    *,
    dimension: int,
) -> tuple[float, ...]:
    if type(value) is not tuple or len(value) != dimension:
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must contain exactly {dimension} values",
        )
    return tuple(_finite(item, field_name) for item in value)


def _quaternion(value: object, field_name: str) -> tuple[float, float, float, float]:
    raw = _vector(value, field_name, dimension=4)
    norm = math.sqrt(sum(item * item for item in raw))
    if norm == 0.0 or abs(norm - 1.0) > QUATERNION_NORM_TOLERANCE:
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must be a normalized non-zero quaternion",
        )
    normalized = tuple(item / norm for item in raw)
    # q and -q encode the same rotation. Select one representation so semantic
    # identity does not depend on a producer's quaternion sign convention.
    for item in reversed(normalized):
        if item == 0.0:
            continue
        if item < 0.0:
            normalized = tuple(-component for component in normalized)
        break
    canonical = tuple(0.0 if component == 0.0 else component for component in normalized)
    return canonical  # type: ignore[return-value]


def _confidence(value: object) -> float:
    result = _finite(value, "confidence")
    if not 0.0 <= result <= 1.0:
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            "confidence must be between 0.0 and 1.0",
        )
    return result


class ObservationSourceKind(StrEnum):
    SIMULATION = "simulation"
    PHYSICAL_SENSOR = "physical_sensor"
    RECORDED_DATA = "recorded_data"
    TEST_FIXTURE = "test_fixture"


class ObservationClock(StrEnum):
    ROS_SIMULATION_TIME = "ros_simulation_time"
    ROS_SYSTEM_TIME = "ros_system_time"
    RECORDED_TIME = "recorded_time"
    TEST_TIME = "test_time"


class ObservationTransport(StrEnum):
    ROS2 = "ros2"
    DIRECT = "direct"
    RECORDED = "recorded"


class SensorKind(StrEnum):
    JOINT_STATE = "joint_state"
    IMU = "imu"
    BODY_POSE = "body_pose"


class SensorAvailability(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    ERROR = "error"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


_CLOCK_BY_SOURCE = {
    ObservationSourceKind.SIMULATION: ObservationClock.ROS_SIMULATION_TIME,
    ObservationSourceKind.PHYSICAL_SENSOR: ObservationClock.ROS_SYSTEM_TIME,
    ObservationSourceKind.RECORDED_DATA: ObservationClock.RECORDED_TIME,
    ObservationSourceKind.TEST_FIXTURE: ObservationClock.TEST_TIME,
}


@dataclass(frozen=True, slots=True)
class ObservationProvenance:
    source_kind: ObservationSourceKind
    source_id: str
    clock: ObservationClock
    transport: ObservationTransport
    interface: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, ObservationSourceKind):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "source_kind must be an ObservationSourceKind",
            )
        if not isinstance(self.clock, ObservationClock):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "clock must be an ObservationClock",
            )
        if not isinstance(self.transport, ObservationTransport):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "transport must be an ObservationTransport",
            )
        try:
            canonical_identifier(self.source_id, "provenance source_id")
            canonical_identifier(self.interface, "provenance interface")
        except WorldModelValidationError as error:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                error.detail,
            ) from error
        if self.clock is not _CLOCK_BY_SOURCE[self.source_kind]:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "source kind and source clock do not match",
            )
        if (
            self.source_kind is ObservationSourceKind.RECORDED_DATA
            and self.transport is not ObservationTransport.RECORDED
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "recorded evidence must use the recorded transport",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "clock": self.clock.value,
            "interface": self.interface,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "transport": self.transport.value,
        }


@dataclass(frozen=True, slots=True)
class SensorIdentity:
    sensor_id: str
    kind: SensorKind
    frame_id: str

    def __post_init__(self) -> None:
        canonical_identifier(self.sensor_id, "sensor_id")
        if not isinstance(self.kind, SensorKind):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "sensor kind must be a SensorKind",
            )
        _frame_id(self.frame_id, "sensor frame_id")

    def document(self) -> dict[str, JSONValue]:
        return {
            "frame_id": self.frame_id,
            "kind": self.kind.value,
            "sensor_id": self.sensor_id,
        }


@dataclass(frozen=True, slots=True)
class CovarianceMatrix:
    """A supplied 3x3 or 6x6 covariance; absence is represented by None."""

    dimension: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if type(self.dimension) is not int or self.dimension not in {3, 6}:
            _invalid(
                WorldModelFailureCode.MALFORMED_COVARIANCE,
                "covariance dimension must be exactly three or six",
            )
        if type(self.values) is not tuple or len(self.values) != self.dimension**2:
            _invalid(
                WorldModelFailureCode.MALFORMED_COVARIANCE,
                "covariance value count does not match its square dimension",
            )
        try:
            values = tuple(_finite(item, "covariance value") for item in self.values)
        except WorldModelValidationError as error:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_COVARIANCE,
                error.detail,
            ) from error
        for row in range(self.dimension):
            diagonal = values[row * self.dimension + row]
            if diagonal < 0.0:
                _invalid(
                    WorldModelFailureCode.MALFORMED_COVARIANCE,
                    "covariance diagonal cannot contain negative variance",
                )
            for column in range(row + 1, self.dimension):
                left = values[row * self.dimension + column]
                right = values[column * self.dimension + row]
                scale = max(1.0, abs(left), abs(right))
                if abs(left - right) > 1e-9 * scale:
                    _invalid(
                        WorldModelFailureCode.MALFORMED_COVARIANCE,
                        "covariance matrix must be symmetric",
                    )
        # A covariance must be positive semidefinite. A bounded LDLᵀ check is
        # dependency-free and accepts zero-variance axes only when their
        # remaining coupled residual is also zero within numerical tolerance.
        scale = max(1.0, *(abs(value) for value in values))
        tolerance = 1e-12 * scale
        lower = [[0.0] * self.dimension for _ in range(self.dimension)]
        diagonal = [0.0] * self.dimension
        for row in range(self.dimension):
            lower[row][row] = 1.0
            for column in range(row):
                residual = values[row * self.dimension + column] - sum(
                    lower[row][index]
                    * diagonal[index]
                    * lower[column][index]
                    for index in range(column)
                )
                if abs(diagonal[column]) <= tolerance:
                    if abs(residual) > tolerance:
                        _invalid(
                            WorldModelFailureCode.MALFORMED_COVARIANCE,
                            "covariance matrix is not positive semidefinite",
                        )
                    lower[row][column] = 0.0
                else:
                    lower[row][column] = residual / diagonal[column]
            pivot = values[row * self.dimension + row] - sum(
                lower[row][index] ** 2 * diagonal[index]
                for index in range(row)
            )
            if pivot < -tolerance:
                _invalid(
                    WorldModelFailureCode.MALFORMED_COVARIANCE,
                    "covariance matrix is not positive semidefinite",
                )
            diagonal[row] = 0.0 if abs(pivot) <= tolerance else pivot
        object.__setattr__(self, "values", values)

    def document(self) -> dict[str, JSONValue]:
        return {"dimension": self.dimension, "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class Pose3D:
    frame_id: str
    child_frame_id: str
    position_xyz: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _frame_id(self.frame_id, "pose frame_id")
        _frame_id(self.child_frame_id, "pose child_frame_id")
        if self.frame_id == self.child_frame_id:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "pose frames must be distinct",
            )
        position = _vector(self.position_xyz, "pose position", dimension=3)
        orientation = _quaternion(self.orientation_xyzw, "pose orientation")
        object.__setattr__(self, "position_xyz", position)
        object.__setattr__(self, "orientation_xyzw", orientation)

    def document(self) -> dict[str, JSONValue]:
        return {
            "child_frame_id": self.child_frame_id,
            "frame_id": self.frame_id,
            "orientation_xyzw": list(self.orientation_xyzw),
            "position_xyz": list(self.position_xyz),
        }


@dataclass(frozen=True, slots=True)
class JointObservation:
    joint_name: str
    position: float
    velocity: float | None = None
    effort: float | None = None

    def __post_init__(self) -> None:
        canonical_identifier(self.joint_name, "joint_name")
        object.__setattr__(self, "position", _finite(self.position, "joint position"))
        if self.velocity is not None:
            object.__setattr__(
                self,
                "velocity",
                _finite(self.velocity, "joint velocity"),
            )
        if self.effort is not None:
            object.__setattr__(self, "effort", _finite(self.effort, "joint effort"))

    def document(self) -> dict[str, JSONValue]:
        return {
            "effort": self.effort,
            "joint_name": self.joint_name,
            "position": self.position,
            "velocity": self.velocity,
        }


class WorldEntityKind(StrEnum):
    OBJECT = "object"
    PERSON = "person"
    SURFACE = "surface"
    LANDMARK = "landmark"
    OBSTACLE = "obstacle"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WorldEntityIdentity:
    entity_id: str
    kind: WorldEntityKind

    def __post_init__(self) -> None:
        canonical_identifier(self.entity_id, "entity_id")
        if not isinstance(self.kind, WorldEntityKind):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "entity kind must be a WorldEntityKind",
            )


class ObservationFingerprintKind(StrEnum):
    ROBOT_STATE = "robot_state"
    IMU = "imu"
    BODY_POSE = "body_pose"
    SENSOR_HEALTH = "sensor_health"
    ENVIRONMENT_ENTITY = "environment_entity"


@dataclass(frozen=True, slots=True)
class ObservationFingerprint:
    kind: ObservationFingerprintKind
    digest: str
    algorithm: str = "sha256"
    schema_version: int = WORLD_MODEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObservationFingerprintKind):
            _invalid(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "observation fingerprint kind is invalid",
            )
        if self.algorithm != "sha256" or self.schema_version != WORLD_MODEL_SCHEMA_VERSION:
            _invalid(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "observation fingerprint format is unsupported",
            )
        if type(self.digest) is not str or _SHA256.fullmatch(self.digest) is None:
            _invalid(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "observation fingerprint digest is malformed",
            )

    def __str__(self) -> str:
        return f"{self.kind.value}:sha256:{self.digest}"


def _observation_document(
    *,
    kind: ObservationFingerprintKind,
    robot_id: str,
    observed_at_ns: int,
    provenance: ObservationProvenance,
    confidence: float | None,
    payload: dict[str, JSONValue],
) -> dict[str, JSONValue]:
    return {
        "confidence": confidence,
        "kind": kind.value,
        "observed_at_ns": observed_at_ns,
        "payload": payload,
        "provenance": provenance.document(),
        "robot_id": robot_id,
        "schema": "ayyo.world-model.observation.v1",
    }


@dataclass(frozen=True, slots=True, init=False)
class RobotStateObservation:
    robot_id: str
    joints: tuple[JointObservation, ...]
    base_pose: Pose3D | None
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        joints: tuple[JointObservation, ...],
        observed_at_ns: int,
        provenance: ObservationProvenance,
        confidence: float,
        base_pose: Pose3D | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(joints) is not tuple or len(joints) > MAX_OBSERVATION_ITEMS:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "robot observation joint collection is invalid or oversized",
            )
        if not joints and base_pose is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "robot observation must contain a joint or base pose",
            )
        if any(type(joint) is not JointObservation for joint in joints):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "robot observation joints must be typed JointObservation values",
            )
        canonical_joints = tuple(sorted(joints, key=lambda item: item.joint_name))
        if len({item.joint_name for item in canonical_joints}) != len(canonical_joints):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "robot observation contains duplicate joint names",
            )
        if base_pose is not None and type(base_pose) is not Pose3D:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "base_pose must be a Pose3D when provided",
            )
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "observation provenance is required",
            )
        confidence_value = _confidence(confidence)
        document = _observation_document(
            kind=ObservationFingerprintKind.ROBOT_STATE,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=confidence_value,
            payload={
                "base_pose": None if base_pose is None else base_pose.document(),
                "joints": [joint.document() for joint in canonical_joints],
            },
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.ROBOT_STATE,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "robot observation fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "robot observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "joints", canonical_joints)
        object.__setattr__(self, "base_pose", base_pose)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "confidence", confidence_value)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)


@dataclass(frozen=True, slots=True, init=False)
class ImuObservation:
    robot_id: str
    sensor: SensorIdentity
    orientation_xyzw: tuple[float, float, float, float] | None
    orientation_covariance: CovarianceMatrix | None
    angular_velocity_xyz: tuple[float, float, float] | None
    angular_velocity_covariance: CovarianceMatrix | None
    linear_acceleration_xyz: tuple[float, float, float] | None
    linear_acceleration_covariance: CovarianceMatrix | None
    observed_at_ns: int
    provenance: ObservationProvenance
    availability: SensorAvailability
    quality: float | None
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        observed_at_ns: int,
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        orientation_xyzw: tuple[float, float, float, float] | None = None,
        orientation_covariance: CovarianceMatrix | None = None,
        angular_velocity_xyz: tuple[float, float, float] | None = None,
        angular_velocity_covariance: CovarianceMatrix | None = None,
        linear_acceleration_xyz: tuple[float, float, float] | None = None,
        linear_acceleration_covariance: CovarianceMatrix | None = None,
        quality: float | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(sensor) is not SensorIdentity or sensor.kind is not SensorKind.IMU:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "IMU evidence requires a typed IMU sensor identity",
            )
        orientation = (
            None
            if orientation_xyzw is None
            else _quaternion(orientation_xyzw, "IMU orientation")
        )
        angular_velocity = (
            None
            if angular_velocity_xyz is None
            else _vector(angular_velocity_xyz, "IMU angular velocity", dimension=3)
        )
        linear_acceleration = (
            None
            if linear_acceleration_xyz is None
            else _vector(
                linear_acceleration_xyz,
                "IMU linear acceleration",
                dimension=3,
            )
        )
        covariance_pairs = (
            (orientation, orientation_covariance, "orientation"),
            (angular_velocity, angular_velocity_covariance, "angular velocity"),
            (linear_acceleration, linear_acceleration_covariance, "linear acceleration"),
        )
        for estimate, covariance, field_name in covariance_pairs:
            if covariance is not None and (
                type(covariance) is not CovarianceMatrix or covariance.dimension != 3
            ):
                _invalid(
                    WorldModelFailureCode.MALFORMED_COVARIANCE,
                    f"IMU {field_name} covariance must be a 3x3 covariance",
                )
            if covariance is not None and estimate is None:
                _invalid(
                    WorldModelFailureCode.MALFORMED_COVARIANCE,
                    f"IMU {field_name} covariance cannot exist without an estimate",
                )
        if all(value is None for value in (orientation, angular_velocity, linear_acceleration)):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "IMU evidence must contain at least one supplied estimate",
            )
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "IMU provenance is required",
            )
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "measurement-bearing IMU evidence must be available or degraded",
            )
        quality_value = None if quality is None else _confidence(quality)
        payload: dict[str, JSONValue] = {
            "angular_velocity_covariance": (
                None
                if angular_velocity_covariance is None
                else angular_velocity_covariance.document()
            ),
            "angular_velocity_xyz": (
                None if angular_velocity is None else list(angular_velocity)
            ),
            "availability": availability.value,
            "linear_acceleration_covariance": (
                None
                if linear_acceleration_covariance is None
                else linear_acceleration_covariance.document()
            ),
            "linear_acceleration_xyz": (
                None if linear_acceleration is None else list(linear_acceleration)
            ),
            "orientation_covariance": (
                None
                if orientation_covariance is None
                else orientation_covariance.document()
            ),
            "orientation_xyzw": None if orientation is None else list(orientation),
            "quality": quality_value,
            "sensor": sensor.document(),
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.IMU,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=quality_value,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.IMU,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "IMU observation fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "IMU observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "orientation_xyzw", orientation)
        object.__setattr__(self, "orientation_covariance", orientation_covariance)
        object.__setattr__(self, "angular_velocity_xyz", angular_velocity)
        object.__setattr__(self, "angular_velocity_covariance", angular_velocity_covariance)
        object.__setattr__(self, "linear_acceleration_xyz", linear_acceleration)
        object.__setattr__(self, "linear_acceleration_covariance", linear_acceleration_covariance)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "quality", quality_value)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)

    def payload_document(self) -> dict[str, JSONValue]:
        return {
            "angular_velocity_covariance": (
                None
                if self.angular_velocity_covariance is None
                else self.angular_velocity_covariance.document()
            ),
            "angular_velocity_xyz": (
                None
                if self.angular_velocity_xyz is None
                else list(self.angular_velocity_xyz)
            ),
            "availability": self.availability.value,
            "linear_acceleration_covariance": (
                None
                if self.linear_acceleration_covariance is None
                else self.linear_acceleration_covariance.document()
            ),
            "linear_acceleration_xyz": (
                None
                if self.linear_acceleration_xyz is None
                else list(self.linear_acceleration_xyz)
            ),
            "orientation_covariance": (
                None
                if self.orientation_covariance is None
                else self.orientation_covariance.document()
            ),
            "orientation_xyzw": (
                None if self.orientation_xyzw is None else list(self.orientation_xyzw)
            ),
            "quality": self.quality,
            "sensor": self.sensor.document(),
        }


@dataclass(frozen=True, slots=True, init=False)
class BodyPoseObservation:
    robot_id: str
    sensor: SensorIdentity
    pose: Pose3D
    covariance: CovarianceMatrix | None
    observed_at_ns: int
    provenance: ObservationProvenance
    availability: SensorAvailability
    quality: float | None
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        pose: Pose3D,
        observed_at_ns: int,
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        covariance: CovarianceMatrix | None = None,
        quality: float | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(sensor) is not SensorIdentity or sensor.kind is not SensorKind.BODY_POSE:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "body-pose evidence requires a typed body-pose source identity",
            )
        if type(pose) is not Pose3D or pose.child_frame_id != sensor.frame_id:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "body-pose target frame must match its reviewed sensor contract",
            )
        if covariance is not None and (
            type(covariance) is not CovarianceMatrix or covariance.dimension != 6
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_COVARIANCE,
                "body pose covariance must be a 6x6 covariance",
            )
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.MALFORMED_PROVENANCE, "pose provenance is required")
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "measurement-bearing pose evidence must be available or degraded",
            )
        quality_value = None if quality is None else _confidence(quality)
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "covariance": None if covariance is None else covariance.document(),
            "pose": pose.document(),
            "quality": quality_value,
            "sensor": sensor.document(),
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.BODY_POSE,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=quality_value,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.BODY_POSE,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "body-pose fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "body-pose observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "pose", pose)
        object.__setattr__(self, "covariance", covariance)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "quality", quality_value)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)


@dataclass(frozen=True, slots=True, init=False)
class SensorHealthObservation:
    robot_id: str
    sensor: SensorIdentity
    availability: SensorAvailability
    observed_at_ns: int
    provenance: ObservationProvenance
    evidence_detail: str
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        availability: SensorAvailability,
        observed_at_ns: int,
        provenance: ObservationProvenance,
        evidence_detail: str = "",
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(sensor) is not SensorIdentity:
            _invalid(WorldModelFailureCode.MALFORMED_OBSERVATION, "sensor identity is required")
        if not isinstance(availability, SensorAvailability):
            _invalid(WorldModelFailureCode.MALFORMED_OBSERVATION, "sensor availability is invalid")
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.MALFORMED_PROVENANCE, "health provenance is required")
        if (
            type(evidence_detail) is not str
            or len(evidence_detail) > 1_024
            or "\x00" in evidence_detail
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "sensor health detail must be bounded text",
            )
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "evidence_detail": evidence_detail,
            "sensor": sensor.document(),
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.SENSOR_HEALTH,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=None,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.SENSOR_HEALTH,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "health fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "health observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "evidence_detail", evidence_detail)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)


@dataclass(frozen=True, slots=True, init=False)
class EnvironmentEntityObservation:
    robot_id: str
    entity: WorldEntityIdentity
    pose: Pose3D | None
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float
    observation_id: str
    fingerprint: ObservationFingerprint
    _properties: JSONValue = field(repr=False, compare=False)
    _canonical_properties: str = field(repr=False)

    def __init__(
        self,
        *,
        robot_id: str,
        entity: WorldEntityIdentity,
        properties: Mapping[str, JSONValue],
        observed_at_ns: int,
        provenance: ObservationProvenance,
        confidence: float,
        pose: Pose3D | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(entity) is not WorldEntityIdentity:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "environment observation entity must be typed",
            )
        if pose is not None and type(pose) is not Pose3D:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "environment pose must be a Pose3D when provided",
            )
        copied = copy_mapping(properties, field_name="environment properties")
        if not copied and pose is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "environment observation must contain bounded evidence",
            )
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "observation provenance is required",
            )
        confidence_value = _confidence(confidence)
        document = _observation_document(
            kind=ObservationFingerprintKind.ENVIRONMENT_ENTITY,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=confidence_value,
            payload={
                "entity_id": entity.entity_id,
                "entity_kind": entity.kind.value,
                "pose": None if pose is None else pose.document(),
                "properties": copied,
            },
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.ENVIRONMENT_ENTITY,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "environment observation fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "environment observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "entity", entity)
        object.__setattr__(self, "pose", pose)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "confidence", confidence_value)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)
        object.__setattr__(self, "_properties", copied)
        object.__setattr__(self, "_canonical_properties", sha256_document(copied))

    @property
    def properties(self) -> dict[str, JSONValue]:
        copied = copy_json(self._properties, field_name="environment properties")
        assert type(copied) is dict
        return copied


Observation: TypeAlias = (
    RobotStateObservation
    | ImuObservation
    | BodyPoseObservation
    | SensorHealthObservation
    | EnvironmentEntityObservation
)


def rebuild_observation(observation: Observation) -> Observation:
    if type(observation) is RobotStateObservation:
        return RobotStateObservation(
            robot_id=observation.robot_id,
            joints=observation.joints,
            base_pose=observation.base_pose,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            confidence=observation.confidence,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is EnvironmentEntityObservation:
        return EnvironmentEntityObservation(
            robot_id=observation.robot_id,
            entity=observation.entity,
            pose=observation.pose,
            properties=observation.properties,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            confidence=observation.confidence,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is ImuObservation:
        return ImuObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            orientation_xyzw=observation.orientation_xyzw,
            orientation_covariance=observation.orientation_covariance,
            angular_velocity_xyz=observation.angular_velocity_xyz,
            angular_velocity_covariance=observation.angular_velocity_covariance,
            linear_acceleration_xyz=observation.linear_acceleration_xyz,
            linear_acceleration_covariance=observation.linear_acceleration_covariance,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            quality=observation.quality,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is BodyPoseObservation:
        return BodyPoseObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            pose=observation.pose,
            covariance=observation.covariance,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            quality=observation.quality,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is SensorHealthObservation:
        return SensorHealthObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            availability=observation.availability,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            evidence_detail=observation.evidence_detail,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    _invalid(
        WorldModelFailureCode.MALFORMED_OBSERVATION,
        "observation has an unsupported concrete type",
    )


class FreshnessState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"


class RobotAvailability(StrEnum):
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    AVAILABLE = "available"


@dataclass(frozen=True, slots=True)
class ObservedJointState:
    joint: JointObservation
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float
    freshness: FreshnessState
    observation_id: str
    observation_fingerprint: ObservationFingerprint

    def __post_init__(self) -> None:
        if type(self.joint) is not JointObservation:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint state is untyped")
        if (
            type(self.observed_at_ns) is not int
            or not 0 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint time is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint provenance is invalid")
        _confidence(self.confidence)
        if not isinstance(self.freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint freshness is invalid")
        if not self.observation_id.startswith("world-observation-"):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint evidence ID is invalid")
        if type(self.observation_fingerprint) is not ObservationFingerprint:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "joint evidence fingerprint is invalid",
            )
        if self.observation_id.removeprefix("world-observation-") != (
            self.observation_fingerprint.digest
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "joint evidence ID and fingerprint disagree",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "confidence": self.confidence,
            "freshness": self.freshness.value,
            "joint": self.joint.document(),
            "observation_fingerprint": str(self.observation_fingerprint),
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "provenance": self.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedPoseState:
    pose: Pose3D
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float | None
    freshness: FreshnessState
    observation_id: str
    sensor: SensorIdentity | None = None
    covariance: CovarianceMatrix | None = None
    availability: SensorAvailability = SensorAvailability.AVAILABLE
    observation_fingerprint: ObservationFingerprint | None = None

    def __post_init__(self) -> None:
        if type(self.pose) is not Pose3D:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose state is untyped")
        if (
            type(self.observed_at_ns) is not int
            or not 0 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose time is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose provenance is invalid")
        if self.confidence is not None:
            _confidence(self.confidence)
        if not isinstance(self.freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose freshness is invalid")
        if (
            type(self.observation_id) is not str
            or re.fullmatch(r"world-observation-[0-9a-f]{64}", self.observation_id)
            is None
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose evidence ID is invalid")
        if self.sensor is not None and (
            type(self.sensor) is not SensorIdentity
            or self.sensor.kind is not SensorKind.BODY_POSE
            or self.pose.child_frame_id != self.sensor.frame_id
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose sensor is invalid")
        if self.covariance is not None and (
            type(self.covariance) is not CovarianceMatrix
            or self.covariance.dimension != 6
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose covariance is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose availability is invalid")
        if self.observation_fingerprint is not None:
            if type(self.observation_fingerprint) is not ObservationFingerprint:
                _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose fingerprint is invalid")
            if self.observation_id.removeprefix("world-observation-") != (
                self.observation_fingerprint.digest
            ):
                _invalid(
                    WorldModelFailureCode.SNAPSHOT_INVARIANT,
                    "pose evidence ID and fingerprint disagree",
                )

    def document(self) -> dict[str, JSONValue]:
        return {
            "confidence": self.confidence,
            "freshness": self.freshness.value,
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "pose": self.pose.document(),
            "provenance": self.provenance.document(),
            "sensor": None if self.sensor is None else self.sensor.document(),
            "covariance": (
                None if self.covariance is None else self.covariance.document()
            ),
            "availability": self.availability.value,
            "observation_fingerprint": (
                None
                if self.observation_fingerprint is None
                else str(self.observation_fingerprint)
            ),
        }


@dataclass(frozen=True, slots=True)
class ObservedImuState:
    observation: ImuObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not ImuObservation:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU state is untyped")
        if not isinstance(self.freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU freshness is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU availability is invalid")
        if self.freshness is FreshnessState.STALE and (
            self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale IMU evidence must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "payload": self.observation.payload_document(),
            "provenance": self.observation.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class SensorAvailabilityState:
    sensor: SensorIdentity
    availability: SensorAvailability
    observed_at_ns: int | None
    provenance: ObservationProvenance | None
    observation_id: str | None

    def __post_init__(self) -> None:
        if type(self.sensor) is not SensorIdentity:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor state identity is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor state is invalid")
        evidence = (self.observed_at_ns, self.provenance, self.observation_id)
        if self.availability is SensorAvailability.UNAVAILABLE and all(
            item is None for item in evidence
        ):
            return
        if any(item is None for item in evidence):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "evidence-backed sensor state requires complete provenance",
            )
        if type(self.observed_at_ns) is not int or not 0 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor state time is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor state provenance is invalid")
        if (
            type(self.observation_id) is not str
            or re.fullmatch(r"world-observation-[0-9a-f]{64}", self.observation_id)
            is None
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor evidence ID is invalid")

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "provenance": None if self.provenance is None else self.provenance.document(),
            "sensor": self.sensor.document(),
        }


@dataclass(frozen=True, slots=True)
class RobotBodyState:
    robot_id: str
    known_joint_names: tuple[str, ...]
    joints: tuple[ObservedJointState, ...]
    base_pose: ObservedPoseState | None
    availability: RobotAvailability
    imu_states: tuple[ObservedImuState, ...] = ()
    sensor_states: tuple[SensorAvailabilityState, ...] = ()

    def __post_init__(self) -> None:
        canonical_identifier(self.robot_id, "robot body identity")
        expected = tuple(sorted(set(self.known_joint_names)))
        if self.known_joint_names != expected:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "known joints must be unique and sorted",
            )
        for joint_name in self.known_joint_names:
            canonical_identifier(joint_name, "known joint name")
        if any(type(item) is not ObservedJointState for item in self.joints):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "robot joints must be ObservedJointState values",
            )
        if self.base_pose is not None and type(self.base_pose) is not ObservedPoseState:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "robot base pose must be an ObservedPoseState",
            )
        actual = tuple(item.joint.joint_name for item in self.joints)
        if actual != tuple(sorted(set(actual))) or not set(actual) <= set(expected):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "observed joints must be unique, sorted, and known",
            )
        expected_availability = (
            RobotAvailability.UNAVAILABLE
            if not actual
            else RobotAvailability.AVAILABLE
            if len(actual) == len(expected)
            else RobotAvailability.PARTIAL
        )
        if self.availability is not expected_availability:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "body availability does not match observed joint coverage",
            )
        if any(type(item) is not ObservedImuState for item in self.imu_states):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU states must be typed")
        imu_ids = tuple(item.observation.sensor.sensor_id for item in self.imu_states)
        if imu_ids != tuple(sorted(set(imu_ids))):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU states must be unique and sorted")
        if any(type(item) is not SensorAvailabilityState for item in self.sensor_states):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor states must be typed")
        sensor_ids = tuple(item.sensor.sensor_id for item in self.sensor_states)
        if sensor_ids != tuple(sorted(set(sensor_ids))):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor states must be unique and sorted")

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "base_pose": None if self.base_pose is None else self.base_pose.document(),
            "joints": [item.document() for item in self.joints],
            "known_joint_names": list(self.known_joint_names),
            "robot_id": self.robot_id,
            "imu_states": [item.document() for item in self.imu_states],
            "sensor_states": [item.document() for item in self.sensor_states],
        }


@dataclass(frozen=True, slots=True, init=False)
class WorldEntity:
    identity: WorldEntityIdentity
    pose: Pose3D | None
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float
    freshness: FreshnessState
    observation_id: str
    _properties: JSONValue = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        identity: WorldEntityIdentity,
        pose: Pose3D | None,
        properties: Mapping[str, JSONValue],
        observed_at_ns: int,
        provenance: ObservationProvenance,
        confidence: float,
        freshness: FreshnessState,
        observation_id: str,
    ) -> None:
        if type(identity) is not WorldEntityIdentity:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity identity is invalid")
        if pose is not None and type(pose) is not Pose3D:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity pose is invalid")
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity time is invalid")
        if type(provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity provenance is invalid")
        copied = copy_mapping(properties, field_name="world entity properties")
        if not isinstance(freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity freshness is invalid")
        if (
            type(observation_id) is not str
            or re.fullmatch(r"world-observation-[0-9a-f]{64}", observation_id) is None
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity evidence ID is invalid")
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "pose", pose)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "confidence", _confidence(confidence))
        object.__setattr__(self, "freshness", freshness)
        object.__setattr__(self, "observation_id", observation_id)
        object.__setattr__(self, "_properties", copied)

    @property
    def properties(self) -> dict[str, JSONValue]:
        copied = copy_json(self._properties, field_name="world entity properties")
        assert type(copied) is dict
        return copied

    def document(self) -> dict[str, JSONValue]:
        return {
            "confidence": self.confidence,
            "entity_id": self.identity.entity_id,
            "entity_kind": self.identity.kind.value,
            "freshness": self.freshness.value,
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "pose": None if self.pose is None else self.pose.document(),
            "properties": self.properties,
            "provenance": self.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class WorldModelVersion:
    digest: str
    algorithm: str = "sha256"
    schema_version: int = WORLD_MODEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.algorithm != "sha256" or self.schema_version != WORLD_MODEL_SCHEMA_VERSION:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot version is unsupported")
        if type(self.digest) is not str or _SHA256.fullmatch(self.digest) is None:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot digest is malformed")

    def __str__(self) -> str:
        return f"world_snapshot:sha256:{self.digest}"


@dataclass(frozen=True, slots=True, init=False)
class WorldSnapshot:
    snapshot_id: str
    captured_at_ns: int
    robot: RobotBodyState
    entities: tuple[WorldEntity, ...]
    version: WorldModelVersion

    def __init__(
        self,
        *,
        captured_at_ns: int,
        robot: RobotBodyState,
        entities: tuple[WorldEntity, ...],
        snapshot_id: str | None = None,
        version: WorldModelVersion | None = None,
    ) -> None:
        if (
            type(captured_at_ns) is not int
            or not 0 <= captured_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot time is invalid")
        if type(robot) is not RobotBodyState:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot robot state is invalid")
        if type(entities) is not tuple or len(entities) > MAX_ENVIRONMENT_ENTITIES:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot entities are invalid")
        if any(type(item) is not WorldEntity for item in entities):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "snapshot entities must be typed WorldEntity values",
            )
        ordered = tuple(sorted(entities, key=lambda item: item.identity.entity_id))
        if len({item.identity.entity_id for item in ordered}) != len(ordered):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot entity IDs repeat")
        document: dict[str, JSONValue] = {
            "entities": [item.document() for item in ordered],
            "robot": robot.document(),
            "schema": "ayyo.world-model.snapshot.v1",
        }
        derived = WorldModelVersion(sha256_document(document))
        derived_id = f"world-snapshot-{derived.digest}"
        if version is not None and version != derived:
            raise SnapshotIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "snapshot version does not match world state",
            )
        if snapshot_id is not None and snapshot_id != derived_id:
            raise SnapshotIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "snapshot ID does not match world state",
            )
        object.__setattr__(self, "captured_at_ns", captured_at_ns)
        object.__setattr__(self, "robot", robot)
        object.__setattr__(self, "entities", ordered)
        object.__setattr__(self, "version", derived)
        object.__setattr__(self, "snapshot_id", derived_id)

    def get_entity(self, entity_id: str) -> WorldEntity | None:
        canonical_identifier(entity_id, "entity query")
        return next(
            (entity for entity in self.entities if entity.identity.entity_id == entity_id),
            None,
        )


def rebuild_snapshot(snapshot: WorldSnapshot) -> WorldSnapshot:
    if type(snapshot) is not WorldSnapshot:
        _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot has an unsupported type")
    return WorldSnapshot(
        captured_at_ns=snapshot.captured_at_ns,
        robot=snapshot.robot,
        entities=snapshot.entities,
        snapshot_id=snapshot.snapshot_id,
        version=snapshot.version,
    )
