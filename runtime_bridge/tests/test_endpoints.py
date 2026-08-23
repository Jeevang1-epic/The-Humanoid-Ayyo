from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_skill_manager import SemanticVersion, ValueSchema, ValueType

from ayyo_runtime_bridge import (
    InvalidRosEndpointError,
    InvalidRuntimeRegistryError,
    RosEndpointAvailability,
    RosEndpointKind,
    RosServiceEndpoint,
    RuntimeEndpointBinding,
    RuntimeEndpointRegistry,
)

from helpers import endpoint, skill


class RosEndpointContractTest(unittest.TestCase):
    def test_service_endpoint_is_immutable_and_fingerprinted(self) -> None:
        contract = endpoint(skill())
        self.assertIs(RosEndpointKind.SERVICE_REQUEST, contract.kind)
        self.assertEqual("/ayyo/runtime/inspect_context", contract.fully_qualified_name)
        with self.assertRaises(FrozenInstanceError):
            contract.endpoint_name = "changed"

    def test_equivalent_endpoint_is_deterministic(self) -> None:
        definition = skill()
        self.assertEqual(endpoint(definition), endpoint(definition))
        self.assertEqual(
            endpoint(definition).fingerprint,
            endpoint(definition).fingerprint,
        )

    def test_endpoint_rejects_invalid_ros_identities(self) -> None:
        definition = skill()
        base = dict(
            endpoint_id="context.inspect.service",
            backend_id=definition.backend_id,
            package_name="ayyo_interfaces",
            interface_name="InspectContext",
            endpoint_name="inspect_context",
            namespace="/ayyo/runtime",
            request_schema=definition.input_schema,
            response_schema=definition.output_schema,
            timeout_ms=1_000,
            availability=RosEndpointAvailability.AVAILABLE,
        )
        for field_name, invalid in (
            ("package_name", "AyyoInterfaces"),
            ("interface_name", "inspect_context"),
            ("endpoint_name", "/arbitrary/service"),
            ("namespace", "relative"),
            ("namespace", "/trailing/"),
        ):
            with self.subTest(field_name=field_name, invalid=invalid):
                arguments = dict(base)
                arguments[field_name] = invalid
                with self.assertRaises(InvalidRosEndpointError):
                    RosServiceEndpoint(**arguments)

    def test_endpoint_requires_object_request_and_response_contracts(self) -> None:
        definition = skill()
        with self.assertRaisesRegex(InvalidRosEndpointError, "non-null objects"):
            RosServiceEndpoint(
                endpoint_id="context.inspect.service",
                backend_id=definition.backend_id,
                package_name="ayyo_interfaces",
                interface_name="InspectContext",
                endpoint_name="inspect_context",
                namespace="/",
                request_schema=ValueSchema(ValueType.STRING),
                response_schema=definition.output_schema,
                timeout_ms=1_000,
                availability=RosEndpointAvailability.AVAILABLE,
            )


class RuntimeEndpointRegistryTest(unittest.TestCase):
    def binding(self, definition=None, contract=None) -> RuntimeEndpointBinding:
        definition = definition or skill()
        contract = contract or endpoint(definition)
        return RuntimeEndpointBinding(
            skill_definition=definition,
            capability_id="context.inspect",
            endpoint=contract,
        )

    def test_binding_rejects_skill_endpoint_disagreement(self) -> None:
        definition = skill()
        wrong_backend = endpoint(skill(backend_id="future.ros.other"))
        with self.assertRaisesRegex(InvalidRuntimeRegistryError, "backend"):
            self.binding(definition, wrong_backend)

        wrong_schema = RosServiceEndpoint(
            endpoint_id="context.inspect.service",
            backend_id=definition.backend_id,
            package_name="ayyo_interfaces",
            interface_name="InspectContext",
            endpoint_name="inspect_context",
            namespace="/ayyo/runtime",
            request_schema=ValueSchema(ValueType.OBJECT, allow_additional_properties=True),
            response_schema=definition.output_schema,
            timeout_ms=1_000,
            availability=RosEndpointAvailability.AVAILABLE,
        )
        with self.assertRaisesRegex(InvalidRuntimeRegistryError, "input"):
            self.binding(definition, wrong_schema)

    def test_registry_resolution_is_exact_and_order_independent(self) -> None:
        first_skill = skill()
        second_skill = skill(
            skill_id="context.read.secondary",
            backend_id="future.ros.read",
            capability_ids=("context.read",),
        )
        first = self.binding(first_skill, endpoint(first_skill))
        second = RuntimeEndpointBinding(
            skill_definition=second_skill,
            capability_id="context.read",
            endpoint=endpoint(
                second_skill,
                endpoint_id="context.read.service",
                endpoint_name="read_context",
            ),
        )
        one = RuntimeEndpointRegistry(
            version=SemanticVersion("1.0.0"),
            bindings=(first, second),
        )
        two = RuntimeEndpointRegistry(
            version=SemanticVersion("1.0.0"),
            bindings=(second, first),
        )
        self.assertEqual(one, two)
        self.assertEqual(one.fingerprint, two.fingerprint)
        self.assertEqual(
            first,
            one.resolve(
                skill_id=first.skill_id,
                skill_version=first.skill_version,
                capability_id=first.capability_id,
                backend_id=first.backend_id,
            ),
        )
        self.assertIsNone(
            one.resolve(
                skill_id=first.skill_id,
                skill_version=SemanticVersion("2.0.0"),
                capability_id=first.capability_id,
                backend_id=first.backend_id,
            )
        )

    def test_registry_rejects_ambiguous_and_duplicate_endpoints(self) -> None:
        binding = self.binding()
        with self.assertRaisesRegex(InvalidRuntimeRegistryError, "ambiguous"):
            RuntimeEndpointRegistry(
                version=SemanticVersion("1.0.0"),
                bindings=(binding, binding),
            )


if __name__ == "__main__":
    unittest.main()
