"""Public deterministic Ayyo perception trust-boundary API."""

from .boundary import PerceptionTrustBoundary
from .errors import (
    PerceptionClockRegressionError,
    PerceptionConfigurationError,
    PerceptionError,
    PerceptionObservationIdentityError,
    PerceptionObservationValidationError,
)
from .models import (
    AdmissionReason,
    AdmissionResult,
    AdmissionStatus,
    EvidenceFailureKind,
    MAX_PERCEPTION_RETENTION_NS,
    MAX_PERCEPTION_SOURCES,
    MAX_SEMANTIC_ADMISSIONS,
    MAX_SEMANTIC_SOURCE_INTERPRETATIONS,
    PerceptionSourceContract,
    PerceptionStats,
    PerceptionTrustConfig,
)
from .semantic_observations import (
    ObjectObservation,
    PersonObservation,
    SemanticObservation,
    SemanticDetectionSource,
    SemanticObservationKind,
    rebuild_semantic_observation,
    semantic_observation_from_detection,
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
    "MAX_SEMANTIC_ADMISSIONS",
    "MAX_SEMANTIC_SOURCE_INTERPRETATIONS",
    "PerceptionClockRegressionError",
    "PerceptionConfigurationError",
    "PerceptionError",
    "PerceptionObservationIdentityError",
    "PerceptionObservationValidationError",
    "PerceptionSourceContract",
    "PerceptionStats",
    "PerceptionTrustBoundary",
    "PerceptionTrustConfig",
    "ObjectObservation",
    "PersonObservation",
    "SemanticObservation",
    "SemanticDetectionSource",
    "SemanticObservationKind",
    "rebuild_semantic_observation",
    "semantic_observation_from_detection",
    "DeterministicVisualReferenceAdapter",
    "REFERENCE_VISUAL_PRODUCER",
]
