"""Typed fail-closed errors for the inert approval-eligibility boundary."""


class ApprovalEligibilityError(ValueError):
    """Base error for approval and activation-eligibility failures."""


class ApprovalEligibilityIntegrityError(ApprovalEligibilityError):
    """An artifact failed structural or content verification."""


class AuthorityReferenceError(ApprovalEligibilityError):
    """An externally supplied authority reference violates the v1 contract."""


class ApprovalRequestError(ApprovalEligibilityError):
    """An approval request violates its exact evidence-chain contract."""


class ApprovalEvidenceError(ApprovalEligibilityError):
    """Authority approval evidence is malformed or cross-composed."""


class ActivationEligibilityRequestError(ApprovalEligibilityError):
    """A future-activation eligibility request is invalid or inconsistent."""


class ActivationEligibilityDecisionError(ApprovalEligibilityError):
    """A future-activation eligibility decision violates the v1 contract."""
