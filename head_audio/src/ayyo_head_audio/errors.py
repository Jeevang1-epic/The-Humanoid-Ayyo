"""Typed failures for the head-audio trust foundation."""


class HeadAudioError(Exception):
    """Base error for transport-neutral head-audio failures."""


class HeadAudioConfigurationError(HeadAudioError):
    """A reviewed source or adapter configuration is invalid."""


class HeadAudioLifecycleError(HeadAudioError):
    """A lifecycle operation is invalid for the current state."""


class HeadAudioValidationError(HeadAudioError):
    """Untrusted audio metadata or payload failed closed."""
