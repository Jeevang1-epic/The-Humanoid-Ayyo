"""Strict canonical inspect-only serialization for showcase artifacts."""

from __future__ import annotations

import json

from .canonical import MAX_SERIALIZED_REPORT_BYTES, canonical_json
from .catalog import verify_showcase_catalog
from .errors import ShowcaseIntegrityError
from .models import (
    SHOWCASE_MANIFEST_SCHEMA_ID,
    SHOWCASE_REPORT_SCHEMA_ID,
    SHOWCASE_SCHEMA_VERSION,
    ShowcaseCapability,
    ShowcaseCheck,
    ShowcaseCheckOutcome,
    ShowcaseClassification,
    ShowcaseEvidenceKind,
    ShowcaseEvidenceReference,
    ShowcaseManifest,
    ShowcaseNonClaim,
    ShowcaseReport,
)
from .report import verify_showcase_report


ShowcaseArtifact = ShowcaseManifest | ShowcaseReport


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ShowcaseIntegrityError("showcase JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ShowcaseIntegrityError(f"non-finite JSON constant is forbidden: {value}")


def _mapping(value: object, field_name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ShowcaseIntegrityError(f"{field_name} has unknown or missing fields")
    return value


def _sequence(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise ShowcaseIntegrityError(f"{field_name} must be a JSON array")
    return value


def _enum(enum_type: type, value: object, field_name: str):
    if type(value) is not str:
        raise ShowcaseIntegrityError(f"{field_name} must use its closed enum")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ShowcaseIntegrityError(
            f"{field_name} uses an unsupported value"
        ) from error


def _schema(root: dict[str, object]) -> tuple[str, str]:
    schema = _mapping(root.get("schema"), "showcase schema", {"id", "version"})
    if type(schema["id"]) is not str or type(schema["version"]) is not str:
        raise ShowcaseIntegrityError("showcase schema identity must be text")
    return schema["id"], schema["version"]


def _evidence(root: object) -> ShowcaseEvidenceReference:
    root = _mapping(
        root,
        "showcase evidence",
        {
            "contract",
            "evidence_fingerprint",
            "evidence_id",
            "kind",
            "provenance",
        },
    )
    contract = _mapping(
        root["contract"], "showcase evidence contract", {"module", "schema", "symbol"}
    )
    schema = contract["schema"]
    if schema is not None:
        schema = _mapping(schema, "showcase evidence schema", {"id", "version"})
    provenance = _mapping(
        root["provenance"], "showcase evidence provenance", {"fingerprint", "source_ref"}
    )
    return ShowcaseEvidenceReference(
        kind=_enum(ShowcaseEvidenceKind, root["kind"], "showcase evidence kind"),
        contract_module=contract["module"],
        contract_symbol=contract["symbol"],
        schema_id=None if schema is None else schema["id"],
        schema_version=None if schema is None else schema["version"],
        provenance_ref=provenance["source_ref"],
        provenance_fingerprint=provenance["fingerprint"],
    )


def _capability(root: object) -> ShowcaseCapability:
    root = _mapping(
        root,
        "showcase capability",
        {
            "capability_fingerprint",
            "capability_id",
            "classifications",
            "does_not_prove",
            "evidence_ids",
            "sequence_index",
            "summary",
            "title",
        },
    )
    return ShowcaseCapability(
        sequence_index=root["sequence_index"],
        capability_id=root["capability_id"],
        title=root["title"],
        summary=root["summary"],
        classifications=tuple(
            _enum(ShowcaseClassification, value, "showcase classification")
            for value in _sequence(root["classifications"], "classifications")
        ),
        evidence_ids=tuple(_sequence(root["evidence_ids"], "evidence_ids")),
        does_not_prove=tuple(
            _enum(ShowcaseNonClaim, value, "showcase non-claim")
            for value in _sequence(root["does_not_prove"], "does_not_prove")
        ),
    )


def _manifest(root: object) -> ShowcaseManifest:
    root = _mapping(
        root,
        "showcase manifest",
        {
            "capabilities",
            "evidence",
            "manifest_fingerprint",
            "manifest_id",
            "schema",
            "summary",
            "title",
        },
    )
    return ShowcaseManifest(
        title=root["title"],
        summary=root["summary"],
        capabilities=tuple(
            _capability(item)
            for item in _sequence(root["capabilities"], "manifest capabilities")
        ),
        evidence=tuple(
            _evidence(item)
            for item in _sequence(root["evidence"], "manifest evidence")
        ),
    )


def _check(root: object) -> ShowcaseCheck:
    root = _mapping(
        root,
        "showcase check",
        {
            "capability_fingerprint",
            "capability_id",
            "check_fingerprint",
            "check_id",
            "evidence_ids",
            "outcome",
        },
    )
    return ShowcaseCheck(
        capability_id=root["capability_id"],
        capability_fingerprint=root["capability_fingerprint"],
        outcome=_enum(ShowcaseCheckOutcome, root["outcome"], "showcase check outcome"),
        evidence_ids=tuple(_sequence(root["evidence_ids"], "check evidence_ids")),
    )


def _report(root: object) -> ShowcaseReport:
    root = _mapping(
        root,
        "showcase report",
        {
            "checks",
            "manifest",
            "report_fingerprint",
            "report_id",
            "schema",
        },
    )
    return ShowcaseReport(
        manifest=_manifest(root["manifest"]),
        checks=tuple(
            _check(item) for item in _sequence(root["checks"], "showcase checks")
        ),
    )


def canonical_showcase_artifact_json(artifact: ShowcaseArtifact) -> str:
    if type(artifact) is ShowcaseManifest:
        verified = verify_showcase_catalog(artifact)
    elif type(artifact) is ShowcaseReport:
        verified = verify_showcase_report(artifact)
    else:
        verified = False
    if not verified:
        raise ShowcaseIntegrityError(
            "showcase artifact type or content failed live-catalog verification"
        )
    return canonical_json(artifact.as_dict())


def showcase_artifact_from_canonical_json(payload: str | bytes) -> ShowcaseArtifact:
    try:
        if isinstance(payload, bytes):
            raw = payload
            text = payload.decode("utf-8")
        elif type(payload) is str:
            text = payload
            raw = payload.encode("utf-8")
        else:
            raise ShowcaseIntegrityError("showcase JSON must be text or bytes")
    except UnicodeError as error:
        raise ShowcaseIntegrityError("showcase JSON is not valid UTF-8") from error
    if not raw or len(raw) > MAX_SERIALIZED_REPORT_BYTES:
        raise ShowcaseIntegrityError(
            "showcase JSON is empty or exceeds the largest v1 artifact bound"
        )
    try:
        document = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ShowcaseIntegrityError:
        raise
    except (UnicodeError, ValueError, RecursionError, json.JSONDecodeError) as error:
        raise ShowcaseIntegrityError("showcase JSON is malformed") from error
    try:
        encoded = canonical_json(document).encode("utf-8")
    except (UnicodeError, TypeError, ValueError, RecursionError) as error:
        raise ShowcaseIntegrityError("showcase JSON is not canonical") from error
    if encoded != raw:
        raise ShowcaseIntegrityError("showcase JSON is not canonical")
    if type(document) is not dict:
        raise ShowcaseIntegrityError("showcase JSON root must be an object")
    schema_id, schema_version = _schema(document)
    if schema_version != SHOWCASE_SCHEMA_VERSION:
        raise ShowcaseIntegrityError("showcase schema version is unsupported")
    try:
        if schema_id == SHOWCASE_MANIFEST_SCHEMA_ID:
            artifact = _manifest(document)
        elif schema_id == SHOWCASE_REPORT_SCHEMA_ID:
            artifact = _report(document)
        else:
            raise ShowcaseIntegrityError("showcase schema identity is unsupported")
    except ShowcaseIntegrityError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ShowcaseIntegrityError(
            "showcase JSON content violates its v1 contract"
        ) from error
    if artifact.as_dict() != document:
        raise ShowcaseIntegrityError(
            "showcase artifact identity, ordering, or content was tampered"
        )
    canonical_showcase_artifact_json(artifact)
    return artifact
