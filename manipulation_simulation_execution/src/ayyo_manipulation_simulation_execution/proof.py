"""Strict adapter for the bounded headless Stage 9C MoveIt report."""

from __future__ import annotations

import json

from ayyo_manipulation_planning import ExecutionDisposition
from ayyo_manipulation_trajectory import PhysicalValidationStatus

from .canonical import MAX_SERIALIZED_ARTIFACT_BYTES, SCHEMA_VERSION, canonical_json
from .errors import (
    SimulationExecutionSerializationError,
    SimulationExecutionValidationError,
)
from .models import (
    STAGE9C_COLLISION_BACKEND_ID,
    STAGE9C_COLLISION_BACKEND_VERSION,
    DenseCollisionSample,
    SimulationCollisionProof,
    SimulationExecutionRequest,
    expected_dense_samples,
    preflight_input_fingerprint,
    verify_execution_request,
)


RAW_MOVEIT_PREFLIGHT_SCHEMA_ID = "ayyo.stage9c.moveit-preflight-report.v1"


def _error(detail: str, cause: BaseException | None = None):
    error = SimulationExecutionSerializationError(detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"duplicate key {key!r} is not canonical")
        result[key] = value
    return result


def _mapping(value: object, name: str) -> dict:
    if type(value) is not dict:
        raise _error(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> list:
    if type(value) is not list:
        raise _error(f"{name} must be an array")
    return value


def moveit_preflight_report_from_collision_proof(
    proof: SimulationCollisionProof,
) -> str:
    """Build the exact raw report shape for deterministic adapter tests."""

    return canonical_json(
        {
            "backend_id": proof.backend_id,
            "backend_version": proof.backend_version,
            "continuous_collision_certification": (
                proof.continuous_collision_certification
            ),
            "execution_disposition": proof.execution_disposition.value,
            "input_fingerprint": proof.input_fingerprint,
            "no_execution_api_used": True,
            "physical_validation": proof.physical_validation.value,
            "samples": [sample.as_dict() for sample in proof.samples],
            "samples_checked": len(proof.samples),
            "schema": {
                "id": RAW_MOVEIT_PREFLIGHT_SCHEMA_ID,
                "version": SCHEMA_VERSION,
            },
        }
    )


def moveit_collision_proof_from_canonical_json(
    request: SimulationExecutionRequest,
    payload: str,
) -> SimulationCollisionProof:
    """Bind canonical MoveIt observations to one exact Stage 9C request."""

    if not verify_execution_request(request):
        raise _error("MoveIt preflight request failed recursive verification")
    if type(payload) is not str:
        raise _error("MoveIt preflight report must be text")
    try:
        encoded = payload.encode("utf-8")
    except UnicodeError as error:
        raise _error("MoveIt preflight report must be UTF-8", error)
    if not encoded or len(encoded) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise _error("MoveIt preflight report violates its byte bound")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _error(f"non-finite {value} is forbidden")
            ),
        )
        item = _mapping(document, "MoveIt preflight report")
        if canonical_json(item) != payload:
            raise _error("MoveIt preflight report is not canonical JSON")
        expected_keys = {
            "backend_id",
            "backend_version",
            "continuous_collision_certification",
            "execution_disposition",
            "input_fingerprint",
            "no_execution_api_used",
            "physical_validation",
            "samples",
            "samples_checked",
            "schema",
        }
        if set(item) != expected_keys:
            raise _error("MoveIt preflight fields do not match the closed v1 schema")
        if item["schema"] != {
            "id": RAW_MOVEIT_PREFLIGHT_SCHEMA_ID,
            "version": SCHEMA_VERSION,
        }:
            raise _error("unknown MoveIt preflight schema or version")
        exact = {
            "backend_id": STAGE9C_COLLISION_BACKEND_ID,
            "backend_version": STAGE9C_COLLISION_BACKEND_VERSION,
            "continuous_collision_certification": False,
            "execution_disposition": ExecutionDisposition.NOT_EXECUTED.value,
            "input_fingerprint": preflight_input_fingerprint(request),
            "no_execution_api_used": True,
            "physical_validation": PhysicalValidationStatus.ABSENT.value,
        }
        for field, expected in exact.items():
            if type(item[field]) is not type(expected) or item[field] != expected:
                raise _error(f"MoveIt preflight {field} differs from the exact request")

        planned = expected_dense_samples(request)
        raw_samples = _sequence(item["samples"], "MoveIt samples")
        if (
            type(item["samples_checked"]) is not int
            or item["samples_checked"] != len(planned)
            or len(raw_samples) != len(planned)
        ):
            raise _error("MoveIt report did not check every exact dense sample")
        samples = []
        expected_sample_keys = {
            "environment_collision_free",
            "positions",
            "sample_index",
            "segment_fraction",
            "segment_index",
            "segment_subdivisions",
            "self_collision_free",
            "subdivision_index",
            "within_joint_limits",
        }
        for raw, expected in zip(raw_samples, planned, strict=True):
            mapped = _mapping(raw, "MoveIt sample")
            if set(mapped) != expected_sample_keys:
                raise _error("MoveIt sample fields do not match the closed v1 schema")
            sample = DenseCollisionSample(
                sample_index=mapped["sample_index"],
                segment_index=mapped["segment_index"],
                subdivision_index=mapped["subdivision_index"],
                segment_subdivisions=mapped["segment_subdivisions"],
                segment_fraction=mapped["segment_fraction"],
                positions=tuple(_sequence(mapped["positions"], "sample positions")),
                self_collision_free=mapped["self_collision_free"],
                environment_collision_free=mapped["environment_collision_free"],
                within_joint_limits=mapped["within_joint_limits"],
            )
            if (
                sample.sample_index != expected.sample_index
                or sample.segment_index != expected.segment_index
                or sample.subdivision_index != expected.subdivision_index
                or sample.segment_subdivisions != expected.segment_subdivisions
                or sample.segment_fraction != expected.segment_fraction
                or sample.positions != expected.positions
            ):
                raise _error("MoveIt sample differs from exact controller interpolation")
            samples.append(sample)
        return SimulationCollisionProof(
            execution_request=request,
            input_fingerprint=item["input_fingerprint"],
            backend_id=item["backend_id"],
            backend_version=item["backend_version"],
            samples=tuple(samples),
            continuous_collision_certification=item[
                "continuous_collision_certification"
            ],
            execution_disposition=ExecutionDisposition(
                item["execution_disposition"]
            ),
            physical_validation=PhysicalValidationStatus(
                item["physical_validation"]
            ),
        )
    except SimulationExecutionSerializationError:
        raise
    except (
        ArithmeticError,
        json.JSONDecodeError,
        KeyError,
        SimulationExecutionValidationError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("MoveIt preflight report failed closed during reconstruction", error)
