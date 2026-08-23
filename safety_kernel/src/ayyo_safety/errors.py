"""Typed failures for the immutable Safety Kernel."""


class SafetyKernelError(Exception):
    """Base class for Safety Kernel failures."""


class SafetyValidationError(SafetyKernelError, ValueError):
    """Base class for malformed public input."""


class InvalidSafetyPolicyError(SafetyValidationError):
    """A policy or classification violates the v1 safety contract."""


class InvalidSafetyProposalError(SafetyValidationError):
    """An Executive decision is not a structurally valid proposal."""


class SafetyPlanInvariantError(SafetyKernelError):
    """A proposed plan violates Safety Kernel graph or relationship invariants."""


class SafetyDecisionInvariantError(SafetyKernelError):
    """A safety decision contains an impossible field combination."""


class StaleSafetyDecisionError(SafetyKernelError):
    """A safety decision no longer matches its proposal or policy."""
