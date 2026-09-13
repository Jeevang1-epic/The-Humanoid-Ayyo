from __future__ import annotations

import copy
import json

import pytest

from ayyo_safety import HazardClass
from ayyo_manipulation_trajectory import (
    ExecutionHandoffEligibilityDecision,
    TrajectorySafetyEligibilityResult,
    TrajectorySerializationError,
    canonical_manipulation_trajectory_artifact_json,
    manipulation_trajectory_artifact_from_canonical_json,
)
from ayyo_manipulation_trajectory.canonical import (
    MAX_CANONICAL_JSON_NODES,
    MAX_SERIALIZED_ARTIFACT_BYTES,
    canonical_json,
    content_identity,
)


def _artifacts(bundle) -> tuple[object, ...]:
    return (
        bundle["timing"],
        bundle["trajectory_request"],
        bundle["trajectory"].points[0],
        bundle["trajectory"],
        bundle["trajectory_evidence"],
        bundle["safety_result"].safety_reference,
        bundle["safety_result"],
        bundle["handoff"].skill_handoff_reference,
        bundle["handoff"],
    )


def _reconstruction_kwargs(artifact, bundle) -> dict[str, object]:
    if type(artifact) is TrajectorySafetyEligibilityResult:
        return {
            "source_proposal": bundle["proposal"],
            "source_safety_decision": bundle["safety_decision"],
            "source_safety_kernel": bundle["kernel"],
        }
    if type(artifact) is ExecutionHandoffEligibilityDecision:
        return {
            "source_proposal": bundle["proposal"],
            "source_safety_decision": bundle["safety_decision"],
            "source_safety_kernel": bundle["kernel"],
            "source_skill_binding": bundle["binding"],
            "source_skill_manager": bundle["manager"],
        }
    return {}


@pytest.mark.parametrize("index", range(9))
def test_every_artifact_round_trips_to_identical_canonical_bytes(
    stage9b_bundle,
    index: int,
) -> None:
    artifact = _artifacts(stage9b_bundle)[index]
    payload = canonical_manipulation_trajectory_artifact_json(artifact)
    rebuilt = manipulation_trajectory_artifact_from_canonical_json(
        payload,
        **_reconstruction_kwargs(artifact, stage9b_bundle),
    )
    assert rebuilt == artifact
    assert canonical_manipulation_trajectory_artifact_json(rebuilt) == payload


@pytest.mark.parametrize("key", ("safety_result", "handoff"))
def test_positive_decision_reconstruction_requires_authoritative_context(
    stage9b_bundle,
    key: str,
) -> None:
    payload = canonical_manipulation_trajectory_artifact_json(stage9b_bundle[key])
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(payload)


def test_serializer_verifies_integrity_before_publication(stage9b_bundle) -> None:
    artifact = copy.deepcopy(stage9b_bundle["trajectory"])
    object.__setattr__(artifact, "trajectory_id", "trajectory-sha256-" + "0" * 64)
    with pytest.raises(TrajectorySerializationError):
        canonical_manipulation_trajectory_artifact_json(artifact)


def test_serializer_normalizes_nested_upstream_assertion(stage9b_bundle) -> None:
    result = stage9b_bundle["safety_result"]
    object.__setattr__(
        result.source_proposal.proposed_plan.steps[0],
        "_parameters",
        [],
    )
    with pytest.raises(TrajectorySerializationError):
        canonical_manipulation_trajectory_artifact_json(result)


def test_reconstruction_normalizes_malformed_authoritative_context(
    stage9b_bundle,
) -> None:
    result = stage9b_bundle["safety_result"]
    payload = canonical_manipulation_trajectory_artifact_json(result)
    object.__setattr__(
        result.source_proposal.proposed_plan.steps[0],
        "_parameters",
        [],
    )
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(
            payload,
            source_proposal=result.source_proposal,
            source_safety_decision=result.source_safety_decision,
            source_safety_kernel=result.source_safety_kernel,
        )


def test_reconstruction_rejects_inconsistent_safety_policy_context(
    stage9b_bundle,
) -> None:
    result = stage9b_bundle["safety_result"]
    payload = canonical_manipulation_trajectory_artifact_json(result)
    object.__setattr__(
        result.source_safety_kernel.policy.capability_rules[0],
        "hazard_class",
        HazardClass.PHYSICAL_MOVEMENT,
    )

    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(
            payload,
            source_proposal=result.source_proposal,
            source_safety_decision=result.source_safety_decision,
            source_safety_kernel=result.source_safety_kernel,
        )


def test_duplicate_key_fails_closed(stage9b_bundle) -> None:
    payload = canonical_manipulation_trajectory_artifact_json(stage9b_bundle["timing"])
    schema = json.dumps(stage9b_bundle["timing"].as_dict()["schema"], separators=(",", ":"), sort_keys=True)
    duplicate = payload[:-1] + ',"schema":' + schema + "}"
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(duplicate)


@pytest.mark.parametrize("mutation", ("unknown", "missing", "schema", "version", "identity"))
def test_closed_schema_and_stale_identity_fail(stage9b_bundle, mutation: str) -> None:
    document = stage9b_bundle["timing"].as_dict()
    if mutation == "unknown":
        document["unexpected"] = True
    elif mutation == "missing":
        document.pop("maximum_points")
    elif mutation == "schema":
        document["schema"]["id"] = "unknown.schema.v1"
    elif mutation == "version":
        document["schema"]["version"] = "2.0.0"
    else:
        document["timing_configuration_id"] = "trajectory-timing-configuration-sha256-" + "0" * 64
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(canonical_json(document))


@pytest.mark.parametrize("value", ("NaN", "Infinity", "-Infinity"))
def test_nonfinite_json_tokens_fail(value: str) -> None:
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(
            '{"schema":{"id":"x","version":"1.0.0"},"value":' + value + "}"
        )


def test_negative_zero_is_not_accepted_canonical_json(stage9b_bundle) -> None:
    document = stage9b_bundle["timing"].as_dict()
    document["velocity_limit_scale"] = -0.0
    payload = json.dumps(document, allow_nan=False, separators=(",", ":"), sort_keys=True)
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(payload)


@pytest.mark.parametrize(
    "payload_mutator",
    (
        lambda payload: " " + payload,
        lambda payload: payload + "\n",
        lambda payload: json.dumps(json.loads(payload), indent=2, sort_keys=True),
    ),
)
def test_alternate_json_spellings_are_rejected(stage9b_bundle, payload_mutator) -> None:
    payload = canonical_manipulation_trajectory_artifact_json(stage9b_bundle["timing"])
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(payload_mutator(payload))


def test_unknown_enum_fails_closed(stage9b_bundle) -> None:
    document = stage9b_bundle["trajectory_evidence"].as_dict()
    document["status"] = "executed"
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(canonical_json(document))


def test_malformed_nested_stage9a_artifact_fails_closed(stage9b_bundle) -> None:
    document = stage9b_bundle["trajectory_request"].as_dict()
    document["stage9a_decision"]["request"]["group"]["joint_names"].reverse()
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(canonical_json(document))


def test_nested_mutation_with_all_outer_rehashes_still_fails(stage9b_bundle) -> None:
    document = stage9b_bundle["trajectory_evidence"].as_dict()
    point = document["trajectory"]["points"][1]
    point["time_from_start"] += 0.01
    point_semantic = {
        key: value
        for key, value in point.items()
        if key not in {"trajectory_point_id", "trajectory_point_fingerprint"}
    }
    point["trajectory_point_id"], point["trajectory_point_fingerprint"] = (
        content_identity("trajectory-point", point_semantic)
    )
    trajectory = document["trajectory"]
    trajectory_semantic = {
        key: value
        for key, value in trajectory.items()
        if key not in {"trajectory_id", "trajectory_fingerprint"}
    }
    trajectory["trajectory_id"], trajectory["trajectory_fingerprint"] = (
        content_identity("deterministic-joint-trajectory", trajectory_semantic)
    )
    evidence_semantic = {
        key: value
        for key, value in document.items()
        if key not in {"trajectory_evidence_id", "trajectory_evidence_fingerprint"}
    }
    document["trajectory_evidence_id"], document["trajectory_evidence_fingerprint"] = (
        content_identity("trajectory-evidence", evidence_semantic)
    )
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(canonical_json(document))


def test_oversized_payload_fails_before_parsing() -> None:
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(
            "x" * (MAX_SERIALIZED_ARTIFACT_BYTES + 1)
        )


def test_excessive_nesting_fails_closed() -> None:
    payload = "[" * 1_200 + "0" + "]" * 1_200
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(payload)


def test_excessive_node_count_fails_closed(stage9b_bundle) -> None:
    document = stage9b_bundle["timing"].as_dict()
    document["unexpected"] = [None] * (MAX_CANONICAL_JSON_NODES + 1)
    payload = json.dumps(document, separators=(",", ":"), sort_keys=True)
    assert len(payload.encode("utf-8")) < MAX_SERIALIZED_ARTIFACT_BYTES
    with pytest.raises(TrajectorySerializationError):
        manipulation_trajectory_artifact_from_canonical_json(payload)


def test_non_string_and_empty_payloads_fail_closed() -> None:
    for payload in (None, b"{}", ""):
        with pytest.raises(TrajectorySerializationError):
            manipulation_trajectory_artifact_from_canonical_json(payload)
