"""Typed perception trust-boundary failures."""

from __future__ import annotations


class PerceptionError(Exception):
    """Base error for the standalone trust boundary."""


class PerceptionConfigurationError(PerceptionError, ValueError):
    """A reviewed source or resource policy is malformed."""


class PerceptionClockRegressionError(PerceptionError):
    """The configured source clock moved backwards across an evidence epoch."""


class PerceptionObservationValidationError(PerceptionError, ValueError):
    """A transport-neutral perception observation contract is malformed."""
