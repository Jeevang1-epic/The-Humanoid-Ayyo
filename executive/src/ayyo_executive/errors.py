"""Typed failures raised by deterministic Executive Cognition."""


class ExecutiveError(Exception):
    """Base class for Executive Cognition failures."""


class ExecutiveValidationError(ExecutiveError, ValueError):
    """Base class for invalid public input."""


class InvalidRequestError(ExecutiveValidationError):
    """A structured executive request violates its contract."""


class InvalidCapabilityDefinitionError(ExecutiveValidationError):
    """A capability definition or registry is malformed."""


class InvalidCapabilityParametersError(ExecutiveValidationError):
    """An invocation does not satisfy its capability parameter contract."""


class PlanInvariantError(ExecutiveError):
    """A declarative plan violates structural invariants."""


class DecisionInvariantError(ExecutiveError):
    """An executive decision contains an impossible combination of fields."""
