# Copyright 2026 P. Jeevan Kumar

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from ayyo_manipulation_grasp_interaction import (
    ContactEvidence,
    EntityPoseEvidence,
    FixtureAttachmentState,
    FixtureStateEvidence,
    ObservedEntityKind,
    STAGE9D_END_EFFECTOR_COLLISION,
    STAGE9D_END_EFFECTOR_ENTITY,
    STAGE9D_FIXTURE_ID,
    STAGE9D_OBJECT_COLLISION,
    STAGE9D_OBJECT_ID,
    STAGE9D_OBJECT_MODEL,
    create_grasp_interaction_request,
    establish_grasp,
    evaluate_pregrasp,
    interaction_preflight_input_document,
    moveit_interaction_proof_from_canonical_json,
)
from ayyo_manipulation_planning import moveit_collision_proof_from_canonical_json


def _fixture_module():
    path = (
        Path(get_package_prefix('ayyo_manipulation_simulation_execution'))
        / 'lib/ayyo_manipulation_simulation_execution/stage9c_reviewed_fixture.py'
    )
    spec = importlib.util.spec_from_file_location('stage9c_reviewed_fixture', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _grasp():
    fixture = _fixture_module()
    description = Path(get_package_share_directory('ayyo_description'))
    planning = Path(get_package_share_directory('ayyo_manipulation_planning'))
    xacro = description / 'urdf/ayyo.urdf.xacro'
    srdf_path = planning / 'config/ayyo_left_arm.srdf'
    urdf = subprocess.run(
        ['xacro', str(xacro), 'use_meshes:=false', 'simulation_mode:=false'],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    planning_request = fixture.reviewed_planning_request(
        urdf,
        srdf_path.read_text(encoding='utf-8'),
    )
    stage9a_executable = (
        Path(get_package_prefix('ayyo_manipulation_planning'))
        / 'lib/ayyo_manipulation_planning/moveit_planning_scene_proof'
    )
    stage9a_report = subprocess.run(
        [str(stage9a_executable), str(srdf_path)],
        input=urdf,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout
    stage9a_proof = moveit_collision_proof_from_canonical_json(
        planning_request,
        stage9a_report,
    )
    stage9c_request = fixture.reviewed_execution_request(
        planning_request,
        stage9a_proof,
    )
    request = create_grasp_interaction_request(
        stage9c_request,
        run_session_id='stage9d-moveit-test-run',
        requested_at_ns=100,
    )
    common = {
        'interaction_request_id': request.interaction_request_id,
        'interaction_request_fingerprint': request.interaction_request_fingerprint,
        'run_session_id': request.run_session_id,
    }
    hand = EntityPoseEvidence(
        **common,
        kind=ObservedEntityKind.END_EFFECTOR,
        entity_name=STAGE9D_END_EFFECTOR_ENTITY,
        frame_id='world',
        position_xyz=(0.0, 0.0, 1.0),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        observed_at_ns=200,
        sequence=1,
        entity_count=1,
        source='stage9d.tf2-gazebo-base.v1',
    )
    obj = EntityPoseEvidence(
        **common,
        kind=ObservedEntityKind.GRASP_OBJECT,
        entity_name=STAGE9D_OBJECT_MODEL,
        frame_id='world',
        position_xyz=(0.02, 0.0, 0.83),
        orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
        observed_at_ns=200,
        sequence=1,
        entity_count=1,
        source='stage9d.gazebo-object-odometry.v1',
    )
    detached = FixtureStateEvidence(
        **common,
        fixture_id=STAGE9D_FIXTURE_ID,
        object_id=STAGE9D_OBJECT_ID,
        state=FixtureAttachmentState.DETACHED,
        available=True,
        observed_at_ns=200,
        sequence=1,
    )
    pregrasp = evaluate_pregrasp(
        request,
        hand,
        obj,
        detached,
        evaluated_at_ns=250,
    )
    contact = ContactEvidence(
        **common,
        object_id=STAGE9D_OBJECT_ID,
        collision_pairs=((STAGE9D_END_EFFECTOR_COLLISION, STAGE9D_OBJECT_COLLISION),),
        observed_at_ns=300,
        sequence=1,
        contact_count=1,
    )
    attached = FixtureStateEvidence(
        **common,
        fixture_id=STAGE9D_FIXTURE_ID,
        object_id=STAGE9D_OBJECT_ID,
        state=FixtureAttachmentState.ATTACHED,
        available=True,
        observed_at_ns=350,
        sequence=2,
    )
    grasp = establish_grasp(
        pregrasp,
        contact,
        attached,
        established_at_ns=400,
    )
    return grasp, urdf, srdf_path


def _run(executable: Path, srdf_path: Path, urdf: str, document: dict):
    input_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', suffix='.json', delete=False
        ) as stream:
            json.dump(document, stream, separators=(',', ':'), sort_keys=True)
            input_path = Path(stream.name)
        return subprocess.run(
            [str(executable), str(srdf_path), str(input_path)],
            input=urdf,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        if input_path is not None:
            input_path.unlink(missing_ok=True)


def test_stage9d_preflight_is_deterministic_target_specific_and_nonexecuting() -> None:
    grasp, urdf, srdf_path = _grasp()
    executable = (
        Path(get_package_prefix('ayyo_manipulation_grasp_interaction'))
        / 'lib/ayyo_manipulation_grasp_interaction/stage9d_moveit_preflight'
    )
    document = interaction_preflight_input_document(
        grasp.request,
        grasp.grasp_evidence_id,
        grasp.grasp_evidence_fingerprint,
    )
    first = _run(executable, srdf_path, urdf, document)
    second = _run(executable, srdf_path, urdf, document)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    proof = moveit_interaction_proof_from_canonical_json(grasp, first.stdout)
    assert proof.collision_free
    assert proof.allowed_touch_links == ('left_hand_link',)
    assert proof.target_object_specific
    assert proof.grasp_interval_only
    assert not proof.global_acm_modified
    assert not proof.continuous_collision_certification
    assert not proof.physical_collision_certification


def test_stage9d_preflight_rejects_another_object() -> None:
    grasp, urdf, srdf_path = _grasp()
    executable = (
        Path(get_package_prefix('ayyo_manipulation_grasp_interaction'))
        / 'lib/ayyo_manipulation_grasp_interaction/stage9d_moveit_preflight'
    )
    document = interaction_preflight_input_document(
        grasp.request,
        grasp.grasp_evidence_id,
        grasp.grasp_evidence_fingerprint,
    )
    document['attached_object']['collision_name'] = 'another::object::collision'
    rejected = _run(executable, srdf_path, urdf, document)
    assert rejected.returncode == 2
    assert 'differs from the Stage 9D primitive' in rejected.stderr
