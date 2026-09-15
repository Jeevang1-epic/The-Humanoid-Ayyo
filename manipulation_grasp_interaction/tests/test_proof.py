from __future__ import annotations

from dataclasses import replace
import json

import pytest

from ayyo_manipulation_grasp_interaction import (
    GraspInteractionSerializationError,
    RAW_INTERACTION_PREFLIGHT_SCHEMA_ID,
    interaction_preflight_input_document,
    interaction_preflight_input_fingerprint,
    moveit_interaction_proof_from_canonical_json,
)


def _report(proof) -> str:
    return json.dumps(
        {
            "allowed_collision_pair": list(proof.allowed_collision_pair),
            "allowed_touch_links": list(proof.allowed_touch_links),
            "backend_id": proof.backend_id,
            "backend_version": proof.backend_version,
            "continuous_collision_certification": False,
            "global_acm_modified": False,
            "grasp_interval_only": True,
            "input_fingerprint": proof.input_fingerprint,
            "physical_collision_certification": False,
            "samples": [sample.as_dict() for sample in proof.samples],
            "samples_checked": len(proof.samples),
            "schema": {
                "id": RAW_INTERACTION_PREFLIGHT_SCHEMA_ID,
                "version": "1.0.0",
            },
            "target_object_specific": True,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def test_preflight_input_is_exact_and_deterministic(stage9d_bundle) -> None:
    grasp = stage9d_bundle["grasp"]
    document = interaction_preflight_input_document(
        grasp.request,
        grasp.grasp_evidence_id,
        grasp.grasp_evidence_fingerprint,
    )
    assert document["joint_names"] == [
        "left_shoulder_yaw_joint",
        "left_shoulder_pitch_joint",
        "left_elbow_flex_joint",
        "left_wrist_yaw_joint",
    ]
    assert document["attached_object"]["touch_links"] == ["left_hand_link"]
    assert document["attached_object"]["relative_position_xyz"] == [
        0.02,
        0.0,
        -0.17,
    ]
    assert interaction_preflight_input_fingerprint(
        grasp.request,
        grasp.grasp_evidence_id,
        grasp.grasp_evidence_fingerprint,
    ) == interaction_preflight_input_fingerprint(
        grasp.request,
        grasp.grasp_evidence_id,
        grasp.grasp_evidence_fingerprint,
    )


def test_raw_moveit_report_reconstructs_exact_proof(stage9d_bundle) -> None:
    expected = stage9d_bundle["interaction_collision"]
    assert moveit_interaction_proof_from_canonical_json(
        stage9d_bundle["grasp"],
        _report(expected),
    ) == expected


def test_reordered_moveit_samples_fail_closed(stage9d_bundle) -> None:
    document = json.loads(_report(stage9d_bundle["interaction_collision"]))
    document["samples"] = list(reversed(document["samples"]))
    payload = json.dumps(document, separators=(",", ":"), sort_keys=True)
    with pytest.raises(GraspInteractionSerializationError):
        moveit_interaction_proof_from_canonical_json(
            stage9d_bundle["grasp"],
            payload,
        )


def test_report_for_valid_but_unrelated_grasp_fails(stage9d_bundle) -> None:
    grasp = stage9d_bundle["grasp"]
    unrelated_contact = replace(
        grasp.contact,
        observed_at_ns=grasp.contact.observed_at_ns + 1,
        sequence=grasp.contact.sequence + 1,
    )
    unrelated_grasp = replace(grasp, contact=unrelated_contact)
    with pytest.raises(GraspInteractionSerializationError):
        moveit_interaction_proof_from_canonical_json(
            unrelated_grasp,
            _report(stage9d_bundle["interaction_collision"]),
        )


def test_duplicate_report_key_fails_closed(stage9d_bundle) -> None:
    proof = stage9d_bundle["interaction_collision"]
    payload = _report(proof).replace(
        '"backend_id":',
        '"backend_id":"duplicate","backend_id":',
        1,
    )
    with pytest.raises(GraspInteractionSerializationError):
        moveit_interaction_proof_from_canonical_json(
            stage9d_bundle["grasp"],
            payload,
        )
