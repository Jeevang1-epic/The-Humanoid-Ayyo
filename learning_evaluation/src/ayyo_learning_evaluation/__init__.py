"""Public API for bounded inert candidate-policy and offline evaluation evidence."""

from .corpus import (
    CORPUS_SCHEMA_ID,
    CORPUS_SCHEMA_VERSION,
    EVIDENCE_SET_SCHEMA_ID,
    EVIDENCE_SET_SCHEMA_VERSION,
    MAX_EPISODES_PER_CORPUS,
    MAX_EPISODES_PER_PARTITION,
    MAX_IDENTIFIER_LENGTH,
    MAX_METADATA_TEXT_LENGTH,
    MAX_SERIALIZED_CORPUS_BYTES,
    CorpusPartition,
    DemonstrationEpisodeReference,
    DemonstrationEvaluationCorpus,
    DemonstrationEvidenceSet,
)
from .corpus_serialization import (
    canonical_corpus_json,
    corpus_from_canonical_json,
    verify_corpus,
)
from .errors import (
    CandidateLineageError,
    CandidatePolicyIntegrityError,
    CorpusConstructionError,
    CorpusIntegrityError,
    EvaluationReportIntegrityError,
    EvaluationTrialError,
    HoldoutPartitionError,
    LearningEvaluationError,
)

__all__ = [
    'CORPUS_SCHEMA_ID',
    'CORPUS_SCHEMA_VERSION',
    'EVIDENCE_SET_SCHEMA_ID',
    'EVIDENCE_SET_SCHEMA_VERSION',
    'MAX_EPISODES_PER_CORPUS',
    'MAX_EPISODES_PER_PARTITION',
    'MAX_IDENTIFIER_LENGTH',
    'MAX_METADATA_TEXT_LENGTH',
    'MAX_SERIALIZED_CORPUS_BYTES',
    'CandidateLineageError',
    'CandidatePolicyIntegrityError',
    'CorpusConstructionError',
    'CorpusIntegrityError',
    'CorpusPartition',
    'DemonstrationEpisodeReference',
    'DemonstrationEvaluationCorpus',
    'DemonstrationEvidenceSet',
    'EvaluationReportIntegrityError',
    'EvaluationTrialError',
    'HoldoutPartitionError',
    'LearningEvaluationError',
    'canonical_corpus_json',
    'corpus_from_canonical_json',
    'verify_corpus',
]
