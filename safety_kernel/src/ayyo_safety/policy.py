"""Explicit immutable policy for deterministic Safety Kernel evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .canonical import JSONValue
from .errors import InvalidSafetyPolicyError
from .models import (
    MAX_SAFETY_CAPABILITIES,
    SAFETY_POLICY_VERSION,
    ApprovalClass,
    CapabilitySafetyRule,
    HazardClass,
    HazardRule,
    SafetyDisposition,
    SafetyFingerprint,
    SafetyFingerprintKind,
    SafetyPrerequisiteDefinition,
    SafetyPrerequisiteKind,
    SafetyReason,
    _validate_identifier,
    fingerprint_document,
)


_MOTION_PREREQUISITE = SafetyPrerequisiteDefinition(
    kind=SafetyPrerequisiteKind.MOTION_SAFETY_EVALUATION,
    prerequisite_id="motion-safety-evaluation",
    description=(
        "A downstream motion-safety subsystem must evaluate the proposed "
        "movement against current robot and environment state."
    ),
)
_CONTACT_PREREQUISITE = SafetyPrerequisiteDefinition(
    kind=SafetyPrerequisiteKind.CONTACT_SAFETY_EVALUATION,
    prerequisite_id="contact-safety-evaluation",
    description=(
        "A downstream contact-safety subsystem must evaluate the proposed "
        "contact against current robot, human, object, and environment state."
    ),
)


_V1_HAZARD_RULES = (
    HazardRule(
        rule_id="hazard.emergency-safety-critical",
        hazard_class=HazardClass.EMERGENCY_SAFETY_CRITICAL,
        disposition=SafetyDisposition.BLOCKED,
        reason=SafetyReason.EMERGENCY_OPERATION_BLOCKED,
    ),
    HazardRule(
        rule_id="hazard.external-digital-effect",
        hazard_class=HazardClass.EXTERNAL_DIGITAL_EFFECT,
        disposition=SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
        reason=SafetyReason.EXTERNAL_EFFECT_APPROVAL_REQUIRED,
        approval_class=ApprovalClass.EXTERNAL_DIGITAL_ACTION,
    ),
    HazardRule(
        rule_id="hazard.informational-read-only",
        hazard_class=HazardClass.INFORMATIONAL_READ_ONLY,
        disposition=SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
        reason=SafetyReason.INFORMATIONAL_OPERATION_ELIGIBLE,
    ),
    HazardRule(
        rule_id="hazard.internal-non-actuating",
        hazard_class=HazardClass.INTERNAL_NON_ACTUATING,
        disposition=SafetyDisposition.ELIGIBLE_FOR_DOWNSTREAM,
        reason=SafetyReason.INTERNAL_OPERATION_ELIGIBLE,
    ),
    HazardRule(
        rule_id="hazard.physical-contact",
        hazard_class=HazardClass.PHYSICAL_CONTACT,
        disposition=SafetyDisposition.DEFERRED,
        reason=SafetyReason.PHYSICAL_CONTACT_INFORMATION_UNAVAILABLE,
        prerequisites=(_CONTACT_PREREQUISITE,),
    ),
    HazardRule(
        rule_id="hazard.physical-movement",
        hazard_class=HazardClass.PHYSICAL_MOVEMENT,
        disposition=SafetyDisposition.DEFERRED,
        reason=SafetyReason.PHYSICAL_MOVEMENT_INFORMATION_UNAVAILABLE,
        prerequisites=(_MOTION_PREREQUISITE,),
    ),
    HazardRule(
        rule_id="hazard.privileged-high-impact",
        hazard_class=HazardClass.PRIVILEGED_HIGH_IMPACT,
        disposition=SafetyDisposition.EXTERNAL_APPROVAL_REQUIRED,
        reason=SafetyReason.PRIVILEGED_APPROVAL_REQUIRED,
        approval_class=ApprovalClass.PRIVILEGED_HIGH_IMPACT,
    ),
    HazardRule(
        rule_id="hazard.unclassified",
        hazard_class=HazardClass.UNCLASSIFIED,
        disposition=SafetyDisposition.BLOCKED,
        reason=SafetyReason.UNKNOWN_CAPABILITY_CLASS,
    ),
)


def _hazard_rule_document(rule: HazardRule) -> dict[str, JSONValue]:
    return {
        "approval_class": (
            rule.approval_class.value if rule.approval_class is not None else None
        ),
        "disposition": rule.disposition.value,
        "hazard_class": rule.hazard_class.value,
        "prerequisites": [
            {
                "description": prerequisite.description,
                "kind": prerequisite.kind.value,
                "prerequisite_id": prerequisite.prerequisite_id,
            }
            for prerequisite in rule.prerequisites
        ],
        "reason": rule.reason.value,
        "rule_id": rule.rule_id,
    }


def _capability_rule_document(
    rule: CapabilitySafetyRule,
) -> dict[str, JSONValue]:
    return {
        "capability_id": rule.capability_id,
        "hazard_class": rule.hazard_class.value,
        "required_constraint_ids": list(rule.required_constraint_ids),
        "required_precondition_ids": list(rule.required_precondition_ids),
        "rule_id": rule.rule_id,
    }


@dataclass(frozen=True, slots=True, init=False)
class SafetyPolicy:
    """A complete v1 policy whose contents are fixed at construction time."""

    version: str
    capability_rules: tuple[CapabilitySafetyRule, ...]
    hazard_rules: tuple[HazardRule, ...]
    fingerprint: SafetyFingerprint
    _capability_index: Mapping[str, CapabilitySafetyRule]
    _hazard_index: Mapping[HazardClass, HazardRule]

    def __init__(
        self,
        *,
        capability_rules: tuple[CapabilitySafetyRule, ...],
    ) -> None:
        if not isinstance(capability_rules, tuple) or not all(
            isinstance(rule, CapabilitySafetyRule) for rule in capability_rules
        ):
            raise InvalidSafetyPolicyError(
                "capability_rules must be a tuple of CapabilitySafetyRule objects"
            )
        if len(capability_rules) > MAX_SAFETY_CAPABILITIES:
            raise InvalidSafetyPolicyError(
                "capability rules exceed the policy limit"
            )
        ordered_capabilities = tuple(
            sorted(capability_rules, key=lambda rule: rule.capability_id)
        )
        capability_ids = tuple(
            rule.capability_id for rule in ordered_capabilities
        )
        if len(capability_ids) != len(set(capability_ids)):
            raise InvalidSafetyPolicyError(
                "capability rules must use unique capability IDs"
            )
        hazard_rules = tuple(
            sorted(_V1_HAZARD_RULES, key=lambda rule: rule.hazard_class.value)
        )
        hazard_classes = tuple(rule.hazard_class for rule in hazard_rules)
        if set(hazard_classes) != set(HazardClass) or len(hazard_classes) != len(
            HazardClass
        ):
            raise InvalidSafetyPolicyError(
                "the v1 policy must define exactly one rule per hazard class"
            )
        document: dict[str, JSONValue] = {
            "capability_rules": [
                _capability_rule_document(rule)
                for rule in ordered_capabilities
            ],
            "hazard_rules": [
                _hazard_rule_document(rule) for rule in hazard_rules
            ],
            "schema": "ayyo.safety.policy.v1",
            "version": SAFETY_POLICY_VERSION,
        }
        fingerprint = fingerprint_document(
            SafetyFingerprintKind.POLICY,
            document,
            error_type=InvalidSafetyPolicyError,
        )
        object.__setattr__(self, "version", SAFETY_POLICY_VERSION)
        object.__setattr__(self, "capability_rules", ordered_capabilities)
        object.__setattr__(self, "hazard_rules", hazard_rules)
        object.__setattr__(self, "fingerprint", fingerprint)
        object.__setattr__(
            self,
            "_capability_index",
            MappingProxyType(
                {rule.capability_id: rule for rule in ordered_capabilities}
            ),
        )
        object.__setattr__(
            self,
            "_hazard_index",
            MappingProxyType({rule.hazard_class: rule for rule in hazard_rules}),
        )

    def capability_rule(self, capability_id: str) -> CapabilitySafetyRule | None:
        validated = _validate_identifier(
            capability_id,
            field_name="capability_id",
            error_type=InvalidSafetyPolicyError,
        )
        return self._capability_index.get(validated)

    def hazard_rule(self, hazard_class: HazardClass) -> HazardRule:
        if not isinstance(hazard_class, HazardClass):
            raise InvalidSafetyPolicyError("hazard_class must be a HazardClass")
        return self._hazard_index[hazard_class]
