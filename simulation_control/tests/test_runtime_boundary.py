# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from ayyo_executive import ExpectedResultCategory
from ayyo_runtime_bridge import (
    RosEndpointAvailability,
    RosServiceEndpoint,
    RuntimeBridge,
    RuntimeEligibility,
)
from ayyo_safety import HazardClass
from ayyo_skill_manager import SchemaProperty, ValueSchema, ValueType

from ayyo_simulation_control import ControlFailureCode, RuntimeControlRejectedError
from ayyo_simulation_control.runtime_boundary import (
    RUNTIME_CONTROL_BACKEND,
    RUNTIME_CONTROL_CAPABILITY,
    RUNTIME_CONTROL_INTERFACE,
    RUNTIME_CONTROL_PACKAGE,
    RuntimeSimulationControlBoundary,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPERS_PATH = REPOSITORY_ROOT / "runtime_bridge" / "tests" / "helpers.py"
SPEC = importlib.util.spec_from_file_location("runtime_test_helpers", HELPERS_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime_helpers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_helpers)


def request_schema() -> ValueSchema:
    return ValueSchema(
        ValueType.OBJECT,
        properties=(
            SchemaProperty("issued_at_ns", ValueSchema(ValueType.INTEGER, minimum=0)),
            SchemaProperty("joint_name", ValueSchema(ValueType.STRING)),
            SchemaProperty("position", ValueSchema(ValueType.NUMBER)),
            SchemaProperty(
                "valid_for_ns",
                ValueSchema(ValueType.INTEGER, minimum=1, maximum=5_000_000_000),
            ),
        ),
    )


def request_fields() -> dict[str, object]:
    return {
        "issued_at_ns": 1_000_000_000,
        "joint_name": "neck_yaw_joint",
        "position": 0.25,
        "valid_for_ns": 1_000_000_000,
    }


def definition(*, hazard: HazardClass, expected: ExpectedResultCategory):
    return runtime_helpers.skill(
        skill_id="simulation.neck.position.v1",
        backend_id=RUNTIME_CONTROL_BACKEND,
        capability_ids=(RUNTIME_CONTROL_CAPABILITY,),
        input_schema=request_schema(),
        safety_classification=hazard,
        expected_result=expected,
    )


def endpoint(skill_definition) -> RosServiceEndpoint:
    return RosServiceEndpoint(
        endpoint_id="simulation.control.position.v1",
        backend_id=RUNTIME_CONTROL_BACKEND,
        package_name=RUNTIME_CONTROL_PACKAGE,
        interface_name=RUNTIME_CONTROL_INTERFACE,
        endpoint_name="apply_runtime_joint_position",
        namespace="/ayyo/simulation_control",
        request_schema=skill_definition.input_schema,
        response_schema=skill_definition.output_schema,
        timeout_ms=skill_definition.timeout_ms,
        availability=RosEndpointAvailability.AVAILABLE,
    )


def binding_and_bridge(skill_definition, *, request_id: str = "request-1"):
    proposal = runtime_helpers.proposal(
        parameters=request_fields(),
        request_id=request_id,
        capability_id=RUNTIME_CONTROL_CAPABILITY,
        expected_result=skill_definition.expected_result,
    )
    binding = runtime_helpers.skill_binding(
        skill_definition,
        source_proposal=proposal,
    )
    registry = runtime_helpers.runtime_registry(
        skill_definition,
        contract=endpoint(skill_definition),
    )
    return binding, RuntimeBridge(registry)


class RuntimeSimulationControlBoundaryTests(unittest.TestCase):
    def test_physical_movement_deferral_remains_non_dispatchable(self) -> None:
        skill_definition = definition(
            hazard=HazardClass.PHYSICAL_MOVEMENT,
            expected=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
        )
        binding, bridge = binding_and_bridge(skill_definition)
        decision = bridge.evaluate(binding)
        self.assertIs(RuntimeEligibility.DEFERRED, decision.status)
        boundary = RuntimeSimulationControlBoundary(bridge)
        with self.assertRaises(RuntimeControlRejectedError) as raised:
            boundary.authorize(decision, binding)
        self.assertIs(
            ControlFailureCode.UPSTREAM_NOT_ELIGIBLE,
            raised.exception.code,
        )

    def test_eligible_nonphysical_skill_cannot_be_laundered_into_motion(self) -> None:
        skill_definition = definition(
            hazard=HazardClass.INFORMATIONAL_READ_ONLY,
            expected=ExpectedResultCategory.INFORMATION,
        )
        binding, bridge = binding_and_bridge(skill_definition)
        decision = bridge.evaluate(binding)
        self.assertIs(RuntimeEligibility.ELIGIBLE, decision.status)
        boundary = RuntimeSimulationControlBoundary(bridge)
        with self.assertRaises(RuntimeControlRejectedError) as raised:
            boundary.authorize(decision, binding)
        self.assertIs(
            ControlFailureCode.UPSTREAM_NOT_ELIGIBLE,
            raised.exception.code,
        )

    def test_stale_runtime_binding_is_rejected_before_translation(self) -> None:
        skill_definition = definition(
            hazard=HazardClass.INFORMATIONAL_READ_ONLY,
            expected=ExpectedResultCategory.INFORMATION,
        )
        binding, bridge = binding_and_bridge(skill_definition)
        decision = bridge.evaluate(binding)
        changed_binding, _ = binding_and_bridge(
            skill_definition,
            request_id="request-2",
        )
        boundary = RuntimeSimulationControlBoundary(bridge)
        with self.assertRaises(RuntimeControlRejectedError) as raised:
            boundary.authorize(decision, changed_binding)
        self.assertIs(
            ControlFailureCode.STALE_RUNTIME_BINDING,
            raised.exception.code,
        )

    def test_unreviewed_endpoint_identity_is_rejected(self) -> None:
        skill_definition = definition(
            hazard=HazardClass.INFORMATIONAL_READ_ONLY,
            expected=ExpectedResultCategory.INFORMATION,
        )
        proposal = runtime_helpers.proposal(
            parameters=request_fields(),
            capability_id=RUNTIME_CONTROL_CAPABILITY,
        )
        binding = runtime_helpers.skill_binding(
            skill_definition,
            source_proposal=proposal,
        )
        wrong_endpoint = RosServiceEndpoint(
            endpoint_id="simulation.control.wrong",
            backend_id=RUNTIME_CONTROL_BACKEND,
            package_name=RUNTIME_CONTROL_PACKAGE,
            interface_name="WrongInterface",
            endpoint_name="wrong",
            namespace="/ayyo/simulation_control",
            request_schema=skill_definition.input_schema,
            response_schema=skill_definition.output_schema,
            timeout_ms=skill_definition.timeout_ms,
            availability=RosEndpointAvailability.AVAILABLE,
        )
        registry = runtime_helpers.runtime_registry(
            skill_definition,
            contract=wrong_endpoint,
        )
        bridge = RuntimeBridge(registry)
        decision = bridge.evaluate(binding)
        with self.assertRaises(RuntimeControlRejectedError) as raised:
            RuntimeSimulationControlBoundary(bridge).authorize(decision, binding)
        self.assertIs(
            ControlFailureCode.RUNTIME_ENDPOINT_MISMATCH,
            raised.exception.code,
        )


if __name__ == "__main__":
    unittest.main()
