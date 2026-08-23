"""Immutable deterministic registry for explicit skill contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .canonical import JSONValue
from .errors import InvalidSkillRegistryError
from .models import (
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillFingerprint,
    SkillFingerprintKind,
    fingerprint_document,
    validate_identifier,
)


MAX_REGISTRY_SKILLS = 256


@dataclass(frozen=True, slots=True, init=False)
class SkillRegistry:
    """A closed registry assembled explicitly; it has no discovery or mutation."""

    version: SemanticVersion
    fingerprint: SkillFingerprint
    _skills: tuple[SkillDefinition, ...]
    _by_id: Mapping[str, SkillDefinition]
    _by_capability: Mapping[str, tuple[SkillDefinition, ...]]

    def __init__(
        self,
        *,
        version: SemanticVersion,
        skills: tuple[SkillDefinition, ...] = (),
    ) -> None:
        if not isinstance(version, SemanticVersion):
            raise InvalidSkillRegistryError(
                "registry version must be a SemanticVersion"
            )
        if not isinstance(skills, tuple) or not all(
            type(skill) is SkillDefinition for skill in skills
        ):
            raise InvalidSkillRegistryError(
                "registry skills must be a tuple of SkillDefinition objects"
            )
        if len(skills) > MAX_REGISTRY_SKILLS:
            raise InvalidSkillRegistryError("registry exceeds the v1 skill limit")
        ordered = tuple(sorted(skills, key=lambda item: item.skill_id))
        identifiers = tuple(item.skill_id for item in ordered)
        if len(identifiers) != len(set(identifiers)):
            raise InvalidSkillRegistryError("registry skill IDs must be unique")
        by_capability: dict[str, list[SkillDefinition]] = {}
        for skill in ordered:
            for capability_id in skill.capability_ids:
                by_capability.setdefault(capability_id, []).append(skill)
        capability_index = {
            capability_id: tuple(
                sorted(definitions, key=lambda item: (item.skill_id, str(item.version)))
            )
            for capability_id, definitions in sorted(by_capability.items())
        }
        document: dict[str, JSONValue] = {
            "schema": "ayyo.skill-manager.registry.v1",
            "skills": [
                {
                    "fingerprint": str(skill.fingerprint),
                    "skill_id": skill.skill_id,
                    "version": str(skill.version),
                }
                for skill in ordered
            ],
            "version": str(version),
        }
        fingerprint = fingerprint_document(
            SkillFingerprintKind.REGISTRY,
            document,
            error_type=InvalidSkillRegistryError,
        )
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "fingerprint", fingerprint)
        object.__setattr__(self, "_skills", ordered)
        object.__setattr__(
            self,
            "_by_id",
            MappingProxyType({skill.skill_id: skill for skill in ordered}),
        )
        object.__setattr__(
            self,
            "_by_capability",
            MappingProxyType(capability_index),
        )

    @property
    def skills(self) -> tuple[SkillDefinition, ...]:
        return self._skills

    def resolve(self, skill_id: str) -> SkillDefinition | None:
        validated = validate_identifier(
            skill_id,
            field_name="skill_id",
            error_type=InvalidSkillRegistryError,
        )
        return self._by_id.get(validated)

    def for_capability(
        self,
        capability_id: str,
        *,
        available_only: bool = False,
    ) -> tuple[SkillDefinition, ...]:
        validated = validate_identifier(
            capability_id,
            field_name="capability_id",
            error_type=InvalidSkillRegistryError,
        )
        if type(available_only) is not bool:
            raise InvalidSkillRegistryError("available_only must be boolean")
        matches = self._by_capability.get(validated, ())
        if not available_only:
            return matches
        return tuple(
            skill
            for skill in matches
            if skill.availability is SkillAvailability.AVAILABLE
        )

    def availability(self, skill_id: str) -> SkillAvailability | None:
        skill = self.resolve(skill_id)
        return None if skill is None else skill.availability
