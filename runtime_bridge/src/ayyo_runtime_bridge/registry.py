"""Immutable allowlist of reviewed Skill-to-ROS endpoint bindings."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ayyo_skill_manager import (
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillFingerprint,
    SkillFingerprintKind,
)

from .canonical import JSONValue
from .endpoints import RosServiceEndpoint
from .errors import InvalidRuntimeRegistryError
from .models import (
    RuntimeFingerprint,
    RuntimeFingerprintKind,
    fingerprint_document,
    validate_identifier,
)


MAX_RUNTIME_BINDINGS = 256


@dataclass(frozen=True, slots=True, init=False)
class RuntimeEndpointBinding:
    """One exact, reviewed Skill contract to ROS endpoint mapping."""

    skill_id: str
    skill_version: SemanticVersion
    skill_fingerprint: SkillFingerprint
    capability_id: str
    backend_id: str
    endpoint: RosServiceEndpoint
    skill_definition: SkillDefinition
    fingerprint: RuntimeFingerprint

    def __init__(
        self,
        *,
        skill_definition: SkillDefinition,
        capability_id: str,
        endpoint: RosServiceEndpoint,
    ) -> None:
        if type(skill_definition) is not SkillDefinition:
            raise InvalidRuntimeRegistryError(
                "runtime binding requires a public SkillDefinition"
            )
        capability_id = validate_identifier(
            capability_id,
            field_name="runtime binding capability_id",
            error_type=InvalidRuntimeRegistryError,
        )
        if type(endpoint) is not RosServiceEndpoint:
            raise InvalidRuntimeRegistryError(
                "runtime binding requires a RosServiceEndpoint"
            )
        if skill_definition.availability is not SkillAvailability.AVAILABLE:
            raise InvalidRuntimeRegistryError(
                "runtime bindings may reference only available skills"
            )
        if capability_id not in skill_definition.capability_ids:
            raise InvalidRuntimeRegistryError(
                "runtime binding capability is absent from the skill contract"
            )
        if skill_definition.backend_id != endpoint.backend_id:
            raise InvalidRuntimeRegistryError(
                "skill and endpoint backend declarations disagree"
            )
        if skill_definition.input_schema != endpoint.request_schema:
            raise InvalidRuntimeRegistryError(
                "skill input and endpoint request schemas disagree"
            )
        if skill_definition.output_schema != endpoint.response_schema:
            raise InvalidRuntimeRegistryError(
                "skill output and endpoint response schemas disagree"
            )
        if endpoint.timeout_ms > skill_definition.timeout_ms:
            raise InvalidRuntimeRegistryError(
                "endpoint timeout cannot exceed the Skill contract timeout"
            )
        document: dict[str, JSONValue] = {
            "backend_id": endpoint.backend_id,
            "capability_id": capability_id,
            "endpoint_fingerprint": str(endpoint.fingerprint),
            "schema": "ayyo.runtime-bridge.endpoint-binding.v1",
            "skill_fingerprint": str(skill_definition.fingerprint),
            "skill_id": skill_definition.skill_id,
            "skill_version": str(skill_definition.version),
        }
        object.__setattr__(self, "skill_id", skill_definition.skill_id)
        object.__setattr__(self, "skill_version", skill_definition.version)
        object.__setattr__(self, "skill_fingerprint", skill_definition.fingerprint)
        object.__setattr__(self, "capability_id", capability_id)
        object.__setattr__(self, "backend_id", endpoint.backend_id)
        object.__setattr__(self, "endpoint", endpoint)
        object.__setattr__(self, "skill_definition", skill_definition)
        object.__setattr__(
            self,
            "fingerprint",
            fingerprint_document(
                RuntimeFingerprintKind.ENDPOINT_BINDING,
                document,
                error_type=InvalidRuntimeRegistryError,
            ),
        )


_BindingKey = tuple[str, str, str, str]


def _binding_key(binding: RuntimeEndpointBinding) -> _BindingKey:
    return (
        binding.skill_id,
        str(binding.skill_version),
        binding.capability_id,
        binding.backend_id,
    )


@dataclass(frozen=True, slots=True, init=False)
class RuntimeEndpointRegistry:
    """Closed, deterministic Runtime Bridge endpoint allowlist."""

    version: SemanticVersion
    fingerprint: RuntimeFingerprint
    _bindings: tuple[RuntimeEndpointBinding, ...]
    _by_key: Mapping[_BindingKey, RuntimeEndpointBinding]

    def __init__(
        self,
        *,
        version: SemanticVersion,
        bindings: tuple[RuntimeEndpointBinding, ...] = (),
    ) -> None:
        if not isinstance(version, SemanticVersion):
            raise InvalidRuntimeRegistryError(
                "runtime registry version must be a SemanticVersion"
            )
        if not isinstance(bindings, tuple) or not all(
            type(binding) is RuntimeEndpointBinding for binding in bindings
        ):
            raise InvalidRuntimeRegistryError(
                "runtime registry bindings must be typed immutable contracts"
            )
        if len(bindings) > MAX_RUNTIME_BINDINGS:
            raise InvalidRuntimeRegistryError("runtime registry exceeds the v1 limit")
        ordered = tuple(sorted(bindings, key=_binding_key))
        keys = tuple(_binding_key(binding) for binding in ordered)
        if len(keys) != len(set(keys)):
            raise InvalidRuntimeRegistryError(
                "runtime registry contains an ambiguous Skill/backend mapping"
            )
        endpoint_ids = tuple(binding.endpoint.endpoint_id for binding in ordered)
        endpoint_names = tuple(
            (
                binding.endpoint.package_name,
                binding.endpoint.interface_name,
                binding.endpoint.fully_qualified_name,
            )
            for binding in ordered
        )
        if len(endpoint_ids) != len(set(endpoint_ids)):
            raise InvalidRuntimeRegistryError("runtime endpoint IDs must be unique")
        if len(endpoint_names) != len(set(endpoint_names)):
            raise InvalidRuntimeRegistryError(
                "runtime ROS endpoint identities must be unique"
            )
        document: dict[str, JSONValue] = {
            "bindings": [str(binding.fingerprint) for binding in ordered],
            "schema": "ayyo.runtime-bridge.endpoint-registry.v1",
            "version": str(version),
        }
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "_bindings", ordered)
        object.__setattr__(self, "_by_key", MappingProxyType(dict(zip(keys, ordered))))
        object.__setattr__(
            self,
            "fingerprint",
            fingerprint_document(
                RuntimeFingerprintKind.REGISTRY,
                document,
                error_type=InvalidRuntimeRegistryError,
            ),
        )

    @property
    def bindings(self) -> tuple[RuntimeEndpointBinding, ...]:
        return self._bindings

    def resolve(
        self,
        *,
        skill_id: str,
        skill_version: SemanticVersion,
        capability_id: str,
        backend_id: str,
    ) -> RuntimeEndpointBinding | None:
        skill_id = validate_identifier(
            skill_id,
            field_name="skill_id",
            error_type=InvalidRuntimeRegistryError,
        )
        capability_id = validate_identifier(
            capability_id,
            field_name="capability_id",
            error_type=InvalidRuntimeRegistryError,
        )
        backend_id = validate_identifier(
            backend_id,
            field_name="backend_id",
            error_type=InvalidRuntimeRegistryError,
        )
        if not isinstance(skill_version, SemanticVersion):
            raise InvalidRuntimeRegistryError("skill_version must be a SemanticVersion")
        return self._by_key.get(
            (skill_id, str(skill_version), capability_id, backend_id)
        )
