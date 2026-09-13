"""Immutable Stage 9C simulation-only execution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import ceil

from ayyo_manipulation_planning import (
    LEFT_ARM_JOINT_NAMES,
    ExecutionDisposition,
)
from ayyo_manipulation_trajectory import (
    ExecutionHandoffEligibilityDecision,
    HandoffEligibilityStatus,
    PhysicalValidationStatus,
    RuntimeEndpointState,
    verify_handoff_decision,
)

from .canonical import (
    JSONValue,
    SCHEMA_VERSION,
    assert_artifact_size,
    bounded_integer,
    bounded_text,
    canonical_json,
    content_identity,
    finite_float,
    fingerprint,
    identifier,
    semantic_fingerprint,
)
from .errors import (
    SimulationExecutionFailureCode,
    SimulationExecutionValidationError,
)


STAGE9C_PROFILE_ID = "development.stage9c.left-arm-trajectory.v1"
STAGE9C_CONTROLLER_NAME = "ayyo_left_arm_trajectory_controller"
STAGE9C_CONTROLLER_TYPE = (
    "joint_trajectory_controller/JointTrajectoryController"
)
STAGE9C_ACTION_ENDPOINT = (
    "/ayyo_left_arm_trajectory_controller/follow_joint_trajectory"
)
STAGE9C_HARDWARE_SYSTEM = "AyyoSystem"
STAGE9C_INTERPOLATION_METHOD = "position-only-linear"
STAGE9C_COLLISION_BACKEND_ID = "moveit.planning-scene.stage9c-preflight.v1"
STAGE9C_COLLISION_BACKEND_VERSION = "moveit-2.12.4"
STAGE9C_SAMPLING_POLICY_ID = "ayyo.stage9c.bounded-linear-sampling.v1"
STAGE9C_REVIEWED_SIMULATION_DESCRIPTION_FINGERPRINT = (
    "ayyo-stage9c-simulation-description-sha256-"
    "106bb6875649b272827f6dd5e37c7e1adfc6333721676e7fbf76bd198ab44b7c"
)
STAGE9C_REVIEWED_CONTROLLER_CONFIGURATION_FINGERPRINT = (
    "ayyo-stage9c-controller-configuration-sha256-"
    "5c0730f025c14b13d9fb81c0d762a761b072680c76861ecc122ba275a368f6ae"
)

MAX_STAGE9C_JOINTS = 4
MAX_STAGE9C_TRAJECTORY_POINTS = 129
MAX_PREFLIGHT_SAMPLES_PER_SEGMENT = 64
MAX_PREFLIGHT_SAMPLES = 4096
DEFAULT_MAXIMUM_JOINT_SAMPLE_STEP = 0.01
MAXIMUM_ALLOWED_JOINT_SAMPLE_STEP = 0.02
DEFAULT_START_TOLERANCE = 0.01
DEFAULT_FINAL_TOLERANCE = 0.02
DEFAULT_STATE_FRESHNESS_NS = 500_000_000
DEFAULT_EXECUTION_TIMEOUT_MARGIN_NS = 5_000_000_000
MAX_EXECUTION_TIMEOUT_NS = 310_000_000_000

CONTROLLER_CONTRACT_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.controller-contract.v1"
)
SAMPLING_POLICY_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.sampling-policy.v1"
)
EXECUTION_REQUEST_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.request.v1"
)
COLLISION_PROOF_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.collision-proof.v1"
)
JOINT_STATE_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.joint-state.v1"
)
CONTROLLER_STATE_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.controller-state.v1"
)
PREFLIGHT_EVIDENCE_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.preflight.v1"
)
EXECUTION_GOAL_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.goal.v1"
)
EXECUTION_OBSERVATION_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.observation.v1"
)
EXECUTION_RESULT_SCHEMA_ID = (
    "ayyo.manipulation-simulation-execution.result.v1"
)


class SimulationEnvironment(StrEnum):
    GAZEBO_HARMONIC = "gazebo_harmonic"


class SimulationAuthority(StrEnum):
    DEVELOPMENT_SIMULATION_ONLY = "development_simulation_only"


class PhysicalValidationClaim(StrEnum):
    NOT_PHYSICALLY_VALIDATED = "not_physically_validated"


class HardwareAuthority(StrEnum):
    NO_HARDWARE_AUTHORITY = "no_hardware_authority"


class ProductionRuntimeAuthority(StrEnum):
    NO_PRODUCTION_RUNTIME_AUTHORITY = "no_production_runtime_authority"


class PreflightStatus(StrEnum):
    READY_FOR_SIMULATION_EXECUTION = "ready_for_simulation_execution"
    REJECTED = "rejected"


class PreflightReason(StrEnum):
    COLLISION_FREE_DENSE_PATH = "collision_free_dense_path"
    CONTROLLER_READY = "controller_ready"
    START_STATE_MATCHED = "start_state_matched"
    COLLISION_REPORTED = "collision_reported"
    CONTROLLER_UNAVAILABLE = "controller_unavailable"
    START_STATE_MISMATCH = "start_state_mismatch"
    STATE_STALE = "state_stale"


class GoalAcceptance(StrEnum):
    NOT_SENT = "not_sent"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class SimulationExecutionOutcome(StrEnum):
    CONTROLLER_UNAVAILABLE = "controller_unavailable"
    GOAL_REJECTED = "goal_rejected"
    SIMULATION_EXECUTION_COMPLETED = "simulation_execution_completed"
    PATH_TOLERANCE_VIOLATED = "path_tolerance_violated"
    GOAL_TOLERANCE_VIOLATED = "goal_tolerance_violated"
    TIMED_OUT = "timed_out"
    CANCELED = "canceled"
    ABORTED = "aborted"
    SIMULATOR_SHUTDOWN = "simulator_shutdown"
    MALFORMED_FEEDBACK = "malformed_feedback"


class SimulationExecutionResultStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class SimulationMotionStatus(StrEnum):
    NOT_SENT = "not_sent"
    ATTEMPTED = "attempted"
    SIMULATION_EXECUTED = "simulation_executed"


def _schema(schema_id: str) -> dict[str, JSONValue]:
    return {"id": schema_id, "version": SCHEMA_VERSION}


def _closed_enum(value: object, expected: type[StrEnum], field_name: str) -> StrEnum:
    if type(value) is not expected:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
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
        SimulationExecutionValidationError,
    ):
        return False


def _closed_tuple(
    value: object,
    field_name: str,
    item_type: type,
    maximum: int,
    *,
    minimum: int = 0,
) -> tuple:
    if type(value) not in {tuple, list}:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a bounded sequence",
        )
    items = tuple(value)
    if not minimum <= len(items) <= maximum or any(
        type(item) is not item_type for item in items
    ):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its item bound or type",
        )
    return items


def _identifier_tuple(
    value: object,
    field_name: str,
    maximum: int,
    *,
    minimum: int = 0,
) -> tuple[str, ...]:
    if type(value) not in {tuple, list}:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a bounded sequence",
        )
    items = tuple(identifier(item, field_name) for item in value)
    if not minimum <= len(items) <= maximum:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its item bound",
        )
    if len(items) != len(set(items)):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} contains duplicates",
        )
    return items


def _position_tuple(value: object, field_name: str) -> tuple[float, ...]:
    if type(value) not in {tuple, list} or len(value) != MAX_STAGE9C_JOINTS:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.TRAJECTORY_MISMATCH,
            f"{field_name} must contain the four reviewed left-arm positions",
        )
    return tuple(finite_float(item, field_name) for item in value)


def _timestamp_ns(value: object, field_name: str) -> int:
    return bounded_integer(value, field_name, 0, 2**63 - 1)


@dataclass(frozen=True, slots=True)
class SimulationControllerContract:
    profile_id: str = STAGE9C_PROFILE_ID
    environment: SimulationEnvironment = SimulationEnvironment.GAZEBO_HARMONIC
    hardware_system: str = STAGE9C_HARDWARE_SYSTEM
    controller_name: str = STAGE9C_CONTROLLER_NAME
    controller_type: str = STAGE9C_CONTROLLER_TYPE
    action_endpoint: str = STAGE9C_ACTION_ENDPOINT
    joint_names: tuple[str, ...] = LEFT_ARM_JOINT_NAMES
    command_interfaces: tuple[str, ...] = ("position",)
    state_interfaces: tuple[str, ...] = ("position", "velocity")
    interpolation_method: str = STAGE9C_INTERPOLATION_METHOD
    allow_partial_joints_goal: bool = False
    use_sim_time: bool = True
    simulation_mode: bool = True
    manipulation_control_enabled: bool = True
    simulation_description_fingerprint: str = (
        STAGE9C_REVIEWED_SIMULATION_DESCRIPTION_FINGERPRINT
    )
    controller_configuration_fingerprint: str = (
        STAGE9C_REVIEWED_CONTROLLER_CONFIGURATION_FINGERPRINT
    )
    schema_id: str = field(init=False, default=CONTROLLER_CONTRACT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    controller_contract_id: str = field(init=False)
    controller_contract_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", identifier(self.profile_id, "profile_id"))
        object.__setattr__(
            self,
            "hardware_system",
            bounded_text(self.hardware_system, "hardware_system", 128),
        )
        object.__setattr__(
            self,
            "controller_name",
            identifier(self.controller_name, "controller_name"),
        )
        object.__setattr__(
            self,
            "controller_type",
            bounded_text(self.controller_type, "controller_type", 128),
        )
        object.__setattr__(
            self,
            "action_endpoint",
            bounded_text(self.action_endpoint, "action_endpoint", 256),
        )
        joints = _identifier_tuple(
            self.joint_names,
            "controller joint_names",
            MAX_STAGE9C_JOINTS,
            minimum=MAX_STAGE9C_JOINTS,
        )
        commands = _identifier_tuple(
            self.command_interfaces,
            "command_interfaces",
            4,
            minimum=1,
        )
        states = _identifier_tuple(
            self.state_interfaces,
            "state_interfaces",
            4,
            minimum=1,
        )
        object.__setattr__(self, "joint_names", joints)
        object.__setattr__(self, "command_interfaces", commands)
        object.__setattr__(self, "state_interfaces", states)
        object.__setattr__(
            self,
            "interpolation_method",
            identifier(self.interpolation_method, "interpolation_method"),
        )
        _closed_enum(self.environment, SimulationEnvironment, "environment")
        for name in (
            "allow_partial_joints_goal",
            "use_sim_time",
            "simulation_mode",
            "manipulation_control_enabled",
        ):
            if type(getattr(self, name)) is not bool:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
                    f"{name} must be boolean",
                )
        object.__setattr__(
            self,
            "simulation_description_fingerprint",
            fingerprint(
                self.simulation_description_fingerprint,
                "simulation_description_fingerprint",
            ),
        )
        object.__setattr__(
            self,
            "controller_configuration_fingerprint",
            fingerprint(
                self.controller_configuration_fingerprint,
                "controller_configuration_fingerprint",
            ),
        )
        exact = (
            self.profile_id == STAGE9C_PROFILE_ID
            and self.environment is SimulationEnvironment.GAZEBO_HARMONIC
            and self.hardware_system == STAGE9C_HARDWARE_SYSTEM
            and self.controller_name == STAGE9C_CONTROLLER_NAME
            and self.controller_type == STAGE9C_CONTROLLER_TYPE
            and self.action_endpoint == STAGE9C_ACTION_ENDPOINT
            and self.joint_names == LEFT_ARM_JOINT_NAMES
            and self.command_interfaces == ("position",)
            and self.state_interfaces == ("position", "velocity")
            and self.interpolation_method == STAGE9C_INTERPOLATION_METHOD
            and not self.allow_partial_joints_goal
            and self.use_sim_time
            and self.simulation_mode
            and self.manipulation_control_enabled
            and self.simulation_description_fingerprint
            == STAGE9C_REVIEWED_SIMULATION_DESCRIPTION_FINGERPRINT
            and self.controller_configuration_fingerprint
            == STAGE9C_REVIEWED_CONTROLLER_CONFIGURATION_FINGERPRINT
        )
        if not exact:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.CONTROLLER_MISMATCH,
                "controller contract differs from the fixed Stage 9C simulation profile",
            )
        identity, content = content_identity(
            "stage9c-controller-contract",
            self._semantic_dict(),
        )
        object.__setattr__(self, "controller_contract_id", identity)
        object.__setattr__(self, "controller_contract_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9C controller contract")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "action_endpoint": self.action_endpoint,
            "allow_partial_joints_goal": self.allow_partial_joints_goal,
            "command_interfaces": list(self.command_interfaces),
            "controller_configuration_fingerprint": (
                self.controller_configuration_fingerprint
            ),
            "controller_name": self.controller_name,
            "controller_type": self.controller_type,
            "environment": self.environment.value,
            "hardware_system": self.hardware_system,
            "interpolation_method": self.interpolation_method,
            "joint_names": list(self.joint_names),
            "manipulation_control_enabled": self.manipulation_control_enabled,
            "profile_id": self.profile_id,
            "schema": _schema(self.schema_id),
            "simulation_description_fingerprint": (
                self.simulation_description_fingerprint
            ),
            "simulation_mode": self.simulation_mode,
            "state_interfaces": list(self.state_interfaces),
            "use_sim_time": self.use_sim_time,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "controller_contract_fingerprint": self.controller_contract_fingerprint,
            "controller_contract_id": self.controller_contract_id,
        }


def verify_controller_contract(value: object) -> bool:
    return _verify(
        value,
        SimulationControllerContract,
        lambda: SimulationControllerContract(
            profile_id=value.profile_id,
            environment=value.environment,
            hardware_system=value.hardware_system,
            controller_name=value.controller_name,
            controller_type=value.controller_type,
            action_endpoint=value.action_endpoint,
            joint_names=value.joint_names,
            command_interfaces=value.command_interfaces,
            state_interfaces=value.state_interfaces,
            interpolation_method=value.interpolation_method,
            allow_partial_joints_goal=value.allow_partial_joints_goal,
            use_sim_time=value.use_sim_time,
            simulation_mode=value.simulation_mode,
            manipulation_control_enabled=value.manipulation_control_enabled,
            simulation_description_fingerprint=(
                value.simulation_description_fingerprint
            ),
            controller_configuration_fingerprint=(
                value.controller_configuration_fingerprint
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class CollisionSamplingPolicy:
    policy_id: str = STAGE9C_SAMPLING_POLICY_ID
    maximum_joint_step: float = DEFAULT_MAXIMUM_JOINT_SAMPLE_STEP
    maximum_samples_per_segment: int = MAX_PREFLIGHT_SAMPLES_PER_SEGMENT
    maximum_total_samples: int = MAX_PREFLIGHT_SAMPLES
    include_segment_endpoints: bool = True
    interpolation_method: str = STAGE9C_INTERPOLATION_METHOD
    schema_id: str = field(init=False, default=SAMPLING_POLICY_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    sampling_policy_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", identifier(self.policy_id, "policy_id"))
        step = finite_float(self.maximum_joint_step, "maximum_joint_step")
        if not 0.001 <= step <= MAXIMUM_ALLOWED_JOINT_SAMPLE_STEP:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "dense preflight sample step is outside its reviewed bound",
            )
        object.__setattr__(self, "maximum_joint_step", step)
        object.__setattr__(
            self,
            "maximum_samples_per_segment",
            bounded_integer(
                self.maximum_samples_per_segment,
                "maximum_samples_per_segment",
                1,
                MAX_PREFLIGHT_SAMPLES_PER_SEGMENT,
            ),
        )
        object.__setattr__(
            self,
            "maximum_total_samples",
            bounded_integer(
                self.maximum_total_samples,
                "maximum_total_samples",
                2,
                MAX_PREFLIGHT_SAMPLES,
            ),
        )
        if type(self.include_segment_endpoints) is not bool or not (
            self.include_segment_endpoints
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "dense preflight must include every segment endpoint",
            )
        object.__setattr__(
            self,
            "interpolation_method",
            identifier(self.interpolation_method, "interpolation_method"),
        )
        if (
            self.policy_id != STAGE9C_SAMPLING_POLICY_ID
            or self.interpolation_method != STAGE9C_INTERPOLATION_METHOD
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "preflight policy differs from position-only controller interpolation",
            )
        object.__setattr__(
            self,
            "sampling_policy_fingerprint",
            semantic_fingerprint("stage9c-sampling-policy", self._semantic_dict()),
        )

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "include_segment_endpoints": self.include_segment_endpoints,
            "interpolation_method": self.interpolation_method,
            "maximum_joint_step": self.maximum_joint_step,
            "maximum_samples_per_segment": self.maximum_samples_per_segment,
            "maximum_total_samples": self.maximum_total_samples,
            "policy_id": self.policy_id,
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "sampling_policy_fingerprint": self.sampling_policy_fingerprint,
        }


def verify_sampling_policy(value: object) -> bool:
    return _verify(
        value,
        CollisionSamplingPolicy,
        lambda: CollisionSamplingPolicy(
            policy_id=value.policy_id,
            maximum_joint_step=value.maximum_joint_step,
            maximum_samples_per_segment=value.maximum_samples_per_segment,
            maximum_total_samples=value.maximum_total_samples,
            include_segment_endpoints=value.include_segment_endpoints,
            interpolation_method=value.interpolation_method,
        ),
    )


@dataclass(frozen=True, slots=True)
class SimulationExecutionRequest:
    stage9b_handoff: ExecutionHandoffEligibilityDecision
    controller_contract: SimulationControllerContract
    sampling_policy: CollisionSamplingPolicy
    authority: SimulationAuthority = SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
    physical_validation: PhysicalValidationClaim = (
        PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
    )
    hardware_authority: HardwareAuthority = HardwareAuthority.NO_HARDWARE_AUTHORITY
    production_runtime_authority: ProductionRuntimeAuthority = (
        ProductionRuntimeAuthority.NO_PRODUCTION_RUNTIME_AUTHORITY
    )
    schema_id: str = field(init=False, default=EXECUTION_REQUEST_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    execution_request_id: str = field(init=False)
    execution_request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_handoff_decision(self.stage9b_handoff):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.UPSTREAM_INTEGRITY,
                "Stage 9C requires a recursively verified Stage 9B handoff",
            )
        if not verify_controller_contract(self.controller_contract):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.CONTROLLER_MISMATCH,
                "Stage 9C controller contract failed recursive verification",
            )
        if not verify_sampling_policy(self.sampling_policy):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "Stage 9C sampling policy failed recursive verification",
            )
        handoff = self.stage9b_handoff
        safety_result = handoff.safety_result
        if (
            handoff.status
            is not HandoffEligibilityStatus.ELIGIBLE_FOR_FUTURE_SIMULATION_HANDOFF_REVIEW
            or handoff.runtime_endpoint_state is not RuntimeEndpointState.NOT_REGISTERED
            or handoff.execution_disposition is not ExecutionDisposition.NOT_EXECUTED
            or handoff.physical_validation is not PhysicalValidationStatus.ABSENT
            or safety_result.execution_disposition is not ExecutionDisposition.NOT_EXECUTED
            or safety_result.physical_validation is not PhysicalValidationStatus.ABSENT
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.UPSTREAM_INELIGIBLE,
                "Stage 9B handoff is not the exact positive inert review decision",
            )
        trajectory = safety_result.trajectory_evidence.trajectory
        planning_request = (
            trajectory.request.stage9a_decision.request
        )
        if (
            trajectory.joint_names != LEFT_ARM_JOINT_NAMES
            or planning_request.group.joint_names != LEFT_ARM_JOINT_NAMES
            or len(trajectory.points) < 2
            or len(trajectory.points) > MAX_STAGE9C_TRAJECTORY_POINTS
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.TRAJECTORY_MISMATCH,
                "Stage 9C accepts only the exact reviewed four-joint left-arm trajectory",
            )
        _closed_enum(self.authority, SimulationAuthority, "authority")
        _closed_enum(
            self.physical_validation,
            PhysicalValidationClaim,
            "physical_validation",
        )
        _closed_enum(self.hardware_authority, HardwareAuthority, "hardware_authority")
        _closed_enum(
            self.production_runtime_authority,
            ProductionRuntimeAuthority,
            "production_runtime_authority",
        )
        if (
            self.authority is not SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
            or self.physical_validation
            is not PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
            or self.hardware_authority is not HardwareAuthority.NO_HARDWARE_AUTHORITY
            or self.production_runtime_authority
            is not ProductionRuntimeAuthority.NO_PRODUCTION_RUNTIME_AUTHORITY
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.SIMULATION_BOUNDARY,
                "Stage 9C grants simulation development authority only",
            )
        identity, content = content_identity(
            "stage9c-execution-request",
            self._semantic_dict(),
        )
        object.__setattr__(self, "execution_request_id", identity)
        object.__setattr__(self, "execution_request_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9C execution request")

    @property
    def trajectory(self):
        return self.stage9b_handoff.safety_result.trajectory_evidence.trajectory

    @property
    def planning_request(self):
        return self.trajectory.request.stage9a_decision.request

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "authority": self.authority.value,
            "controller_contract": self.controller_contract.as_dict(),
            "hardware_authority": self.hardware_authority.value,
            "physical_validation": self.physical_validation.value,
            "production_runtime_authority": self.production_runtime_authority.value,
            "sampling_policy": self.sampling_policy.as_dict(),
            "schema": _schema(self.schema_id),
            "stage9b_handoff": self.stage9b_handoff.as_dict(),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "execution_request_fingerprint": self.execution_request_fingerprint,
            "execution_request_id": self.execution_request_id,
        }


def verify_execution_request(value: object) -> bool:
    return _verify(
        value,
        SimulationExecutionRequest,
        lambda: SimulationExecutionRequest(
            stage9b_handoff=value.stage9b_handoff,
            controller_contract=value.controller_contract,
            sampling_policy=value.sampling_policy,
            authority=value.authority,
            physical_validation=value.physical_validation,
            hardware_authority=value.hardware_authority,
            production_runtime_authority=value.production_runtime_authority,
        ),
    )


@dataclass(frozen=True, slots=True)
class DenseCollisionSample:
    sample_index: int
    segment_index: int
    subdivision_index: int
    segment_subdivisions: int
    segment_fraction: float
    positions: tuple[float, ...]
    self_collision_free: bool
    environment_collision_free: bool
    within_joint_limits: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sample_index",
            bounded_integer(
                self.sample_index,
                "sample_index",
                0,
                MAX_PREFLIGHT_SAMPLES - 1,
            ),
        )
        object.__setattr__(
            self,
            "segment_index",
            bounded_integer(
                self.segment_index,
                "segment_index",
                0,
                MAX_STAGE9C_TRAJECTORY_POINTS - 2,
            ),
        )
        object.__setattr__(
            self,
            "segment_subdivisions",
            bounded_integer(
                self.segment_subdivisions,
                "segment_subdivisions",
                1,
                MAX_PREFLIGHT_SAMPLES_PER_SEGMENT,
            ),
        )
        object.__setattr__(
            self,
            "subdivision_index",
            bounded_integer(
                self.subdivision_index,
                "subdivision_index",
                0,
                self.segment_subdivisions,
            ),
        )
        fraction = finite_float(self.segment_fraction, "segment_fraction")
        if not 0.0 <= fraction <= 1.0:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "collision sample fraction is outside its segment",
            )
        object.__setattr__(self, "segment_fraction", fraction)
        object.__setattr__(
            self,
            "positions",
            _position_tuple(self.positions, "collision sample positions"),
        )
        for name in (
            "self_collision_free",
            "environment_collision_free",
            "within_joint_limits",
        ):
            if type(getattr(self, name)) is not bool:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
                    f"{name} must be boolean",
                )

    @property
    def collision_free(self) -> bool:
        return (
            self.self_collision_free
            and self.environment_collision_free
            and self.within_joint_limits
        )

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            "environment_collision_free": self.environment_collision_free,
            "positions": list(self.positions),
            "sample_index": self.sample_index,
            "segment_fraction": self.segment_fraction,
            "segment_index": self.segment_index,
            "segment_subdivisions": self.segment_subdivisions,
            "self_collision_free": self.self_collision_free,
            "subdivision_index": self.subdivision_index,
            "within_joint_limits": self.within_joint_limits,
        }


def _trajectory_positions(request: SimulationExecutionRequest) -> tuple[tuple[float, ...], ...]:
    try:
        return tuple(
            tuple(item.position for item in point.positions)
            for point in request.trajectory.points
        )
    except (AssertionError, AttributeError, TypeError, ValueError) as error:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.TRAJECTORY_MISMATCH,
            "Stage 9B trajectory positions are malformed",
        ) from error


def expected_dense_samples(
    request: SimulationExecutionRequest,
) -> tuple[DenseCollisionSample, ...]:
    """Derive the bounded position-only controller interpolation samples."""

    if not verify_execution_request(request):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.UPSTREAM_INTEGRITY,
            "dense sampling requires a verified Stage 9C request",
        )
    policy = request.sampling_policy
    positions = _trajectory_positions(request)
    samples: list[DenseCollisionSample] = [
        DenseCollisionSample(
            sample_index=0,
            segment_index=0,
            subdivision_index=0,
            segment_subdivisions=1,
            segment_fraction=0.0,
            positions=positions[0],
            self_collision_free=True,
            environment_collision_free=True,
            within_joint_limits=True,
        )
    ]
    for segment_index, (start, end) in enumerate(zip(positions, positions[1:])):
        maximum_delta = max(
            abs(end_value - start_value)
            for start_value, end_value in zip(start, end, strict=True)
        )
        subdivisions = max(1, ceil(maximum_delta / policy.maximum_joint_step))
        if subdivisions > policy.maximum_samples_per_segment:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.RESOURCE_LIMIT,
                "dense preflight exceeds its per-segment sample ceiling",
            )
        for subdivision_index in range(1, subdivisions + 1):
            fraction = subdivision_index / subdivisions
            sample_positions = tuple(
                start_value + ((end_value - start_value) * fraction)
                for start_value, end_value in zip(start, end, strict=True)
            )
            samples.append(
                DenseCollisionSample(
                    sample_index=len(samples),
                    segment_index=segment_index,
                    subdivision_index=subdivision_index,
                    segment_subdivisions=subdivisions,
                    segment_fraction=fraction,
                    positions=sample_positions,
                    self_collision_free=True,
                    environment_collision_free=True,
                    within_joint_limits=True,
                )
            )
            if len(samples) > policy.maximum_total_samples:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.RESOURCE_LIMIT,
                    "dense preflight exceeds its total sample ceiling",
                )
    return tuple(samples)


def preflight_input_document(request: SimulationExecutionRequest) -> dict[str, JSONValue]:
    """Return the exact bounded input document consumed by the MoveIt checker."""

    if not verify_execution_request(request):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.UPSTREAM_INTEGRITY,
            "MoveIt preflight input requires a verified execution request",
        )
    planning_request = request.planning_request
    samples = expected_dense_samples(request)
    return {
        "collision_model_fingerprint": planning_request.collision_model.collision_model_fingerprint,
        "collision_model_id": planning_request.collision_model.collision_model_id,
        "collision_objects": [item.as_dict() for item in planning_request.scene.collision_objects],
        "disabled_collision_pairs": [
            list(item) for item in planning_request.collision_model.disabled_collision_pairs
        ],
        "execution_request_fingerprint": request.execution_request_fingerprint,
        "execution_request_id": request.execution_request_id,
        "group_fingerprint": planning_request.group.group_fingerprint,
        "group_id": planning_request.group.group_id,
        "joint_catalog_fingerprint": planning_request.joint_catalog.joint_catalog_fingerprint,
        "joint_catalog_id": planning_request.joint_catalog.joint_catalog_id,
        "joint_names": list(LEFT_ARM_JOINT_NAMES),
        "robot_description_content_fingerprint": (
            planning_request.collision_model.robot_description_content_fingerprint
        ),
        "robot_model_fingerprint": planning_request.robot_model.robot_model_fingerprint,
        "robot_model_id": planning_request.robot_model.robot_model_id,
        "samples": [
            {
                "positions": list(sample.positions),
                "sample_index": sample.sample_index,
                "segment_fraction": sample.segment_fraction,
                "segment_index": sample.segment_index,
                "segment_subdivisions": sample.segment_subdivisions,
                "subdivision_index": sample.subdivision_index,
            }
            for sample in samples
        ],
        "sampling_policy_fingerprint": request.sampling_policy.sampling_policy_fingerprint,
        "scene_fingerprint": planning_request.scene.scene_fingerprint,
        "scene_id": planning_request.scene.scene_id,
        "schema": {"id": "ayyo.stage9c.moveit-preflight-input.v1", "version": SCHEMA_VERSION},
        "srdf_content_fingerprint": planning_request.collision_model.srdf_content_fingerprint,
        "trajectory_fingerprint": request.trajectory.trajectory_fingerprint,
        "trajectory_id": request.trajectory.trajectory_id,
    }


def preflight_input_fingerprint(request: SimulationExecutionRequest) -> str:
    return semantic_fingerprint(
        "stage9c-moveit-preflight-input",
        preflight_input_document(request),
    )


@dataclass(frozen=True, slots=True)
class SimulationCollisionProof:
    execution_request: SimulationExecutionRequest
    input_fingerprint: str
    backend_id: str
    backend_version: str
    samples: tuple[DenseCollisionSample, ...]
    continuous_collision_certification: bool = False
    execution_disposition: ExecutionDisposition = ExecutionDisposition.NOT_EXECUTED
    physical_validation: PhysicalValidationStatus = PhysicalValidationStatus.ABSENT
    schema_id: str = field(init=False, default=COLLISION_PROOF_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    collision_proof_id: str = field(init=False)
    collision_proof_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_execution_request(self.execution_request):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.UPSTREAM_INTEGRITY,
                "collision proof contains an invalid execution request",
            )
        object.__setattr__(
            self,
            "input_fingerprint",
            fingerprint(self.input_fingerprint, "input_fingerprint"),
        )
        object.__setattr__(self, "backend_id", identifier(self.backend_id, "backend_id"))
        object.__setattr__(
            self,
            "backend_version",
            bounded_text(self.backend_version, "backend_version", 64),
        )
        samples = _closed_tuple(
            self.samples,
            "collision samples",
            DenseCollisionSample,
            self.execution_request.sampling_policy.maximum_total_samples,
            minimum=2,
        )
        expected = expected_dense_samples(self.execution_request)
        if len(samples) != len(expected):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "collision proof checked a different dense sample count",
            )
        for actual, planned in zip(samples, expected, strict=True):
            if (
                actual.sample_index != planned.sample_index
                or actual.segment_index != planned.segment_index
                or actual.subdivision_index != planned.subdivision_index
                or actual.segment_subdivisions != planned.segment_subdivisions
                or actual.segment_fraction != planned.segment_fraction
                or actual.positions != planned.positions
            ):
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                    "collision proof samples differ from exact controller interpolation",
                )
        object.__setattr__(self, "samples", samples)
        if (
            self.input_fingerprint != preflight_input_fingerprint(self.execution_request)
            or self.backend_id != STAGE9C_COLLISION_BACKEND_ID
            or self.backend_version != STAGE9C_COLLISION_BACKEND_VERSION
            or type(self.continuous_collision_certification) is not bool
            or self.continuous_collision_certification
            or self.execution_disposition is not ExecutionDisposition.NOT_EXECUTED
            or self.physical_validation is not PhysicalValidationStatus.ABSENT
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "collision proof overclaims or differs from its reviewed MoveIt input",
            )
        identity, content = content_identity(
            "stage9c-collision-proof",
            self._semantic_dict(),
        )
        object.__setattr__(self, "collision_proof_id", identity)
        object.__setattr__(self, "collision_proof_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9C collision proof")

    @property
    def collision_free(self) -> bool:
        return all(sample.collision_free for sample in self.samples)

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "backend_id": self.backend_id,
            "backend_version": self.backend_version,
            "continuous_collision_certification": self.continuous_collision_certification,
            "execution_disposition": self.execution_disposition.value,
            "execution_request": self.execution_request.as_dict(),
            "input_fingerprint": self.input_fingerprint,
            "physical_validation": self.physical_validation.value,
            "samples": [sample.as_dict() for sample in self.samples],
            "schema": _schema(self.schema_id),
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
        SimulationCollisionProof,
        lambda: SimulationCollisionProof(
            execution_request=value.execution_request,
            input_fingerprint=value.input_fingerprint,
            backend_id=value.backend_id,
            backend_version=value.backend_version,
            samples=value.samples,
            continuous_collision_certification=value.continuous_collision_certification,
            execution_disposition=value.execution_disposition,
            physical_validation=value.physical_validation,
        ),
    )


@dataclass(frozen=True, slots=True)
class SimulatedJointState:
    joint_names: tuple[str, ...]
    positions: tuple[float, ...]
    observed_at_ns: int
    sequence: int
    source: str = "joint_state_broadcaster"
    schema_id: str = field(init=False, default=JOINT_STATE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    joint_state_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        names = _identifier_tuple(
            self.joint_names,
            "joint state names",
            MAX_STAGE9C_JOINTS,
            minimum=MAX_STAGE9C_JOINTS,
        )
        positions = _position_tuple(self.positions, "joint state positions")
        object.__setattr__(self, "joint_names", names)
        object.__setattr__(self, "positions", positions)
        object.__setattr__(
            self,
            "observed_at_ns",
            _timestamp_ns(self.observed_at_ns, "observed_at_ns"),
        )
        object.__setattr__(
            self,
            "sequence",
            bounded_integer(self.sequence, "sequence", 1, 2**63 - 1),
        )
        object.__setattr__(self, "source", identifier(self.source, "source"))
        if names != LEFT_ARM_JOINT_NAMES or self.source != "joint_state_broadcaster":
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.START_STATE_MISMATCH,
                "joint feedback must bind the exact reviewed left-arm order and source",
            )
        object.__setattr__(
            self,
            "joint_state_fingerprint",
            semantic_fingerprint("stage9c-joint-state", self._semantic_dict()),
        )

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "joint_names": list(self.joint_names),
            "observed_at_ns": self.observed_at_ns,
            "positions": list(self.positions),
            "schema": _schema(self.schema_id),
            "sequence": self.sequence,
            "source": self.source,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self._semantic_dict(), "joint_state_fingerprint": self.joint_state_fingerprint}


def verify_joint_state(value: object) -> bool:
    return _verify(
        value,
        SimulatedJointState,
        lambda: SimulatedJointState(
            joint_names=value.joint_names,
            positions=value.positions,
            observed_at_ns=value.observed_at_ns,
            sequence=value.sequence,
            source=value.source,
        ),
    )


@dataclass(frozen=True, slots=True)
class SimulationControllerState:
    controller_contract_id: str
    controller_contract_fingerprint: str
    controller_active: bool
    hardware_active: bool
    state_broadcaster_active: bool
    action_server_available: bool
    claimed_command_interfaces: tuple[str, ...]
    observed_at_ns: int
    schema_id: str = field(init=False, default=CONTROLLER_STATE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    controller_state_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "controller_contract_id",
            identifier(self.controller_contract_id, "controller_contract_id"),
        )
        object.__setattr__(
            self,
            "controller_contract_fingerprint",
            fingerprint(
                self.controller_contract_fingerprint,
                "controller_contract_fingerprint",
            ),
        )
        for name in (
            "controller_active",
            "hardware_active",
            "state_broadcaster_active",
            "action_server_available",
        ):
            if type(getattr(self, name)) is not bool:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
                    f"{name} must be boolean",
                )
        interfaces = _identifier_tuple(
            self.claimed_command_interfaces,
            "claimed_command_interfaces",
            MAX_STAGE9C_JOINTS,
        )
        expected = tuple(f"{name}/position" for name in LEFT_ARM_JOINT_NAMES)
        if interfaces not in {(), expected}:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.CONTROLLER_MISMATCH,
                "controller state exposes substituted or partial command interfaces",
            )
        object.__setattr__(self, "claimed_command_interfaces", interfaces)
        object.__setattr__(
            self,
            "observed_at_ns",
            _timestamp_ns(self.observed_at_ns, "observed_at_ns"),
        )
        object.__setattr__(
            self,
            "controller_state_fingerprint",
            semantic_fingerprint("stage9c-controller-state", self._semantic_dict()),
        )

    @property
    def ready(self) -> bool:
        return (
            self.controller_active
            and self.hardware_active
            and self.state_broadcaster_active
            and self.action_server_available
            and self.claimed_command_interfaces
            == tuple(f"{name}/position" for name in LEFT_ARM_JOINT_NAMES)
        )

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "action_server_available": self.action_server_available,
            "claimed_command_interfaces": list(self.claimed_command_interfaces),
            "controller_active": self.controller_active,
            "controller_contract_fingerprint": self.controller_contract_fingerprint,
            "controller_contract_id": self.controller_contract_id,
            "hardware_active": self.hardware_active,
            "observed_at_ns": self.observed_at_ns,
            "schema": _schema(self.schema_id),
            "state_broadcaster_active": self.state_broadcaster_active,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "controller_state_fingerprint": self.controller_state_fingerprint,
        }


def verify_controller_state(value: object) -> bool:
    return _verify(
        value,
        SimulationControllerState,
        lambda: SimulationControllerState(
            controller_contract_id=value.controller_contract_id,
            controller_contract_fingerprint=value.controller_contract_fingerprint,
            controller_active=value.controller_active,
            hardware_active=value.hardware_active,
            state_broadcaster_active=value.state_broadcaster_active,
            action_server_available=value.action_server_available,
            claimed_command_interfaces=value.claimed_command_interfaces,
            observed_at_ns=value.observed_at_ns,
        ),
    )


def _preflight_reasons(
    proof: SimulationCollisionProof,
    start_state: SimulatedJointState,
    controller_state: SimulationControllerState,
    evaluated_at_ns: int,
    *,
    start_tolerance: float,
    state_freshness_ns: int,
) -> tuple[PreflightReason, ...]:
    reasons: list[PreflightReason] = []
    if not proof.collision_free:
        reasons.append(PreflightReason.COLLISION_REPORTED)
    if not controller_state.ready:
        reasons.append(PreflightReason.CONTROLLER_UNAVAILABLE)
    ages = (
        evaluated_at_ns - start_state.observed_at_ns,
        evaluated_at_ns - controller_state.observed_at_ns,
    )
    if any(age < 0 or age > state_freshness_ns for age in ages):
        reasons.append(PreflightReason.STATE_STALE)
    expected_start = _trajectory_positions(proof.execution_request)[0]
    if any(
        abs(actual - expected) > start_tolerance
        for actual, expected in zip(start_state.positions, expected_start, strict=True)
    ):
        reasons.append(PreflightReason.START_STATE_MISMATCH)
    if reasons:
        return tuple(reasons)
    return (
        PreflightReason.COLLISION_FREE_DENSE_PATH,
        PreflightReason.CONTROLLER_READY,
        PreflightReason.START_STATE_MATCHED,
    )


@dataclass(frozen=True, slots=True)
class SimulationPreflightEvidence:
    collision_proof: SimulationCollisionProof
    start_state: SimulatedJointState
    controller_state: SimulationControllerState
    evaluated_at_ns: int
    status: PreflightStatus
    reasons: tuple[PreflightReason, ...]
    start_tolerance: float = DEFAULT_START_TOLERANCE
    state_freshness_ns: int = DEFAULT_STATE_FRESHNESS_NS
    physical_validation: PhysicalValidationClaim = (
        PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
    )
    schema_id: str = field(init=False, default=PREFLIGHT_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    preflight_evidence_id: str = field(init=False)
    preflight_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_collision_proof(self.collision_proof):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "preflight contains an invalid dense collision proof",
            )
        if not verify_joint_state(self.start_state):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.START_STATE_MISMATCH,
                "preflight contains malformed simulated start state",
            )
        if not verify_controller_state(self.controller_state):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.CONTROLLER_MISMATCH,
                "preflight contains malformed controller state",
            )
        contract = self.collision_proof.execution_request.controller_contract
        if (
            self.controller_state.controller_contract_id
            != contract.controller_contract_id
            or self.controller_state.controller_contract_fingerprint
            != contract.controller_contract_fingerprint
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.CONTROLLER_MISMATCH,
                "controller availability evidence is bound to another contract",
            )
        evaluated_at_ns = _timestamp_ns(self.evaluated_at_ns, "evaluated_at_ns")
        object.__setattr__(self, "evaluated_at_ns", evaluated_at_ns)
        start_tolerance = finite_float(self.start_tolerance, "start_tolerance")
        if not 0.0 < start_tolerance <= DEFAULT_START_TOLERANCE:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.START_STATE_MISMATCH,
                "start-state tolerance exceeds its simulation-only bound",
            )
        object.__setattr__(self, "start_tolerance", start_tolerance)
        object.__setattr__(
            self,
            "state_freshness_ns",
            bounded_integer(
                self.state_freshness_ns,
                "state_freshness_ns",
                1,
                DEFAULT_STATE_FRESHNESS_NS,
            ),
        )
        _closed_enum(self.status, PreflightStatus, "preflight status")
        _closed_enum(
            self.physical_validation,
            PhysicalValidationClaim,
            "physical_validation",
        )
        reasons = _closed_tuple(
            self.reasons,
            "preflight reasons",
            PreflightReason,
            len(PreflightReason),
            minimum=1,
        )
        if len(reasons) != len(set(reasons)):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
                "preflight reasons must be unique",
            )
        expected_reasons = _preflight_reasons(
            self.collision_proof,
            self.start_state,
            self.controller_state,
            self.evaluated_at_ns,
            start_tolerance=self.start_tolerance,
            state_freshness_ns=self.state_freshness_ns,
        )
        positive = expected_reasons == (
            PreflightReason.COLLISION_FREE_DENSE_PATH,
            PreflightReason.CONTROLLER_READY,
            PreflightReason.START_STATE_MATCHED,
        )
        expected_status = (
            PreflightStatus.READY_FOR_SIMULATION_EXECUTION
            if positive
            else PreflightStatus.REJECTED
        )
        if (
            reasons != expected_reasons
            or self.status is not expected_status
            or self.physical_validation
            is not PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "preflight status does not match current collision/controller/start evidence",
            )
        object.__setattr__(self, "reasons", reasons)
        identity, content = content_identity(
            "stage9c-preflight-evidence",
            self._semantic_dict(),
        )
        object.__setattr__(self, "preflight_evidence_id", identity)
        object.__setattr__(self, "preflight_evidence_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9C preflight evidence")

    @property
    def execution_request(self) -> SimulationExecutionRequest:
        return self.collision_proof.execution_request

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "collision_proof": self.collision_proof.as_dict(),
            "controller_state": self.controller_state.as_dict(),
            "evaluated_at_ns": self.evaluated_at_ns,
            "physical_validation": self.physical_validation.value,
            "reasons": [reason.value for reason in self.reasons],
            "schema": _schema(self.schema_id),
            "start_state": self.start_state.as_dict(),
            "start_tolerance": self.start_tolerance,
            "state_freshness_ns": self.state_freshness_ns,
            "status": self.status.value,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "preflight_evidence_fingerprint": self.preflight_evidence_fingerprint,
            "preflight_evidence_id": self.preflight_evidence_id,
        }


def verify_preflight_evidence(value: object) -> bool:
    return _verify(
        value,
        SimulationPreflightEvidence,
        lambda: SimulationPreflightEvidence(
            collision_proof=value.collision_proof,
            start_state=value.start_state,
            controller_state=value.controller_state,
            evaluated_at_ns=value.evaluated_at_ns,
            status=value.status,
            reasons=value.reasons,
            start_tolerance=value.start_tolerance,
            state_freshness_ns=value.state_freshness_ns,
            physical_validation=value.physical_validation,
        ),
    )


@dataclass(frozen=True, slots=True)
class SimulationGoalPoint:
    positions: tuple[float, ...]
    time_from_start: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "positions",
            _position_tuple(self.positions, "goal point positions"),
        )
        time_value = finite_float(self.time_from_start, "time_from_start")
        if time_value < 0.0:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.TRAJECTORY_MISMATCH,
                "goal time_from_start cannot be negative",
            )
        object.__setattr__(self, "time_from_start", time_value)

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            "positions": list(self.positions),
            "time_from_start": self.time_from_start,
        }


def expected_goal_points(
    request: SimulationExecutionRequest,
) -> tuple[SimulationGoalPoint, ...]:
    if not verify_execution_request(request):
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.UPSTREAM_INTEGRITY,
            "goal construction requires a verified execution request",
        )
    try:
        return tuple(
            SimulationGoalPoint(
                positions=tuple(item.position for item in point.positions),
                time_from_start=point.time_from_start,
            )
            for point in request.trajectory.points
        )
    except (AssertionError, AttributeError, ArithmeticError, TypeError, ValueError) as error:
        raise SimulationExecutionValidationError(
            SimulationExecutionFailureCode.TRAJECTORY_MISMATCH,
            "Stage 9B trajectory cannot be mapped to a position-only goal",
        ) from error


@dataclass(frozen=True, slots=True)
class SimulationExecutionGoal:
    preflight_evidence: SimulationPreflightEvidence
    action_endpoint: str
    joint_names: tuple[str, ...]
    points: tuple[SimulationGoalPoint, ...]
    execution_timeout_ns: int
    schema_id: str = field(init=False, default=EXECUTION_GOAL_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    execution_goal_id: str = field(init=False)
    execution_goal_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_preflight_evidence(self.preflight_evidence):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "execution goal contains malformed preflight evidence",
            )
        if (
            self.preflight_evidence.status
            is not PreflightStatus.READY_FOR_SIMULATION_EXECUTION
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.COLLISION_PREFLIGHT,
                "no action goal may be created after rejected preflight",
            )
        action_endpoint = bounded_text(self.action_endpoint, "action_endpoint", 256)
        names = _identifier_tuple(
            self.joint_names,
            "goal joint_names",
            MAX_STAGE9C_JOINTS,
            minimum=MAX_STAGE9C_JOINTS,
        )
        points = _closed_tuple(
            self.points,
            "goal points",
            SimulationGoalPoint,
            MAX_STAGE9C_TRAJECTORY_POINTS,
            minimum=2,
        )
        request = self.preflight_evidence.execution_request
        if (
            action_endpoint != request.controller_contract.action_endpoint
            or names != request.controller_contract.joint_names
            or points != expected_goal_points(request)
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.TRAJECTORY_MISMATCH,
                "action goal differs from the exact accepted Stage 9B trajectory",
            )
        expected_timeout = round(
            (points[-1].time_from_start * 1_000_000_000)
        ) + DEFAULT_EXECUTION_TIMEOUT_MARGIN_NS
        timeout = bounded_integer(
            self.execution_timeout_ns,
            "execution_timeout_ns",
            1,
            MAX_EXECUTION_TIMEOUT_NS,
        )
        if timeout != expected_timeout:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.EXECUTION_TIMEOUT,
                "execution timeout must equal reviewed duration plus fixed margin",
            )
        object.__setattr__(self, "action_endpoint", action_endpoint)
        object.__setattr__(self, "joint_names", names)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "execution_timeout_ns", timeout)
        identity, content = content_identity("stage9c-execution-goal", self._semantic_dict())
        object.__setattr__(self, "execution_goal_id", identity)
        object.__setattr__(self, "execution_goal_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9C execution goal")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "action_endpoint": self.action_endpoint,
            "execution_timeout_ns": self.execution_timeout_ns,
            "joint_names": list(self.joint_names),
            "points": [point.as_dict() for point in self.points],
            "preflight_evidence": self.preflight_evidence.as_dict(),
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "execution_goal_fingerprint": self.execution_goal_fingerprint,
            "execution_goal_id": self.execution_goal_id,
        }


def verify_execution_goal(value: object) -> bool:
    return _verify(
        value,
        SimulationExecutionGoal,
        lambda: SimulationExecutionGoal(
            preflight_evidence=value.preflight_evidence,
            action_endpoint=value.action_endpoint,
            joint_names=value.joint_names,
            points=value.points,
            execution_timeout_ns=value.execution_timeout_ns,
        ),
    )


@dataclass(frozen=True, slots=True)
class SimulationExecutionObservation:
    execution_goal_id: str
    execution_goal_fingerprint: str
    acceptance: GoalAcceptance
    outcome: SimulationExecutionOutcome
    controller_error_code: int
    started_at_ns: int
    completed_at_ns: int
    starting_positions: tuple[float, ...]
    ending_positions: tuple[float, ...] | None
    final_target_positions: tuple[float, ...]
    final_joint_errors: tuple[float, ...] | None
    feedback_samples_observed: int
    cancellation_requested: bool
    cancellation_confirmed: bool
    timed_out: bool
    detail: str
    schema_id: str = field(init=False, default=EXECUTION_OBSERVATION_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    observation_id: str = field(init=False)
    observation_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_goal_id",
            identifier(self.execution_goal_id, "execution_goal_id"),
        )
        object.__setattr__(
            self,
            "execution_goal_fingerprint",
            fingerprint(self.execution_goal_fingerprint, "execution_goal_fingerprint"),
        )
        _closed_enum(self.acceptance, GoalAcceptance, "goal acceptance")
        _closed_enum(self.outcome, SimulationExecutionOutcome, "execution outcome")
        object.__setattr__(
            self,
            "controller_error_code",
            bounded_integer(
                self.controller_error_code,
                "controller_error_code",
                -1000,
                1000,
            ),
        )
        started = _timestamp_ns(self.started_at_ns, "started_at_ns")
        completed = _timestamp_ns(self.completed_at_ns, "completed_at_ns")
        if completed < started:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.FEEDBACK_INVALID,
                "execution completion precedes its start",
            )
        object.__setattr__(self, "started_at_ns", started)
        object.__setattr__(self, "completed_at_ns", completed)
        starting = _position_tuple(self.starting_positions, "starting_positions")
        target = _position_tuple(self.final_target_positions, "final_target_positions")
        ending = (
            None
            if self.ending_positions is None
            else _position_tuple(self.ending_positions, "ending_positions")
        )
        errors = (
            None
            if self.final_joint_errors is None
            else _position_tuple(self.final_joint_errors, "final_joint_errors")
        )
        if errors is not None and any(value < 0.0 for value in errors):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.FEEDBACK_INVALID,
                "final joint errors cannot be negative",
            )
        if (ending is None) != (errors is None):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.FEEDBACK_INVALID,
                "ending positions and final errors must appear together",
            )
        if ending is not None:
            expected_errors = tuple(
                abs(actual - expected)
                for actual, expected in zip(ending, target, strict=True)
            )
            if errors != expected_errors:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.FEEDBACK_INVALID,
                    "final joint errors differ from observed positions",
                )
        object.__setattr__(self, "starting_positions", starting)
        object.__setattr__(self, "ending_positions", ending)
        object.__setattr__(self, "final_target_positions", target)
        object.__setattr__(self, "final_joint_errors", errors)
        object.__setattr__(
            self,
            "feedback_samples_observed",
            bounded_integer(
                self.feedback_samples_observed,
                "feedback_samples_observed",
                0,
                1_000_000,
            ),
        )
        for name in (
            "cancellation_requested",
            "cancellation_confirmed",
            "timed_out",
        ):
            if type(getattr(self, name)) is not bool:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
                    f"{name} must be boolean",
                )
        object.__setattr__(self, "detail", bounded_text(self.detail, "detail"))
        if self.cancellation_confirmed and not self.cancellation_requested:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.EXECUTION_CANCELED,
                "cancellation cannot be confirmed before it is requested",
            )
        accepted = self.acceptance is GoalAcceptance.ACCEPTED
        completed_success = (
            self.outcome
            is SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED
        )
        if completed_success:
            if (
                not accepted
                or self.controller_error_code != 0
                or ending is None
                or errors is None
                or any(value > DEFAULT_FINAL_TOLERANCE for value in errors)
                or self.feedback_samples_observed < 1
                or self.cancellation_requested
                or self.cancellation_confirmed
                or self.timed_out
            ):
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.FEEDBACK_INVALID,
                    "simulation completion lacks exact successful action and feedback evidence",
                )
        elif self.outcome is SimulationExecutionOutcome.CONTROLLER_UNAVAILABLE:
            if accepted or self.acceptance is not GoalAcceptance.NOT_SENT:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.ACTION_UNAVAILABLE,
                    "unavailable controller cannot accept a goal",
                )
        elif self.outcome is SimulationExecutionOutcome.GOAL_REJECTED:
            if self.acceptance is not GoalAcceptance.REJECTED:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.GOAL_REJECTED,
                    "goal rejection requires explicit rejected acceptance",
                )
        elif self.outcome is SimulationExecutionOutcome.TIMED_OUT:
            if not accepted or not self.timed_out or not self.cancellation_requested:
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.EXECUTION_TIMEOUT,
                    "timeout must request cancellation of an accepted goal",
                )
        elif self.outcome is SimulationExecutionOutcome.CANCELED:
            if (
                not accepted
                or not self.cancellation_requested
                or not self.cancellation_confirmed
                or self.timed_out
            ):
                raise SimulationExecutionValidationError(
                    SimulationExecutionFailureCode.EXECUTION_CANCELED,
                    "canceled outcome lacks confirmed accepted-goal cancellation",
                )
        elif not accepted:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.MALFORMED_ARTIFACT,
                "post-acceptance outcome cannot be reported for an unsent goal",
            )
        if self.outcome is not SimulationExecutionOutcome.TIMED_OUT and self.timed_out:
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.EXECUTION_TIMEOUT,
                "only a timeout outcome may set timed_out",
            )
        identity, content = content_identity(
            "stage9c-execution-observation",
            self._semantic_dict(),
        )
        object.__setattr__(self, "observation_id", identity)
        object.__setattr__(self, "observation_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9C execution observation")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "acceptance": self.acceptance.value,
            "cancellation_confirmed": self.cancellation_confirmed,
            "cancellation_requested": self.cancellation_requested,
            "completed_at_ns": self.completed_at_ns,
            "controller_error_code": self.controller_error_code,
            "detail": self.detail,
            "ending_positions": (
                None if self.ending_positions is None else list(self.ending_positions)
            ),
            "execution_goal_fingerprint": self.execution_goal_fingerprint,
            "execution_goal_id": self.execution_goal_id,
            "feedback_samples_observed": self.feedback_samples_observed,
            "final_joint_errors": (
                None
                if self.final_joint_errors is None
                else list(self.final_joint_errors)
            ),
            "final_target_positions": list(self.final_target_positions),
            "outcome": self.outcome.value,
            "schema": _schema(self.schema_id),
            "started_at_ns": self.started_at_ns,
            "starting_positions": list(self.starting_positions),
            "timed_out": self.timed_out,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "observation_fingerprint": self.observation_fingerprint,
            "observation_id": self.observation_id,
        }


def verify_execution_observation(value: object) -> bool:
    return _verify(
        value,
        SimulationExecutionObservation,
        lambda: SimulationExecutionObservation(
            execution_goal_id=value.execution_goal_id,
            execution_goal_fingerprint=value.execution_goal_fingerprint,
            acceptance=value.acceptance,
            outcome=value.outcome,
            controller_error_code=value.controller_error_code,
            started_at_ns=value.started_at_ns,
            completed_at_ns=value.completed_at_ns,
            starting_positions=value.starting_positions,
            ending_positions=value.ending_positions,
            final_target_positions=value.final_target_positions,
            final_joint_errors=value.final_joint_errors,
            feedback_samples_observed=value.feedback_samples_observed,
            cancellation_requested=value.cancellation_requested,
            cancellation_confirmed=value.cancellation_confirmed,
            timed_out=value.timed_out,
            detail=value.detail,
        ),
    )


def _motion_status(observation: SimulationExecutionObservation) -> SimulationMotionStatus:
    if observation.acceptance is GoalAcceptance.NOT_SENT:
        return SimulationMotionStatus.NOT_SENT
    if (
        observation.outcome
        is SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED
    ):
        return SimulationMotionStatus.SIMULATION_EXECUTED
    return SimulationMotionStatus.ATTEMPTED


@dataclass(frozen=True, slots=True)
class SimulationExecutionResult:
    execution_goal: SimulationExecutionGoal
    observation: SimulationExecutionObservation
    status: SimulationExecutionResultStatus
    motion_status: SimulationMotionStatus
    authority: SimulationAuthority = SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
    physical_validation: PhysicalValidationClaim = (
        PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
    )
    hardware_authority: HardwareAuthority = HardwareAuthority.NO_HARDWARE_AUTHORITY
    production_runtime_authority: ProductionRuntimeAuthority = (
        ProductionRuntimeAuthority.NO_PRODUCTION_RUNTIME_AUTHORITY
    )
    schema_id: str = field(init=False, default=EXECUTION_RESULT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    execution_result_id: str = field(init=False)
    execution_result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_execution_goal(self.execution_goal):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.UPSTREAM_INTEGRITY,
                "result contains an invalid Stage 9C goal",
            )
        if not verify_execution_observation(self.observation):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.FEEDBACK_INVALID,
                "result contains an invalid simulation observation",
            )
        if (
            self.observation.execution_goal_id != self.execution_goal.execution_goal_id
            or self.observation.execution_goal_fingerprint
            != self.execution_goal.execution_goal_fingerprint
            or self.observation.starting_positions
            != self.execution_goal.preflight_evidence.start_state.positions
            or self.observation.final_target_positions
            != self.execution_goal.points[-1].positions
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.TRAJECTORY_MISMATCH,
                "observed run is bound to another request, start, or target",
            )
        _closed_enum(self.status, SimulationExecutionResultStatus, "result status")
        _closed_enum(self.motion_status, SimulationMotionStatus, "motion status")
        _closed_enum(self.authority, SimulationAuthority, "authority")
        _closed_enum(
            self.physical_validation,
            PhysicalValidationClaim,
            "physical_validation",
        )
        _closed_enum(self.hardware_authority, HardwareAuthority, "hardware_authority")
        _closed_enum(
            self.production_runtime_authority,
            ProductionRuntimeAuthority,
            "production_runtime_authority",
        )
        success = (
            self.observation.outcome
            is SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED
        )
        if (
            self.status
            is not (
                SimulationExecutionResultStatus.COMPLETED
                if success
                else SimulationExecutionResultStatus.FAILED
            )
            or self.motion_status is not _motion_status(self.observation)
            or self.authority is not SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
            or self.physical_validation
            is not PhysicalValidationClaim.NOT_PHYSICALLY_VALIDATED
            or self.hardware_authority is not HardwareAuthority.NO_HARDWARE_AUTHORITY
            or self.production_runtime_authority
            is not ProductionRuntimeAuthority.NO_PRODUCTION_RUNTIME_AUTHORITY
        ):
            raise SimulationExecutionValidationError(
                SimulationExecutionFailureCode.SIMULATION_BOUNDARY,
                "result status or authority claims contradict the observed simulation run",
            )
        identity, content = content_identity(
            "stage9c-execution-result",
            self._semantic_dict(),
        )
        object.__setattr__(self, "execution_result_id", identity)
        object.__setattr__(self, "execution_result_fingerprint", content)
        assert_artifact_size(self.as_dict(), "Stage 9C execution result")

    def _semantic_dict(self) -> dict[str, JSONValue]:
        return {
            "authority": self.authority.value,
            "execution_goal": self.execution_goal.as_dict(),
            "hardware_authority": self.hardware_authority.value,
            "motion_status": self.motion_status.value,
            "observation": self.observation.as_dict(),
            "physical_validation": self.physical_validation.value,
            "production_runtime_authority": self.production_runtime_authority.value,
            "schema": _schema(self.schema_id),
            "status": self.status.value,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self._semantic_dict(),
            "execution_result_fingerprint": self.execution_result_fingerprint,
            "execution_result_id": self.execution_result_id,
        }


def verify_execution_result(value: object) -> bool:
    return _verify(
        value,
        SimulationExecutionResult,
        lambda: SimulationExecutionResult(
            execution_goal=value.execution_goal,
            observation=value.observation,
            status=value.status,
            motion_status=value.motion_status,
            authority=value.authority,
            physical_validation=value.physical_validation,
            hardware_authority=value.hardware_authority,
            production_runtime_authority=value.production_runtime_authority,
        ),
    )
