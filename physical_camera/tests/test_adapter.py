from __future__ import annotations

from dataclasses import replace
import unittest

from ayyo_physical_camera import (
    PhysicalCameraAdmission,
    PhysicalCameraConfigurationError,
    PhysicalCameraDiagnosticEvent,
    PhysicalCameraLifecycleAdapter,
    PhysicalCameraLifecycleError,
    PhysicalCameraLifecycleState,
    PhysicalCameraSourceRegistry,
    PhysicalCameraValidationError,
    fixture_camera_info_metadata,
    fixture_image_metadata,
    physical_camera_fixture_bundle,
)
from ayyo_world_model import (
    MAX_IMAGE_DATA_BYTES,
    ObservationClock,
    ObservationSourceKind,
    ObservationTransport,
    SensorIdentity,
    SensorKind,
)


def configured_adapter(**bounds):
    bundle = physical_camera_fixture_bundle()
    registry = PhysicalCameraSourceRegistry()
    registry.register(bundle.source)
    adapter = PhysicalCameraLifecycleAdapter(registry, **bounds)
    adapter.configure(bundle.source.source_id, bundle.calibration)
    session = adapter.activate()
    return bundle, adapter, session


class PhysicalCameraAdapterTest(unittest.TestCase):
    def test_exact_pair_is_sealed_in_either_arrival_order(self) -> None:
        for order in ("image_first", "info_first"):
            bundle, adapter, session = configured_adapter()
            image = fixture_image_metadata(bundle, session, 100)
            info = fixture_camera_info_metadata(bundle, session, 100)
            if order == "image_first":
                self.assertIsNone(adapter.submit_image(image, now_ns=100))
                admission = adapter.submit_camera_info(info, now_ns=100)
            else:
                self.assertIsNone(adapter.submit_camera_info(info, now_ns=100))
                admission = adapter.submit_image(image, now_ns=100)
            self.assertIsInstance(admission, PhysicalCameraAdmission)
            assert admission is not None
            self.assertEqual(bundle.source.provenance, admission.frame.provenance)
            self.assertEqual(bundle.calibration.calibration.calibration_id, admission.frame.calibration_id)
            self.assertEqual(PhysicalCameraDiagnosticEvent.FRAME_ACCEPTED, admission.diagnostics.event)
            self.assertEqual(0, admission.diagnostics.pending_image_count)
            self.assertEqual(0, admission.diagnostics.pending_camera_info_count)

    def test_admission_constructor_is_sealed(self) -> None:
        bundle, adapter, session = configured_adapter()
        adapter.submit_camera_info(
            fixture_camera_info_metadata(bundle, session, 100),
            now_ns=100,
        )
        admission = adapter.submit_image(
            fixture_image_metadata(bundle, session, 100),
            now_ns=100,
        )
        assert admission is not None
        with self.assertRaises(PhysicalCameraConfigurationError):
            PhysicalCameraAdmission(
                frame=admission.frame,
                health=admission.health,
                requirement=admission.requirement,
                session_id=admission.session_id,
                diagnostics=admission.diagnostics,
                _seal=object(),
            )

    def test_wrong_source_robot_frame_and_session_are_rejected_then_valid_recovers(self) -> None:
        bundle, adapter, session = configured_adapter()
        cases = (
            fixture_image_metadata(bundle, session, 100, source_id="other.source.v1"),
            fixture_image_metadata(bundle, session, 101, robot_id="other.robot.v1"),
            fixture_image_metadata(bundle, session, 102, frame_id="head_camera_frame"),
            fixture_image_metadata(
                bundle,
                "physical-camera-session-sha256-" + "1" * 64,
                103,
            ),
        )
        for index, image in enumerate(cases):
            with self.subTest(index=index):
                self.assertIsNone(adapter.submit_image(image, now_ns=image.observed_at_ns))
        adapter.submit_camera_info(
            fixture_camera_info_metadata(bundle, session, 200),
            now_ns=200,
        )
        self.assertIsNotNone(
            adapter.submit_image(
                fixture_image_metadata(bundle, session, 200),
                now_ns=200,
            )
        )

    def test_wrong_camera_and_recorded_source_cannot_claim_physical_identity(self) -> None:
        bundle, adapter, session = configured_adapter()
        wrong_camera = SensorIdentity(
            "other.camera.head.rgb.v1",
            SensorKind.RGB_CAMERA,
            bundle.source.camera.frame_id,
        )
        recorded_provenance = replace(
            bundle.source.provenance,
            source_kind=ObservationSourceKind.RECORDED_DATA,
            clock=ObservationClock.RECORDED_TIME,
            transport=ObservationTransport.RECORDED,
        )
        for image in (
            fixture_image_metadata(
                bundle,
                session,
                100,
                camera=wrong_camera,
            ),
            fixture_image_metadata(
                bundle,
                session,
                101,
                provenance=recorded_provenance,
            ),
        ):
            with self.subTest(image=image):
                self.assertIsNone(
                    adapter.submit_image(image, now_ns=image.observed_at_ns)
                )
                self.assertEqual(
                    PhysicalCameraDiagnosticEvent.WRONG_SOURCE,
                    adapter.diagnostics.event,
                )

    def test_wrong_dimensions_encoding_and_calibration_fail(self) -> None:
        bundle, adapter, session = configured_adapter()
        wrong_images = (
            fixture_image_metadata(
                bundle,
                session,
                100,
                width=5,
                step=15,
                data_size_bytes=30,
            ),
            fixture_image_metadata(bundle, session, 101, encoding="bgr8"),
        )
        for image in wrong_images:
            self.assertIsNone(adapter.submit_image(image, now_ns=image.observed_at_ns))
        wrong_calibration = replace(
            bundle.calibration,
            calibration_version="test.calibration.changed.v1",
            calibration_record_id=None,
        )
        wrong_info = fixture_camera_info_metadata(
            bundle,
            session,
            102,
            calibration=wrong_calibration,
        )
        self.assertIsNone(adapter.submit_camera_info(wrong_info, now_ns=102))
        self.assertEqual(
            PhysicalCameraDiagnosticEvent.CALIBRATION_INVALID,
            adapter.diagnostics.event,
        )

    def test_pair_geometry_and_malformed_image_metadata_fail_closed(self) -> None:
        bundle = physical_camera_fixture_bundle()
        source = replace(
            bundle.source,
            maximum_width=bundle.source.maximum_width + 1,
            manifest_id=None,
        )
        registry = PhysicalCameraSourceRegistry()
        registry.register(source)
        adapter = PhysicalCameraLifecycleAdapter(registry)
        adapter.configure(source.source_id, bundle.calibration)
        session = adapter.activate()
        adapter.submit_camera_info(
            fixture_camera_info_metadata(bundle, session, 100),
            now_ns=100,
        )
        self.assertIsNone(
            adapter.submit_image(
                fixture_image_metadata(
                    bundle,
                    session,
                    100,
                    width=bundle.calibration.calibration.width + 1,
                    step=(bundle.calibration.calibration.width + 1) * 3,
                    data_size_bytes=(
                        (bundle.calibration.calibration.width + 1)
                        * bundle.calibration.calibration.height
                        * 3
                    ),
                ),
                now_ns=100,
            )
        )
        self.assertEqual(
            PhysicalCameraDiagnosticEvent.PAIR_MISMATCH,
            adapter.diagnostics.event,
        )
        with self.assertRaises(PhysicalCameraValidationError):
            fixture_image_metadata(
                bundle,
                session,
                101,
                step=MAX_IMAGE_DATA_BYTES,
                data_size_bytes=MAX_IMAGE_DATA_BYTES * 2,
            )
        empty_encoding = fixture_image_metadata(
            bundle,
            session,
            102,
            encoding="",
        )
        self.assertIsNone(
            adapter.submit_image(empty_encoding, now_ns=102)
        )
        self.assertEqual(
            PhysicalCameraDiagnosticEvent.UNSUPPORTED_ENCODING,
            adapter.diagnostics.event,
        )

    def test_stale_future_regressed_and_repeated_times_fail_closed(self) -> None:
        bundle, adapter, session = configured_adapter(retention_ns=100, pair_wait_ns=10, future_skew_ns=5)
        stale = fixture_image_metadata(bundle, session, 1)
        future = fixture_image_metadata(bundle, session, 200)
        self.assertIsNone(adapter.submit_image(stale, now_ns=102))
        self.assertEqual(PhysicalCameraDiagnosticEvent.STALE_FRAME, adapter.diagnostics.event)
        self.assertIsNone(adapter.submit_image(future, now_ns=100))
        self.assertEqual(PhysicalCameraDiagnosticEvent.FUTURE_FRAME, adapter.diagnostics.event)
        adapter.submit_camera_info(fixture_camera_info_metadata(bundle, session, 100), now_ns=100)
        self.assertIsNotNone(adapter.submit_image(fixture_image_metadata(bundle, session, 100), now_ns=100))
        self.assertIsNone(adapter.submit_image(fixture_image_metadata(bundle, session, 99), now_ns=100))
        self.assertEqual(PhysicalCameraDiagnosticEvent.SOURCE_CLOCK_REGRESSION, adapter.diagnostics.event)
        self.assertIsNone(adapter.submit_image(fixture_image_metadata(bundle, session, 100), now_ns=100))
        self.assertEqual(PhysicalCameraDiagnosticEvent.REPEATED_TIMESTAMP, adapter.diagnostics.event)

    def test_exact_time_pairing_never_uses_nearby_camera_info(self) -> None:
        bundle, adapter, session = configured_adapter()
        adapter.submit_camera_info(fixture_camera_info_metadata(bundle, session, 101), now_ns=101)
        self.assertIsNone(adapter.submit_image(fixture_image_metadata(bundle, session, 100), now_ns=101))
        self.assertEqual(1, adapter.diagnostics.pending_image_count)
        self.assertEqual(1, adapter.diagnostics.pending_camera_info_count)
        admission = adapter.submit_camera_info(
            fixture_camera_info_metadata(bundle, session, 100),
            now_ns=101,
        )
        self.assertIsNotNone(admission)
        self.assertEqual(1, adapter.diagnostics.pending_camera_info_count)

    def test_pending_collections_are_bounded_and_evicted_deterministically(self) -> None:
        bundle, adapter, session = configured_adapter(pair_wait_ns=1_000_000_000)
        for observed_at_ns in range(100, 120):
            adapter.submit_image(
                fixture_image_metadata(bundle, session, observed_at_ns),
                now_ns=observed_at_ns,
            )
        self.assertEqual(8, adapter.diagnostics.pending_image_count)
        self.assertGreaterEqual(adapter.diagnostics.evicted_count, 12)
        self.assertEqual(PhysicalCameraDiagnosticEvent.PENDING_EVICTED, adapter.diagnostics.event)
        self.assertIsNone(
            adapter.submit_camera_info(
                fixture_camera_info_metadata(bundle, session, 100),
                now_ns=119,
            )
        )

    def test_deactivate_clears_pending_and_reactivation_uses_new_session(self) -> None:
        bundle, adapter, first_session = configured_adapter()
        adapter.submit_image(fixture_image_metadata(bundle, first_session, 100), now_ns=100)
        adapter.deactivate()
        self.assertEqual(PhysicalCameraLifecycleState.INACTIVE, adapter.state)
        self.assertEqual(0, adapter.diagnostics.pending_image_count)
        second_session = adapter.activate()
        self.assertNotEqual(first_session, second_session)
        self.assertIsNone(
            adapter.submit_camera_info(
                fixture_camera_info_metadata(bundle, first_session, 101),
                now_ns=101,
            )
        )
        adapter.submit_camera_info(
            fixture_camera_info_metadata(bundle, second_session, 102),
            now_ns=102,
        )
        admission = adapter.submit_image(
            fixture_image_metadata(bundle, second_session, 102),
            now_ns=102,
        )
        self.assertIsNotNone(admission)

    def test_inactive_cleanup_and_shutdown_fail_closed(self) -> None:
        bundle, adapter, session = configured_adapter()
        adapter.deactivate()
        self.assertIsNone(
            adapter.submit_image(
                fixture_image_metadata(bundle, session, 100),
                now_ns=100,
            )
        )
        adapter.cleanup()
        self.assertEqual(PhysicalCameraLifecycleState.UNCONFIGURED, adapter.state)
        adapter.shutdown()
        self.assertEqual(PhysicalCameraLifecycleState.FINALIZED, adapter.state)
        with self.assertRaises(PhysicalCameraLifecycleError):
            adapter.activate()


if __name__ == "__main__":
    unittest.main()
