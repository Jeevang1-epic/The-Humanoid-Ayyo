"""Errors raised while constructing explicit consolidation requests."""


class MemoryConsolidationError(Exception):
    """Base error for the standalone candidate-staging boundary."""


class ConsolidationRequestError(MemoryConsolidationError, ValueError):
    """An explicit request is malformed or exceeds a resource bound."""


class CandidateSelectionError(MemoryConsolidationError, ValueError):
    """A candidate-selection record violates a structural invariant."""


class CandidateDiscoveryError(MemoryConsolidationError, ValueError):
    """A candidate-discovery request or record violates a safe bound."""


class ControlledMemoryReviewError(MemoryConsolidationError, ValueError):
    """A controlled review invocation violates a structural invariant."""
