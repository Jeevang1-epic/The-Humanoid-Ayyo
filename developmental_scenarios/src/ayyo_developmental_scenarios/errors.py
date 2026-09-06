"""Typed failures for developmental scenario contracts."""


class DevelopmentScenarioError(Exception):
    """Base error for the development-only scenario framework."""


class InvalidScenarioDefinitionError(DevelopmentScenarioError, ValueError):
    """A scenario definition violates the bounded v1 contract."""


class InvalidScenarioResultError(DevelopmentScenarioError, ValueError):
    """Scenario evidence or a result violates the bounded v1 contract."""


class ScenarioExecutionError(DevelopmentScenarioError, RuntimeError):
    """The fixed typed executor could not complete a scenario operation."""
