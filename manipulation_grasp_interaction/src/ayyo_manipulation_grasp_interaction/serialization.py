"""Strict canonical serialization for Stage 9D evidence."""

from __future__ import annotations

import json
from typing import Callable, TypeAlias

from ayyo_manipulation_simulation_execution import (
    simulation_execution_artifact_from_canonical_json,
)

from .canonical import MAX_SERIALIZED_ARTIFACT_BYTES, canonical_json
from .errors import (
    GraspInteractionSerializationError,
    GraspInteractionValidationError,
)
from .models import (
    COLLISION_PROOF_SCHEMA_ID,
    CONTACT_EVIDENCE_SCHEMA_ID,
    END_EFFECTOR_CONTRACT_SCHEMA_ID,
    FIXTURE_EVIDENCE_SCHEMA_ID,
    GRASP_EVIDENCE_SCHEMA_ID,
    HOLD_EVIDENCE_SCHEMA_ID,
    OBJECT_CONTRACT_SCHEMA_ID,
    POSE_EVIDENCE_SCHEMA_ID,
    PREGRASP_EVIDENCE_SCHEMA_ID,
    RELEASE_EVIDENCE_SCHEMA_ID,
    REQUEST_SCHEMA_ID,
    RESULT_SCHEMA_ID,
    ContactEvidence,
    EndEffectorContract,
    EntityPoseEvidence,
    FixtureAttachmentState,
    FixtureAvailability,
    FixtureStateEvidence,
    GraspEstablishedEvidence,
    GraspInteractionMode,
    GraspInteractionPhase,
    GraspInteractionRequest,
    GraspInteractionResult,
    GraspInteractionResultStatus,
    GraspableObjectContract,
    HardwareAuthority,
    HoldEvidence,
    InteractionCollisionProof,
    InteractionCollisionSample,
    ObservedEntityKind,
    PhysicalValidationClaim,
    PregraspEvidence,
    ProductionRuntimeAuthority,
    ReleaseEvidence,
    SimulationAuthority,
    verify_collision_proof,
    verify_contact_evidence,
    verify_end_effector_contract,
    verify_fixture_evidence,
    verify_grasp_evidence,
    verify_hold_evidence,
    verify_interaction_request,
    verify_interaction_result,
    verify_object_contract,
    verify_pose_evidence,
    verify_pregrasp_evidence,
    verify_release_evidence,
)


Stage9DArtifact: TypeAlias = (
    EndEffectorContract
    | GraspableObjectContract
    | GraspInteractionRequest
    | EntityPoseEvidence
    | FixtureStateEvidence
    | ContactEvidence
    | PregraspEvidence
    | GraspEstablishedEvidence
    | InteractionCollisionProof
    | HoldEvidence
    | ReleaseEvidence
    | GraspInteractionResult
)


def _error(detail: str, cause: BaseException | None = None) -> GraspInteractionSerializationError:
    error = GraspInteractionSerializationError(detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"duplicate canonical key: {key}")
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


def _verified(item: dict, artifact: Stage9DArtifact) -> Stage9DArtifact:
    if artifact.as_dict() != item:
        raise _error("Stage 9D artifact contains stale, missing, or unexpected data")
    return artifact


def _stage9c(value: object, context: dict):
    item = _mapping(value, "nested Stage 9C artifact")
    return simulation_execution_artifact_from_canonical_json(
        canonical_json(item),
        **context,
    )


def _end_effector(value: object) -> EndEffectorContract:
    item = _mapping(value, "end-effector contract")
    return _verified(
        item,
        EndEffectorContract(
            robot_name=item["robot_name"],
            robot_model_id=item["robot_model_id"],
            robot_model_fingerprint=item["robot_model_fingerprint"],
            end_effector_link=item["end_effector_link"],
            end_effector_frame=item["end_effector_frame"],
            end_effector_entity=item["end_effector_entity"],
            contact_collision=item["contact_collision"],
            fixture_id=item["fixture_id"],
            fixture_version=item["fixture_version"],
            mode=GraspInteractionMode(item["mode"]),
            availability=FixtureAvailability(item["availability"]),
            authority=SimulationAuthority(item["authority"]),
        ),
    )


def _object_contract(value: object) -> GraspableObjectContract:
    item = _mapping(value, "object contract")
    return _verified(
        item,
        GraspableObjectContract(
            object_id=item["object_id"],
            model_name=item["model_name"],
            link_name=item["link_name"],
            collision_name=item["collision_name"],
            primitive=item["primitive"],
            dimensions_xyz=tuple(_sequence(item["dimensions_xyz"], "dimensions_xyz")),
            initial_frame=item["initial_frame"],
            initial_position_xyz=tuple(
                _sequence(item["initial_position_xyz"], "initial_position_xyz")
            ),
            initial_orientation_xyzw=tuple(
                _sequence(
                    item["initial_orientation_xyzw"],
                    "initial_orientation_xyzw",
                )
            ),
            mass_kg=item["mass_kg"],
            inertia_diagonal=tuple(
                _sequence(item["inertia_diagonal"], "inertia_diagonal")
            ),
            gravity_enabled=item["gravity_enabled"],
            collision_enabled=item["collision_enabled"],
            dynamic=item["dynamic"],
            provenance=item["provenance"],
            allowed_target_identity=item["allowed_target_identity"],
        ),
    )


def _request(value: object, context: dict) -> GraspInteractionRequest:
    item = _mapping(value, "interaction request")
    return _verified(
        item,
        GraspInteractionRequest(
            stage9c_execution_request=_stage9c(
                item["stage9c_execution_request"], context
            ),
            end_effector=_end_effector(item["end_effector"]),
            grasp_object=_object_contract(item["grasp_object"]),
            run_session_id=item["run_session_id"],
            requested_at_ns=item["requested_at_ns"],
            profile_id=item["profile_id"],
            authority=SimulationAuthority(item["authority"]),
        ),
    )


def _pose(value: object) -> EntityPoseEvidence:
    item = _mapping(value, "pose evidence")
    return _verified(
        item,
        EntityPoseEvidence(
            interaction_request_id=item["interaction_request_id"],
            interaction_request_fingerprint=item["interaction_request_fingerprint"],
            run_session_id=item["run_session_id"],
            kind=ObservedEntityKind(item["kind"]),
            entity_name=item["entity_name"],
            frame_id=item["frame_id"],
            position_xyz=tuple(_sequence(item["position_xyz"], "position_xyz")),
            orientation_xyzw=tuple(
                _sequence(item["orientation_xyzw"], "orientation_xyzw")
            ),
            observed_at_ns=item["observed_at_ns"],
            sequence=item["sequence"],
            entity_count=item["entity_count"],
            source=item["source"],
        ),
    )


def _fixture(value: object) -> FixtureStateEvidence:
    item = _mapping(value, "fixture evidence")
    return _verified(
        item,
        FixtureStateEvidence(
            interaction_request_id=item["interaction_request_id"],
            interaction_request_fingerprint=item["interaction_request_fingerprint"],
            run_session_id=item["run_session_id"],
            fixture_id=item["fixture_id"],
            object_id=item["object_id"],
            state=FixtureAttachmentState(item["state"]),
            available=item["available"],
            observed_at_ns=item["observed_at_ns"],
            sequence=item["sequence"],
            source_topic=item["source_topic"],
        ),
    )


def _contact(value: object) -> ContactEvidence:
    item = _mapping(value, "contact evidence")
    return _verified(
        item,
        ContactEvidence(
            interaction_request_id=item["interaction_request_id"],
            interaction_request_fingerprint=item["interaction_request_fingerprint"],
            run_session_id=item["run_session_id"],
            object_id=item["object_id"],
            collision_pairs=tuple(
                tuple(_sequence(pair, "contact pair"))
                for pair in _sequence(item["collision_pairs"], "collision_pairs")
            ),
            observed_at_ns=item["observed_at_ns"],
            sequence=item["sequence"],
            contact_count=item["contact_count"],
            maximum_penetration_depth=item["maximum_penetration_depth"],
            source_topic=item["source_topic"],
            message_type=item["message_type"],
            phase=GraspInteractionPhase(item["phase"]),
        ),
    )


def _pregrasp(value: object, context: dict) -> PregraspEvidence:
    item = _mapping(value, "pregrasp evidence")
    return _verified(
        item,
        PregraspEvidence(
            request=_request(item["request"], context),
            end_effector_pose=_pose(item["end_effector_pose"]),
            object_pose=_pose(item["object_pose"]),
            detached_fixture=_fixture(item["detached_fixture"]),
            evaluated_at_ns=item["evaluated_at_ns"],
            translation_error=item["translation_error"],
            rotation_error=item["rotation_error"],
            translation_tolerance=item["translation_tolerance"],
            rotation_tolerance=item["rotation_tolerance"],
            phase=GraspInteractionPhase(item["phase"]),
        ),
    )


def _grasp(value: object, context: dict) -> GraspEstablishedEvidence:
    item = _mapping(value, "grasp evidence")
    return _verified(
        item,
        GraspEstablishedEvidence(
            pregrasp=_pregrasp(item["pregrasp"], context),
            contact=_contact(item["contact"]),
            attached_fixture=_fixture(item["attached_fixture"]),
            established_at_ns=item["established_at_ns"],
            phase=GraspInteractionPhase(item["phase"]),
        ),
    )


def _collision_sample(value: object) -> InteractionCollisionSample:
    item = _mapping(value, "interaction collision sample")
    sample = InteractionCollisionSample(
        sample_index=item["sample_index"],
        positions=tuple(_sequence(item["positions"], "sample positions")),
        within_joint_limits=item["within_joint_limits"],
        self_collision_free=item["self_collision_free"],
        environment_collision_free=item["environment_collision_free"],
        attached_object_checked=item["attached_object_checked"],
    )
    if sample.as_dict() != item:
        raise _error("collision sample contains stale or unexpected data")
    return sample


def _collision(value: object, context: dict) -> InteractionCollisionProof:
    item = _mapping(value, "collision proof")
    return _verified(
        item,
        InteractionCollisionProof(
            request=_request(item["request"], context),
            grasp_evidence_id=item["grasp_evidence_id"],
            grasp_evidence_fingerprint=item["grasp_evidence_fingerprint"],
            backend_id=item["backend_id"],
            backend_version=item["backend_version"],
            samples=tuple(
                _collision_sample(value)
                for value in _sequence(item["samples"], "collision samples")
            ),
            allowed_touch_links=tuple(
                _sequence(item["allowed_touch_links"], "allowed_touch_links")
            ),
            allowed_collision_pair=tuple(
                _sequence(item["allowed_collision_pair"], "allowed_collision_pair")
            ),
            target_object_specific=item["target_object_specific"],
            grasp_interval_only=item["grasp_interval_only"],
            global_acm_modified=item["global_acm_modified"],
            continuous_collision_certification=item[
                "continuous_collision_certification"
            ],
            physical_collision_certification=item[
                "physical_collision_certification"
            ],
        ),
    )


def _hold(value: object, context: dict) -> HoldEvidence:
    item = _mapping(value, "hold evidence")
    return _verified(
        item,
        HoldEvidence(
            grasp=_grasp(item["grasp"], context),
            collision_proof=_collision(item["collision_proof"], context),
            stage9c_result=_stage9c(item["stage9c_result"], context),
            final_end_effector_pose=_pose(item["final_end_effector_pose"]),
            final_object_pose=_pose(item["final_object_pose"]),
            attached_fixture=_fixture(item["attached_fixture"]),
            evaluated_at_ns=item["evaluated_at_ns"],
            relative_translation_change=item["relative_translation_change"],
            relative_rotation_change=item["relative_rotation_change"],
            object_world_displacement=item["object_world_displacement"],
            translation_tolerance=item["translation_tolerance"],
            rotation_tolerance=item["rotation_tolerance"],
            maximum_object_teleport=item["maximum_object_teleport"],
            phase=GraspInteractionPhase(item["phase"]),
        ),
    )


def _release(value: object, context: dict) -> ReleaseEvidence:
    item = _mapping(value, "release evidence")
    return _verified(
        item,
        ReleaseEvidence(
            hold=_hold(item["hold"], context),
            release_requested_at_ns=item["release_requested_at_ns"],
            detached_fixture=_fixture(item["detached_fixture"]),
            post_release_end_effector_pose=_pose(
                item["post_release_end_effector_pose"]
            ),
            post_release_object_pose=_pose(item["post_release_object_pose"]),
            post_release_stability=_stage9c(
                item["post_release_stability"], context
            ),
            evaluated_at_ns=item["evaluated_at_ns"],
            relative_pose_change=item["relative_pose_change"],
            minimum_relative_change=item["minimum_relative_change"],
            requested_phase=GraspInteractionPhase(item["requested_phase"]),
            phase=GraspInteractionPhase(item["phase"]),
        ),
    )


def _result(value: object, context: dict) -> GraspInteractionResult:
    item = _mapping(value, "interaction result")
    return _verified(
        item,
        GraspInteractionResult(
            request=_request(item["request"], context),
            release=_release(item["release"], context),
            status=GraspInteractionResultStatus(item["status"]),
            completed_phases=tuple(
                GraspInteractionPhase(value)
                for value in _sequence(item["completed_phases"], "completed phases")
            ),
            failure_reasons=tuple(),
            authority=SimulationAuthority(item["authority"]),
            physical_validation=PhysicalValidationClaim(item["physical_validation"]),
            hardware_authority=HardwareAuthority(item["hardware_authority"]),
            production_runtime_authority=ProductionRuntimeAuthority(
                item["production_runtime_authority"]
            ),
        ),
    )


_VERIFIERS: dict[type, Callable[[object], bool]] = {
    EndEffectorContract: verify_end_effector_contract,
    GraspableObjectContract: verify_object_contract,
    GraspInteractionRequest: verify_interaction_request,
    EntityPoseEvidence: verify_pose_evidence,
    FixtureStateEvidence: verify_fixture_evidence,
    ContactEvidence: verify_contact_evidence,
    PregraspEvidence: verify_pregrasp_evidence,
    GraspEstablishedEvidence: verify_grasp_evidence,
    InteractionCollisionProof: verify_collision_proof,
    HoldEvidence: verify_hold_evidence,
    ReleaseEvidence: verify_release_evidence,
    GraspInteractionResult: verify_interaction_result,
}


def canonical_grasp_interaction_artifact_json(artifact: Stage9DArtifact) -> str:
    """Serialize only recursively verified Stage 9D artifacts."""

    try:
        verifier = _VERIFIERS.get(type(artifact))
        if verifier is None or not verifier(artifact):
            raise _error("Stage 9D artifact failed recursive integrity verification")
        payload = canonical_json(artifact.as_dict())
        if len(payload.encode("utf-8")) > MAX_SERIALIZED_ARTIFACT_BYTES:
            raise _error("Stage 9D artifact violates its byte bound")
        return payload
    except GraspInteractionSerializationError:
        raise
    except (
        AssertionError,
        ArithmeticError,
        AttributeError,
        KeyError,
        GraspInteractionValidationError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("Stage 9D artifact cannot be serialized canonically", error)


def grasp_interaction_artifact_from_canonical_json(
    payload: str,
    *,
    source_proposal=None,
    source_safety_decision=None,
    source_safety_kernel=None,
    source_skill_binding=None,
    source_skill_manager=None,
) -> Stage9DArtifact:
    """Reconstruct exact bytes while delegating Stage 9C lineage verification."""

    if type(payload) is not str:
        raise _error("canonical Stage 9D payload must be text")
    try:
        encoded = payload.encode("utf-8")
    except UnicodeError as error:
        raise _error("canonical Stage 9D payload must be UTF-8", error)
    if not encoded or len(encoded) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise _error("canonical Stage 9D payload violates its byte bound")
    context = {
        "source_proposal": source_proposal,
        "source_safety_decision": source_safety_decision,
        "source_safety_kernel": source_safety_kernel,
        "source_skill_binding": source_skill_binding,
        "source_skill_manager": source_skill_manager,
    }
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _error(f"non-finite {value} is forbidden")
            ),
        )
        item = _mapping(document, "Stage 9D artifact")
        if canonical_json(item) != payload:
            raise _error("Stage 9D payload is not canonical JSON")
        schema = _mapping(item.get("schema"), "schema")
        schema_id = schema.get("id")
        if schema_id == END_EFFECTOR_CONTRACT_SCHEMA_ID:
            return _end_effector(item)
        if schema_id == OBJECT_CONTRACT_SCHEMA_ID:
            return _object_contract(item)
        if schema_id == REQUEST_SCHEMA_ID:
            return _request(item, context)
        if schema_id == POSE_EVIDENCE_SCHEMA_ID:
            return _pose(item)
        if schema_id == FIXTURE_EVIDENCE_SCHEMA_ID:
            return _fixture(item)
        if schema_id == CONTACT_EVIDENCE_SCHEMA_ID:
            return _contact(item)
        if schema_id == PREGRASP_EVIDENCE_SCHEMA_ID:
            return _pregrasp(item, context)
        if schema_id == GRASP_EVIDENCE_SCHEMA_ID:
            return _grasp(item, context)
        if schema_id == COLLISION_PROOF_SCHEMA_ID:
            return _collision(item, context)
        if schema_id == HOLD_EVIDENCE_SCHEMA_ID:
            return _hold(item, context)
        if schema_id == RELEASE_EVIDENCE_SCHEMA_ID:
            return _release(item, context)
        if schema_id == RESULT_SCHEMA_ID:
            return _result(item, context)
        raise _error("unknown Stage 9D artifact schema")
    except GraspInteractionSerializationError:
        raise
    except (
        AssertionError,
        ArithmeticError,
        AttributeError,
        json.JSONDecodeError,
        KeyError,
        GraspInteractionValidationError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("Stage 9D payload failed closed during reconstruction", error)
