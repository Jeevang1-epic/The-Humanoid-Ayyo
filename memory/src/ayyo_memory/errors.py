"""Domain and persistence errors raised by the Memory OS core."""


class AyyoMemoryError(Exception):
    """Base class for Memory OS failures."""


class MemoryValidationError(AyyoMemoryError, ValueError):
    """Base class for invalid domain input."""


class InvalidMemoryDataError(MemoryValidationError):
    """A memory field violates a domain invariant."""


class InvalidConfidenceError(MemoryValidationError):
    """A confidence value is not a finite number in the inclusive range 0..1."""


class InvalidProvenanceError(MemoryValidationError):
    """Required provenance is absent, malformed, or unsuitable for an operation."""


class MemoryNotFoundError(AyyoMemoryError, LookupError):
    """The requested memory does not exist."""


class InvalidCorrectionTargetError(AyyoMemoryError):
    """The requested memory cannot be corrected in its current state."""


class InvalidRetractionTargetError(AyyoMemoryError):
    """The requested memory cannot be retracted in its current state."""


class AlreadyRetractedError(AyyoMemoryError):
    """The requested memory has already been retracted."""


class MemoryPersistenceError(AyyoMemoryError):
    """Base class for durable store failures."""


class PersistenceConflictError(MemoryPersistenceError):
    """A persistence constraint prevented a mutation."""


class SchemaVersionError(AyyoMemoryError):
    """The database schema cannot be safely opened or migrated."""


class StoreClosedError(AyyoMemoryError):
    """An operation was attempted after the store was closed."""
