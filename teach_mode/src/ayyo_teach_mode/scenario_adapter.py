"""Read-only adapter from immutable Stage-6 reports to demonstration evidence."""

from __future__ import annotations

from ayyo_developmental_scenarios import (
    AssertionOutcome,
    DevelopmentScenarioReport,
    FRAMEWORK_ID,
    ScenarioOutcome,
    scenario_by_id,
)

from .capture import DemonstrationRecorder
from .errors import ScenarioDemonstrationAdapterError
from .models import (
    AYYO_ROBOT_ID,
    DemonstrationActionAuthority,
    DemonstrationActionDisposition,
    DemonstrationActionKind,
    DemonstrationActionReference,
    DemonstrationActionUnit,
    DemonstrationAnnotation,
    DemonstrationAnnotationKind,
    DemonstrationClockKind,
    DemonstrationEvent,
    DemonstrationEventType,
    DemonstrationObservationReference,
    DemonstrationOutcome,
    DemonstrationOutcomeStatus,
    DemonstrationProvenance,
    DemonstrationSourceKind,
    DemonstrationSourceTimeRange,
    ObservationReferenceKind,
    ReferenceEvidenceStatus,
)


_DEVELOPMENT_MOTION_SCENARIO = 'development-only-neck-actuation'
_PRODUCTION_DEFER_SCENARIO = 'production-physical-request-deferred'
_INVALID_COMMAND_SCENARIO = 'invalid-development-command-rejected'


def _verified_report(report: object) -> DevelopmentScenarioReport:
    if type(report) is not DevelopmentScenarioReport:
        raise ScenarioDemonstrationAdapterError(
            'adapter requires one immutable Stage-6 report'
        )
    try:
        definition = scenario_by_id(report.scenario_id)
        rebuilt = DevelopmentScenarioReport(
            definition=definition,
            outcome=report.outcome,
            assertion_results=report.assertion_results,
            failure_reasons=report.failure_reasons,
            observed_identities=report.observed_identities,
            policy_decisions=report.policy_decisions,
            development_authority_used=report.development_authority_used,
            production_dispatch_count=report.production_dispatch_count,
            sources=report.sources,
            cleanup=report.cleanup,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise ScenarioDemonstrationAdapterError(
            'Stage-6 report structure or identity is invalid'
        ) from error
    if report.framework_id != FRAMEWORK_ID or rebuilt != report:
        raise ScenarioDemonstrationAdapterError(
            'Stage-6 report integrity or catalog binding failed'
        )
    robot_values = tuple(
        item.value for item in report.observed_identities if item.kind == 'robot'
    )
    if robot_values != (AYYO_ROBOT_ID,):
        raise ScenarioDemonstrationAdapterError(
            'Stage-6 report must contain one canonical Ayyo robot identity'
        )
    return report


def _report_reference(report: DevelopmentScenarioReport):
    report_status = {
        ScenarioOutcome.PASS: ReferenceEvidenceStatus.PASS,
        ScenarioOutcome.FAIL: ReferenceEvidenceStatus.FAIL,
        ScenarioOutcome.NOT_APPLICABLE: ReferenceEvidenceStatus.NOT_APPLICABLE,
    }[report.outcome]
    return DemonstrationObservationReference(
        kind=ObservationReferenceKind.SCENARIO_REPORT,
        reference_id=report.report_id,
        fingerprint=report.scenario_fingerprint,
        status=report_status,
        provenance_kind='development-scenario',
        interface_id=report.framework_id,
    )


def _identity_references(report: DevelopmentScenarioReport):
    return tuple(
        DemonstrationObservationReference(
            kind=(
                ObservationReferenceKind.ROBOT_BODY_STATE
                if item.kind == 'robot'
                else ObservationReferenceKind.PUBLIC_EVIDENCE
            ),
            reference_id=item.value,
            status=ReferenceEvidenceStatus.OBSERVED,
        )
        for item in report.observed_identities
    )


def _source_references(report: DevelopmentScenarioReport):
    return tuple(
        DemonstrationObservationReference(
            kind=ObservationReferenceKind.SENSOR_EVIDENCE,
            reference_id=item.source_id,
            status=ReferenceEvidenceStatus.OBSERVED,
            provenance_kind=item.provenance_kind,
            interface_id=item.interface,
        )
        for item in report.sources
    )


def _assertion_reference(report: DevelopmentScenarioReport, assertion_id: str):
    match = tuple(
        item for item in report.assertion_results if item.assertion_id == assertion_id
    )
    if len(match) != 1:
        raise ScenarioDemonstrationAdapterError(
            f'Stage-6 report is missing assertion evidence: {assertion_id}'
        )
    status = {
        AssertionOutcome.PASS: ReferenceEvidenceStatus.PASS,
        AssertionOutcome.FAIL: ReferenceEvidenceStatus.FAIL,
        AssertionOutcome.NOT_APPLICABLE: ReferenceEvidenceStatus.NOT_APPLICABLE,
    }[match[0].outcome]
    return DemonstrationObservationReference(
        kind=ObservationReferenceKind.SCENARIO_ASSERTION,
        reference_id=assertion_id,
        fingerprint=report.report_id,
        status=status,
        provenance_kind='development-scenario',
        interface_id=report.framework_id,
    )


def _action(
    report: DevelopmentScenarioReport,
    *,
    action_id: str,
    kind: DemonstrationActionKind,
    authority: DemonstrationActionAuthority,
    disposition: DemonstrationActionDisposition,
    reason_code: str | None = None,
    target_id: str | None = None,
    target_value: float | None = None,
):
    return DemonstrationActionReference(
        action_id=action_id,
        kind=kind,
        authority=authority,
        disposition=disposition,
        evidence_ref=report.report_id,
        reason_code=reason_code,
        target_id=target_id,
        target_value=target_value,
        target_unit=(
            DemonstrationActionUnit.RADIAN
            if target_value is not None
            else DemonstrationActionUnit.NONE
        ),
    )


def _policy_decision(report: DevelopmentScenarioReport, layer: str):
    matches = tuple(item for item in report.policy_decisions if item.layer == layer)
    if len(matches) != 1:
        raise ScenarioDemonstrationAdapterError(
            f'Stage-6 report is missing one exact {layer} policy decision'
        )
    return matches[0]


def _annotation(kind: DemonstrationAnnotationKind, text: str):
    return DemonstrationAnnotation(kind=kind, text=text)


def _event(
    index: int,
    event_id: str,
    event_type: DemonstrationEventType,
    *,
    observations=(),
    actions=(),
    annotations=(),
):
    return DemonstrationEvent(
        event_id=event_id,
        sequence_index=index,
        event_type=event_type,
        observation_references=observations,
        action_references=actions,
        annotations=annotations,
    )


def _development_motion_events(report: DevelopmentScenarioReport):
    return (
        _event(
            0,
            'initial-robot-state',
            DemonstrationEventType.OBSERVATION,
            observations=(
                _report_reference(report),
                *_identity_references(report),
                *_source_references(report),
                _assertion_reference(report, 'initial-neck-observed'),
            ),
        ),
        _event(
            1,
            'development-neck-target-requested',
            DemonstrationEventType.DEVELOPMENT_ACTION,
            actions=(
                _action(
                    report,
                    action_id='development-neck-target-request',
                    kind=DemonstrationActionKind.DEVELOPMENT_JOINT_POSITION,
                    authority=DemonstrationActionAuthority.DEVELOPMENT_ONLY,
                    disposition=DemonstrationActionDisposition.REQUESTED,
                    target_id='neck_yaw_joint',
                    target_value=0.1,
                ),
            ),
            annotations=(
                _annotation(
                    DemonstrationAnnotationKind.LIMITATION,
                    'Historical DEVELOPMENT-only request evidence; it grants no production authority.',
                ),
            ),
        ),
        _event(
            2,
            'development-neck-target-observed',
            DemonstrationEventType.OBSERVATION,
            observations=(
                _assertion_reference(report, 'development-command-completed'),
                _assertion_reference(report, 'neck-target-observed'),
                _assertion_reference(report, 'world-model-neck-updated'),
                _assertion_reference(report, 'production-authority-unused'),
            ),
            actions=(
                _action(
                    report,
                    action_id='development-neck-target-result',
                    kind=DemonstrationActionKind.DEVELOPMENT_JOINT_POSITION,
                    authority=DemonstrationActionAuthority.DEVELOPMENT_ONLY,
                    disposition=DemonstrationActionDisposition.COMPLETED,
                    target_id='neck_yaw_joint',
                    target_value=0.1,
                ),
            ),
        ),
        _event(
            3,
            'development-neck-reset-observed',
            DemonstrationEventType.DEVELOPMENT_ACTION,
            observations=(
                _assertion_reference(report, 'neck-restored-neutral'),
                _assertion_reference(report, 'development-cleanup-complete'),
            ),
            actions=(
                _action(
                    report,
                    action_id='development-neck-neutral-reset',
                    kind=DemonstrationActionKind.DEVELOPMENT_RESET,
                    authority=DemonstrationActionAuthority.DEVELOPMENT_ONLY,
                    disposition=DemonstrationActionDisposition.COMPLETED,
                    target_id='neck_yaw_joint',
                    target_value=0.0,
                ),
            ),
        ),
        _event(
            4,
            'demonstration-outcome',
            DemonstrationEventType.OUTCOME,
            annotations=(
                _annotation(
                    DemonstrationAnnotationKind.OUTCOME_REASON,
                    'The bounded DEVELOPMENT neck target and neutral reset were observed.',
                ),
            ),
        ),
    )


def _production_defer_events(report: DevelopmentScenarioReport):
    executive = _policy_decision(report, 'executive')
    safety = _policy_decision(report, 'safety')
    skill = _policy_decision(report, 'skill-manager')
    runtime = _policy_decision(report, 'runtime-bridge')
    if (
        safety.outcome != 'deferred'
        or skill.outcome != 'ineligible'
        or runtime.outcome != 'deferred'
        or report.production_dispatch_count != 0
        or report.development_authority_used
    ):
        raise ScenarioDemonstrationAdapterError(
            'production scenario no longer proves DEFERRED and zero dispatch'
        )
    return (
        _event(
            0,
            'production-neck-request',
            DemonstrationEventType.INTENT,
            observations=(_report_reference(report), *_identity_references(report)),
            actions=(
                _action(
                    report,
                    action_id='production-neck-position-request',
                    kind=DemonstrationActionKind.EXECUTIVE_REQUEST,
                    authority=DemonstrationActionAuthority.NONE,
                    disposition=DemonstrationActionDisposition.REQUESTED,
                    target_id='neck_yaw_joint',
                    target_value=0.1,
                ),
            ),
        ),
        _event(
            1,
            'executive-proposal',
            DemonstrationEventType.EXECUTIVE_PROPOSAL,
            observations=(
                _assertion_reference(report, 'executive-proposal-structured'),
            ),
            actions=(
                _action(
                    report,
                    action_id='executive-neck-proposal',
                    kind=DemonstrationActionKind.EXECUTIVE_PROPOSAL,
                    authority=DemonstrationActionAuthority.NONE,
                    disposition=DemonstrationActionDisposition.PROPOSED,
                    reason_code=executive.reason,
                ),
            ),
        ),
        _event(
            2,
            'safety-decision',
            DemonstrationEventType.SAFETY_DECISION,
            observations=(_assertion_reference(report, 'safety-deferred'),),
            actions=(
                _action(
                    report,
                    action_id='safety-neck-decision',
                    kind=DemonstrationActionKind.SAFETY_DECISION,
                    authority=DemonstrationActionAuthority.NONE,
                    disposition=DemonstrationActionDisposition.DEFERRED,
                    reason_code=safety.reason,
                ),
            ),
        ),
        _event(
            3,
            'skill-binding',
            DemonstrationEventType.SKILL_BINDING,
            observations=(_assertion_reference(report, 'skill-binding-ineligible'),),
            actions=(
                _action(
                    report,
                    action_id='skill-neck-binding',
                    kind=DemonstrationActionKind.SKILL_BINDING,
                    authority=DemonstrationActionAuthority.NONE,
                    disposition=DemonstrationActionDisposition.INELIGIBLE,
                    reason_code=skill.reason,
                ),
            ),
        ),
        _event(
            4,
            'runtime-nondispatch',
            DemonstrationEventType.RUNTIME_RESULT,
            observations=(
                _assertion_reference(report, 'runtime-not-dispatchable'),
                _assertion_reference(report, 'production-dispatch-zero'),
                _assertion_reference(report, 'development-service-not-called'),
                _assertion_reference(report, 'controller-command-not-issued'),
            ),
            actions=(
                _action(
                    report,
                    action_id='runtime-neck-eligibility',
                    kind=DemonstrationActionKind.RUNTIME_RESULT,
                    authority=DemonstrationActionAuthority.NONE,
                    disposition=DemonstrationActionDisposition.DEFERRED,
                    reason_code=runtime.reason,
                ),
                _action(
                    report,
                    action_id='production-neck-nondispatch',
                    kind=DemonstrationActionKind.RUNTIME_RESULT,
                    authority=DemonstrationActionAuthority.NONE,
                    disposition=DemonstrationActionDisposition.NOT_DISPATCHED,
                    reason_code='production-dispatch-zero',
                ),
            ),
        ),
        _event(
            5,
            'stationary-production-target',
            DemonstrationEventType.OBSERVATION,
            observations=(
                *_source_references(report),
                _assertion_reference(report, 'requested-joint-stationary'),
            ),
        ),
        _event(
            6,
            'demonstration-outcome',
            DemonstrationEventType.OUTCOME,
            annotations=(
                _annotation(
                    DemonstrationAnnotationKind.OUTCOME_REASON,
                    'Safety remained DEFERRED and production movement remained exactly zero.',
                ),
            ),
        ),
    )


def _invalid_command_events(report: DevelopmentScenarioReport):
    return (
        _event(
            0,
            'pre-command-state',
            DemonstrationEventType.OBSERVATION,
            observations=(
                _report_reference(report),
                *_identity_references(report),
                *_source_references(report),
                _assertion_reference(report, 'pre-command-state-observed'),
            ),
        ),
        _event(
            1,
            'invalid-development-command',
            DemonstrationEventType.DEVELOPMENT_ACTION,
            observations=(
                _assertion_reference(report, 'invalid-command-rejected'),
                _assertion_reference(report, 'typed-rejection-reason'),
                _assertion_reference(report, 'invalid-not-clamped'),
            ),
            actions=(
                _action(
                    report,
                    action_id='invalid-development-neck-request',
                    kind=DemonstrationActionKind.DEVELOPMENT_JOINT_POSITION,
                    authority=DemonstrationActionAuthority.DEVELOPMENT_ONLY,
                    disposition=DemonstrationActionDisposition.REQUESTED,
                    target_id='neck_yaw_joint',
                    target_value=1.3,
                ),
                _action(
                    report,
                    action_id='invalid-development-neck-rejection',
                    kind=DemonstrationActionKind.DEVELOPMENT_JOINT_POSITION,
                    authority=DemonstrationActionAuthority.DEVELOPMENT_ONLY,
                    disposition=DemonstrationActionDisposition.REJECTED,
                    reason_code='above-maximum',
                    target_id='neck_yaw_joint',
                    target_value=1.3,
                ),
            ),
        ),
        _event(
            2,
            'post-rejection-state',
            DemonstrationEventType.OBSERVATION,
            observations=(
                _assertion_reference(report, 'invalid-target-not-reached'),
                _assertion_reference(report, 'world-model-not-fabricated'),
                _assertion_reference(report, 'controller-remains-healthy'),
                _assertion_reference(report, 'post-rejection-query-works'),
            ),
        ),
        _event(
            3,
            'demonstration-outcome',
            DemonstrationEventType.OUTCOME,
            annotations=(
                _annotation(
                    DemonstrationAnnotationKind.OUTCOME_REASON,
                    'The invalid DEVELOPMENT request was rejected with no invalid movement.',
                ),
            ),
        ),
    )


def _generic_events(report: DevelopmentScenarioReport):
    observations = (
        _report_reference(report),
        *_identity_references(report),
        *_source_references(report),
    )
    if len(observations) > 16:
        raise ScenarioDemonstrationAdapterError(
            'Stage-6 report references exceed the Teach Mode event bound'
        )
    return (
        _event(
            0,
            'scenario-evidence',
            DemonstrationEventType.OBSERVATION,
            observations=observations,
        ),
        _event(
            1,
            'demonstration-outcome',
            DemonstrationEventType.OUTCOME,
            annotations=(
                _annotation(
                    DemonstrationAnnotationKind.OUTCOME_REASON,
                    'The explicit episode preserves the completed Stage-6 scenario result.',
                ),
            ),
        ),
    )


def _outcome_for(report: DevelopmentScenarioReport):
    if report.outcome is ScenarioOutcome.FAIL:
        return DemonstrationOutcome(
            DemonstrationOutcomeStatus.FAILURE,
            tuple(item.value for item in report.failure_reasons) or ('scenario-failed',),
            'The source Stage-6 scenario reported failure.',
        )
    if report.outcome is ScenarioOutcome.NOT_APPLICABLE:
        return DemonstrationOutcome(
            DemonstrationOutcomeStatus.INCOMPLETE,
            ('scenario-not-applicable',),
            'The source Stage-6 scenario did not provide a completed demonstration.',
        )
    if report.scenario_id == _PRODUCTION_DEFER_SCENARIO:
        return DemonstrationOutcome(
            DemonstrationOutcomeStatus.DEFERRED,
            ('physical-movement-information-unavailable', 'production-dispatch-zero'),
            'The request was deferred by Safety and no production movement occurred.',
        )
    if report.scenario_id == _INVALID_COMMAND_SCENARIO:
        return DemonstrationOutcome(
            DemonstrationOutcomeStatus.REJECTED,
            ('above-maximum', 'invalid-target-not-reached'),
            'The invalid DEVELOPMENT command was rejected without invalid movement.',
        )
    return DemonstrationOutcome(
        DemonstrationOutcomeStatus.SUCCESS,
        ('scenario-pass',),
        'The exact bounded Stage-6 scenario completed with its expected safe result.',
    )


def capture_development_scenario_report(
    report: DevelopmentScenarioReport,
    *,
    teacher_source_ref: str | None = None,
):
    """Capture one verified Stage-6 report as immutable historical evidence."""
    report = _verified_report(report)
    if report.scenario_id == _DEVELOPMENT_MOTION_SCENARIO:
        events = _development_motion_events(report)
    elif report.scenario_id == _PRODUCTION_DEFER_SCENARIO:
        events = _production_defer_events(report)
    elif report.scenario_id == _INVALID_COMMAND_SCENARIO:
        events = _invalid_command_events(report)
    else:
        events = _generic_events(report)
    recorder = DemonstrationRecorder()
    session = recorder.begin(
        source_kind=DemonstrationSourceKind.DEVELOPMENT_SCENARIO,
        robot_id=AYYO_ROBOT_ID,
        source_time=DemonstrationSourceTimeRange(
            DemonstrationClockKind.UNAVAILABLE,
            None,
            None,
        ),
        provenance=DemonstrationProvenance(
            source_ref=report.report_id,
            source_fingerprint=report.scenario_fingerprint,
            teacher_source_ref=teacher_source_ref,
        ),
    )
    for event in events:
        session.append(event)
    return session.finish(_outcome_for(report))
