from __future__ import annotations

import json

import pytest

from ayyo_manipulation_simulation_execution import (
    SimulationExecutionSerializationError,
    canonical_simulation_execution_artifact_json,
    simulation_execution_artifact_from_canonical_json,
)


def _context(bundle: dict[str, object]) -> dict[str, object]:
    return {
        "source_proposal": bundle["proposal"],
        "source_safety_decision": bundle["safety_decision"],
        "source_safety_kernel": bundle["kernel"],
        "source_skill_binding": bundle["binding"],
        "source_skill_manager": bundle["manager"],
    }


@pytest.mark.parametrize(
    "name",
    (
        "execution_request",
        "collision_proof",
        "state",
        "controller_state",
        "initial_whole_body_state",
        "final_whole_body_state",
        "stability_observation",
        "preflight",
        "execution_goal",
        "observation",
        "result",
    ),
)
def test_canonical_round_trip_is_exact(stage9c_bundle, name: str) -> None:
    artifact = stage9c_bundle[name]
    encoded = canonical_simulation_execution_artifact_json(artifact)
    reconstructed = simulation_execution_artifact_from_canonical_json(
        encoded,
        **_context(stage9c_bundle),
    )
    assert reconstructed == artifact
    assert canonical_simulation_execution_artifact_json(reconstructed) == encoded


@pytest.mark.parametrize(
    "payload",
    (
        "",
        "[]",
        '{"schema":{"id":"unknown","version":"1.0.0"}}',
        '{"duplicate":1,"duplicate":2}',
        '{"nonfinite":NaN}',
        "{",
    ),
)
def test_malformed_json_fails_with_typed_error(payload: str) -> None:
    with pytest.raises(SimulationExecutionSerializationError):
        simulation_execution_artifact_from_canonical_json(payload)


def test_noncanonical_json_is_rejected(stage9c_bundle) -> None:
    document = stage9c_bundle["controller_state"].as_dict()
    noncanonical = json.dumps(document, indent=2, sort_keys=False)
    with pytest.raises(SimulationExecutionSerializationError):
        simulation_execution_artifact_from_canonical_json(noncanonical)


def test_stale_nested_stage9b_identity_is_rejected(stage9c_bundle) -> None:
    encoded = canonical_simulation_execution_artifact_json(
        stage9c_bundle["execution_request"]
    )
    document = json.loads(encoded)
    reference = document["stage9b_handoff"]["skill_handoff_reference"]
    reference["skill_fingerprint"] = "skill:sha256:" + "0" * 64
    corrupted = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    with pytest.raises(SimulationExecutionSerializationError):
        simulation_execution_artifact_from_canonical_json(
            corrupted,
            **_context(stage9c_bundle),
        )


def test_authoritative_context_substitution_is_rejected(stage9c_bundle) -> None:
    encoded = canonical_simulation_execution_artifact_json(stage9c_bundle["result"])
    context = _context(stage9c_bundle)
    context["source_safety_kernel"] = None
    with pytest.raises(SimulationExecutionSerializationError):
        simulation_execution_artifact_from_canonical_json(encoded, **context)


def test_mutated_outer_identity_is_rejected(stage9c_bundle) -> None:
    encoded = canonical_simulation_execution_artifact_json(stage9c_bundle["result"])
    document = json.loads(encoded)
    document["execution_result_id"] = (
        "stage9c-execution-result-sha256-" + "0" * 64
    )
    corrupted = json.dumps(document, separators=(",", ":"), sort_keys=True)
    with pytest.raises(SimulationExecutionSerializationError):
        simulation_execution_artifact_from_canonical_json(
            corrupted,
            **_context(stage9c_bundle),
        )
