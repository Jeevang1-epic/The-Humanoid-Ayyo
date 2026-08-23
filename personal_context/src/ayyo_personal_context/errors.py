"""Typed failures raised by the Personal Context Twin."""


class PersonalContextError(Exception):
    """Base class for Personal Context Twin failures."""


class PersonalContextValidationError(PersonalContextError, ValueError):
    """A caller supplied invalid context configuration or query input."""


class InvalidOwnerError(PersonalContextValidationError):
    """The configured owner subject is invalid."""


class InvalidContextQueryError(PersonalContextValidationError):
    """A context query is malformed."""


class ContextInvariantError(PersonalContextError):
    """A context model or projection violates a required invariant."""


class InconsistentSourceStateError(PersonalContextError):
    """Separate Memory OS reads did not describe one coherent active state."""
