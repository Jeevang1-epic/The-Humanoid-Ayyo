"""Public bounded Ayyo RGB-D synchronization API."""

from .adapter import RgbdFusionLifecycleAdapter
from .errors import (
    RgbdFusionConfigurationError,
    RgbdFusionError,
    RgbdFusionLifecycleError,
    RgbdFusionValidationError,
)
from .models import (
    HEAD_RGBD_FUSION_SENSOR,
    MAX_RGBD_COUNT,
    MAX_RGBD_PENDING_PER_STREAM,
    RGBD_INTERFACE,
    RGBD_PAIRING_POLICY_ID,
    RGBD_PAIRING_POLICY_VERSION,
    RGBD_TEST_PROVENANCE,
    RgbdFusionAdmission,
    RgbdFusionDiagnostics,
    RgbdFusionEvent,
    RgbdFusionLifecycleState,
    RgbdFusionRequirement,
    rgbd_test_requirement,
)

__all__ = [
    "HEAD_RGBD_FUSION_SENSOR",
    "MAX_RGBD_COUNT",
    "MAX_RGBD_PENDING_PER_STREAM",
    "RGBD_INTERFACE",
    "RGBD_PAIRING_POLICY_ID",
    "RGBD_PAIRING_POLICY_VERSION",
    "RGBD_TEST_PROVENANCE",
    "RgbdFusionAdmission",
    "RgbdFusionConfigurationError",
    "RgbdFusionDiagnostics",
    "RgbdFusionError",
    "RgbdFusionEvent",
    "RgbdFusionLifecycleAdapter",
    "RgbdFusionLifecycleError",
    "RgbdFusionLifecycleState",
    "RgbdFusionRequirement",
    "RgbdFusionValidationError",
    "rgbd_test_requirement",
]
