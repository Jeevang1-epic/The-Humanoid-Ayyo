from __future__ import annotations

import unittest

from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
)


CAMERA_SENSOR = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
SIMULATION_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.SIMULATION,
    "ros.camera.head.simulation.gz-harmonic.v1",
    ObservationClock.ROS_SIMULATION_TIME,
    ObservationTransport.ROS2,
    "sensor-msgs.image-camera-info.v1",
)
PHYSICAL_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    "ros.camera.head.physical.standard-driver.v1",
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    "sensor-msgs.image-camera-info.v1",
)
CALIBRATION_ID = "camera-calibration-sha256-" + "1" * 64


def visual(**overrides) -> VisualFrameObservation:
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": CAMERA_SENSOR,
        "width": 320,
        "height": 240,
        "encoding": "rgb8",
        "step": 960,
        "data_size_bytes": 230_400,
        "is_bigendian": False,
        "calibration_id": CALIBRATION_ID,
        "observed_at_ns": 100,
        "provenance": SIMULATION_PROVENANCE,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualFrameObservation(**values)


def boundary() -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.ROS_SIMULATION_TIME,
            sources=(PerceptionSourceContract(CAMERA_SENSOR, SIMULATION_PROVENANCE),),
            freshness_ns=50,
            retention_ttl_ns=100,
            permitted_future_skew_ns=5,
        )
    )


class VisualPerceptionBoundaryTest(unittest.TestCase):
    @staticmethod
    def admit(trust, observation, *, now=100, receipt=1):
        return trust.admit(
            observation,
            now_ns=now,
            received_at_monotonic_ns=receipt,
        )

    def test_exact_visual_source_is_admitted_and_duplicate_is_bounded(self) -> None:
        trust = boundary()
        observation = visual()
        self.assertEqual(
            AdmissionStatus.ACCEPTED,
            self.admit(trust, observation).status,
        )
        duplicate = self.admit(trust, observation, receipt=2)
        self.assertEqual(AdmissionReason.DUPLICATE, duplicate.reason)
        self.assertEqual(1, trust.stats().tracked_source_key_count)

    def test_wrong_robot_sensor_frame_and_source_profile_fail_closed(self) -> None:
        cases = (
            (visual(robot_id="other.robot.v1"), AdmissionReason.WRONG_ROBOT_IDENTITY),
            (
                visual(
                    sensor=SensorIdentity(
                        "ayyo.camera.other.rgb.v1",
                        SensorKind.RGB_CAMERA,
                        "head_camera_optical_frame",
                    )
                ),
                AdmissionReason.UNKNOWN_SENSOR,
            ),
            (
                visual(
                    sensor=SensorIdentity(
                        CAMERA_SENSOR.sensor_id,
                        SensorKind.RGB_CAMERA,
                        "head_camera_frame",
                    )
                ),
                AdmissionReason.FRAME_MISMATCH,
            ),
            (
                visual(provenance=PHYSICAL_PROVENANCE),
                AdmissionReason.CLOCK_DOMAIN_MISMATCH,
            ),
        )
        for observation, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(reason, self.admit(boundary(), observation).reason)

    def test_future_stale_out_of_order_and_conflicting_frames_fail_closed(self) -> None:
        self.assertEqual(
            AdmissionReason.FUTURE_OBSERVATION,
            self.admit(boundary(), visual(observed_at_ns=106)).reason,
        )
        self.assertEqual(
            AdmissionReason.STALE_OBSERVATION,
            self.admit(boundary(), visual(observed_at_ns=1), now=102).reason,
        )
        trust = boundary()
        self.admit(trust, visual(observed_at_ns=100))
        self.assertEqual(
            AdmissionReason.OUT_OF_ORDER,
            self.admit(trust, visual(observed_at_ns=99), receipt=2).reason,
        )
        conflict = visual(observed_at_ns=100, calibration_id="camera-calibration-sha256-" + "2" * 64)
        self.assertEqual(
            AdmissionReason.TEMPORAL_CONFLICT,
            self.admit(trust, conflict, receipt=3).reason,
        )


if __name__ == "__main__":
    unittest.main()
