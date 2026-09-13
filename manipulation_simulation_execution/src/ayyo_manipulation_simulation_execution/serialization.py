"""Strict canonical serialization for Stage 9C contracts."""

from __future__ import annotations

import json
from typing import Callable

from ayyo_manipulation_trajectory import (
    ExecutionHandoffEligibilityDecision,
    manipulation_trajectory_artifact_from_canonical_json,
)

from .canonical import (
    JSONValue,
    MAX_SERIALIZED_ARTIFACT_BYTES,
    SCHEMA_VERSION,
    canonical_json,
)
from .errors import (
    SimulationExecutionSerializationError,
    SimulationExecutionValidationError,
)
from .models import (
    COLLISION_PROOF_SCHEMA_ID,
    CONTROLLER_CONTRACT_SCHEMA_ID,
    CONTROLLER_STATE_SCHEMA_ID,
    EXECUTION_GOAL_SCHEMA_ID,
    EXECUTION_OBSERVATION_SCHEMA_ID,
    EXECUTION_REQUEST_SCHEMA_ID,
    EXECUTION_RESULT_SCHEMA_ID,
    JOINT_STATE_SCHEMA_ID,
    PREFLIGHT_EVIDENCE_SCHEMA_ID,
    SAMPLING_POLICY_SCHEMA_ID,
    CollisionSamplingPolicy,
    DenseCollisionSample,
    GoalAcceptance,
    HardwareAuthority,
    PhysicalValidationClaim,
    PreflightReason,
    PreflightStatus,
    ProductionRuntimeAuthority,
    SimulationAuthority,
    SimulationCollisionProof,
    SimulationControllerContract,
    SimulationControllerState,
    SimulationEnvironment,
    SimulationExecutionGoal,
    SimulationExecutionObservation,
    SimulationExecutionOutcome,
    SimulationExecutionRequest,
    SimulationExecutionResult,
    SimulationExecutionResultStatus,
    SimulationGoalPoint,
    SimulationMotionStatus,
    SimulationPreflightEvidence,
    SimulatedJointState,
    verify_collision_proof,
    verify_controller_contract,
    verify_controller_state,
    verify_execution_goal,
    verify_execution_observation,
    verify_execution_request,
    verify_execution_result,
    verify_joint_state,
    verify_preflight_evidence,
    verify_sampling_policy,
)


Stage9CArtifact = (
    SimulationControllerContract
    | CollisionSamplingPolicy
    | SimulationExecutionRequest
    | SimulationCollisionProof
    | SimulatedJointState
    | SimulationControllerState
    | SimulationPreflightEvidence
    | SimulationExecutionGoal
    | SimulationExecutionObservation
    | SimulationExecutionResult
)


def _error(
    detail: str,
    cause: BaseException | None = None,
) -> SimulationExecutionSerializationError:
    error = SimulationExecutionSerializationError(detail)
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
        raise _error("unknown Stage 9C schema or version")


def _verify_recomputed(
    document: dict[str, JSONValue],
    artifact: Stage9CArtifact,
) -> Stage9CArtifact:
    if artifact.as_dict() != document:
        raise _error("serialized identities or content do not match recomputed evidence")
    return artifact


def _controller(value: object) -> SimulationControllerContract:
    item = _mapping(value, "controller_contract")
    _exact_keys(
        item,
        {
            "action_endpoint",
            "allow_partial_joints_goal",
            "command_interfaces",
            "controller_configuration_fingerprint",
            "controller_contract_fingerprint",
            "controller_contract_id",
            "controller_name",
            "controller_type",
            "environment",
            "hardware_system",
            "interpolation_method",
            "joint_names",
            "manipulation_control_enabled",
            "profile_id",
            "schema",
            "simulation_description_fingerprint",
            "simulation_mode",
            "state_interfaces",
            "use_sim_time",
        },
        "controller_contract",
    )
    _schema(item, CONTROLLER_CONTRACT_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SimulationControllerContract(
            profile_id=item["profile_id"],
            environment=SimulationEnvironment(item["environment"]),
            hardware_system=item["hardware_system"],
            controller_name=item["controller_name"],
            controller_type=item["controller_type"],
            action_endpoint=item["action_endpoint"],
            joint_names=tuple(_sequence(item["joint_names"], "joint_names")),
            command_interfaces=tuple(
                _sequence(item["command_interfaces"], "command_interfaces")
            ),
            state_interfaces=tuple(
                _sequence(item["state_interfaces"], "state_interfaces")
            ),
            interpolation_method=item["interpolation_method"],
            allow_partial_joints_goal=item["allow_partial_joints_goal"],
            use_sim_time=item["use_sim_time"],
            simulation_mode=item["simulation_mode"],
            manipulation_control_enabled=item["manipulation_control_enabled"],
            simulation_description_fingerprint=(
                item["simulation_description_fingerprint"]
            ),
            controller_configuration_fingerprint=(
                item["controller_configuration_fingerprint"]
            ),
        ),
    )


def _sampling_policy(value: object) -> CollisionSamplingPolicy:
    item = _mapping(value, "sampling_policy")
    _exact_keys(
        item,
        {
            "include_segment_endpoints",
            "interpolation_method",
            "maximum_joint_step",
            "maximum_samples_per_segment",
            "maximum_total_samples",
            "policy_id",
            "sampling_policy_fingerprint",
            "schema",
        },
        "sampling_policy",
    )
    _schema(item, SAMPLING_POLICY_SCHEMA_ID)
    return _verify_recomputed(
        item,
        CollisionSamplingPolicy(
            policy_id=item["policy_id"],
            maximum_joint_step=item["maximum_joint_step"],
            maximum_samples_per_segment=item["maximum_samples_per_segment"],
            maximum_total_samples=item["maximum_total_samples"],
            include_segment_endpoints=item["include_segment_endpoints"],
            interpolation_method=item["interpolation_method"],
        ),
    )


def _stage9b_handoff(value: object, context: dict[str, object]):
    item = _mapping(value, "stage9b_handoff")
    try:
        artifact = manipulation_trajectory_artifact_from_canonical_json(
            canonical_json(item),
            **context,
        )
    except (
        AssertionError,
        ArithmeticError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("nested Stage 9B handoff failed authoritative reconstruction", error)
    if type(artifact) is not ExecutionHandoffEligibilityDecision:
        raise _error("nested Stage 9B artifact is not a final handoff decision")
    return artifact


def _request(value: object, context: dict[str, object]) -> SimulationExecutionRequest:
    item = _mapping(value, "execution_request")
    _exact_keys(
        item,
        {
            "authority",
            "controller_contract",
            "execution_request_fingerprint",
            "execution_request_id",
            "hardware_authority",
            "physical_validation",
            "production_runtime_authority",
            "sampling_policy",
            "schema",
            "stage9b_handoff",
        },
        "execution_request",
    )
    _schema(item, EXECUTION_REQUEST_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SimulationExecutionRequest(
            stage9b_handoff=_stage9b_handoff(item["stage9b_handoff"], context),
            controller_contract=_controller(item["controller_contract"]),
            sampling_policy=_sampling_policy(item["sampling_policy"]),
            authority=SimulationAuthority(item["authority"]),
            physical_validation=PhysicalValidationClaim(item["physical_validation"]),
            hardware_authority=HardwareAuthority(item["hardware_authority"]),
            production_runtime_authority=ProductionRuntimeAuthority(
                item["production_runtime_authority"]
            ),
        ),
    )


def _sample(value: object) -> DenseCollisionSample:
    item = _mapping(value, "collision_sample")
    _exact_keys(
        item,
        {
            "environment_collision_free",
            "positions",
            "sample_index",
            "segment_fraction",
            "segment_index",
            "segment_subdivisions",
            "self_collision_free",
            "subdivision_index",
            "within_joint_limits",
        },
        "collision_sample",
    )
    return DenseCollisionSample(
        sample_index=item["sample_index"],
        segment_index=item["segment_index"],
        subdivision_index=item["subdivision_index"],
        segment_subdivisions=item["segment_subdivisions"],
        segment_fraction=item["segment_fraction"],
        positions=tuple(_sequence(item["positions"], "sample positions")),
        self_collision_free=item["self_collision_free"],
        environment_collision_free=item["environment_collision_free"],
        within_joint_limits=item["within_joint_limits"],
    )


def _collision_proof(value: object, context: dict[str, object]) -> SimulationCollisionProof:
    item = _mapping(value, "collision_proof")
    _exact_keys(
        item,
        {
            "backend_id",
            "backend_version",
            "collision_proof_fingerprint",
            "collision_proof_id",
            "continuous_collision_certification",
            "execution_disposition",
            "execution_request",
            "input_fingerprint",
            "physical_validation",
            "samples",
            "schema",
        },
        "collision_proof",
    )
    _schema(item, COLLISION_PROOF_SCHEMA_ID)
    from ayyo_manipulation_planning import ExecutionDisposition
    from ayyo_manipulation_trajectory import PhysicalValidationStatus

    return _verify_recomputed(
        item,
        SimulationCollisionProof(
            execution_request=_request(item["execution_request"], context),
            input_fingerprint=item["input_fingerprint"],
            backend_id=item["backend_id"],
            backend_version=item["backend_version"],
            samples=tuple(
                _sample(raw) for raw in _sequence(item["samples"], "samples")
            ),
            continuous_collision_certification=item[
                "continuous_collision_certification"
            ],
            execution_disposition=ExecutionDisposition(item["execution_disposition"]),
            physical_validation=PhysicalValidationStatus(item["physical_validation"]),
        ),
    )


def _joint_state(value: object) -> SimulatedJointState:
    item = _mapping(value, "joint_state")
    _exact_keys(
        item,
        {
            "joint_names",
            "joint_state_fingerprint",
            "observed_at_ns",
            "positions",
            "schema",
            "sequence",
            "source",
        },
        "joint_state",
    )
    _schema(item, JOINT_STATE_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SimulatedJointState(
            joint_names=tuple(_sequence(item["joint_names"], "joint_names")),
            positions=tuple(_sequence(item["positions"], "positions")),
            observed_at_ns=item["observed_at_ns"],
            sequence=item["sequence"],
            source=item["source"],
        ),
    )


def _controller_state(value: object) -> SimulationControllerState:
    item = _mapping(value, "controller_state")
    _exact_keys(
        item,
        {
            "action_server_available",
            "claimed_command_interfaces",
            "controller_active",
            "controller_contract_fingerprint",
            "controller_contract_id",
            "controller_state_fingerprint",
            "hardware_active",
            "observed_at_ns",
            "schema",
            "state_broadcaster_active",
        },
        "controller_state",
    )
    _schema(item, CONTROLLER_STATE_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SimulationControllerState(
            controller_contract_id=item["controller_contract_id"],
            controller_contract_fingerprint=item[
                "controller_contract_fingerprint"
            ],
            controller_active=item["controller_active"],
            hardware_active=item["hardware_active"],
            state_broadcaster_active=item["state_broadcaster_active"],
            action_server_available=item["action_server_available"],
            claimed_command_interfaces=tuple(
                _sequence(
                    item["claimed_command_interfaces"],
                    "claimed_command_interfaces",
                )
            ),
            observed_at_ns=item["observed_at_ns"],
        ),
    )


def _preflight(value: object, context: dict[str, object]) -> SimulationPreflightEvidence:
    item = _mapping(value, "preflight_evidence")
    _exact_keys(
        item,
        {
            "collision_proof",
            "controller_state",
            "evaluated_at_ns",
            "physical_validation",
            "preflight_evidence_fingerprint",
            "preflight_evidence_id",
            "reasons",
            "schema",
            "start_state",
            "start_tolerance",
            "state_freshness_ns",
            "status",
        },
        "preflight_evidence",
    )
    _schema(item, PREFLIGHT_EVIDENCE_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SimulationPreflightEvidence(
            collision_proof=_collision_proof(item["collision_proof"], context),
            start_state=_joint_state(item["start_state"]),
            controller_state=_controller_state(item["controller_state"]),
            evaluated_at_ns=item["evaluated_at_ns"],
            status=PreflightStatus(item["status"]),
            reasons=tuple(
                PreflightReason(raw)
                for raw in _sequence(item["reasons"], "reasons")
            ),
            start_tolerance=item["start_tolerance"],
            state_freshness_ns=item["state_freshness_ns"],
            physical_validation=PhysicalValidationClaim(item["physical_validation"]),
        ),
    )


def _goal_point(value: object) -> SimulationGoalPoint:
    item = _mapping(value, "goal_point")
    _exact_keys(item, {"positions", "time_from_start"}, "goal_point")
    return SimulationGoalPoint(
        positions=tuple(_sequence(item["positions"], "positions")),
        time_from_start=item["time_from_start"],
    )


def _goal(value: object, context: dict[str, object]) -> SimulationExecutionGoal:
    item = _mapping(value, "execution_goal")
    _exact_keys(
        item,
        {
            "action_endpoint",
            "execution_goal_fingerprint",
            "execution_goal_id",
            "execution_timeout_ns",
            "joint_names",
            "points",
            "preflight_evidence",
            "schema",
        },
        "execution_goal",
    )
    _schema(item, EXECUTION_GOAL_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SimulationExecutionGoal(
            preflight_evidence=_preflight(item["preflight_evidence"], context),
            action_endpoint=item["action_endpoint"],
            joint_names=tuple(_sequence(item["joint_names"], "joint_names")),
            points=tuple(
                _goal_point(raw) for raw in _sequence(item["points"], "points")
            ),
            execution_timeout_ns=item["execution_timeout_ns"],
        ),
    )


def _optional_positions(value: object, name: str) -> tuple[float, ...] | None:
    if value is None:
        return None
    return tuple(_sequence(value, name))


def _observation(value: object) -> SimulationExecutionObservation:
    item = _mapping(value, "execution_observation")
    _exact_keys(
        item,
        {
            "acceptance",
            "cancellation_confirmed",
            "cancellation_requested",
            "completed_at_ns",
            "controller_error_code",
            "detail",
            "ending_positions",
            "execution_goal_fingerprint",
            "execution_goal_id",
            "feedback_samples_observed",
            "final_joint_errors",
            "final_target_positions",
            "observation_fingerprint",
            "observation_id",
            "outcome",
            "schema",
            "started_at_ns",
            "starting_positions",
            "timed_out",
        },
        "execution_observation",
    )
    _schema(item, EXECUTION_OBSERVATION_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SimulationExecutionObservation(
            execution_goal_id=item["execution_goal_id"],
            execution_goal_fingerprint=item["execution_goal_fingerprint"],
            acceptance=GoalAcceptance(item["acceptance"]),
            outcome=SimulationExecutionOutcome(item["outcome"]),
            controller_error_code=item["controller_error_code"],
            started_at_ns=item["started_at_ns"],
            completed_at_ns=item["completed_at_ns"],
            starting_positions=tuple(
                _sequence(item["starting_positions"], "starting_positions")
            ),
            ending_positions=_optional_positions(
                item["ending_positions"],
                "ending_positions",
            ),
            final_target_positions=tuple(
                _sequence(
                    item["final_target_positions"],
                    "final_target_positions",
                )
            ),
            final_joint_errors=_optional_positions(
                item["final_joint_errors"],
                "final_joint_errors",
            ),
            feedback_samples_observed=item["feedback_samples_observed"],
            cancellation_requested=item["cancellation_requested"],
            cancellation_confirmed=item["cancellation_confirmed"],
            timed_out=item["timed_out"],
            detail=item["detail"],
        ),
    )


def _result(value: object, context: dict[str, object]) -> SimulationExecutionResult:
    item = _mapping(value, "execution_result")
    _exact_keys(
        item,
        {
            "authority",
            "execution_goal",
            "execution_result_fingerprint",
            "execution_result_id",
            "hardware_authority",
            "motion_status",
            "observation",
            "physical_validation",
            "production_runtime_authority",
            "schema",
            "status",
        },
        "execution_result",
    )
    _schema(item, EXECUTION_RESULT_SCHEMA_ID)
    return _verify_recomputed(
        item,
        SimulationExecutionResult(
            execution_goal=_goal(item["execution_goal"], context),
            observation=_observation(item["observation"]),
            status=SimulationExecutionResultStatus(item["status"]),
            motion_status=SimulationMotionStatus(item["motion_status"]),
            authority=SimulationAuthority(item["authority"]),
            physical_validation=PhysicalValidationClaim(item["physical_validation"]),
            hardware_authority=HardwareAuthority(item["hardware_authority"]),
            production_runtime_authority=ProductionRuntimeAuthority(
                item["production_runtime_authority"]
            ),
        ),
    )


_VERIFIERS: dict[type, Callable[[object], bool]] = {
    SimulationControllerContract: verify_controller_contract,
    CollisionSamplingPolicy: verify_sampling_policy,
    SimulationExecutionRequest: verify_execution_request,
    SimulationCollisionProof: verify_collision_proof,
    SimulatedJointState: verify_joint_state,
    SimulationControllerState: verify_controller_state,
    SimulationPreflightEvidence: verify_preflight_evidence,
    SimulationExecutionGoal: verify_execution_goal,
    SimulationExecutionObservation: verify_execution_observation,
    SimulationExecutionResult: verify_execution_result,
}


def canonical_simulation_execution_artifact_json(artifact: Stage9CArtifact) -> str:
    """Serialize only recursively verified Stage 9C artifacts."""

    try:
        verifier = _VERIFIERS.get(type(artifact))
        if verifier is None or not verifier(artifact):
            raise _error("Stage 9C artifact failed recursive integrity verification")
        payload = canonical_json(artifact.as_dict())
        if len(payload.encode("utf-8")) > MAX_SERIALIZED_ARTIFACT_BYTES:
            raise _error("Stage 9C artifact violates its byte bound")
        return payload
    except SimulationExecutionSerializationError:
        raise
    except (
        AssertionError,
        ArithmeticError,
        AttributeError,
        KeyError,
        SimulationExecutionValidationError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("Stage 9C artifact cannot be serialized canonically", error)


def simulation_execution_artifact_from_canonical_json(
    payload: str,
    *,
    source_proposal=None,
    source_safety_decision=None,
    source_safety_kernel=None,
    source_skill_binding=None,
    source_skill_manager=None,
) -> Stage9CArtifact:
    """Reconstruct exact canonical bytes using Stage 9B authoritative contexts."""

    if type(payload) is not str:
        raise _error("canonical Stage 9C payload must be text")
    try:
        encoded = payload.encode("utf-8")
    except UnicodeError as error:
        raise _error("canonical Stage 9C payload must be UTF-8", error)
    if not encoded or len(encoded) > MAX_SERIALIZED_ARTIFACT_BYTES:
        raise _error("canonical Stage 9C payload violates its byte bound")
    context = {
        "source_proposal": source_proposal,
        "source_safety_decision": source_safety_decision,
        "source_safety_kernel": source_safety_kernel,
        "source_skill_binding": source_skill_binding,
        "source_skill_manager": source_skill_manager,
    }
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                _error(f"non-finite {value} is forbidden")
            ),
        )
        item = _mapping(document, "Stage 9C artifact")
        if canonical_json(item) != payload:
            raise _error("Stage 9C payload is not canonical JSON")
        schema = _mapping(item.get("schema"), "schema")
        schema_id = schema.get("id")
        if schema_id == CONTROLLER_CONTRACT_SCHEMA_ID:
            return _controller(item)
        if schema_id == SAMPLING_POLICY_SCHEMA_ID:
            return _sampling_policy(item)
        if schema_id == EXECUTION_REQUEST_SCHEMA_ID:
            return _request(item, context)
        if schema_id == COLLISION_PROOF_SCHEMA_ID:
            return _collision_proof(item, context)
        if schema_id == JOINT_STATE_SCHEMA_ID:
            return _joint_state(item)
        if schema_id == CONTROLLER_STATE_SCHEMA_ID:
            return _controller_state(item)
        if schema_id == PREFLIGHT_EVIDENCE_SCHEMA_ID:
            return _preflight(item, context)
        if schema_id == EXECUTION_GOAL_SCHEMA_ID:
            return _goal(item, context)
        if schema_id == EXECUTION_OBSERVATION_SCHEMA_ID:
            return _observation(item)
        if schema_id == EXECUTION_RESULT_SCHEMA_ID:
            return _result(item, context)
        raise _error("unknown Stage 9C artifact schema")
    except SimulationExecutionSerializationError:
        raise
    except (
        AssertionError,
        ArithmeticError,
        AttributeError,
        json.JSONDecodeError,
        KeyError,
        SimulationExecutionValidationError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
    ) as error:
        raise _error("Stage 9C payload failed closed during reconstruction", error)
