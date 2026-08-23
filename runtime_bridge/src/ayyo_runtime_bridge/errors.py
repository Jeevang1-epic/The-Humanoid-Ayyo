"""Typed failures for the Runtime Bridge boundary."""


class RuntimeBridgeError(Exception):
    """Base class for expected Runtime Bridge domain failures."""


class RuntimeValidationError(RuntimeBridgeError, ValueError):
    """Base class for malformed deterministic runtime data."""


class InvalidRuntimeContractError(RuntimeValidationError):
    """Raised when a runtime model violates its invariant."""


class InvalidRosEndpointError(RuntimeValidationError):
    """Raised when a declarative ROS endpoint is malformed."""


class InvalidRuntimeRegistryError(RuntimeValidationError):
    """Raised when an endpoint allowlist is malformed or ambiguous."""


class InvalidRuntimeBindingError(RuntimeValidationError):
    """Raised when upstream binding data is malformed."""


class StaleRuntimeDecisionError(RuntimeBridgeError):
    """Raised when dispatch is attempted with a stale eligibility decision."""


class RuntimeTransportError(RuntimeBridgeError):
    """Base class for expected transport failures."""


class RuntimeTransportUnavailableError(RuntimeTransportError):
    """Raised when the selected production transport is unavailable."""


class RuntimeTransportRejectedError(RuntimeTransportError):
    """Raised when transport rejects a request before accepting it."""
