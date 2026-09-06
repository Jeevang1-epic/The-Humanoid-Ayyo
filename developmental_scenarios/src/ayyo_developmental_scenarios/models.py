"""Immutable bounded contracts for Stage-6 developmental scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from .canonical import semantic_sha256
from .errors import InvalidScenarioDefinitionError, InvalidScenarioResultError


FRAMEWORK_ID = 'ayyo.developmental-scenarios.v1'
FRAMEWORK_VERSION = '1.0.0'
MAX_SCENARIOS_PER_INVOCATION = 8
MAX_STEPS_PER_SCENARIO = 32
MAX_ASSERTIONS_PER_SCENARIO = 64
MAX_REASONS_PER_REPORT = 16
MAX_REPORT_TEXT_LENGTH = 512
MAX_SOURCE_SUMMARIES = 16
MAX_OBSERVED_IDENTITIES = 32
MAX_POLICY_DECISIONS = 16
MAX_RETAINED_ROS_SAMPLES = 64
MAX_DIAGNOSTIC_RECORDS = 32
MIN_STEP_TIMEOUT_MS = 100
MAX_STEP_TIMEOUT_MS = 120_000

_IDENTIFIER = re.compile(r'^[a-z0-9]+(?:[._-][a-z0-9]+)*$')
_SEMVER = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')


class ScenarioCategory(StrEnum):
    EMBODIED_OBSERVATION = 'embodied_observation'
    VISUAL_SEMANTIC_OBSERVATION = 'visual_semantic_observation'
    COGNITIVE_POLICY_BOUNDARY = 'cognitive_policy_boundary'
    DEVELOPMENT_ACTUATION = 'development_actuation'
    FAIL_CLOSED_CONTROL = 'fail_closed_control'
    SENSOR_AVAILABILITY = 'sensor_availability'


class ScenarioLaunchProfile(StrEnum):
    OBSERVATION = 'observation'
    DEVELOPMENT_CONTROL = 'development_control'
    SENSOR_ABSENCE = 'sensor_absence'


class ScenarioAuthority(StrEnum):
    NONE = 'none'
    DEVELOPMENT_NECK_CONTROL = 'development_neck_control'


class ScenarioOperation(StrEnum):
    WAIT_FOR_GAZEBO = 'wait_for_gazebo'
    VERIFY_SINGLE_AYYO_MODEL = 'verify_single_ayyo_model'
    WAIT_FOR_WORLD_MODEL_ACTIVE = 'wait_for_world_model_active'
    WAIT_FOR_CLOCK = 'wait_for_clock'
    WAIT_FOR_AUTHORITATIVE_JOINT_STATE = 'wait_for_authoritative_joint_state'
    QUERY_ROBOT_BODY_STATE = 'query_robot_body_state'
    WAIT_FOR_IMU_OBSERVATION = 'wait_for_imu_observation'
    WAIT_FOR_LOCALIZATION_OBSERVATION = 'wait_for_localization_observation'
    WAIT_FOR_RGB_OBSERVATION = 'wait_for_rgb_observation'
    QUERY_ANONYMOUS_SEMANTIC_STATE = 'query_anonymous_semantic_state'
    REQUEST_EXECUTIVE_PHYSICAL_DECISION = 'request_executive_physical_decision'
    EVALUATE_SAFETY = 'evaluate_safety'
    BIND_SKILL = 'bind_skill'
    CHECK_RUNTIME_BINDING = 'check_runtime_binding'
    ASSERT_NO_PRODUCTION_DISPATCH = 'assert_no_production_dispatch'
    WAIT_FOR_DEVELOPMENT_CONTROL = 'wait_for_development_control'
    READ_NECK_STATE = 'read_neck_state'
    CALL_DEVELOPMENT_NECK_CONTROL = 'call_development_neck_control'
    WAIT_FOR_NECK_TARGET = 'wait_for_neck_target'
    RESTORE_DEVELOPMENT_NECK_NEUTRAL = 'restore_development_neck_neutral'
    CALL_INVALID_DEVELOPMENT_NECK_CONTROL = (
        'call_invalid_development_neck_control'
    )
    VERIFY_OPTIONAL_SENSOR_ABSENT = 'verify_optional_sensor_absent'
    ASSERT_NO_DURABLE_MEMORY_WRITE = 'assert_no_durable_memory_write'
    ASSERT_PROCESS_HEALTH = 'assert_process_health'


class ScenarioOutcome(StrEnum):
    PASS = 'pass'
    FAIL = 'fail'
    NOT_APPLICABLE = 'not_applicable'


class AssertionOutcome(StrEnum):
    PASS = 'pass'
    FAIL = 'fail'
    NOT_APPLICABLE = 'not_applicable'


class ScenarioFailureReason(StrEnum):
    ASSERTION_FAILED = 'assertion_failed'
    DEADLINE_EXCEEDED = 'deadline_exceeded'
    REQUIRED_INTERFACE_UNAVAILABLE = 'required_interface_unavailable'
    UNEXPECTED_PROCESS_EXIT = 'unexpected_process_exit'
    DUPLICATE_AUTHORITY_SOURCE = 'duplicate_authority_source'
    POLICY_BOUNDARY_CHANGED = 'policy_boundary_changed'
    DEVELOPMENT_AUTHORITY_UNAVAILABLE = 'development_authority_unavailable'
    CLEANUP_INCOMPLETE = 'cleanup_incomplete'


class CleanupOutcome(StrEnum):
    CLEAN = 'clean'
    ESCALATED = 'escalated'
    INCOMPLETE = 'incomplete'


def _identifier(value: object, field_name: str, error_type: type[ValueError]) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise error_type(f'{field_name} must be a non-empty trimmed string')
    if len(value) > 128 or _IDENTIFIER.fullmatch(value) is None:
        raise error_type(f'{field_name} must be a bounded lowercase identifier')
    return value


def _text(value: object, field_name: str, error_type: type[ValueError]) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise error_type(f'{field_name} must be a non-empty trimmed string')
    if len(value) > MAX_REPORT_TEXT_LENGTH:
        raise error_type(f'{field_name} exceeds the report text bound')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise error_type(f'{field_name} contains invalid Unicode') from error
    lowered = value.lower()
    if '/home/' in lowered or 'pid=' in lowered or 'process id' in lowered:
        raise error_type(f'{field_name} cannot contain machine-local identity')
    return value


def _unique_typed_tuple(
    values: tuple,
    *,
    item_type: type,
    key,
    limit: int,
    field_name: str,
    error_type: type[ValueError],
) -> tuple:
    if not isinstance(values, tuple) or not all(type(item) is item_type for item in values):
        raise error_type(f'{field_name} must be an immutable typed tuple')
    if len(values) > limit:
        raise error_type(f'{field_name} exceeds the v1 bound')
    keys = tuple(key(item) for item in values)
    if len(keys) != len(set(keys)):
        raise error_type(f'{field_name} must contain unique identities')
    return values


@dataclass(frozen=True, slots=True)
class DevelopmentScenarioAssertion:
    assertion_id: str
    description: str
    required: bool = True

    def __post_init__(self) -> None:
        _identifier(
            self.assertion_id,
            'assertion_id',
            InvalidScenarioDefinitionError,
        )
        _text(
            self.description,
            'assertion description',
            InvalidScenarioDefinitionError,
        )
        if type(self.required) is not bool:
            raise InvalidScenarioDefinitionError('assertion required flag is invalid')


@dataclass(frozen=True, slots=True)
class DevelopmentScenarioStep:
    step_id: str
    operation: ScenarioOperation
    timeout_ms: int
    assertion_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.step_id, 'step_id', InvalidScenarioDefinitionError)
        if not isinstance(self.operation, ScenarioOperation):
            raise InvalidScenarioDefinitionError('unknown typed scenario operation')
        if (
            type(self.timeout_ms) is not int
            or not MIN_STEP_TIMEOUT_MS <= self.timeout_ms <= MAX_STEP_TIMEOUT_MS
        ):
            raise InvalidScenarioDefinitionError('step timeout is outside v1 bounds')
        if not isinstance(self.assertion_ids, tuple) or not self.assertion_ids:
            raise InvalidScenarioDefinitionError('a step requires assertion identities')
        for assertion_id in self.assertion_ids:
            _identifier(
                assertion_id,
                'step assertion_id',
                InvalidScenarioDefinitionError,
            )
        if len(self.assertion_ids) != len(set(self.assertion_ids)):
            raise InvalidScenarioDefinitionError('step assertion IDs must be unique')


@dataclass(frozen=True, slots=True, init=False)
class DevelopmentScenarioDefinition:
    scenario_id: str
    version: str
    category: ScenarioCategory
    description: str
    launch_profile: ScenarioLaunchProfile
    expected_safe_outcome: str
    authority: ScenarioAuthority
    steps: tuple[DevelopmentScenarioStep, ...]
    assertions: tuple[DevelopmentScenarioAssertion, ...]
    fingerprint: str

    def __init__(
        self,
        *,
        scenario_id: str,
        version: str,
        category: ScenarioCategory,
        description: str,
        launch_profile: ScenarioLaunchProfile,
        expected_safe_outcome: str,
        authority: ScenarioAuthority,
        steps: tuple[DevelopmentScenarioStep, ...],
        assertions: tuple[DevelopmentScenarioAssertion, ...],
    ) -> None:
        scenario_id = _identifier(
            scenario_id,
            'scenario_id',
            InvalidScenarioDefinitionError,
        )
        if type(version) is not str or _SEMVER.fullmatch(version) is None:
            raise InvalidScenarioDefinitionError('scenario version must be semantic')
        if not isinstance(category, ScenarioCategory):
            raise InvalidScenarioDefinitionError('scenario category is invalid')
        description = _text(
            description,
            'scenario description',
            InvalidScenarioDefinitionError,
        )
        if not isinstance(launch_profile, ScenarioLaunchProfile):
            raise InvalidScenarioDefinitionError('launch profile is invalid')
        expected_safe_outcome = _text(
            expected_safe_outcome,
            'expected safe outcome',
            InvalidScenarioDefinitionError,
        )
        if not isinstance(authority, ScenarioAuthority):
            raise InvalidScenarioDefinitionError('scenario authority is invalid')
        _unique_typed_tuple(
            steps,
            item_type=DevelopmentScenarioStep,
            key=lambda item: item.step_id,
            limit=MAX_STEPS_PER_SCENARIO,
            field_name='scenario steps',
            error_type=InvalidScenarioDefinitionError,
        )
        if not steps:
            raise InvalidScenarioDefinitionError('a scenario requires at least one step')
        _unique_typed_tuple(
            assertions,
            item_type=DevelopmentScenarioAssertion,
            key=lambda item: item.assertion_id,
            limit=MAX_ASSERTIONS_PER_SCENARIO,
            field_name='scenario assertions',
            error_type=InvalidScenarioDefinitionError,
        )
        if not assertions:
            raise InvalidScenarioDefinitionError('a scenario requires assertions')
        declared = {item.assertion_id for item in assertions}
        referenced = tuple(
            assertion_id for step in steps for assertion_id in step.assertion_ids
        )
        if set(referenced) != declared or len(referenced) != len(set(referenced)):
            raise InvalidScenarioDefinitionError(
                'every scenario assertion must be assigned to exactly one step'
            )
        document = {
            'assertions': [
                {
                    'description': item.description,
                    'id': item.assertion_id,
                    'required': item.required,
                }
                for item in assertions
            ],
            'authority': authority.value,
            'category': category.value,
            'description': description,
            'expected_safe_outcome': expected_safe_outcome,
            'framework': FRAMEWORK_ID,
            'launch_profile': launch_profile.value,
            'scenario_id': scenario_id,
            'steps': [
                {
                    'assertions': list(item.assertion_ids),
                    'id': item.step_id,
                    'operation': item.operation.value,
                    'timeout_ms': item.timeout_ms,
                }
                for item in steps
            ],
            'version': version,
        }
        object.__setattr__(self, 'scenario_id', scenario_id)
        object.__setattr__(self, 'version', version)
        object.__setattr__(self, 'category', category)
        object.__setattr__(self, 'description', description)
        object.__setattr__(self, 'launch_profile', launch_profile)
        object.__setattr__(self, 'expected_safe_outcome', expected_safe_outcome)
        object.__setattr__(self, 'authority', authority)
        object.__setattr__(self, 'steps', steps)
        object.__setattr__(self, 'assertions', assertions)
        object.__setattr__(
            self,
            'fingerprint',
            semantic_sha256('development-scenario', document),
        )


@dataclass(frozen=True, slots=True)
class DevelopmentScenarioAssertionResult:
    assertion_id: str
    outcome: AssertionOutcome
    detail: str
    reasons: tuple[ScenarioFailureReason, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.assertion_id, 'assertion_id', InvalidScenarioResultError)
        if not isinstance(self.outcome, AssertionOutcome):
            raise InvalidScenarioResultError('assertion outcome is invalid')
        _text(self.detail, 'assertion detail', InvalidScenarioResultError)
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, ScenarioFailureReason) for item in self.reasons
        ):
            raise InvalidScenarioResultError('assertion reasons are invalid')
        if len(self.reasons) > MAX_REASONS_PER_REPORT or len(self.reasons) != len(
            set(self.reasons)
        ):
            raise InvalidScenarioResultError('assertion reasons exceed bounds or repeat')
        if self.outcome is AssertionOutcome.PASS and self.reasons:
            raise InvalidScenarioResultError('passing assertion cannot carry failures')
        if self.outcome is AssertionOutcome.FAIL and not self.reasons:
            raise InvalidScenarioResultError('failed assertion requires a typed reason')


@dataclass(frozen=True, slots=True)
class DevelopmentScenarioStepResult:
    step_id: str
    operation: ScenarioOperation
    assertions: tuple[DevelopmentScenarioAssertionResult, ...]

    def __post_init__(self) -> None:
        _identifier(self.step_id, 'step result ID', InvalidScenarioResultError)
        if not isinstance(self.operation, ScenarioOperation):
            raise InvalidScenarioResultError('step result operation is invalid')
        _unique_typed_tuple(
            self.assertions,
            item_type=DevelopmentScenarioAssertionResult,
            key=lambda item: item.assertion_id,
            limit=MAX_ASSERTIONS_PER_SCENARIO,
            field_name='step result assertions',
            error_type=InvalidScenarioResultError,
        )
        if not self.assertions:
            raise InvalidScenarioResultError('a step result requires assertions')


@dataclass(frozen=True, slots=True)
class ScenarioObservedIdentity:
    kind: str
    value: str

    def __post_init__(self) -> None:
        _identifier(self.kind, 'identity kind', InvalidScenarioResultError)
        _identifier(self.value, 'observed identity', InvalidScenarioResultError)


@dataclass(frozen=True, slots=True)
class ScenarioPolicyDecision:
    layer: str
    outcome: str
    reason: str

    def __post_init__(self) -> None:
        _identifier(self.layer, 'policy layer', InvalidScenarioResultError)
        _identifier(self.outcome, 'policy outcome', InvalidScenarioResultError)
        _identifier(self.reason, 'policy reason', InvalidScenarioResultError)


@dataclass(frozen=True, slots=True)
class ScenarioSourceSummary:
    source_id: str
    provenance_kind: str
    interface: str

    def __post_init__(self) -> None:
        _identifier(self.source_id, 'source_id', InvalidScenarioResultError)
        _identifier(
            self.provenance_kind,
            'source provenance',
            InvalidScenarioResultError,
        )
        _identifier(self.interface, 'source interface', InvalidScenarioResultError)


@dataclass(frozen=True, slots=True)
class ScenarioCleanupResult:
    outcome: CleanupOutcome
    owned_processes_remaining: int
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, CleanupOutcome):
            raise InvalidScenarioResultError('cleanup outcome is invalid')
        if (
            type(self.owned_processes_remaining) is not int
            or not 0 <= self.owned_processes_remaining <= 256
        ):
            raise InvalidScenarioResultError('cleanup process count is invalid')
        _text(self.detail, 'cleanup detail', InvalidScenarioResultError)
        if (
            self.outcome is CleanupOutcome.CLEAN
            and self.owned_processes_remaining != 0
        ):
            raise InvalidScenarioResultError('clean cleanup cannot retain processes')


@dataclass(frozen=True, slots=True, init=False)
class DevelopmentScenarioReport:
    framework_id: str
    framework_fingerprint: str
    scenario_id: str
    scenario_version: str
    scenario_fingerprint: str
    report_id: str
    outcome: ScenarioOutcome
    launch_profile: ScenarioLaunchProfile
    assertion_results: tuple[DevelopmentScenarioAssertionResult, ...]
    failure_reasons: tuple[ScenarioFailureReason, ...]
    observed_identities: tuple[ScenarioObservedIdentity, ...]
    policy_decisions: tuple[ScenarioPolicyDecision, ...]
    development_authority_used: bool
    production_dispatch_count: int
    sources: tuple[ScenarioSourceSummary, ...]
    cleanup: ScenarioCleanupResult

    def __init__(
        self,
        *,
        definition: DevelopmentScenarioDefinition,
        outcome: ScenarioOutcome,
        assertion_results: tuple[DevelopmentScenarioAssertionResult, ...],
        failure_reasons: tuple[ScenarioFailureReason, ...],
        observed_identities: tuple[ScenarioObservedIdentity, ...],
        policy_decisions: tuple[ScenarioPolicyDecision, ...],
        development_authority_used: bool,
        production_dispatch_count: int,
        sources: tuple[ScenarioSourceSummary, ...],
        cleanup: ScenarioCleanupResult,
    ) -> None:
        if type(definition) is not DevelopmentScenarioDefinition:
            raise InvalidScenarioResultError('report requires a scenario definition')
        if not isinstance(outcome, ScenarioOutcome):
            raise InvalidScenarioResultError('scenario outcome is invalid')
        _unique_typed_tuple(
            assertion_results,
            item_type=DevelopmentScenarioAssertionResult,
            key=lambda item: item.assertion_id,
            limit=MAX_ASSERTIONS_PER_SCENARIO,
            field_name='report assertions',
            error_type=InvalidScenarioResultError,
        )
        expected_ids = {item.assertion_id for item in definition.assertions}
        if {item.assertion_id for item in assertion_results} != expected_ids:
            raise InvalidScenarioResultError('report assertions do not match definition')
        required = {
            item.assertion_id for item in definition.assertions if item.required
        }
        failed_required = any(
            item.assertion_id in required and item.outcome is AssertionOutcome.FAIL
            for item in assertion_results
        )
        cleanup_failed = (
            type(cleanup) is ScenarioCleanupResult
            and cleanup.outcome is CleanupOutcome.INCOMPLETE
        )
        if (outcome is ScenarioOutcome.FAIL) != (failed_required or cleanup_failed):
            raise InvalidScenarioResultError(
                'a failed required assertion or incomplete cleanup must fail the scenario'
            )
        if outcome is ScenarioOutcome.PASS and any(
            item.outcome is not AssertionOutcome.PASS for item in assertion_results
            if item.assertion_id in required
        ):
            raise InvalidScenarioResultError('passing scenario has unmet assertions')
        if not isinstance(failure_reasons, tuple) or not all(
            isinstance(item, ScenarioFailureReason) for item in failure_reasons
        ):
            raise InvalidScenarioResultError('report failure reasons are invalid')
        if len(failure_reasons) > MAX_REASONS_PER_REPORT or len(
            set(failure_reasons)
        ) != len(failure_reasons):
            raise InvalidScenarioResultError('report failure reasons exceed bounds')
        if outcome is ScenarioOutcome.PASS and failure_reasons:
            raise InvalidScenarioResultError('passing scenario cannot carry failures')
        _unique_typed_tuple(
            observed_identities,
            item_type=ScenarioObservedIdentity,
            key=lambda item: (item.kind, item.value),
            limit=MAX_OBSERVED_IDENTITIES,
            field_name='observed identities',
            error_type=InvalidScenarioResultError,
        )
        _unique_typed_tuple(
            policy_decisions,
            item_type=ScenarioPolicyDecision,
            key=lambda item: item.layer,
            limit=MAX_POLICY_DECISIONS,
            field_name='policy decisions',
            error_type=InvalidScenarioResultError,
        )
        if type(development_authority_used) is not bool:
            raise InvalidScenarioResultError('development authority flag is invalid')
        if definition.authority is ScenarioAuthority.NONE and development_authority_used:
            raise InvalidScenarioResultError('scenario used undeclared authority')
        if type(production_dispatch_count) is not int or not 0 <= production_dispatch_count <= 16:
            raise InvalidScenarioResultError('production dispatch count is invalid')
        _unique_typed_tuple(
            sources,
            item_type=ScenarioSourceSummary,
            key=lambda item: item.source_id,
            limit=MAX_SOURCE_SUMMARIES,
            field_name='source summaries',
            error_type=InvalidScenarioResultError,
        )
        if type(cleanup) is not ScenarioCleanupResult:
            raise InvalidScenarioResultError('report cleanup is invalid')
        assertion_document = [
            {
                'detail': item.detail,
                'id': item.assertion_id,
                'outcome': item.outcome.value,
                'reasons': [reason.value for reason in item.reasons],
            }
            for item in assertion_results
        ]
        document = {
            'assertions': assertion_document,
            'cleanup': {
                'detail': cleanup.detail,
                'outcome': cleanup.outcome.value,
                'owned_processes_remaining': cleanup.owned_processes_remaining,
            },
            'development_authority_used': development_authority_used,
            'failure_reasons': [item.value for item in failure_reasons],
            'framework': FRAMEWORK_ID,
            'observed_identities': [
                {'kind': item.kind, 'value': item.value}
                for item in observed_identities
            ],
            'outcome': outcome.value,
            'policy_decisions': [
                {
                    'layer': item.layer,
                    'outcome': item.outcome,
                    'reason': item.reason,
                }
                for item in policy_decisions
            ],
            'production_dispatch_count': production_dispatch_count,
            'scenario_fingerprint': definition.fingerprint,
            'sources': [
                {
                    'id': item.source_id,
                    'interface': item.interface,
                    'provenance': item.provenance_kind,
                }
                for item in sources
            ],
        }
        framework_fingerprint = semantic_sha256(
            'scenario-framework',
            {
                'framework': FRAMEWORK_ID,
                'limits': {
                    'assertions': MAX_ASSERTIONS_PER_SCENARIO,
                    'diagnostics': MAX_DIAGNOSTIC_RECORDS,
                    'reasons': MAX_REASONS_PER_REPORT,
                    'retained_ros_samples': MAX_RETAINED_ROS_SAMPLES,
                    'scenarios': MAX_SCENARIOS_PER_INVOCATION,
                    'steps': MAX_STEPS_PER_SCENARIO,
                },
                'version': FRAMEWORK_VERSION,
            },
        )
        object.__setattr__(self, 'framework_id', FRAMEWORK_ID)
        object.__setattr__(self, 'framework_fingerprint', framework_fingerprint)
        object.__setattr__(self, 'scenario_id', definition.scenario_id)
        object.__setattr__(self, 'scenario_version', definition.version)
        object.__setattr__(self, 'scenario_fingerprint', definition.fingerprint)
        object.__setattr__(self, 'report_id', semantic_sha256('scenario-report', document))
        object.__setattr__(self, 'outcome', outcome)
        object.__setattr__(self, 'launch_profile', definition.launch_profile)
        object.__setattr__(self, 'assertion_results', assertion_results)
        object.__setattr__(self, 'failure_reasons', failure_reasons)
        object.__setattr__(self, 'observed_identities', observed_identities)
        object.__setattr__(self, 'policy_decisions', policy_decisions)
        object.__setattr__(self, 'development_authority_used', development_authority_used)
        object.__setattr__(self, 'production_dispatch_count', production_dispatch_count)
        object.__setattr__(self, 'sources', sources)
        object.__setattr__(self, 'cleanup', cleanup)

    def as_dict(self) -> dict[str, object]:
        """Return bounded JSON-ready report content without runtime-local identity."""
        return {
            'assertions': [
                {
                    'detail': item.detail,
                    'id': item.assertion_id,
                    'outcome': item.outcome.value,
                    'reasons': [reason.value for reason in item.reasons],
                }
                for item in self.assertion_results
            ],
            'cleanup': {
                'detail': self.cleanup.detail,
                'outcome': self.cleanup.outcome.value,
                'owned_processes_remaining': self.cleanup.owned_processes_remaining,
            },
            'development_authority_used': self.development_authority_used,
            'failure_reasons': [item.value for item in self.failure_reasons],
            'framework_fingerprint': self.framework_fingerprint,
            'framework_id': self.framework_id,
            'launch_profile': self.launch_profile.value,
            'observed_identities': [
                {'kind': item.kind, 'value': item.value}
                for item in self.observed_identities
            ],
            'outcome': self.outcome.value,
            'policy_decisions': [
                {
                    'layer': item.layer,
                    'outcome': item.outcome,
                    'reason': item.reason,
                }
                for item in self.policy_decisions
            ],
            'production_dispatch_count': self.production_dispatch_count,
            'report_id': self.report_id,
            'scenario_fingerprint': self.scenario_fingerprint,
            'scenario_id': self.scenario_id,
            'scenario_version': self.scenario_version,
            'sources': [
                {
                    'id': item.source_id,
                    'interface': item.interface,
                    'provenance': item.provenance_kind,
                }
                for item in self.sources
            ],
        }
