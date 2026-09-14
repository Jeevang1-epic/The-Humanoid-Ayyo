from __future__ import annotations

from dataclasses import replace

import pytest

from manipulation_simulation_execution.tests.conftest import (  # noqa: F401
    expanded_urdf,
    reviewed_srdf,
    stage9c_bundle,
    _stage9c_base,
)
from ayyo_manipulation_grasp_interaction import (
    ContactEvidence,
    EntityPoseEvidence,
    FixtureAttachmentState,
    FixtureStateEvidence,
    InteractionCollisionSample,
    ObservedEntityKind,
    STAGE9D_END_EFFECTOR_COLLISION,
    STAGE9D_END_EFFECTOR_ENTITY,
    STAGE9D_FIXTURE_ID,
    STAGE9D_OBJECT_COLLISION,
    STAGE9D_OBJECT_ID,
    STAGE9D_OBJECT_MODEL,
    create_grasp_interaction_request,
    create_grasp_interaction_result,
    create_interaction_collision_proof,
    establish_grasp,
    evaluate_hold,
    evaluate_pregrasp,
    evaluate_release,
)
from ayyo_manipulation_simulation_execution import (
    SimulationControllerState,
    SimulatedBasePose,
    evaluate_whole_body_stability,
    expected_dense_samples,
)


def _pose(request, kind, position, *, sequence, observed_at_ns):
    return EntityPoseEvidence(
        interaction_request_id=request.interaction_request_id,
        interaction_request_fingerprint=request.interaction_request_fingerprint,
        run_session_id=request.run_session_id,
        kind=kind,
        entity_name=(
            STAGE9D_END_EFFECTOR_ENTITY
            if kind is ObservedEntityKind.END_EFFECTOR
            else STAGE9D_OBJECT_MODEL
        ),
        frame_id="world",
        position_xyz=position,
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        observed_at_ns=observed_at_ns,
        sequence=sequence,
        entity_count=1,
        source=(
            "stage9d.tf2-gazebo-base.v1"
            if kind is ObservedEntityKind.END_EFFECTOR
            else "stage9d.gazebo-object-odometry.v1"
        ),
    )


def _fixture(request, state, *, sequence, observed_at_ns):
    return FixtureStateEvidence(
        interaction_request_id=request.interaction_request_id,
        interaction_request_fingerprint=request.interaction_request_fingerprint,
        run_session_id=request.run_session_id,
        fixture_id=STAGE9D_FIXTURE_ID,
        object_id=STAGE9D_OBJECT_ID,
        state=state,
        available=True,
        observed_at_ns=observed_at_ns,
        sequence=sequence,
    )


@pytest.fixture(scope="session")
def stage9d_bundle(_stage9c_base):
    stage9c_bundle = dict(_stage9c_base)
    request = create_grasp_interaction_request(
        stage9c_bundle["execution_request"],
        run_session_id="stage9d-test-run-1",
        requested_at_ns=500_000_000,
    )
    initial_end_effector = _pose(
        request,
        ObservedEntityKind.END_EFFECTOR,
        (0.0, 0.0, 1.0),
        sequence=1,
        observed_at_ns=900_000_000,
    )
    initial_object = _pose(
        request,
        ObservedEntityKind.GRASP_OBJECT,
        (0.02, 0.0, 0.83),
        sequence=1,
        observed_at_ns=900_000_000,
    )
    detached = _fixture(
        request,
        FixtureAttachmentState.DETACHED,
        sequence=1,
        observed_at_ns=900_000_000,
    )
    pregrasp = evaluate_pregrasp(
        request,
        initial_end_effector,
        initial_object,
        detached,
        evaluated_at_ns=1_000_000_000,
    )
    contact = ContactEvidence(
        interaction_request_id=request.interaction_request_id,
        interaction_request_fingerprint=request.interaction_request_fingerprint,
        run_session_id=request.run_session_id,
        object_id=STAGE9D_OBJECT_ID,
        collision_pairs=((STAGE9D_END_EFFECTOR_COLLISION, STAGE9D_OBJECT_COLLISION),),
        observed_at_ns=1_050_000_000,
        sequence=1,
        contact_count=1,
    )
    attached = _fixture(
        request,
        FixtureAttachmentState.ATTACHED,
        sequence=2,
        observed_at_ns=1_060_000_000,
    )
    grasp = establish_grasp(
        pregrasp,
        contact,
        attached,
        established_at_ns=1_070_000_000,
    )
    collision_samples = tuple(
        InteractionCollisionSample(
            sample_index=index,
            positions=sample.positions,
            within_joint_limits=True,
            self_collision_free=True,
            environment_collision_free=True,
            attached_object_checked=True,
        )
        for index, sample in enumerate(
            expected_dense_samples(stage9c_bundle["execution_request"])
        )
    )
    interaction_collision = create_interaction_collision_proof(
        grasp,
        collision_samples,
    )
    final_end_effector = _pose(
        request,
        ObservedEntityKind.END_EFFECTOR,
        (0.2, 0.3, 1.2),
        sequence=2,
        observed_at_ns=3_600_000_000,
    )
    final_object = _pose(
        request,
        ObservedEntityKind.GRASP_OBJECT,
        (0.22, 0.3, 1.03),
        sequence=2,
        observed_at_ns=3_600_000_000,
    )
    hold_attached = _fixture(
        request,
        FixtureAttachmentState.ATTACHED,
        sequence=3,
        observed_at_ns=3_600_000_000,
    )
    hold = evaluate_hold(
        grasp,
        interaction_collision,
        stage9c_bundle["result"],
        final_end_effector,
        final_object,
        hold_attached,
        evaluated_at_ns=3_700_000_000,
    )
    release_detached = _fixture(
        request,
        FixtureAttachmentState.DETACHED,
        sequence=4,
        observed_at_ns=3_810_000_000,
    )
    post_end_effector = _pose(
        request,
        ObservedEntityKind.END_EFFECTOR,
        (0.2, 0.3, 1.2),
        sequence=3,
        observed_at_ns=4_000_000_000,
    )
    post_object = _pose(
        request,
        ObservedEntityKind.GRASP_OBJECT,
        (0.22, 0.3, 1.01),
        sequence=3,
        observed_at_ns=4_000_000_000,
    )
    initial_whole = stage9c_bundle["initial_whole_body_state"]
    final_whole = replace(
        stage9c_bundle["final_whole_body_state"],
        observed_at_ns=4_000_000_000,
        sequence=3,
        base_pose=SimulatedBasePose(
            position_xyz=(0.0, 0.0, 0.95),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            observed_at_ns=4_000_000_000,
            sequence=3,
        ),
    )
    contract = request.stage9c_execution_request.controller_contract
    post_controller = SimulationControllerState(
        controller_contract_id=contract.controller_contract_id,
        controller_contract_fingerprint=contract.controller_contract_fingerprint,
        controller_active=True,
        hardware_active=True,
        state_broadcaster_active=True,
        action_server_available=True,
        support_fixture_active=True,
        base_pose_observable=True,
        claimed_command_interfaces=tuple(
            f"{name}/position" for name in contract.joint_names
        ),
        observed_at_ns=4_000_000_000,
    )
    post_release_stability = evaluate_whole_body_stability(
        initial_whole,
        final_whole,
        post_controller,
        evaluated_at_ns=4_000_000_000,
    )
    release = evaluate_release(
        hold,
        release_requested_at_ns=3_800_000_000,
        detached_fixture=release_detached,
        post_release_end_effector_pose=post_end_effector,
        post_release_object_pose=post_object,
        post_release_stability=post_release_stability,
        evaluated_at_ns=4_000_000_000,
    )
    result = create_grasp_interaction_result(request, release)
    return {
        **stage9c_bundle,
        "stage9c_result": stage9c_bundle["result"],
        "request": request,
        "end_effector_contract": request.end_effector,
        "object_contract": request.grasp_object,
        "initial_end_effector": initial_end_effector,
        "initial_object": initial_object,
        "detached": detached,
        "pregrasp": pregrasp,
        "contact": contact,
        "attached": attached,
        "grasp": grasp,
        "interaction_collision": interaction_collision,
        "final_end_effector": final_end_effector,
        "final_object": final_object,
        "hold_attached": hold_attached,
        "hold": hold,
        "release_detached": release_detached,
        "post_end_effector": post_end_effector,
        "post_object": post_object,
        "post_release_stability": post_release_stability,
        "release": release,
        "result": result,
    }
