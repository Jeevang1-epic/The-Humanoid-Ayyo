from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_executive import ContextRequirement, ExpectedResultCategory
from ayyo_personal_context import ContextDomain
from ayyo_safety import ApprovalClass, HazardClass
from ayyo_skill_manager import (
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    InvalidSchemaError,
    InvalidSkillDefinitionError,
    ResourceAccess,
    ResourceRequirement,
    SchemaProperty,
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillLifecycle,
    ValueSchema,
    ValueType,
)


def object_schema(*properties: SchemaProperty) -> ValueSchema:
    return ValueSchema(ValueType.OBJECT, properties=properties)


def skill(**overrides) -> SkillDefinition:
    arguments = {
        "skill_id": "context.inspect.primary",
        "version": SemanticVersion("1.0.0"),
        "name": "Primary context inspection",
        "description": "Produces bounded informational context output.",
        "capability_ids": ("context.inspect",),
        "backend_id": "future.ros.context",
        "input_schema": object_schema(
            SchemaProperty("key", ValueSchema(ValueType.STRING, min_length=1, max_length=64))
        ),
        "output_schema": object_schema(
            SchemaProperty("value", ValueSchema(ValueType.STRING, nullable=True), required=False)
        ),
        "required_context": (
            ContextRequirement(ContextDomain.SEMANTIC, "profile"),
        ),
        "required_resources": (
            ResourceRequirement("camera", ResourceAccess.SHARED),
        ),
        "required_approval_classes": (),
        "safety_classification": HazardClass.INFORMATIONAL_READ_ONLY,
        "expected_result": ExpectedResultCategory.INFORMATION,
        "timeout_ms": 2_000,
        "concurrency_policy": ConcurrencyPolicy.PARALLEL,
        "idempotency": IdempotencyClass.IDEMPOTENT,
        "failure_semantics": FailureSemantics.NON_RETRYABLE,
        "availability": SkillAvailability.AVAILABLE,
        "lifecycle": SkillLifecycle.VALIDATED,
        "metadata": {"labels": ["read-only"]},
    }
    arguments.update(overrides)
    return SkillDefinition(**arguments)


class SkillModelTest(unittest.TestCase):
    def test_skill_is_frozen_and_metadata_is_defensively_copied(self) -> None:
        metadata = {"labels": ["initial"]}
        definition = skill(metadata=metadata)
        metadata["labels"].append("caller mutation")
        returned = definition.metadata
        returned["labels"].append("output mutation")
        self.assertEqual({"labels": ["initial"]}, definition.metadata)
        with self.assertRaises(FrozenInstanceError):
            definition.name = "changed"

    def test_equivalent_logical_order_produces_same_fingerprint(self) -> None:
        left = skill(
            capability_ids=("context.read", "context.inspect"),
            metadata={"z": 2, "a": {"b": 1}},
        )
        right = skill(
            capability_ids=("context.inspect", "context.read"),
            metadata={"a": {"b": 1}, "z": 2},
        )
        self.assertEqual(left.fingerprint, right.fingerprint)

    def test_semantic_versions_reject_invalid_or_ambiguous_forms(self) -> None:
        for value in ("1", "1.0", "01.0.0", "1.0.0-01", "v1.0.0"):
            with self.subTest(value=value), self.assertRaises(InvalidSkillDefinitionError):
                SemanticVersion(value)

    def test_identifiers_and_duplicates_are_rejected(self) -> None:
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(skill_id="Not Canonical")
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(capability_ids=("context.inspect", "context.inspect"))
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(
                required_resources=(
                    ResourceRequirement("camera", ResourceAccess.SHARED),
                    ResourceRequirement("camera", ResourceAccess.EXCLUSIVE),
                )
            )

    def test_lifecycle_and_availability_contradictions_are_rejected(self) -> None:
        for availability in (SkillAvailability.AVAILABLE, SkillAvailability.DEGRADED):
            with self.subTest(availability=availability), self.assertRaises(
                InvalidSkillDefinitionError
            ):
                skill(lifecycle=SkillLifecycle.DEPRECATED, availability=availability)

    def test_unclassified_safety_contract_is_rejected(self) -> None:
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(safety_classification=HazardClass.UNCLASSIFIED)

    def test_concurrency_resource_contradictions_are_rejected(self) -> None:
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(
                concurrency_policy=ConcurrencyPolicy.PARALLEL,
                required_resources=(
                    ResourceRequirement("camera", ResourceAccess.EXCLUSIVE),
                ),
            )
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(
                concurrency_policy=ConcurrencyPolicy.RESOURCE_GOVERNED,
                required_resources=(),
            )
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(
                concurrency_policy=ConcurrencyPolicy.EXCLUSIVE,
                required_resources=(
                    ResourceRequirement("camera", ResourceAccess.SHARED),
                ),
            )

    def test_schema_rejects_contradictory_shapes_and_duplicates(self) -> None:
        with self.assertRaises(InvalidSchemaError):
            ValueSchema(ValueType.ARRAY)
        with self.assertRaises(InvalidSchemaError):
            ValueSchema(ValueType.STRING, minimum=0)
        property_definition = SchemaProperty("name", ValueSchema(ValueType.STRING))
        with self.assertRaises(InvalidSchemaError):
            object_schema(property_definition, property_definition)
        with self.assertRaises(InvalidSchemaError):
            ValueSchema(ValueType.INTEGER, allowed_values=(1, 1))

    def test_boolean_is_not_an_integer_schema_value(self) -> None:
        with self.assertRaises(InvalidSchemaError):
            ValueSchema(ValueType.INTEGER, allowed_values=(True,))

    def test_timeout_and_input_root_are_bounded(self) -> None:
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(timeout_ms=0)
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(input_schema=ValueSchema(ValueType.STRING))

    def test_approval_classes_are_unique(self) -> None:
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(
                required_approval_classes=(
                    ApprovalClass.EXECUTIVE_DECLARED,
                    ApprovalClass.EXECUTIVE_DECLARED,
                )
            )

    def test_invalid_failure_semantics_are_rejected(self) -> None:
        with self.assertRaises(InvalidSkillDefinitionError):
            skill(failure_semantics="retry")


if __name__ == "__main__":
    unittest.main()
