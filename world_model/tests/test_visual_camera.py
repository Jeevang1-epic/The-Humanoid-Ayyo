from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    CameraCalibration,
    ObservationFingerprint,
    ObservationFingerprintKind,
    ObservationIdentityError,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
    WorldModelValidationError,
    rebuild_observation,
)

from helpers import TEST_PROVENANCE


CAMERA_SENSOR = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)


def calibration(**overrides) -> CameraCalibration:
    values = {
        "width": 320,
        "height": 240,
        "distortion_model": "plumb_bob",
        "d": (),
        "k": (277.0, 0.0, 160.0, 0.0, 277.0, 120.0, 0.0, 0.0, 1.0),
        "r": (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        "p": (
            277.0,
            0.0,
            160.0,
            0.0,
            0.0,
            277.0,
            120.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
        ),
    }
    values.update(overrides)
    return CameraCalibration(**values)


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
        "calibration_id": calibration().calibration_id,
        "observed_at_ns": 100,
        "provenance": TEST_PROVENANCE,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualFrameObservation(**values)


class VisualCameraContractTest(unittest.TestCase):
    def test_calibration_identity_is_deterministic_and_metadata_bound(self) -> None:
        left = calibration()
        right = calibration()
        changed = calibration(k=(278.0,) + left.k[1:])
        self.assertEqual(left, right)
        self.assertEqual(left.calibration_id, right.calibration_id)
        self.assertNotEqual(left.calibration_id, changed.calibration_id)
        self.assertTrue(left.calibration_id.startswith("camera-calibration-sha256-"))

    def test_calibration_rejects_malformed_and_false_calibration_claims(self) -> None:
        invalid = (
            {"width": 0},
            {"height": 4_097},
            {"distortion_model": ""},
            {"d": (float("nan"),)},
            {"k": (0.0,) * 9},
            {"r": (0.0,) * 9},
            {"p": (0.0,) * 12},
            {"k": (1.0,) * 8},
            {"roi": (319, 0, 2, 1, False)},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(
                WorldModelValidationError
            ):
                calibration(**overrides)

    def test_calibration_identity_substitution_is_rejected(self) -> None:
        with self.assertRaises(ObservationIdentityError):
            calibration(calibration_id="camera-calibration-sha256-" + "0" * 64)

    def test_visual_frame_is_compact_immutable_metadata(self) -> None:
        observation = visual()
        self.assertEqual(230_400, observation.data_size_bytes)
        self.assertFalse(hasattr(observation, "data"))
        self.assertEqual(observation, rebuild_observation(observation))
        with self.assertRaises(FrozenInstanceError):
            observation.width = 640

    def test_visual_frame_rejects_invalid_time_dimensions_encoding_and_stride(self) -> None:
        invalid = (
            {"observed_at_ns": 0},
            {"width": 0},
            {"width": 4_097},
            {"encoding": "bgr8"},
            {"encoding": "x" * 4_097},
            {"step": 959},
            {"data_size_bytes": 1},
            {"is_bigendian": 0},
            {"calibration_id": "missing"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(
                WorldModelValidationError
            ):
                visual(**overrides)

    def test_visual_frame_requires_exact_rgb_sensor_and_measurement_state(self) -> None:
        with self.assertRaises(WorldModelValidationError):
            visual(sensor=SensorIdentity("ayyo.imu.body.v1", SensorKind.IMU, "imu_link"))
        for availability in (
            SensorAvailability.ERROR,
            SensorAvailability.STALE,
            SensorAvailability.UNAVAILABLE,
        ):
            with self.subTest(availability=availability), self.assertRaises(
                WorldModelValidationError
            ):
                visual(availability=availability)

    def test_visual_fingerprint_detects_metadata_or_identity_tampering(self) -> None:
        observation = visual()
        object.__setattr__(
            observation,
            "fingerprint",
            ObservationFingerprint(ObservationFingerprintKind.VISUAL_FRAME, "0" * 64),
        )
        with self.assertRaises(ObservationIdentityError):
            rebuild_observation(observation)


if __name__ == "__main__":
    unittest.main()
