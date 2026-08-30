"""Depth-camera configuration, lifecycle, and evidence failures."""


class DepthCameraError(Exception):
    """Base error for the depth-camera foundation."""


class DepthCameraConfigurationError(DepthCameraError):
    """A reviewed source or calibration is absent or conflicting."""


class DepthCameraLifecycleError(DepthCameraError):
    """A lifecycle transition or callback is invalid for the current state."""


class DepthCameraValidationError(DepthCameraError, ValueError):
    """Depth evidence is malformed or outside its exact source contract."""
