#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""TEST-ONLY adversarial and resource proof for visual interpretation."""

from __future__ import annotations

import json
import math

from ayyo_perception import (
    AdmissionStatus,
    DeterministicVisualReferenceAdapter,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
    REFERENCE_VISUAL_PRODUCER,
)
from ayyo_working_memory import IngestionStatus, WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    JointContract,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotJointCatalog,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
    VisualInterpretationObservation,
    WorldModelValidationError,
)


CAMERA = SensorIdentity(
    'ayyo.camera.head.rgb.v1',
    SensorKind.RGB_CAMERA,
    'head_camera_optical_frame',
)
SIMULATION_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.SIMULATION,
    'ros.camera.head.simulation.gz-harmonic.v1',
    ObservationClock.ROS_SIMULATION_TIME,
    ObservationTransport.ROS2,
    'sensor-msgs.image-camera-info.v1',
)
PHYSICAL_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    'ros.camera.head.physical.standard-driver.v1',
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    'sensor-msgs.image-camera-info.v1',
)


def frame(time_ns: int, **overrides) -> VisualFrameObservation:
    values = {
        'robot_id': AYYO_ROBOT_ID,
        'sensor': CAMERA,
        'width': 32,
        'height': 24,
        'encoding': 'rgb8',
        'step': 96,
        'data_size_bytes': 2304,
        'is_bigendian': False,
        'calibration_id': 'camera-calibration-sha256-' + '1' * 64,
        'observed_at_ns': time_ns,
        'provenance': SIMULATION_PROVENANCE,
        'availability': SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualFrameObservation(**values)


def result_with(result, **overrides) -> VisualInterpretationObservation:
    values = {
        'robot_id': result.robot_id,
        'sensor': result.sensor,
        'reference_frame_id': result.reference_frame_id,
        'source_visual_observation_id': result.source_visual_observation_id,
        'source_visual_fingerprint': result.source_visual_fingerprint,
        'observed_at_ns': result.observed_at_ns,
        'result_at_ns': result.result_at_ns,
        'producer': result.producer,
        'detections': result.detections,
        'provenance': result.provenance,
        'availability': result.availability,
    }
    values.update(overrides)
    return VisualInterpretationObservation(**values)


def main() -> None:
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
    trust = PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.ROS_SIMULATION_TIME,
            sources=(PerceptionSourceContract(CAMERA, SIMULATION_PROVENANCE),),
            freshness_ns=100,
            retention_ttl_ns=10_000,
            permitted_future_skew_ns=5,
            visual_interpretation_producers=(REFERENCE_VISUAL_PRODUCER,),
        )
    )
    memory = WorkingMemory(
        catalog,
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.ROS_SIMULATION_TIME,
            allowed_provenance=(SIMULATION_PROVENANCE,),
            sensors=(CAMERA,),
            freshness_ns=100,
            retention_ttl_ns=10_000,
            permitted_future_skew_ns=5,
            recent_evidence_capacity=16,
            visual_interpretation_producers=(REFERENCE_VISUAL_PRODUCER,),
        ),
    )
    adapter = DeterministicVisualReferenceAdapter()
    source = frame(1)
    result = adapter.interpret(source, result_at_ns=2)
    missing = trust.admit(result, now_ns=2, received_at_monotonic_ns=1)
    accepted_frame = trust.admit(source, now_ns=2, received_at_monotonic_ns=2)
    assert accepted_frame.status is AdmissionStatus.ACCEPTED
    assert memory.ingest(
        accepted_frame.observation,
        now_ns=2,
        received_at_monotonic_ns=2,
    ).status is IngestionStatus.ACCEPTED
    wrong_robot = trust.admit(
        result_with(result, robot_id='other.robot.v1'),
        now_ns=2,
        received_at_monotonic_ns=3,
    )
    wrong_camera = trust.admit(
        result_with(
            result,
            sensor=SensorIdentity(
                'ayyo.camera.other.rgb.v1',
                SensorKind.RGB_CAMERA,
                'head_camera_optical_frame',
            ),
        ),
        now_ns=2,
        received_at_monotonic_ns=4,
    )
    physical = trust.admit(
        result_with(result, provenance=PHYSICAL_PROVENANCE),
        now_ns=2,
        received_at_monotonic_ns=5,
    )
    malformed_rejected = False
    try:
        ImageRegion2D(x_min=math.nan, y_min=0.0, x_max=1.0, y_max=1.0)
    except WorldModelValidationError:
        malformed_rejected = True
    accepted_result = trust.admit(result, now_ns=2, received_at_monotonic_ns=6)
    assert accepted_result.status is AdmissionStatus.ACCEPTED
    assert memory.ingest(
        accepted_result.observation,
        now_ns=2,
        received_at_monotonic_ns=6,
    ).status is IngestionStatus.ACCEPTED
    before_duplicate = memory.stats(now_ns=2)
    duplicate = trust.admit(result, now_ns=2, received_at_monotonic_ns=7)
    after_duplicate = memory.stats(now_ns=2)

    receipt = 7
    for time_ns in range(3, 1003):
        source = frame(time_ns)
        receipt += 1
        accepted_frame = trust.admit(
            source,
            now_ns=time_ns,
            received_at_monotonic_ns=receipt,
        )
        assert accepted_frame.status is AdmissionStatus.ACCEPTED
        assert memory.ingest(
            accepted_frame.observation,
            now_ns=time_ns,
            received_at_monotonic_ns=receipt,
        ).status is IngestionStatus.ACCEPTED
        interpreted = adapter.interpret(source, result_at_ns=time_ns)
        receipt += 1
        accepted_interpretation = trust.admit(
            interpreted,
            now_ns=time_ns,
            received_at_monotonic_ns=receipt,
        )
        assert accepted_interpretation.status is AdmissionStatus.ACCEPTED
        assert memory.ingest(
            accepted_interpretation.observation,
            now_ns=time_ns,
            received_at_monotonic_ns=receipt,
        ).status is IngestionStatus.ACCEPTED

    snapshot = memory.current_snapshot(now_ns=1002)
    stats = memory.stats(now_ns=1002)
    trust_stats = trust.stats()
    state_text = repr(snapshot.robot.document()).lower()
    assert 'pixels' not in state_text and 'image_data' not in state_text
    assert len(snapshot.robot.visual_interpretation_states) == 1
    assert snapshot.robot.visual_interpretation_states[0].observation.detections[0].confidence is None
    assert duplicate.status.value == 'duplicate'
    assert before_duplicate.recent_evidence_count == after_duplicate.recent_evidence_count
    assert stats.current_visual_count == 1
    assert stats.current_visual_interpretation_count == 1
    assert stats.recent_evidence_count == 16
    assert trust_stats.tracked_visual_source_count == 64
    print(
        json.dumps(
            {
                'duplicate_bounded': True,
                'malformed_rejected': malformed_rejected,
                'missing_source': missing.reason.value,
                'no_confidence': True,
                'pixel_free_state': True,
                'recent_evidence_count': stats.recent_evidence_count,
                'tracked_visual_source_count': trust_stats.tracked_visual_source_count,
                'valid_after_adversarial': True,
                'wrong_camera': wrong_camera.reason.value,
                'wrong_robot': wrong_robot.reason.value,
                'physical_substitution': physical.reason.value,
            },
            separators=(',', ':'),
            sort_keys=True,
        )
    )


if __name__ == '__main__':
    main()
