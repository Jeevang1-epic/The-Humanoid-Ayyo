"""Typed physical-camera configuration and admission failures."""


class PhysicalCameraError(Exception):
    """Base failure for the transport-neutral physical-camera boundary."""


class PhysicalCameraValidationError(PhysicalCameraError, ValueError):
    """A physical source, calibration, or frame contract is invalid."""


class PhysicalCameraConfigurationError(PhysicalCameraError, ValueError):
    """Physical-camera registration or lifecycle configuration failed."""


class PhysicalCameraLifecycleError(PhysicalCameraError, RuntimeError):
    """An operation is invalid for the deterministic lifecycle state."""
