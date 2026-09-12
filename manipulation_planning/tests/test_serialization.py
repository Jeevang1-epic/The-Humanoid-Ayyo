from __future__ import annotations

from copy import deepcopy
import json

import pytest

from ayyo_manipulation_planning import (
    PlanningSerializationError,
    canonical_manipulation_planning_artifact_json,
    evaluate_manipulation_plan,
    manipulation_planning_artifact_from_canonical_json,
)
from ayyo_manipulation_planning.canonical import canonical_json, content_identity


def _rehash(document, prefix, id_field, fingerprint_field):
    semantic = {
        key: value for key, value in document.items()
        if key not in {id_field, fingerprint_field}
    }
    identity, fingerprint = content_identity(prefix, semantic)
    document[id_field] = identity
    document[fingerprint_field] = fingerprint


def test_all_public_artifact_types_round_trip(planning_bundle):
    model, catalog, group, start, goal, scene, request, evidence = planning_bundle
    decision = evaluate_manipulation_plan(request, evidence)
    artifacts = (
        model,
        *catalog.chain_joints,
        catalog,
        group,
        start,
        goal,
        request.planner_configuration,
        *scene.collision_objects,
        scene,
        request,
        evidence,
        decision,
    )
    for artifact in artifacts:
        payload = canonical_manipulation_planning_artifact_json(artifact)
        assert manipulation_planning_artifact_from_canonical_json(payload) == artifact
        assert canonical_manipulation_planning_artifact_json(artifact) == payload


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "{}",
        '{"schema":{"id":"unknown","version":"1.0.0"}}',
        '{"a":1,"a":2}',
        '{"value":NaN}',
        "[]",
        "null",
        " true ",
        "{" * 2000,
    ],
)
def test_malformed_and_noncanonical_payloads_fail_closed(payload):
    with pytest.raises(PlanningSerializationError):
        manipulation_planning_artifact_from_canonical_json(payload)


def test_whitespace_and_key_order_variants_are_not_canonical(planning_bundle):
    model, *_ = planning_bundle
    payload = canonical_manipulation_planning_artifact_json(model)
    for variant in (payload + "\n", json.dumps(json.loads(payload), indent=2)):
        with pytest.raises(PlanningSerializationError):
            manipulation_planning_artifact_from_canonical_json(variant)


def test_unknown_field_and_missing_field_fail_closed(planning_bundle):
    model, *_ = planning_bundle
    document = model.as_dict()
    extra = {**document, "unexpected": True}
    missing = {key: value for key, value in document.items() if key != "robot_model_id"}
    for candidate in (extra, missing):
        with pytest.raises(PlanningSerializationError):
            manipulation_planning_artifact_from_canonical_json(canonical_json(candidate))


def test_unknown_schema_version_fails_closed(planning_bundle):
    model, *_ = planning_bundle
    document = deepcopy(model.as_dict())
    document["schema"]["version"] = "2.0.0"
    with pytest.raises(PlanningSerializationError):
        manipulation_planning_artifact_from_canonical_json(canonical_json(document))


def test_outer_rehash_cannot_hide_nested_robot_model_substitution(planning_bundle):
    *_, request, _ = planning_bundle
    document = deepcopy(request.as_dict())
    nested_model = document["robot_model"]
    nested_model["description_fingerprint"] = "description-sha256-" + ("a" * 64)
    _rehash(nested_model, "manipulation-robot-model", "robot_model_id", "robot_model_fingerprint")
    _rehash(document, "manipulation-planning-request", "request_id", "request_fingerprint")

    with pytest.raises(PlanningSerializationError):
        manipulation_planning_artifact_from_canonical_json(canonical_json(document))


def test_recomputed_evidence_identity_cannot_hide_request_substitution(planning_bundle):
    *_, evidence = planning_bundle
    document = deepcopy(evidence.as_dict())
    document["request"]["request_id"] = "request-sha256-" + ("b" * 64)
    _rehash(document, "manipulation-plan-evidence", "plan_evidence_id", "plan_evidence_fingerprint")

    with pytest.raises(PlanningSerializationError):
        manipulation_planning_artifact_from_canonical_json(canonical_json(document))


def test_recomputed_decision_identity_cannot_hide_cross_object_request_substitution(planning_bundle):
    *_, request, evidence = planning_bundle
    decision = evaluate_manipulation_plan(request, evidence)
    document = deepcopy(decision.as_dict())
    document["request"]["request_fingerprint"] = "request-content-sha256-" + ("c" * 64)
    _rehash(document, "manipulation-planning-decision", "decision_id", "decision_fingerprint")

    with pytest.raises(PlanningSerializationError):
        manipulation_planning_artifact_from_canonical_json(canonical_json(document))


def test_pathological_resource_payload_is_rejected():
    payload = "{" + ('\"x\":' + ('[' * 40000) + "0" + (']' * 40000)) + "}"
    with pytest.raises(PlanningSerializationError):
        manipulation_planning_artifact_from_canonical_json(payload)
