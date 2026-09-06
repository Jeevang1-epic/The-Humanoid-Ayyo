"""Closed v1 catalog of reviewed developmental simulation scenarios."""

from __future__ import annotations

from .errors import InvalidScenarioDefinitionError
from .models import (
    DevelopmentScenarioAssertion,
    DevelopmentScenarioDefinition,
    DevelopmentScenarioStep,
    MAX_SCENARIOS_PER_INVOCATION,
    ScenarioAuthority,
    ScenarioCategory,
    ScenarioLaunchProfile,
    ScenarioOperation,
)


def _assertions(*items: tuple[str, str]) -> tuple[DevelopmentScenarioAssertion, ...]:
    return tuple(
        DevelopmentScenarioAssertion(assertion_id=identifier, description=description)
        for identifier, description in items
    )


def _step(
    step_id: str,
    operation: ScenarioOperation,
    *assertion_ids: str,
    timeout_ms: int = 30_000,
) -> DevelopmentScenarioStep:
    return DevelopmentScenarioStep(
        step_id=step_id,
        operation=operation,
        timeout_ms=timeout_ms,
        assertion_ids=assertion_ids,
    )


EMBODIED_OBSERVATION = DevelopmentScenarioDefinition(
    scenario_id='embodied-observation-baseline',
    version='1.0.0',
    category=ScenarioCategory.EMBODIED_OBSERVATION,
    description='Observe the existing proxy Ayyo body through Gazebo and World Model.',
    launch_profile=ScenarioLaunchProfile.OBSERVATION,
    expected_safe_outcome=(
        'Simulation evidence is available without durable memory or motion authority.'
    ),
    authority=ScenarioAuthority.NONE,
    steps=(
        _step('gazebo-ready', ScenarioOperation.WAIT_FOR_GAZEBO, 'gazebo-running'),
        _step(
            'single-model',
            ScenarioOperation.VERIFY_SINGLE_AYYO_MODEL,
            'ayyo-spawned-once',
        ),
        _step(
            'world-model-active',
            ScenarioOperation.WAIT_FOR_WORLD_MODEL_ACTIVE,
            'world-model-active',
        ),
        _step('clock-ready', ScenarioOperation.WAIT_FOR_CLOCK, 'clock-available'),
        _step(
            'joint-state-ready',
            ScenarioOperation.WAIT_FOR_AUTHORITATIVE_JOINT_STATE,
            'joint-state-authoritative',
        ),
        _step(
            'imu-ready',
            ScenarioOperation.WAIT_FOR_IMU_OBSERVATION,
            'imu-admitted',
        ),
        _step(
            'localization-ready',
            ScenarioOperation.WAIT_FOR_LOCALIZATION_OBSERVATION,
            'localization-admitted',
        ),
        _step(
            'body-query',
            ScenarioOperation.QUERY_ROBOT_BODY_STATE,
            'body-state-exposed',
            'canonical-robot-identity',
            'simulation-provenance',
        ),
        _step(
            'memory-unchanged',
            ScenarioOperation.ASSERT_NO_DURABLE_MEMORY_WRITE,
            'no-durable-memory-side-effect',
        ),
        _step(
            'production-authority-absent',
            ScenarioOperation.ASSERT_NO_PRODUCTION_DISPATCH,
            'no-production-motion-authority',
        ),
        _step(
            'process-health',
            ScenarioOperation.ASSERT_PROCESS_HEALTH,
            'owned-processes-clean',
        ),
    ),
    assertions=_assertions(
        ('gazebo-running', 'Gazebo server remained alive through observation.'),
        ('ayyo-spawned-once', 'The canonical Ayyo model spawned exactly once.'),
        ('world-model-active', 'World Model reached active lifecycle state.'),
        ('clock-available', 'The simulation clock produced bounded samples.'),
        (
            'joint-state-authoritative',
            'One controller-derived authoritative joint-state publisher was present.',
        ),
        ('imu-admitted', 'Simulation IMU evidence reached the World Model query.'),
        (
            'localization-admitted',
            'Simulation odometry evidence reached the World Model query.',
        ),
        ('body-state-exposed', 'World Model exposed current observed body state.'),
        ('canonical-robot-identity', 'Body state retained ayyo.robot.v1 identity.'),
        ('simulation-provenance', 'Observed body sources retained simulation provenance.'),
        (
            'no-durable-memory-side-effect',
            'Observation created no durable Memory OS record.',
        ),
        (
            'no-production-motion-authority',
            'No production motion endpoint or dispatch authority appeared.',
        ),
        ('owned-processes-clean', 'The owned process set became empty on shutdown.'),
    ),
)


VISUAL_SEMANTIC_OBSERVATION = DevelopmentScenarioDefinition(
    scenario_id='visual-anonymous-semantic-observation',
    version='1.0.0',
    category=ScenarioCategory.VISUAL_SEMANTIC_OBSERVATION,
    description='Validate reviewed TEST person and object evidence from one Gazebo RGB frame.',
    launch_profile=ScenarioLaunchProfile.OBSERVATION,
    expected_safe_outcome=(
        'Anonymous bounded TEST evidence is queryable without identity or persistence.'
    ),
    authority=ScenarioAuthority.NONE,
    steps=(
        _step(
            'rgb-observation',
            ScenarioOperation.WAIT_FOR_RGB_OBSERVATION,
            'rgb-source-identity',
            'rgb-source-time',
        ),
        _step(
            'semantic-query',
            ScenarioOperation.QUERY_ANONYMOUS_SEMANTIC_STATE,
            'person-remains-anonymous',
            'object-remains-anonymous',
            'object-category-not-identity',
            'confidence-exact',
            'partial-observation-conservative',
            'query-read-only',
            'test-fixture-provenance',
        ),
        _step(
            'semantic-memory-unchanged',
            ScenarioOperation.ASSERT_NO_DURABLE_MEMORY_WRITE,
            'semantic-not-persisted',
        ),
    ),
    assertions=_assertions(
        ('rgb-source-identity', 'The exact admitted Gazebo RGB source identity was retained.'),
        ('rgb-source-time', 'The exact RGB source acquisition timestamp was retained.'),
        ('person-remains-anonymous', 'PERSON evidence contained no persistent identity.'),
        ('object-remains-anonymous', 'OBJECT evidence contained no persistent identity.'),
        ('object-category-not-identity', 'The object label remained a category only.'),
        ('confidence-exact', 'Absent and zero confidence semantics remained distinct.'),
        (
            'partial-observation-conservative',
            'Partial evidence did not imply complete physical-scene absence.',
        ),
        ('query-read-only', 'The anonymous semantic query caused no mutation.'),
        ('test-fixture-provenance', 'Semantic production was labeled TEST fixture provenance.'),
        ('semantic-not-persisted', 'Semantic evidence created no durable Memory OS record.'),
    ),
)


PRODUCTION_MOTION_DEFERRED = DevelopmentScenarioDefinition(
    scenario_id='production-physical-request-deferred',
    version='1.0.0',
    category=ScenarioCategory.COGNITIVE_POLICY_BOUNDARY,
    description=(
        'Pass one structured neck movement request through current public '
        'policy contracts.'
    ),
    launch_profile=ScenarioLaunchProfile.OBSERVATION,
    expected_safe_outcome='Safety defers movement and no production dispatch or motion occurs.',
    authority=ScenarioAuthority.NONE,
    steps=(
        _step(
            'executive-decision',
            ScenarioOperation.REQUEST_EXECUTIVE_PHYSICAL_DECISION,
            'executive-proposal-structured',
        ),
        _step(
            'safety-decision',
            ScenarioOperation.EVALUATE_SAFETY,
            'safety-deferred',
        ),
        _step(
            'skill-binding',
            ScenarioOperation.BIND_SKILL,
            'skill-binding-ineligible',
        ),
        _step(
            'runtime-binding',
            ScenarioOperation.CHECK_RUNTIME_BINDING,
            'runtime-not-dispatchable',
        ),
        _step(
            'production-dispatch',
            ScenarioOperation.ASSERT_NO_PRODUCTION_DISPATCH,
            'production-dispatch-zero',
            'development-service-not-called',
            'controller-command-not-issued',
        ),
        _step(
            'stationary-joint',
            ScenarioOperation.WAIT_FOR_AUTHORITATIVE_JOINT_STATE,
            'requested-joint-stationary',
        ),
    ),
    assertions=_assertions(
        ('executive-proposal-structured', 'Executive produced a bounded declarative proposal.'),
        ('safety-deferred', 'Immutable Safety classified physical movement as DEFERRED.'),
        (
            'skill-binding-ineligible',
            'Skill Manager preserved Safety deferral without invocation.',
        ),
        ('runtime-not-dispatchable', 'Runtime Bridge returned no dispatchable request.'),
        ('production-dispatch-zero', 'Production dispatch count remained exactly zero.'),
        ('development-service-not-called', 'Cognition did not call the development service.'),
        ('controller-command-not-issued', 'Cognition emitted no controller command.'),
        ('requested-joint-stationary', 'The requested neck joint remained stationary.'),
    ),
)


DEVELOPMENT_NECK_ACTUATION = DevelopmentScenarioDefinition(
    scenario_id='development-only-neck-actuation',
    version='1.0.0',
    category=ScenarioCategory.DEVELOPMENT_ACTUATION,
    description=(
        'Exercise the existing bounded neck command through explicit '
        'development authority.'
    ),
    launch_profile=ScenarioLaunchProfile.DEVELOPMENT_CONTROL,
    expected_safe_outcome=(
        'The valid bounded neck command moves in simulation and returns to neutral.'
    ),
    authority=ScenarioAuthority.DEVELOPMENT_NECK_CONTROL,
    steps=(
        _step(
            'development-control-ready',
            ScenarioOperation.WAIT_FOR_DEVELOPMENT_CONTROL,
            'controller-hardware-active',
        ),
        _step('initial-neck', ScenarioOperation.READ_NECK_STATE, 'initial-neck-observed'),
        _step(
            'valid-neck-command',
            ScenarioOperation.CALL_DEVELOPMENT_NECK_CONTROL,
            'development-command-completed',
        ),
        _step(
            'target-neck',
            ScenarioOperation.WAIT_FOR_NECK_TARGET,
            'neck-target-observed',
            'neck-within-urdf-limit',
            'world-model-neck-updated',
            'production-authority-unused',
        ),
        _step(
            'restore-neck',
            ScenarioOperation.RESTORE_DEVELOPMENT_NECK_NEUTRAL,
            'neck-restored-neutral',
            'development-cleanup-complete',
        ),
    ),
    assertions=_assertions(
        ('controller-hardware-active', 'Controller and simulated hardware were active.'),
        ('initial-neck-observed', 'Initial controller-derived neck state was captured.'),
        ('development-command-completed', 'The typed DEVELOPMENT command completed.'),
        ('neck-target-observed', 'Controller-derived state reached the bounded target.'),
        (
            'neck-within-urdf-limit',
            'Observed neck state remained inside authoritative URDF limits.',
        ),
        ('world-model-neck-updated', 'World Model exposed the updated proprioceptive state.'),
        ('production-authority-unused', 'No production Safety or Runtime authority was used.'),
        ('neck-restored-neutral', 'The reviewed development reset returned the neck to neutral.'),
        ('development-cleanup-complete', 'Owned controlled-simulation processes shut down.'),
    ),
)


INVALID_DEVELOPMENT_COMMAND = DevelopmentScenarioDefinition(
    scenario_id='invalid-development-command-rejected',
    version='1.0.0',
    category=ScenarioCategory.FAIL_CLOSED_CONTROL,
    description='Reject one out-of-bounds development neck request without fabricated state.',
    launch_profile=ScenarioLaunchProfile.DEVELOPMENT_CONTROL,
    expected_safe_outcome=(
        'The typed boundary rejects the target and controller state remains healthy.'
    ),
    authority=ScenarioAuthority.DEVELOPMENT_NECK_CONTROL,
    steps=(
        _step('before-invalid', ScenarioOperation.READ_NECK_STATE, 'pre-command-state-observed'),
        _step(
            'invalid-neck-command',
            ScenarioOperation.CALL_INVALID_DEVELOPMENT_NECK_CONTROL,
            'invalid-command-rejected',
            'typed-rejection-reason',
            'invalid-not-clamped',
        ),
        _step(
            'after-invalid',
            ScenarioOperation.QUERY_ROBOT_BODY_STATE,
            'invalid-target-not-reached',
            'world-model-not-fabricated',
            'controller-remains-healthy',
            'post-rejection-query-works',
        ),
    ),
    assertions=_assertions(
        ('pre-command-state-observed', 'A controller-derived pre-command state was captured.'),
        ('invalid-command-rejected', 'The out-of-bounds command was rejected.'),
        ('typed-rejection-reason', 'The response retained the typed above-maximum reason.'),
        ('invalid-not-clamped', 'The invalid target was not silently accepted by clamping.'),
        ('invalid-target-not-reached', 'The neck did not move to the invalid target.'),
        (
            'world-model-not-fabricated',
            'World Model did not expose requested state as observed state.',
        ),
        ('controller-remains-healthy', 'The controller remained active after rejection.'),
        ('post-rejection-query-works', 'A subsequent typed body query succeeded.'),
    ),
)


SENSOR_ABSENCE = DevelopmentScenarioDefinition(
    scenario_id='optional-visual-source-absent',
    version='1.0.0',
    category=ScenarioCategory.SENSOR_AVAILABILITY,
    description=(
        'Start without optional visual and semantic sources and require '
        'conservative state.'
    ),
    launch_profile=ScenarioLaunchProfile.SENSOR_ABSENCE,
    expected_safe_outcome=(
        'World Model remains active without fabricating visual evidence or absence.'
    ),
    authority=ScenarioAuthority.NONE,
    steps=(
        _step(
            'world-model-without-visual',
            ScenarioOperation.WAIT_FOR_WORLD_MODEL_ACTIVE,
            'world-model-available-without-visual',
        ),
        _step(
            'visual-source-absent',
            ScenarioOperation.VERIFY_OPTIONAL_SENSOR_ABSENT,
            'visual-source-not-enabled',
            'no-fake-visual-evidence',
            'no-stale-refresh',
        ),
        _step(
            'empty-semantic-query',
            ScenarioOperation.QUERY_ANONYMOUS_SEMANTIC_STATE,
            'no-fake-person-object-evidence',
            'no-complete-scene-absence-claim',
            'availability-diagnostics-exact',
        ),
        _step(
            'absence-process-health',
            ScenarioOperation.ASSERT_PROCESS_HEALTH,
            'system-operational-without-visual',
        ),
    ),
    assertions=_assertions(
        (
            'world-model-available-without-visual',
            'World Model remained active without visual input.',
        ),
        ('visual-source-not-enabled', 'The optional RGB source had no publisher.'),
        ('no-fake-visual-evidence', 'No visual observation was fabricated.'),
        ('no-stale-refresh', 'Absent traffic did not refresh retained evidence.'),
        ('no-fake-person-object-evidence', 'No person or object evidence was fabricated.'),
        (
            'no-complete-scene-absence-claim',
            'Empty retained evidence was not interpreted as physical-scene absence.',
        ),
        ('availability-diagnostics-exact', 'The query represented the source as not enabled.'),
        ('system-operational-without-visual', 'The owned system stayed healthy and shut down.'),
    ),
)


SCENARIO_CATALOG = (
    EMBODIED_OBSERVATION,
    VISUAL_SEMANTIC_OBSERVATION,
    PRODUCTION_MOTION_DEFERRED,
    DEVELOPMENT_NECK_ACTUATION,
    INVALID_DEVELOPMENT_COMMAND,
    SENSOR_ABSENCE,
)

if len(SCENARIO_CATALOG) > MAX_SCENARIOS_PER_INVOCATION:
    raise RuntimeError('the reviewed scenario catalog exceeds the invocation bound')

_BY_ID = {item.scenario_id: item for item in SCENARIO_CATALOG}
if len(_BY_ID) != len(SCENARIO_CATALOG):
    raise RuntimeError('the reviewed scenario catalog contains duplicate identities')


def scenario_by_id(scenario_id: str) -> DevelopmentScenarioDefinition:
    """Resolve one exact reviewed scenario; arbitrary definitions are not loaded."""
    if type(scenario_id) is not str or scenario_id not in _BY_ID:
        raise InvalidScenarioDefinitionError('unknown reviewed scenario ID')
    return _BY_ID[scenario_id]
