"""Immutable canonical manifest and pure-local catalog integrity checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_json, semantic_sha256
from .catalog import SCENARIO_CATALOG
from .errors import InvalidScenarioManifestError
from .models import (
    DevelopmentScenarioAssertion,
    DevelopmentScenarioDefinition,
    DevelopmentScenarioStep,
    FRAMEWORK_ID,
    FRAMEWORK_VERSION,
    is_semantic_version,
    MAX_ASSERTIONS_PER_SCENARIO,
    MAX_REPORT_TEXT_LENGTH,
    MAX_SCENARIOS_PER_INVOCATION,
    MAX_STEP_TIMEOUT_MS,
    MAX_STEPS_PER_SCENARIO,
    MIN_STEP_TIMEOUT_MS,
    ScenarioAuthority,
    ScenarioCategory,
    ScenarioLaunchProfile,
    ScenarioOperation,
)


MANIFEST_SCHEMA_ID = 'ayyo.developmental-scenario-manifest.v1'
MANIFEST_SCHEMA_VERSION = '1.0.0'
MAX_MANIFEST_JSON_BYTES = 65_536

_CANONICAL_SCENARIO_IDS = tuple(item.scenario_id for item in SCENARIO_CATALOG)


class ScenarioManifestIntegrityReason(StrEnum):
    """Closed reasons returned by expected catalog integrity failures."""

    CATALOG_TYPE_INVALID = 'catalog_type_invalid'
    CATALOG_SIZE_OUT_OF_BOUNDS = 'catalog_size_out_of_bounds'
    SCENARIO_DEFINITION_INVALID = 'scenario_definition_invalid'
    DUPLICATE_SCENARIO_ID = 'duplicate_scenario_id'
    CATALOG_ORDER_INVALID = 'catalog_order_invalid'
    SCENARIO_VERSION_INVALID = 'scenario_version_invalid'
    SCENARIO_CATEGORY_INVALID = 'scenario_category_invalid'
    LAUNCH_PROFILE_INVALID = 'launch_profile_invalid'
    AUTHORITY_INVALID = 'authority_invalid'
    RESOURCE_BOUND_EXCEEDED = 'resource_bound_exceeded'
    DUPLICATE_STEP_ID = 'duplicate_step_id'
    DUPLICATE_ASSERTION_ID = 'duplicate_assertion_id'
    SCENARIO_OPERATION_INVALID = 'scenario_operation_invalid'
    SCENARIO_STRUCTURE_INVALID = 'scenario_structure_invalid'
    SCENARIO_FINGERPRINT_MISMATCH = 'scenario_fingerprint_mismatch'
    MANIFEST_CONTENT_MISMATCH = 'manifest_content_mismatch'
    MANIFEST_FINGERPRINT_MISMATCH = 'manifest_fingerprint_mismatch'


@dataclass(frozen=True, slots=True, init=False)
class DevelopmentScenarioManifestEntry:
    """Bounded public metadata for one reviewed scenario definition."""

    scenario_id: str
    scenario_version: str
    scenario_fingerprint: str
    category: ScenarioCategory
    launch_profile: ScenarioLaunchProfile
    authority: ScenarioAuthority
    expected_safe_outcome: str

    def __init__(self, definition: DevelopmentScenarioDefinition) -> None:
        if type(definition) is not DevelopmentScenarioDefinition:
            raise InvalidScenarioManifestError(
                'manifest entries require exact scenario definitions'
            )
        object.__setattr__(self, 'scenario_id', definition.scenario_id)
        object.__setattr__(self, 'scenario_version', definition.version)
        object.__setattr__(self, 'scenario_fingerprint', definition.fingerprint)
        object.__setattr__(self, 'category', definition.category)
        object.__setattr__(self, 'launch_profile', definition.launch_profile)
        object.__setattr__(self, 'authority', definition.authority)
        object.__setattr__(
            self,
            'expected_safe_outcome',
            definition.expected_safe_outcome,
        )

    def as_dict(self) -> dict[str, object]:
        """Return new JSON-ready entry content in the public manifest schema."""
        return {
            'authority': self.authority.value,
            'category': self.category.value,
            'expected_safe_outcome': self.expected_safe_outcome,
            'launch_profile': self.launch_profile.value,
            'scenario_fingerprint': self.scenario_fingerprint,
            'scenario_id': self.scenario_id,
            'scenario_version': self.scenario_version,
        }


@dataclass(frozen=True, slots=True, init=False)
class DevelopmentScenarioManifest:
    """Canonical bounded manifest for the complete fixed Stage-6 catalog."""

    framework_id: str
    framework_version: str
    manifest_schema_id: str
    manifest_schema_version: str
    entries: tuple[DevelopmentScenarioManifestEntry, ...]
    manifest_fingerprint: str

    def __init__(
        self,
        entries: tuple[DevelopmentScenarioManifestEntry, ...],
    ) -> None:
        if not isinstance(entries, tuple) or not entries:
            raise InvalidScenarioManifestError(
                'manifest entries must be a non-empty immutable tuple'
            )
        if len(entries) > MAX_SCENARIOS_PER_INVOCATION:
            raise InvalidScenarioManifestError('manifest exceeds the scenario bound')
        if not all(type(item) is DevelopmentScenarioManifestEntry for item in entries):
            raise InvalidScenarioManifestError('manifest contains an invalid entry')
        scenario_ids = tuple(item.scenario_id for item in entries)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise InvalidScenarioManifestError('manifest scenario IDs must be unique')
        if scenario_ids != _CANONICAL_SCENARIO_IDS:
            raise InvalidScenarioManifestError(
                'manifest must contain the complete canonical catalog order'
            )
        object.__setattr__(self, 'framework_id', FRAMEWORK_ID)
        object.__setattr__(self, 'framework_version', FRAMEWORK_VERSION)
        object.__setattr__(self, 'manifest_schema_id', MANIFEST_SCHEMA_ID)
        object.__setattr__(self, 'manifest_schema_version', MANIFEST_SCHEMA_VERSION)
        object.__setattr__(self, 'entries', entries)
        document = self.semantic_document()
        if len(canonical_json(document).encode('utf-8')) > MAX_MANIFEST_JSON_BYTES:
            raise InvalidScenarioManifestError('manifest JSON exceeds the byte bound')
        object.__setattr__(
            self,
            'manifest_fingerprint',
            semantic_sha256('development-scenario-manifest', document),
        )

    def semantic_document(self) -> dict[str, object]:
        """Return new canonical semantic content excluding its derived fingerprint."""
        return {
            'framework_id': self.framework_id,
            'framework_version': self.framework_version,
            'manifest_schema_id': self.manifest_schema_id,
            'manifest_schema_version': self.manifest_schema_version,
            'scenario_count': len(self.entries),
            'scenarios': [item.as_dict() for item in self.entries],
        }

    def recompute_fingerprint(self) -> str:
        """Recompute the manifest identity from canonical semantic content."""
        return semantic_sha256(
            'development-scenario-manifest',
            self.semantic_document(),
        )

    def as_dict(self) -> dict[str, object]:
        """Return the complete public canonical manifest document."""
        document = self.semantic_document()
        document['manifest_fingerprint'] = self.manifest_fingerprint
        return document


@dataclass(frozen=True, slots=True)
class DevelopmentScenarioManifestVerification:
    """Immutable deterministic result of pure-local catalog verification."""

    scenario_count: int
    manifest_fingerprint: str | None
    reasons: tuple[ScenarioManifestIntegrityReason, ...]

    def __post_init__(self) -> None:
        if type(self.scenario_count) is not int or not 0 <= self.scenario_count <= 256:
            raise InvalidScenarioManifestError('verification scenario count is invalid')
        if self.manifest_fingerprint is not None and type(
            self.manifest_fingerprint
        ) is not str:
            raise InvalidScenarioManifestError(
                'verification manifest fingerprint is invalid'
            )
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, ScenarioManifestIntegrityReason) for item in self.reasons
        ):
            raise InvalidScenarioManifestError('verification reasons are invalid')
        if len(self.reasons) != len(set(self.reasons)):
            raise InvalidScenarioManifestError('verification reasons must be unique')

    @property
    def valid(self) -> bool:
        """Return true only when no typed integrity reason was found."""
        return not self.reasons


def build_scenario_manifest(
    catalog: tuple[DevelopmentScenarioDefinition, ...] = SCENARIO_CATALOG,
) -> DevelopmentScenarioManifest:
    """Build one immutable manifest while preserving declared catalog order."""
    if not isinstance(catalog, tuple) or not catalog:
        raise InvalidScenarioManifestError(
            'scenario catalog must be a non-empty immutable tuple'
        )
    return DevelopmentScenarioManifest(
        tuple(DevelopmentScenarioManifestEntry(item) for item in catalog)
    )


def canonical_manifest_json(manifest: DevelopmentScenarioManifest) -> str:
    """Serialize one exact manifest with the shared canonical JSON rules."""
    if type(manifest) is not DevelopmentScenarioManifest:
        raise InvalidScenarioManifestError('canonical output requires a manifest')
    return canonical_json(manifest.as_dict())


def _ordered_reasons(
    findings: set[ScenarioManifestIntegrityReason],
) -> tuple[ScenarioManifestIntegrityReason, ...]:
    return tuple(reason for reason in ScenarioManifestIntegrityReason if reason in findings)


def verify_scenario_catalog(
    catalog: object = SCENARIO_CATALOG,
    *,
    manifest: object | None = None,
) -> DevelopmentScenarioManifestVerification:
    """Verify expected integrity faults without hiding unexpected programmer errors."""
    findings: set[ScenarioManifestIntegrityReason] = set()
    if not isinstance(catalog, tuple):
        findings.add(ScenarioManifestIntegrityReason.CATALOG_TYPE_INVALID)
        return DevelopmentScenarioManifestVerification(
            scenario_count=0,
            manifest_fingerprint=None,
            reasons=_ordered_reasons(findings),
        )
    scenario_count = len(catalog)
    if not 0 < scenario_count <= MAX_SCENARIOS_PER_INVOCATION:
        findings.add(ScenarioManifestIntegrityReason.CATALOG_SIZE_OUT_OF_BOUNDS)
    if not all(type(item) is DevelopmentScenarioDefinition for item in catalog):
        findings.add(ScenarioManifestIntegrityReason.SCENARIO_DEFINITION_INVALID)
        return DevelopmentScenarioManifestVerification(
            scenario_count=scenario_count,
            manifest_fingerprint=None,
            reasons=_ordered_reasons(findings),
        )

    scenario_ids = tuple(item.scenario_id for item in catalog)
    if len(scenario_ids) != len(set(scenario_ids)):
        findings.add(ScenarioManifestIntegrityReason.DUPLICATE_SCENARIO_ID)
    if scenario_ids != _CANONICAL_SCENARIO_IDS:
        findings.add(ScenarioManifestIntegrityReason.CATALOG_ORDER_INVALID)

    for definition in catalog:
        if not is_semantic_version(definition.version):
            findings.add(ScenarioManifestIntegrityReason.SCENARIO_VERSION_INVALID)
        if not isinstance(definition.category, ScenarioCategory):
            findings.add(ScenarioManifestIntegrityReason.SCENARIO_CATEGORY_INVALID)
        if not isinstance(definition.launch_profile, ScenarioLaunchProfile):
            findings.add(ScenarioManifestIntegrityReason.LAUNCH_PROFILE_INVALID)
        if not isinstance(definition.authority, ScenarioAuthority):
            findings.add(ScenarioManifestIntegrityReason.AUTHORITY_INVALID)
        if (
            type(definition.description) is not str
            or len(definition.description) > MAX_REPORT_TEXT_LENGTH
            or type(definition.expected_safe_outcome) is not str
            or len(definition.expected_safe_outcome) > MAX_REPORT_TEXT_LENGTH
        ):
            findings.add(ScenarioManifestIntegrityReason.RESOURCE_BOUND_EXCEEDED)

        steps_are_typed = isinstance(definition.steps, tuple) and all(
            type(item) is DevelopmentScenarioStep for item in definition.steps
        )
        assertions_are_typed = isinstance(definition.assertions, tuple) and all(
            type(item) is DevelopmentScenarioAssertion
            for item in definition.assertions
        )
        if not steps_are_typed or not assertions_are_typed:
            findings.add(ScenarioManifestIntegrityReason.SCENARIO_STRUCTURE_INVALID)
            continue
        if not 0 < len(definition.steps) <= MAX_STEPS_PER_SCENARIO:
            findings.add(ScenarioManifestIntegrityReason.RESOURCE_BOUND_EXCEEDED)
        if not 0 < len(definition.assertions) <= MAX_ASSERTIONS_PER_SCENARIO:
            findings.add(ScenarioManifestIntegrityReason.RESOURCE_BOUND_EXCEEDED)

        step_ids = tuple(item.step_id for item in definition.steps)
        assertion_ids = tuple(item.assertion_id for item in definition.assertions)
        if len(step_ids) != len(set(step_ids)):
            findings.add(ScenarioManifestIntegrityReason.DUPLICATE_STEP_ID)
        if len(assertion_ids) != len(set(assertion_ids)):
            findings.add(ScenarioManifestIntegrityReason.DUPLICATE_ASSERTION_ID)
        if any(
            not isinstance(item.operation, ScenarioOperation)
            for item in definition.steps
        ):
            findings.add(ScenarioManifestIntegrityReason.SCENARIO_OPERATION_INVALID)
        if any(
            type(item.timeout_ms) is not int
            or not MIN_STEP_TIMEOUT_MS <= item.timeout_ms <= MAX_STEP_TIMEOUT_MS
            for item in definition.steps
        ):
            findings.add(ScenarioManifestIntegrityReason.RESOURCE_BOUND_EXCEEDED)
        if any(
            not isinstance(item.assertion_ids, tuple)
            or not item.assertion_ids
            or len(item.assertion_ids) > MAX_ASSERTIONS_PER_SCENARIO
            or len(item.assertion_ids) != len(set(item.assertion_ids))
            for item in definition.steps
        ):
            findings.add(ScenarioManifestIntegrityReason.SCENARIO_STRUCTURE_INVALID)
        referenced_ids = tuple(
            assertion_id
            for step in definition.steps
            for assertion_id in step.assertion_ids
        )
        if (
            set(referenced_ids) != set(assertion_ids)
            or len(referenced_ids) != len(set(referenced_ids))
        ):
            findings.add(ScenarioManifestIntegrityReason.SCENARIO_STRUCTURE_INVALID)

        can_recompute = (
            is_semantic_version(definition.version)
            and isinstance(definition.category, ScenarioCategory)
            and isinstance(definition.launch_profile, ScenarioLaunchProfile)
            and isinstance(definition.authority, ScenarioAuthority)
            and all(
                isinstance(item.operation, ScenarioOperation)
                for item in definition.steps
            )
        )
        if can_recompute and definition.recompute_fingerprint() != definition.fingerprint:
            findings.add(
                ScenarioManifestIntegrityReason.SCENARIO_FINGERPRINT_MISMATCH
            )

    manifest_fingerprint = None
    can_build_manifest = (
        0 < scenario_count <= MAX_SCENARIOS_PER_INVOCATION
        and len(scenario_ids) == len(set(scenario_ids))
        and scenario_ids == _CANONICAL_SCENARIO_IDS
    )
    if can_build_manifest:
        expected_manifest = build_scenario_manifest(catalog)
        inspected_manifest = expected_manifest if manifest is None else manifest
        if type(inspected_manifest) is not DevelopmentScenarioManifest:
            findings.add(ScenarioManifestIntegrityReason.MANIFEST_CONTENT_MISMATCH)
        else:
            manifest_fingerprint = inspected_manifest.manifest_fingerprint
            if (
                inspected_manifest.framework_id != FRAMEWORK_ID
                or inspected_manifest.framework_version != FRAMEWORK_VERSION
                or inspected_manifest.manifest_schema_id != MANIFEST_SCHEMA_ID
                or inspected_manifest.manifest_schema_version
                != MANIFEST_SCHEMA_VERSION
                or inspected_manifest.entries != expected_manifest.entries
            ):
                findings.add(ScenarioManifestIntegrityReason.MANIFEST_CONTENT_MISMATCH)
            if (
                inspected_manifest.recompute_fingerprint()
                != inspected_manifest.manifest_fingerprint
            ):
                findings.add(
                    ScenarioManifestIntegrityReason.MANIFEST_FINGERPRINT_MISMATCH
                )

    return DevelopmentScenarioManifestVerification(
        scenario_count=scenario_count,
        manifest_fingerprint=manifest_fingerprint,
        reasons=_ordered_reasons(findings),
    )
