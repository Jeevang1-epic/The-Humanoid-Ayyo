"""Typed failures for bounded Teach Mode demonstration evidence."""


class TeachModeError(Exception):
    """Base error for the transport-neutral Teach Mode capture package."""


class DemonstrationValidationError(TeachModeError, ValueError):
    """Demonstration evidence violates a typed or bounded v1 contract."""


class DemonstrationIntegrityError(TeachModeError, ValueError):
    """Serialized or reconstructed demonstration evidence fails integrity."""


class DemonstrationSessionError(TeachModeError, RuntimeError):
    """An explicit capture session is used outside its valid lifecycle."""


class ScenarioDemonstrationAdapterError(TeachModeError, ValueError):
    """A Stage-6 report cannot be truthfully represented as a demonstration."""
