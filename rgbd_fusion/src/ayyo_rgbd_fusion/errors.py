"""RGB-D synchronization failures."""


class RgbdFusionError(Exception):
    """Base RGB-D synchronization error."""


class RgbdFusionConfigurationError(RgbdFusionError, ValueError):
    """A synchronization policy or lifecycle configuration is invalid."""


class RgbdFusionLifecycleError(RgbdFusionError, RuntimeError):
    """An operation is invalid for the current synchronization lifecycle."""


class RgbdFusionValidationError(RgbdFusionError, ValueError):
    """Candidate component evidence violates the configured pair contract."""
