"""Typed fail-closed errors for the inert policy-registry boundary."""


class PolicyRegistryError(ValueError):
    """Base error for policy-registry contract failures."""


class PolicyRegistryIntegrityError(PolicyRegistryError):
    """A registry artifact failed structural or content verification."""


class RegistrationRequestError(PolicyRegistryError):
    """A candidate-registration request violates the v1 contract."""


class RegisteredPolicyVersionError(PolicyRegistryError):
    """A registered policy-version record is invalid or contradictory."""


class PolicyRegistrySnapshotError(PolicyRegistryError):
    """A registry snapshot violates bounds, uniqueness, or lineage rules."""


class CandidateRegistrationError(PolicyRegistryError):
    """Supplied evidence cannot establish an inert registry record."""


class VersionLineageError(CandidateRegistrationError):
    """Explicit candidate parentage cannot be resolved or is incompatible."""


class PolicyResolutionError(PolicyRegistryError):
    """A read-only registry lookup request is malformed."""
