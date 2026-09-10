"""Immutable authority, approval-request, and approval-evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ayyo_policy_registry import (
    RegisteredPolicyVersion,
    verify_registered_policy_version,
)

from .canonical import (
    MAX_SERIALIZED_APPROVAL_EVIDENCE_BYTES,
    MAX_SERIALIZED_APPROVAL_REQUEST_BYTES,
    MAX_SERIALIZED_AUTHORITY_BYTES,
    MAX_SERIALIZED_ELIGIBILITY_DECISION_BYTES,
    MAX_SERIALIZED_ELIGIBILITY_REQUEST_BYTES,
    assert_size,
    fingerprint,
    identifier,
    optional_note,
    semantic_sha256,
    semantic_version,
)
from .errors import (
    ActivationEligibilityDecisionError,
    ActivationEligibilityRequestError,
    ApprovalEligibilityIntegrityError,
    ApprovalEvidenceError,
    ApprovalRequestError,
    AuthorityReferenceError,
)


APPROVAL_ELIGIBILITY_SCHEMA_VERSION = '1.0.0'
AUTHORITY_REFERENCE_SCHEMA_ID = 'ayyo.approval-eligibility.authority-reference.v1'
APPROVAL_REQUEST_SCHEMA_ID = 'ayyo.approval-eligibility.approval-request.v1'
AUTHORITY_APPROVAL_EVIDENCE_SCHEMA_ID = (
    'ayyo.approval-eligibility.authority-approval-evidence.v1'
)
ACTIVATION_ELIGIBILITY_REQUEST_SCHEMA_ID = (
    'ayyo.approval-eligibility.activation-eligibility-request.v1'
)
ACTIVATION_ELIGIBILITY_DECISION_SCHEMA_ID = (
    'ayyo.approval-eligibility.activation-eligibility-decision.v1'
)


class AuthorityVerificationStatus(StrEnum):
    UNVERIFIED = 'unverified'
    EXTERNALLY_VERIFIED = 'externally_verified'
    REVOKED = 'revoked'


class ApprovalScope(StrEnum):
    FUTURE_ACTIVATION_REVIEW = 'future_activation_review'


class ApprovalDisposition(StrEnum):
    APPROVED = 'approved'
    REJECTED = 'rejected'
    REVOKED = 'revoked'


class ActivationEligibilityStatus(StrEnum):
    ELIGIBLE_FOR_FUTURE_ACTIVATION = 'eligible_for_future_activation'
    INELIGIBLE = 'ineligible'


class ActivationEligibilityReason(StrEnum):
    ELIGIBILITY_REQUIREMENTS_SATISFIED = 'eligibility_requirements_satisfied'
    AUTHORITY_NOT_EXTERNALLY_VERIFIED = 'authority_not_externally_verified'
    AUTHORITY_REVOKED = 'authority_revoked'
    APPROVAL_REJECTED = 'approval_rejected'
    APPROVAL_REVOKED = 'approval_revoked'


def _identity(identifier_value: str, fingerprint_value: str) -> dict[str, str]:
    return {'fingerprint': fingerprint_value, 'id': identifier_value}


def _set_identity(
    instance: object,
    *,
    prefix: str,
    fingerprint_name: str,
    id_name: str,
    maximum_bytes: int,
    artifact_name: str,
) -> None:
    content_fingerprint = semantic_sha256(f'{prefix}-content', instance.semantic_document())
    object.__setattr__(instance, fingerprint_name, content_fingerprint)
    object.__setattr__(
        instance,
        id_name,
        semantic_sha256(
            prefix,
            {
                'content_fingerprint': content_fingerprint,
                'schema_id': instance.schema_id,
                'schema_version': instance.schema_version,
            },
        ),
    )
    assert_size(instance.as_dict(), maximum_bytes, artifact_name)


def _optional_identity_pair(
    reference: object,
    identity_fingerprint: object,
    field_name: str,
) -> tuple[str | None, str | None]:
    if (reference is None) != (identity_fingerprint is None):
        raise ApprovalEligibilityIntegrityError(
            f'{field_name} reference and fingerprint must be supplied together'
        )
    if reference is None:
        return None, None
    return (
        identifier(reference, f'{field_name}_ref'),
        fingerprint(identity_fingerprint, f'{field_name}_fingerprint'),
    )


@dataclass(frozen=True, slots=True, init=False)
class AuthorityReference:
    schema_id: str
    schema_version: str
    authority_reference_id: str
    authority_reference_fingerprint: str
    authority_id: str
    authority_fingerprint: str
    verification_status: AuthorityVerificationStatus
    verification_provider_ref: str | None
    verification_provider_fingerprint: str | None
    verification_evidence_ref: str | None
    verification_evidence_fingerprint: str | None
    provenance_ref: str
    provenance_fingerprint: str
    note: str | None

    def __init__(
        self,
        *,
        authority_id: str,
        authority_fingerprint: str,
        verification_status: AuthorityVerificationStatus,
        verification_provider_ref: str | None = None,
        verification_provider_fingerprint: str | None = None,
        verification_evidence_ref: str | None = None,
        verification_evidence_fingerprint: str | None = None,
        provenance_ref: str,
        provenance_fingerprint: str,
        note: str | None = None,
    ) -> None:
        self._initialize(
            authority_id=authority_id,
            authority_fingerprint=authority_fingerprint,
            verification_status=verification_status,
            verification_provider_ref=verification_provider_ref,
            verification_provider_fingerprint=verification_provider_fingerprint,
            verification_evidence_ref=verification_evidence_ref,
            verification_evidence_fingerprint=verification_evidence_fingerprint,
            provenance_ref=provenance_ref,
            provenance_fingerprint=provenance_fingerprint,
            note=note,
        )

    @classmethod
    def _from_fields(cls, **fields) -> AuthorityReference:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', AUTHORITY_REFERENCE_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', APPROVAL_ELIGIBILITY_SCHEMA_VERSION)
            object.__setattr__(
                self, 'authority_id', identifier(fields['authority_id'], 'authority_id')
            )
            object.__setattr__(
                self,
                'authority_fingerprint',
                fingerprint(fields['authority_fingerprint'], 'authority_fingerprint'),
            )
            status = fields['verification_status']
            if not isinstance(status, AuthorityVerificationStatus):
                raise AuthorityReferenceError(
                    'verification_status must use its closed enum'
                )
            provider = _optional_identity_pair(
                fields['verification_provider_ref'],
                fields['verification_provider_fingerprint'],
                'verification_provider',
            )
            evidence = _optional_identity_pair(
                fields['verification_evidence_ref'],
                fields['verification_evidence_fingerprint'],
                'verification_evidence',
            )
            if status is AuthorityVerificationStatus.UNVERIFIED:
                if provider != (None, None) or evidence != (None, None):
                    raise AuthorityReferenceError(
                        'unverified authority cannot carry verified-provider evidence'
                    )
            elif provider == (None, None) or evidence == (None, None):
                raise AuthorityReferenceError(
                    'externally verified or revoked authority requires external evidence'
                )
            object.__setattr__(self, 'verification_status', status)
            object.__setattr__(self, 'verification_provider_ref', provider[0])
            object.__setattr__(self, 'verification_provider_fingerprint', provider[1])
            object.__setattr__(self, 'verification_evidence_ref', evidence[0])
            object.__setattr__(self, 'verification_evidence_fingerprint', evidence[1])
            object.__setattr__(
                self, 'provenance_ref', identifier(fields['provenance_ref'], 'provenance_ref')
            )
            object.__setattr__(
                self,
                'provenance_fingerprint',
                fingerprint(fields['provenance_fingerprint'], 'provenance_fingerprint'),
            )
            object.__setattr__(self, 'note', optional_note(fields['note']))
            _set_identity(
                self,
                prefix='authority-reference',
                fingerprint_name='authority_reference_fingerprint',
                id_name='authority_reference_id',
                maximum_bytes=MAX_SERIALIZED_AUTHORITY_BYTES,
                artifact_name='authority reference',
            )
        except AuthorityReferenceError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise AuthorityReferenceError(
                'authority reference violates the v1 contract'
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'authority': _identity(self.authority_id, self.authority_fingerprint),
            'note': self.note,
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'verification': {
                'evidence': (
                    {
                        'fingerprint': self.verification_evidence_fingerprint,
                        'source_ref': self.verification_evidence_ref,
                    }
                    if self.verification_evidence_ref is not None
                    else None
                ),
                'provider': (
                    {
                        'fingerprint': self.verification_provider_fingerprint,
                        'source_ref': self.verification_provider_ref,
                    }
                    if self.verification_provider_ref is not None
                    else None
                ),
                'status': self.verification_status.value,
            },
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('authority-reference-content', self.semantic_document())

    def recompute_authority_reference_id(self) -> str:
        return semantic_sha256(
            'authority-reference',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'authority_reference_fingerprint': self.authority_reference_fingerprint,
            'authority_reference_id': self.authority_reference_id,
        }


def verify_authority_reference(authority: object) -> bool:
    if type(authority) is not AuthorityReference:
        return False
    try:
        rebuilt = AuthorityReference._from_fields(
            **{
                name: getattr(authority, name)
                for name in AuthorityReference.__annotations__
                if name
                not in {
                    'schema_id',
                    'schema_version',
                    'authority_reference_id',
                    'authority_reference_fingerprint',
                }
            }
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == authority


@dataclass(frozen=True, slots=True, init=False)
class ApprovalRequest:
    schema_id: str
    schema_version: str
    approval_request_id: str
    approval_request_fingerprint: str
    candidate_id: str
    candidate_fingerprint: str
    candidate_semantic_version: str
    registry_record_id: str
    registry_record_fingerprint: str
    registration_request_id: str
    registration_request_fingerprint: str
    promotion_decision_id: str
    promotion_decision_fingerprint: str
    promotion_target_stage: str
    authority_reference_id: str
    authority_reference_fingerprint: str
    authority_id: str
    authority_fingerprint: str
    approval_scope: ApprovalScope
    provenance_ref: str
    provenance_fingerprint: str
    note: str | None

    def __init__(
        self,
        *,
        registered_version: RegisteredPolicyVersion,
        authority: AuthorityReference,
        approval_scope: ApprovalScope,
        provenance_ref: str,
        provenance_fingerprint: str,
        note: str | None = None,
    ) -> None:
        if not verify_registered_policy_version(registered_version):
            raise ApprovalRequestError('approval request requires a verified registry record')
        if not verify_authority_reference(authority):
            raise ApprovalRequestError('approval request requires a verified authority reference')
        self._initialize(
            candidate_id=registered_version.candidate_id,
            candidate_fingerprint=registered_version.candidate_fingerprint,
            candidate_semantic_version=registered_version.semantic_version,
            registry_record_id=registered_version.record_id,
            registry_record_fingerprint=registered_version.record_fingerprint,
            registration_request_id=registered_version.registration_request_id,
            registration_request_fingerprint=(
                registered_version.registration_request_fingerprint
            ),
            promotion_decision_id=registered_version.promotion_decision_id,
            promotion_decision_fingerprint=(
                registered_version.promotion_decision_fingerprint
            ),
            promotion_target_stage=registered_version.target_stage.value,
            authority_reference_id=authority.authority_reference_id,
            authority_reference_fingerprint=authority.authority_reference_fingerprint,
            authority_id=authority.authority_id,
            authority_fingerprint=authority.authority_fingerprint,
            approval_scope=approval_scope,
            provenance_ref=provenance_ref,
            provenance_fingerprint=provenance_fingerprint,
            note=note,
        )

    @classmethod
    def _from_fields(cls, **fields) -> ApprovalRequest:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            object.__setattr__(self, 'schema_id', APPROVAL_REQUEST_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', APPROVAL_ELIGIBILITY_SCHEMA_VERSION)
            for name in (
                'candidate_id',
                'registry_record_id',
                'registration_request_id',
                'promotion_decision_id',
                'promotion_target_stage',
                'authority_reference_id',
                'authority_id',
                'provenance_ref',
            ):
                object.__setattr__(self, name, identifier(fields[name], name))
            for name in (
                'candidate_fingerprint',
                'registry_record_fingerprint',
                'registration_request_fingerprint',
                'promotion_decision_fingerprint',
                'authority_reference_fingerprint',
                'authority_fingerprint',
                'provenance_fingerprint',
            ):
                object.__setattr__(self, name, fingerprint(fields[name], name))
            object.__setattr__(
                self,
                'candidate_semantic_version',
                semantic_version(
                    fields['candidate_semantic_version'], 'candidate_semantic_version'
                ),
            )
            scope = fields['approval_scope']
            if not isinstance(scope, ApprovalScope):
                raise ApprovalRequestError('approval_scope must use its closed enum')
            object.__setattr__(self, 'approval_scope', scope)
            object.__setattr__(self, 'note', optional_note(fields['note']))
            _set_identity(
                self,
                prefix='approval-request',
                fingerprint_name='approval_request_fingerprint',
                id_name='approval_request_id',
                maximum_bytes=MAX_SERIALIZED_APPROVAL_REQUEST_BYTES,
                artifact_name='approval request',
            )
        except ApprovalRequestError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ApprovalRequestError('approval request violates the v1 contract') from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'approval_scope': self.approval_scope.value,
            'authority': {
                'identity': _identity(self.authority_id, self.authority_fingerprint),
                'reference': _identity(
                    self.authority_reference_id,
                    self.authority_reference_fingerprint,
                ),
            },
            'candidate': {
                'fingerprint': self.candidate_fingerprint,
                'id': self.candidate_id,
                'semantic_version': self.candidate_semantic_version,
            },
            'note': self.note,
            'promotion': {
                'decision': _identity(
                    self.promotion_decision_id,
                    self.promotion_decision_fingerprint,
                ),
                'target_stage': self.promotion_target_stage,
            },
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'registration_request': _identity(
                self.registration_request_id,
                self.registration_request_fingerprint,
            ),
            'registry_record': _identity(
                self.registry_record_id,
                self.registry_record_fingerprint,
            ),
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('approval-request-content', self.semantic_document())

    def recompute_approval_request_id(self) -> str:
        return semantic_sha256(
            'approval-request',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'approval_request_fingerprint': self.approval_request_fingerprint,
            'approval_request_id': self.approval_request_id,
        }


def verify_approval_request(request: object) -> bool:
    if type(request) is not ApprovalRequest:
        return False
    try:
        rebuilt = ApprovalRequest._from_fields(
            **{
                name: getattr(request, name)
                for name in ApprovalRequest.__annotations__
                if name
                not in {
                    'schema_id',
                    'schema_version',
                    'approval_request_id',
                    'approval_request_fingerprint',
                }
            }
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == request


@dataclass(frozen=True, slots=True, init=False)
class AuthorityApprovalEvidence:
    schema_id: str
    schema_version: str
    approval_evidence_id: str
    approval_evidence_fingerprint: str
    approval_request: ApprovalRequest
    authority: AuthorityReference
    disposition: ApprovalDisposition
    evidence_ref: str
    evidence_fingerprint: str
    note: str | None

    def __init__(
        self,
        *,
        approval_request: ApprovalRequest,
        authority: AuthorityReference,
        disposition: ApprovalDisposition,
        evidence_ref: str,
        evidence_fingerprint: str,
        note: str | None = None,
    ) -> None:
        self._initialize(
            approval_request=approval_request,
            authority=authority,
            disposition=disposition,
            evidence_ref=evidence_ref,
            evidence_fingerprint=evidence_fingerprint,
            note=note,
        )

    @classmethod
    def _from_fields(cls, **fields) -> AuthorityApprovalEvidence:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            request = fields['approval_request']
            authority = fields['authority']
            if not verify_approval_request(request):
                raise ApprovalEvidenceError('approval evidence requires a verified request')
            if not verify_authority_reference(authority):
                raise ApprovalEvidenceError(
                    'approval evidence requires a verified authority reference'
                )
            if (
                request.authority_reference_id,
                request.authority_reference_fingerprint,
                request.authority_id,
                request.authority_fingerprint,
            ) != (
                authority.authority_reference_id,
                authority.authority_reference_fingerprint,
                authority.authority_id,
                authority.authority_fingerprint,
            ):
                raise ApprovalEvidenceError(
                    'approval evidence authority differs from its approval request'
                )
            disposition = fields['disposition']
            if not isinstance(disposition, ApprovalDisposition):
                raise ApprovalEvidenceError('disposition must use its closed enum')
            object.__setattr__(self, 'schema_id', AUTHORITY_APPROVAL_EVIDENCE_SCHEMA_ID)
            object.__setattr__(self, 'schema_version', APPROVAL_ELIGIBILITY_SCHEMA_VERSION)
            object.__setattr__(self, 'approval_request', request)
            object.__setattr__(self, 'authority', authority)
            object.__setattr__(self, 'disposition', disposition)
            object.__setattr__(
                self, 'evidence_ref', identifier(fields['evidence_ref'], 'evidence_ref')
            )
            object.__setattr__(
                self,
                'evidence_fingerprint',
                fingerprint(fields['evidence_fingerprint'], 'evidence_fingerprint'),
            )
            object.__setattr__(self, 'note', optional_note(fields['note']))
            _set_identity(
                self,
                prefix='authority-approval-evidence',
                fingerprint_name='approval_evidence_fingerprint',
                id_name='approval_evidence_id',
                maximum_bytes=MAX_SERIALIZED_APPROVAL_EVIDENCE_BYTES,
                artifact_name='authority approval evidence',
            )
        except ApprovalEvidenceError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ApprovalEvidenceError(
                'authority approval evidence violates the v1 contract'
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'approval_request': self.approval_request.as_dict(),
            'authority': self.authority.as_dict(),
            'disposition': self.disposition.value,
            'evidence_source': {
                'fingerprint': self.evidence_fingerprint,
                'source_ref': self.evidence_ref,
            },
            'note': self.note,
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256(
            'authority-approval-evidence-content', self.semantic_document()
        )

    def recompute_approval_evidence_id(self) -> str:
        return semantic_sha256(
            'authority-approval-evidence',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'approval_evidence_fingerprint': self.approval_evidence_fingerprint,
            'approval_evidence_id': self.approval_evidence_id,
        }


def verify_authority_approval_evidence(evidence: object) -> bool:
    if type(evidence) is not AuthorityApprovalEvidence:
        return False
    try:
        rebuilt = AuthorityApprovalEvidence._from_fields(
            approval_request=evidence.approval_request,
            authority=evidence.authority,
            disposition=evidence.disposition,
            evidence_ref=evidence.evidence_ref,
            evidence_fingerprint=evidence.evidence_fingerprint,
            note=evidence.note,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == evidence


def _require_exact_approval_chain(
    registered_version: RegisteredPolicyVersion,
    approval_request: ApprovalRequest,
    approval_evidence: AuthorityApprovalEvidence,
) -> None:
    expected_request_chain = (
        registered_version.candidate_id,
        registered_version.candidate_fingerprint,
        registered_version.semantic_version,
        registered_version.record_id,
        registered_version.record_fingerprint,
        registered_version.registration_request_id,
        registered_version.registration_request_fingerprint,
        registered_version.promotion_decision_id,
        registered_version.promotion_decision_fingerprint,
        registered_version.target_stage.value,
    )
    actual_request_chain = (
        approval_request.candidate_id,
        approval_request.candidate_fingerprint,
        approval_request.candidate_semantic_version,
        approval_request.registry_record_id,
        approval_request.registry_record_fingerprint,
        approval_request.registration_request_id,
        approval_request.registration_request_fingerprint,
        approval_request.promotion_decision_id,
        approval_request.promotion_decision_fingerprint,
        approval_request.promotion_target_stage,
    )
    if actual_request_chain != expected_request_chain:
        raise ActivationEligibilityRequestError(
            'approval request differs from the exact registered policy evidence chain'
        )
    if approval_request.approval_scope is not ApprovalScope.FUTURE_ACTIVATION_REVIEW:
        raise ActivationEligibilityRequestError(
            'approval request does not target the v1 future-activation review scope'
        )
    if approval_evidence.approval_request != approval_request:
        raise ActivationEligibilityRequestError(
            'approval evidence differs from the exact approval request'
        )
    expected_authority_chain = (
        approval_request.authority_reference_id,
        approval_request.authority_reference_fingerprint,
        approval_request.authority_id,
        approval_request.authority_fingerprint,
    )
    actual_authority_chain = (
        approval_evidence.authority.authority_reference_id,
        approval_evidence.authority.authority_reference_fingerprint,
        approval_evidence.authority.authority_id,
        approval_evidence.authority.authority_fingerprint,
    )
    if actual_authority_chain != expected_authority_chain:
        raise ActivationEligibilityRequestError(
            'approval authority differs from the exact approval request authority'
        )


@dataclass(frozen=True, slots=True, init=False)
class ActivationEligibilityRequest:
    schema_id: str
    schema_version: str
    eligibility_request_id: str
    eligibility_request_fingerprint: str
    registered_version: RegisteredPolicyVersion
    approval_request: ApprovalRequest
    approval_evidence: AuthorityApprovalEvidence
    provenance_ref: str
    provenance_fingerprint: str
    note: str | None

    def __init__(
        self,
        *,
        registered_version: RegisteredPolicyVersion,
        approval_request: ApprovalRequest,
        approval_evidence: AuthorityApprovalEvidence,
        provenance_ref: str,
        provenance_fingerprint: str,
        note: str | None = None,
    ) -> None:
        self._initialize(
            registered_version=registered_version,
            approval_request=approval_request,
            approval_evidence=approval_evidence,
            provenance_ref=provenance_ref,
            provenance_fingerprint=provenance_fingerprint,
            note=note,
        )

    @classmethod
    def _from_fields(cls, **fields) -> ActivationEligibilityRequest:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            registered_version = fields['registered_version']
            approval_request = fields['approval_request']
            approval_evidence = fields['approval_evidence']
            if not verify_registered_policy_version(registered_version):
                raise ActivationEligibilityRequestError(
                    'eligibility request requires a verified registry record'
                )
            if not verify_approval_request(approval_request):
                raise ActivationEligibilityRequestError(
                    'eligibility request requires a verified approval request'
                )
            if not verify_authority_approval_evidence(approval_evidence):
                raise ActivationEligibilityRequestError(
                    'eligibility request requires one verified approval evidence object'
                )
            _require_exact_approval_chain(
                registered_version,
                approval_request,
                approval_evidence,
            )
            object.__setattr__(
                self, 'schema_id', ACTIVATION_ELIGIBILITY_REQUEST_SCHEMA_ID
            )
            object.__setattr__(self, 'schema_version', APPROVAL_ELIGIBILITY_SCHEMA_VERSION)
            object.__setattr__(self, 'registered_version', registered_version)
            object.__setattr__(self, 'approval_request', approval_request)
            object.__setattr__(self, 'approval_evidence', approval_evidence)
            object.__setattr__(
                self,
                'provenance_ref',
                identifier(fields['provenance_ref'], 'provenance_ref'),
            )
            object.__setattr__(
                self,
                'provenance_fingerprint',
                fingerprint(fields['provenance_fingerprint'], 'provenance_fingerprint'),
            )
            object.__setattr__(self, 'note', optional_note(fields['note']))
            _set_identity(
                self,
                prefix='activation-eligibility-request',
                fingerprint_name='eligibility_request_fingerprint',
                id_name='eligibility_request_id',
                maximum_bytes=MAX_SERIALIZED_ELIGIBILITY_REQUEST_BYTES,
                artifact_name='activation eligibility request',
            )
        except ActivationEligibilityRequestError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ActivationEligibilityRequestError(
                'activation eligibility request violates the v1 contract'
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'approval_evidence': self.approval_evidence.as_dict(),
            'approval_request': self.approval_request.as_dict(),
            'note': self.note,
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'registered_version': self.registered_version.as_dict(),
            'schema': {'id': self.schema_id, 'version': self.schema_version},
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256(
            'activation-eligibility-request-content', self.semantic_document()
        )

    def recompute_eligibility_request_id(self) -> str:
        return semantic_sha256(
            'activation-eligibility-request',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'eligibility_request_fingerprint': self.eligibility_request_fingerprint,
            'eligibility_request_id': self.eligibility_request_id,
        }


def verify_activation_eligibility_request(request: object) -> bool:
    if type(request) is not ActivationEligibilityRequest:
        return False
    try:
        rebuilt = ActivationEligibilityRequest._from_fields(
            registered_version=request.registered_version,
            approval_request=request.approval_request,
            approval_evidence=request.approval_evidence,
            provenance_ref=request.provenance_ref,
            provenance_fingerprint=request.provenance_fingerprint,
            note=request.note,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == request


@dataclass(frozen=True, slots=True, init=False)
class ActivationEligibilityDecision:
    schema_id: str
    schema_version: str
    eligibility_decision_id: str
    eligibility_decision_fingerprint: str
    request: ActivationEligibilityRequest
    status: ActivationEligibilityStatus
    reasons: tuple[ActivationEligibilityReason, ...]

    @classmethod
    def _create(cls, **fields) -> ActivationEligibilityDecision:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(self, **fields) -> None:
        try:
            request = fields['request']
            if not verify_activation_eligibility_request(request):
                raise ActivationEligibilityDecisionError(
                    'eligibility decision requires a verified request'
                )
            status = fields['status']
            if not isinstance(status, ActivationEligibilityStatus):
                raise ActivationEligibilityDecisionError('status must use its closed enum')
            raw_reasons = fields['reasons']
            if isinstance(raw_reasons, (str, bytes)):
                raise ActivationEligibilityDecisionError(
                    'eligibility reasons must be a bounded sequence'
                )
            try:
                reasons = tuple(raw_reasons)
            except TypeError as error:
                raise ActivationEligibilityDecisionError(
                    'eligibility reasons must be a bounded sequence'
                ) from error
            if (
                not reasons
                or len(reasons) > len(ActivationEligibilityReason)
                or any(not isinstance(item, ActivationEligibilityReason) for item in reasons)
                or len(set(reasons)) != len(reasons)
                or reasons != tuple(sorted(reasons, key=lambda item: item.value))
            ):
                raise ActivationEligibilityDecisionError(
                    'eligibility reasons must be unique canonical closed-enum values'
                )
            satisfied = ActivationEligibilityReason.ELIGIBILITY_REQUIREMENTS_SATISFIED
            if status is ActivationEligibilityStatus.ELIGIBLE_FOR_FUTURE_ACTIVATION:
                if reasons != (satisfied,):
                    raise ActivationEligibilityDecisionError(
                        'eligible decision requires only requirements_satisfied'
                    )
            elif satisfied in reasons:
                raise ActivationEligibilityDecisionError(
                    'ineligible decision cannot claim requirements_satisfied'
                )
            object.__setattr__(
                self, 'schema_id', ACTIVATION_ELIGIBILITY_DECISION_SCHEMA_ID
            )
            object.__setattr__(self, 'schema_version', APPROVAL_ELIGIBILITY_SCHEMA_VERSION)
            object.__setattr__(self, 'request', request)
            object.__setattr__(self, 'status', status)
            object.__setattr__(self, 'reasons', reasons)
            _set_identity(
                self,
                prefix='activation-eligibility-decision',
                fingerprint_name='eligibility_decision_fingerprint',
                id_name='eligibility_decision_id',
                maximum_bytes=MAX_SERIALIZED_ELIGIBILITY_DECISION_BYTES,
                artifact_name='activation eligibility decision',
            )
        except ActivationEligibilityDecisionError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ActivationEligibilityDecisionError(
                'activation eligibility decision violates the v1 contract'
            ) from error

    def semantic_document(self) -> dict[str, object]:
        return {
            'reasons': [item.value for item in self.reasons],
            'request': self.request.as_dict(),
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'status': self.status.value,
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256(
            'activation-eligibility-decision-content', self.semantic_document()
        )

    def recompute_eligibility_decision_id(self) -> str:
        return semantic_sha256(
            'activation-eligibility-decision',
            {
                'content_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'eligibility_decision_fingerprint': self.eligibility_decision_fingerprint,
            'eligibility_decision_id': self.eligibility_decision_id,
        }
