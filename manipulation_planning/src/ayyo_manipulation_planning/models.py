"""Immutable Stage 9A manipulation-planning evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .canonical import (
    JSONValue,
    MAX_CHAIN_JOINTS,
    MAX_COLLISION_OBJECTS,
    MAX_LINKS,
    MAX_PLANNING_JOINTS,
    MAX_ROBOT_JOINTS,
    MAX_WAYPOINTS,
    SCHEMA_VERSION,
    assert_artifact_size,
    bounded_items,
    bounded_text,
    content_identity,
    finite_float,
    finite_vector,
    fingerprint,
    identifier,
)
from .errors import PlanningFailureCode, PlanningValidationError


LEFT_ARM_GROUP_NAME = "left_arm"
LEFT_ARM_BASE_LINK = "left_shoulder_mount_link"
LEFT_ARM_TIP_LINK = "left_hand_link"
LEFT_ARM_JOINT_NAMES = (
    "left_shoulder_yaw_joint",
    "left_shoulder_pitch_joint",
    "left_elbow_flex_joint",
    "left_wrist_yaw_joint",
)
LEFT_ARM_CHAIN_JOINT_NAMES = (
    "left_shoulder_yaw_joint",
    "left_shoulder_pitch_joint",
    "left_upper_arm_to_elbow_joint",
    "left_elbow_flex_joint",
    "left_wrist_yaw_joint",
    "left_wrist_to_hand_joint",
)
PLANNING_FRAME = "base_link"
PLANNER_ID = "ayyo.bounded-linear-joint-space.v1"
COLLISION_BACKEND_ID = "moveit.planning-scene.v1"

ROBOT_MODEL_SCHEMA_ID = "ayyo.manipulation-planning.robot-model.v1"
ROBOT_JOINT_SCHEMA_ID = "ayyo.manipulation-planning.robot-joint.v1"
JOINT_CATALOG_SCHEMA_ID = "ayyo.manipulation-planning.joint-catalog.v1"
MANIPULATOR_GROUP_SCHEMA_ID = "ayyo.manipulation-planning.group.v1"
JOINT_STATE_SCHEMA_ID = "ayyo.manipulation-planning.joint-state.v1"
JOINT_GOAL_SCHEMA_ID = "ayyo.manipulation-planning.joint-goal.v1"
PLANNER_CONFIGURATION_SCHEMA_ID = "ayyo.manipulation-planning.planner-config.v1"
COLLISION_BOX_SCHEMA_ID = "ayyo.manipulation-planning.collision-box.v1"
PLANNING_SCENE_SCHEMA_ID = "ayyo.manipulation-planning.scene.v1"
PLANNING_REQUEST_SCHEMA_ID = "ayyo.manipulation-planning.request.v1"
PLAN_EVIDENCE_SCHEMA_ID = "ayyo.manipulation-planning.plan-evidence.v1"
PLANNING_DECISION_SCHEMA_ID = "ayyo.manipulation-planning.decision.v1"


class RobotJointKind(StrEnum):
    FIXED = "fixed"
    REVOLUTE = "revolute"


class PlanEvidenceStatus(StrEnum):
    COLLISION_FREE_PLAN_REPORTED = "collision_free_plan_reported"
    START_STATE_COLLISION_REPORTED = "start_state_collision_reported"
    GOAL_STATE_COLLISION_REPORTED = "goal_state_collision_reported"
    PATH_COLLISION_REPORTED = "path_collision_reported"
    NO_PLAN_REPORTED = "no_plan_reported"


class PlanningDisposition(StrEnum):
    PLAN_AVAILABLE_FOR_REVIEW = "plan_available_for_review"
    REJECTED = "rejected"


class ExecutionDisposition(StrEnum):
    NOT_EXECUTED = "not_executed"


class PlanningDecisionReason(StrEnum):
    COLLISION_FREE_PLAN_EVIDENCE_ACCEPTED = "collision_free_plan_evidence_accepted"
    START_STATE_COLLISION = "start_state_collision"
    GOAL_STATE_COLLISION = "goal_state_collision"
    PATH_COLLISION = "path_collision"
    NO_PLAN_FOUND = "no_plan_found"
    EXECUTION_OUT_OF_SCOPE = "execution_out_of_scope"
    PHYSICAL_VALIDATION_ABSENT = "physical_validation_absent"


_STATUS_REASON = {
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


def _schema(schema_id: str) -> dict[str, JSONValue]:
    return {"id": schema_id, "version": SCHEMA_VERSION}


def _closed_enum(value: object, enum_type: type[StrEnum], field_name: str) -> StrEnum:
    if type(value) is not enum_type:
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must use its closed enum",
        )
    return value


def _identifier_tuple(
    value: object,
    field_name: str,
    maximum: int,
    *,
    allow_empty: bool = False,
    sort_items: bool = False,
) -> tuple[str, ...]:
    if type(value) not in {tuple, list}:
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} must be a bounded sequence",
        )
    values = tuple(identifier(item, field_name) for item in value)
    if (not allow_empty and not values) or len(values) > maximum:
        raise PlanningValidationError(
            PlanningFailureCode.RESOURCE_LIMIT,
            f"{field_name} violates its resource bound",
        )
    if len(set(values)) != len(values):
        raise PlanningValidationError(
            PlanningFailureCode.MALFORMED_ARTIFACT,
            f"{field_name} contains duplicates",
        )
    return tuple(sorted(values)) if sort_items else values


def _verify(instance: object, expected_type: type, builder) -> bool:
    if type(instance) is not expected_type:
        return False
    try:
        return builder() == instance
    except (AttributeError, TypeError, ValueError, PlanningValidationError):
        return False


@dataclass(frozen=True, slots=True)
class RobotModelIdentity:
    robot_name: str
    root_link: str
    description_source: str
    description_fingerprint: str
    link_names: tuple[str, ...]
    joint_names: tuple[str, ...]
    schema_id: str = field(init=False, default=ROBOT_MODEL_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    robot_model_id: str = field(init=False)
    robot_model_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "robot_name", identifier(self.robot_name, "robot_name"))
        object.__setattr__(self, "root_link", identifier(self.root_link, "root_link"))
        object.__setattr__(
            self,
            "description_source",
            identifier(self.description_source, "description_source"),
        )
        object.__setattr__(
            self,
            "description_fingerprint",
            fingerprint(self.description_fingerprint, "description_fingerprint"),
        )
        links = _identifier_tuple(
            self.link_names, "link_names", MAX_LINKS, sort_items=True
        )
        joints = _identifier_tuple(
            self.joint_names, "joint_names", MAX_ROBOT_JOINTS, sort_items=True
        )
        if self.root_link not in links:
            raise PlanningValidationError(
                PlanningFailureCode.MALFORMED_MODEL,
                "robot root link is absent from the authoritative link catalog",
            )
        object.__setattr__(self, "link_names", links)
        object.__setattr__(self, "joint_names", joints)
        identity, content = content_identity("manipulation-robot-model", self.semantic_document())
        object.__setattr__(self, "robot_model_id", identity)
        object.__setattr__(self, "robot_model_fingerprint", content)
        assert_artifact_size(self.as_dict(), "robot model identity")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "description_fingerprint": self.description_fingerprint,
            "description_source": self.description_source,
            "joint_names": list(self.joint_names),
            "link_names": list(self.link_names),
            "robot_name": self.robot_name,
            "root_link": self.root_link,
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self.semantic_document(),
            "robot_model_fingerprint": self.robot_model_fingerprint,
            "robot_model_id": self.robot_model_id,
        }


def verify_robot_model_identity(model: object) -> bool:
    return _verify(
        model,
        RobotModelIdentity,
        lambda: RobotModelIdentity(
            robot_name=model.robot_name,
            root_link=model.root_link,
            description_source=model.description_source,
            description_fingerprint=model.description_fingerprint,
            link_names=model.link_names,
            joint_names=model.joint_names,
        ),
    )


@dataclass(frozen=True, slots=True)
class RobotJointReference:
    joint_name: str
    kind: RobotJointKind
    parent_link: str
    child_link: str
    origin_xyz: tuple[float, float, float]
    origin_rpy: tuple[float, float, float]
    axis_xyz: tuple[float, float, float] | None
    lower: float | None
    upper: float | None
    effort: float | None
    velocity: float | None
    schema_id: str = field(init=False, default=ROBOT_JOINT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    joint_evidence_id: str = field(init=False)
    joint_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "joint_name", identifier(self.joint_name, "joint_name"))
        object.__setattr__(self, "parent_link", identifier(self.parent_link, "parent_link"))
        object.__setattr__(self, "child_link", identifier(self.child_link, "child_link"))
        _closed_enum(self.kind, RobotJointKind, "joint kind")
        object.__setattr__(self, "origin_xyz", finite_vector(self.origin_xyz, "origin_xyz", 3))
        object.__setattr__(self, "origin_rpy", finite_vector(self.origin_rpy, "origin_rpy", 3))
        if self.kind is RobotJointKind.FIXED:
            if any(value is not None for value in (self.axis_xyz, self.lower, self.upper, self.effort, self.velocity)):
                raise PlanningValidationError(
                    PlanningFailureCode.MALFORMED_MODEL,
                    "fixed joint evidence cannot carry movable-joint values",
                )
        else:
            axis = finite_vector(self.axis_xyz, "axis_xyz", 3)
            if axis == (0.0, 0.0, 0.0):
                raise PlanningValidationError(
                    PlanningFailureCode.MALFORMED_MODEL,
                    "revolute joint axis cannot be zero",
                )
            lower = finite_float(self.lower, "joint lower limit")
            upper = finite_float(self.upper, "joint upper limit")
            effort = finite_float(self.effort, "joint effort limit")
            velocity = finite_float(self.velocity, "joint velocity limit")
            if lower >= upper or effort <= 0.0 or velocity <= 0.0:
                raise PlanningValidationError(
                    PlanningFailureCode.MALFORMED_MODEL,
                    "revolute joint limits are invalid",
                )
            object.__setattr__(self, "axis_xyz", axis)
            object.__setattr__(self, "lower", lower)
            object.__setattr__(self, "upper", upper)
            object.__setattr__(self, "effort", effort)
            object.__setattr__(self, "velocity", velocity)
        identity, content = content_identity("manipulation-joint-evidence", self.semantic_document())
        object.__setattr__(self, "joint_evidence_id", identity)
        object.__setattr__(self, "joint_evidence_fingerprint", content)
        assert_artifact_size(self.as_dict(), "robot joint reference")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "axis_xyz": None if self.axis_xyz is None else list(self.axis_xyz),
            "child_link": self.child_link,
            "effort": self.effort,
            "joint_name": self.joint_name,
            "kind": self.kind.value,
            "lower": self.lower,
            "origin_rpy": list(self.origin_rpy),
            "origin_xyz": list(self.origin_xyz),
            "parent_link": self.parent_link,
            "schema": _schema(self.schema_id),
            "upper": self.upper,
            "velocity": self.velocity,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self.semantic_document(),
            "joint_evidence_fingerprint": self.joint_evidence_fingerprint,
            "joint_evidence_id": self.joint_evidence_id,
        }


def verify_robot_joint_reference(joint: object) -> bool:
    return _verify(
        joint,
        RobotJointReference,
        lambda: RobotJointReference(
            joint_name=joint.joint_name,
            kind=joint.kind,
            parent_link=joint.parent_link,
            child_link=joint.child_link,
            origin_xyz=joint.origin_xyz,
            origin_rpy=joint.origin_rpy,
            axis_xyz=joint.axis_xyz,
            lower=joint.lower,
            upper=joint.upper,
            effort=joint.effort,
            velocity=joint.velocity,
        ),
    )


@dataclass(frozen=True, slots=True)
class ManipulatorJointCatalog:
    robot_model: RobotModelIdentity
    group_name: str
    base_link: str
    tip_link: str
    chain_joints: tuple[RobotJointReference, ...]
    planning_joint_names: tuple[str, ...]
    schema_id: str = field(init=False, default=JOINT_CATALOG_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    joint_catalog_id: str = field(init=False)
    joint_catalog_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_robot_model_identity(self.robot_model):
            raise PlanningValidationError(
                PlanningFailureCode.MODEL_MISMATCH,
                "joint catalog requires an exact robot model identity",
            )
        group_name = identifier(self.group_name, "group_name")
        base_link = identifier(self.base_link, "base_link")
        tip_link = identifier(self.tip_link, "tip_link")
        if (group_name, base_link, tip_link) != (
            LEFT_ARM_GROUP_NAME,
            LEFT_ARM_BASE_LINK,
            LEFT_ARM_TIP_LINK,
        ):
            raise PlanningValidationError(
                PlanningFailureCode.WRONG_MANIPULATOR_GROUP,
                "Stage 9A accepts only the reviewed left-arm chain",
            )
        joints = bounded_items(
            self.chain_joints,
            "chain_joints",
            RobotJointReference,
            MAX_CHAIN_JOINTS,
        )
        if any(not verify_robot_joint_reference(item) for item in joints):
            raise PlanningValidationError(
                PlanningFailureCode.MALFORMED_MODEL,
                "joint catalog contains invalid joint evidence",
            )
        names = [item.joint_name for item in joints]
        if len(names) != len(set(names)):
            raise PlanningValidationError(
                PlanningFailureCode.DUPLICATE_JOINT,
                "left-arm chain contains duplicate joints",
            )
        if tuple(names) != LEFT_ARM_CHAIN_JOINT_NAMES:
            raise PlanningValidationError(
                PlanningFailureCode.WRONG_MANIPULATOR_GROUP,
                "left-arm chain differs from the reviewed authoritative joint sequence",
            )
        if joints[0].parent_link != base_link or joints[-1].child_link != tip_link:
            raise PlanningValidationError(
                PlanningFailureCode.MALFORMED_MODEL,
                "left-arm chain endpoints do not match its group identity",
            )
        if any(left.child_link != right.parent_link for left, right in zip(joints, joints[1:])):
            raise PlanningValidationError(
                PlanningFailureCode.MALFORMED_MODEL,
                "left-arm joint chain is not contiguous",
            )
        if any(item.joint_name not in self.robot_model.joint_names for item in joints):
            raise PlanningValidationError(
                PlanningFailureCode.MODEL_MISMATCH,
                "left-arm chain names a joint outside the robot model",
            )
        planning_names = _identifier_tuple(
            self.planning_joint_names,
            "planning_joint_names",
            MAX_PLANNING_JOINTS,
        )
        derived = tuple(item.joint_name for item in joints if item.kind is RobotJointKind.REVOLUTE)
        if planning_names != derived or planning_names != LEFT_ARM_JOINT_NAMES:
            raise PlanningValidationError(
                PlanningFailureCode.WRONG_MANIPULATOR_GROUP,
                "planning joints differ from the authoritative Stage 9A left arm",
            )
        object.__setattr__(self, "group_name", group_name)
        object.__setattr__(self, "base_link", base_link)
        object.__setattr__(self, "tip_link", tip_link)
        object.__setattr__(self, "chain_joints", joints)
        object.__setattr__(self, "planning_joint_names", planning_names)
        identity, content = content_identity("manipulation-joint-catalog", self.semantic_document())
        object.__setattr__(self, "joint_catalog_id", identity)
        object.__setattr__(self, "joint_catalog_fingerprint", content)
        assert_artifact_size(self.as_dict(), "manipulator joint catalog")

    @property
    def fixed_joint_names(self) -> tuple[str, ...]:
        return tuple(item.joint_name for item in self.chain_joints if item.kind is RobotJointKind.FIXED)

    def joint_for(self, name: str) -> RobotJointReference | None:
        return next((item for item in self.chain_joints if item.joint_name == name), None)

    def validate_positions(self, positions: tuple["JointPosition", ...]) -> None:
        names = tuple(item.joint_name for item in positions)
        if len(names) != len(set(names)):
            raise PlanningValidationError(
                PlanningFailureCode.DUPLICATE_JOINT,
                "joint positions contain a duplicate joint",
            )
        expected = self.planning_joint_names
        for name in names:
            if name not in expected:
                chain_joint = self.joint_for(name)
                if chain_joint is not None and chain_joint.kind is RobotJointKind.FIXED:
                    code = PlanningFailureCode.FIXED_JOINT
                elif name in self.robot_model.joint_names:
                    code = PlanningFailureCode.WRONG_ARM_JOINT
                else:
                    code = PlanningFailureCode.UNKNOWN_JOINT
                raise PlanningValidationError(code, f"joint {name!r} is not a movable left-arm planning joint")
        if set(names) != set(expected):
            raise PlanningValidationError(
                PlanningFailureCode.MISSING_JOINT,
                "joint positions omit a required left-arm planning joint",
            )
        if names != expected:
            raise PlanningValidationError(
                PlanningFailureCode.JOINT_ORDER_MISMATCH,
                "joint positions are not in authoritative chain order",
            )
        for position in positions:
            joint = self.joint_for(position.joint_name)
            assert joint is not None and joint.lower is not None and joint.upper is not None
            if position.position < joint.lower:
                raise PlanningValidationError(
                    PlanningFailureCode.BELOW_JOINT_LIMIT,
                    f"{position.joint_name} is below its authoritative URDF lower limit",
                )
            if position.position > joint.upper:
                raise PlanningValidationError(
                    PlanningFailureCode.ABOVE_JOINT_LIMIT,
                    f"{position.joint_name} is above its authoritative URDF upper limit",
                )

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "base_link": self.base_link,
            "chain_joints": [item.as_dict() for item in self.chain_joints],
            "group_name": self.group_name,
            "planning_joint_names": list(self.planning_joint_names),
            "robot_model": self.robot_model.as_dict(),
            "schema": _schema(self.schema_id),
            "tip_link": self.tip_link,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self.semantic_document(),
            "joint_catalog_fingerprint": self.joint_catalog_fingerprint,
            "joint_catalog_id": self.joint_catalog_id,
        }


def verify_manipulator_joint_catalog(catalog: object) -> bool:
    return _verify(
        catalog,
        ManipulatorJointCatalog,
        lambda: ManipulatorJointCatalog(
            robot_model=catalog.robot_model,
            group_name=catalog.group_name,
            base_link=catalog.base_link,
            tip_link=catalog.tip_link,
            chain_joints=catalog.chain_joints,
            planning_joint_names=catalog.planning_joint_names,
        ),
    )


@dataclass(frozen=True, slots=True)
class ManipulatorGroupIdentity:
    robot_model_id: str
    robot_model_fingerprint: str
    joint_catalog_id: str
    joint_catalog_fingerprint: str
    group_name: str
    base_link: str
    tip_link: str
    joint_names: tuple[str, ...]
    fixed_joint_names: tuple[str, ...]
    schema_id: str = field(init=False, default=MANIPULATOR_GROUP_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    group_id: str = field(init=False)
    group_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "robot_model_id",
            "robot_model_fingerprint",
            "joint_catalog_id",
            "joint_catalog_fingerprint",
        ):
            object.__setattr__(self, name, fingerprint(getattr(self, name), name))
        object.__setattr__(self, "group_name", identifier(self.group_name, "group_name"))
        object.__setattr__(self, "base_link", identifier(self.base_link, "base_link"))
        object.__setattr__(self, "tip_link", identifier(self.tip_link, "tip_link"))
        joints = _identifier_tuple(self.joint_names, "joint_names", MAX_PLANNING_JOINTS)
        fixed = _identifier_tuple(
            self.fixed_joint_names,
            "fixed_joint_names",
            MAX_CHAIN_JOINTS,
            allow_empty=True,
        )
        if (
            self.group_name != LEFT_ARM_GROUP_NAME
            or self.base_link != LEFT_ARM_BASE_LINK
            or self.tip_link != LEFT_ARM_TIP_LINK
            or joints != LEFT_ARM_JOINT_NAMES
        ):
            raise PlanningValidationError(
                PlanningFailureCode.WRONG_MANIPULATOR_GROUP,
                "manipulator group is not the reviewed Stage 9A left arm",
            )
        object.__setattr__(self, "joint_names", joints)
        object.__setattr__(self, "fixed_joint_names", fixed)
        identity, content = content_identity("manipulator-group", self.semantic_document())
        object.__setattr__(self, "group_id", identity)
        object.__setattr__(self, "group_fingerprint", content)
        assert_artifact_size(self.as_dict(), "manipulator group identity")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "base_link": self.base_link,
            "fixed_joint_names": list(self.fixed_joint_names),
            "group_name": self.group_name,
            "joint_catalog_fingerprint": self.joint_catalog_fingerprint,
            "joint_catalog_id": self.joint_catalog_id,
            "joint_names": list(self.joint_names),
            "robot_model_fingerprint": self.robot_model_fingerprint,
            "robot_model_id": self.robot_model_id,
            "schema": _schema(self.schema_id),
            "tip_link": self.tip_link,
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            **self.semantic_document(),
            "group_fingerprint": self.group_fingerprint,
            "group_id": self.group_id,
        }


def verify_manipulator_group_identity(group: object) -> bool:
    return _verify(
        group,
        ManipulatorGroupIdentity,
        lambda: ManipulatorGroupIdentity(
            robot_model_id=group.robot_model_id,
            robot_model_fingerprint=group.robot_model_fingerprint,
            joint_catalog_id=group.joint_catalog_id,
            joint_catalog_fingerprint=group.joint_catalog_fingerprint,
            group_name=group.group_name,
            base_link=group.base_link,
            tip_link=group.tip_link,
            joint_names=group.joint_names,
            fixed_joint_names=group.fixed_joint_names,
        ),
    )


@dataclass(frozen=True, slots=True)
class JointPosition:
    joint_name: str
    position: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "joint_name", identifier(self.joint_name, "joint_name"))
        object.__setattr__(self, "position", finite_float(self.position, "joint position"))

    def as_dict(self) -> dict[str, JSONValue]:
        return {"joint_name": self.joint_name, "position": self.position}


def _positions(value: object, field_name: str) -> tuple[JointPosition, ...]:
    positions = bounded_items(value, field_name, JointPosition, MAX_PLANNING_JOINTS)
    names = [item.joint_name for item in positions]
    if len(names) != len(set(names)):
        raise PlanningValidationError(
            PlanningFailureCode.DUPLICATE_JOINT,
            f"{field_name} contains duplicate joints",
        )
    return positions


@dataclass(frozen=True, slots=True)
class ManipulatorJointState:
    group_id: str
    group_fingerprint: str
    joint_catalog_id: str
    joint_catalog_fingerprint: str
    positions: tuple[JointPosition, ...]
    schema_id: str = field(init=False, default=JOINT_STATE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    state_id: str = field(init=False)
    state_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("group_id", "group_fingerprint", "joint_catalog_id", "joint_catalog_fingerprint"):
            object.__setattr__(self, name, fingerprint(getattr(self, name), name))
        object.__setattr__(self, "positions", _positions(self.positions, "state positions"))
        identity, content = content_identity("manipulation-start-state", self.semantic_document())
        object.__setattr__(self, "state_id", identity)
        object.__setattr__(self, "state_fingerprint", content)
        assert_artifact_size(self.as_dict(), "manipulator joint state")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "group_fingerprint": self.group_fingerprint,
            "group_id": self.group_id,
            "joint_catalog_fingerprint": self.joint_catalog_fingerprint,
            "joint_catalog_id": self.joint_catalog_id,
            "positions": [item.as_dict() for item in self.positions],
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self.semantic_document(), "state_fingerprint": self.state_fingerprint, "state_id": self.state_id}


@dataclass(frozen=True, slots=True)
class JointSpaceGoal:
    group_id: str
    group_fingerprint: str
    joint_catalog_id: str
    joint_catalog_fingerprint: str
    positions: tuple[JointPosition, ...]
    schema_id: str = field(init=False, default=JOINT_GOAL_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    goal_id: str = field(init=False)
    goal_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("group_id", "group_fingerprint", "joint_catalog_id", "joint_catalog_fingerprint"):
            object.__setattr__(self, name, fingerprint(getattr(self, name), name))
        object.__setattr__(self, "positions", _positions(self.positions, "goal positions"))
        identity, content = content_identity("manipulation-joint-goal", self.semantic_document())
        object.__setattr__(self, "goal_id", identity)
        object.__setattr__(self, "goal_fingerprint", content)
        assert_artifact_size(self.as_dict(), "joint-space goal")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "group_fingerprint": self.group_fingerprint,
            "group_id": self.group_id,
            "joint_catalog_fingerprint": self.joint_catalog_fingerprint,
            "joint_catalog_id": self.joint_catalog_id,
            "positions": [item.as_dict() for item in self.positions],
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self.semantic_document(), "goal_fingerprint": self.goal_fingerprint, "goal_id": self.goal_id}


def verify_manipulator_joint_state(state: object) -> bool:
    return _verify(
        state,
        ManipulatorJointState,
        lambda: ManipulatorJointState(
            group_id=state.group_id,
            group_fingerprint=state.group_fingerprint,
            joint_catalog_id=state.joint_catalog_id,
            joint_catalog_fingerprint=state.joint_catalog_fingerprint,
            positions=state.positions,
        ),
    )


def verify_joint_space_goal(goal: object) -> bool:
    return _verify(
        goal,
        JointSpaceGoal,
        lambda: JointSpaceGoal(
            group_id=goal.group_id,
            group_fingerprint=goal.group_fingerprint,
            joint_catalog_id=goal.joint_catalog_id,
            joint_catalog_fingerprint=goal.joint_catalog_fingerprint,
            positions=goal.positions,
        ),
    )


@dataclass(frozen=True, slots=True)
class PlannerConfiguration:
    planner_id: str
    collision_backend_id: str
    interpolation_step: float
    max_waypoints: int
    deterministic_seed: int
    schema_id: str = field(init=False, default=PLANNER_CONFIGURATION_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    configuration_id: str = field(init=False)
    configuration_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.planner_id != PLANNER_ID or self.collision_backend_id != COLLISION_BACKEND_ID:
            raise PlanningValidationError(
                PlanningFailureCode.EVIDENCE_MISMATCH,
                "planner configuration names an unreviewed planning backend",
            )
        step = finite_float(self.interpolation_step, "interpolation_step")
        if step <= 0.0 or step > 0.25:
            raise PlanningValidationError(
                PlanningFailureCode.RESOURCE_LIMIT,
                "interpolation step is outside the reviewed bound",
            )
        if type(self.max_waypoints) is not int or not 2 <= self.max_waypoints <= MAX_WAYPOINTS:
            raise PlanningValidationError(
                PlanningFailureCode.RESOURCE_LIMIT,
                "max_waypoints is outside the reviewed bound",
            )
        if type(self.deterministic_seed) is not int or not 0 <= self.deterministic_seed <= 2_147_483_647:
            raise PlanningValidationError(
                PlanningFailureCode.MALFORMED_ARTIFACT,
                "deterministic_seed must be a bounded integer",
            )
        identity, content = content_identity("manipulation-planner-config", self.semantic_document())
        object.__setattr__(self, "configuration_id", identity)
        object.__setattr__(self, "configuration_fingerprint", content)
        assert_artifact_size(self.as_dict(), "planner configuration")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "collision_backend_id": self.collision_backend_id,
            "deterministic_seed": self.deterministic_seed,
            "interpolation_step": self.interpolation_step,
            "max_waypoints": self.max_waypoints,
            "planner_id": self.planner_id,
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self.semantic_document(), "configuration_fingerprint": self.configuration_fingerprint, "configuration_id": self.configuration_id}


def verify_planner_configuration(configuration: object) -> bool:
    return _verify(
        configuration,
        PlannerConfiguration,
        lambda: PlannerConfiguration(
            planner_id=configuration.planner_id,
            collision_backend_id=configuration.collision_backend_id,
            interpolation_step=configuration.interpolation_step,
            max_waypoints=configuration.max_waypoints,
            deterministic_seed=configuration.deterministic_seed,
        ),
    )


@dataclass(frozen=True, slots=True)
class CollisionBox:
    object_id: str
    frame_id: str
    position_xyz: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]
    dimensions_xyz: tuple[float, float, float]
    schema_id: str = field(init=False, default=COLLISION_BOX_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    object_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "object_id", identifier(self.object_id, "collision object_id"))
        object.__setattr__(self, "frame_id", identifier(self.frame_id, "collision frame_id"))
        position = finite_vector(self.position_xyz, "collision position_xyz", 3)
        orientation = finite_vector(self.orientation_xyzw, "collision orientation_xyzw", 4)
        dimensions = finite_vector(self.dimensions_xyz, "collision dimensions_xyz", 3)
        if any(abs(value) > 10.0 for value in position):
            raise PlanningValidationError(
                PlanningFailureCode.INVALID_COLLISION_OBJECT,
                "collision object position exceeds the reviewed workspace bound",
            )
        if orientation != (0.0, 0.0, 0.0, 1.0):
            raise PlanningValidationError(
                PlanningFailureCode.INVALID_COLLISION_OBJECT,
                "Stage 9A collision boxes must use the identity orientation",
            )
        if any(value <= 0.0 or value > 5.0 for value in dimensions):
            raise PlanningValidationError(
                PlanningFailureCode.INVALID_COLLISION_OBJECT,
                "collision box dimensions must be positive and bounded",
            )
        object.__setattr__(self, "position_xyz", position)
        object.__setattr__(self, "orientation_xyzw", orientation)
        object.__setattr__(self, "dimensions_xyz", dimensions)
        object.__setattr__(
            self,
            "object_fingerprint",
            content_identity("manipulation-collision-box", self.semantic_document())[1],
        )
        assert_artifact_size(self.as_dict(), "collision box")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "dimensions_xyz": list(self.dimensions_xyz),
            "frame_id": self.frame_id,
            "object_id": self.object_id,
            "orientation_xyzw": list(self.orientation_xyzw),
            "position_xyz": list(self.position_xyz),
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self.semantic_document(), "object_fingerprint": self.object_fingerprint}


def verify_collision_box(box: object) -> bool:
    return _verify(
        box,
        CollisionBox,
        lambda: CollisionBox(
            object_id=box.object_id,
            frame_id=box.frame_id,
            position_xyz=box.position_xyz,
            orientation_xyzw=box.orientation_xyzw,
            dimensions_xyz=box.dimensions_xyz,
        ),
    )


@dataclass(frozen=True, slots=True)
class PlanningSceneEvidence:
    robot_model_id: str
    robot_model_fingerprint: str
    group_id: str
    group_fingerprint: str
    frame_id: str
    collision_objects: tuple[CollisionBox, ...]
    schema_id: str = field(init=False, default=PLANNING_SCENE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    scene_id: str = field(init=False)
    scene_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("robot_model_id", "robot_model_fingerprint", "group_id", "group_fingerprint"):
            object.__setattr__(self, name, fingerprint(getattr(self, name), name))
        frame_id = identifier(self.frame_id, "planning frame_id")
        if frame_id != PLANNING_FRAME:
            raise PlanningValidationError(
                PlanningFailureCode.UNKNOWN_FRAME,
                "Stage 9A accepts collision geometry only in base_link",
            )
        objects = bounded_items(
            self.collision_objects,
            "collision_objects",
            CollisionBox,
            MAX_COLLISION_OBJECTS,
            allow_empty=True,
        )
        if any(not verify_collision_box(item) for item in objects):
            raise PlanningValidationError(
                PlanningFailureCode.INVALID_COLLISION_OBJECT,
                "planning scene contains an invalid collision box",
            )
        objects = tuple(sorted(objects, key=lambda item: item.object_id))
        if len({item.object_id for item in objects}) != len(objects):
            raise PlanningValidationError(
                PlanningFailureCode.DUPLICATE_COLLISION_OBJECT,
                "planning scene contains duplicate collision object IDs",
            )
        if any(item.frame_id != frame_id for item in objects):
            raise PlanningValidationError(
                PlanningFailureCode.UNKNOWN_FRAME,
                "collision object frame differs from the reviewed planning frame",
            )
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "collision_objects", objects)
        identity, content = content_identity("manipulation-planning-scene", self.semantic_document())
        object.__setattr__(self, "scene_id", identity)
        object.__setattr__(self, "scene_fingerprint", content)
        assert_artifact_size(self.as_dict(), "planning scene evidence")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "collision_objects": [item.as_dict() for item in self.collision_objects],
            "frame_id": self.frame_id,
            "group_fingerprint": self.group_fingerprint,
            "group_id": self.group_id,
            "robot_model_fingerprint": self.robot_model_fingerprint,
            "robot_model_id": self.robot_model_id,
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self.semantic_document(), "scene_fingerprint": self.scene_fingerprint, "scene_id": self.scene_id}


def verify_planning_scene_evidence(scene: object) -> bool:
    return _verify(
        scene,
        PlanningSceneEvidence,
        lambda: PlanningSceneEvidence(
            robot_model_id=scene.robot_model_id,
            robot_model_fingerprint=scene.robot_model_fingerprint,
            group_id=scene.group_id,
            group_fingerprint=scene.group_fingerprint,
            frame_id=scene.frame_id,
            collision_objects=scene.collision_objects,
        ),
    )


def _same_binding(group: ManipulatorGroupIdentity, catalog: ManipulatorJointCatalog) -> bool:
    return (
        group.robot_model_id == catalog.robot_model.robot_model_id
        and group.robot_model_fingerprint == catalog.robot_model.robot_model_fingerprint
        and group.joint_catalog_id == catalog.joint_catalog_id
        and group.joint_catalog_fingerprint == catalog.joint_catalog_fingerprint
        and group.group_name == catalog.group_name
        and group.base_link == catalog.base_link
        and group.tip_link == catalog.tip_link
        and group.joint_names == catalog.planning_joint_names
        and group.fixed_joint_names == catalog.fixed_joint_names
    )


@dataclass(frozen=True, slots=True)
class ManipulationPlanningRequest:
    robot_model: RobotModelIdentity
    joint_catalog: ManipulatorJointCatalog
    group: ManipulatorGroupIdentity
    start_state: ManipulatorJointState
    goal: JointSpaceGoal
    scene: PlanningSceneEvidence
    planner_configuration: PlannerConfiguration
    schema_id: str = field(init=False, default=PLANNING_REQUEST_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    request_id: str = field(init=False)
    request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_robot_model_identity(self.robot_model):
            raise PlanningValidationError(PlanningFailureCode.MODEL_MISMATCH, "request robot model is invalid")
        if not verify_manipulator_joint_catalog(self.joint_catalog) or self.joint_catalog.robot_model != self.robot_model:
            raise PlanningValidationError(PlanningFailureCode.MODEL_MISMATCH, "request joint catalog differs from its robot model")
        if not verify_manipulator_group_identity(self.group) or not _same_binding(self.group, self.joint_catalog):
            raise PlanningValidationError(PlanningFailureCode.WRONG_MANIPULATOR_GROUP, "request group differs from its joint catalog")
        if not verify_manipulator_joint_state(self.start_state) or not verify_joint_space_goal(self.goal):
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "request state or goal is invalid")
        expected_binding = (
            self.group.group_id,
            self.group.group_fingerprint,
            self.joint_catalog.joint_catalog_id,
            self.joint_catalog.joint_catalog_fingerprint,
        )
        if (
            self.start_state.group_id,
            self.start_state.group_fingerprint,
            self.start_state.joint_catalog_id,
            self.start_state.joint_catalog_fingerprint,
        ) != expected_binding or (
            self.goal.group_id,
            self.goal.group_fingerprint,
            self.goal.joint_catalog_id,
            self.goal.joint_catalog_fingerprint,
        ) != expected_binding:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "request state/goal identity binding was substituted")
        self.joint_catalog.validate_positions(self.start_state.positions)
        self.joint_catalog.validate_positions(self.goal.positions)
        if not verify_planning_scene_evidence(self.scene):
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "request scene is invalid")
        if (
            self.scene.robot_model_id != self.robot_model.robot_model_id
            or self.scene.robot_model_fingerprint != self.robot_model.robot_model_fingerprint
            or self.scene.group_id != self.group.group_id
            or self.scene.group_fingerprint != self.group.group_fingerprint
            or self.scene.frame_id != self.robot_model.root_link
        ):
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "request planning scene binding was substituted")
        if not verify_planner_configuration(self.planner_configuration):
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "request planner configuration is invalid")
        identity, content = content_identity("manipulation-planning-request", self.semantic_document())
        object.__setattr__(self, "request_id", identity)
        object.__setattr__(self, "request_fingerprint", content)
        assert_artifact_size(self.as_dict(), "manipulation planning request")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "goal": self.goal.as_dict(),
            "group": self.group.as_dict(),
            "joint_catalog": self.joint_catalog.as_dict(),
            "planner_configuration": self.planner_configuration.as_dict(),
            "robot_model": self.robot_model.as_dict(),
            "scene": self.scene.as_dict(),
            "schema": _schema(self.schema_id),
            "start_state": self.start_state.as_dict(),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self.semantic_document(), "request_fingerprint": self.request_fingerprint, "request_id": self.request_id}


def verify_manipulation_planning_request(request: object) -> bool:
    return _verify(
        request,
        ManipulationPlanningRequest,
        lambda: ManipulationPlanningRequest(
            robot_model=request.robot_model,
            joint_catalog=request.joint_catalog,
            group=request.group,
            start_state=request.start_state,
            goal=request.goal,
            scene=request.scene,
            planner_configuration=request.planner_configuration,
        ),
    )


@dataclass(frozen=True, slots=True)
class ManipulationPlanEvidence:
    request: ManipulationPlanningRequest
    status: PlanEvidenceStatus
    backend_version: str
    planner_seed: int
    waypoints: tuple[ManipulatorJointState, ...]
    checked_collision_object_ids: tuple[str, ...]
    colliding_object_ids: tuple[str, ...]
    self_collision_checked: bool
    environment_collision_checked: bool
    execution_disposition: ExecutionDisposition
    schema_id: str = field(init=False, default=PLAN_EVIDENCE_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    plan_evidence_id: str = field(init=False)
    plan_evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_manipulation_planning_request(self.request):
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "plan evidence request is invalid")
        _closed_enum(self.status, PlanEvidenceStatus, "plan evidence status")
        backend_version = bounded_text(self.backend_version, "backend_version", 64)
        if type(self.planner_seed) is not int or self.planner_seed != self.request.planner_configuration.deterministic_seed:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "planner seed differs from the exact request")
        waypoints = bounded_items(self.waypoints, "waypoints", ManipulatorJointState, MAX_WAYPOINTS, allow_empty=True)
        if any(not verify_manipulator_joint_state(item) for item in waypoints):
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "plan contains invalid waypoint evidence")
        checked = _identifier_tuple(self.checked_collision_object_ids, "checked_collision_object_ids", MAX_COLLISION_OBJECTS, allow_empty=True, sort_items=True)
        colliding = _identifier_tuple(self.colliding_object_ids, "colliding_object_ids", MAX_COLLISION_OBJECTS, allow_empty=True, sort_items=True)
        expected_objects = tuple(item.object_id for item in self.request.scene.collision_objects)
        if checked != expected_objects or not set(colliding) <= set(checked):
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "collision evidence differs from the exact request scene")
        if type(self.self_collision_checked) is not bool or not self.self_collision_checked:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "self-collision checking must be explicit")
        if type(self.environment_collision_checked) is not bool or not self.environment_collision_checked:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "environment-collision checking must be explicit")
        if self.execution_disposition is not ExecutionDisposition.NOT_EXECUTED:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "planning evidence can only be not executed")
        if self.status is PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED:
            if len(waypoints) < 2 or len(waypoints) > self.request.planner_configuration.max_waypoints or colliding:
                raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "collision-free plan evidence is incomplete or contradictory")
            for waypoint in waypoints:
                if (
                    waypoint.group_id != self.request.group.group_id
                    or waypoint.group_fingerprint != self.request.group.group_fingerprint
                    or waypoint.joint_catalog_id != self.request.joint_catalog.joint_catalog_id
                    or waypoint.joint_catalog_fingerprint != self.request.joint_catalog.joint_catalog_fingerprint
                ):
                    raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "plan waypoint binding was substituted")
                self.request.joint_catalog.validate_positions(waypoint.positions)
            if waypoints[0] != self.request.start_state or waypoints[-1].positions != self.request.goal.positions:
                raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "plan endpoints differ from the exact request")
        elif waypoints:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "rejected planning evidence cannot carry a usable trajectory")
        object.__setattr__(self, "backend_version", backend_version)
        object.__setattr__(self, "waypoints", waypoints)
        object.__setattr__(self, "checked_collision_object_ids", checked)
        object.__setattr__(self, "colliding_object_ids", colliding)
        identity, content = content_identity("manipulation-plan-evidence", self.semantic_document())
        object.__setattr__(self, "plan_evidence_id", identity)
        object.__setattr__(self, "plan_evidence_fingerprint", content)
        assert_artifact_size(self.as_dict(), "manipulation plan evidence")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "backend_id": COLLISION_BACKEND_ID,
            "backend_version": self.backend_version,
            "checked_collision_object_ids": list(self.checked_collision_object_ids),
            "colliding_object_ids": list(self.colliding_object_ids),
            "environment_collision_checked": self.environment_collision_checked,
            "execution_disposition": self.execution_disposition.value,
            "planner_seed": self.planner_seed,
            "request": self.request.as_dict(),
            "schema": _schema(self.schema_id),
            "self_collision_checked": self.self_collision_checked,
            "status": self.status.value,
            "waypoints": [item.as_dict() for item in self.waypoints],
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self.semantic_document(), "plan_evidence_fingerprint": self.plan_evidence_fingerprint, "plan_evidence_id": self.plan_evidence_id}


def verify_manipulation_plan_evidence(evidence: object) -> bool:
    return _verify(
        evidence,
        ManipulationPlanEvidence,
        lambda: ManipulationPlanEvidence(
            request=evidence.request,
            status=evidence.status,
            backend_version=evidence.backend_version,
            planner_seed=evidence.planner_seed,
            waypoints=evidence.waypoints,
            checked_collision_object_ids=evidence.checked_collision_object_ids,
            colliding_object_ids=evidence.colliding_object_ids,
            self_collision_checked=evidence.self_collision_checked,
            environment_collision_checked=evidence.environment_collision_checked,
            execution_disposition=evidence.execution_disposition,
        ),
    )


@dataclass(frozen=True, slots=True)
class ManipulationPlanningDecision:
    request: ManipulationPlanningRequest
    plan_evidence: ManipulationPlanEvidence
    disposition: PlanningDisposition
    reasons: tuple[PlanningDecisionReason, ...]
    execution_disposition: ExecutionDisposition
    schema_id: str = field(init=False, default=PLANNING_DECISION_SCHEMA_ID)
    schema_version: str = field(init=False, default=SCHEMA_VERSION)
    decision_id: str = field(init=False)
    decision_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not verify_manipulation_planning_request(self.request) or not verify_manipulation_plan_evidence(self.plan_evidence):
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "planning decision contains invalid evidence")
        if self.plan_evidence.request != self.request:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "planning decision request was substituted")
        _closed_enum(self.disposition, PlanningDisposition, "planning disposition")
        reasons = bounded_items(self.reasons, "planning reasons", PlanningDecisionReason, 8)
        reasons = tuple(sorted(reasons, key=lambda item: item.value))
        if len(set(reasons)) != len(reasons):
            raise PlanningValidationError(PlanningFailureCode.MALFORMED_ARTIFACT, "planning reasons contain duplicates")
        expected_reasons = tuple(
            sorted(
                (
                    _STATUS_REASON[self.plan_evidence.status],
                    PlanningDecisionReason.EXECUTION_OUT_OF_SCOPE,
                    PlanningDecisionReason.PHYSICAL_VALIDATION_ABSENT,
                ),
                key=lambda item: item.value,
            )
        )
        if reasons != expected_reasons:
            raise PlanningValidationError(
                PlanningFailureCode.EVIDENCE_MISMATCH,
                "planning decision reasons differ from its exact evidence status",
            )
        expected_positive = self.plan_evidence.status is PlanEvidenceStatus.COLLISION_FREE_PLAN_REPORTED
        if (self.disposition is PlanningDisposition.PLAN_AVAILABLE_FOR_REVIEW) != expected_positive:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "decision disposition escalates its plan evidence")
        if self.execution_disposition is not ExecutionDisposition.NOT_EXECUTED:
            raise PlanningValidationError(PlanningFailureCode.EVIDENCE_MISMATCH, "planning decision can only be not executed")
        object.__setattr__(self, "reasons", reasons)
        identity, content = content_identity("manipulation-planning-decision", self.semantic_document())
        object.__setattr__(self, "decision_id", identity)
        object.__setattr__(self, "decision_fingerprint", content)
        assert_artifact_size(self.as_dict(), "manipulation planning decision")

    def semantic_document(self) -> dict[str, JSONValue]:
        return {
            "disposition": self.disposition.value,
            "execution_disposition": self.execution_disposition.value,
            "plan_evidence": self.plan_evidence.as_dict(),
            "reasons": [item.value for item in self.reasons],
            "request": self.request.as_dict(),
            "schema": _schema(self.schema_id),
        }

    def as_dict(self) -> dict[str, JSONValue]:
        return {**self.semantic_document(), "decision_fingerprint": self.decision_fingerprint, "decision_id": self.decision_id}


def verify_manipulation_planning_decision(decision: object) -> bool:
    return _verify(
        decision,
        ManipulationPlanningDecision,
        lambda: ManipulationPlanningDecision(
            request=decision.request,
            plan_evidence=decision.plan_evidence,
            disposition=decision.disposition,
            reasons=decision.reasons,
            execution_disposition=decision.execution_disposition,
        ),
    )
