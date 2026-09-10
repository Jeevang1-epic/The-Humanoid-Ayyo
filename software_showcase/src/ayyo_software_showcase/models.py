"""Immutable truthful software-showcase contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .canonical import (
    MAX_CAPABILITIES,
    MAX_CLASSIFICATIONS_PER_CAPABILITY,
    MAX_EVIDENCE_PER_CAPABILITY,
    MAX_EVIDENCE_REFERENCES,
    MAX_NON_CLAIMS_PER_CAPABILITY,
    MAX_SERIALIZED_CAPABILITY_BYTES,
    MAX_SERIALIZED_CHECK_BYTES,
    MAX_SERIALIZED_EVIDENCE_BYTES,
    MAX_SERIALIZED_MANIFEST_BYTES,
    MAX_SERIALIZED_REPORT_BYTES,
    MAX_SUMMARY_LENGTH,
    MAX_TITLE_LENGTH,
    assert_size,
    bounded_text,
    fingerprint,
    identifier,
    module_name,
    optional_contract_text,
    semantic_sha256,
    symbol_name,
)
from .errors import (
    ShowcaseCapabilityError,
    ShowcaseEvidenceError,
    ShowcaseManifestError,
    ShowcaseReportError,
)


SHOWCASE_SCHEMA_VERSION = "1.0.0"
SHOWCASE_MANIFEST_SCHEMA_ID = "ayyo.software-showcase.manifest.v1"
SHOWCASE_REPORT_SCHEMA_ID = "ayyo.software-showcase.report.v1"


class ShowcaseEvidenceKind(StrEnum):
    PUBLIC_CONTRACT = "public_contract"
    VERSIONED_SCHEMA = "versioned_schema"


class ShowcaseClassification(StrEnum):
    IMPLEMENTED = "implemented"
    TEST = "test"
    SIMULATION = "simulation"
    DEVELOPMENT_ONLY = "development_only"
    INERT_EVIDENCE_ONLY = "inert_evidence_only"
    NOT_YET_IMPLEMENTED = "not_yet_implemented"
    NOT_PHYSICALLY_VALIDATED = "not_physically_validated"


class ShowcaseNonClaim(StrEnum):
    ACTIVE_OR_INSTALLED_POLICY = "active_or_installed_policy"
    AUTHENTICATED_AUTHORITY = "authenticated_authority"
    AUTOMATIC_LEARNING = "automatic_learning"
    AUTOMATIC_PROMOTION_OR_ROLLBACK = "automatic_promotion_or_rollback"
    COMPLETE_SCENE_KNOWLEDGE = "complete_scene_knowledge"
    DURABLE_PERSISTENCE = "durable_persistence"
    EXECUTED_MOTION = "executed_motion"
    HARDWARE_AUTHORITY = "hardware_authority"
    MODEL_EXECUTION = "model_execution"
    PHYSICAL_SAFETY_CERTIFICATION = "physical_safety_certification"
    PHYSICAL_VALIDATION = "physical_validation"
    POLICY_ACTIVATION = "policy_activation"
    PRODUCTION_ROS_COMMAND = "production_ros_command"
    RUNTIME_DISPATCH = "runtime_dispatch"
    SAFETY_BYPASS = "safety_bypass"


class ShowcaseCheckOutcome(StrEnum):
    SUPPORTED_BY_PUBLIC_CONTRACT = "supported_by_public_contract"
    EXPLICITLY_UNAVAILABLE = "explicitly_unavailable"


def _identity(prefix: str, semantic_document: dict[str, object]) -> tuple[str, str]:
    content_fingerprint = semantic_sha256(f"{prefix}-content", semantic_document)
    identity = semantic_sha256(
        prefix,
        {"content_fingerprint": content_fingerprint},
    )
    return identity, content_fingerprint


def _closed_tuple(
    values: object,
    enum_type: type[StrEnum],
    field_name: str,
    maximum: int,
) -> tuple[StrEnum, ...]:
    if type(values) not in {tuple, list}:
        raise ShowcaseCapabilityError(f"{field_name} must be a bounded sequence")
    items = tuple(values)
    if not items or len(items) > maximum or any(type(item) is not enum_type for item in items):
        raise ShowcaseCapabilityError(f"{field_name} violates its closed v1 contract")
    if len(set(items)) != len(items):
        raise ShowcaseCapabilityError(f"{field_name} contains duplicates")
    return tuple(sorted(items, key=lambda item: item.value))


def _identity_tuple(
    values: object,
    field_name: str,
    maximum: int,
) -> tuple[str, ...]:
    if type(values) not in {tuple, list}:
        raise ShowcaseCapabilityError(f"{field_name} must be a bounded sequence")
    items = tuple(identifier(value, field_name) for value in values)
    if not items or len(items) > maximum or len(set(items)) != len(items):
        raise ShowcaseCapabilityError(f"{field_name} violates its uniqueness bound")
    return tuple(sorted(items))


@dataclass(frozen=True, slots=True)
class ShowcaseEvidenceReference:
    kind: ShowcaseEvidenceKind
    contract_module: str
    contract_symbol: str
    schema_id: str | None
    schema_version: str | None
    provenance_ref: str
    provenance_fingerprint: str
    evidence_id: str = field(init=False)
    evidence_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        try:
            if type(self.kind) is not ShowcaseEvidenceKind:
                raise ShowcaseEvidenceError("evidence kind must use its closed enum")
            object.__setattr__(
                self,
                "contract_module",
                module_name(self.contract_module, "contract_module"),
            )
            object.__setattr__(
                self,
                "contract_symbol",
                symbol_name(self.contract_symbol, "contract_symbol"),
            )
            schema_id = optional_contract_text(self.schema_id, "schema_id")
            schema_version = optional_contract_text(
                self.schema_version, "schema_version"
            )
            if (schema_id is None) != (schema_version is None):
                raise ShowcaseEvidenceError(
                    "schema identity and version must be both present or both absent"
                )
            if self.kind is ShowcaseEvidenceKind.VERSIONED_SCHEMA and schema_id is None:
                raise ShowcaseEvidenceError(
                    "versioned-schema evidence requires an exact schema identity"
                )
            object.__setattr__(self, "schema_id", schema_id)
            object.__setattr__(self, "schema_version", schema_version)
            object.__setattr__(
                self,
                "provenance_ref",
                identifier(self.provenance_ref, "provenance_ref"),
            )
            object.__setattr__(
                self,
                "provenance_fingerprint",
                fingerprint(self.provenance_fingerprint, "provenance_fingerprint"),
            )
            evidence_id, evidence_fingerprint = _identity(
                "showcase-evidence", self.semantic_document()
            )
            object.__setattr__(self, "evidence_id", evidence_id)
            object.__setattr__(self, "evidence_fingerprint", evidence_fingerprint)
            assert_size(
                self.as_dict(),
                MAX_SERIALIZED_EVIDENCE_BYTES,
                "showcase evidence reference",
            )
        except ShowcaseEvidenceError:
            raise
        except (AttributeError, TypeError, ValueError) as error:
            raise ShowcaseEvidenceError(
                "showcase evidence reference violates its v1 contract"
            ) from error

    def semantic_document(self) -> dict[str, object]:
        schema = (
            None
            if self.schema_id is None
            else {"id": self.schema_id, "version": self.schema_version}
        )
        return {
            "contract": {
                "module": self.contract_module,
                "schema": schema,
                "symbol": self.contract_symbol,
            },
            "kind": self.kind.value,
            "provenance": {
                "fingerprint": self.provenance_fingerprint,
                "source_ref": self.provenance_ref,
            },
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            "evidence_fingerprint": self.evidence_fingerprint,
            "evidence_id": self.evidence_id,
        }


def verify_showcase_evidence(reference: object) -> bool:
    if type(reference) is not ShowcaseEvidenceReference:
        return False
    try:
        rebuilt = ShowcaseEvidenceReference(
            kind=reference.kind,
            contract_module=reference.contract_module,
            contract_symbol=reference.contract_symbol,
            schema_id=reference.schema_id,
            schema_version=reference.schema_version,
            provenance_ref=reference.provenance_ref,
            provenance_fingerprint=reference.provenance_fingerprint,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == reference


@dataclass(frozen=True, slots=True)
class ShowcaseCapability:
    sequence_index: int
    capability_id: str
    title: str
    summary: str
    classifications: tuple[ShowcaseClassification, ...]
    evidence_ids: tuple[str, ...]
    does_not_prove: tuple[ShowcaseNonClaim, ...]
    capability_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        try:
            if (
                type(self.sequence_index) is not int
                or self.sequence_index < 0
                or self.sequence_index >= MAX_CAPABILITIES
            ):
                raise ShowcaseCapabilityError(
                    "capability sequence index is outside the v1 bound"
                )
            object.__setattr__(
                self,
                "capability_id",
                identifier(self.capability_id, "capability_id"),
            )
            object.__setattr__(
                self,
                "title",
                bounded_text(self.title, "capability title", MAX_TITLE_LENGTH),
            )
            object.__setattr__(
                self,
                "summary",
                bounded_text(self.summary, "capability summary", MAX_SUMMARY_LENGTH),
            )
            classifications = _closed_tuple(
                self.classifications,
                ShowcaseClassification,
                "classifications",
                MAX_CLASSIFICATIONS_PER_CAPABILITY,
            )
            primary = {
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.NOT_YET_IMPLEMENTED,
            }.intersection(classifications)
            if len(primary) != 1:
                raise ShowcaseCapabilityError(
                    "capability must be exactly implemented or not yet implemented"
                )
            object.__setattr__(self, "classifications", classifications)
            object.__setattr__(
                self,
                "evidence_ids",
                _identity_tuple(
                    self.evidence_ids,
                    "capability evidence identity",
                    MAX_EVIDENCE_PER_CAPABILITY,
                ),
            )
            object.__setattr__(
                self,
                "does_not_prove",
                _closed_tuple(
                    self.does_not_prove,
                    ShowcaseNonClaim,
                    "does_not_prove",
                    MAX_NON_CLAIMS_PER_CAPABILITY,
                ),
            )
            _, capability_fingerprint = _identity(
                "showcase-capability", self.semantic_document()
            )
            object.__setattr__(
                self, "capability_fingerprint", capability_fingerprint
            )
            assert_size(
                self.as_dict(),
                MAX_SERIALIZED_CAPABILITY_BYTES,
                "showcase capability",
            )
        except ShowcaseCapabilityError:
            raise
        except (AttributeError, TypeError, ValueError) as error:
            raise ShowcaseCapabilityError(
                "showcase capability violates its v1 contract"
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "classifications": [item.value for item in self.classifications],
            "does_not_prove": [item.value for item in self.does_not_prove],
            "evidence_ids": list(self.evidence_ids),
            "sequence_index": self.sequence_index,
            "summary": self.summary,
            "title": self.title,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            "capability_fingerprint": self.capability_fingerprint,
        }


def verify_showcase_capability(capability: object) -> bool:
    if type(capability) is not ShowcaseCapability:
        return False
    try:
        rebuilt = ShowcaseCapability(
            sequence_index=capability.sequence_index,
            capability_id=capability.capability_id,
            title=capability.title,
            summary=capability.summary,
            classifications=capability.classifications,
            evidence_ids=capability.evidence_ids,
            does_not_prove=capability.does_not_prove,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == capability


@dataclass(frozen=True, slots=True)
class ShowcaseManifest:
    title: str
    summary: str
    capabilities: tuple[ShowcaseCapability, ...]
    evidence: tuple[ShowcaseEvidenceReference, ...]
    schema_id: str = field(init=False, default=SHOWCASE_MANIFEST_SCHEMA_ID)
    schema_version: str = field(init=False, default=SHOWCASE_SCHEMA_VERSION)
    manifest_id: str = field(init=False)
    manifest_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "title",
                bounded_text(self.title, "manifest title", MAX_TITLE_LENGTH),
            )
            object.__setattr__(
                self,
                "summary",
                bounded_text(self.summary, "manifest summary", MAX_SUMMARY_LENGTH),
            )
            if type(self.capabilities) not in {tuple, list}:
                raise ShowcaseManifestError("capabilities must be a bounded sequence")
            capabilities = tuple(self.capabilities)
            if (
                not capabilities
                or len(capabilities) > MAX_CAPABILITIES
                or any(type(item) is not ShowcaseCapability for item in capabilities)
                or any(not verify_showcase_capability(item) for item in capabilities)
            ):
                raise ShowcaseManifestError("manifest capabilities are invalid")
            if any(item.sequence_index != index for index, item in enumerate(capabilities)):
                raise ShowcaseManifestError(
                    "capability sequence must be contiguous and declared"
                )
            if len({item.capability_id for item in capabilities}) != len(capabilities):
                raise ShowcaseManifestError("manifest contains duplicate capabilities")
            if len({item.capability_fingerprint for item in capabilities}) != len(
                capabilities
            ):
                raise ShowcaseManifestError(
                    "manifest contains duplicate capability evidence"
                )
            if type(self.evidence) not in {tuple, list}:
                raise ShowcaseManifestError("evidence must be a bounded sequence")
            evidence = tuple(self.evidence)
            if (
                not evidence
                or len(evidence) > MAX_EVIDENCE_REFERENCES
                or any(type(item) is not ShowcaseEvidenceReference for item in evidence)
                or any(not verify_showcase_evidence(item) for item in evidence)
            ):
                raise ShowcaseManifestError("manifest evidence is invalid")
            evidence = tuple(sorted(evidence, key=lambda item: item.evidence_id))
            evidence_ids = {item.evidence_id for item in evidence}
            if len(evidence_ids) != len(evidence) or len(
                {item.evidence_fingerprint for item in evidence}
            ) != len(evidence):
                raise ShowcaseManifestError("manifest contains duplicate evidence")
            referenced = {
                evidence_id
                for capability in capabilities
                for evidence_id in capability.evidence_ids
            }
            if referenced != evidence_ids:
                raise ShowcaseManifestError(
                    "manifest evidence must be referenced exactly by its capabilities"
                )
            object.__setattr__(self, "capabilities", capabilities)
            object.__setattr__(self, "evidence", evidence)
            manifest_id, manifest_fingerprint = _identity(
                "software-showcase-manifest", self.semantic_document()
            )
            object.__setattr__(self, "manifest_id", manifest_id)
            object.__setattr__(self, "manifest_fingerprint", manifest_fingerprint)
            assert_size(
                self.as_dict(),
                MAX_SERIALIZED_MANIFEST_BYTES,
                "software showcase manifest",
            )
        except ShowcaseManifestError:
            raise
        except (AttributeError, TypeError, ValueError) as error:
            raise ShowcaseManifestError(
                "software showcase manifest violates its v1 contract"
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            "capabilities": [item.as_dict() for item in self.capabilities],
            "evidence": [item.as_dict() for item in self.evidence],
            "schema": {"id": self.schema_id, "version": self.schema_version},
            "summary": self.summary,
            "title": self.title,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            "manifest_fingerprint": self.manifest_fingerprint,
            "manifest_id": self.manifest_id,
        }


def verify_showcase_manifest(manifest: object) -> bool:
    if type(manifest) is not ShowcaseManifest:
        return False
    try:
        rebuilt = ShowcaseManifest(
            title=manifest.title,
            summary=manifest.summary,
            capabilities=manifest.capabilities,
            evidence=manifest.evidence,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == manifest


@dataclass(frozen=True, slots=True)
class ShowcaseCheck:
    capability_id: str
    capability_fingerprint: str
    outcome: ShowcaseCheckOutcome
    evidence_ids: tuple[str, ...]
    check_id: str = field(init=False)
    check_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "capability_id",
                identifier(self.capability_id, "check capability_id"),
            )
            object.__setattr__(
                self,
                "capability_fingerprint",
                fingerprint(
                    self.capability_fingerprint, "check capability_fingerprint"
                ),
            )
            if type(self.outcome) is not ShowcaseCheckOutcome:
                raise ShowcaseReportError("check outcome must use its closed enum")
            object.__setattr__(
                self,
                "evidence_ids",
                _identity_tuple(
                    self.evidence_ids,
                    "check evidence identity",
                    MAX_EVIDENCE_PER_CAPABILITY,
                ),
            )
            check_id, check_fingerprint = _identity(
                "software-showcase-check", self.semantic_document()
            )
            object.__setattr__(self, "check_id", check_id)
            object.__setattr__(self, "check_fingerprint", check_fingerprint)
            assert_size(
                self.as_dict(), MAX_SERIALIZED_CHECK_BYTES, "software showcase check"
            )
        except ShowcaseReportError:
            raise
        except (AttributeError, TypeError, ValueError) as error:
            raise ShowcaseReportError(
                "software showcase check violates its v1 contract"
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            "capability_fingerprint": self.capability_fingerprint,
            "capability_id": self.capability_id,
            "evidence_ids": list(self.evidence_ids),
            "outcome": self.outcome.value,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            "check_fingerprint": self.check_fingerprint,
            "check_id": self.check_id,
        }


def verify_showcase_check(check: object) -> bool:
    if type(check) is not ShowcaseCheck:
        return False
    try:
        rebuilt = ShowcaseCheck(
            capability_id=check.capability_id,
            capability_fingerprint=check.capability_fingerprint,
            outcome=check.outcome,
            evidence_ids=check.evidence_ids,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == check


@dataclass(frozen=True, slots=True)
class ShowcaseReport:
    manifest: ShowcaseManifest
    checks: tuple[ShowcaseCheck, ...]
    schema_id: str = field(init=False, default=SHOWCASE_REPORT_SCHEMA_ID)
    schema_version: str = field(init=False, default=SHOWCASE_SCHEMA_VERSION)
    report_id: str = field(init=False)
    report_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        try:
            if not verify_showcase_manifest(self.manifest):
                raise ShowcaseReportError("report requires a verified manifest")
            if type(self.checks) not in {tuple, list}:
                raise ShowcaseReportError("checks must be a bounded sequence")
            checks = tuple(self.checks)
            if (
                len(checks) != len(self.manifest.capabilities)
                or any(type(item) is not ShowcaseCheck for item in checks)
                or any(not verify_showcase_check(item) for item in checks)
            ):
                raise ShowcaseReportError("report checks are invalid or incomplete")
            if len({item.check_id for item in checks}) != len(checks):
                raise ShowcaseReportError("report contains duplicate checks")
            for capability, check in zip(self.manifest.capabilities, checks, strict=True):
                expected_outcome = (
                    ShowcaseCheckOutcome.EXPLICITLY_UNAVAILABLE
                    if ShowcaseClassification.NOT_YET_IMPLEMENTED
                    in capability.classifications
                    else ShowcaseCheckOutcome.SUPPORTED_BY_PUBLIC_CONTRACT
                )
                if (
                    check.capability_id != capability.capability_id
                    or check.capability_fingerprint
                    != capability.capability_fingerprint
                    or check.evidence_ids != capability.evidence_ids
                    or check.outcome is not expected_outcome
                ):
                    raise ShowcaseReportError(
                        "report check differs from the exact capability claim"
                    )
            object.__setattr__(self, "checks", checks)
            report_id, report_fingerprint = _identity(
                "software-showcase-report", self.semantic_document()
            )
            object.__setattr__(self, "report_id", report_id)
            object.__setattr__(self, "report_fingerprint", report_fingerprint)
            assert_size(
                self.as_dict(),
                MAX_SERIALIZED_REPORT_BYTES,
                "software showcase report",
            )
        except ShowcaseReportError:
            raise
        except (AttributeError, TypeError, ValueError) as error:
            raise ShowcaseReportError(
                "software showcase report violates its v1 contract"
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            "checks": [item.as_dict() for item in self.checks],
            "manifest": self.manifest.as_dict(),
            "schema": {"id": self.schema_id, "version": self.schema_version},
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            "report_fingerprint": self.report_fingerprint,
            "report_id": self.report_id,
        }
