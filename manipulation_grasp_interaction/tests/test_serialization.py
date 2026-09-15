from __future__ import annotations

import json
from hashlib import sha256

import pytest

from ayyo_manipulation_grasp_interaction import (
    GraspInteractionSerializationError,
    canonical_grasp_interaction_artifact_json,
    grasp_interaction_artifact_from_canonical_json,
)


def _context(bundle):
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
        "end_effector_contract",
        "object_contract",
        "request",
        "initial_end_effector",
        "detached",
        "contact",
        "pregrasp",
        "grasp",
        "interaction_collision",
        "hold",
        "release",
        "result",
    ),
)
def test_canonical_round_trip_is_exact(stage9d_bundle, name: str) -> None:
    artifact = stage9d_bundle[name]
    encoded = canonical_grasp_interaction_artifact_json(artifact)
    reconstructed = grasp_interaction_artifact_from_canonical_json(
        encoded,
        **_context(stage9d_bundle),
    )
    assert reconstructed == artifact
    assert canonical_grasp_interaction_artifact_json(reconstructed) == encoded


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
def test_malformed_json_is_typed(payload: str) -> None:
    with pytest.raises(GraspInteractionSerializationError):
        grasp_interaction_artifact_from_canonical_json(payload)


def test_noncanonical_json_is_rejected(stage9d_bundle) -> None:
    payload = json.dumps(stage9d_bundle["contact"].as_dict(), indent=2)
    with pytest.raises(GraspInteractionSerializationError):
        grasp_interaction_artifact_from_canonical_json(payload)


def test_outer_rehash_cannot_hide_nested_stage9c_tampering(stage9d_bundle) -> None:
    document = stage9d_bundle["result"].as_dict()
    nested = document["release"]["hold"]["stage9c_result"]
    nested["observation"]["controller_error_code"] = 7
    payload = json.dumps(document, separators=(",", ":"), sort_keys=True)
    with pytest.raises(GraspInteractionSerializationError):
        grasp_interaction_artifact_from_canonical_json(
            payload,
            **_context(stage9d_bundle),
        )


def test_recomputed_outer_identity_cannot_hide_nested_tampering(stage9d_bundle) -> None:
    document = stage9d_bundle["result"].as_dict()
    nested = document["release"]["hold"]["stage9c_result"]
    nested["observation"]["controller_error_code"] = 7
    semantic = {
        key: value
        for key, value in document.items()
        if key not in {"interaction_result_id", "interaction_result_fingerprint"}
    }
    encoded_semantic = json.dumps(
        semantic,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = sha256(encoded_semantic.encode("utf-8")).hexdigest()
    document["interaction_result_id"] = f"stage9d-result-sha256-{digest}"
    document["interaction_result_fingerprint"] = (
        f"stage9d-result-content-sha256-{digest}"
    )
    payload = json.dumps(document, separators=(",", ":"), sort_keys=True)
    with pytest.raises(GraspInteractionSerializationError):
        grasp_interaction_artifact_from_canonical_json(
            payload,
            **_context(stage9d_bundle),
        )


def test_wrong_authoritative_stage9c_context_is_rejected(stage9d_bundle) -> None:
    payload = canonical_grasp_interaction_artifact_json(stage9d_bundle["result"])
    context = _context(stage9d_bundle)
    context["source_safety_kernel"] = None
    with pytest.raises(GraspInteractionSerializationError):
        grasp_interaction_artifact_from_canonical_json(payload, **context)


def test_unexpected_field_is_rejected(stage9d_bundle) -> None:
    document = stage9d_bundle["object_contract"].as_dict()
    document["arbitrary_target"] = "other"
    payload = json.dumps(document, separators=(",", ":"), sort_keys=True)
    with pytest.raises(GraspInteractionSerializationError):
        grasp_interaction_artifact_from_canonical_json(payload)


def test_serialized_resource_limit_is_rejected() -> None:
    payload = '{"oversized":"' + ('x' * (16 * 1024 * 1024)) + '"}'
    with pytest.raises(GraspInteractionSerializationError):
        grasp_interaction_artifact_from_canonical_json(payload)


def test_semantic_contact_order_is_canonical(stage9d_bundle) -> None:
    contact = stage9d_bundle["contact"]
    pair = contact.collision_pairs[0]
    from dataclasses import replace

    reordered = replace(contact, collision_pairs=((pair[1], pair[0]),))
    assert reordered == contact
