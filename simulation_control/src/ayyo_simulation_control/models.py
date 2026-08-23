"""Immutable command, evidence, result, and failure contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
import re

from .canonical import JSONValue, sha256_document
from .errors import ControlFailureCode, ControlValidationError


CONTROL_SCHEMA_VERSION = 1
MAX_CONTROL_TARGETS = 8
MAX_COMMAND_WINDOW_NS = 5_000_000_000
MAX_CONTROL_TEXT_LENGTH = 16_384

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 256
        or _IDENTIFIER_PATTERN.fullmatch(value) is None
    ):
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_COMMAND,
            f"{field_name} must be a bounded lowercase ASCII identifier",
        )
    return value


def _text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_CONTROL_TEXT_LENGTH
    ):
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_COMMAND,
            f"{field_name} must be non-empty bounded text",
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_COMMAND,
            f"{field_name} contains invalid Unicode",
        ) from error
    return value


def _fingerprint_text(value: object, prefix: str, field_name: str) -> str:
    if type(value) is not str or not value.startswith(prefix):
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
            f"{field_name} has an unsupported fingerprint kind",
        )
    digest = value.removeprefix(prefix)
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
            f"{field_name} must contain lowercase SHA-256 hexadecimal",
        )
    return value


class ControlFingerprintKind(StrEnum):
    COMMAND = "command"
    FAILURE = "failure"
    RESULT = "result"
    LIMIT_CATALOG = "limit_catalog"


@dataclass(frozen=True, slots=True)
class ControlFingerprint:
    kind: ControlFingerprintKind
    digest: str
    algorithm: str = "sha256"
    schema_version: int = CONTROL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ControlFingerprintKind):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control fingerprint kind is invalid",
            )
        if self.algorithm != "sha256" or self.schema_version != CONTROL_SCHEMA_VERSION:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control fingerprint format is unsupported",
            )
        if type(self.digest) is not str or _SHA256_PATTERN.fullmatch(self.digest) is None:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control fingerprint digest must be lowercase SHA-256 hexadecimal",
            )

    def __str__(self) -> str:
        return f"{self.kind.value}:sha256:{self.digest}"


def fingerprint_document(
    kind: ControlFingerprintKind,
    document: JSONValue,
) -> ControlFingerprint:
    return ControlFingerprint(kind=kind, digest=sha256_document(document))


class ControlAuthorityKind(StrEnum):
    DEVELOPMENT_TEST = "development_test"
    RUNTIME_ELIGIBLE = "runtime_eligible"


class ControlCommandType(StrEnum):
    SET_JOINT_POSITIONS = "set_joint_positions"


class ControlResultStatus(StrEnum):
    REJECTED = "rejected"
    COMPLETED = "completed"


class ControllerLifecycle(StrEnum):
    UNAVAILABLE = "unavailable"
    INACTIVE = "inactive"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class ControlAuthority:
    kind: ControlAuthorityKind
    source_id: str
    runtime_request_id: str | None = None
    runtime_request_fingerprint: str | None = None
    runtime_decision_id: str | None = None
    runtime_decision_fingerprint: str | None = None
    invocation_fingerprint: str | None = None
    endpoint_binding_fingerprint: str | None = None
    runtime_registry_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ControlAuthorityKind):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "control authority kind is invalid",
            )
        _identifier(self.source_id, "authority source_id")
        runtime_fields = (
            self.runtime_request_id,
            self.runtime_request_fingerprint,
            self.runtime_decision_id,
            self.runtime_decision_fingerprint,
            self.invocation_fingerprint,
            self.endpoint_binding_fingerprint,
            self.runtime_registry_fingerprint,
        )
        if self.kind is ControlAuthorityKind.DEVELOPMENT_TEST:
            if any(value is not None for value in runtime_fields):
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                    "development authority cannot claim Runtime Bridge identity",
                )
            return
        if any(value is None for value in runtime_fields):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "runtime authority requires the complete upstream identity chain",
            )
        assert self.runtime_request_id is not None
        match = re.fullmatch(r"runtime-request-([0-9a-f]{64})", self.runtime_request_id)
        if match is None:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "runtime request identity is malformed",
            )
        assert self.runtime_request_fingerprint is not None
        _fingerprint_text(
            self.runtime_request_fingerprint,
            "request:sha256:",
            "runtime request fingerprint",
        )
        if match.group(1) != self.runtime_request_fingerprint.rsplit(":", 1)[1]:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "runtime request ID and fingerprint disagree",
            )
        assert self.runtime_decision_id is not None
        decision_match = re.fullmatch(
            r"runtime-decision-([0-9a-f]{64})",
            self.runtime_decision_id,
        )
        if decision_match is None:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "runtime decision identity is malformed",
            )
        assert self.runtime_decision_fingerprint is not None
        _fingerprint_text(
            self.runtime_decision_fingerprint,
            "decision:sha256:",
            "runtime decision fingerprint",
        )
        if decision_match.group(1) != self.runtime_decision_fingerprint.rsplit(":", 1)[1]:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "runtime decision ID and fingerprint disagree",
            )
        assert self.invocation_fingerprint is not None
        assert self.endpoint_binding_fingerprint is not None
        assert self.runtime_registry_fingerprint is not None
        _fingerprint_text(
            self.invocation_fingerprint,
            "invocation:sha256:",
            "invocation fingerprint",
        )
        _fingerprint_text(
            self.endpoint_binding_fingerprint,
            "endpoint_binding:sha256:",
            "endpoint binding fingerprint",
        )
        _fingerprint_text(
            self.runtime_registry_fingerprint,
            "registry:sha256:",
            "runtime registry fingerprint",
        )

    def document(self) -> dict[str, JSONValue]:
        return {
            "endpoint_binding_fingerprint": self.endpoint_binding_fingerprint,
            "invocation_fingerprint": self.invocation_fingerprint,
            "kind": self.kind.value,
            "runtime_registry_fingerprint": self.runtime_registry_fingerprint,
            "runtime_decision_fingerprint": self.runtime_decision_fingerprint,
            "runtime_decision_id": self.runtime_decision_id,
            "runtime_request_fingerprint": self.runtime_request_fingerprint,
            "runtime_request_id": self.runtime_request_id,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class JointPositionTarget:
    joint_name: str
    position: float

    def __post_init__(self) -> None:
        _identifier(self.joint_name, "joint_name")
        if type(self.position) not in {int, float} or not math.isfinite(self.position):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "joint position must be a finite real number",
            )
        object.__setattr__(self, "position", float(self.position))


@dataclass(frozen=True, slots=True, init=False)
class SimulationControlCommand:
    command_id: str
    command_type: ControlCommandType
    targets: tuple[JointPositionTarget, ...]
    issued_at_ns: int
    expires_at_ns: int
    authority: ControlAuthority
    fingerprint: ControlFingerprint

    def __init__(
        self,
        *,
        command_type: ControlCommandType,
        targets: tuple[JointPositionTarget, ...],
        issued_at_ns: int,
        expires_at_ns: int,
        authority: ControlAuthority,
    ) -> None:
        if not isinstance(command_type, ControlCommandType):
            raise ControlValidationError(
                ControlFailureCode.UNSUPPORTED_COMMAND_TYPE,
                "simulation control command type is unsupported",
            )
        if (
            type(targets) is not tuple
            or not targets
            or len(targets) > MAX_CONTROL_TARGETS
            or not all(type(target) is JointPositionTarget for target in targets)
        ):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "joint targets must be a bounded immutable tuple",
            )
        names = tuple(target.joint_name for target in targets)
        if len(names) != len(set(names)):
            raise ControlValidationError(
                ControlFailureCode.DUPLICATE_TARGET,
                "a command cannot target the same joint more than once",
            )
        if type(issued_at_ns) is not int or issued_at_ns < 0:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "issued_at_ns must be a non-negative integer in simulation time",
            )
        if (
            type(expires_at_ns) is not int
            or expires_at_ns <= issued_at_ns
            or expires_at_ns - issued_at_ns > MAX_COMMAND_WINDOW_NS
        ):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "command expiry must define a positive bounded simulation-time window",
            )
        if type(authority) is not ControlAuthority:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "command authority must be a typed immutable contract",
            )
        targets = tuple(sorted(targets, key=lambda target: target.joint_name))
        document: dict[str, JSONValue] = {
            "authority": authority.document(),
            "command_type": command_type.value,
            "expires_at_ns": expires_at_ns,
            "issued_at_ns": issued_at_ns,
            "schema": "ayyo.simulation-control.command.v1",
            "targets": [
                {"joint_name": target.joint_name, "position": target.position}
                for target in targets
            ],
        }
        fingerprint = fingerprint_document(ControlFingerprintKind.COMMAND, document)
        object.__setattr__(self, "command_id", f"control-command-{fingerprint.digest}")
        object.__setattr__(self, "command_type", command_type)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "issued_at_ns", issued_at_ns)
        object.__setattr__(self, "expires_at_ns", expires_at_ns)
        object.__setattr__(self, "authority", authority)
        object.__setattr__(self, "fingerprint", fingerprint)


def rebuild_command(command: object) -> SimulationControlCommand:
    if type(command) is not SimulationControlCommand:
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_COMMAND,
            "control boundary requires a SimulationControlCommand",
        )
    rebuilt = SimulationControlCommand(
        command_type=command.command_type,
        targets=command.targets,
        issued_at_ns=command.issued_at_ns,
        expires_at_ns=command.expires_at_ns,
        authority=command.authority,
    )
    if rebuilt != command:
        raise ControlValidationError(
            ControlFailureCode.MALFORMED_COMMAND,
            "control command identity is stale",
        )
    return rebuilt


@dataclass(frozen=True, slots=True)
class JointStateSample:
    joint_name: str
    position: float
    observed_at_ns: int
    sequence: int

    def __post_init__(self) -> None:
        _identifier(self.joint_name, "state joint_name")
        if type(self.position) not in {int, float} or not math.isfinite(self.position):
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "joint state position must be finite",
            )
        if type(self.observed_at_ns) is not int or self.observed_at_ns < 0:
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "joint state timestamp is invalid",
            )
        if type(self.sequence) is not int or self.sequence < 0:
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "joint state sequence is invalid",
            )
        object.__setattr__(self, "position", float(self.position))


@dataclass(frozen=True, slots=True)
class ControllerSnapshot:
    controller_name: str
    controller_lifecycle: ControllerLifecycle
    broadcaster_lifecycle: ControllerLifecycle
    hardware_lifecycle: ControllerLifecycle
    command_subscribers: int
    observed_at_ns: int
    joint_state: JointStateSample | None

    def __post_init__(self) -> None:
        _identifier(self.controller_name, "controller_name")
        for lifecycle in (
            self.controller_lifecycle,
            self.broadcaster_lifecycle,
            self.hardware_lifecycle,
        ):
            if not isinstance(lifecycle, ControllerLifecycle):
                raise ControlValidationError(
                    ControlFailureCode.CONTROLLER_UNAVAILABLE,
                    "controller lifecycle state is invalid",
                )
        if type(self.command_subscribers) is not int or self.command_subscribers < 0:
            raise ControlValidationError(
                ControlFailureCode.CONTROLLER_UNAVAILABLE,
                "controller subscriber count is invalid",
            )
        if type(self.observed_at_ns) is not int or self.observed_at_ns < 0:
            raise ControlValidationError(
                ControlFailureCode.CONTROLLER_UNAVAILABLE,
                "controller observation timestamp is invalid",
            )
        if self.joint_state is not None and type(self.joint_state) is not JointStateSample:
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "controller snapshot state is invalid",
            )


@dataclass(frozen=True, slots=True, init=False)
class ControlFailure:
    failure_id: str
    code: ControlFailureCode
    detail: str
    command_id: str | None
    command_fingerprint: ControlFingerprint | None
    fingerprint: ControlFingerprint

    def __init__(
        self,
        *,
        code: ControlFailureCode,
        detail: str,
        command: SimulationControlCommand | None = None,
    ) -> None:
        if not isinstance(code, ControlFailureCode):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control failure code is invalid",
            )
        detail = _text(detail, "control failure detail")
        if command is not None:
            command = rebuild_command(command)
        document: dict[str, JSONValue] = {
            "code": code.value,
            "command_fingerprint": None if command is None else str(command.fingerprint),
            "command_id": None if command is None else command.command_id,
            "detail": detail,
            "schema": "ayyo.simulation-control.failure.v1",
        }
        fingerprint = fingerprint_document(ControlFingerprintKind.FAILURE, document)
        object.__setattr__(self, "failure_id", f"control-failure-{fingerprint.digest}")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "detail", detail)
        object.__setattr__(self, "command_id", None if command is None else command.command_id)
        object.__setattr__(
            self,
            "command_fingerprint",
            None if command is None else command.fingerprint,
        )
        object.__setattr__(self, "fingerprint", fingerprint)


@dataclass(frozen=True, slots=True, init=False)
class SimulationControlResult:
    result_id: str
    status: ControlResultStatus
    command: SimulationControlCommand
    failure: ControlFailure | None
    boundary_accepted: bool
    controller_dispatched: bool
    feedback_observed: bool
    state_changed: bool
    target_reached: bool
    initial_position: float | None
    final_position: float | None
    observed_at_ns: int | None
    fingerprint: ControlFingerprint

    def __init__(
        self,
        *,
        status: ControlResultStatus,
        command: SimulationControlCommand,
        failure: ControlFailure | None,
        boundary_accepted: bool,
        controller_dispatched: bool,
        feedback_observed: bool,
        state_changed: bool,
        target_reached: bool,
        initial_position: float | None,
        final_position: float | None,
        observed_at_ns: int | None,
    ) -> None:
        command = rebuild_command(command)
        if not isinstance(status, ControlResultStatus):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control result status is invalid",
            )
        flags = (
            boundary_accepted,
            controller_dispatched,
            feedback_observed,
            state_changed,
            target_reached,
        )
        if not all(type(flag) is bool for flag in flags):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control result evidence flags must be booleans",
            )
        evidence_chain = (
            boundary_accepted,
            controller_dispatched,
            feedback_observed,
            state_changed,
            target_reached,
        )
        if any(
            evidence_chain[index] and not evidence_chain[index - 1]
            for index in range(1, len(evidence_chain))
        ):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "control result evidence cannot skip a causal boundary",
            )
        if initial_position is not None and (
            type(initial_position) not in {int, float} or not math.isfinite(initial_position)
        ):
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "initial feedback position is invalid",
            )
        if final_position is not None and (
            type(final_position) not in {int, float} or not math.isfinite(final_position)
        ):
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "final feedback position is invalid",
            )
        if observed_at_ns is not None and (
            type(observed_at_ns) is not int or observed_at_ns < 0
        ):
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "result observation timestamp is invalid",
            )
        if boundary_accepted != (initial_position is not None):
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "boundary acceptance requires exactly one initial state value",
            )
        if (
            feedback_observed
            and (final_position is None or observed_at_ns is None)
        ) or (
            not feedback_observed
            and (final_position is not None or observed_at_ns is not None)
        ):
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "feedback evidence requires final state and observation time",
            )
        if observed_at_ns is not None and observed_at_ns < command.issued_at_ns:
            raise ControlValidationError(
                ControlFailureCode.STATE_UNAVAILABLE,
                "feedback observation predates command issuance",
            )
        if status is ControlResultStatus.COMPLETED:
            if failure is not None or not all(flags):
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_COMMAND,
                    "completed control result requires the full evidence chain",
                )
            if initial_position is None or final_position is None or observed_at_ns is None:
                raise ControlValidationError(
                    ControlFailureCode.STATE_UNAVAILABLE,
                    "completed control result requires before-and-after feedback",
                )
        else:
            if type(failure) is not ControlFailure or target_reached:
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_COMMAND,
                    "rejected control result requires a typed failure and no completion",
                )
            if failure.command_id != command.command_id:
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_COMMAND,
                    "control failure does not match its result command",
                )
        document: dict[str, JSONValue] = {
            "boundary_accepted": boundary_accepted,
            "command_fingerprint": str(command.fingerprint),
            "command_id": command.command_id,
            "controller_dispatched": controller_dispatched,
            "failure_fingerprint": None if failure is None else str(failure.fingerprint),
            "feedback_observed": feedback_observed,
            "final_position": None if final_position is None else float(final_position),
            "initial_position": (
                None if initial_position is None else float(initial_position)
            ),
            "observed_at_ns": observed_at_ns,
            "schema": "ayyo.simulation-control.result.v1",
            "state_changed": state_changed,
            "status": status.value,
            "target_reached": target_reached,
        }
        fingerprint = fingerprint_document(ControlFingerprintKind.RESULT, document)
        object.__setattr__(self, "result_id", f"control-result-{fingerprint.digest}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "failure", failure)
        object.__setattr__(self, "boundary_accepted", boundary_accepted)
        object.__setattr__(self, "controller_dispatched", controller_dispatched)
        object.__setattr__(self, "feedback_observed", feedback_observed)
        object.__setattr__(self, "state_changed", state_changed)
        object.__setattr__(self, "target_reached", target_reached)
        object.__setattr__(
            self,
            "initial_position",
            None if initial_position is None else float(initial_position),
        )
        object.__setattr__(
            self,
            "final_position",
            None if final_position is None else float(final_position),
        )
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "fingerprint", fingerprint)
