"""Deterministic runner for the fixed typed scenario operation set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .errors import InvalidScenarioResultError, ScenarioExecutionError
from .models import (
    AssertionOutcome,
    CleanupOutcome,
    DevelopmentScenarioDefinition,
    DevelopmentScenarioReport,
    DevelopmentScenarioStep,
    DevelopmentScenarioStepResult,
    MAX_SCENARIOS_PER_INVOCATION,
    ScenarioCleanupResult,
    ScenarioFailureReason,
    ScenarioObservedIdentity,
    ScenarioOutcome,
    ScenarioPolicyDecision,
    ScenarioSourceSummary,
)


@runtime_checkable
class DevelopmentScenarioExecutor(Protocol):
    """Fixed-operation adapter implemented by reviewed test orchestration."""

    def execute(
        self,
        definition: DevelopmentScenarioDefinition,
        step: DevelopmentScenarioStep,
    ) -> DevelopmentScenarioStepResult:
        ...

    def observed_identities(self) -> tuple[ScenarioObservedIdentity, ...]:
        ...

    def policy_decisions(self) -> tuple[ScenarioPolicyDecision, ...]:
        ...

    def development_authority_used(self) -> bool:
        ...

    def production_dispatch_count(self) -> int:
        ...

    def source_summaries(self) -> tuple[ScenarioSourceSummary, ...]:
        ...

    def cleanup(self) -> ScenarioCleanupResult:
        ...


@dataclass(frozen=True, slots=True)
class DevelopmentScenarioRunner:
    """Execute at most eight definitions in caller order with fail-closed reports."""

    def run(
        self,
        definition: DevelopmentScenarioDefinition,
        executor: DevelopmentScenarioExecutor,
    ) -> DevelopmentScenarioReport:
        if type(definition) is not DevelopmentScenarioDefinition:
            raise ScenarioExecutionError('runner requires a scenario definition')
        if not isinstance(executor, DevelopmentScenarioExecutor):
            raise ScenarioExecutionError('runner requires a typed scenario executor')
        assertion_results = []
        execution_failure = None
        try:
            for step in definition.steps:
                result = executor.execute(definition, step)
                if type(result) is not DevelopmentScenarioStepResult:
                    raise InvalidScenarioResultError(
                        'executor returned an invalid step result'
                    )
                if result.step_id != step.step_id or result.operation is not step.operation:
                    raise InvalidScenarioResultError(
                        'step result does not match the requested typed operation'
                    )
                if tuple(item.assertion_id for item in result.assertions) != step.assertion_ids:
                    raise InvalidScenarioResultError(
                        'step result assertions do not match the definition'
                    )
                assertion_results.extend(result.assertions)
        except (InvalidScenarioResultError, ScenarioExecutionError):
            execution_failure = ScenarioFailureReason.ASSERTION_FAILED
            raise
        finally:
            cleanup = executor.cleanup()
        if type(cleanup) is not ScenarioCleanupResult:
            raise InvalidScenarioResultError('executor returned invalid cleanup state')
        failed = any(
            item.outcome is AssertionOutcome.FAIL for item in assertion_results
        )
        reasons = {
            reason for item in assertion_results for reason in item.reasons
        }
        if execution_failure is not None:
            reasons.add(execution_failure)
        if cleanup.outcome is CleanupOutcome.INCOMPLETE:
            failed = True
            reasons.add(ScenarioFailureReason.CLEANUP_INCOMPLETE)
        return DevelopmentScenarioReport(
            definition=definition,
            outcome=ScenarioOutcome.FAIL if failed else ScenarioOutcome.PASS,
            assertion_results=tuple(assertion_results),
            failure_reasons=tuple(
                reason for reason in ScenarioFailureReason if reason in reasons
            ),
            observed_identities=executor.observed_identities(),
            policy_decisions=executor.policy_decisions(),
            development_authority_used=executor.development_authority_used(),
            production_dispatch_count=executor.production_dispatch_count(),
            sources=executor.source_summaries(),
            cleanup=cleanup,
        )

    def run_batch(
        self,
        work: tuple[
            tuple[DevelopmentScenarioDefinition, DevelopmentScenarioExecutor], ...
        ],
    ) -> tuple[DevelopmentScenarioReport, ...]:
        if not isinstance(work, tuple) or not work:
            raise ScenarioExecutionError('scenario invocation must be a non-empty tuple')
        if len(work) > MAX_SCENARIOS_PER_INVOCATION:
            raise ScenarioExecutionError('scenario invocation exceeds the v1 bound')
        return tuple(self.run(definition, executor) for definition, executor in work)
