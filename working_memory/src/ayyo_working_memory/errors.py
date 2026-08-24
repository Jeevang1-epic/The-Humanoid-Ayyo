"""Typed Working Memory failures."""

from __future__ import annotations


class WorkingMemoryError(Exception):
    """Base error for bounded Working Memory."""


class WorkingMemoryConfigurationError(WorkingMemoryError, ValueError):
    """Retention or trust-boundary configuration is malformed."""


class WorkingMemoryClockRegressionError(WorkingMemoryError):
    """The configured source clock moved behind previously evaluated time."""
