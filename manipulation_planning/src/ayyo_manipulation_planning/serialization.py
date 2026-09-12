"""Strict canonical JSON boundary for Stage 9A planning artifacts."""

from __future__ import annotations

import json
from typing import Callable

from .canonical import (
    JSONValue,
    MAX_SERIALIZED_ARTIFACT_BYTES,
    SCHEMA_VERSION,
    canonical_json,
)
from .errors import PlanningSerializationError, PlanningValidationError
from .models import (
    COLLISION_BOX_SCHEMA_ID,
    JOINT_CATALOG_SCHEMA_ID,
    JOINT_GOAL_SCHEMA_ID,
    JOINT_STATE_SCHEMA_ID,
    MANIPULATOR_GROUP_SCHEMA_ID,
    PLAN_EVIDENCE_SCHEMA_ID,
    PLANNER_CONFIGURATION_SCHEMA_ID,
    PLANNING_DECISION_SCHEMA_ID,
    PLANNING_REQUEST_SCHEMA_ID,
    PLANNING_SCENE_SCHEMA_ID,
    ROBOT_JOINT_SCHEMA_ID,
    ROBOT_MODEL_SCHEMA_ID,
    CollisionBox,
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
    PlanningSceneEvidence,
    RobotJointKind,
    RobotJointReference,
    RobotModelIdentity,
)


PlanningArtifact = (
    RobotModelIdentity
    | RobotJointReference
    | ManipulatorJointCatalog
    | ManipulatorGroupIdentity
    | ManipulatorJointState
    | JointSpaceGoal
    | PlannerConfiguration
    | CollisionBox
    | PlanningSceneEvidence
    | ManipulationPlanningRequest
    | ManipulationPlanEvidence
    | ManipulationPlanningDecision
)


def _error(detail: str, cause: BaseException | None = None) -> PlanningSerializationError:
    error = PlanningSerializationError(detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def _object(pairs: list[tuple[str, JSONValue]]) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"duplicate key {key!r} is not canonical")
        result[key] = value
    return result


def _mapping(value: object, name: str) -> dict[str, JSONValue]:
    if type(value) is not dict:
        raise _error(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> list[JSONValue]:
    if type(value) is not list:
        raise _error(f"{name} must be an array")
    return value


def _exact_keys(value: dict[str, JSONValue], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise _error(f"{name} fields do not match the closed v1 schema")


def _schema(value: dict[str, JSONValue], schema_id: str) -> None:
    schema = _mapping(value.get("schema"), "schema")
    _exact_keys(schema, {"id", "version"}, "schema")
    if schema != {"id": schema_id, "version": SCHEMA_VERSION}:
        raise _error("unknown planning schema or version")


def _verify_recomputed(
    document: dict[str, JSONValue],
    artifact: PlanningArtifact,
) -> PlanningArtifact:
    if artifact.as_dict() != document:
        raise _error("serialized identities or content do not match recomputed evidence")
    return artifact


def _robot_model(value: object) -> RobotModelIdentity:
    item = _mapping(value, "robot_model")
    _exact_keys(item, {
        "description_fingerprint", "description_source", "joint_names", "link_names",
        "robot_model_fingerprint", "robot_model_id", "robot_name", "root_link", "schema",
    }, "robot_model")
    _schema(item, ROBOT_MODEL_SCHEMA_ID)
    return _verify_recomputed(item, RobotModelIdentity(
        robot_name=item["robot_name"],
        root_link=item["root_link"],
        description_source=item["description_source"],
        description_fingerprint=item["description_fingerprint"],
        link_names=tuple(_sequence(item["link_names"], "link_names")),
        joint_names=tuple(_sequence(item["joint_names"], "joint_names")),
    ))


def _joint(value: object) -> RobotJointReference:
    item = _mapping(value, "robot_joint")
    _exact_keys(item, {
        "axis_xyz", "child_link", "effort", "joint_evidence_fingerprint",
        "joint_evidence_id", "joint_name", "kind", "lower", "origin_rpy",
        "origin_xyz", "parent_link", "schema", "upper", "velocity",
    }, "robot_joint")
    _schema(item, ROBOT_JOINT_SCHEMA_ID)
    axis = item["axis_xyz"]
    return _verify_recomputed(item, RobotJointReference(
        joint_name=item["joint_name"],
        kind=RobotJointKind(item["kind"]),
        parent_link=item["parent_link"],
        child_link=item["child_link"],
        origin_xyz=tuple(_sequence(item["origin_xyz"], "origin_xyz")),
        origin_rpy=tuple(_sequence(item["origin_rpy"], "origin_rpy")),
        axis_xyz=None if axis is None else tuple(_sequence(axis, "axis_xyz")),
        lower=item["lower"],
        upper=item["upper"],
        effort=item["effort"],
        velocity=item["velocity"],
    ))


def _catalog(value: object) -> ManipulatorJointCatalog:
    item = _mapping(value, "joint_catalog")
    _exact_keys(item, {
        "base_link", "chain_joints", "group_name", "joint_catalog_fingerprint",
        "joint_catalog_id", "planning_joint_names", "robot_model", "schema", "tip_link",
    }, "joint_catalog")
    _schema(item, JOINT_CATALOG_SCHEMA_ID)
    return _verify_recomputed(item, ManipulatorJointCatalog(
        robot_model=_robot_model(item["robot_model"]),
        group_name=item["group_name"],
        base_link=item["base_link"],
        tip_link=item["tip_link"],
        chain_joints=tuple(_joint(value) for value in _sequence(item["chain_joints"], "chain_joints")),
        planning_joint_names=tuple(_sequence(item["planning_joint_names"], "planning_joint_names")),
    ))


def _group(value: object) -> ManipulatorGroupIdentity:
    item = _mapping(value, "group")
    _exact_keys(item, {
        "base_link", "fixed_joint_names", "group_fingerprint", "group_id", "group_name",
        "joint_catalog_fingerprint", "joint_catalog_id", "joint_names",
        "robot_model_fingerprint", "robot_model_id", "schema", "tip_link",
    }, "group")
    _schema(item, MANIPULATOR_GROUP_SCHEMA_ID)
    return _verify_recomputed(item, ManipulatorGroupIdentity(
        robot_model_id=item["robot_model_id"],
        robot_model_fingerprint=item["robot_model_fingerprint"],
        joint_catalog_id=item["joint_catalog_id"],
        joint_catalog_fingerprint=item["joint_catalog_fingerprint"],
        group_name=item["group_name"],
        base_link=item["base_link"],
        tip_link=item["tip_link"],
        joint_names=tuple(_sequence(item["joint_names"], "joint_names")),
        fixed_joint_names=tuple(_sequence(item["fixed_joint_names"], "fixed_joint_names")),
    ))


def _positions(value: object) -> tuple[JointPosition, ...]:
    result = []
    for raw in _sequence(value, "positions"):
        item = _mapping(raw, "joint_position")
        _exact_keys(item, {"joint_name", "position"}, "joint_position")
        result.append(JointPosition(joint_name=item["joint_name"], position=item["position"]))
    return tuple(result)


def _state(value: object) -> ManipulatorJointState:
    item = _mapping(value, "joint_state")
    _exact_keys(item, {
        "group_fingerprint", "group_id", "joint_catalog_fingerprint", "joint_catalog_id",
        "positions", "schema", "state_fingerprint", "state_id",
    }, "joint_state")
    _schema(item, JOINT_STATE_SCHEMA_ID)
    return _verify_recomputed(item, ManipulatorJointState(
        group_id=item["group_id"],
        group_fingerprint=item["group_fingerprint"],
        joint_catalog_id=item["joint_catalog_id"],
        joint_catalog_fingerprint=item["joint_catalog_fingerprint"],
        positions=_positions(item["positions"]),
    ))


def _goal(value: object) -> JointSpaceGoal:
    item = _mapping(value, "joint_goal")
    _exact_keys(item, {
        "goal_fingerprint", "goal_id", "group_fingerprint", "group_id",
        "joint_catalog_fingerprint", "joint_catalog_id", "positions", "schema",
    }, "joint_goal")
    _schema(item, JOINT_GOAL_SCHEMA_ID)
    return _verify_recomputed(item, JointSpaceGoal(
        group_id=item["group_id"],
        group_fingerprint=item["group_fingerprint"],
        joint_catalog_id=item["joint_catalog_id"],
        joint_catalog_fingerprint=item["joint_catalog_fingerprint"],
        positions=_positions(item["positions"]),
    ))


def _configuration(value: object) -> PlannerConfiguration:
    item = _mapping(value, "planner_configuration")
    _exact_keys(item, {
        "collision_backend_id", "configuration_fingerprint", "configuration_id",
        "deterministic_seed", "interpolation_step", "max_waypoints", "planner_id", "schema",
    }, "planner_configuration")
    _schema(item, PLANNER_CONFIGURATION_SCHEMA_ID)
    return _verify_recomputed(item, PlannerConfiguration(
        planner_id=item["planner_id"],
        collision_backend_id=item["collision_backend_id"],
        interpolation_step=item["interpolation_step"],
        max_waypoints=item["max_waypoints"],
        deterministic_seed=item["deterministic_seed"],
    ))


def _box(value: object) -> CollisionBox:
    item = _mapping(value, "collision_box")
    _exact_keys(item, {
        "dimensions_xyz", "frame_id", "object_fingerprint", "object_id",
        "orientation_xyzw", "position_xyz", "schema",
    }, "collision_box")
    _schema(item, COLLISION_BOX_SCHEMA_ID)
    return _verify_recomputed(item, CollisionBox(
        object_id=item["object_id"],
        frame_id=item["frame_id"],
        position_xyz=tuple(_sequence(item["position_xyz"], "position_xyz")),
        orientation_xyzw=tuple(_sequence(item["orientation_xyzw"], "orientation_xyzw")),
        dimensions_xyz=tuple(_sequence(item["dimensions_xyz"], "dimensions_xyz")),
    ))


def _scene(value: object) -> PlanningSceneEvidence:
    item = _mapping(value, "planning_scene")
    _exact_keys(item, {
        "collision_objects", "frame_id", "group_fingerprint", "group_id",
        "robot_model_fingerprint", "robot_model_id", "scene_fingerprint", "scene_id", "schema",
    }, "planning_scene")
    _schema(item, PLANNING_SCENE_SCHEMA_ID)
    return _verify_recomputed(item, PlanningSceneEvidence(
        robot_model_id=item["robot_model_id"],
        robot_model_fingerprint=item["robot_model_fingerprint"],
        group_id=item["group_id"],
        group_fingerprint=item["group_fingerprint"],
        frame_id=item["frame_id"],
        collision_objects=tuple(_box(value) for value in _sequence(item["collision_objects"], "collision_objects")),
    ))


def _request(value: object) -> ManipulationPlanningRequest:
    item = _mapping(value, "planning_request")
    _exact_keys(item, {
        "goal", "group", "joint_catalog", "planner_configuration", "request_fingerprint",
        "request_id", "robot_model", "scene", "schema", "start_state",
    }, "planning_request")
    _schema(item, PLANNING_REQUEST_SCHEMA_ID)
    return _verify_recomputed(item, ManipulationPlanningRequest(
        robot_model=_robot_model(item["robot_model"]),
        joint_catalog=_catalog(item["joint_catalog"]),
        group=_group(item["group"]),
        start_state=_state(item["start_state"]),
        goal=_goal(item["goal"]),
        scene=_scene(item["scene"]),
        planner_configuration=_configuration(item["planner_configuration"]),
    ))


def _evidence(value: object) -> ManipulationPlanEvidence:
    item = _mapping(value, "plan_evidence")
    _exact_keys(item, {
        "backend_id", "backend_version", "checked_collision_object_ids",
        "colliding_object_ids", "environment_collision_checked", "execution_disposition",
        "plan_evidence_fingerprint", "plan_evidence_id", "planner_seed", "request", "schema",
        "self_collision_checked", "status", "waypoints",
    }, "plan_evidence")
    _schema(item, PLAN_EVIDENCE_SCHEMA_ID)
    return _verify_recomputed(item, ManipulationPlanEvidence(
        request=_request(item["request"]),
        status=PlanEvidenceStatus(item["status"]),
        backend_version=item["backend_version"],
        planner_seed=item["planner_seed"],
        waypoints=tuple(_state(value) for value in _sequence(item["waypoints"], "waypoints")),
        checked_collision_object_ids=tuple(_sequence(item["checked_collision_object_ids"], "checked_collision_object_ids")),
        colliding_object_ids=tuple(_sequence(item["colliding_object_ids"], "colliding_object_ids")),
        self_collision_checked=item["self_collision_checked"],
        environment_collision_checked=item["environment_collision_checked"],
        execution_disposition=ExecutionDisposition(item["execution_disposition"]),
    ))


def _decision(value: object) -> ManipulationPlanningDecision:
    item = _mapping(value, "planning_decision")
    _exact_keys(item, {
        "decision_fingerprint", "decision_id", "disposition", "execution_disposition",
        "plan_evidence", "reasons", "request", "schema",
    }, "planning_decision")
    _schema(item, PLANNING_DECISION_SCHEMA_ID)
    return _verify_recomputed(item, ManipulationPlanningDecision(
        request=_request(item["request"]),
        plan_evidence=_evidence(item["plan_evidence"]),
        disposition=PlanningDisposition(item["disposition"]),
        reasons=tuple(PlanningDecisionReason(value) for value in _sequence(item["reasons"], "reasons")),
        execution_disposition=ExecutionDisposition(item["execution_disposition"]),
    ))


_PARSERS: dict[str, Callable[[object], PlanningArtifact]] = {
    ROBOT_MODEL_SCHEMA_ID: _robot_model,
    ROBOT_JOINT_SCHEMA_ID: _joint,
    JOINT_CATALOG_SCHEMA_ID: _catalog,
    MANIPULATOR_GROUP_SCHEMA_ID: _group,
    JOINT_STATE_SCHEMA_ID: _state,
    JOINT_GOAL_SCHEMA_ID: _goal,
    PLANNER_CONFIGURATION_SCHEMA_ID: _configuration,
    COLLISION_BOX_SCHEMA_ID: _box,
    PLANNING_SCENE_SCHEMA_ID: _scene,
    PLANNING_REQUEST_SCHEMA_ID: _request,
    PLAN_EVIDENCE_SCHEMA_ID: _evidence,
    PLANNING_DECISION_SCHEMA_ID: _decision,
}


def canonical_manipulation_planning_artifact_json(artifact: PlanningArtifact) -> str:
    if type(artifact) not in {
        RobotModelIdentity, RobotJointReference, ManipulatorJointCatalog,
        ManipulatorGroupIdentity, ManipulatorJointState, JointSpaceGoal,
        PlannerConfiguration, CollisionBox, PlanningSceneEvidence,
        ManipulationPlanningRequest, ManipulationPlanEvidence,
        ManipulationPlanningDecision,
    }:
        raise _error("unsupported manipulation-planning artifact type")
    try:
        return canonical_json(artifact.as_dict())
    except (PlanningValidationError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise _error("planning artifact cannot be serialized canonically", error)


def manipulation_planning_artifact_from_canonical_json(payload: str) -> PlanningArtifact:
    if type(payload) is not str:
        raise _error("canonical planning payload must be text")
    try:
        encoded = payload.encode("utf-8")
    except UnicodeError as error:
        raise _error("canonical planning payload must be UTF-8", error)
    if not encoded or len(encoded) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise _error("canonical planning payload violates its byte bound")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(_error(f"non-finite {value} is forbidden")),
        )
        item = _mapping(document, "planning artifact")
        if canonical_json(item) != payload:
            raise _error("planning payload is not canonical JSON")
        schema = _mapping(item.get("schema"), "schema")
        parser = _PARSERS.get(schema.get("id"))
        if parser is None:
            raise _error("unknown planning artifact schema")
        return parser(item)
    except PlanningSerializationError:
        raise
    except (json.JSONDecodeError, PlanningValidationError, KeyError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise _error("planning payload failed closed during reconstruction", error)
