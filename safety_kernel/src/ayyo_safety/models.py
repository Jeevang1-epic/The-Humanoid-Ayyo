"""Immutable public models for Safety Kernel policy and decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256

from ayyo_executive import Fingerprint as ExecutiveFingerprint
from ayyo_executive import FingerprintKind as ExecutiveFingerprintKind

from .canonical import JSONValue, canonicalize_json
from .errors import (
    InvalidSafetyPolicyError,
    SafetyDecisionInvariantError,
    StaleSafetyDecisionError,
)


SAFETY_SCHEMA_VERSION = 1
SAFETY_POLICY_VERSION = "ayyo.safety.policy.v1"
MAX_SAFETY_ITEMS = 128
MAX_SAFETY_CAPABILITIES = 256
MAX_SAFETY_STEPS = 64
MAX_SAFETY_DECISION_ITEMS = 512
MAX_SAFETY_AGGREGATE_ITEMS = 20_000
MAX_SAFETY_TEXT_LENGTH = 16_384
MAX_SAFETY_IDENTIFIER_LENGTH = 256
MAX_FINGERPRINT_JSON_NODES = 250_000
MAX_FINGERPRINT_JSON_CHARACTERS = 32_000_000


class SafetyFingerprintKind(StrEnum):
    POLICY = "policy"
    PROPOSAL = "proposal"
    DECISION = "decision"


class SafetyDisposition(StrEnum):
    ELIGIBLE_FOR_DOWNSTREAM = "eligible_for_downstream"
    EXTERNAL_APPROVAL_REQUIRED = "external_approval_required"
    DEFERRED = "deferred"
    BLOCKED = "blocked"


class HazardClass(StrEnum):
    INFORMATIONAL_READ_ONLY = "informational_read_only"
    INTERNAL_NON_ACTUATING = "internal_non_actuating"
    EXTERNAL_DIGITAL_EFFECT = "external_digital_effect"
    PHYSICAL_MOVEMENT = "physical_movement"
    PHYSICAL_CONTACT = "physical_contact"
    PRIVILEGED_HIGH_IMPACT = "privileged_high_impact"
    EMERGENCY_SAFETY_CRITICAL = "emergency_safety_critical"
    UNCLASSIFIED = "unclassified"


class ApprovalClass(StrEnum):
    EXECUTIVE_DECLARED = "executive_declared"
    EXTERNAL_DIGITAL_ACTION = "external_digital_action"
    PRIVILEGED_HIGH_IMPACT = "privileged_high_impact"


class ApprovalSource(StrEnum):
    EXECUTIVE = "executive"
    SAFETY_POLICY = "safety_policy"


class SafetyPrerequisiteKind(StrEnum):
    MOTION_SAFETY_EVALUATION = "motion_safety_evaluation"
    CONTACT_SAFETY_EVALUATION = "contact_safety_evaluation"
    REQUIRED_PRECONDITION = "required_precondition"
    REQUIRED_CONSTRAINT = "required_constraint"
    REQUIRED_CONTEXT = "required_context"
    ASSUMPTION_VERIFICATION = "assumption_verification"


class SafetyReason(StrEnum):
    INFORMATIONAL_OPERATION_ELIGIBLE = "informational_operation_eligible"
    INTERNAL_OPERATION_ELIGIBLE = "internal_operation_eligible"
    EXTERNAL_EFFECT_APPROVAL_REQUIRED = "external_effect_approval_required"
    PRIVILEGED_APPROVAL_REQUIRED = "privileged_approval_required"
    EXECUTIVE_APPROVAL_UNVERIFIED = "executive_approval_unverified"
    PHYSICAL_MOVEMENT_INFORMATION_UNAVAILABLE = (
        "physical_movement_information_unavailable"
    )
    PHYSICAL_CONTACT_INFORMATION_UNAVAILABLE = (
        "physical_contact_information_unavailable"
    )
    EMERGENCY_OPERATION_BLOCKED = "emergency_operation_blocked"
    UNKNOWN_CAPABILITY_CLASS = "unknown_capability_class"
    CAPABILITY_DECLARATION_CONFLICT = "capability_declaration_conflict"
    REQUIRED_SAFETY_METADATA_MISSING = "required_safety_metadata_missing"
    REQUIRED_CONTEXT_UNAVAILABLE = "required_context_unavailable"
    UNVERIFIED_ASSUMPTION = "unverified_assumption"


class SafetyRevalidationStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class SafetyRevalidationReason(StrEnum):
    PROPOSAL_CHANGED = "proposal_changed"
    POLICY_CHANGED = "policy_changed"


_DISPOSITION_RANK = {
    SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM: 0,
    SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED: 1,
    SafetyDisposition.DEFERRED: 2,
    SafetyDisposition.BLOCKED: 3,
}
_REASON_RANK = {reason: index for index, reason in enumerate(SafetyReason)}
_REVALIDATION_RANK = {
    reason: index for index, reason in enumerate(SafetyRevalidationReason)
}
_HAZARD_BASE_REASON = {
    HazardClass.INFORMATIONAL_READ_ONLY: (
        SafetyReason.INFORMATIONAL_OPERATION_ELIGIBLE
    ),
    HazardClass.INTERNAL_NON_ACTUATING: SafetyReason.INTERNAL_OPERATION_ELIGIBLE,
    HazardClass.EXTERNAL_DIGITAL_EFFECT: (
        SafetyReason.EXTERNAL_EFFECT_APPROVAL_REQUIRED
    ),
    HazardClass.PHYSICAL_MOVEMENT: (
        SafetyReason.PHYSICAL_MOVEMENT_INFORMATION_UNAVAILABLE
    ),
    HazardClass.PHYSICAL_CONTACT: (
        SafetyReason.PHYSICAL_CONTACT_INFORMATION_UNAVAILABLE
    ),
    HazardClass.PRIVILEGED_HIGH_IMPACT: SafetyReason.PRIVILEGED_APPROVAL_REQUIRED,
    HazardClass.EMERGENCY_SAFETY_CRITICAL: SafetyReason.EMERGENCY_OPERATION_BLOCKED,
    HazardClass.UNCLASSIFIED: SafetyReason.UNKNOWN_CAPABILITY_CLASS,
}
_HAZARD_MINIMUM_DISPOSITION = {
    HazardClass.INFORMATIONAL_READ_ONLY: SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
    HazardClass.INTERNAL_NON_ACTUATING: SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
    HazardClass.EXTERNAL_DIGITAL_EFFECT: SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
    HazardClass.PHYSICAL_MOVEMENT: SafetyDisposition.DEFERRED,
    HazardClass.PHYSICAL_CONTACT: SafetyDisposition.DEFERRED,
    HazardClass.PRIVILEGED_HIGH_IMPACT: (
        SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED
    ),
    HazardClass.EMERGENCY_SAFETY_CRITICAL: SafetyDisposition.BLOCKED,
    HazardClass.UNCLASSIFIED: SafetyDisposition.BLOCKED,
}


def _validate_text(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception],
) -> str:
    if not isinstance(value, str) or not value:
        raise error_type(f"{field_name} must be a non-empty string")
    if len(value) > MAX_SAFETY_TEXT_LENGTH:
        raise error_type(f"{field_name} exceeds the text length limit")
    if not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise error_type(f"{field_name} must not have surrounding whitespace")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise error_type(f"{field_name} contains invalid Unicode") from error
    return value


def _validate_identifier(
    value: object,
    *,
    field_name: str,
    error_type: type[Exception],
    max_length: int = MAX_SAFETY_IDENTIFIER_LENGTH,
) -> str:
    text = _validate_text(value, field_name=field_name, error_type=error_type)
    if len(text) > max_length:
        raise error_type(f"{field_name} exceeds the identifier length limit")
    if not text[0].isalnum() or any(
        not (character.isalnum() or character in {"-", "_", "."})
        for character in text
    ):
        raise error_type(
            f"{field_name} must use letters, numbers, '.', '-', or '_'"
        )
    return text


@dataclass(frozen=True, slots=True)
class SafetyFingerprint:
    kind: SafetyFingerprintKind
    digest: str
    algorithm: str = "sha256"
    schema_version: int = SAFETY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SafetyFingerprintKind):
            raise SafetyDecisionInvariantError(
                "safety fingerprint kind must be a SafetyFingerprintKind"
            )
        if self.algorithm != "sha256":
            raise SafetyDecisionInvariantError(
                "safety fingerprint algorithm must be sha256"
            )
        if self.schema_version != SAFETY_SCHEMA_VERSION:
            raise SafetyDecisionInvariantError(
                "safety fingerprint schema version is unsupported"
            )
        if (
            not isinstance(self.digest, str)
            or len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise SafetyDecisionInvariantError(
                "safety fingerprint digest must be lowercase SHA-256 hexadecimal"
            )

    def __str__(self) -> str:
        return f"{self.kind.value}:sha256:{self.digest}"


def fingerprint_document(
    kind: SafetyFingerprintKind,
    document: JSONValue,
    *,
    error_type: type[Exception] = SafetyDecisionInvariantError,
) -> SafetyFingerprint:
    canonical = canonicalize_json(
        document,
        field_name=f"{kind.value} fingerprint document",
        error_type=error_type,
        max_nodes=MAX_FINGERPRINT_JSON_NODES,
        max_characters=MAX_FINGERPRINT_JSON_CHARACTERS,
    )
    return SafetyFingerprint(
        kind=kind,
        digest=sha256(canonical.encode("utf-8")).hexdigest(),
    )


def _identifier_tuple(
    values: tuple[str, ...],
    *,
    field_name: str,
    error_type: type[Exception],
    max_identifier_length: int = MAX_SAFETY_IDENTIFIER_LENGTH,
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not all(
        isinstance(value, str) for value in values
    ):
        raise error_type(f"{field_name} must be a tuple of identifiers")
    if len(values) > MAX_SAFETY_ITEMS:
        raise error_type(f"{field_name} exceeds the item limit")
    for value in values:
        _validate_identifier(
            value,
            field_name=field_name,
            error_type=error_type,
            max_length=max_identifier_length,
        )
    ordered = tuple(sorted(set(values)))
    if len(ordered) != len(values):
        raise error_type(f"{field_name} must be unique")
    return ordered


@dataclass(frozen=True, slots=True, init=False)
class CapabilitySafetyRule:
    capability_id: str
    hazard_class: HazardClass
    required_precondition_ids: tuple[str, ...]
    required_constraint_ids: tuple[str, ...]

    def __init__(
        self,
        *,
        capability_id: str,
        hazard_class: HazardClass,
        required_precondition_ids: tuple[str, ...] = (),
        required_constraint_ids: tuple[str, ...] = (),
    ) -> None:
        capability_id = _validate_identifier(
            capability_id,
            field_name="capability_id",
            error_type=InvalidSafetyPolicyError,
        )
        if not isinstance(hazard_class, HazardClass) or hazard_class is (
            HazardClass.UNCLASSIFIED
        ):
            raise InvalidSafetyPolicyError(
                "a capability rule requires an explicit classified hazard"
            )
        preconditions = _identifier_tuple(
            required_precondition_ids,
            field_name="required precondition IDs",
            error_type=InvalidSafetyPolicyError,
        )
        constraints = _identifier_tuple(
            required_constraint_ids,
            field_name="required constraint IDs",
            error_type=InvalidSafetyPolicyError,
        )
        object.__setattr__(self, "capability_id", capability_id)
        object.__setattr__(self, "hazard_class", hazard_class)
        object.__setattr__(self, "required_precondition_ids", preconditions)
        object.__setattr__(self, "required_constraint_ids", constraints)

    @property
    def rule_id(self) -> str:
        return f"capability.{self.capability_id}"


@dataclass(frozen=True, slots=True)
class SafetyPrerequisiteDefinition:
    kind: SafetyPrerequisiteKind
    prerequisite_id: str
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SafetyPrerequisiteKind):
            raise InvalidSafetyPolicyError(
                "prerequisite kind must be a SafetyPrerequisiteKind"
            )
        _validate_identifier(
            self.prerequisite_id,
            field_name="prerequisite_id",
            error_type=InvalidSafetyPolicyError,
        )
        _validate_text(
            self.description,
            field_name="prerequisite description",
            error_type=InvalidSafetyPolicyError,
        )


@dataclass(frozen=True, slots=True)
class HazardRule:
    rule_id: str
    hazard_class: HazardClass
    disposition: SafetyDisposition
    reason: SafetyReason
    approval_class: ApprovalClass | None = None
    prerequisites: tuple[SafetyPrerequisiteDefinition, ...] = ()

    def __post_init__(self) -> None:
        _validate_identifier(
            self.rule_id,
            field_name="hazard rule_id",
            error_type=InvalidSafetyPolicyError,
        )
        if not isinstance(self.hazard_class, HazardClass):
            raise InvalidSafetyPolicyError(
                "hazard rule class must be a HazardClass"
            )
        if not isinstance(self.disposition, SafetyDisposition):
            raise InvalidSafetyPolicyError(
                "hazard rule disposition must be a SafetyDisposition"
            )
        if not isinstance(self.reason, SafetyReason):
            raise InvalidSafetyPolicyError(
                "hazard rule reason must be a SafetyReason"
            )
        if self.approval_class is not None and not isinstance(
            self.approval_class,
            ApprovalClass,
        ):
            raise InvalidSafetyPolicyError(
                "hazard rule approval class is invalid"
            )
        if not isinstance(self.prerequisites, tuple) or not all(
            isinstance(item, SafetyPrerequisiteDefinition)
            for item in self.prerequisites
        ):
            raise InvalidSafetyPolicyError(
                "hazard rule prerequisites must be typed definitions"
            )
        prerequisite_keys = tuple(
            (item.kind.value, item.prerequisite_id) for item in self.prerequisites
        )
        if prerequisite_keys != tuple(sorted(set(prerequisite_keys))):
            raise InvalidSafetyPolicyError(
                "hazard rule prerequisites must be unique and ordered"
            )
        if (
            self.disposition is SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED
        ) != (self.approval_class is not None):
            raise InvalidSafetyPolicyError(
                "approval disposition and approval class must appear together"
            )
        if (self.disposition is SafetyDisposition.DEFERRED) != bool(
            self.prerequisites
        ):
            raise InvalidSafetyPolicyError(
                "deferred hazard rules require explicit prerequisites"
            )


@dataclass(frozen=True, slots=True)
class SafetyApprovalRequirement:
    approval_class: ApprovalClass
    source: ApprovalSource
    requirement_id: str
    description: str
    affected_step_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.approval_class, ApprovalClass):
            raise SafetyDecisionInvariantError("approval class is invalid")
        if not isinstance(self.source, ApprovalSource):
            raise SafetyDecisionInvariantError("approval source is invalid")
        for value, field_name in (
            (self.requirement_id, "approval requirement_id"),
            (self.affected_step_id, "approval affected_step_id"),
        ):
            _validate_identifier(
                value,
                field_name=field_name,
                error_type=SafetyDecisionInvariantError,
            )
        _validate_text(
            self.description,
            field_name="approval description",
            error_type=SafetyDecisionInvariantError,
        )


def _approval_key(
    approval: SafetyApprovalRequirement,
) -> tuple[str, str, str, str]:
    return (
        approval.affected_step_id,
        approval.source.value,
        approval.approval_class.value,
        approval.requirement_id,
    )


@dataclass(frozen=True, slots=True)
class UnresolvedSafetyPrerequisite:
    kind: SafetyPrerequisiteKind
    prerequisite_id: str
    description: str
    affected_step_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SafetyPrerequisiteKind):
            raise SafetyDecisionInvariantError("safety prerequisite kind is invalid")
        for value, field_name in (
            (self.prerequisite_id, "prerequisite_id"),
            (self.affected_step_id, "prerequisite affected_step_id"),
        ):
            _validate_identifier(
                value,
                field_name=field_name,
                error_type=SafetyDecisionInvariantError,
            )
        _validate_text(
            self.description,
            field_name="prerequisite description",
            error_type=SafetyDecisionInvariantError,
        )


def _prerequisite_key(
    prerequisite: UnresolvedSafetyPrerequisite,
) -> tuple[str, str, str]:
    return (
        prerequisite.affected_step_id,
        prerequisite.kind.value,
        prerequisite.prerequisite_id,
    )


def _ordered_objects(
    values: tuple,
    *,
    item_type: type,
    key,
    field_name: str,
) -> tuple:
    if not isinstance(values, tuple) or not all(
        isinstance(value, item_type) for value in values
    ):
        raise SafetyDecisionInvariantError(
            f"{field_name} must contain only {item_type.__name__} objects"
        )
    if len(values) > MAX_SAFETY_DECISION_ITEMS:
        raise SafetyDecisionInvariantError(f"{field_name} exceeds the item limit")
    ordered = tuple(sorted(values, key=key))
    keys = tuple(key(value) for value in ordered)
    if len(keys) != len(set(keys)):
        raise SafetyDecisionInvariantError(f"{field_name} must be unique")
    return ordered


@dataclass(frozen=True, slots=True, init=False)
class SafetyStepDecision:
    step_id: str
    capability_id: str
    hazard_class: HazardClass
    disposition: SafetyDisposition
    reason_codes: tuple[SafetyReason, ...]
    triggering_policy_rules: tuple[str, ...]
    required_approvals: tuple[SafetyApprovalRequirement, ...]
    unresolved_prerequisites: tuple[UnresolvedSafetyPrerequisite, ...]

    def __init__(
        self,
        *,
        step_id: str,
        capability_id: str,
        hazard_class: HazardClass,
        disposition: SafetyDisposition,
        reason_codes: tuple[SafetyReason, ...],
        triggering_policy_rules: tuple[str, ...],
        required_approvals: tuple[SafetyApprovalRequirement, ...] = (),
        unresolved_prerequisites: tuple[UnresolvedSafetyPrerequisite, ...] = (),
    ) -> None:
        for value, field_name in (
            (step_id, "step decision step_id"),
            (capability_id, "step decision capability_id"),
        ):
            _validate_identifier(
                value,
                field_name=field_name,
                error_type=SafetyDecisionInvariantError,
            )
        if not isinstance(hazard_class, HazardClass):
            raise SafetyDecisionInvariantError("step hazard class is invalid")
        if not isinstance(disposition, SafetyDisposition):
            raise SafetyDecisionInvariantError("step disposition is invalid")
        if not isinstance(reason_codes, tuple) or not reason_codes or not all(
            isinstance(reason, SafetyReason) for reason in reason_codes
        ):
            raise SafetyDecisionInvariantError(
                "step reasons must be a non-empty typed tuple"
            )
        ordered_reasons = tuple(sorted(set(reason_codes), key=_REASON_RANK.get))
        if reason_codes != ordered_reasons:
            raise SafetyDecisionInvariantError(
                "step reasons must be unique and ordered"
            )
        policy_rules = _identifier_tuple(
            triggering_policy_rules,
            field_name="triggering policy rules",
            error_type=SafetyDecisionInvariantError,
            max_identifier_length=(
                MAX_SAFETY_IDENTIFIER_LENGTH + len("capability.")
            ),
        )
        if not policy_rules:
            raise SafetyDecisionInvariantError(
                "a step decision requires a triggering policy rule"
            )
        approvals = _ordered_objects(
            required_approvals,
            item_type=SafetyApprovalRequirement,
            key=_approval_key,
            field_name="step approval requirements",
        )
        prerequisites = _ordered_objects(
            unresolved_prerequisites,
            item_type=UnresolvedSafetyPrerequisite,
            key=_prerequisite_key,
            field_name="step unresolved prerequisites",
        )
        if any(item.affected_step_id != step_id for item in approvals):
            raise SafetyDecisionInvariantError(
                "step approvals must identify their affected step"
            )
        if any(item.affected_step_id != step_id for item in prerequisites):
            raise SafetyDecisionInvariantError(
                "step prerequisites must identify their affected step"
            )
        if disposition is SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM and (
            approvals or prerequisites
        ):
            raise SafetyDecisionInvariantError(
                "eligible steps cannot retain approval or prerequisite blockers"
            )
        if disposition is SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED and (
            not approvals or prerequisites
        ):
            raise SafetyDecisionInvariantError(
                "approval-required steps need approvals and no stronger blocker"
            )
        if disposition is SafetyDisposition.DEFERRED and not prerequisites:
            raise SafetyDecisionInvariantError(
                "deferred steps need unresolved prerequisites"
            )
        blocking_reasons = {
            SafetyReason.EMERGENCY_OPERATION_BLOCKED,
            SafetyReason.UNKNOWN_CAPABILITY_CLASS,
            SafetyReason.CAPABILITY_DECLARATION_CONFLICT,
            SafetyReason.REQUIRED_SAFETY_METADATA_MISSING,
        }
        if disposition is SafetyDisposition.BLOCKED and not (
            set(reason_codes) & blocking_reasons
        ):
            raise SafetyDecisionInvariantError(
                "blocked steps require an explicit blocking reason"
            )
        if hazard_class is HazardClass.UNCLASSIFIED and (
            disposition is not SafetyDisposition.BLOCKED
            or SafetyReason.UNKNOWN_CAPABILITY_CLASS not in reason_codes
        ):
            raise SafetyDecisionInvariantError(
                "unclassified capabilities must be explicitly blocked"
            )
        if _HAZARD_BASE_REASON[hazard_class] not in reason_codes:
            raise SafetyDecisionInvariantError(
                "step reasons must identify the evaluated hazard rule"
            )
        if _DISPOSITION_RANK[disposition] < _DISPOSITION_RANK[
            _HAZARD_MINIMUM_DISPOSITION[hazard_class]
        ]:
            raise SafetyDecisionInvariantError(
                "a step cannot weaken its hazard class disposition"
            )
        approval_reasons = {
            SafetyReason.EXTERNAL_EFFECT_APPROVAL_REQUIRED,
            SafetyReason.PRIVILEGED_APPROVAL_REQUIRED,
            SafetyReason.EXECUTIVE_APPROVAL_UNVERIFIED,
        }
        if disposition is SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED and not (
            set(reason_codes) & approval_reasons
        ):
            raise SafetyDecisionInvariantError(
                "approval-required steps need an explicit approval reason"
            )
        defer_reasons = {
            SafetyReason.PHYSICAL_MOVEMENT_INFORMATION_UNAVAILABLE,
            SafetyReason.PHYSICAL_CONTACT_INFORMATION_UNAVAILABLE,
            SafetyReason.REQUIRED_CONTEXT_UNAVAILABLE,
            SafetyReason.UNVERIFIED_ASSUMPTION,
        }
        if disposition is SafetyDisposition.DEFERRED and not (
            set(reason_codes) & defer_reasons
        ):
            raise SafetyDecisionInvariantError(
                "deferred steps need an explicit deferral reason"
            )
        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "capability_id", capability_id)
        object.__setattr__(self, "hazard_class", hazard_class)
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "triggering_policy_rules", policy_rules)
        object.__setattr__(self, "required_approvals", approvals)
        object.__setattr__(self, "unresolved_prerequisites", prerequisites)


def _approval_document(approval: SafetyApprovalRequirement) -> dict[str, JSONValue]:
    return {
        "affected_step_id": approval.affected_step_id,
        "approval_class": approval.approval_class.value,
        "description": approval.description,
        "requirement_id": approval.requirement_id,
        "source": approval.source.value,
    }


def _prerequisite_document(
    prerequisite: UnresolvedSafetyPrerequisite,
) -> dict[str, JSONValue]:
    return {
        "affected_step_id": prerequisite.affected_step_id,
        "description": prerequisite.description,
        "kind": prerequisite.kind.value,
        "prerequisite_id": prerequisite.prerequisite_id,
    }


def _step_decision_document(decision: SafetyStepDecision) -> dict[str, JSONValue]:
    return {
        "capability_id": decision.capability_id,
        "disposition": decision.disposition.value,
        "hazard_class": decision.hazard_class.value,
        "reason_codes": [reason.value for reason in decision.reason_codes],
        "required_approvals": [
            _approval_document(item) for item in decision.required_approvals
        ],
        "step_id": decision.step_id,
        "triggering_policy_rules": list(decision.triggering_policy_rules),
        "unresolved_prerequisites": [
            _prerequisite_document(item)
            for item in decision.unresolved_prerequisites
        ],
    }


@dataclass(frozen=True, slots=True, init=False)
class SafetyDecision:
    decision_id: str
    disposition: SafetyDisposition
    reason_codes: tuple[SafetyReason, ...]
    source_decision_id: str
    source_request_id: str
    owner_subject: str
    source_decision_fingerprint: ExecutiveFingerprint
    policy_version: str
    policy_fingerprint: SafetyFingerprint
    proposal_fingerprint: SafetyFingerprint
    decision_fingerprint: SafetyFingerprint
    step_decisions: tuple[SafetyStepDecision, ...]
    required_approvals: tuple[SafetyApprovalRequirement, ...]
    unresolved_prerequisites: tuple[UnresolvedSafetyPrerequisite, ...]

    def __init__(
        self,
        *,
        source_decision_id: str,
        source_request_id: str,
        owner_subject: str,
        source_decision_fingerprint: ExecutiveFingerprint,
        policy_version: str,
        policy_fingerprint: SafetyFingerprint,
        proposal_fingerprint: SafetyFingerprint,
        step_decisions: tuple[SafetyStepDecision, ...],
    ) -> None:
        for value, field_name in (
            (source_decision_id, "source_decision_id"),
            (source_request_id, "source_request_id"),
            (owner_subject, "owner_subject"),
            (policy_version, "policy_version"),
        ):
            _validate_text(
                value,
                field_name=field_name,
                error_type=SafetyDecisionInvariantError,
            )
        if policy_version != SAFETY_POLICY_VERSION:
            raise SafetyDecisionInvariantError(
                "safety decision policy version is unsupported"
            )
        if (
            not isinstance(source_decision_fingerprint, ExecutiveFingerprint)
            or source_decision_fingerprint.kind
            is not ExecutiveFingerprintKind.DECISION
        ):
            raise SafetyDecisionInvariantError(
                "source decision fingerprint is invalid"
            )
        for fingerprint, kind in (
            (policy_fingerprint, SafetyFingerprintKind.POLICY),
            (proposal_fingerprint, SafetyFingerprintKind.PROPOSAL),
        ):
            if not isinstance(fingerprint, SafetyFingerprint) or (
                fingerprint.kind is not kind
            ):
                raise SafetyDecisionInvariantError(
                    f"{kind.value} fingerprint is invalid"
                )
        if not isinstance(step_decisions, tuple) or not step_decisions or not all(
            isinstance(item, SafetyStepDecision) for item in step_decisions
        ):
            raise SafetyDecisionInvariantError(
                "a safety decision requires typed step decisions"
            )
        if len(step_decisions) > MAX_SAFETY_STEPS:
            raise SafetyDecisionInvariantError(
                "step decisions exceed the item limit"
            )
        step_ids = tuple(item.step_id for item in step_decisions)
        if len(step_ids) != len(set(step_ids)):
            raise SafetyDecisionInvariantError("step decision IDs must be unique")
        disposition = max(
            (item.disposition for item in step_decisions),
            key=_DISPOSITION_RANK.get,
        )
        reasons = tuple(
            sorted(
                {
                    reason
                    for item in step_decisions
                    for reason in item.reason_codes
                },
                key=_REASON_RANK.get,
            )
        )
        approvals = tuple(
            sorted(
                {
                    approval
                    for item in step_decisions
                    for approval in item.required_approvals
                },
                key=_approval_key,
            )
        )
        prerequisites = tuple(
            sorted(
                {
                    prerequisite
                    for item in step_decisions
                    for prerequisite in item.unresolved_prerequisites
                },
                key=_prerequisite_key,
            )
        )
        if len(approvals) > MAX_SAFETY_AGGREGATE_ITEMS:
            raise SafetyDecisionInvariantError(
                "decision approval requirements exceed the aggregate limit"
            )
        if len(prerequisites) > MAX_SAFETY_AGGREGATE_ITEMS:
            raise SafetyDecisionInvariantError(
                "decision prerequisites exceed the aggregate limit"
            )
        document: dict[str, JSONValue] = {
            "disposition": disposition.value,
            "owner_subject": owner_subject,
            "policy_fingerprint": str(policy_fingerprint),
            "policy_version": policy_version,
            "proposal_fingerprint": str(proposal_fingerprint),
            "reason_codes": [reason.value for reason in reasons],
            "required_approvals": [
                _approval_document(item) for item in approvals
            ],
            "schema": "ayyo.safety.decision.v1",
            "source_decision_fingerprint": str(source_decision_fingerprint),
            "source_decision_id": source_decision_id,
            "source_request_id": source_request_id,
            "step_decisions": [
                _step_decision_document(item) for item in step_decisions
            ],
            "unresolved_prerequisites": [
                _prerequisite_document(item) for item in prerequisites
            ],
        }
        decision_fingerprint = fingerprint_document(
            SafetyFingerprintKind.DECISION,
            document,
        )
        object.__setattr__(
            self,
            "decision_id",
            f"safety-decision-{decision_fingerprint.digest}",
        )
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "source_decision_id", source_decision_id)
        object.__setattr__(self, "source_request_id", source_request_id)
        object.__setattr__(self, "owner_subject", owner_subject)
        object.__setattr__(
            self,
            "source_decision_fingerprint",
            source_decision_fingerprint,
        )
        object.__setattr__(self, "policy_version", policy_version)
        object.__setattr__(self, "policy_fingerprint", policy_fingerprint)
        object.__setattr__(self, "proposal_fingerprint", proposal_fingerprint)
        object.__setattr__(self, "decision_fingerprint", decision_fingerprint)
        object.__setattr__(self, "step_decisions", step_decisions)
        object.__setattr__(self, "required_approvals", approvals)
        object.__setattr__(self, "unresolved_prerequisites", prerequisites)


@dataclass(frozen=True, slots=True)
class SafetyRevalidationResult:
    decision_id: str
    status: SafetyRevalidationStatus
    reasons: tuple[SafetyRevalidationReason, ...]
    prior_proposal_fingerprint: SafetyFingerprint
    current_proposal_fingerprint: SafetyFingerprint
    prior_policy_fingerprint: SafetyFingerprint
    current_policy_fingerprint: SafetyFingerprint

    def __post_init__(self) -> None:
        _validate_text(
            self.decision_id,
            field_name="revalidation decision_id",
            error_type=SafetyDecisionInvariantError,
        )
        if not isinstance(self.status, SafetyRevalidationStatus):
            raise SafetyDecisionInvariantError("revalidation status is invalid")
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(reason, SafetyRevalidationReason) for reason in self.reasons
        ):
            raise SafetyDecisionInvariantError("revalidation reasons are invalid")
        ordered = tuple(sorted(set(self.reasons), key=_REVALIDATION_RANK.get))
        if self.reasons != ordered:
            raise SafetyDecisionInvariantError(
                "revalidation reasons must be unique and ordered"
            )
        for fingerprint, kind in (
            (self.prior_proposal_fingerprint, SafetyFingerprintKind.PROPOSAL),
            (self.current_proposal_fingerprint, SafetyFingerprintKind.PROPOSAL),
            (self.prior_policy_fingerprint, SafetyFingerprintKind.POLICY),
            (self.current_policy_fingerprint, SafetyFingerprintKind.POLICY),
        ):
            if not isinstance(fingerprint, SafetyFingerprint) or (
                fingerprint.kind is not kind
            ):
                raise SafetyDecisionInvariantError(
                    f"revalidation {kind.value} fingerprint is invalid"
                )
        expected: set[SafetyRevalidationReason] = set()
        if self.prior_proposal_fingerprint != self.current_proposal_fingerprint:
            expected.add(SafetyRevalidationReason.PROPOSAL_CHANGED)
        if self.prior_policy_fingerprint != self.current_policy_fingerprint:
            expected.add(SafetyRevalidationReason.POLICY_CHANGED)
        if set(self.reasons) != expected:
            raise SafetyDecisionInvariantError(
                "revalidation reasons do not match compared fingerprints"
            )
        if (self.status is SafetyRevalidationStatus.CURRENT) != (not expected):
            raise SafetyDecisionInvariantError(
                "revalidation status does not match compared fingerprints"
            )

    def assert_current(self) -> None:
        if self.status is SafetyRevalidationStatus.STALE:
            raise StaleSafetyDecisionError(
                f"safety decision {self.decision_id} is stale: "
                f"{[reason.value for reason in self.reasons]}"
            )
