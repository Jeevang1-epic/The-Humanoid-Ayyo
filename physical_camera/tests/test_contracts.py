from __future__ import annotations

from dataclasses import replace
import math
import unittest

from ayyo_physical_camera import (
    FIXTURE_CAMERA,
    FIXTURE_PROVENANCE,
    PhysicalCameraCalibration,
    PhysicalCameraCalibrationSource,
    PhysicalCameraConfigurationError,
    PhysicalCameraLifecycleAdapter,
    PhysicalCameraLifecycleError,
    PhysicalCameraSourceClassification,
    PhysicalCameraSourceManifest,
    PhysicalCameraSourceRegistry,
    PhysicalCameraValidationError,
    physical_camera_fixture_bundle,
)
from ayyo_world_model import AYYO_ROBOT_ID, CameraCalibration


class PhysicalCameraContractTest(unittest.TestCase):
    def test_fixture_is_explicitly_test_only_and_has_no_fake_device_identity(self) -> None:
        bundle = physical_camera_fixture_bundle()
        self.assertIs(
            bundle.source.classification,
            PhysicalCameraSourceClassification.TEST_FIXTURE,
        )
        self.assertIsNone(bundle.source.device_serial)
        self.assertIsNone(bundle.source.device_fingerprint_sha256)
        self.assertIn("test-fixture", bundle.source.source_id)
        self.assertEqual(bundle.source.provenance, FIXTURE_PROVENANCE)

    def test_calibration_identity_is_deterministic_and_normalizes_negative_zero(self) -> None:
        first = physical_camera_fixture_bundle().calibration
        base = first.calibration
        equivalent = PhysicalCameraCalibration(
            camera=first.camera,
            source_id=first.source_id,
            camera_frame_id=first.camera_frame_id,
            optical_frame_id=first.optical_frame_id,
            calibration_version=first.calibration_version,
            calibration_source=first.calibration_source,
            import_identity=first.import_identity,
            calibration=CameraCalibration(
                width=base.width,
                height=base.height,
                distortion_model=base.distortion_model,
                d=tuple(-0.0 for _ in base.d),
                k=base.k,
                r=base.r,
                p=base.p,
            ),
        )
        self.assertEqual(first.calibration_record_id, equivalent.calibration_record_id)
        self.assertEqual(first.calibration.calibration_id, equivalent.calibration.calibration_id)

    def test_calibration_change_changes_both_compact_identities(self) -> None:
        first = physical_camera_fixture_bundle().calibration
        changed = PhysicalCameraCalibration(
            camera=first.camera,
            source_id=first.source_id,
            camera_frame_id=first.camera_frame_id,
            optical_frame_id=first.optical_frame_id,
            calibration_version="test.calibration.v2",
            calibration_source=first.calibration_source,
            calibration=CameraCalibration(
                width=first.calibration.width,
                height=first.calibration.height,
                distortion_model="plumb_bob",
                d=(0.01, 0.0, 0.0, 0.0, 0.0),
                k=first.calibration.k,
                r=first.calibration.r,
                p=first.calibration.p,
            ),
        )
        self.assertNotEqual(first.calibration.calibration_id, changed.calibration.calibration_id)
        self.assertNotEqual(first.calibration_record_id, changed.calibration_record_id)

    def test_unsupported_distortion_model_and_coefficient_count_fail(self) -> None:
        base = physical_camera_fixture_bundle().calibration
        for model, coefficients in (("unknown_model", ()), ("plumb_bob", (0.0,))):
            with self.subTest(model=model, coefficients=coefficients):
                with self.assertRaises(PhysicalCameraValidationError):
                    PhysicalCameraCalibration(
                        camera=base.camera,
                        source_id=base.source_id,
                        camera_frame_id=base.camera_frame_id,
                        optical_frame_id=base.optical_frame_id,
                        calibration_version=base.calibration_version,
                        calibration_source=base.calibration_source,
                        calibration=CameraCalibration(
                            width=4,
                            height=2,
                            distortion_model=model,
                            d=coefficients,
                            k=base.calibration.k,
                            r=base.calibration.r,
                            p=base.calibration.p,
                        ),
                    )

    def test_world_calibration_rejects_bad_lengths_nonfinite_and_impossible_matrices(self) -> None:
        base = physical_camera_fixture_bundle().calibration.calibration
        cases = (
            {"k": (1.0,) * 8},
            {"k": (math.nan,) + base.k[1:]},
            {"p": (math.inf,) + base.p[1:]},
            {"r": (0.0,) * 9},
            {"width": -1},
        )
        for values in cases:
            with self.subTest(values=values):
                kwargs = {
                    "width": base.width,
                    "height": base.height,
                    "distortion_model": base.distortion_model,
                    "d": base.d,
                    "k": base.k,
                    "r": base.r,
                    "p": base.p,
                }
                kwargs.update(values)
                with self.assertRaises(ValueError):
                    CameraCalibration(**kwargs)

    def test_wrong_camera_frame_and_calibration_binding_fail_closed(self) -> None:
        bundle = physical_camera_fixture_bundle()
        with self.assertRaises(PhysicalCameraValidationError):
            PhysicalCameraCalibration(
                camera=FIXTURE_CAMERA,
                source_id=bundle.source.source_id,
                camera_frame_id=FIXTURE_CAMERA.frame_id,
                optical_frame_id=FIXTURE_CAMERA.frame_id,
                calibration_version="test.calibration.v1",
                calibration_source=PhysicalCameraCalibrationSource.TEST_FIXTURE,
                calibration=bundle.calibration.calibration,
            )
        wrong_source = replace(
            bundle.calibration,
            source_id="other.physical.source.v1",
            calibration_record_id=None,
        )
        registry = PhysicalCameraSourceRegistry()
        registry.register(bundle.source)
        adapter = PhysicalCameraLifecycleAdapter(registry)
        with self.assertRaises(PhysicalCameraConfigurationError):
            adapter.configure(bundle.source.source_id, wrong_source)

    def test_source_manifest_rejects_wrong_robot_topics_and_malformed_identifiers(self) -> None:
        bundle = physical_camera_fixture_bundle()
        base = {
            "source_id": bundle.source.source_id,
            "robot_id": AYYO_ROBOT_ID,
            "camera": bundle.source.camera,
            "adapter_id": bundle.source.adapter_id,
            "adapter_version": bundle.source.adapter_version,
            "adapter_implementation_sha256": bundle.source.adapter_implementation_sha256,
            "provenance": bundle.source.provenance,
            "classification": bundle.source.classification,
            "camera_frame_id": bundle.source.camera_frame_id,
            "encodings": bundle.source.encodings,
            "minimum_width": bundle.source.minimum_width,
            "maximum_width": bundle.source.maximum_width,
            "minimum_height": bundle.source.minimum_height,
            "maximum_height": bundle.source.maximum_height,
            "calibration_id": bundle.source.calibration_id,
            "calibration_record_id": bundle.source.calibration_record_id,
        }
        for overrides in (
            {"robot_id": "other.robot.v1"},
            {"source_id": "UPPERCASE"},
            {"adapter_id": "a" * 129},
            {"image_topic": "/camera/image"},
            {"camera_info_topic": "/camera/info"},
        ):
            values = dict(base)
            values.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(PhysicalCameraValidationError):
                    PhysicalCameraSourceManifest(**values)

    def test_registry_is_idempotent_but_rejects_conflict_and_unknown_source(self) -> None:
        bundle = physical_camera_fixture_bundle()
        registry = PhysicalCameraSourceRegistry()
        self.assertTrue(registry.register(bundle.source))
        self.assertFalse(registry.register(bundle.source))
        conflict = replace(
            bundle.source,
            adapter_version="test.adapter.v2",
            manifest_id=None,
        )
        with self.assertRaises(PhysicalCameraConfigurationError):
            registry.register(conflict)
        with self.assertRaises(PhysicalCameraConfigurationError):
            registry.resolve("unknown.physical.camera.v1")

    def test_missing_calibration_is_unknown_and_prevents_activation(self) -> None:
        bundle = physical_camera_fixture_bundle()
        registry = PhysicalCameraSourceRegistry()
        registry.register(bundle.source)
        adapter = PhysicalCameraLifecycleAdapter(registry)
        adapter.configure(bundle.source.source_id, None)
        self.assertEqual("unknown", adapter.diagnostics.calibration_state.value)
        self.assertEqual("calibration_missing", adapter.diagnostics.event.value)
        with self.assertRaises(PhysicalCameraLifecycleError):
            adapter.activate()


if __name__ == "__main__":
    unittest.main()
