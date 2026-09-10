"""Pure future-activation eligibility evaluation; grants no activation authority."""

from __future__ import annotations

from .errors import ActivationEligibilityDecisionError
from .models import (
    ActivationEligibilityDecision,
    ActivationEligibilityReason,
    ActivationEligibilityRequest,
    ActivationEligibilityStatus,
    ApprovalDisposition,
    AuthorityVerificationStatus,
    verify_activation_eligibility_request,
)


def evaluate_activation_eligibility(
    request: ActivationEligibilityRequest,
) -> ActivationEligibilityDecision:
    """Evaluate exact explicit evidence; never activate, load, install, or execute."""
    if not verify_activation_eligibility_request(request):
        raise ActivationEligibilityDecisionError(
            'activation eligibility request failed integrity verification'
        )

    reasons: list[ActivationEligibilityReason] = []
    authority_status = request.approval_evidence.authority.verification_status
    if authority_status is AuthorityVerificationStatus.UNVERIFIED:
        reasons.append(ActivationEligibilityReason.AUTHORITY_NOT_EXTERNALLY_VERIFIED)
    elif authority_status is AuthorityVerificationStatus.REVOKED:
        reasons.append(ActivationEligibilityReason.AUTHORITY_REVOKED)

    disposition = request.approval_evidence.disposition
    if disposition is ApprovalDisposition.REJECTED:
        reasons.append(ActivationEligibilityReason.APPROVAL_REJECTED)
    elif disposition is ApprovalDisposition.REVOKED:
        reasons.append(ActivationEligibilityReason.APPROVAL_REVOKED)

    if reasons:
        status = ActivationEligibilityStatus.INELIGIBLE
        canonical_reasons = tuple(sorted(reasons, key=lambda item: item.value))
    else:
        status = ActivationEligibilityStatus.ELIGIBLE_FOR_FUTURE_ACTIVATION
        canonical_reasons = (
            ActivationEligibilityReason.ELIGIBILITY_REQUIREMENTS_SATISFIED,
        )
    return ActivationEligibilityDecision._create(
        request=request,
        status=status,
        reasons=canonical_reasons,
    )


def verify_activation_eligibility_decision(decision: object) -> bool:
    """Verify structure and recompute the authoritative evidence-only result."""
    if type(decision) is not ActivationEligibilityDecision:
        return False
    try:
        rebuilt = ActivationEligibilityDecision._create(
            request=decision.request,
            status=decision.status,
            reasons=decision.reasons,
        )
        authoritative = evaluate_activation_eligibility(decision.request)
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == decision and authoritative == decision
