#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""TEST-ONLY deterministic visual evaluation and bounded trust-path proof."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tracemalloc

from ayyo_perception import (
    AdmissionStatus,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_working_memory import IngestionStatus, WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    JointContract,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotJointCatalog,
    SensorAvailability,
    VisualFrameObservation,
)
from ayyo_visual_evaluation import (
    DeterministicFixtureInvoker,
    FIXTURE_CAMERA,
    InMemoryVisualRecordedSource,
    MalformedBoxFixtureProducer,
    OwnedProcessVisualProducerInvoker,
    SlowFixtureProducer,
    VisualEvaluationConfigurationError,
    VisualEvaluationInput,
    VisualEvaluationSample,
    VisualProducerEvaluator,
    VisualProducerRegistry,
    WrongModelFixtureProducer,
    WrongSourceFixtureProducer,
    fixture_bundle,
    fixture_bundle_for_live_profile,
    fixture_detection,
)


CYCLE_COUNT = 5_000
WIDTH = 32
HEIGHT = 24
RGB8 = bytes(index % 251 for index in range(WIDTH * HEIGHT * 3))
RGB8_SHA256 = sha256(RGB8).hexdigest()
SIMULATION_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.SIMULATION,
    'ros.camera.head.simulation.evaluation-fixture.v1',
    ObservationClock.ROS_SIMULATION_TIME,
    ObservationTransport.ROS2,
    'sensor-msgs.image-camera-info.v1',
)
PHYSICAL_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    'ros.camera.head.physical.evaluation-fixture.v1',
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    'sensor-msgs.image-camera-info.v1',
)


def _evaluator(bundle, invoker=None) -> VisualProducerEvaluator:
    registry = VisualProducerRegistry()
    registry.register(bundle.registration)
    return VisualProducerEvaluator(
        registry,
        DeterministicFixtureInvoker() if invoker is None else invoker,
    )


def _evaluate_adversarial(adapter, *, owned: bool = False):
    bundle = fixture_bundle(sample_count=1, adapter=adapter)
    outcome = _evaluator(
        bundle,
        OwnedProcessVisualProducerInvoker() if owned else None,
    ).evaluate(
        producer_id=bundle.manifest.producer.producer_id,
        dataset=bundle.dataset,
        source=bundle.source,
        policy=bundle.policy,
        run_id='fixture.adversarial.v1',
    )
    assert not outcome.admissions
    return outcome


def _frame(index: int, provenance=SIMULATION_PROVENANCE) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=FIXTURE_CAMERA,
        width=WIDTH,
        height=HEIGHT,
        encoding='rgb8',
        step=WIDTH * 3,
        data_size_bytes=len(RGB8),
        is_bigendian=False,
        calibration_id='camera-calibration-sha256-' + '9' * 64,
        observed_at_ns=2_000_000_000 + index * 2_000_000,
        provenance=provenance,
        availability=SensorAvailability.AVAILABLE,
    )


def _input(frame: VisualFrameObservation, index: int) -> VisualEvaluationInput:
    sample = VisualEvaluationSample(
        sample_id=f'fixture.qualified-live.{index:05d}',
        sequence_index=0,
        frame=frame,
        asset_reference='live/ephemeral-not-retained.rgb8',
        asset_sha256=RGB8_SHA256,
        asset_size_bytes=len(RGB8),
        scenario_ids=('fixture.bounded-live-cycle.v1',),
        expected_detections=(fixture_detection(frame),),
    )
    return VisualEvaluationInput(sample=sample, rgb8=RGB8)


def _owned_visual_evaluation_processes() -> tuple[int, ...]:
    marker = b'AYYO_VISUAL_EVALUATION_RUN_ID='
    found = []
    for environment in Path('/proc').glob('[0-9]*/environ'):
        try:
            entries = environment.read_bytes().split(b'\0')
        except OSError:
            continue
        if any(entry.startswith(marker) for entry in entries):
            found.append(int(environment.parent.name))
    return tuple(sorted(found))


def main() -> None:
    qualification = fixture_bundle_for_live_profile(
        SIMULATION_PROVENANCE,
        width=WIDTH,
        height=HEIGHT,
    )
    first = _evaluator(qualification).evaluate(
        producer_id=qualification.manifest.producer.producer_id,
        dataset=qualification.dataset,
        source=qualification.source,
        policy=qualification.policy,
        run_id='fixture.reproducibility.first.v1',
    )
    evaluator = _evaluator(qualification)
    second = evaluator.evaluate(
        producer_id=qualification.manifest.producer.producer_id,
        dataset=qualification.dataset,
        source=qualification.source,
        policy=qualification.policy,
        run_id='fixture.reproducibility.second.v1',
    )
    assert first.report.semantic_sha256 == second.report.semantic_sha256
    assert first.observations == second.observations

    wrong_model = _evaluate_adversarial(WrongModelFixtureProducer())
    wrong_source = _evaluate_adversarial(WrongSourceFixtureProducer())
    malformed = _evaluate_adversarial(MalformedBoxFixtureProducer())
    timeout = _evaluate_adversarial(SlowFixtureProducer(), owned=True)
    assert _owned_visual_evaluation_processes() == ()

    corrupt_bundle = fixture_bundle(sample_count=1)
    corrupt = _evaluator(corrupt_bundle).evaluate(
        producer_id=corrupt_bundle.manifest.producer.producer_id,
        dataset=corrupt_bundle.dataset,
        source=InMemoryVisualRecordedSource(
            {'samples/shared.rgb8': b'x' * 24}
        ),
        policy=corrupt_bundle.policy,
        run_id='fixture.corrupt.v1',
    )
    assert not corrupt.admissions
    recovered = _evaluator(corrupt_bundle).evaluate(
        producer_id=corrupt_bundle.manifest.producer.producer_id,
        dataset=corrupt_bundle.dataset,
        source=corrupt_bundle.source,
        policy=corrupt_bundle.policy,
        run_id='fixture.recovered.v1',
    )
    assert len(recovered.admissions) == 1

    physical_substitution = False
    try:
        evaluator.invoke_qualified_input(
            producer_id=qualification.manifest.producer.producer_id,
            evaluation_input=_input(_frame(0, PHYSICAL_PROVENANCE), 0),
            policy=qualification.policy,
            qualified_report=second.report,
        )
    except VisualEvaluationConfigurationError:
        physical_substitution = True
    assert physical_substitution

    catalog = RobotJointCatalog(
        robot_id=AYYO_ROBOT_ID,
        joints=(
            JointContract(
                'neck_yaw_joint',
                'revolute',
                -1.2,
                1.2,
                1.5,
                8.0,
            ),
        ),
    )
    source_contract = PerceptionSourceContract(
        qualification.dataset.sensor,
        SIMULATION_PROVENANCE,
    )
    trust = PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.ROS_SIMULATION_TIME,
            sources=(source_contract,),
            freshness_ns=100_000_000,
            retention_ttl_ns=500_000_000,
            permitted_future_skew_ns=5_000_000,
            visual_interpretation_producers=(qualification.manifest.producer,),
            visual_evaluation_requirements=(second.admissions[0].requirement,),
        )
    )
    memory = WorkingMemory(
        catalog,
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.ROS_SIMULATION_TIME,
            allowed_provenance=(SIMULATION_PROVENANCE,),
            sensors=(qualification.dataset.sensor,),
            freshness_ns=100_000_000,
            retention_ttl_ns=500_000_000,
            permitted_future_skew_ns=5_000_000,
            recent_evidence_capacity=16,
            visual_interpretation_producers=(qualification.manifest.producer,),
            visual_evaluation_requirements=(second.admissions[0].requirement,),
        ),
    )

    receipt = 0
    last_sealed = None
    tracemalloc.start()
    try:
        for index in range(CYCLE_COUNT):
            frame = _frame(index)
            now_ns = frame.observed_at_ns + 1_000_000
            receipt += 1
            source_admission = trust.admit(
                frame,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt,
            )
            assert source_admission.status is AdmissionStatus.ACCEPTED
            assert memory.ingest(
                source_admission.observation,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt,
            ).status is IngestionStatus.ACCEPTED
            last_sealed = evaluator.invoke_qualified_input(
                producer_id=qualification.manifest.producer.producer_id,
                evaluation_input=_input(frame, index),
                policy=qualification.policy,
                qualified_report=second.report,
            )
            assert trust.authorize_evaluated_visual(last_sealed)
            receipt += 1
            interpreted = trust.admit(
                last_sealed.observation,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt,
            )
            assert interpreted.status is AdmissionStatus.ACCEPTED
            assert memory.ingest(
                interpreted.observation,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt,
            ).status is IngestionStatus.ACCEPTED
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert last_sealed is not None
    assert trust.authorize_evaluated_visual(last_sealed)
    receipt += 1
    duplicate = trust.admit(
        last_sealed.observation,
        now_ns=last_sealed.observation.result_at_ns,
        received_at_monotonic_ns=receipt,
    )
    final_now = last_sealed.observation.result_at_ns
    first_query = memory.current_snapshot(now_ns=final_now)
    second_query = memory.current_snapshot(now_ns=final_now)
    stats = memory.stats(now_ns=final_now)
    trust_stats = trust.stats()
    interpretations = first_query.robot.visual_interpretation_states
    assert duplicate.status.value == 'duplicate'
    assert first_query.snapshot_id == second_query.snapshot_id
    assert first_query.version == second_query.version
    assert len(interpretations) == 1
    assert interpretations[0].observation.evaluation_reference is not None
    assert stats.current_visual_count == 1
    assert stats.current_visual_interpretation_count == 1
    assert stats.recent_evidence_count == 16
    assert stats.retained_unique_observation_count <= 18
    assert trust_stats.tracked_visual_source_count == 64
    assert trust_stats.tracked_evaluated_visual_count == 0
    assert peak_bytes < 64 * 1_024 * 1_024
    assert 'pixels' not in repr(first_query.robot.document()).lower()

    summary = {
        'accepted_count': trust_stats.accepted_count,
        'corrupt_sample_rejected': not corrupt.admissions,
        'current_evaluation_reference_count': 1,
        'current_interpretation_count': stats.current_visual_interpretation_count,
        'cycle_count': CYCLE_COUNT,
        'duplicate_bounded': duplicate.status.value == 'duplicate',
        'malformed_output_decision': malformed.report.decision.value,
        'model_provenance_sha256': second.report.model.provenance_sha256,
        'owned_evaluation_processes': list(_owned_visual_evaluation_processes()),
        'physical_source_substitution_rejected': physical_substitution,
        'recent_bounded_state_size': stats.recent_evidence_count,
        'recovered_after_corruption': len(recovered.admissions) == 1,
        'rejected_count': trust_stats.rejected_count,
        'report_semantic_sha256': second.report.semantic_sha256,
        'reproducible': first.report.semantic_sha256 == second.report.semantic_sha256,
        'retained_unique_state_count': stats.retained_unique_observation_count,
        'semantic_reference_count': len(
            {state.observation.evaluation_reference for state in interpretations}
        ),
        'timeout_decision': timeout.report.decision.value,
        'traced_python_current_bytes': current_bytes,
        'traced_python_peak_bytes': peak_bytes,
        'wrong_model_decision': wrong_model.report.decision.value,
        'wrong_source_decision': wrong_source.report.decision.value,
    }
    print(
        'VISUAL_EVALUATION_FIXTURE_RESULT='
        + json.dumps(summary, separators=(',', ':'), sort_keys=True)
    )


if __name__ == '__main__':
    main()
