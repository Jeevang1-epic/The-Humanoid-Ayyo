from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_executive import ExpectedResultCategory
from ayyo_safety import HazardClass
from ayyo_skill_manager import (
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    InvalidSkillRegistryError,
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillLifecycle,
    SkillRegistry,
    ValueSchema,
    ValueType,
)


def skill(
    skill_id: str,
    capability_ids: tuple[str, ...],
    *,
    availability: SkillAvailability = SkillAvailability.AVAILABLE,
) -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        version=SemanticVersion("1.0.0"),
        name=f"Skill {skill_id}",
        description="A deterministic test-only declarative skill.",
        capability_ids=capability_ids,
        backend_id="future.ros.test",
        input_schema=ValueSchema(ValueType.OBJECT),
        output_schema=ValueSchema(ValueType.OBJECT),
        safety_classification=HazardClass.INFORMATIONAL_READ_ONLY,
        expected_result=ExpectedResultCategory.INFORMATION,
        timeout_ms=1_000,
        concurrency_policy=ConcurrencyPolicy.PARALLEL,
        idempotency=IdempotencyClass.IDEMPOTENT,
        failure_semantics=FailureSemantics.NON_RETRYABLE,
        availability=availability,
        lifecycle=SkillLifecycle.VALIDATED,
    )


class SkillRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.primary = skill(
            "context.inspect.primary",
            ("context.inspect", "context.summarize"),
        )
        self.secondary = skill(
            "context.inspect.secondary",
            ("context.inspect",),
            availability=SkillAvailability.DEGRADED,
        )

    def test_exact_resolution_enumeration_and_availability(self) -> None:
        registry = SkillRegistry(
            version=SemanticVersion("1.0.0"),
            skills=(self.secondary, self.primary),
        )
        self.assertIs(self.primary, registry.resolve(self.primary.skill_id))
        self.assertIsNone(registry.resolve("context.missing"))
        self.assertEqual(
            (self.primary, self.secondary),
            registry.skills,
        )
        self.assertEqual(
            SkillAvailability.DEGRADED,
            registry.availability(self.secondary.skill_id),
        )
        self.assertIsNone(registry.availability("context.missing"))

    def test_capability_resolution_is_deterministic(self) -> None:
        registry = SkillRegistry(
            version=SemanticVersion("1.0.0"),
            skills=(self.secondary, self.primary),
        )
        self.assertEqual(
            (self.primary, self.secondary),
            registry.for_capability("context.inspect"),
        )
        self.assertEqual(
            (self.primary,),
            registry.for_capability("context.inspect", available_only=True),
        )
        self.assertEqual((), registry.for_capability("context.unknown"))

    def test_duplicate_skill_ids_are_rejected_without_overwrite(self) -> None:
        duplicate = skill("context.inspect.primary", ("context.other",))
        with self.assertRaises(InvalidSkillRegistryError):
            SkillRegistry(
                version=SemanticVersion("1.0.0"),
                skills=(self.primary, duplicate),
            )

    def test_registry_fingerprint_is_order_independent_and_stable(self) -> None:
        left = SkillRegistry(
            version=SemanticVersion("1.0.0"),
            skills=(self.primary, self.secondary),
        )
        right = SkillRegistry(
            version=SemanticVersion("1.0.0"),
            skills=(self.secondary, self.primary),
        )
        self.assertEqual(left.fingerprint, right.fingerprint)

    def test_registry_fingerprint_binds_version_and_definitions(self) -> None:
        base = SkillRegistry(
            version=SemanticVersion("1.0.0"),
            skills=(self.primary,),
        )
        new_version = SkillRegistry(
            version=SemanticVersion("1.0.1"),
            skills=(self.primary,),
        )
        changed_skill = SkillRegistry(
            version=SemanticVersion("1.0.0"),
            skills=(skill("context.inspect.changed", ("context.inspect",)),),
        )
        self.assertNotEqual(base.fingerprint, new_version.fingerprint)
        self.assertNotEqual(base.fingerprint, changed_skill.fingerprint)

    def test_registry_is_frozen_and_does_not_alias_input(self) -> None:
        source = [self.primary]
        registry = SkillRegistry(
            version=SemanticVersion("1.0.0"),
            skills=tuple(source),
        )
        source.append(self.secondary)
        self.assertEqual((self.primary,), registry.skills)
        with self.assertRaises(FrozenInstanceError):
            registry.version = SemanticVersion("2.0.0")

    def test_invalid_lookup_inputs_fail_typed(self) -> None:
        registry = SkillRegistry(version=SemanticVersion("1.0.0"))
        with self.assertRaises(InvalidSkillRegistryError):
            registry.resolve("Invalid ID")
        with self.assertRaises(InvalidSkillRegistryError):
            registry.for_capability("context.inspect", available_only=1)


if __name__ == "__main__":
    unittest.main()
