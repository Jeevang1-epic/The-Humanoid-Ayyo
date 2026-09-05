"""Public API for explicit Working Memory candidate staging."""

from .errors import ConsolidationRequestError, MemoryConsolidationError
from .models import (
    MEMORY_CONSOLIDATION_SCHEMA_VERSION,
    MAX_CONSOLIDATION_IDENTITY_TEXT,
    MAX_CONSOLIDATION_METADATA_FIELDS,
    MAX_STAGING_DETAIL_TEXT,
    MAX_SUPPORTING_EVIDENCE_COUNT,
    CandidateStagingReason,
    CandidateStagingResult,
    CandidateStagingStatus,
    ConsolidationRequest,
    EvidenceReference,
)
from .service import WorkingMemoryCandidateBridge

__all__ = [
    "CandidateStagingReason",
    "CandidateStagingResult",
    "CandidateStagingStatus",
    "ConsolidationRequest",
    "ConsolidationRequestError",
    "EvidenceReference",
    "MAX_CONSOLIDATION_IDENTITY_TEXT",
    "MAX_CONSOLIDATION_METADATA_FIELDS",
    "MAX_STAGING_DETAIL_TEXT",
    "MAX_SUPPORTING_EVIDENCE_COUNT",
    "MEMORY_CONSOLIDATION_SCHEMA_VERSION",
    "MemoryConsolidationError",
    "WorkingMemoryCandidateBridge",
]
