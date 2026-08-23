"""Runtime Bridge to simulation-control authorization gate.

This module is intentionally separate from the ROS-installed core import path.
It requires the complete standalone Runtime Bridge dependency chain and accepts
only reconstructed public Runtime Bridge objects.
"""

from __future__ import annotations

from dataclasses import dataclass

from ayyo_runtime_bridge import (
    RuntimeBridge,
    RuntimeDecision,
    RuntimeEligibility,
)

from .errors import ControlFailureCode, RuntimeControlRejectedError
from .models import (
    ControlAuthority,
    ControlAuthorityKind,
    ControlCommandType,
    JointPositionTarget,
    SimulationControlCommand,
)


RUNTIME_CONTROL_CAPABILITY = "simulation.joint.position.set"
RUNTIME_CONTROL_BACKEND = "simulation.control.position.v1"
RUNTIME_CONTROL_PACKAGE = "ayyo_interfaces"
RUNTIME_CONTROL_INTERFACE = "ApplyRuntimeJointPosition"
RUNTIME_CONTROL_SERVICE = "/ayyo/simulation_control/apply_runtime_joint_position"
RUNTIME_CONTROL_REQUEST_FIELDS = frozenset(
    {"issued_at_ns", "joint_name", "position", "valid_for_ns"}
)


@dataclass(frozen=True, slots=True)
class RuntimeSimulationControlBoundary:
    """Convert only a current eligible exact runtime request into a command."""

    bridge: RuntimeBridge

    def __post_init__(self) -> None:
        if type(self.bridge) is not RuntimeBridge:
            raise RuntimeControlRejectedError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "runtime control boundary requires a public RuntimeBridge",
            )

    def authorize(
        self,
        decision: RuntimeDecision,
        current_binding: object,
    ) -> SimulationControlCommand:
        """Revalidate and translate one exact Runtime Bridge request."""

        if type(decision) is not RuntimeDecision:
            raise RuntimeControlRejectedError(
                ControlFailureCode.MALFORMED_UPSTREAM_IDENTITY,
                "runtime control authorization requires a RuntimeDecision",
            )
        if decision.status is not RuntimeEligibility.ELIGIBLE:
            raise RuntimeControlRejectedError(
                ControlFailureCode.UPSTREAM_NOT_ELIGIBLE,
                "Runtime Bridge did not establish dispatch eligibility.",
            )
        current = self.bridge.revalidate(decision, current_binding)
        if current != decision or current.status is not RuntimeEligibility.ELIGIBLE:
            raise RuntimeControlRejectedError(
                ControlFailureCode.STALE_RUNTIME_BINDING,
                "Runtime Bridge eligibility changed before control translation.",
            )
        request = decision.request
        assert request is not None
        endpoint = request.endpoint_binding.endpoint
        invocation = request.invocation
        if (
            request.endpoint_binding.capability_id != RUNTIME_CONTROL_CAPABILITY
            or request.endpoint_binding.backend_id != RUNTIME_CONTROL_BACKEND
            or endpoint.package_name != RUNTIME_CONTROL_PACKAGE
            or endpoint.interface_name != RUNTIME_CONTROL_INTERFACE
            or endpoint.fully_qualified_name != RUNTIME_CONTROL_SERVICE
        ):
            raise RuntimeControlRejectedError(
                ControlFailureCode.RUNTIME_ENDPOINT_MISMATCH,
                "Runtime request does not match the reviewed control endpoint.",
            )
        if invocation.skill_definition.safety_classification.value != (
            "physical_movement"
        ):
            raise RuntimeControlRejectedError(
                ControlFailureCode.UPSTREAM_NOT_ELIGIBLE,
                "A movement adapter requires an explicit physical-movement classification.",
            )
        fields = request.request_fields
        if frozenset(fields) != RUNTIME_CONTROL_REQUEST_FIELDS:
            raise RuntimeControlRejectedError(
                ControlFailureCode.RUNTIME_ENDPOINT_MISMATCH,
                "Runtime control request fields do not match the reviewed contract.",
            )
        joint_name = fields["joint_name"]
        position = fields["position"]
        issued_at_ns = fields["issued_at_ns"]
        valid_for_ns = fields["valid_for_ns"]
        if type(issued_at_ns) is not int or type(valid_for_ns) is not int:
            raise RuntimeControlRejectedError(
                ControlFailureCode.RUNTIME_ENDPOINT_MISMATCH,
                "Runtime control time fields must be integer simulation nanoseconds.",
            )
        authority = ControlAuthority(
            kind=ControlAuthorityKind.RUNTIME_ELIGIBLE,
            source_id="runtime.bridge",
            runtime_request_id=request.request_id,
            runtime_request_fingerprint=str(request.fingerprint),
            runtime_decision_id=decision.decision_id,
            runtime_decision_fingerprint=str(decision.fingerprint),
            invocation_fingerprint=str(invocation.fingerprint),
            endpoint_binding_fingerprint=str(request.endpoint_binding.fingerprint),
            runtime_registry_fingerprint=str(request.runtime_registry_fingerprint),
        )
        return SimulationControlCommand(
            command_type=ControlCommandType.SET_JOINT_POSITIONS,
            targets=(JointPositionTarget(joint_name, position),),
            issued_at_ns=issued_at_ns,
            expires_at_ns=issued_at_ns + valid_for_ns,
            authority=authority,
        )
