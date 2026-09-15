from __future__ import annotations

import copy
from dataclasses import replace
from math import inf, nan

import pytest

from ayyo_manipulation_grasp_interaction import (
    ContactEvidence,
    EndEffectorContract,
    EntityPoseEvidence,
    FixtureAttachmentState,
    GraspInteractionFailureCode,
    GraspInteractionPhase,
    GraspInteractionResultStatus,
    GraspInteractionValidationError,
    ObservedEntityKind,
    STAGE9D_END_EFFECTOR_COLLISION,
    STAGE9D_OBJECT_COLLISION,
    STAGE9D_OBJECT_ID,
    STAGE9D_OBJECT_MODEL,
    create_grasp_interaction_request,
    establish_grasp,
    evaluate_hold,
    evaluate_pregrasp,
    evaluate_release,
    verify_interaction_result,
)


def test_positive_result_has_exact_bounded_progression(stage9d_bundle) -> None:
    result = stage9d_bundle["result"]
    assert result.status is GraspInteractionResultStatus.SIMULATION_GRASP_INTERACTION_COMPLETED
    assert result.completed_phases == tuple(GraspInteractionPhase)
    assert result.failure_reasons == ()
    assert result.authority.value == "development_simulation_only"
    assert result.physical_validation.value == "not_physically_validated"
    assert result.hardware_authority.value == "no_hardware_authority"
    assert result.production_runtime_authority.value == "no_production_runtime_authority"
    assert verify_interaction_result(result)


def test_deterministic_contracts_and_run_specific_requests(stage9d_bundle) -> None:
    request = stage9d_bundle["request"]
    same = create_grasp_interaction_request(
        request.stage9c_execution_request,
        run_session_id=request.run_session_id,
        requested_at_ns=request.requested_at_ns,
    )
    other = create_grasp_interaction_request(
        request.stage9c_execution_request,
        run_session_id="stage9d-test-run-2",
        requested_at_ns=request.requested_at_ns,
    )
    assert same == request
    assert same.end_effector == request.end_effector
    assert same.grasp_object == request.grasp_object
    assert other.interaction_request_id != request.interaction_request_id


def test_exact_object_and_end_effector_contracts(stage9d_bundle) -> None:
    request = stage9d_bundle["request"]
    assert request.end_effector.end_effector_link == "left_hand_link"
    assert request.end_effector.contact_collision == STAGE9D_END_EFFECTOR_COLLISION
    assert request.grasp_object.object_id == STAGE9D_OBJECT_ID
    assert request.grasp_object.collision_name == STAGE9D_OBJECT_COLLISION
    assert request.grasp_object.dimensions_xyz == (0.03, 0.03, 0.02)
    assert request.grasp_object.mass_kg == 0.05
    assert request.grasp_object.gravity_enabled
    assert request.grasp_object.dynamic


def test_fixture_must_begin_detached(stage9d_bundle) -> None:
    attached = replace(
        stage9d_bundle["detached"],
        state=FixtureAttachmentState.ATTACHED,
    )
    with pytest.raises(GraspInteractionValidationError) as raised:
        evaluate_pregrasp(
            stage9d_bundle["request"],
            stage9d_bundle["initial_end_effector"],
            stage9d_bundle["initial_object"],
            attached,
            evaluated_at_ns=1_000_000_000,
        )
    assert raised.value.code is GraspInteractionFailureCode.FIXTURE_UNEXPECTEDLY_ATTACHED


def test_wrong_end_effector_link_substitution_fails_closed(stage9d_bundle) -> None:
    contract = stage9d_bundle["end_effector_contract"]
    with pytest.raises(GraspInteractionValidationError) as raised:
        EndEffectorContract(
            robot_name=contract.robot_name,
            robot_model_id=contract.robot_model_id,
            robot_model_fingerprint=contract.robot_model_fingerprint,
            end_effector_link="left_wrist_link",
        )
    assert raised.value.code is GraspInteractionFailureCode.WRONG_END_EFFECTOR


def test_duplicate_object_observation_fails_closed(stage9d_bundle) -> None:
    with pytest.raises(GraspInteractionValidationError) as raised:
        replace(stage9d_bundle["initial_object"], entity_count=2)
    assert raised.value.code is GraspInteractionFailureCode.DUPLICATE_OBJECT


def test_wrong_contact_participant_fails_closed(stage9d_bundle) -> None:
    request = stage9d_bundle["request"]
    with pytest.raises(GraspInteractionValidationError) as raised:
        ContactEvidence(
            interaction_request_id=request.interaction_request_id,
            interaction_request_fingerprint=request.interaction_request_fingerprint,
            run_session_id=request.run_session_id,
            object_id=STAGE9D_OBJECT_ID,
            collision_pairs=((STAGE9D_OBJECT_COLLISION, "ground::link::collision"),),
            observed_at_ns=1_050_000_000,
            sequence=1,
            contact_count=1,
        )
    assert raised.value.code is GraspInteractionFailureCode.WRONG_CONTACT_PARTICIPANTS


def test_contact_duplicates_are_replay_not_target_contact(stage9d_bundle) -> None:
    request = stage9d_bundle["request"]
    pair = (STAGE9D_END_EFFECTOR_COLLISION, STAGE9D_OBJECT_COLLISION)
    with pytest.raises(GraspInteractionValidationError) as raised:
        ContactEvidence(
            interaction_request_id=request.interaction_request_id,
            interaction_request_fingerprint=request.interaction_request_fingerprint,
            run_session_id=request.run_session_id,
            object_id=STAGE9D_OBJECT_ID,
            collision_pairs=(pair, pair),
            observed_at_ns=1_050_000_000,
            sequence=1,
            contact_count=2,
        )
    assert raised.value.code is GraspInteractionFailureCode.CONTACT_REPLAY


def test_attach_without_contact_is_rejected(stage9d_bundle) -> None:
    with pytest.raises(GraspInteractionValidationError) as raised:
        establish_grasp(
            stage9d_bundle["pregrasp"],
            None,
            stage9d_bundle["attached"],
            established_at_ns=1_070_000_000,
        )
    assert raised.value.code is GraspInteractionFailureCode.NO_CONTACT


def test_stale_contact_cannot_establish_grasp(stage9d_bundle) -> None:
    stale = replace(stage9d_bundle["contact"], observed_at_ns=400_000_000)
    with pytest.raises(GraspInteractionValidationError) as raised:
        replace(stage9d_bundle["grasp"], contact=stale)
    assert raised.value.code is GraspInteractionFailureCode.CONTACT_REPLAY


def test_cross_run_contact_composition_fails(stage9d_bundle) -> None:
    contact = replace(stage9d_bundle["contact"], run_session_id="stage9d-test-run-2")
    with pytest.raises(GraspInteractionValidationError) as raised:
        replace(stage9d_bundle["grasp"], contact=contact)
    assert raised.value.code is GraspInteractionFailureCode.CROSS_RUN_COMPOSITION


def test_object_disappearance_fails_hold(stage9d_bundle) -> None:
    with pytest.raises(GraspInteractionValidationError) as raised:
        evaluate_hold(
            stage9d_bundle["grasp"],
            stage9d_bundle["interaction_collision"],
            stage9d_bundle["stage9c_result"],
            stage9d_bundle["final_end_effector"],
            None,
            stage9d_bundle["hold_attached"],
            evaluated_at_ns=3_700_000_000,
        )
    assert raised.value.code is GraspInteractionFailureCode.OBJECT_DISAPPEARED


def test_hold_without_attachment_is_rejected(stage9d_bundle) -> None:
    detached = replace(
        stage9d_bundle["hold_attached"],
        state=FixtureAttachmentState.DETACHED,
    )
    with pytest.raises(GraspInteractionValidationError) as raised:
        evaluate_hold(
            stage9d_bundle["grasp"],
            stage9d_bundle["interaction_collision"],
            stage9d_bundle["stage9c_result"],
            stage9d_bundle["final_end_effector"],
            stage9d_bundle["final_object"],
            detached,
            evaluated_at_ns=3_700_000_000,
        )
    assert raised.value.code is GraspInteractionFailureCode.ATTACHMENT_STATE_MISMATCH


def test_reordered_collision_samples_are_rejected(stage9d_bundle) -> None:
    proof = stage9d_bundle["interaction_collision"]
    with pytest.raises(GraspInteractionValidationError) as raised:
        replace(proof, samples=tuple(reversed(proof.samples)))
    assert raised.value.code is GraspInteractionFailureCode.INTERACTION_COLLISION


def test_slip_translation_boundary_is_enforced(stage9d_bundle) -> None:
    slipped = replace(
        stage9d_bundle["final_object"],
        position_xyz=(0.226, 0.3, 1.03),
    )
    with pytest.raises(GraspInteractionValidationError) as raised:
        evaluate_hold(
            stage9d_bundle["grasp"],
            stage9d_bundle["interaction_collision"],
            stage9d_bundle["stage9c_result"],
            stage9d_bundle["final_end_effector"],
            slipped,
            stage9d_bundle["hold_attached"],
            evaluated_at_ns=3_700_000_000,
        )
    assert raised.value.code is GraspInteractionFailureCode.SLIP_HOLD_FAILURE


def test_slip_rotation_boundary_is_enforced(stage9d_bundle) -> None:
    rotated = replace(
        stage9d_bundle["final_object"],
        orientation_xyzw=(0.0, 0.0, 0.03, 0.9995498987044118),
    )
    with pytest.raises(GraspInteractionValidationError) as raised:
        evaluate_hold(
            stage9d_bundle["grasp"],
            stage9d_bundle["interaction_collision"],
            stage9d_bundle["stage9c_result"],
            stage9d_bundle["final_end_effector"],
            rotated,
            stage9d_bundle["hold_attached"],
            evaluated_at_ns=3_700_000_000,
        )
    assert raised.value.code is GraspInteractionFailureCode.SLIP_HOLD_FAILURE


def test_release_requires_non_rigid_relative_change(stage9d_bundle) -> None:
    unchanged = replace(
        stage9d_bundle["post_object"],
        position_xyz=stage9d_bundle["final_object"].position_xyz,
    )
    with pytest.raises(GraspInteractionValidationError) as raised:
        evaluate_release(
            stage9d_bundle["hold"],
            release_requested_at_ns=3_800_000_000,
            detached_fixture=stage9d_bundle["release_detached"],
            post_release_end_effector_pose=stage9d_bundle["post_end_effector"],
            post_release_object_pose=unchanged,
            post_release_stability=stage9d_bundle["post_release_stability"],
            evaluated_at_ns=4_000_000_000,
        )
    assert raised.value.code is GraspInteractionFailureCode.RELEASE_REJECTED


@pytest.mark.parametrize("bad", (nan, inf, -inf, -0.0))
def test_malformed_numeric_pose_values_fail_closed(stage9d_bundle, bad: float) -> None:
    pose = stage9d_bundle["initial_object"]
    with pytest.raises(GraspInteractionValidationError):
        replace(pose, position_xyz=(bad, *pose.position_xyz[1:]))


def test_changed_nested_stage9c_result_is_rejected(stage9d_bundle) -> None:
    result = copy.copy(stage9d_bundle["stage9c_result"])
    object.__setattr__(result, "execution_result_id", "stage9c-execution-result-sha256-" + "0" * 64)
    with pytest.raises(GraspInteractionValidationError) as raised:
        evaluate_hold(
            stage9d_bundle["grasp"],
            stage9d_bundle["interaction_collision"],
            result,
            stage9d_bundle["final_end_effector"],
            stage9d_bundle["final_object"],
            stage9d_bundle["hold_attached"],
            evaluated_at_ns=3_700_000_000,
        )
    assert raised.value.code is GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE


def test_pose_substitution_is_rejected(stage9d_bundle) -> None:
    pose = stage9d_bundle["final_object"]
    with pytest.raises(GraspInteractionValidationError) as raised:
        EntityPoseEvidence(
            interaction_request_id=pose.interaction_request_id,
            interaction_request_fingerprint=pose.interaction_request_fingerprint,
            run_session_id=pose.run_session_id,
            kind=ObservedEntityKind.GRASP_OBJECT,
            entity_name="unreviewed_object",
            frame_id=pose.frame_id,
            position_xyz=pose.position_xyz,
            orientation_xyzw=pose.orientation_xyzw,
            observed_at_ns=pose.observed_at_ns,
            sequence=pose.sequence,
            entity_count=1,
            source=pose.source,
        )
    assert raised.value.code is GraspInteractionFailureCode.OBJECT_SUBSTITUTION
