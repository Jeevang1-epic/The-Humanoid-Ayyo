"""Public deterministic Ayyo perception trust-boundary API."""

from .boundary import PerceptionTrustBoundary
from .errors import (
    PerceptionClockRegressionError,
    PerceptionConfigurationError,
    PerceptionError,
)
from .models import (
    MAX_PERCEPTION_RETENTION_NS,
    MAX_PERCEPTION_SOURCES,
    AdmissionReason,
    AdmissionResult,
    AdmissionStatus,
    EvidenceFailureKind,
    PerceptionSourceContract,
    PerceptionStats,
    PerceptionTrustConfig,
)

__all__ = [
    "AdmissionReason",
    "AdmissionResult",
    "AdmissionStatus",
    "EvidenceFailureKind",
    "MAX_PERCEPTION_RETENTION_NS",
    "MAX_PERCEPTION_SOURCES",
    "PerceptionClockRegressionError",
    "PerceptionConfigurationError",
    "PerceptionError",
    "PerceptionSourceContract",
    "PerceptionStats",
    "PerceptionTrustBoundary",
    "PerceptionTrustConfig",
]
