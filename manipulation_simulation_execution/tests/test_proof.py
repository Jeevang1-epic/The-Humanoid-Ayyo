from __future__ import annotations

import json

import pytest

from ayyo_manipulation_simulation_execution import (
    SimulationExecutionSerializationError,
    moveit_collision_proof_from_canonical_json,
    moveit_preflight_report_from_collision_proof,
)


def _canonical(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def test_moveit_report_round_trip_binds_every_dense_sample(stage9c_bundle) -> None:
    request = stage9c_bundle["execution_request"]
    payload = moveit_preflight_report_from_collision_proof(
        stage9c_bundle["collision_proof"]
    )
    proof = moveit_collision_proof_from_canonical_json(request, payload)
    assert proof == stage9c_bundle["collision_proof"]
    assert len(proof.samples) > len(request.trajectory.points)


@pytest.mark.parametrize(
    "field,value",
    (
        ("input_fingerprint", "stage9c-moveit-preflight-input-sha256-" + "0" * 64),
        ("no_execution_api_used", False),
        ("continuous_collision_certification", True),
        ("samples_checked", 1),
        ("backend_id", "substituted.backend"),
    ),
)
def test_moveit_report_substitution_fails_closed(
    stage9c_bundle,
    field: str,
    value: object,
) -> None:
    request = stage9c_bundle["execution_request"]
    document = json.loads(
        moveit_preflight_report_from_collision_proof(
            stage9c_bundle["collision_proof"]
        )
    )
    document[field] = value
    with pytest.raises(SimulationExecutionSerializationError):
        moveit_collision_proof_from_canonical_json(request, _canonical(document))


def test_moveit_report_rejects_reordered_or_omitted_sample(stage9c_bundle) -> None:
    request = stage9c_bundle["execution_request"]
    document = json.loads(
        moveit_preflight_report_from_collision_proof(
            stage9c_bundle["collision_proof"]
        )
    )
    document["samples"][1], document["samples"][2] = (
        document["samples"][2],
        document["samples"][1],
    )
    with pytest.raises(SimulationExecutionSerializationError):
        moveit_collision_proof_from_canonical_json(request, _canonical(document))

    document = json.loads(
        moveit_preflight_report_from_collision_proof(
            stage9c_bundle["collision_proof"]
        )
    )
    document["samples"].pop()
    document["samples_checked"] -= 1
    with pytest.raises(SimulationExecutionSerializationError):
        moveit_collision_proof_from_canonical_json(request, _canonical(document))


def test_collision_observation_is_preserved_as_rejection_evidence(stage9c_bundle) -> None:
    request = stage9c_bundle["execution_request"]
    document = json.loads(
        moveit_preflight_report_from_collision_proof(
            stage9c_bundle["collision_proof"]
        )
    )
    document["samples"][3]["environment_collision_free"] = False
    proof = moveit_collision_proof_from_canonical_json(request, _canonical(document))
    assert proof.collision_free is False
