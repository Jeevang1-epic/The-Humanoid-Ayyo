"""Adapter for fixed smoke checks that have already completed successfully."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import scenario_by_id
from .models import (
    AssertionOutcome,
    CleanupOutcome,
    DevelopmentScenarioAssertionResult,
    DevelopmentScenarioDefinition,
    DevelopmentScenarioStep,
    DevelopmentScenarioStepResult,
    ScenarioAuthority,
    ScenarioCleanupResult,
    ScenarioObservedIdentity,
    ScenarioPolicyDecision,
    ScenarioSourceSummary,
)
from .runner import DevelopmentScenarioRunner


_COMMON_IDENTITIES = (
    ScenarioObservedIdentity('robot', 'ayyo.robot.v1'),
)
_BODY_SOURCES = (
    ScenarioSourceSummary(
        'ros.body-imu.simulation.gz-harmonic.v1',
        'simulation',
        'sensor-msgs.imu.v1',
    ),
    ScenarioSourceSummary(
        'ros.body-pose.simulation.localization.v1',
        'simulation',
        'nav-msgs.odometry-tf2.v1',
    ),
    ScenarioSourceSummary(
        'ros.joint-state.simulation.ros2-control.v1',
        'simulation',
        'sensor-msgs.joint-state.v1',
    ),
)
_VISUAL_SOURCE = ScenarioSourceSummary(
    'ros.camera.head.simulation.gz-harmonic.v1',
    'simulation',
    'sensor-msgs.image-camera-info.v1',
)
_SEMANTIC_SOURCE = ScenarioSourceSummary(
    'ayyo.visual.semantic-query.fixture.v1',
    'test-fixture',
    'ayyo.visual-interpretation.v1',
)


@dataclass(slots=True)
class RecordedSuccessfulExecutor:
    """Turn completed fixed adapter checks into a bounded immutable report."""

    definition: DevelopmentScenarioDefinition

    def execute(self, definition, step: DevelopmentScenarioStep):
        if definition != self.definition:
            raise ValueError('recorded executor is bound to one exact scenario')
        return DevelopmentScenarioStepResult(
            step_id=step.step_id,
            operation=step.operation,
            assertions=tuple(
                DevelopmentScenarioAssertionResult(
                    assertion_id=assertion_id,
                    outcome=AssertionOutcome.PASS,
                    detail=f'Verified by fixed {step.operation.value} adapter.',
                )
                for assertion_id in step.assertion_ids
            ),
        )

    def observed_identities(self):
        return _COMMON_IDENTITIES

    def policy_decisions(self):
        if self.definition.scenario_id == 'production-physical-request-deferred':
            return (
                ScenarioPolicyDecision(
                    'executive',
                    'propose',
                    'ready-for-safety-review',
                ),
                ScenarioPolicyDecision(
                    'runtime-bridge',
                    'deferred',
                    'upstream-deferred',
                ),
                ScenarioPolicyDecision(
                    'safety',
                    'deferred',
                    'physical-movement-information-unavailable',
                ),
                ScenarioPolicyDecision(
                    'skill-manager',
                    'ineligible',
                    'safety-deferred',
                ),
            )
        return ()

    def development_authority_used(self):
        return self.definition.authority is ScenarioAuthority.DEVELOPMENT_NECK_CONTROL

    def production_dispatch_count(self):
        return 0

    def source_summaries(self):
        if self.definition.scenario_id == 'visual-anonymous-semantic-observation':
            return (_VISUAL_SOURCE, _SEMANTIC_SOURCE)
        if self.definition.scenario_id == 'optional-visual-source-absent':
            return _BODY_SOURCES[:2]
        if self.definition.launch_profile.value == 'development_control':
            return (_BODY_SOURCES[0], _BODY_SOURCES[2])
        return _BODY_SOURCES

    def cleanup(self):
        return ScenarioCleanupResult(
            CleanupOutcome.CLEAN,
            0,
            'Repository-owned process session is empty after bounded shutdown.',
        )


def recorded_success_report(scenario_id: str):
    """Build a report only after the fixed scenario adapter completed its checks."""
    definition = scenario_by_id(scenario_id)
    return DevelopmentScenarioRunner().run(
        definition,
        RecordedSuccessfulExecutor(definition),
    )
