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
    SkillManagerError,
)

from .canonical import JSONValue
from .endpoints import (
    RosServiceEndpoint,
    rebuild_ros_service_endpoint,
    rebuild_schema_contract,
)
from .errors import InvalidRosEndpointError, InvalidRuntimeRegistryError
from .models import (
    RuntimeFingerprint,
    RuntimeFingerprintKind,
    fingerprint_document,
    validate_identifier,
)


MAX_RUNTIME_BINDINGS = 256


def rebuild_semantic_version(
    version: object,
    *,
    field_name: str,
) -> SemanticVersion:
    if not isinstance(version, SemanticVersion):
        raise InvalidRuntimeRegistryError(f"{field_name} must be a SemanticVersion")
    try:
        rebuilt = SemanticVersion(str(version))
    except (SkillManagerError, InvalidRosEndpointError) as error:
        raise InvalidRuntimeRegistryError(f"{field_name} is invalid") from error
    if rebuilt != version:
        raise InvalidRuntimeRegistryError(f"{field_name} is not canonical")
    return rebuilt


def rebuild_skill_definition(skill: object) -> SkillDefinition:
    """Reconstruct a public Skill contract before accepting it into the allowlist."""

    if type(skill) is not SkillDefinition:
        raise InvalidRuntimeRegistryError(
            "runtime binding requires a public SkillDefinition"
        )
    try:
        rebuilt = SkillDefinition(
            skill_id=skill.skill_id,
            version=rebuild_semantic_version(
                skill.version,
                field_name="skill version",
            ),
            name=skill.name,
            description=skill.description,
            capability_ids=skill.capability_ids,
            backend_id=skill.backend_id,
            input_schema=rebuild_schema_contract(
                skill.input_schema,
                field_name="skill input schema",
            ),
            output_schema=rebuild_schema_contract(
                skill.output_schema,
                field_name="skill output schema",
            ),
            required_context=skill.required_context,
            required_resources=skill.required_resources,
            required_approval_classes=skill.required_approval_classes,
            safety_classification=skill.safety_classification,
            expected_result=skill.expected_result,
            timeout_ms=skill.timeout_ms,
            concurrency_policy=skill.concurrency_policy,
            idempotency=skill.idempotency,
            failure_semantics=skill.failure_semantics,
            availability=skill.availability,
            lifecycle=skill.lifecycle,
            metadata=skill.metadata,
        )
    except SkillManagerError as error:
        raise InvalidRuntimeRegistryError(
            "skill definition failed integrity reconstruction"
        ) from error
    if rebuilt != skill or rebuilt.fingerprint != skill.fingerprint:
        raise InvalidRuntimeRegistryError("skill definition fingerprint is stale")
    return rebuilt


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
        skill_definition = rebuild_skill_definition(skill_definition)
        capability_id = validate_identifier(
            capability_id,
            field_name="runtime binding capability_id",
            error_type=InvalidRuntimeRegistryError,
        )
        try:
            endpoint = rebuild_ros_service_endpoint(endpoint)
        except InvalidRosEndpointError as error:
            raise InvalidRuntimeRegistryError(
                "runtime binding ROS endpoint failed integrity reconstruction"
            ) from error
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
        version = rebuild_semantic_version(
            version,
            field_name="runtime registry version",
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
        skill_version = rebuild_semantic_version(
            skill_version,
            field_name="skill_version",
        )
        return self._by_key.get(
            (skill_id, str(skill_version), capability_id, backend_id)
        )
