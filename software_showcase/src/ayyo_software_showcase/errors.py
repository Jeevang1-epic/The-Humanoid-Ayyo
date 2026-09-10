"""Typed failures for the bounded Ayyo software showcase."""


class SoftwareShowcaseError(Exception):
    """Base software-showcase failure."""


class ShowcaseIntegrityError(SoftwareShowcaseError, ValueError):
    """A showcase artifact is malformed or has invalid identity."""


class ShowcaseEvidenceError(ShowcaseIntegrityError):
    """A public-contract evidence reference is invalid."""


class ShowcaseCapabilityError(ShowcaseIntegrityError):
    """A capability claim is invalid or untruthful."""


class ShowcaseManifestError(ShowcaseIntegrityError):
    """A showcase manifest violates its bounded catalog contract."""


class ShowcaseReportError(ShowcaseIntegrityError):
    """A showcase report is invalid or differs from authoritative evaluation."""


class UnknownShowcaseCapabilityError(SoftwareShowcaseError, LookupError):
    """A requested capability is not part of the reviewed v1 catalog."""
