"""Immutable Stage 9D simulation-only grasp interaction contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import acos, sqrt

from ayyo_manipulation_simulation_execution import (
    DEFAULT_STATE_FRESHNESS_NS,
    SimulationExecutionRequest,
    SimulationExecutionResult,
    SimulationExecutionResultStatus,
    SimulationMotionStatus,
    SimulationStabilityObservation,
    StabilityStatus,
    expected_dense_samples,
    verify_execution_request,
    verify_execution_result,
    verify_stability_observation,
)

from .canonical import (
    JSONValue,
    SCHEMA_VERSION,
    assert_artifact_size,
    bounded_integer,
    bounded_text,
    content_identity,
    finite_float,
    fingerprint,
    identifier,
    semantic_fingerprint,
)
from .errors import GraspInteractionFailureCode, GraspInteractionValidationError


STAGE9D_PROFILE_ID = "development.stage9d.left-hand-grasp-interaction.v1"
STAGE9D_ROBOT_NAME = "ayyo"
STAGE9D_END_EFFECTOR_LINK = "left_hand_link"
STAGE9D_END_EFFECTOR_FRAME = "left_hand_link"
STAGE9D_END_EFFECTOR_ENTITY = "ayyo::left_hand_link"
STAGE9D_END_EFFECTOR_COLLISION = "ayyo::left_hand_link::collision"
STAGE9D_FIXTURE_ID = "ayyo.stage9d.contact-gated-fixed-constraint.v1"
STAGE9D_FIXTURE_VERSION = "1.0.0"
STAGE9D_FIXTURE_STATE_TOPIC = "/ayyo/stage9d/grasp_fixture/state"
STAGE9D_FIXTURE_ATTACH_TOPIC = "/ayyo/stage9d/grasp_fixture/attach"
STAGE9D_FIXTURE_DETACH_TOPIC = "/ayyo/stage9d/grasp_fixture/detach"
STAGE9D_CONTACT_TOPIC = "/ayyo/stage9d/grasp_object/contacts"
STAGE9D_CONTACT_MESSAGE_TYPE = "ros_gz_interfaces/msg/Contacts"
STAGE9D_OBJECT_ODOMETRY_TOPIC = "/ayyo/stage9d/grasp_object/odometry"
STAGE9D_OBJECT_ID = "ayyo.stage9d.reviewed-grasp-object.v1"
STAGE9D_OBJECT_MODEL = "stage9d_grasp_object"
STAGE9D_OBJECT_LINK = "stage9d_grasp_object_link"
STAGE9D_OBJECT_COLLISION = (
    "stage9d_grasp_object::stage9d_grasp_object_link::"
    "stage9d_grasp_object_collision"
)
STAGE9D_OBJECT_FRAME = "world"
STAGE9D_OBJECT_DIMENSIONS = (0.03, 0.03, 0.02)
STAGE9D_OBJECT_MASS = 0.05
STAGE9D_OBJECT_INERTIA = (
    0.000005416666666666667,
    0.000005416666666666667,
    0.0000075,
)
STAGE9D_OBJECT_INITIAL_POSITION = (
    -0.07754797120196011,
    0.19,
    0.8567740568197316,
)
STAGE9D_OBJECT_INITIAL_ORIENTATION = (
    0.0,
    0.09983341664682815,
    0.0,
    0.9950041652780258,
)
STAGE9D_EXPECTED_RELATIVE_POSITION = (0.02, 0.0, -0.17)
STAGE9D_EXPECTED_RELATIVE_ORIENTATION = (0.0, 0.0, 0.0, 1.0)
STAGE9D_COLLISION_BACKEND_ID = "moveit.planning-scene.stage9d-attached-object.v1"
STAGE9D_COLLISION_BACKEND_VERSION = "moveit-2.12.4"
DEFAULT_ALIGNMENT_TRANSLATION_TOLERANCE = 0.012
DEFAULT_ALIGNMENT_ROTATION_TOLERANCE = 0.10
DEFAULT_HOLD_TRANSLATION_TOLERANCE = 0.005
DEFAULT_HOLD_ROTATION_TOLERANCE = 0.05
DEFAULT_MAXIMUM_OBJECT_TELEPORT = 1.0
DEFAULT_MINIMUM_RELEASE_RELATIVE_CHANGE = 0.005
DEFAULT_EVIDENCE_FRESHNESS_NS = DEFAULT_STATE_FRESHNESS_NS
MAX_CONTACT_ENTRIES = 16
MAX_COLLISION_SAMPLES = 4096

END_EFFECTOR_CONTRACT_SCHEMA_ID = (
    "ayyo.manipulation-grasp-interaction.end-effector-contract.v1"
)
OBJECT_CONTRACT_SCHEMA_ID = (
    "ayyo.manipulation-grasp-interaction.object-contract.v1"
)
REQUEST_SCHEMA_ID = "ayyo.manipulation-grasp-interaction.request.v1"
POSE_EVIDENCE_SCHEMA_ID = "ayyo.manipulation-grasp-interaction.pose-evidence.v1"
FIXTURE_EVIDENCE_SCHEMA_ID = (
    "ayyo.manipulation-grasp-interaction.fixture-evidence.v1"
)
CONTACT_EVIDENCE_SCHEMA_ID = (
    "ayyo.manipulation-grasp-interaction.contact-evidence.v1"
)
PREGRASP_EVIDENCE_SCHEMA_ID = (
    "ayyo.manipulation-grasp-interaction.pregrasp-evidence.v1"
)
GRASP_EVIDENCE_SCHEMA_ID = (
    "ayyo.manipulation-grasp-interaction.grasp-evidence.v1"
)
COLLISION_PROOF_SCHEMA_ID = (
    "ayyo.manipulation-grasp-interaction.collision-proof.v1"
)
HOLD_EVIDENCE_SCHEMA_ID = "ayyo.manipulation-grasp-interaction.hold-evidence.v1"
RELEASE_EVIDENCE_SCHEMA_ID = (
    "ayyo.manipulation-grasp-interaction.release-evidence.v1"
)
RESULT_SCHEMA_ID = "ayyo.manipulation-grasp-interaction.result.v1"


class GraspInteractionMode(StrEnum):
    CONTACT_GATED_FIXED_CONSTRAINT = "contact_gated_fixed_constraint"


class FixtureAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class FixtureAttachmentState(StrEnum):
    DETACHED = "detached"
    ATTACHED = "attached"


class ObservedEntityKind(StrEnum):
    END_EFFECTOR = "end_effector"
    GRASP_OBJECT = "grasp_object"


class GraspInteractionPhase(StrEnum):
    PREGRASP_VALIDATED = "pregrasp_validated"
    CONTACT_OBSERVED = "contact_observed"
    GRASP_ESTABLISHED = "grasp_established"
    HOLD_VALIDATED = "hold_validated"
    RELEASE_REQUESTED = "release_requested"
    RELEASE_OBSERVED = "release_observed"


class GraspInteractionResultStatus(StrEnum):
    SIMULATION_GRASP_INTERACTION_COMPLETED = (
        "simulation_grasp_interaction_completed"
    )
    REJECTED = "rejected"


class SimulationAuthority(StrEnum):
    DEVELOPMENT_SIMULATION_ONLY = "development_simulation_only"


class PhysicalValidationClaim(StrEnum):
    NOT_PHYSICALLY_VALIDATED = "not_physically_validated"


class HardwareAuthority(StrEnum):
    NO_HARDWARE_AUTHORITY = "no_hardware_authority"


class ProductionRuntimeAuthority(StrEnum):
    NO_PRODUCTION_RUNTIME_AUTHORITY = "no_production_runtime_authority"


def _schema(schema_id: str) -> dict[str, JSONValue]:
    return {"id": schema_id, "version": SCHEMA_VERSION}


def _closed_enum(value: object, expected: type[StrEnum], field_name: str) -> StrEnum:
    if type(value) is not expected:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
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
        KeyError,
        TypeError,
        ValueError,
        GraspInteractionValidationError,
    ):
        return False


def _timestamp(value: object, field_name: str) -> int:
    return bounded_integer(value, field_name, 0, 2**63 - 1)


def _vector(value: object, field_name: str, length: int) -> tuple[float, ...]:
    if type(value) not in {tuple, list} or len(value) != length:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must contain exactly {length} explicit floats",
        )
    return tuple(finite_float(item, field_name) for item in value)


def _quaternion(value: object, field_name: str) -> tuple[float, ...]:
    quaternion = _vector(value, field_name, 4)
    norm = sqrt(sum(item * item for item in quaternion))
    if abs(norm - 1.0) > 1e-6:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a normalized quaternion",
        )
    return quaternion


def _request_binding(value, request: "GraspInteractionRequest", name: str) -> None:
    if (
        value.interaction_request_id != request.interaction_request_id
        or value.interaction_request_fingerprint
        != request.interaction_request_fingerprint
        or value.run_session_id != request.run_session_id
    ):
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.CROSS_RUN_COMPOSITION,
            f"{name} is bound to another Stage 9D run",
        )


def _quaternion_conjugate(value: tuple[float, ...]) -> tuple[float, ...]:
    return (-value[0], -value[1], -value[2], value[3])


def _quaternion_multiply(
    left: tuple[float, ...], right: tuple[float, ...]
) -> tuple[float, ...]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def _rotate_vector(
    quaternion: tuple[float, ...], vector: tuple[float, ...]
) -> tuple[float, ...]:
    rotated = _quaternion_multiply(
        _quaternion_multiply(quaternion, (*vector, 0.0)),
        _quaternion_conjugate(quaternion),
    )
    return rotated[:3]


def relative_pose(
    parent: "EntityPoseEvidence", child: "EntityPoseEvidence"
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return child pose in parent coordinates."""

    inverse = _quaternion_conjugate(parent.orientation_xyzw)
    delta = tuple(
        child_value - parent_value
        for child_value, parent_value in zip(
            child.position_xyz,
            parent.position_xyz,
            strict=True,
        )
    )
    position = _rotate_vector(inverse, delta)
    orientation = _quaternion_multiply(inverse, child.orientation_xyzw)
    if orientation[3] < 0.0:
        orientation = tuple(-item for item in orientation)
    return tuple(position), tuple(orientation)


def _translation_distance(
    left: tuple[float, ...], right: tuple[float, ...]
) -> float:
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _rotation_distance(
    left: tuple[float, ...], right: tuple[float, ...]
) -> float:
    dot = abs(sum(a * b for a, b in zip(left, right, strict=True)))
    return 2.0 * acos(min(1.0, max(-1.0, dot)))


@dataclass(frozen=True, slots=True)
class EndEffectorContract:
    robot_name: str
    robot_model_id: str
    robot_model_fingerprint: str
    end_effector_link: str = STAGE9D_END_EFFECTOR_LINK
    end_effector_frame: str = STAGE9D_END_EFFECTOR_FRAME
    end_effector_entity: str = STAGE9D_END_EFFECTOR_ENTITY
    contact_collision: str = STAGE9D_END_EFFECTOR_COLLISION
    fixture_id: str = STAGE9D_FIXTURE_ID
    fixture_version: str = STAGE9D_FIXTURE_VERSION
    mode: GraspInteractionMode = GraspInteractionMode.CONTACT_GATED_FIXED_CONSTRAINT
    availability: FixtureAvailability = FixtureAvailability.AVAILABLE
    authority: SimulationAuthority = SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
    schema_id: str = field(init=False, default=END_EFFECTOR_CONTRACT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    configuration_fingerprint: str = field(init=False)
    end_effector_contract_id: str = field(init=False)

    def __post_init__(self) -> None:
        robot_name = identifier(self.robot_name, "robot_name")
        robot_model_id = identifier(self.robot_model_id, "robot_model_id")
        robot_model_fingerprint = fingerprint(
            self.robot_model_fingerprint, "robot_model_fingerprint"
        )
        object.__setattr__(self, "robot_name", robot_name)
        object.__setattr__(self, "robot_model_id", robot_model_id)
        object.__setattr__(self, "robot_model_fingerprint", robot_model_fingerprint)
        for name in ("end_effector_link", "end_effector_frame", "fixture_id"):
            object.__setattr__(self, name, identifier(getattr(self, name), name))
        for name in (
            "end_effector_entity",
            "contact_collision",
            "fixture_version",
        ):
            object.__setattr__(self, name, bounded_text(getattr(self, name), name, 256))
        _closed_enum(self.mode, GraspInteractionMode, "grasp mode")
        _closed_enum(self.availability, FixtureAvailability, "fixture availability")
        _closed_enum(self.authority, SimulationAuthority, "authority")
        if (
            robot_name != STAGE9D_ROBOT_NAME
            or self.end_effector_link != STAGE9D_END_EFFECTOR_LINK
            or self.end_effector_frame != STAGE9D_END_EFFECTOR_FRAME
            or self.end_effector_entity != STAGE9D_END_EFFECTOR_ENTITY
            or self.contact_collision != STAGE9D_END_EFFECTOR_COLLISION
            or self.fixture_id != STAGE9D_FIXTURE_ID
            or self.fixture_version != STAGE9D_FIXTURE_VERSION
            or self.mode is not GraspInteractionMode.CONTACT_GATED_FIXED_CONSTRAINT
            or self.availability is not FixtureAvailability.AVAILABLE
            or self.authority is not SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_END_EFFECTOR,
                "end-effector contract differs from the fixed Stage 9D interface",
            )
        identity, config = content_identity("stage9d-end-effector", self._semantic_dict())
        object.__setattr__(self, "end_effector_contract_id", identity)
        object.__setattr__(self, "configuration_fingerprint", config)
        assert_artifact_size(self.as_dict(), "Stage 9D end-effector contract")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "authority": self.authority.value,
            "availability": self.availability.value,
            "contact_collision": self.contact_collision,
            "end_effector_entity": self.end_effector_entity,
            "end_effector_frame": self.end_effector_frame,
            "end_effector_link": self.end_effector_link,
            "fixture_id": self.fixture_id,
            "fixture_version": self.fixture_version,
            "mode": self.mode.value,
            "robot_model_fingerprint": self.robot_model_fingerprint,
            "robot_model_id": self.robot_model_id,
            "robot_name": self.robot_name,
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "configuration_fingerprint": self.configuration_fingerprint,
            "end_effector_contract_id": self.end_effector_contract_id,
        }


def verify_end_effector_contract(value: object) -> bool:
    return _verify(
        value,
        EndEffectorContract,
        lambda: EndEffectorContract(
            robot_name=value.robot_name,
            robot_model_id=value.robot_model_id,
            robot_model_fingerprint=value.robot_model_fingerprint,
            end_effector_link=value.end_effector_link,
            end_effector_frame=value.end_effector_frame,
            end_effector_entity=value.end_effector_entity,
            contact_collision=value.contact_collision,
            fixture_id=value.fixture_id,
            fixture_version=value.fixture_version,
            mode=value.mode,
            availability=value.availability,
            authority=value.authority,
        ),
    )


@dataclass(frozen=True, slots=True)
class GraspableObjectContract:
    object_id: str = STAGE9D_OBJECT_ID
    model_name: str = STAGE9D_OBJECT_MODEL
    link_name: str = STAGE9D_OBJECT_LINK
    collision_name: str = STAGE9D_OBJECT_COLLISION
    primitive: str = "box"
    dimensions_xyz: tuple[float, ...] = STAGE9D_OBJECT_DIMENSIONS
    initial_frame: str = STAGE9D_OBJECT_FRAME
    initial_position_xyz: tuple[float, ...] = STAGE9D_OBJECT_INITIAL_POSITION
    initial_orientation_xyzw: tuple[float, ...] = STAGE9D_OBJECT_INITIAL_ORIENTATION
    mass_kg: float = STAGE9D_OBJECT_MASS
    inertia_diagonal: tuple[float, ...] = STAGE9D_OBJECT_INERTIA
    gravity_enabled: bool = True
    collision_enabled: bool = True
    dynamic: bool = True
    provenance: str = "gazebo-harmonic.stage9d-reviewed-fixture.v1"
    allowed_target_identity: str = STAGE9D_OBJECT_ID
    schema_id: str = field(init=False, default=OBJECT_CONTRACT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    object_contract_id: str = field(init=False)
    configuration_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "object_id",
            "model_name",
            "link_name",
            "primitive",
            "initial_frame",
            "provenance",
            "allowed_target_identity",
        ):
            object.__setattr__(self, name, identifier(getattr(self, name), name))
        object.__setattr__(
            self, "collision_name", bounded_text(self.collision_name, "collision_name", 256)
        )
        dimensions = _vector(self.dimensions_xyz, "dimensions_xyz", 3)
        position = _vector(self.initial_position_xyz, "initial_position_xyz", 3)
        orientation = _quaternion(
            self.initial_orientation_xyzw, "initial_orientation_xyzw"
        )
        inertia = _vector(self.inertia_diagonal, "inertia_diagonal", 3)
        mass = finite_float(self.mass_kg, "mass_kg")
        object.__setattr__(self, "dimensions_xyz", dimensions)
        object.__setattr__(self, "initial_position_xyz", position)
        object.__setattr__(self, "initial_orientation_xyzw", orientation)
        object.__setattr__(self, "inertia_diagonal", inertia)
        object.__setattr__(self, "mass_kg", mass)
        for name in ("gravity_enabled", "collision_enabled", "dynamic"):
            if type(getattr(self, name)) is not bool:
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.MALFORMED_OBJECT_CONTRACT,
                    f"{name} must be boolean",
                )
        exact = (
            self.object_id == STAGE9D_OBJECT_ID
            and self.model_name == STAGE9D_OBJECT_MODEL
            and self.link_name == STAGE9D_OBJECT_LINK
            and self.collision_name == STAGE9D_OBJECT_COLLISION
            and self.primitive == "box"
            and dimensions == STAGE9D_OBJECT_DIMENSIONS
            and self.initial_frame == STAGE9D_OBJECT_FRAME
            and position == STAGE9D_OBJECT_INITIAL_POSITION
            and orientation == STAGE9D_OBJECT_INITIAL_ORIENTATION
            and mass == STAGE9D_OBJECT_MASS
            and inertia == STAGE9D_OBJECT_INERTIA
            and self.gravity_enabled
            and self.collision_enabled
            and self.dynamic
            and self.provenance == "gazebo-harmonic.stage9d-reviewed-fixture.v1"
            and self.allowed_target_identity == STAGE9D_OBJECT_ID
        )
        if not exact:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_OBJECT_CONTRACT,
                "object contract differs from the one reviewed Stage 9D primitive",
            )
        identity, config = content_identity("stage9d-object-contract", self._semantic_dict())
        object.__setattr__(self, "object_contract_id", identity)
        object.__setattr__(self, "configuration_fingerprint", config)
        assert_artifact_size(self.as_dict(), "Stage 9D object contract")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "allowed_target_identity": self.allowed_target_identity,
            "collision_enabled": self.collision_enabled,
            "collision_name": self.collision_name,
            "dimensions_xyz": list(self.dimensions_xyz),
            "dynamic": self.dynamic,
            "gravity_enabled": self.gravity_enabled,
            "inertia_diagonal": list(self.inertia_diagonal),
            "initial_frame": self.initial_frame,
            "initial_orientation_xyzw": list(self.initial_orientation_xyzw),
            "initial_position_xyz": list(self.initial_position_xyz),
            "link_name": self.link_name,
            "mass_kg": self.mass_kg,
            "model_name": self.model_name,
            "object_id": self.object_id,
            "primitive": self.primitive,
            "provenance": self.provenance,
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "configuration_fingerprint": self.configuration_fingerprint,
            "object_contract_id": self.object_contract_id,
        }


def verify_object_contract(value: object) -> bool:
    return _verify(
        value,
        GraspableObjectContract,
        lambda: GraspableObjectContract(
            object_id=value.object_id,
            model_name=value.model_name,
            link_name=value.link_name,
            collision_name=value.collision_name,
            primitive=value.primitive,
            dimensions_xyz=value.dimensions_xyz,
            initial_frame=value.initial_frame,
            initial_position_xyz=value.initial_position_xyz,
            initial_orientation_xyzw=value.initial_orientation_xyzw,
            mass_kg=value.mass_kg,
            inertia_diagonal=value.inertia_diagonal,
            gravity_enabled=value.gravity_enabled,
            collision_enabled=value.collision_enabled,
            dynamic=value.dynamic,
            provenance=value.provenance,
            allowed_target_identity=value.allowed_target_identity,
        ),
    )


@dataclass(frozen=True, slots=True)
class GraspInteractionRequest:
    stage9c_execution_request: SimulationExecutionRequest
    end_effector: EndEffectorContract
    grasp_object: GraspableObjectContract
    run_session_id: str
    requested_at_ns: int
    profile_id: str = STAGE9D_PROFILE_ID
    authority: SimulationAuthority = SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
    schema_id: str = field(init=False, default=REQUEST_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    interaction_request_id: str = field(init=False)
    interaction_request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_execution_request(self.stage9c_execution_request):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE,
                "request requires a recursively verified Stage 9C source request",
            )
        if not verify_end_effector_contract(self.end_effector):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_END_EFFECTOR,
                "request contains an invalid end-effector contract",
            )
        if not verify_object_contract(self.grasp_object):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_OBJECT_CONTRACT,
                "request contains an invalid object contract",
            )
        planning_model = self.stage9c_execution_request.planning_request.robot_model
        if (
            planning_model.robot_name != STAGE9D_ROBOT_NAME
            or self.end_effector.robot_name != planning_model.robot_name
            or self.end_effector.robot_model_id != planning_model.robot_model_id
            or self.end_effector.robot_model_fingerprint
            != planning_model.robot_model_fingerprint
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_ROBOT,
                "end-effector identity differs from the exact Stage 9C robot model",
            )
        object.__setattr__(
            self, "run_session_id", identifier(self.run_session_id, "run_session_id")
        )
        object.__setattr__(
            self, "requested_at_ns", _timestamp(self.requested_at_ns, "requested_at_ns")
        )
        object.__setattr__(self, "profile_id", identifier(self.profile_id, "profile_id"))
        _closed_enum(self.authority, SimulationAuthority, "authority")
        if (
            self.profile_id != STAGE9D_PROFILE_ID
            or self.authority is not SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "request differs from the fixed Stage 9D development profile",
            )
        identity, content = content_identity("stage9d-request", self._semantic_dict())
        object.__setattr__(self, "interaction_request_id", identity)
        object.__setattr__(self, "interaction_request_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9D request")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "authority": self.authority.value,
            "end_effector": self.end_effector.as_dict(),
            "grasp_object": self.grasp_object.as_dict(),
            "profile_id": self.profile_id,
            "requested_at_ns": self.requested_at_ns,
            "run_session_id": self.run_session_id,
            "schema": _schema(self.schema_id),
            "stage9c_execution_request": self.stage9c_execution_request.as_dict(),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "interaction_request_fingerprint": self.interaction_request_fingerprint,
            "interaction_request_id": self.interaction_request_id,
        }


def verify_interaction_request(value: object) -> bool:
    return _verify(
        value,
        GraspInteractionRequest,
        lambda: GraspInteractionRequest(
            stage9c_execution_request=value.stage9c_execution_request,
            end_effector=value.end_effector,
            grasp_object=value.grasp_object,
            run_session_id=value.run_session_id,
            requested_at_ns=value.requested_at_ns,
            profile_id=value.profile_id,
            authority=value.authority,
        ),
    )


@dataclass(frozen=True, slots=True)
class EntityPoseEvidence:
    interaction_request_id: str
    interaction_request_fingerprint: str
    run_session_id: str
    kind: ObservedEntityKind
    entity_name: str
    frame_id: str
    position_xyz: tuple[float, ...]
    orientation_xyzw: tuple[float, ...]
    observed_at_ns: int
    sequence: int
    entity_count: int
    source: str
    schema_id: str = field(init=False, default=POSE_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    pose_evidence_id: str = field(init=False)
    pose_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interaction_request_id",
            identifier(self.interaction_request_id, "interaction_request_id"),
        )
        object.__setattr__(
            self,
            "interaction_request_fingerprint",
            fingerprint(
                self.interaction_request_fingerprint,
                "interaction_request_fingerprint",
            ),
        )
        object.__setattr__(
            self, "run_session_id", identifier(self.run_session_id, "run_session_id")
        )
        _closed_enum(self.kind, ObservedEntityKind, "observed entity kind")
        object.__setattr__(
            self, "entity_name", bounded_text(self.entity_name, "entity_name", 256)
        )
        object.__setattr__(self, "frame_id", identifier(self.frame_id, "frame_id"))
        object.__setattr__(
            self, "position_xyz", _vector(self.position_xyz, "position_xyz", 3)
        )
        object.__setattr__(
            self,
            "orientation_xyzw",
            _quaternion(self.orientation_xyzw, "orientation_xyzw"),
        )
        object.__setattr__(
            self, "observed_at_ns", _timestamp(self.observed_at_ns, "observed_at_ns")
        )
        object.__setattr__(
            self,
            "sequence",
            bounded_integer(self.sequence, "pose sequence", 1, 2**63 - 1),
        )
        object.__setattr__(
            self,
            "entity_count",
            bounded_integer(self.entity_count, "entity_count", 0, 2),
        )
        object.__setattr__(self, "source", identifier(self.source, "pose source"))
        expected = {
            ObservedEntityKind.END_EFFECTOR: (
                STAGE9D_END_EFFECTOR_ENTITY,
                "stage9d.tf2-gazebo-base.v1",
            ),
            ObservedEntityKind.GRASP_OBJECT: (
                STAGE9D_OBJECT_MODEL,
                "stage9d.gazebo-object-odometry.v1",
            ),
        }[self.kind]
        if self.entity_name != expected[0] or self.source != expected[1]:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.OBJECT_SUBSTITUTION
                if self.kind is ObservedEntityKind.GRASP_OBJECT
                else GraspInteractionFailureCode.WRONG_END_EFFECTOR,
                "pose evidence identifies an unexpected entity or source",
            )
        if self.frame_id != STAGE9D_OBJECT_FRAME:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "pose evidence must use the fixed world frame",
            )
        if self.entity_count == 0:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MISSING_OBJECT,
                "positive pose evidence requires the exact entity to exist",
            )
        if self.entity_count != 1:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.DUPLICATE_OBJECT,
                "positive pose evidence requires exactly one entity",
            )
        identity, content = content_identity("stage9d-pose-evidence", self._semantic_dict())
        object.__setattr__(self, "pose_evidence_id", identity)
        object.__setattr__(self, "pose_evidence_fingerprint", content)

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "entity_count": self.entity_count,
            "entity_name": self.entity_name,
            "frame_id": self.frame_id,
            "interaction_request_fingerprint": self.interaction_request_fingerprint,
            "interaction_request_id": self.interaction_request_id,
            "kind": self.kind.value,
            "observed_at_ns": self.observed_at_ns,
            "orientation_xyzw": list(self.orientation_xyzw),
            "position_xyz": list(self.position_xyz),
            "run_session_id": self.run_session_id,
            "schema": _schema(self.schema_id),
            "sequence": self.sequence,
            "source": self.source,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "pose_evidence_fingerprint": self.pose_evidence_fingerprint,
            "pose_evidence_id": self.pose_evidence_id,
        }


def verify_pose_evidence(value: object) -> bool:
    return _verify(
        value,
        EntityPoseEvidence,
        lambda: EntityPoseEvidence(
            interaction_request_id=value.interaction_request_id,
            interaction_request_fingerprint=value.interaction_request_fingerprint,
            run_session_id=value.run_session_id,
            kind=value.kind,
            entity_name=value.entity_name,
            frame_id=value.frame_id,
            position_xyz=value.position_xyz,
            orientation_xyzw=value.orientation_xyzw,
            observed_at_ns=value.observed_at_ns,
            sequence=value.sequence,
            entity_count=value.entity_count,
            source=value.source,
        ),
    )


@dataclass(frozen=True, slots=True)
class FixtureStateEvidence:
    interaction_request_id: str
    interaction_request_fingerprint: str
    run_session_id: str
    fixture_id: str
    object_id: str
    state: FixtureAttachmentState
    available: bool
    observed_at_ns: int
    sequence: int
    source_topic: str = STAGE9D_FIXTURE_STATE_TOPIC
    schema_id: str = field(init=False, default=FIXTURE_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    fixture_evidence_id: str = field(init=False)
    fixture_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interaction_request_id",
            identifier(self.interaction_request_id, "interaction_request_id"),
        )
        object.__setattr__(
            self,
            "interaction_request_fingerprint",
            fingerprint(
                self.interaction_request_fingerprint,
                "interaction_request_fingerprint",
            ),
        )
        for name in ("run_session_id", "fixture_id", "object_id"):
            object.__setattr__(self, name, identifier(getattr(self, name), name))
        _closed_enum(self.state, FixtureAttachmentState, "fixture state")
        if type(self.available) is not bool:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "fixture availability must be boolean",
            )
        object.__setattr__(
            self, "observed_at_ns", _timestamp(self.observed_at_ns, "observed_at_ns")
        )
        object.__setattr__(
            self,
            "sequence",
            bounded_integer(self.sequence, "fixture sequence", 1, 2**63 - 1),
        )
        object.__setattr__(
            self,
            "source_topic",
            bounded_text(self.source_topic, "fixture source_topic", 256),
        )
        if (
            self.fixture_id != STAGE9D_FIXTURE_ID
            or self.object_id != STAGE9D_OBJECT_ID
            or self.source_topic != STAGE9D_FIXTURE_STATE_TOPIC
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.ATTACHMENT_STATE_MISMATCH,
                "fixture evidence identifies another mechanism or object",
            )
        if not self.available:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.FIXTURE_UNAVAILABLE,
                "positive fixture evidence requires the fixture to be available",
            )
        identity, content = content_identity(
            "stage9d-fixture-evidence", self._semantic_dict()
        )
        object.__setattr__(self, "fixture_evidence_id", identity)
        object.__setattr__(self, "fixture_evidence_fingerprint", content)

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "available": self.available,
            "fixture_id": self.fixture_id,
            "interaction_request_fingerprint": self.interaction_request_fingerprint,
            "interaction_request_id": self.interaction_request_id,
            "object_id": self.object_id,
            "observed_at_ns": self.observed_at_ns,
            "run_session_id": self.run_session_id,
            "schema": _schema(self.schema_id),
            "sequence": self.sequence,
            "source_topic": self.source_topic,
            "state": self.state.value,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "fixture_evidence_fingerprint": self.fixture_evidence_fingerprint,
            "fixture_evidence_id": self.fixture_evidence_id,
        }


def verify_fixture_evidence(value: object) -> bool:
    return _verify(
        value,
        FixtureStateEvidence,
        lambda: FixtureStateEvidence(
            interaction_request_id=value.interaction_request_id,
            interaction_request_fingerprint=value.interaction_request_fingerprint,
            run_session_id=value.run_session_id,
            fixture_id=value.fixture_id,
            object_id=value.object_id,
            state=value.state,
            available=value.available,
            observed_at_ns=value.observed_at_ns,
            sequence=value.sequence,
            source_topic=value.source_topic,
        ),
    )


@dataclass(frozen=True, slots=True)
class ContactEvidence:
    interaction_request_id: str
    interaction_request_fingerprint: str
    run_session_id: str
    object_id: str
    collision_pairs: tuple[tuple[str, str], ...]
    observed_at_ns: int
    sequence: int
    contact_count: int
    maximum_penetration_depth: float | None = None
    source_topic: str = STAGE9D_CONTACT_TOPIC
    message_type: str = STAGE9D_CONTACT_MESSAGE_TYPE
    phase: GraspInteractionPhase = GraspInteractionPhase.CONTACT_OBSERVED
    schema_id: str = field(init=False, default=CONTACT_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    replay_token: str = field(init=False)
    contact_evidence_id: str = field(init=False)
    contact_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interaction_request_id",
            identifier(self.interaction_request_id, "interaction_request_id"),
        )
        object.__setattr__(
            self,
            "interaction_request_fingerprint",
            fingerprint(
                self.interaction_request_fingerprint,
                "interaction_request_fingerprint",
            ),
        )
        object.__setattr__(
            self, "run_session_id", identifier(self.run_session_id, "run_session_id")
        )
        object.__setattr__(self, "object_id", identifier(self.object_id, "object_id"))
        if type(self.collision_pairs) not in {tuple, list}:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_CONTACT_PARTICIPANTS,
                "contact pairs must be a bounded sequence",
            )
        pairs: list[tuple[str, str]] = []
        for item in self.collision_pairs:
            if type(item) not in {tuple, list} or len(item) != 2:
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.WRONG_CONTACT_PARTICIPANTS,
                    "each contact must identify two collision participants",
                )
            pair = tuple(sorted(bounded_text(value, "contact participant", 256) for value in item))
            pairs.append(pair)
        normalized = tuple(sorted(pairs))
        if not 1 <= len(normalized) <= MAX_CONTACT_ENTRIES:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RESOURCE_LIMIT,
                "contact evidence violates its retained-entry bound",
            )
        if len(normalized) != len(set(normalized)):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.CONTACT_REPLAY,
                "contact evidence contains duplicate entries",
            )
        expected = tuple(sorted((STAGE9D_END_EFFECTOR_COLLISION, STAGE9D_OBJECT_COLLISION)))
        if any(pair != expected for pair in normalized):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_CONTACT_PARTICIPANTS,
                "contact does not exclusively bind the reviewed hand and object",
            )
        object.__setattr__(self, "collision_pairs", normalized)
        object.__setattr__(
            self, "observed_at_ns", _timestamp(self.observed_at_ns, "observed_at_ns")
        )
        object.__setattr__(
            self,
            "sequence",
            bounded_integer(self.sequence, "contact sequence", 1, 2**63 - 1),
        )
        object.__setattr__(
            self,
            "contact_count",
            bounded_integer(self.contact_count, "contact_count", 1, MAX_CONTACT_ENTRIES),
        )
        if self.contact_count < len(normalized):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.NO_CONTACT,
                "contact count cannot be smaller than retained entries",
            )
        depth = self.maximum_penetration_depth
        if depth is not None:
            depth = finite_float(depth, "maximum_penetration_depth")
            if not 0.0 <= depth <= 0.01:
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                    "reported penetration exceeds the bounded observation range",
                )
        object.__setattr__(self, "maximum_penetration_depth", depth)
        object.__setattr__(
            self, "source_topic", bounded_text(self.source_topic, "source_topic", 256)
        )
        object.__setattr__(
            self, "message_type", bounded_text(self.message_type, "message_type", 128)
        )
        _closed_enum(self.phase, GraspInteractionPhase, "contact phase")
        if (
            self.object_id != STAGE9D_OBJECT_ID
            or self.source_topic != STAGE9D_CONTACT_TOPIC
            or self.message_type != STAGE9D_CONTACT_MESSAGE_TYPE
            or self.phase is not GraspInteractionPhase.CONTACT_OBSERVED
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_OBJECT,
                "contact evidence differs from the reviewed Stage 9D source",
            )
        replay = semantic_fingerprint(
            "stage9d-contact-replay",
            {
                "observed_at_ns": self.observed_at_ns,
                "pairs": [list(pair) for pair in normalized],
                "run_session_id": self.run_session_id,
                "sequence": self.sequence,
            },
        )
        object.__setattr__(self, "replay_token", replay)
        identity, content = content_identity("stage9d-contact-evidence", self._semantic_dict())
        object.__setattr__(self, "contact_evidence_id", identity)
        object.__setattr__(self, "contact_evidence_fingerprint", content)

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "collision_pairs": [list(pair) for pair in self.collision_pairs],
            "contact_count": self.contact_count,
            "interaction_request_fingerprint": self.interaction_request_fingerprint,
            "interaction_request_id": self.interaction_request_id,
            "maximum_penetration_depth": self.maximum_penetration_depth,
            "message_type": self.message_type,
            "object_id": self.object_id,
            "observed_at_ns": self.observed_at_ns,
            "phase": self.phase.value,
            "run_session_id": self.run_session_id,
            "schema": _schema(self.schema_id),
            "sequence": self.sequence,
            "source_topic": self.source_topic,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "contact_evidence_fingerprint": self.contact_evidence_fingerprint,
            "contact_evidence_id": self.contact_evidence_id,
            "replay_token": self.replay_token,
        }


def verify_contact_evidence(value: object) -> bool:
    return _verify(
        value,
        ContactEvidence,
        lambda: ContactEvidence(
            interaction_request_id=value.interaction_request_id,
            interaction_request_fingerprint=value.interaction_request_fingerprint,
            run_session_id=value.run_session_id,
            object_id=value.object_id,
            collision_pairs=value.collision_pairs,
            observed_at_ns=value.observed_at_ns,
            sequence=value.sequence,
            contact_count=value.contact_count,
            maximum_penetration_depth=value.maximum_penetration_depth,
            source_topic=value.source_topic,
            message_type=value.message_type,
            phase=value.phase,
        ),
    )


@dataclass(frozen=True, slots=True)
class PregraspEvidence:
    request: GraspInteractionRequest
    end_effector_pose: EntityPoseEvidence
    object_pose: EntityPoseEvidence
    detached_fixture: FixtureStateEvidence
    evaluated_at_ns: int
    translation_error: float
    rotation_error: float
    translation_tolerance: float = DEFAULT_ALIGNMENT_TRANSLATION_TOLERANCE
    rotation_tolerance: float = DEFAULT_ALIGNMENT_ROTATION_TOLERANCE
    phase: GraspInteractionPhase = GraspInteractionPhase.PREGRASP_VALIDATED
    schema_id: str = field(init=False, default=PREGRASP_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    pregrasp_evidence_id: str = field(init=False)
    pregrasp_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_interaction_request(self.request):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE,
                "pregrasp requires a verified Stage 9D request",
            )
        if not verify_pose_evidence(self.end_effector_pose) or not verify_pose_evidence(
            self.object_pose
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_ALIGNMENT,
                "pregrasp requires verified object and end-effector poses",
            )
        if not verify_fixture_evidence(self.detached_fixture):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.FIXTURE_UNAVAILABLE,
                "pregrasp requires verified fixture state",
            )
        for evidence, name in (
            (self.end_effector_pose, "end-effector pose"),
            (self.object_pose, "object pose"),
            (self.detached_fixture, "detached fixture"),
        ):
            _request_binding(evidence, self.request, name)
        if self.end_effector_pose.kind is not ObservedEntityKind.END_EFFECTOR:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_END_EFFECTOR,
                "pregrasp end-effector pose has another entity kind",
            )
        if self.object_pose.kind is not ObservedEntityKind.GRASP_OBJECT:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_OBJECT,
                "pregrasp object pose has another entity kind",
            )
        if self.detached_fixture.state is not FixtureAttachmentState.DETACHED:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.FIXTURE_UNEXPECTEDLY_ATTACHED,
                "the Stage 9D fixture must be observed detached before contact",
            )
        evaluated = _timestamp(self.evaluated_at_ns, "pregrasp evaluated_at_ns")
        object.__setattr__(self, "evaluated_at_ns", evaluated)
        ages = (
            evaluated - self.end_effector_pose.observed_at_ns,
            evaluated - self.object_pose.observed_at_ns,
            evaluated - self.detached_fixture.observed_at_ns,
        )
        if any(age < 0 or age > DEFAULT_EVIDENCE_FRESHNESS_NS for age in ages):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.STALE_OBJECT_OBSERVATION,
                "pregrasp pose or fixture evidence is stale",
            )
        translation_tolerance = finite_float(
            self.translation_tolerance, "translation_tolerance"
        )
        rotation_tolerance = finite_float(
            self.rotation_tolerance, "rotation_tolerance"
        )
        if not 0.0 < translation_tolerance <= DEFAULT_ALIGNMENT_TRANSLATION_TOLERANCE:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_ALIGNMENT,
                "pregrasp translation tolerance exceeds its development bound",
            )
        if not 0.0 < rotation_tolerance <= DEFAULT_ALIGNMENT_ROTATION_TOLERANCE:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_ALIGNMENT,
                "pregrasp rotation tolerance exceeds its development bound",
            )
        position, orientation = relative_pose(
            self.end_effector_pose, self.object_pose
        )
        expected_translation = _translation_distance(
            position, STAGE9D_EXPECTED_RELATIVE_POSITION
        )
        expected_rotation = _rotation_distance(
            orientation, STAGE9D_EXPECTED_RELATIVE_ORIENTATION
        )
        translation_error = finite_float(self.translation_error, "translation_error")
        rotation_error = finite_float(self.rotation_error, "rotation_error")
        if (
            abs(translation_error - expected_translation) > 1e-12
            or abs(rotation_error - expected_rotation) > 1e-12
            or translation_error > translation_tolerance
            or rotation_error > rotation_tolerance
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_ALIGNMENT,
                "object is outside the fixed Stage 9D pregrasp alignment bounds",
            )
        object.__setattr__(self, "translation_error", translation_error)
        object.__setattr__(self, "rotation_error", rotation_error)
        object.__setattr__(self, "translation_tolerance", translation_tolerance)
        object.__setattr__(self, "rotation_tolerance", rotation_tolerance)
        _closed_enum(self.phase, GraspInteractionPhase, "pregrasp phase")
        if self.phase is not GraspInteractionPhase.PREGRASP_VALIDATED:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "pregrasp phase is not validated",
            )
        identity, content = content_identity("stage9d-pregrasp", self._semantic_dict())
        object.__setattr__(self, "pregrasp_evidence_id", identity)
        object.__setattr__(self, "pregrasp_evidence_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9D pregrasp evidence")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "detached_fixture": self.detached_fixture.as_dict(),
            "end_effector_pose": self.end_effector_pose.as_dict(),
            "evaluated_at_ns": self.evaluated_at_ns,
            "object_pose": self.object_pose.as_dict(),
            "phase": self.phase.value,
            "request": self.request.as_dict(),
            "rotation_error": self.rotation_error,
            "rotation_tolerance": self.rotation_tolerance,
            "schema": _schema(self.schema_id),
            "translation_error": self.translation_error,
            "translation_tolerance": self.translation_tolerance,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "pregrasp_evidence_fingerprint": self.pregrasp_evidence_fingerprint,
            "pregrasp_evidence_id": self.pregrasp_evidence_id,
        }


def verify_pregrasp_evidence(value: object) -> bool:
    return _verify(
        value,
        PregraspEvidence,
        lambda: PregraspEvidence(
            request=value.request,
            end_effector_pose=value.end_effector_pose,
            object_pose=value.object_pose,
            detached_fixture=value.detached_fixture,
            evaluated_at_ns=value.evaluated_at_ns,
            translation_error=value.translation_error,
            rotation_error=value.rotation_error,
            translation_tolerance=value.translation_tolerance,
            rotation_tolerance=value.rotation_tolerance,
            phase=value.phase,
        ),
    )


@dataclass(frozen=True, slots=True)
class GraspEstablishedEvidence:
    pregrasp: PregraspEvidence
    contact: ContactEvidence
    attached_fixture: FixtureStateEvidence
    established_at_ns: int
    phase: GraspInteractionPhase = GraspInteractionPhase.GRASP_ESTABLISHED
    schema_id: str = field(init=False, default=GRASP_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    grasp_evidence_id: str = field(init=False)
    grasp_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_pregrasp_evidence(self.pregrasp):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_ALIGNMENT,
                "grasp establishment requires verified pregrasp evidence",
            )
        if not verify_contact_evidence(self.contact):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.NO_CONTACT,
                "grasp establishment requires verified contact",
            )
        if not verify_fixture_evidence(self.attached_fixture):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.ATTACHMENT_STATE_MISMATCH,
                "grasp establishment requires verified attached state",
            )
        request = self.pregrasp.request
        _request_binding(self.contact, request, "contact evidence")
        _request_binding(self.attached_fixture, request, "attached fixture")
        if self.contact.object_id != request.grasp_object.object_id:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_OBJECT,
                "contact names another grasp object",
            )
        if self.contact.observed_at_ns < self.pregrasp.evaluated_at_ns:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.CONTACT_REPLAY,
                "contact predates the current run's pregrasp validation",
            )
        if (
            self.attached_fixture.state is not FixtureAttachmentState.ATTACHED
            or self.attached_fixture.sequence
            <= self.pregrasp.detached_fixture.sequence
            or self.attached_fixture.observed_at_ns < self.contact.observed_at_ns
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.ATTACHMENT_STATE_MISMATCH,
                "attachment was not observed after fresh target contact",
            )
        established = _timestamp(self.established_at_ns, "established_at_ns")
        if (
            established < self.attached_fixture.observed_at_ns
            or established - self.contact.observed_at_ns
            > DEFAULT_EVIDENCE_FRESHNESS_NS
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.STALE_CONTACT,
                "attachment did not use fresh contact evidence",
            )
        object.__setattr__(self, "established_at_ns", established)
        _closed_enum(self.phase, GraspInteractionPhase, "grasp phase")
        if self.phase is not GraspInteractionPhase.GRASP_ESTABLISHED:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "grasp phase is not established",
            )
        identity, content = content_identity("stage9d-grasp", self._semantic_dict())
        object.__setattr__(self, "grasp_evidence_id", identity)
        object.__setattr__(self, "grasp_evidence_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9D grasp evidence")

    @property
    def request(self) -> GraspInteractionRequest:
        return self.pregrasp.request

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "attached_fixture": self.attached_fixture.as_dict(),
            "contact": self.contact.as_dict(),
            "established_at_ns": self.established_at_ns,
            "phase": self.phase.value,
            "pregrasp": self.pregrasp.as_dict(),
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "grasp_evidence_fingerprint": self.grasp_evidence_fingerprint,
            "grasp_evidence_id": self.grasp_evidence_id,
        }


def verify_grasp_evidence(value: object) -> bool:
    return _verify(
        value,
        GraspEstablishedEvidence,
        lambda: GraspEstablishedEvidence(
            pregrasp=value.pregrasp,
            contact=value.contact,
            attached_fixture=value.attached_fixture,
            established_at_ns=value.established_at_ns,
            phase=value.phase,
        ),
    )


@dataclass(frozen=True, slots=True)
class InteractionCollisionSample:
    sample_index: int
    positions: tuple[float, ...]
    within_joint_limits: bool
    self_collision_free: bool
    environment_collision_free: bool
    attached_object_checked: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sample_index",
            bounded_integer(self.sample_index, "sample_index", 0, MAX_COLLISION_SAMPLES - 1),
        )
        object.__setattr__(self, "positions", _vector(self.positions, "sample positions", 4))
        for name in (
            "within_joint_limits",
            "self_collision_free",
            "environment_collision_free",
            "attached_object_checked",
        ):
            if type(getattr(self, name)) is not bool:
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                    f"{name} must be boolean",
                )

    @property
    def collision_free(self) -> bool:
        return (
            self.within_joint_limits
            and self.self_collision_free
            and self.environment_collision_free
            and self.attached_object_checked
        )

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            "attached_object_checked": self.attached_object_checked,
            "environment_collision_free": self.environment_collision_free,
            "positions": list(self.positions),
            "sample_index": self.sample_index,
            "self_collision_free": self.self_collision_free,
            "within_joint_limits": self.within_joint_limits,
        }


@dataclass(frozen=True, slots=True)
class InteractionCollisionProof:
    request: GraspInteractionRequest
    grasp_evidence_id: str
    grasp_evidence_fingerprint: str
    backend_id: str
    backend_version: str
    input_fingerprint: str
    samples: tuple[InteractionCollisionSample, ...]
    allowed_touch_links: tuple[str, ...]
    allowed_collision_pair: tuple[str, str]
    target_object_specific: bool
    grasp_interval_only: bool
    global_acm_modified: bool
    continuous_collision_certification: bool
    physical_collision_certification: bool
    schema_id: str = field(init=False, default=COLLISION_PROOF_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    collision_proof_id: str = field(init=False)
    collision_proof_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_interaction_request(self.request):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE,
                "collision proof requires a verified request",
            )
        object.__setattr__(
            self,
            "grasp_evidence_id",
            identifier(self.grasp_evidence_id, "grasp_evidence_id"),
        )
        object.__setattr__(
            self,
            "grasp_evidence_fingerprint",
            fingerprint(self.grasp_evidence_fingerprint, "grasp_evidence_fingerprint"),
        )
        object.__setattr__(self, "backend_id", identifier(self.backend_id, "backend_id"))
        object.__setattr__(
            self, "backend_version", bounded_text(self.backend_version, "backend_version", 64)
        )
        object.__setattr__(
            self,
            "input_fingerprint",
            fingerprint(self.input_fingerprint, "input_fingerprint"),
        )
        from .proof import interaction_preflight_input_fingerprint

        if self.input_fingerprint != interaction_preflight_input_fingerprint(
            self.request, self.grasp_evidence_id, self.grasp_evidence_fingerprint
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INTERACTION_COLLISION,
                "collision input is not bound to the exact Stage 9D grasp",
            )
        if type(self.samples) not in {tuple, list}:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RESOURCE_LIMIT,
                "collision samples must be a bounded sequence",
            )
        samples = tuple(self.samples)
        if not 2 <= len(samples) <= MAX_COLLISION_SAMPLES or any(
            type(item) is not InteractionCollisionSample for item in samples
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RESOURCE_LIMIT,
                "collision sample count or type is invalid",
            )
        expected = expected_dense_samples(self.request.stage9c_execution_request)
        if len(samples) != len(expected) or any(
            item.sample_index != index or item.positions != expected[index].positions
            for index, item in enumerate(samples)
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INTERACTION_COLLISION,
                "collision proof does not cover the exact dense Stage 9C path",
            )
        object.__setattr__(self, "samples", samples)
        links = tuple(identifier(item, "allowed_touch_link") for item in self.allowed_touch_links)
        pair = tuple(bounded_text(item, "allowed collision participant", 256) for item in self.allowed_collision_pair)
        if (
            links != (STAGE9D_END_EFFECTOR_LINK,)
            or pair != (STAGE9D_END_EFFECTOR_LINK, STAGE9D_OBJECT_COLLISION)
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INTERACTION_COLLISION,
                "collision exception is not exact to the reviewed hand and target",
            )
        object.__setattr__(self, "allowed_touch_links", links)
        object.__setattr__(self, "allowed_collision_pair", pair)
        for name in (
            "target_object_specific",
            "grasp_interval_only",
            "global_acm_modified",
            "continuous_collision_certification",
            "physical_collision_certification",
        ):
            if type(getattr(self, name)) is not bool:
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                    f"{name} must be boolean",
                )
        if (
            self.backend_id != STAGE9D_COLLISION_BACKEND_ID
            or self.backend_version != STAGE9D_COLLISION_BACKEND_VERSION
            or not self.target_object_specific
            or not self.grasp_interval_only
            or self.global_acm_modified
            or self.continuous_collision_certification
            or self.physical_collision_certification
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INTERACTION_COLLISION,
                "collision proof weakens or overstates the Stage 9D boundary",
            )
        identity, content = content_identity(
            "stage9d-collision-proof", self._semantic_dict()
        )
        object.__setattr__(self, "collision_proof_id", identity)
        object.__setattr__(self, "collision_proof_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9D collision proof")

    @property
    def collision_free(self) -> bool:
        return all(item.collision_free for item in self.samples)

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "allowed_collision_pair": list(self.allowed_collision_pair),
            "allowed_touch_links": list(self.allowed_touch_links),
            "backend_id": self.backend_id,
            "backend_version": self.backend_version,
            "continuous_collision_certification": self.continuous_collision_certification,
            "global_acm_modified": self.global_acm_modified,
            "grasp_evidence_fingerprint": self.grasp_evidence_fingerprint,
            "grasp_evidence_id": self.grasp_evidence_id,
            "grasp_interval_only": self.grasp_interval_only,
            "input_fingerprint": self.input_fingerprint,
            "physical_collision_certification": self.physical_collision_certification,
            "request": self.request.as_dict(),
            "samples": [item.as_dict() for item in self.samples],
            "schema": _schema(self.schema_id),
            "target_object_specific": self.target_object_specific,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "collision_proof_fingerprint": self.collision_proof_fingerprint,
            "collision_proof_id": self.collision_proof_id,
        }


def verify_collision_proof(value: object) -> bool:
    return _verify(
        value,
        InteractionCollisionProof,
        lambda: InteractionCollisionProof(
            request=value.request,
            grasp_evidence_id=value.grasp_evidence_id,
            grasp_evidence_fingerprint=value.grasp_evidence_fingerprint,
            backend_id=value.backend_id,
            backend_version=value.backend_version,
            input_fingerprint=value.input_fingerprint,
            samples=value.samples,
            allowed_touch_links=value.allowed_touch_links,
            allowed_collision_pair=value.allowed_collision_pair,
            target_object_specific=value.target_object_specific,
            grasp_interval_only=value.grasp_interval_only,
            global_acm_modified=value.global_acm_modified,
            continuous_collision_certification=value.continuous_collision_certification,
            physical_collision_certification=value.physical_collision_certification,
        ),
    )


@dataclass(frozen=True, slots=True)
class HoldEvidence:
    grasp: GraspEstablishedEvidence
    collision_proof: InteractionCollisionProof
    stage9c_result: SimulationExecutionResult
    final_end_effector_pose: EntityPoseEvidence
    final_object_pose: EntityPoseEvidence
    attached_fixture: FixtureStateEvidence
    evaluated_at_ns: int
    relative_translation_change: float
    relative_rotation_change: float
    object_world_displacement: float
    translation_tolerance: float = DEFAULT_HOLD_TRANSLATION_TOLERANCE
    rotation_tolerance: float = DEFAULT_HOLD_ROTATION_TOLERANCE
    maximum_object_teleport: float = DEFAULT_MAXIMUM_OBJECT_TELEPORT
    phase: GraspInteractionPhase = GraspInteractionPhase.HOLD_VALIDATED
    schema_id: str = field(init=False, default=HOLD_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    hold_evidence_id: str = field(init=False)
    hold_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_grasp_evidence(self.grasp):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RELEASE_WITHOUT_ESTABLISHED_HOLD,
                "hold validation requires a verified established grasp",
            )
        if not verify_collision_proof(self.collision_proof):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INTERACTION_COLLISION,
                "hold validation requires a verified interaction collision proof",
            )
        if not self.collision_proof.collision_free:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INTERACTION_COLLISION,
                "interaction-aware collision proof reported a collision",
            )
        if not verify_execution_result(self.stage9c_result):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE,
                "hold contains an invalid Stage 9C result",
            )
        if (
            self.stage9c_result.status is not SimulationExecutionResultStatus.COMPLETED
            or self.stage9c_result.motion_status is not SimulationMotionStatus.SIMULATION_EXECUTED
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.STAGE9C_EXECUTION_FAILURE,
                "the exact reviewed Stage 9C execution did not complete",
            )
        request = self.grasp.request
        stage9c_source = (
            self.stage9c_result.execution_goal.preflight_evidence.execution_request
        )
        if stage9c_source != request.stage9c_execution_request:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE,
                "Stage 9C result is bound to another request or trajectory",
            )
        if (
            self.collision_proof.request != request
            or self.collision_proof.grasp_evidence_id != self.grasp.grasp_evidence_id
            or self.collision_proof.grasp_evidence_fingerprint
            != self.grasp.grasp_evidence_fingerprint
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.CROSS_RUN_COMPOSITION,
                "collision proof and grasp evidence come from different runs",
            )
        for evidence, name in (
            (self.final_end_effector_pose, "final end-effector pose"),
            (self.final_object_pose, "final object pose"),
            (self.attached_fixture, "hold fixture state"),
        ):
            if isinstance(evidence, EntityPoseEvidence):
                if not verify_pose_evidence(evidence):
                    raise GraspInteractionValidationError(
                        GraspInteractionFailureCode.OBJECT_DISAPPEARED,
                        f"{name} is invalid",
                    )
            elif not verify_fixture_evidence(evidence):
                raise GraspInteractionValidationError(
                    GraspInteractionFailureCode.ATTACHMENT_STATE_MISMATCH,
                    f"{name} is invalid",
                )
            _request_binding(evidence, request, name)
        if self.final_end_effector_pose.kind is not ObservedEntityKind.END_EFFECTOR:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.WRONG_END_EFFECTOR,
                "hold end-effector evidence identifies another entity",
            )
        if self.final_object_pose.kind is not ObservedEntityKind.GRASP_OBJECT:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.OBJECT_SUBSTITUTION,
                "hold object evidence identifies another entity",
            )
        if (
            self.attached_fixture.state is not FixtureAttachmentState.ATTACHED
            or self.attached_fixture.sequence <= self.grasp.attached_fixture.sequence
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.ATTACHMENT_STATE_MISMATCH,
                "fixture was not freshly observed attached after movement",
            )
        completed = self.stage9c_result.observation.completed_at_ns
        evaluated = _timestamp(self.evaluated_at_ns, "hold evaluated_at_ns")
        object.__setattr__(self, "evaluated_at_ns", evaluated)
        timestamps = (
            self.final_end_effector_pose.observed_at_ns,
            self.final_object_pose.observed_at_ns,
            self.attached_fixture.observed_at_ns,
        )
        if any(
            timestamp < completed
            or evaluated - timestamp < 0
            or evaluated - timestamp > DEFAULT_EVIDENCE_FRESHNESS_NS
            for timestamp in timestamps
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.STALE_OBJECT_OBSERVATION,
                "hold evidence is stale or predates Stage 9C completion",
            )
        initial_relative = relative_pose(
            self.grasp.pregrasp.end_effector_pose,
            self.grasp.pregrasp.object_pose,
        )
        final_relative = relative_pose(
            self.final_end_effector_pose, self.final_object_pose
        )
        expected_translation_change = _translation_distance(
            initial_relative[0], final_relative[0]
        )
        expected_rotation_change = _rotation_distance(
            initial_relative[1], final_relative[1]
        )
        expected_world_displacement = _translation_distance(
            self.grasp.pregrasp.object_pose.position_xyz,
            self.final_object_pose.position_xyz,
        )
        translation_change = finite_float(
            self.relative_translation_change, "relative_translation_change"
        )
        rotation_change = finite_float(
            self.relative_rotation_change, "relative_rotation_change"
        )
        world_displacement = finite_float(
            self.object_world_displacement, "object_world_displacement"
        )
        translation_tolerance = finite_float(
            self.translation_tolerance, "translation_tolerance"
        )
        rotation_tolerance = finite_float(
            self.rotation_tolerance, "rotation_tolerance"
        )
        maximum_teleport = finite_float(
            self.maximum_object_teleport, "maximum_object_teleport"
        )
        if (
            abs(translation_change - expected_translation_change) > 1e-12
            or abs(rotation_change - expected_rotation_change) > 1e-12
            or abs(world_displacement - expected_world_displacement) > 1e-12
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "hold metrics differ from the bound pose observations",
            )
        if not 0.0 < translation_tolerance <= DEFAULT_HOLD_TRANSLATION_TOLERANCE:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.EXCESSIVE_RELATIVE_TRANSLATION,
                "hold translation tolerance exceeds its development bound",
            )
        if not 0.0 < rotation_tolerance <= DEFAULT_HOLD_ROTATION_TOLERANCE:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.EXCESSIVE_RELATIVE_ROTATION,
                "hold rotation tolerance exceeds its development bound",
            )
        if maximum_teleport != DEFAULT_MAXIMUM_OBJECT_TELEPORT:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "object teleport bound differs from the reviewed value",
            )
        if translation_change > translation_tolerance:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.SLIP_HOLD_FAILURE,
                "object slipped beyond the relative translation bound",
            )
        if rotation_change > rotation_tolerance:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.SLIP_HOLD_FAILURE,
                "object rotated beyond the relative hold bound",
            )
        if world_displacement > maximum_teleport:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.OBJECT_SUBSTITUTION,
                "object displacement is incompatible with the reviewed movement",
            )
        object.__setattr__(self, "relative_translation_change", translation_change)
        object.__setattr__(self, "relative_rotation_change", rotation_change)
        object.__setattr__(self, "object_world_displacement", world_displacement)
        object.__setattr__(self, "translation_tolerance", translation_tolerance)
        object.__setattr__(self, "rotation_tolerance", rotation_tolerance)
        object.__setattr__(self, "maximum_object_teleport", maximum_teleport)
        _closed_enum(self.phase, GraspInteractionPhase, "hold phase")
        if self.phase is not GraspInteractionPhase.HOLD_VALIDATED:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "hold phase is not validated",
            )
        identity, content = content_identity("stage9d-hold", self._semantic_dict())
        object.__setattr__(self, "hold_evidence_id", identity)
        object.__setattr__(self, "hold_evidence_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9D hold evidence")

    @property
    def request(self) -> GraspInteractionRequest:
        return self.grasp.request

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "attached_fixture": self.attached_fixture.as_dict(),
            "collision_proof": self.collision_proof.as_dict(),
            "evaluated_at_ns": self.evaluated_at_ns,
            "final_end_effector_pose": self.final_end_effector_pose.as_dict(),
            "final_object_pose": self.final_object_pose.as_dict(),
            "grasp": self.grasp.as_dict(),
            "maximum_object_teleport": self.maximum_object_teleport,
            "object_world_displacement": self.object_world_displacement,
            "phase": self.phase.value,
            "relative_rotation_change": self.relative_rotation_change,
            "relative_translation_change": self.relative_translation_change,
            "rotation_tolerance": self.rotation_tolerance,
            "schema": _schema(self.schema_id),
            "stage9c_result": self.stage9c_result.as_dict(),
            "translation_tolerance": self.translation_tolerance,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "hold_evidence_fingerprint": self.hold_evidence_fingerprint,
            "hold_evidence_id": self.hold_evidence_id,
        }


def verify_hold_evidence(value: object) -> bool:
    return _verify(
        value,
        HoldEvidence,
        lambda: HoldEvidence(
            grasp=value.grasp,
            collision_proof=value.collision_proof,
            stage9c_result=value.stage9c_result,
            final_end_effector_pose=value.final_end_effector_pose,
            final_object_pose=value.final_object_pose,
            attached_fixture=value.attached_fixture,
            evaluated_at_ns=value.evaluated_at_ns,
            relative_translation_change=value.relative_translation_change,
            relative_rotation_change=value.relative_rotation_change,
            object_world_displacement=value.object_world_displacement,
            translation_tolerance=value.translation_tolerance,
            rotation_tolerance=value.rotation_tolerance,
            maximum_object_teleport=value.maximum_object_teleport,
            phase=value.phase,
        ),
    )


@dataclass(frozen=True, slots=True)
class ReleaseEvidence:
    hold: HoldEvidence
    release_requested_at_ns: int
    detached_fixture: FixtureStateEvidence
    post_release_end_effector_pose: EntityPoseEvidence
    post_release_object_pose: EntityPoseEvidence
    post_release_stability: SimulationStabilityObservation
    evaluated_at_ns: int
    relative_pose_change: float
    minimum_relative_change: float = DEFAULT_MINIMUM_RELEASE_RELATIVE_CHANGE
    requested_phase: GraspInteractionPhase = GraspInteractionPhase.RELEASE_REQUESTED
    phase: GraspInteractionPhase = GraspInteractionPhase.RELEASE_OBSERVED
    schema_id: str = field(init=False, default=RELEASE_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    release_evidence_id: str = field(init=False)
    release_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_hold_evidence(self.hold):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RELEASE_WITHOUT_ESTABLISHED_HOLD,
                "release requires verified hold evidence",
            )
        if not verify_fixture_evidence(self.detached_fixture):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.STILL_ATTACHED_AFTER_RELEASE,
                "release requires a verified detached fixture observation",
            )
        if not verify_pose_evidence(
            self.post_release_end_effector_pose
        ) or not verify_pose_evidence(self.post_release_object_pose):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.OBJECT_DISAPPEARED,
                "release requires fresh object and end-effector poses",
            )
        if not verify_stability_observation(self.post_release_stability):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.UNSTABLE_WHOLE_BODY,
                "release requires the public Stage 9C stability verifier",
            )
        request = self.hold.request
        for evidence, name in (
            (self.detached_fixture, "post-release fixture"),
            (self.post_release_end_effector_pose, "post-release end-effector"),
            (self.post_release_object_pose, "post-release object"),
        ):
            _request_binding(evidence, request, name)
        if (
            self.detached_fixture.state is not FixtureAttachmentState.DETACHED
            or self.detached_fixture.sequence <= self.hold.attached_fixture.sequence
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.STILL_ATTACHED_AFTER_RELEASE,
                "fixture remains attached or its state was replayed",
            )
        if (
            self.post_release_end_effector_pose.kind
            is not ObservedEntityKind.END_EFFECTOR
            or self.post_release_object_pose.kind
            is not ObservedEntityKind.GRASP_OBJECT
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.OBJECT_SUBSTITUTION,
                "release pose evidence contains substituted entities",
            )
        if self.post_release_stability.status is not StabilityStatus.WHOLE_BODY_STABLE:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.UNSTABLE_WHOLE_BODY,
                "whole-body/controller state became invalid after release",
            )
        released_at = _timestamp(
            self.release_requested_at_ns, "release_requested_at_ns"
        )
        evaluated = _timestamp(self.evaluated_at_ns, "release evaluated_at_ns")
        object.__setattr__(self, "release_requested_at_ns", released_at)
        object.__setattr__(self, "evaluated_at_ns", evaluated)
        if released_at < self.hold.evaluated_at_ns:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RELEASE_WITHOUT_ESTABLISHED_HOLD,
                "release was requested before hold validation",
            )
        timestamps = (
            self.detached_fixture.observed_at_ns,
            self.post_release_end_effector_pose.observed_at_ns,
            self.post_release_object_pose.observed_at_ns,
            self.post_release_stability.final_state.observed_at_ns,
            self.post_release_stability.final_state.base_pose.observed_at_ns,
            self.post_release_stability.post_controller_state.observed_at_ns,
        )
        if any(
            timestamp < released_at
            or evaluated - timestamp < 0
            or evaluated - timestamp > DEFAULT_EVIDENCE_FRESHNESS_NS
            for timestamp in timestamps
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.STALE_POST_RELEASE_EVIDENCE,
                "release evidence is stale or predates the explicit request",
            )
        before = relative_pose(
            self.hold.final_end_effector_pose,
            self.hold.final_object_pose,
        )
        after = relative_pose(
            self.post_release_end_effector_pose,
            self.post_release_object_pose,
        )
        expected_change = _translation_distance(before[0], after[0])
        change = finite_float(self.relative_pose_change, "relative_pose_change")
        minimum = finite_float(self.minimum_relative_change, "minimum_relative_change")
        if abs(change - expected_change) > 1e-12:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "release metric differs from the observed relative poses",
            )
        if minimum != DEFAULT_MINIMUM_RELEASE_RELATIVE_CHANGE or change < minimum:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RELEASE_REJECTED,
                "object did not stop rigidly following the end effector",
            )
        object.__setattr__(self, "relative_pose_change", change)
        object.__setattr__(self, "minimum_relative_change", minimum)
        _closed_enum(self.requested_phase, GraspInteractionPhase, "requested release phase")
        _closed_enum(self.phase, GraspInteractionPhase, "release phase")
        if (
            self.requested_phase is not GraspInteractionPhase.RELEASE_REQUESTED
            or self.phase is not GraspInteractionPhase.RELEASE_OBSERVED
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.RELEASE_REJECTED,
                "release progression is incomplete",
            )
        identity, content = content_identity("stage9d-release", self._semantic_dict())
        object.__setattr__(self, "release_evidence_id", identity)
        object.__setattr__(self, "release_evidence_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9D release evidence")

    @property
    def request(self) -> GraspInteractionRequest:
        return self.hold.request

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "detached_fixture": self.detached_fixture.as_dict(),
            "evaluated_at_ns": self.evaluated_at_ns,
            "hold": self.hold.as_dict(),
            "minimum_relative_change": self.minimum_relative_change,
            "phase": self.phase.value,
            "post_release_end_effector_pose": (
                self.post_release_end_effector_pose.as_dict()
            ),
            "post_release_object_pose": self.post_release_object_pose.as_dict(),
            "post_release_stability": self.post_release_stability.as_dict(),
            "relative_pose_change": self.relative_pose_change,
            "release_requested_at_ns": self.release_requested_at_ns,
            "requested_phase": self.requested_phase.value,
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "release_evidence_fingerprint": self.release_evidence_fingerprint,
            "release_evidence_id": self.release_evidence_id,
        }


def verify_release_evidence(value: object) -> bool:
    return _verify(
        value,
        ReleaseEvidence,
        lambda: ReleaseEvidence(
            hold=value.hold,
            release_requested_at_ns=value.release_requested_at_ns,
            detached_fixture=value.detached_fixture,
            post_release_end_effector_pose=value.post_release_end_effector_pose,
            post_release_object_pose=value.post_release_object_pose,
            post_release_stability=value.post_release_stability,
            evaluated_at_ns=value.evaluated_at_ns,
            relative_pose_change=value.relative_pose_change,
            minimum_relative_change=value.minimum_relative_change,
            requested_phase=value.requested_phase,
            phase=value.phase,
        ),
    )


@dataclass(frozen=True, slots=True)
class GraspInteractionResult:
    request: GraspInteractionRequest
    release: ReleaseEvidence
    status: GraspInteractionResultStatus = (
        GraspInteractionResultStatus.SIMULATION_GRASP_INTERACTION_COMPLETED
    )
    completed_phases: tuple[GraspInteractionPhase, ...] = tuple(
        GraspInteractionPhase
    )
    failure_reasons: tuple[GraspInteractionFailureCode, ...] = ()
    authority: SimulationAuthority = SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
    physical_validation: PhysicalValidationClaim = (
        PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
    )
    hardware_authority: HardwareAuthority = HardwareAuthority.NO_HARDWARE_AUTHORITY
    production_runtime_authority: ProductionRuntimeAuthority = (
        ProductionRuntimeAuthority.NO_PRODUCTION_RUNTIME_AUTHORITY
    )
    schema_id: str = field(init=False, default=RESULT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    interaction_result_id: str = field(init=False)
    interaction_result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_interaction_request(self.request) or not verify_release_evidence(
            self.release
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "final result requires verified request and release evidence",
            )
        if self.release.request != self.request:
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.CROSS_RUN_COMPOSITION,
                "final result combines different Stage 9D runs",
            )
        _closed_enum(self.status, GraspInteractionResultStatus, "result status")
        if type(self.completed_phases) not in {tuple, list} or any(
            type(item) is not GraspInteractionPhase for item in self.completed_phases
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "completed phases must use the closed progression",
            )
        phases = tuple(self.completed_phases)
        failures = tuple(self.failure_reasons)
        if any(type(item) is not GraspInteractionFailureCode for item in failures):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "failure reasons must use the Stage 9D taxonomy",
            )
        if (
            self.status
            is not GraspInteractionResultStatus.SIMULATION_GRASP_INTERACTION_COMPLETED
            or phases != tuple(GraspInteractionPhase)
            or failures
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "positive final result lacks the exact required progression",
            )
        object.__setattr__(self, "completed_phases", phases)
        object.__setattr__(self, "failure_reasons", failures)
        for value, enum_type, name in (
            (self.authority, SimulationAuthority, "authority"),
            (self.physical_validation, PhysicalValidationClaim, "physical validation"),
            (self.hardware_authority, HardwareAuthority, "hardware authority"),
            (
                self.production_runtime_authority,
                ProductionRuntimeAuthority,
                "production runtime authority",
            ),
        ):
            _closed_enum(value, enum_type, name)
        if (
            self.authority is not SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
            or self.physical_validation
            is not PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
            or self.hardware_authority is not HardwareAuthority.NO_HARDWARE_AUTHORITY
            or self.production_runtime_authority
            is not ProductionRuntimeAuthority.NO_PRODUCTION_RUNTIME_AUTHORITY
        ):
            raise GraspInteractionValidationError(
                GraspInteractionFailureCode.MALFORMED_ARTIFACT,
                "Stage 9D result cannot grant physical, hardware, or Runtime authority",
            )
        identity, content = content_identity("stage9d-result", self._semantic_dict())
        object.__setattr__(self, "interaction_result_id", identity)
        object.__setattr__(self, "interaction_result_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9D result")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "authority": self.authority.value,
            "completed_phases": [item.value for item in self.completed_phases],
            "failure_reasons": [item.value for item in self.failure_reasons],
            "hardware_authority": self.hardware_authority.value,
            "physical_validation": self.physical_validation.value,
            "production_runtime_authority": self.production_runtime_authority.value,
            "release": self.release.as_dict(),
            "request": self.request.as_dict(),
            "schema": _schema(self.schema_id),
            "status": self.status.value,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "interaction_result_fingerprint": self.interaction_result_fingerprint,
            "interaction_result_id": self.interaction_result_id,
        }


def verify_interaction_result(value: object) -> bool:
    return _verify(
        value,
        GraspInteractionResult,
        lambda: GraspInteractionResult(
            request=value.request,
            release=value.release,
            status=value.status,
            completed_phases=value.completed_phases,
            failure_reasons=value.failure_reasons,
            authority=value.authority,
            physical_validation=value.physical_validation,
            hardware_authority=value.hardware_authority,
            production_runtime_authority=value.production_runtime_authority,
        ),
    )
