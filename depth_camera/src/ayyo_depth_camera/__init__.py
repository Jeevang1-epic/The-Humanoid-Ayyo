"""Public transport-neutral Ayyo head-depth foundation API."""

from .adapter import DepthLifecycleAdapter, DepthSourceRegistry
from .errors import (
    DepthCameraConfigurationError,
    DepthCameraError,
    DepthCameraLifecycleError,
    DepthCameraValidationError,
)
from .fixtures import (
    HEAD_DEPTH_SENSOR,
    SIMULATION_DEPTH_PROVENANCE,
    SIMULATION_DEPTH_SOURCE_ID,
    TEST_DEPTH_PROVENANCE,
    TEST_DEPTH_SOURCE_ID,
    DepthFixtureBundle,
    depth_simulation_bundle,
    depth_test_fixture_bundle,
    fixture_depth_bytes,
    fixture_depth_camera_info_metadata,
    fixture_depth_image_metadata,
)
from .models import (
    DEPTH_CAMERA_INFO_TOPIC,
    DEPTH_IMAGE_TOPIC,
    DEPTH_INTERFACE,
    MAX_DEPTH_CAMERA_SOURCES,
    MAX_DEPTH_COUNT,
    MAX_DEPTH_PENDING_PAIRS,
    DepthCameraAdmission,
    DepthCameraCalibration,
    DepthCalibrationSource,
    DepthCalibrationState,
    DepthCameraInfoMetadata,
    DepthDiagnosticEvent,
    DepthDiagnostics,
    DepthImageMetadata,
    DepthLifecycleState,
    DepthSourceClassification,
    DepthSourceManifest,
    DepthTrustRequirement,
    depth_camera_session_id,
    summarize_depth_image,
)

__all__ = [name for name in globals() if not name.startswith("_")]
