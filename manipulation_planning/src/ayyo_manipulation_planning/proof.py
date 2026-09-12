"""Strict adapter from the headless MoveIt result to immutable proof evidence."""

from __future__ import annotations

import json

from .canonical import MAX_SERIALIZED_ARTIFACT_BYTES, canonical_json
from .errors import PlanningSerializationError, PlanningValidationError
from .models import (
    COLLISION_BACKEND_ID,
    LEFT_ARM_GROUP_NAME,
    LEFT_ARM_JOINT_NAMES,
    PLANNER_ID,
    SCHEMA_VERSION,
    ExecutionDisposition,
    ManipulationPlanningRequest,
    MoveItCollisionProof,
    verify_manipulation_planning_request,
)
from .planning import deterministic_joint_interpolation


RAW_MOVEIT_PROOF_SCHEMA_ID = "ayyo.moveit-planning-scene-proof.v1"
REVIEWED_MOVEIT_BACKEND_VERSION = "moveit-2.12.4"


def _error(detail: str, cause: BaseException | None = None) -> PlanningSerializationError:
    error = PlanningSerializationError(detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"duplicate key {key!r} is not canonical")
        result[key] = value
    return result


def _mapping(value: object, name: str) -> dict:
    if type(value) is not dict:
        raise _error(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> list:
    if type(value) is not list:
        raise _error(f"{name} must be an array")
    return value


def _require_exact_float_vector(value: object, expected: tuple[float, ...], name: str) -> None:
    actual = _sequence(value, name)
    if (
        len(actual) != len(expected)
        or any(type(item) is not float for item in actual)
        or tuple(actual) != expected
    ):
        raise _error(f"{name} differs from the exact request")


def _expected_collision_objects(request: ManipulationPlanningRequest) -> list[dict]:
    return [
        {
            "dimensions_xyz": list(item.dimensions_xyz),
            "frame_id": item.frame_id,
            "object_id": item.object_id,
            "orientation_xyzw": list(item.orientation_xyzw),
            "position_xyz": list(item.position_xyz),
        }
        for item in request.scene.collision_objects
    ]


def moveit_collision_proof_from_canonical_json(
    request: ManipulationPlanningRequest,
    payload: str,
) -> MoveItCollisionProof:
    """Bind canonical headless MoveIt output to one exact planning request."""

    if not verify_manipulation_planning_request(request):
        raise _error("MoveIt proof request failed integrity verification")
    if type(payload) is not str:
        raise _error("MoveIt proof payload must be text")
    try:
        encoded = payload.encode("utf-8")
    except UnicodeError as error:
        raise _error("MoveIt proof payload must be UTF-8", error)
    if not encoded or len(encoded) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise _error("MoveIt proof payload violates its byte bound")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _error(f"non-finite {value} is forbidden")
            ),
        )
        item = _mapping(document, "MoveIt proof")
        if canonical_json(item) != payload:
            raise _error("MoveIt proof payload is not canonical JSON")
        expected_keys = {
            "backend_id",
            "backend_version",
            "collision_objects",
            "deterministic_seed",
            "disabled_collision_pairs",
            "environment_collision_free",
            "execution_disposition",
            "goal_obstacle_collision_reported",
            "group_name",
            "interpolation_step",
            "joint_names",
            "limits_match_reviewed",
            "max_waypoints",
            "model_frame",
            "no_execution_api_used",
            "physical_validation",
            "planner_id",
            "result",
            "robot_description_content_fingerprint",
            "samples_checked",
            "schema",
            "self_collision_free",
            "srdf_content_fingerprint",
            "waypoints",
        }
        if set(item) != expected_keys:
            raise _error("MoveIt proof fields do not match the closed v1 schema")
        schema = _mapping(item["schema"], "MoveIt proof schema")
        if schema != {"id": RAW_MOVEIT_PROOF_SCHEMA_ID, "version": SCHEMA_VERSION}:
            raise _error("unknown MoveIt proof schema or version")

        configuration = request.planner_configuration
        collision_model = request.collision_model
        exact_scalars = {
            "backend_id": COLLISION_BACKEND_ID,
            "backend_version": REVIEWED_MOVEIT_BACKEND_VERSION,
            "deterministic_seed": configuration.deterministic_seed,
            "execution_disposition": ExecutionDisposition.NOT_EXECUTED.value,
            "goal_obstacle_collision_reported": True,
            "group_name": LEFT_ARM_GROUP_NAME,
            "interpolation_step": configuration.interpolation_step,
            "joint_names": list(LEFT_ARM_JOINT_NAMES),
            "limits_match_reviewed": True,
            "max_waypoints": configuration.max_waypoints,
            "model_frame": request.robot_model.root_link,
            "no_execution_api_used": True,
            "physical_validation": "absent",
            "planner_id": PLANNER_ID,
            "result": "plan_available_for_review",
            "robot_description_content_fingerprint": (
                collision_model.robot_description_content_fingerprint
            ),
            "srdf_content_fingerprint": collision_model.srdf_content_fingerprint,
        }
        for field, expected in exact_scalars.items():
            if type(item[field]) is not type(expected) or item[field] != expected:
                raise _error(f"MoveIt proof {field} differs from the exact request")

        raw_pairs = _sequence(item["disabled_collision_pairs"], "disabled collision pairs")
        if any(
            type(pair) is not list
            or len(pair) != 2
            or any(type(link) is not str for link in pair)
            for pair in raw_pairs
        ) or tuple(tuple(pair) for pair in raw_pairs) != collision_model.disabled_collision_pairs:
            raise _error("MoveIt proof allowed-collision semantics were substituted")

        raw_objects = _sequence(item["collision_objects"], "collision objects")
        for raw_object in raw_objects:
            mapped = _mapping(raw_object, "collision object")
            if set(mapped) != {
                "dimensions_xyz",
                "frame_id",
                "object_id",
                "orientation_xyzw",
                "position_xyz",
            }:
                raise _error("MoveIt proof collision object has unknown or missing fields")
            expected_object = next(
                (
                    candidate
                    for candidate in request.scene.collision_objects
                    if candidate.object_id == mapped["object_id"]
                ),
                None,
            )
            if expected_object is None:
                raise _error("MoveIt proof collision object differs from the exact scene")
            _require_exact_float_vector(
                mapped["dimensions_xyz"], expected_object.dimensions_xyz, "box dimensions"
            )
            _require_exact_float_vector(
                mapped["orientation_xyzw"],
                expected_object.orientation_xyzw,
                "box orientation",
            )
            _require_exact_float_vector(
                mapped["position_xyz"], expected_object.position_xyz, "box position"
            )
        if raw_objects != _expected_collision_objects(request):
            raise _error("MoveIt proof collision scene differs from the exact request")

        expected_waypoints = deterministic_joint_interpolation(request)
        raw_waypoints = _sequence(item["waypoints"], "waypoints")
        if len(raw_waypoints) != len(expected_waypoints):
            raise _error("MoveIt proof does not cover the exact candidate path")
        for index, (raw, expected) in enumerate(zip(raw_waypoints, expected_waypoints, strict=True)):
            _require_exact_float_vector(
                raw,
                tuple(position.position for position in expected.positions),
                f"waypoint {index}",
            )
        if type(item["samples_checked"]) is not int or item["samples_checked"] != len(
            expected_waypoints
        ):
            raise _error("MoveIt proof sample count differs from the exact candidate path")

        result_fields = ("self_collision_free", "environment_collision_free")
        results = {}
        for field in result_fields:
            values = _sequence(item[field], field)
            if (
                len(values) != len(expected_waypoints)
                or any(type(value) is not bool for value in values)
                or not all(values)
            ):
                raise _error(f"MoveIt proof {field} is not collision-free at every waypoint")
            results[field] = tuple(values)

        return MoveItCollisionProof(
            request_id=request.request_id,
            request_fingerprint=request.request_fingerprint,
            collision_model_id=collision_model.collision_model_id,
            collision_model_fingerprint=collision_model.collision_model_fingerprint,
            planner_configuration_id=configuration.configuration_id,
            planner_configuration_fingerprint=configuration.configuration_fingerprint,
            robot_description_content_fingerprint=(
                collision_model.robot_description_content_fingerprint
            ),
            srdf_content_fingerprint=collision_model.srdf_content_fingerprint,
            disabled_collision_pairs=collision_model.disabled_collision_pairs,
            backend_version=item["backend_version"],
            joint_names=tuple(item["joint_names"]),
            waypoints=expected_waypoints,
            collision_objects=request.scene.collision_objects,
            self_collision_free=results["self_collision_free"],
            environment_collision_free=results["environment_collision_free"],
            limits_match_reviewed=item["limits_match_reviewed"],
            goal_obstacle_collision_reported=item["goal_obstacle_collision_reported"],
            execution_disposition=ExecutionDisposition(item["execution_disposition"]),
        )
    except PlanningSerializationError:
        raise
    except (json.JSONDecodeError, PlanningValidationError, KeyError, TypeError, ValueError,
            UnicodeError, RecursionError, StopIteration) as error:
        raise _error("MoveIt proof failed closed during reconstruction", error)
