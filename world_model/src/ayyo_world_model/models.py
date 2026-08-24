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
        if type(self.position_xyz) is not tuple or len(self.position_xyz) != 3:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "pose position_xyz must contain exactly three values",
            )
        if type(self.orientation_xyzw) is not tuple or len(self.orientation_xyzw) != 4:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "pose orientation_xyzw must contain exactly four values",
            )
        position = tuple(_finite(item, "pose position") for item in self.position_xyz)
        orientation = tuple(
            _finite(item, "pose orientation") for item in self.orientation_xyzw
        )
        norm = math.sqrt(sum(item * item for item in orientation))
        if abs(norm - 1.0) > 1e-6:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "pose orientation must be a normalized quaternion",
            )
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
    confidence: float,
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


Observation: TypeAlias = RobotStateObservation | EnvironmentEntityObservation


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
    confidence: float
    freshness: FreshnessState
    observation_id: str

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
        _confidence(self.confidence)
        if not isinstance(self.freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose freshness is invalid")
        if (
            type(self.observation_id) is not str
            or re.fullmatch(r"world-observation-[0-9a-f]{64}", self.observation_id)
            is None
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose evidence ID is invalid")

    def document(self) -> dict[str, JSONValue]:
        return {
            "confidence": self.confidence,
            "freshness": self.freshness.value,
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "pose": self.pose.document(),
            "provenance": self.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class RobotBodyState:
    robot_id: str
    known_joint_names: tuple[str, ...]
    joints: tuple[ObservedJointState, ...]
    base_pose: ObservedPoseState | None
    availability: RobotAvailability

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

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "base_pose": None if self.base_pose is None else self.base_pose.document(),
            "joints": [item.document() for item in self.joints],
            "known_joint_names": list(self.known_joint_names),
            "robot_id": self.robot_id,
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
