"""Immutable public domain models for declarative skill contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import re
from typing import Mapping

from ayyo_executive import ContextRequirement, ExpectedResultCategory
from ayyo_safety import ApprovalClass, HazardClass

from .canonical import JSONValue, canonicalize_json, copy_json
from .errors import InvalidSkillDefinitionError, SkillInvocationInvariantError
from .schema import ValueSchema, ValueType, schema_document, validate_schema_graph


SKILL_SCHEMA_VERSION = 1
MAX_SKILL_ITEMS = 128
MAX_SKILL_TIMEOUT_MS = 86_400_000
MAX_TEXT_LENGTH = 16_384
MAX_IDENTIFIER_LENGTH = 256

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def validate_text(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception],
) -> str:
    if type(value) is not str or not value or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise error_type(f"{field_name} must not have surrounding whitespace")
    if len(value) > MAX_TEXT_LENGTH:
        raise error_type(f"{field_name} exceeds the text length limit")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise error_type(f"{field_name} contains invalid Unicode") from error
    return value


def validate_identifier(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception],
) -> str:
    text = validate_text(value, field_name=field_name, error_type=error_type)
    if len(text) > MAX_IDENTIFIER_LENGTH or _IDENTIFIER_PATTERN.fullmatch(text) is None:
        raise error_type(
            f"{field_name} must be a lowercase ASCII identifier using '.', '-', or '_'"
        )
    return text


@dataclass(frozen=True, slots=True)
class SemanticVersion:
    value: str

    def __post_init__(self) -> None:
        validate_text(
            self.value,
            field_name="semantic version",
            error_type=InvalidSkillDefinitionError,
        )
        match = _SEMVER_PATTERN.fullmatch(self.value)
        if match is None:
            raise InvalidSkillDefinitionError("version must be valid Semantic Versioning")
        prerelease = match.group(4)
        if prerelease is not None:
            for identifier in prerelease.split("."):
                if identifier.isdigit() and len(identifier) > 1 and identifier[0] == "0":
                    raise InvalidSkillDefinitionError(
                        "numeric prerelease identifiers cannot contain leading zeroes"
                    )

    def __str__(self) -> str:
        return self.value


class SkillFingerprintKind(StrEnum):
    SKILL = "skill"
    REGISTRY = "registry"
    SELECTION = "selection"
    INVOCATION = "invocation"


@dataclass(frozen=True, slots=True)
class SkillFingerprint:
    kind: SkillFingerprintKind
    digest: str
    algorithm: str = "sha256"
    schema_version: int = SKILL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SkillFingerprintKind):
            raise SkillInvocationInvariantError("skill fingerprint kind is invalid")
        if self.algorithm != "sha256" or self.schema_version != SKILL_SCHEMA_VERSION:
            raise SkillInvocationInvariantError("skill fingerprint format is unsupported")
        if (
            type(self.digest) is not str
            or len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise SkillInvocationInvariantError(
                "skill fingerprint digest must be lowercase SHA-256 hexadecimal"
            )

    def __str__(self) -> str:
        return f"{self.kind.value}:sha256:{self.digest}"


def fingerprint_document(
    kind: SkillFingerprintKind,
    document: JSONValue,
    *,
    error_type: type[Exception] = SkillInvocationInvariantError,
) -> SkillFingerprint:
    canonical = canonicalize_json(
        document,
        field_name=f"{kind.value} fingerprint document",
        error_type=error_type,
    )
    return SkillFingerprint(kind=kind, digest=sha256(canonical.encode("utf-8")).hexdigest())


class SkillAvailability(StrEnum):
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class SkillLifecycle(StrEnum):
    EXPERIMENTAL = "experimental"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"


class ResourceAccess(StrEnum):
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


class ConcurrencyPolicy(StrEnum):
    PARALLEL = "parallel"
    RESOURCE_GOVERNED = "resource_governed"
    EXCLUSIVE = "exclusive"


class IdempotencyClass(StrEnum):
    IDEMPOTENT = "idempotent"
    CONDITIONALLY_IDEMPOTENT = "conditionally_idempotent"
    NON_IDEMPOTENT = "non_idempotent"


class FailureSemantics(StrEnum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    REQUIRES_REPLAN = "requires_replan"
    REQUIRES_OPERATOR = "requires_operator"
    EMERGENCY_ABORT = "emergency_abort"


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    resource_id: str
    access: ResourceAccess

    def __post_init__(self) -> None:
        validate_identifier(
            self.resource_id,
            field_name="resource_id",
            error_type=InvalidSkillDefinitionError,
        )
        if not isinstance(self.access, ResourceAccess):
            raise InvalidSkillDefinitionError("resource access is invalid")


def _context_key(item: ContextRequirement) -> tuple[str, str]:
    return (item.domain.value, item.predicate)


def _skill_document(skill: SkillDefinition) -> dict[str, JSONValue]:
    return {
        "availability": skill.availability.value,
        "backend_id": skill.backend_id,
        "capability_ids": list(skill.capability_ids),
        "concurrency_policy": skill.concurrency_policy.value,
        "description": skill.description,
        "expected_result": skill.expected_result.value,
        "failure_semantics": skill.failure_semantics.value,
        "idempotency": skill.idempotency.value,
        "input_schema": schema_document(skill.input_schema),
        "lifecycle": skill.lifecycle.value,
        "metadata": skill.metadata,
        "name": skill.name,
        "output_schema": schema_document(skill.output_schema),
        "required_approval_classes": [item.value for item in skill.required_approval_classes],
        "required_context": [
            {"domain": item.domain.value, "predicate": item.predicate}
            for item in skill.required_context
        ],
        "required_resources": [
            {"access": item.access.value, "resource_id": item.resource_id}
            for item in skill.required_resources
        ],
        "safety_classification": skill.safety_classification.value,
        "schema": "ayyo.skill-manager.skill.v1",
        "skill_id": skill.skill_id,
        "timeout_ms": skill.timeout_ms,
        "version": str(skill.version),
    }


@dataclass(frozen=True, slots=True, init=False)
class SkillDefinition:
    skill_id: str
    version: SemanticVersion
    name: str
    description: str
    capability_ids: tuple[str, ...]
    backend_id: str
    input_schema: ValueSchema
    output_schema: ValueSchema
    required_context: tuple[ContextRequirement, ...]
    required_resources: tuple[ResourceRequirement, ...]
    required_approval_classes: tuple[ApprovalClass, ...]
    safety_classification: HazardClass
    expected_result: ExpectedResultCategory
    timeout_ms: int
    concurrency_policy: ConcurrencyPolicy
    idempotency: IdempotencyClass
    failure_semantics: FailureSemantics
    availability: SkillAvailability
    lifecycle: SkillLifecycle
    fingerprint: SkillFingerprint
    _metadata: JSONValue = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        skill_id: str,
        version: SemanticVersion,
        name: str,
        description: str,
        capability_ids: tuple[str, ...],
        backend_id: str,
        input_schema: ValueSchema,
        output_schema: ValueSchema,
        required_context: tuple[ContextRequirement, ...] = (),
        required_resources: tuple[ResourceRequirement, ...] = (),
        required_approval_classes: tuple[ApprovalClass, ...] = (),
        safety_classification: HazardClass,
        expected_result: ExpectedResultCategory,
        timeout_ms: int,
        concurrency_policy: ConcurrencyPolicy,
        idempotency: IdempotencyClass,
        failure_semantics: FailureSemantics,
        availability: SkillAvailability,
        lifecycle: SkillLifecycle,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> None:
        skill_id = validate_identifier(
            skill_id,
            field_name="skill_id",
            error_type=InvalidSkillDefinitionError,
        )
        if not isinstance(version, SemanticVersion):
            raise InvalidSkillDefinitionError("version must be a SemanticVersion")
        name = validate_text(name, field_name="skill name", error_type=InvalidSkillDefinitionError)
        description = validate_text(
            description,
            field_name="skill description",
            error_type=InvalidSkillDefinitionError,
        )
        if not isinstance(capability_ids, tuple) or not capability_ids:
            raise InvalidSkillDefinitionError("a skill requires capability identifiers")
        if len(capability_ids) > MAX_SKILL_ITEMS:
            raise InvalidSkillDefinitionError("skill capabilities exceed the item limit")
        capabilities = tuple(
            sorted(
                validate_identifier(
                    value,
                    field_name="capability_id",
                    error_type=InvalidSkillDefinitionError,
                )
                for value in capability_ids
            )
        )
        if len(capabilities) != len(set(capabilities)):
            raise InvalidSkillDefinitionError("skill capability IDs must be unique")
        backend_id = validate_identifier(
            backend_id,
            field_name="backend_id",
            error_type=InvalidSkillDefinitionError,
        )
        validate_schema_graph(input_schema)
        validate_schema_graph(output_schema)
        if input_schema.value_type is not ValueType.OBJECT or input_schema.nullable:
            raise InvalidSkillDefinitionError("skill input_schema must be a non-null object")
        if not isinstance(required_context, tuple) or not all(
            type(item) is ContextRequirement for item in required_context
        ):
            raise InvalidSkillDefinitionError("required_context must use public context contracts")
        required_context = tuple(sorted(required_context, key=_context_key))
        if len(required_context) > MAX_SKILL_ITEMS or len(required_context) != len(set(required_context)):
            raise InvalidSkillDefinitionError("required_context must be bounded and unique")
        if not isinstance(required_resources, tuple) or not all(
            isinstance(item, ResourceRequirement) for item in required_resources
        ):
            raise InvalidSkillDefinitionError("required_resources must be typed")
        required_resources = tuple(sorted(required_resources, key=lambda item: item.resource_id))
        resource_ids = tuple(item.resource_id for item in required_resources)
        if len(required_resources) > MAX_SKILL_ITEMS or len(resource_ids) != len(set(resource_ids)):
            raise InvalidSkillDefinitionError("resource requirements must be bounded and unique")
        if not isinstance(required_approval_classes, tuple) or not all(
            isinstance(item, ApprovalClass) for item in required_approval_classes
        ):
            raise InvalidSkillDefinitionError("required approval classes are invalid")
        required_approval_classes = tuple(sorted(required_approval_classes, key=lambda item: item.value))
        if len(required_approval_classes) != len(set(required_approval_classes)):
            raise InvalidSkillDefinitionError("required approval classes must be unique")
        if not isinstance(safety_classification, HazardClass) or safety_classification is HazardClass.UNCLASSIFIED:
            raise InvalidSkillDefinitionError("skill safety classification must be explicit")
        if not isinstance(expected_result, ExpectedResultCategory):
            raise InvalidSkillDefinitionError("expected_result is invalid")
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= MAX_SKILL_TIMEOUT_MS:
            raise InvalidSkillDefinitionError("timeout_ms is outside the deterministic v1 bounds")
        for value, field_name, enum_type in (
            (concurrency_policy, "concurrency policy", ConcurrencyPolicy),
            (idempotency, "idempotency", IdempotencyClass),
            (failure_semantics, "failure semantics", FailureSemantics),
            (availability, "availability", SkillAvailability),
            (lifecycle, "lifecycle", SkillLifecycle),
        ):
            if not isinstance(value, enum_type):
                raise InvalidSkillDefinitionError(f"{field_name} is invalid")
        if lifecycle is SkillLifecycle.DEPRECATED and availability in {
            SkillAvailability.AVAILABLE,
            SkillAvailability.DEGRADED,
        }:
            raise InvalidSkillDefinitionError("deprecated skills cannot be available or degraded")
        if concurrency_policy is ConcurrencyPolicy.PARALLEL and any(
            item.access is ResourceAccess.EXCLUSIVE for item in required_resources
        ):
            raise InvalidSkillDefinitionError("parallel skills cannot claim exclusive resources")
        if concurrency_policy is ConcurrencyPolicy.RESOURCE_GOVERNED and not required_resources:
            raise InvalidSkillDefinitionError("resource-governed skills require resources")
        if concurrency_policy is ConcurrencyPolicy.EXCLUSIVE and (
            not required_resources
            or any(item.access is not ResourceAccess.EXCLUSIVE for item in required_resources)
        ):
            raise InvalidSkillDefinitionError("exclusive skills require only exclusive resources")
        metadata_source = {} if metadata is None else metadata
        if type(metadata_source) is not dict:
            raise InvalidSkillDefinitionError("skill metadata must be a plain dictionary")
        metadata_copy = copy_json(
            metadata_source,
            field_name="skill metadata",
            error_type=InvalidSkillDefinitionError,
        )
        assert isinstance(metadata_copy, dict)
        object.__setattr__(self, "skill_id", skill_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "capability_ids", capabilities)
        object.__setattr__(self, "backend_id", backend_id)
        object.__setattr__(self, "input_schema", input_schema)
        object.__setattr__(self, "output_schema", output_schema)
        object.__setattr__(self, "required_context", required_context)
        object.__setattr__(self, "required_resources", required_resources)
        object.__setattr__(self, "required_approval_classes", required_approval_classes)
        object.__setattr__(self, "safety_classification", safety_classification)
        object.__setattr__(self, "expected_result", expected_result)
        object.__setattr__(self, "timeout_ms", timeout_ms)
        object.__setattr__(self, "concurrency_policy", concurrency_policy)
        object.__setattr__(self, "idempotency", idempotency)
        object.__setattr__(self, "failure_semantics", failure_semantics)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "lifecycle", lifecycle)
        object.__setattr__(self, "_metadata", metadata_copy)
        object.__setattr__(
            self,
            "fingerprint",
            fingerprint_document(
                SkillFingerprintKind.SKILL,
                _skill_document(self),
                error_type=InvalidSkillDefinitionError,
            ),
        )

    @property
    def metadata(self) -> dict[str, JSONValue]:
        copied = copy_json(self._metadata, field_name="skill metadata")
        assert isinstance(copied, dict)
        return copied
