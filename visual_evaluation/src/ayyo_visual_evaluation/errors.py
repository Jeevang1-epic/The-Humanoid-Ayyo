"""Typed failures for the standalone visual producer evaluator."""

from __future__ import annotations


class VisualEvaluationError(Exception):
    """Base failure for visual evaluation."""


class VisualEvaluationConfigurationError(VisualEvaluationError, ValueError):
    """An immutable manifest, policy, or registration is malformed."""


class VisualDatasetError(VisualEvaluationError, ValueError):
    """A recorded dataset or one of its assets fails closed."""


class VisualProducerRegistrationError(VisualEvaluationError, ValueError):
    """A producer registration is unknown, conflicting, or unverifiable."""


class VisualInvocationError(VisualEvaluationError, RuntimeError):
    """The fixed invocation boundary could not safely execute or clean up."""
