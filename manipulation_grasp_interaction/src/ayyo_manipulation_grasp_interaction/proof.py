"""Strict adapter for the bounded Stage 9D attached-object MoveIt report."""

from __future__ import annotations

from hashlib import sha256
import json

from ayyo_manipulation_simulation_execution import expected_dense_samples

from .canonical import MAX_SERIALIZED_ARTIFACT_BYTES, SCHEMA_VERSION, canonical_json
from .errors import (
    GraspInteractionFailureCode,
    GraspInteractionSerializationError,
    GraspInteractionValidationError,
)
from .models import (
    STAGE9D_COLLISION_BACKEND_ID,
    STAGE9D_COLLISION_BACKEND_VERSION,
    STAGE9D_END_EFFECTOR_LINK,
    STAGE9D_EXPECTED_RELATIVE_ORIENTATION,
    STAGE9D_EXPECTED_RELATIVE_POSITION,
    STAGE9D_OBJECT_COLLISION,
    GraspEstablishedEvidence,
    GraspInteractionRequest,
    InteractionCollisionProof,
    InteractionCollisionSample,
    verify_grasp_evidence,
    verify_interaction_request,
)


INTERACTION_PREFLIGHT_INPUT_SCHEMA_ID = (
    "ayyo.stage9d.moveit-interaction-preflight-input.v1"
)
RAW_INTERACTION_PREFLIGHT_SCHEMA_ID = (
    "ayyo.stage9d.moveit-interaction-preflight-report.v1"
)


def _error(detail: str, cause: BaseException | None = None):
    error = GraspInteractionSerializationError(detail)
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


def interaction_preflight_input_document(
    request: GraspInteractionRequest,
    grasp_evidence_id: str,
    grasp_evidence_fingerprint: str,
) -> dict:
    """Describe the one attached-body check without granting execution authority."""

    if not verify_interaction_request(request):
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE,
            "interaction preflight requires a verified request",
        )
    stage9c = request.stage9c_execution_request
    planning = stage9c.planning_request
    collision_model = planning.collision_model
    return {
        "attached_object": {
            "collision_name": request.grasp_object.collision_name,
            "dimensions_xyz": list(request.grasp_object.dimensions_xyz),
            "object_id": request.grasp_object.object_id,
            "relative_orientation_xyzw": list(STAGE9D_EXPECTED_RELATIVE_ORIENTATION),
            "relative_position_xyz": list(STAGE9D_EXPECTED_RELATIVE_POSITION),
            "touch_links": [STAGE9D_END_EFFECTOR_LINK],
        },
        "collision_objects": [item.as_dict() for item in planning.scene.collision_objects],
        "disabled_collision_pairs": [
            list(item) for item in collision_model.disabled_collision_pairs
        ],
        "execution_request_fingerprint": stage9c.execution_request_fingerprint,
        "execution_request_id": stage9c.execution_request_id,
        "grasp_evidence_fingerprint": grasp_evidence_fingerprint,
        "grasp_evidence_id": grasp_evidence_id,
        "interaction_request_fingerprint": request.interaction_request_fingerprint,
        "interaction_request_id": request.interaction_request_id,
        "joint_names": list(stage9c.controller_contract.joint_names),
        "robot_description_content_fingerprint": (
            collision_model.robot_description_content_fingerprint
        ),
        "robot_model_fingerprint": planning.robot_model.robot_model_fingerprint,
        "robot_model_id": planning.robot_model.robot_model_id,
        "samples": [
            {
                "positions": list(sample.positions),
                "sample_index": sample.sample_index,
                "segment_fraction": sample.segment_fraction,
                "segment_index": sample.segment_index,
                "segment_subdivisions": sample.segment_subdivisions,
                "subdivision_index": sample.subdivision_index,
            }
            for sample in expected_dense_samples(stage9c)
        ],
        "schema": {"id": INTERACTION_PREFLIGHT_INPUT_SCHEMA_ID, "version": SCHEMA_VERSION},
        "srdf_content_fingerprint": collision_model.srdf_content_fingerprint,
    }


def interaction_preflight_input_fingerprint(
    request: GraspInteractionRequest,
    grasp_evidence_id: str,
    grasp_evidence_fingerprint: str,
) -> str:
    payload = canonical_json(
        interaction_preflight_input_document(
            request,
            grasp_evidence_id,
            grasp_evidence_fingerprint,
        )
    )
    return "stage9d-moveit-interaction-input-sha256-" + sha256(
        payload.encode("utf-8")
    ).hexdigest()


def moveit_interaction_proof_from_canonical_json(
    grasp: GraspEstablishedEvidence,
    payload: str,
) -> InteractionCollisionProof:
    """Reconstruct and bind exact raw MoveIt observations to one grasp interval."""

    if not verify_grasp_evidence(grasp):
        raise _error("MoveIt interaction grasp failed recursive verification")
    if type(payload) is not str:
        raise _error("MoveIt interaction report must be text")
    try:
        encoded = payload.encode("utf-8")
    except UnicodeError as error:
        raise _error("MoveIt interaction report must be UTF-8", error)
    if not encoded or len(encoded) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise _error("MoveIt interaction report violates its byte bound")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _error(f"non-finite {value} is forbidden")
            ),
        )
        item = _mapping(document, "MoveIt interaction report")
        if canonical_json(item) != payload:
            raise _error("MoveIt interaction report is not canonical JSON")
        expected_keys = {
            "allowed_collision_pair",
            "allowed_touch_links",
            "backend_id",
            "backend_version",
            "continuous_collision_certification",
            "global_acm_modified",
            "grasp_interval_only",
            "input_fingerprint",
            "physical_collision_certification",
            "samples",
            "samples_checked",
            "schema",
            "target_object_specific",
        }
        if set(item) != expected_keys:
            raise _error("MoveIt interaction fields differ from the closed v1 schema")
        if item["schema"] != {
            "id": RAW_INTERACTION_PREFLIGHT_SCHEMA_ID,
            "version": SCHEMA_VERSION,
        }:
            raise _error("unknown MoveIt interaction report schema or version")
        exact = {
            "allowed_collision_pair": [STAGE9D_END_EFFECTOR_LINK, STAGE9D_OBJECT_COLLISION],
            "allowed_touch_links": [STAGE9D_END_EFFECTOR_LINK],
            "backend_id": STAGE9D_COLLISION_BACKEND_ID,
            "backend_version": STAGE9D_COLLISION_BACKEND_VERSION,
            "continuous_collision_certification": False,
            "global_acm_modified": False,
            "grasp_interval_only": True,
            "input_fingerprint": interaction_preflight_input_fingerprint(
                grasp.request,
                grasp.grasp_evidence_id,
                grasp.grasp_evidence_fingerprint,
            ),
            "physical_collision_certification": False,
            "target_object_specific": True,
        }
        for field, expected in exact.items():
            if type(item[field]) is not type(expected) or item[field] != expected:
                raise _error(f"MoveIt interaction {field} differs from the exact grasp")
        planned = expected_dense_samples(grasp.request.stage9c_execution_request)
        raw_samples = _sequence(item["samples"], "MoveIt interaction samples")
        if (
            type(item["samples_checked"]) is not int
            or item["samples_checked"] != len(planned)
            or len(raw_samples) != len(planned)
        ):
            raise _error("MoveIt interaction did not check every dense sample")
        expected_sample_keys = {
            "attached_object_checked",
            "environment_collision_free",
            "positions",
            "sample_index",
            "self_collision_free",
            "within_joint_limits",
        }
        samples = []
        for raw, expected in zip(raw_samples, planned, strict=True):
            mapped = _mapping(raw, "MoveIt interaction sample")
            if set(mapped) != expected_sample_keys:
                raise _error("MoveIt interaction sample fields differ")
            sample = InteractionCollisionSample(
                sample_index=mapped["sample_index"],
                positions=tuple(_sequence(mapped["positions"], "sample positions")),
                within_joint_limits=mapped["within_joint_limits"],
                self_collision_free=mapped["self_collision_free"],
                environment_collision_free=mapped["environment_collision_free"],
                attached_object_checked=mapped["attached_object_checked"],
            )
            if sample.sample_index != expected.sample_index or sample.positions != expected.positions:
                raise _error("MoveIt interaction sample differs from Stage 9C interpolation")
            samples.append(sample)
        return InteractionCollisionProof(
            request=grasp.request,
            grasp_evidence_id=grasp.grasp_evidence_id,
            grasp_evidence_fingerprint=grasp.grasp_evidence_fingerprint,
            backend_id=item["backend_id"],
            backend_version=item["backend_version"],
            input_fingerprint=item["input_fingerprint"],
            samples=tuple(samples),
            allowed_touch_links=tuple(item["allowed_touch_links"]),
            allowed_collision_pair=tuple(item["allowed_collision_pair"]),
            target_object_specific=item["target_object_specific"],
            grasp_interval_only=item["grasp_interval_only"],
            global_acm_modified=item["global_acm_modified"],
            continuous_collision_certification=item[
                "continuous_collision_certification"
            ],
            physical_collision_certification=item[
                "physical_collision_certification"
            ],
        )
    except GraspInteractionSerializationError:
        raise
    except (
        ArithmeticError,
        GraspInteractionValidationError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("MoveIt interaction report failed closed", error)
