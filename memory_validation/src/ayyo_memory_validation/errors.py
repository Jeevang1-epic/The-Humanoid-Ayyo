"""Domain errors for deterministic memory validation policy."""


class MemoryValidationPolicyError(Exception):
    """Base class for validation-policy failures."""


class CandidateValidationError(MemoryValidationPolicyError, ValueError):
    """Candidate evidence violates a structural policy invariant."""


class CandidateProvenanceError(CandidateValidationError):
    """Candidate provenance is absent or malformed."""


class CandidateConfidenceError(CandidateValidationError):
    """Candidate confidence is not finite and within the inclusive range 0..1."""


class CandidateTimestampError(CandidateValidationError):
    """A candidate timestamp is not timezone-aware UTC."""


class InvalidCorrectionRequestError(CandidateValidationError):
    """Correction intent is incomplete or malformed."""


class NormalizationError(CandidateValidationError):
    """Input cannot be normalized without violating deterministic policy."""


class UnsupportedValueError(NormalizationError):
    """A value is not finite, JSON-compatible data."""


class CyclicValueError(NormalizationError):
    """A JSON-like input contains a reference cycle."""


class DecisionApplicationError(MemoryValidationPolicyError):
    """A policy decision cannot be applied safely."""


class DecisionNotApplicableError(DecisionApplicationError):
    """The decision does not permit a persistence mutation."""


class StaleDecisionError(DecisionApplicationError):
    """Active memory state changed after policy evaluation."""


class PolicyInvariantError(MemoryValidationPolicyError):
    """The policy received an internally inconsistent state."""
