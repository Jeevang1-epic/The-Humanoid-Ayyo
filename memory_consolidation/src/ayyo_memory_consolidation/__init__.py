"""Public API for explicit candidate staging and reviewed selection."""

from .errors import (
    CandidateSelectionError,
    ConsolidationRequestError,
    MemoryConsolidationError,
)
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
from .selection_models import (
    CANDIDATE_SELECTION_POLICY_ID,
    CANDIDATE_SELECTION_POLICY_VERSION,
    MAX_CANDIDATE_SELECTION_AGGREGATE_CHARACTERS,
    MAX_CANDIDATE_SELECTION_COUNT,
    MAX_CANDIDATE_SELECTION_REASONS,
    MIN_REVIEW_CONFIDENCE,
    CandidateReviewItem,
    CandidateSelectionDecision,
    CandidateSelectionItemDecision,
    CandidateSelectionOutcome,
    CandidateSelectionReason,
)
from .selection_policy import (
    CANDIDATE_SELECTION_POLICY_FINGERPRINT,
    ReviewedMemoryCandidateSelectionPolicy,
    candidate_identity,
)

__all__ = [
    "CandidateStagingReason",
    "CandidateStagingResult",
    "CandidateStagingStatus",
    "CandidateReviewItem",
    "CandidateSelectionDecision",
    "CandidateSelectionError",
    "CandidateSelectionItemDecision",
    "CandidateSelectionOutcome",
    "CandidateSelectionReason",
    "CANDIDATE_SELECTION_POLICY_FINGERPRINT",
    "CANDIDATE_SELECTION_POLICY_ID",
    "CANDIDATE_SELECTION_POLICY_VERSION",
    "ConsolidationRequest",
    "ConsolidationRequestError",
    "EvidenceReference",
    "MAX_CONSOLIDATION_IDENTITY_TEXT",
    "MAX_CONSOLIDATION_METADATA_FIELDS",
    "MAX_CANDIDATE_SELECTION_AGGREGATE_CHARACTERS",
    "MAX_CANDIDATE_SELECTION_COUNT",
    "MAX_CANDIDATE_SELECTION_REASONS",
    "MAX_STAGING_DETAIL_TEXT",
    "MAX_SUPPORTING_EVIDENCE_COUNT",
    "MEMORY_CONSOLIDATION_SCHEMA_VERSION",
    "MemoryConsolidationError",
    "MIN_REVIEW_CONFIDENCE",
    "ReviewedMemoryCandidateSelectionPolicy",
    "WorkingMemoryCandidateBridge",
    "candidate_identity",
]
