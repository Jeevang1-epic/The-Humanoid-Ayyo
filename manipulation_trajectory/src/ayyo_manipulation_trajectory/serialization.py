"""Strict canonical JSON boundary for Stage 9B artifacts."""

from __future__ import annotations

import json
from typing import Callable

from ayyo_manipulation_planning import (
    ExecutionDisposition,
    JointPosition,
    ManipulationPlanningDecision,
    PlanningSerializationError,
    manipulation_planning_artifact_from_canonical_json,
)
from ayyo_executive import ExecutiveDecision
from ayyo_safety import SafetyDecision, SafetyKernel
from ayyo_skill_manager import (
    SkillBindingResult,
    SkillManagerService,
)

from .canonical import (
    JSONValue,
    MAX_SERIALIZED_ARTIFACT_BYTES,
    SCHEMA_VERSION,
    canonical_json,
)
from .errors import (
    TrajectorySerializationError,
    TrajectoryValidationError,
)
from .models import (
    HANDOFF_DECISION_SCHEMA_ID,
    SAFETY_REFERENCE_SCHEMA_ID,
    SAFETY_RESULT_SCHEMA_ID,
    SKILL_HANDOFF_REFERENCE_SCHEMA_ID,
    TIMING_CONFIGURATION_SCHEMA_ID,
    TRAJECTORY_EVIDENCE_SCHEMA_ID,
    TRAJECTORY_POINT_SCHEMA_ID,
    TRAJECTORY_REQUEST_SCHEMA_ID,
    TRAJECTORY_SCHEMA_ID,
    DeterministicJointTrajectory,
    ExecutionHandoffEligibilityDecision,
    HandoffEligibilityReason,
    HandoffEligibilityStatus,
    PhysicalValidationStatus,
    ReviewedHazardClass,
    ReviewedSafetyDisposition,
    RuntimeEndpointState,
    SafetyEligibilityReason,
    SafetyEligibilityReference,
    SafetyEligibilityStatus,
    SkillRuntimeHandoffReference,
    TrajectoryConstructionRequest,
    TrajectoryEvidence,
    TrajectoryEvidenceStatus,
    TrajectoryPoint,
    TrajectorySafetyEligibilityResult,
    TrajectoryTimingConfiguration,
    verify_handoff_decision,
    verify_safety_reference,
    verify_safety_result,
    verify_skill_handoff_reference,
    verify_timing_configuration,
    verify_trajectory,
    verify_trajectory_evidence,
    verify_trajectory_point,
    verify_trajectory_request,
)


TrajectoryArtifact = (
    TrajectoryTimingConfiguration
    | TrajectoryConstructionRequest
    | TrajectoryPoint
    | DeterministicJointTrajectory
    | TrajectoryEvidence
    | SafetyEligibilityReference
    | TrajectorySafetyEligibilityResult
    | SkillRuntimeHandoffReference
    | ExecutionHandoffEligibilityDecision
)


def _error(
    detail: str,
    cause: BaseException | None = None,
) -> TrajectorySerializationError:
    error = TrajectorySerializationError(detail)
    if cause is not None:
        error.__cause__ = cause
    return error


def _object(pairs: list[tuple[str, JSONValue]]) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"duplicate key {key!r} is not canonical")
        result[key] = value
    return result


def _mapping(value: object, name: str) -> dict[str, JSONValue]:
    if type(value) is not dict:
        raise _error(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> list[JSONValue]:
    if type(value) is not list:
        raise _error(f"{name} must be an array")
    return value


def _exact_keys(value: dict[str, JSONValue], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise _error(f"{name} fields do not match the closed v1 schema")


def _schema(value: dict[str, JSONValue], schema_id: str) -> None:
    schema = _mapping(value.get("schema"), "schema")
    _exact_keys(schema, {"id", "version"}, "schema")
    if schema != {"id": schema_id, "version": SCHEMA_VERSION}:
        raise _error("unknown trajectory schema or version")


def _verify_recomputed(
    document: dict[str, JSONValue],
    artifact: TrajectoryArtifact,
) -> TrajectoryArtifact:
    if artifact.as_dict() != document:
        raise _error("serialized identities or content do not match recomputed evidence")
    return artifact


def _stage9a_decision(value: object) -> ManipulationPlanningDecision:
    item = _mapping(value, "stage9a_decision")
    try:
        artifact = manipulation_planning_artifact_from_canonical_json(
            canonical_json(item)
        )
    except (
        PlanningSerializationError,
        TrajectoryValidationError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("nested Stage 9A decision failed canonical reconstruction", error)
    if type(artifact) is not ManipulationPlanningDecision:
        raise _error("nested Stage 9A artifact is not a planning decision")
    return artifact


def _positions(value: object) -> tuple[JointPosition, ...]:
    result = []
    for raw in _sequence(value, "positions"):
        item = _mapping(raw, "joint_position")
        _exact_keys(item, {"joint_name", "position"}, "joint_position")
        result.append(
            JointPosition(joint_name=item["joint_name"], position=item["position"])
        )
    return tuple(result)


def _timing(value: object) -> TrajectoryTimingConfiguration:
    item = _mapping(value, "timing_configuration")
    _exact_keys(
        item,
        {
            "maximum_duration",
            "maximum_points",
            "method_id",
            "minimum_segment_duration",
            "schema",
            "timing_configuration_fingerprint",
            "timing_configuration_id",
            "velocity_limit_scale",
        },
        "timing_configuration",
    )
    _schema(item, TIMING_CONFIGURATION_SCHEMA_ID)
    return _verify_recomputed(
        item,
        TrajectoryTimingConfiguration(
            velocity_limit_scale=item["velocity_limit_scale"],
            minimum_segment_duration=item["minimum_segment_duration"],
            maximum_duration=item["maximum_duration"],
            maximum_points=item["maximum_points"],
        ),
    )


def _request(value: object) -> TrajectoryConstructionRequest:
    item = _mapping(value, "trajectory_request")
    _exact_keys(
        item,
        {
            "candidate_path_fingerprint",
            "candidate_path_id",
            "collision_model_fingerprint",
            "collision_model_id",
            "collision_proof_fingerprint",
            "collision_proof_id",
            "execution_disposition",
            "group_fingerprint",
            "group_id",
            "joint_catalog_fingerprint",
            "joint_catalog_id",
            "physical_validation",
            "robot_model_fingerprint",
            "robot_model_id",
            "schema",
            "stage9a_decision",
            "stage9a_decision_fingerprint",
            "stage9a_decision_id",
            "stage9a_evidence_fingerprint",
            "stage9a_evidence_id",
            "stage9a_request_fingerprint",
            "stage9a_request_id",
            "timing_configuration",
            "trajectory_request_fingerprint",
            "trajectory_request_id",
        },
        "trajectory_request",
    )
    _schema(item, TRAJECTORY_REQUEST_SCHEMA_ID)
    return _verify_recomputed(
        item,
        TrajectoryConstructionRequest(
            stage9a_decision=_stage9a_decision(item["stage9a_decision"]),
            timing_configuration=_timing(item["timing_configuration"]),
        ),
    )


def _point(value: object) -> TrajectoryPoint:
    item = _mapping(value, "trajectory_point")
    _exact_keys(
        item,
        {
            "group_fingerprint",
            "group_id",
            "joint_catalog_fingerprint",
            "joint_catalog_id",
            "joint_names",
            "point_index",
            "positions",
            "schema",
            "time_from_start",
            "trajectory_point_fingerprint",
            "trajectory_point_id",
        },
        "trajectory_point",
    )
    _schema(item, TRAJECTORY_POINT_SCHEMA_ID)
    return _verify_recomputed(
        item,
        TrajectoryPoint(
            point_index=item["point_index"],
            group_id=item["group_id"],
            group_fingerprint=item["group_fingerprint"],
            joint_catalog_id=item["joint_catalog_id"],
            joint_catalog_fingerprint=item["joint_catalog_fingerprint"],
            joint_names=tuple(_sequence(item["joint_names"], "joint_names")),
            positions=_positions(item["positions"]),
            time_from_start=item["time_from_start"],
        ),
    )


def _trajectory(value: object) -> DeterministicJointTrajectory:
    item = _mapping(value, "trajectory")
    _exact_keys(
        item,
        {
            "candidate_path_fingerprint",
            "candidate_path_id",
            "duration",
            "execution_disposition",
            "joint_names",
            "physical_validation",
            "point_count",
            "points",
            "request",
            "schema",
            "timing_configuration_fingerprint",
            "timing_configuration_id",
            "trajectory_fingerprint",
            "trajectory_id",
            "trajectory_request_fingerprint",
            "trajectory_request_id",
        },
        "trajectory",
    )
    _schema(item, TRAJECTORY_SCHEMA_ID)
    return _verify_recomputed(
        item,
        DeterministicJointTrajectory(
            request=_request(item["request"]),
            points=tuple(
                _point(raw) for raw in _sequence(item["points"], "points")
            ),
        ),
    )


def _evidence(value: object) -> TrajectoryEvidence:
    item = _mapping(value, "trajectory_evidence")
    _exact_keys(
        item,
        {
            "execution_disposition",
            "joint_limits_checked",
            "physical_validation",
            "request",
            "schema",
            "status",
            "timing_constraints_checked",
            "trajectory",
            "trajectory_evidence_fingerprint",
            "trajectory_evidence_id",
        },
        "trajectory_evidence",
    )
    _schema(item, TRAJECTORY_EVIDENCE_SCHEMA_ID)
    return _verify_recomputed(
        item,
        TrajectoryEvidence(
            request=_request(item["request"]),
            trajectory=_trajectory(item["trajectory"]),
            status=TrajectoryEvidenceStatus(item["status"]),
            joint_limits_checked=item["joint_limits_checked"],
            timing_constraints_checked=item["timing_constraints_checked"],
            execution_disposition=ExecutionDisposition(item["execution_disposition"]),
            physical_validation=PhysicalValidationStatus(item["physical_validation"]),
        ),
    )


def _safety_reference(value: object) -> SafetyEligibilityReference:
    item = _mapping(value, "safety_reference")
    _exact_keys(
        item,
        {
            "capability_id",
            "hazard_class",
            "safety_disposition",
            "safety_reference_fingerprint",
            "safety_reference_id",
            "schema",
            "source_executive_decision_fingerprint",
            "source_executive_decision_id",
            "source_policy_fingerprint",
            "source_policy_version",
            "source_proposal_fingerprint",
            "source_safety_decision_fingerprint",
            "source_safety_decision_id",
            "source_step_id",
            "trajectory_binding_fingerprint",
        },
        "safety_reference",
    )
    _schema(item, SAFETY_REFERENCE_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SafetyEligibilityReference(
            source_executive_decision_id=item["source_executive_decision_id"],
            source_executive_decision_fingerprint=item[
                "source_executive_decision_fingerprint"
            ],
            source_safety_decision_id=item["source_safety_decision_id"],
            source_safety_decision_fingerprint=item[
                "source_safety_decision_fingerprint"
            ],
            source_proposal_fingerprint=item["source_proposal_fingerprint"],
            source_policy_version=item["source_policy_version"],
            source_policy_fingerprint=item["source_policy_fingerprint"],
            source_step_id=item["source_step_id"],
            capability_id=item["capability_id"],
            safety_disposition=ReviewedSafetyDisposition(
                item["safety_disposition"]
            ),
            hazard_class=ReviewedHazardClass(item["hazard_class"]),
            trajectory_binding_fingerprint=item["trajectory_binding_fingerprint"],
        ),
    )


def _safety_result(
    value: object,
    *,
    source_proposal: ExecutiveDecision | None = None,
    source_safety_decision: SafetyDecision | None = None,
    source_safety_kernel: SafetyKernel | None = None,
) -> TrajectorySafetyEligibilityResult:
    item = _mapping(value, "safety_result")
    _exact_keys(
        item,
        {
            "execution_disposition",
            "physical_validation",
            "reasons",
            "safety_reference",
            "safety_result_fingerprint",
            "safety_result_id",
            "schema",
            "status",
            "trajectory_evidence",
        },
        "safety_result",
    )
    _schema(item, SAFETY_RESULT_SCHEMA_ID)
    return _verify_recomputed(
        item,
        TrajectorySafetyEligibilityResult(
            trajectory_evidence=_evidence(item["trajectory_evidence"]),
            safety_reference=_safety_reference(item["safety_reference"]),
            status=SafetyEligibilityStatus(item["status"]),
            reasons=tuple(
                SafetyEligibilityReason(raw)
                for raw in _sequence(item["reasons"], "reasons")
            ),
            source_proposal=source_proposal,
            source_safety_decision=source_safety_decision,
            source_safety_kernel=source_safety_kernel,
            execution_disposition=ExecutionDisposition(item["execution_disposition"]),
            physical_validation=PhysicalValidationStatus(item["physical_validation"]),
        ),
    )


def _skill_reference(value: object) -> SkillRuntimeHandoffReference:
    item = _mapping(value, "skill_handoff_reference")
    _exact_keys(
        item,
        {
            "backend_id",
            "capability_id",
            "invocation_fingerprint",
            "invocation_id",
            "schema",
            "selection_fingerprint",
            "skill_fingerprint",
            "skill_handoff_reference_fingerprint",
            "skill_handoff_reference_id",
            "skill_id",
            "skill_version",
            "source_safety_decision_id",
            "source_safety_decision_fingerprint",
            "source_safety_result_fingerprint",
            "source_safety_result_id",
            "source_step_id",
            "trajectory_binding_fingerprint",
        },
        "skill_handoff_reference",
    )
    _schema(item, SKILL_HANDOFF_REFERENCE_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SkillRuntimeHandoffReference(
            source_safety_result_id=item["source_safety_result_id"],
            source_safety_result_fingerprint=item["source_safety_result_fingerprint"],
            source_safety_decision_id=item["source_safety_decision_id"],
            source_safety_decision_fingerprint=item[
                "source_safety_decision_fingerprint"
            ],
            source_step_id=item["source_step_id"],
            capability_id=item["capability_id"],
            skill_id=item["skill_id"],
            skill_version=item["skill_version"],
            skill_fingerprint=item["skill_fingerprint"],
            selection_fingerprint=item["selection_fingerprint"],
            invocation_id=item["invocation_id"],
            invocation_fingerprint=item["invocation_fingerprint"],
            backend_id=item["backend_id"],
            trajectory_binding_fingerprint=item["trajectory_binding_fingerprint"],
        ),
    )


def _handoff(
    value: object,
    *,
    source_proposal: ExecutiveDecision | None = None,
    source_safety_decision: SafetyDecision | None = None,
    source_safety_kernel: SafetyKernel | None = None,
    source_skill_binding: SkillBindingResult | None = None,
    source_skill_manager: SkillManagerService | None = None,
) -> ExecutionHandoffEligibilityDecision:
    item = _mapping(value, "handoff_decision")
    _exact_keys(
        item,
        {
            "execution_disposition",
            "future_runtime_contract_id",
            "handoff_decision_fingerprint",
            "handoff_decision_id",
            "physical_validation",
            "reasons",
            "runtime_endpoint_state",
            "safety_result",
            "schema",
            "skill_handoff_reference",
            "status",
        },
        "handoff_decision",
    )
    _schema(item, HANDOFF_DECISION_SCHEMA_ID)
    raw_reference = item["skill_handoff_reference"]
    return _verify_recomputed(
        item,
        ExecutionHandoffEligibilityDecision(
            safety_result=_safety_result(
                item["safety_result"],
                source_proposal=source_proposal,
                source_safety_decision=source_safety_decision,
                source_safety_kernel=source_safety_kernel,
            ),
            status=HandoffEligibilityStatus(item["status"]),
            reasons=tuple(
                HandoffEligibilityReason(raw)
                for raw in _sequence(item["reasons"], "reasons")
            ),
            skill_handoff_reference=(
                None if raw_reference is None else _skill_reference(raw_reference)
            ),
            source_skill_binding=source_skill_binding,
            source_skill_manager=source_skill_manager,
            runtime_endpoint_state=RuntimeEndpointState(
                item["runtime_endpoint_state"]
            ),
            future_runtime_contract_id=item["future_runtime_contract_id"],
            execution_disposition=ExecutionDisposition(item["execution_disposition"]),
            physical_validation=PhysicalValidationStatus(item["physical_validation"]),
        ),
    )


_PARSERS: dict[str, Callable[[object], TrajectoryArtifact]] = {
    TIMING_CONFIGURATION_SCHEMA_ID: _timing,
    TRAJECTORY_REQUEST_SCHEMA_ID: _request,
    TRAJECTORY_POINT_SCHEMA_ID: _point,
    TRAJECTORY_SCHEMA_ID: _trajectory,
    TRAJECTORY_EVIDENCE_SCHEMA_ID: _evidence,
    SAFETY_REFERENCE_SCHEMA_ID: _safety_reference,
    SAFETY_RESULT_SCHEMA_ID: _safety_result,
    SKILL_HANDOFF_REFERENCE_SCHEMA_ID: _skill_reference,
    HANDOFF_DECISION_SCHEMA_ID: _handoff,
}

_VERIFIERS: dict[type, Callable[[object], bool]] = {
    TrajectoryTimingConfiguration: verify_timing_configuration,
    TrajectoryConstructionRequest: verify_trajectory_request,
    TrajectoryPoint: verify_trajectory_point,
    DeterministicJointTrajectory: verify_trajectory,
    TrajectoryEvidence: verify_trajectory_evidence,
    SafetyEligibilityReference: verify_safety_reference,
    TrajectorySafetyEligibilityResult: verify_safety_result,
    SkillRuntimeHandoffReference: verify_skill_handoff_reference,
    ExecutionHandoffEligibilityDecision: verify_handoff_decision,
}


def canonical_manipulation_trajectory_artifact_json(
    artifact: TrajectoryArtifact,
) -> str:
    """Serialize only recursively verified Stage 9B artifacts."""

    verifier = _VERIFIERS.get(type(artifact))
    if verifier is None or not verifier(artifact):
        raise _error("trajectory artifact type or content failed integrity verification")
    try:
        payload = canonical_json(artifact.as_dict())
        if len(payload.encode("utf-8")) > MAX_SERIALIZED_ARTIFACT_BYTES:
            raise _error("trajectory artifact violates its byte bound")
        return payload
    except TrajectorySerializationError:
        raise
    except (
        TrajectoryValidationError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("trajectory artifact cannot be serialized canonically", error)


def manipulation_trajectory_artifact_from_canonical_json(
    payload: str,
    *,
    source_proposal: ExecutiveDecision | None = None,
    source_safety_decision: SafetyDecision | None = None,
    source_safety_kernel: SafetyKernel | None = None,
    source_skill_binding: SkillBindingResult | None = None,
    source_skill_manager: SkillManagerService | None = None,
) -> TrajectoryArtifact:
    """Parse exact canonical bytes using required authoritative provenance."""

    if type(payload) is not str:
        raise _error("canonical trajectory payload must be text")
    try:
        encoded = payload.encode("utf-8")
    except UnicodeError as error:
        raise _error("canonical trajectory payload must be UTF-8", error)
    if not encoded or len(encoded) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise _error("canonical trajectory payload violates its byte bound")
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _error(f"non-finite {value} is forbidden")
            ),
        )
        item = _mapping(document, "trajectory artifact")
        if canonical_json(item) != payload:
            raise _error("trajectory payload is not canonical JSON")
        schema = _mapping(item.get("schema"), "schema")
        parser = _PARSERS.get(schema.get("id"))
        if parser is None:
            raise _error("unknown trajectory artifact schema")
        if schema.get("id") == SAFETY_RESULT_SCHEMA_ID:
            return _safety_result(
                item,
                source_proposal=source_proposal,
                source_safety_decision=source_safety_decision,
                source_safety_kernel=source_safety_kernel,
            )
        if schema.get("id") == HANDOFF_DECISION_SCHEMA_ID:
            return _handoff(
                item,
                source_proposal=source_proposal,
                source_safety_decision=source_safety_decision,
                source_safety_kernel=source_safety_kernel,
                source_skill_binding=source_skill_binding,
                source_skill_manager=source_skill_manager,
            )
        return parser(item)
    except TrajectorySerializationError:
        raise
    except (
        json.JSONDecodeError,
        TrajectoryValidationError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("trajectory payload failed closed during reconstruction", error)
