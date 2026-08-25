from __future__ import annotations

import unittest

from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    DeterministicVisualReferenceAdapter,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
    REFERENCE_VISUAL_PRODUCER,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    MAX_VISUAL_SOURCE_REFERENCES,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
    VisualProducerKind,
    VisualFrameObservation,
)


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.camera.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.visual-frame.v1",
)


def frame(time_ns: int = 100, **overrides) -> VisualFrameObservation:
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": CAMERA,
        "width": 32,
        "height": 24,
        "encoding": "rgb8",
        "step": 96,
        "data_size_bytes": 2304,
        "is_bigendian": False,
        "calibration_id": "camera-calibration-sha256-" + "1" * 64,
        "observed_at_ns": time_ns,
        "provenance": PROVENANCE,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualFrameObservation(**values)


def boundary(*, ttl: int = 1000) -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            sources=(PerceptionSourceContract(CAMERA, PROVENANCE),),
            freshness_ns=50,
            retention_ttl_ns=ttl,
            permitted_future_skew_ns=5,
            visual_interpretation_producers=(REFERENCE_VISUAL_PRODUCER,),
        )
    )


def admit(trust, observation, *, now: int, receipt: int):
    return trust.admit(
        observation,
        now_ns=now,
        received_at_monotonic_ns=receipt,
    )


class VisualInterpretationBoundaryTest(unittest.TestCase):
    def test_admitted_frame_to_reference_result_and_duplicate(self) -> None:
        trust = boundary()
        source = frame()
        self.assertEqual(AdmissionStatus.ACCEPTED, admit(trust, source, now=100, receipt=1).status)
        result = DeterministicVisualReferenceAdapter().interpret(
            source,
            result_at_ns=101,
        )
        accepted = admit(trust, result, now=101, receipt=2)
        self.assertEqual(AdmissionStatus.ACCEPTED, accepted.status)
        self.assertIsNone(result.detections[0].confidence)
        self.assertEqual(
            AdmissionReason.DUPLICATE,
            admit(trust, result, now=101, receipt=3).reason,
        )
        self.assertEqual(2, trust.stats().tracked_source_key_count)

    def test_nonexistent_mismatched_unknown_and_future_results_fail_closed(self) -> None:
        adapter = DeterministicVisualReferenceAdapter()
        source = frame()
        result = adapter.interpret(source, result_at_ns=101)
        self.assertEqual(
            AdmissionReason.SOURCE_FRAME_NOT_ADMITTED,
            admit(boundary(), result, now=101, receipt=1).reason,
        )
        trust = boundary()
        admit(trust, source, now=100, receipt=1)
        source_count = trust.stats().tracked_visual_source_count
        spoofed_time = VisualInterpretationObservation(
            robot_id=result.robot_id,
            sensor=result.sensor,
            reference_frame_id=result.reference_frame_id,
            source_visual_observation_id=result.source_visual_observation_id,
            source_visual_fingerprint=result.source_visual_fingerprint,
            observed_at_ns=99,
            result_at_ns=101,
            producer=result.producer,
            detections=result.detections,
            provenance=result.provenance,
            availability=result.availability,
        )
        self.assertEqual(
            AdmissionReason.SOURCE_FRAME_MISMATCH,
            admit(trust, spoofed_time, now=101, receipt=2).reason,
        )
        unknown = VisualInterpretationProducer(
            "ayyo.visual.unknown.v1",
            VisualProducerKind.TEST_FIXTURE,
            "none",
            "ayyo.visual.unknown.adapter.v1",
            "ayyo.visual-interpretation.v1",
        )
        unknown_result = VisualInterpretationObservation(
            robot_id=result.robot_id,
            sensor=result.sensor,
            reference_frame_id=result.reference_frame_id,
            source_visual_observation_id=result.source_visual_observation_id,
            source_visual_fingerprint=result.source_visual_fingerprint,
            observed_at_ns=result.observed_at_ns,
            result_at_ns=result.result_at_ns,
            producer=unknown,
            detections=result.detections,
            provenance=result.provenance,
            availability=result.availability,
        )
        self.assertEqual(
            AdmissionReason.UNKNOWN_PRODUCER,
            admit(trust, unknown_result, now=101, receipt=3).reason,
        )
        future = adapter.interpret(source, result_at_ns=110)
        self.assertEqual(
            AdmissionReason.RESULT_TIME_INVALID,
            admit(trust, future, now=101, receipt=4).reason,
        )
        self.assertEqual(1, trust.stats().tracked_source_key_count)
        self.assertEqual(source_count, trust.stats().tracked_visual_source_count)

    def test_high_rate_source_reference_retention_is_hard_bounded(self) -> None:
        trust = boundary(ttl=10_000)
        for index in range(1, 1001):
            source = frame(index)
            accepted = admit(trust, source, now=index, receipt=index)
            self.assertEqual(AdmissionStatus.ACCEPTED, accepted.status)
        self.assertEqual(
            MAX_VISUAL_SOURCE_REFERENCES,
            trust.stats().tracked_visual_source_count,
        )
        newest = frame(1000)
        result = DeterministicVisualReferenceAdapter().interpret(
            newest,
            result_at_ns=1000,
        )
        self.assertEqual(
            AdmissionStatus.ACCEPTED,
            admit(trust, result, now=1000, receipt=1001).status,
        )

    def test_result_order_and_same_result_time_conflict_fail_closed(self) -> None:
        trust = boundary()
        adapter = DeterministicVisualReferenceAdapter()
        first_source = frame(100)
        second_source = frame(102)
        admit(trust, first_source, now=100, receipt=1)
        first = adapter.interpret(first_source, result_at_ns=101)
        self.assertEqual(
            AdmissionStatus.ACCEPTED,
            admit(trust, first, now=101, receipt=2).status,
        )
        admit(trust, second_source, now=102, receipt=3)
        newest = adapter.interpret(second_source, result_at_ns=103)
        self.assertEqual(
            AdmissionStatus.ACCEPTED,
            admit(trust, newest, now=103, receipt=4).status,
        )
        older_result = adapter.interpret(first_source, result_at_ns=102)
        self.assertEqual(
            AdmissionReason.OUT_OF_ORDER,
            admit(trust, older_result, now=103, receipt=5).reason,
        )
        same_result_time = adapter.interpret(first_source, result_at_ns=103)
        self.assertEqual(
            AdmissionReason.TEMPORAL_CONFLICT,
            admit(trust, same_result_time, now=103, receipt=6).reason,
        )
        self.assertEqual(
            newest.observation_id,
            trust.admit(
                newest,
                now_ns=103,
                received_at_monotonic_ns=7,
            ).observation_id,
        )


if __name__ == "__main__":
    unittest.main()
