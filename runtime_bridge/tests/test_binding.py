from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_skill_manager import SchemaProperty, ValueSchema, ValueType

from ayyo_runtime_bridge import (
    InvalidRuntimeBindingError,
    RuntimeRequest,
    bind_runtime_request,
)

from helpers import proposal, runtime_registry, skill, skill_binding


class RuntimeRequestBindingTest(unittest.TestCase):
    def request(self, *, parameters: dict | None = None) -> RuntimeRequest:
        schema = ValueSchema(
            ValueType.OBJECT,
            properties=(
                SchemaProperty("query", ValueSchema(ValueType.STRING)),
            ),
        )
        definition = skill(input_schema=schema)
        result = skill_binding(
            definition,
            source_proposal=proposal(parameters=parameters or {"query": "status"}),
        )
        self.assertIsNotNone(result.invocation)
        return bind_runtime_request(result.invocation, runtime_registry(definition))

    def test_request_retains_complete_upstream_and_endpoint_identity(self) -> None:
        request = self.request()
        invocation = request.invocation
        self.assertEqual(invocation.invocation_id, request.invocation.invocation_id)
        self.assertEqual(
            invocation.source_executive_fingerprint,
            request.invocation.source_executive_fingerprint,
        )
        self.assertEqual(
            invocation.source_safety_fingerprint,
            request.invocation.source_safety_fingerprint,
        )
        self.assertEqual(
            invocation.source_policy_fingerprint,
            request.invocation.source_policy_fingerprint,
        )
        self.assertEqual(
            invocation.selection.registry_fingerprint,
            request.invocation.selection.registry_fingerprint,
        )
        self.assertEqual(
            request.endpoint_binding.endpoint.fingerprint,
            request.endpoint_binding.endpoint.fingerprint,
        )
        self.assertEqual(
            f"runtime-request-{request.fingerprint.digest}",
            request.request_id,
        )

    def test_equivalent_inputs_produce_identical_request(self) -> None:
        self.assertEqual(self.request(), self.request())

    def test_request_fields_are_defensive_and_immutable(self) -> None:
        request = self.request(parameters={"query": "initial"})
        returned = request.request_fields
        returned["query"] = "changed"
        self.assertEqual({"query": "initial"}, request.request_fields)
        with self.assertRaises(FrozenInstanceError):
            request.request_id = "changed"

    def test_approval_required_invocation_cannot_form_dispatch_request(self) -> None:
        request = self.request()
        object.__setattr__(
            request.invocation,
            "status",
            request.invocation.status.EXTERNAL_APPROVAL_REQUIRED,
        )
        with self.assertRaisesRegex(InvalidRuntimeBindingError, "integrity"):
            bind_runtime_request(request.invocation, runtime_registry(request.invocation.skill_definition))

    def test_tampered_parameters_are_rejected_against_invocation_fingerprint(self) -> None:
        request = self.request()
        object.__setattr__(request.invocation, "_parameters", {"query": "tampered"})
        with self.assertRaisesRegex(InvalidRuntimeBindingError, "fingerprint is stale"):
            bind_runtime_request(request.invocation, runtime_registry(request.invocation.skill_definition))

    def test_changed_skill_version_has_no_registered_binding(self) -> None:
        old_definition = skill(version="1.0.0")
        old_result = skill_binding(old_definition)
        new_definition = skill(version="2.0.0")
        with self.assertRaisesRegex(InvalidRuntimeBindingError, "no exact registered"):
            bind_runtime_request(
                old_result.invocation,
                runtime_registry(new_definition),
            )


if __name__ == "__main__":
    unittest.main()
