import json

import pytest

from ayyo_software_showcase import (
    MAX_SERIALIZED_REPORT_BYTES,
    SHOWCASE_SCHEMA_VERSION,
    ShowcaseIntegrityError,
    ShowcaseManifest,
    build_showcase_manifest,
    canonical_showcase_artifact_json,
    generate_showcase_report,
    showcase_artifact_from_canonical_json,
)


def canonical(document):
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@pytest.mark.parametrize(
    "artifact",
    [build_showcase_manifest(), generate_showcase_report()],
)
def test_manifest_and_report_round_trip_as_strict_text_and_bytes(artifact):
    encoded = canonical_showcase_artifact_json(artifact)

    assert showcase_artifact_from_canonical_json(encoded) == artifact
    assert showcase_artifact_from_canonical_json(encoded.encode("utf-8")) == artifact
    assert canonical_showcase_artifact_json(
        showcase_artifact_from_canonical_json(encoded)
    ) == encoded


def test_canonical_report_output_is_byte_deterministic_and_compact():
    first = canonical_showcase_artifact_json(generate_showcase_report())
    second = canonical_showcase_artifact_json(generate_showcase_report())

    assert first == second
    assert "\n" not in first
    assert ": " not in first


@pytest.mark.parametrize(
    "payload",
    ["", "not-json", "[]", "NaN", b"\xff", None, 1, True],
)
def test_malformed_nonobject_utf8_and_wrong_transport_inputs_fail_closed(payload):
    with pytest.raises(ShowcaseIntegrityError):
        showcase_artifact_from_canonical_json(payload)


def test_duplicate_json_key_is_rejected():
    encoded = canonical_showcase_artifact_json(build_showcase_manifest())
    duplicated = encoded.replace('"title":', '"title":"duplicate","title":', 1)

    with pytest.raises(ShowcaseIntegrityError, match="duplicate key"):
        showcase_artifact_from_canonical_json(duplicated)


def test_noncanonical_whitespace_and_evidence_reordering_are_rejected():
    document = build_showcase_manifest().as_dict()
    with pytest.raises(ShowcaseIntegrityError, match="not canonical"):
        showcase_artifact_from_canonical_json(json.dumps(document, indent=2))

    document["evidence"].reverse()
    with pytest.raises(ShowcaseIntegrityError, match="ordering"):
        showcase_artifact_from_canonical_json(canonical(document))


@pytest.mark.parametrize("mutation", ["unknown", "missing", "schema-id", "schema-version"])
def test_unknown_missing_and_unsupported_schema_fields_are_rejected(mutation):
    document = build_showcase_manifest().as_dict()
    if mutation == "unknown":
        document["unexpected"] = "value"
    elif mutation == "missing":
        del document["summary"]
    elif mutation == "schema-id":
        document["schema"]["id"] = "ayyo.software-showcase.unknown.v1"
    else:
        document["schema"]["version"] = "2.0.0"

    with pytest.raises(ShowcaseIntegrityError):
        showcase_artifact_from_canonical_json(canonical(document))


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("manifest", "capabilities", 0, "classifications", 0), "physically_validated"),
        (("manifest", "capabilities", 12, "capability_id"), "policy-active"),
        (("manifest", "evidence", 0, "kind"), "runtime_execution"),
        (
            ("manifest", "evidence", 0, "provenance", "source_ref"),
            "invented.source.v1",
        ),
    ],
)
def test_nested_claim_and_evidence_tampering_is_rejected(path, replacement):
    document = generate_showcase_report().as_dict()
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(ShowcaseIntegrityError):
        showcase_artifact_from_canonical_json(canonical(document))


def test_recomputed_structurally_valid_non_catalog_manifest_is_rejected():
    source = build_showcase_manifest()
    altered = ShowcaseManifest(
        title=source.title,
        summary="A structurally valid but unreviewed replacement summary.",
        capabilities=source.capabilities,
        evidence=source.evidence,
    )

    with pytest.raises(ShowcaseIntegrityError, match="live-catalog"):
        showcase_artifact_from_canonical_json(canonical(altered.as_dict()))


def test_oversized_and_pathological_bounded_inputs_use_typed_failure():
    oversized = b"{" + b" " * MAX_SERIALIZED_REPORT_BYTES + b"}"
    pathological = (
        chr(0xD800),
        '{"schema":' + "1" * 5_000 + "}",
        "[" * 1_200 + "0" + "]" * 1_200,
    )

    with pytest.raises(ShowcaseIntegrityError, match="largest v1"):
        showcase_artifact_from_canonical_json(oversized)
    for payload in pathological:
        with pytest.raises(ShowcaseIntegrityError):
            showcase_artifact_from_canonical_json(payload)


def test_serializer_rejects_unrecognized_and_in_memory_tampered_artifacts():
    report = generate_showcase_report()
    object.__setattr__(report, "report_id", "tampered")

    with pytest.raises(ShowcaseIntegrityError):
        canonical_showcase_artifact_json(report)
    with pytest.raises(ShowcaseIntegrityError):
        canonical_showcase_artifact_json(object())
