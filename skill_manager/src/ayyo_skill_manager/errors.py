"""Typed failures for Ayyo's declarative Skill Manager."""


class SkillManagerError(Exception):
    """Base class for Skill Manager failures."""


class SkillValidationError(SkillManagerError, ValueError):
    """Base class for malformed public input."""


class InvalidSchemaError(SkillValidationError):
    """A bounded value schema is malformed or contradictory."""


class InvalidSkillDefinitionError(SkillValidationError):
    """A skill definition violates the immutable contract."""


class InvalidSkillRegistryError(SkillValidationError):
    """A skill registry violates identity or consistency invariants."""


class InvalidSkillParametersError(SkillValidationError):
    """Proposed parameters do not conform to a skill input contract."""


class InvalidSkillBindingError(SkillManagerError):
    """A proposed Safety-to-skill binding is structurally invalid."""


class StaleSkillBindingError(SkillManagerError):
    """A binding input no longer matches its pinned immutable sources."""


class SkillInvocationInvariantError(SkillManagerError):
    """A skill invocation or binding result has an impossible shape."""
