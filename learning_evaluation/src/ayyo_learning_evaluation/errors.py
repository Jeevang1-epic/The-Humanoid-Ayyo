"""Typed fail-closed errors for inert policy evaluation evidence."""


class LearningEvaluationError(Exception):
    """Base error for the transport-neutral learning-evaluation package."""


class CorpusConstructionError(LearningEvaluationError, ValueError):
    """Caller-supplied demonstrations cannot form a valid bounded corpus."""


class CorpusIntegrityError(LearningEvaluationError, ValueError):
    """A corpus or serialized corpus fails deterministic integrity checks."""


class CandidatePolicyIntegrityError(LearningEvaluationError, ValueError):
    """An inert candidate-policy manifest is invalid or was altered."""


class CandidateLineageError(LearningEvaluationError, ValueError):
    """Candidate, corpus, or evidence-set identities do not agree."""


class HoldoutPartitionError(LearningEvaluationError, ValueError):
    """Evidence crosses or violates the explicit holdout boundary."""


class EvaluationTrialError(LearningEvaluationError, ValueError):
    """A caller-supplied offline trial is structurally or referentially invalid."""


class EvaluationReportIntegrityError(LearningEvaluationError, ValueError):
    """An offline evaluation report fails deterministic integrity checks."""
