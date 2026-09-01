"""Public deterministic Ayyo perception trust-boundary API."""

from .boundary import PerceptionTrustBoundary
from .errors import (
    PerceptionClockRegressionError,
    PerceptionConfigurationError,
    PerceptionError,
    PerceptionObservationValidationError,
)
from .models import (
    AdmissionReason,
    AdmissionResult,
    AdmissionStatus,
    EvidenceFailureKind,
    MAX_PERCEPTION_RETENTION_NS,
    MAX_PERCEPTION_SOURCES,
    PerceptionSourceContract,
    PerceptionStats,
    PerceptionTrustConfig,
)
from .semantic_observations import (
    ObjectObservation,
    PersonObservation,
    SemanticObservationKind,
)
from .visual_reference import (
    DeterministicVisualReferenceAdapter,
    REFERENCE_VISUAL_PRODUCER,
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
    "PerceptionObservationValidationError",
    "PerceptionSourceContract",
    "PerceptionStats",
    "PerceptionTrustBoundary",
    "PerceptionTrustConfig",
    "ObjectObservation",
    "PersonObservation",
    "SemanticObservationKind",
    "DeterministicVisualReferenceAdapter",
    "REFERENCE_VISUAL_PRODUCER",
]
