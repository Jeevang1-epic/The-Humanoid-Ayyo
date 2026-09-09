"""Typed failures for the inert promotion-control contracts."""


class PromotionControlError(Exception):
    """Base error for the transport-neutral promotion-control package."""


class PromotionControlIntegrityError(PromotionControlError, ValueError):
    """A control-plane artifact is invalid, incompatible, or altered."""


class PromotionCriteriaError(PromotionControlIntegrityError):
    """Caller-owned promotion criteria violate the bounded v1 contract."""


class PromotionRequestError(PromotionControlIntegrityError):
    """A candidate promotion request is structurally invalid or altered."""


class PromotionDecisionError(PromotionControlIntegrityError):
    """Promotion evidence cannot be evaluated or verified safely."""


class RollbackControlError(PromotionControlIntegrityError):
    """Known-good or rollback evidence violates the bounded v1 contract."""
