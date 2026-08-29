from __future__ import annotations

from dataclasses import replace
import unittest

from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    PerceptionConfigurationError,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_physical_camera import (
    PhysicalCameraLifecycleAdapter,
    PhysicalCameraSourceRegistry,
    fixture_camera_info_metadata,
    fixture_image_metadata,
    physical_camera_fixture_bundle,
)
from ayyo_world_model import ObservationClock


def sealed_admission(observed_at_ns: int = 100):
    bundle = physical_camera_fixture_bundle()
    registry = PhysicalCameraSourceRegistry()
    registry.register(bundle.source)
    adapter = PhysicalCameraLifecycleAdapter(registry)
    adapter.configure(bundle.source.source_id, bundle.calibration)
    session = adapter.activate()
    adapter.submit_camera_info(
        fixture_camera_info_metadata(bundle, session, observed_at_ns),
        now_ns=observed_at_ns,
    )
    admission = adapter.submit_image(
        fixture_image_metadata(bundle, session, observed_at_ns),
        now_ns=observed_at_ns,
    )
    assert admission is not None
    return bundle, admission


def boundary(bundle) -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=bundle.source.robot_id,
            source_clock=ObservationClock.ROS_SYSTEM_TIME,
            sources=(
                PerceptionSourceContract(
                    bundle.source.camera,
                    bundle.source.provenance,
                ),
            ),
            physical_camera_requirements=(bundle.source.requirement(),),
            freshness_ns=50,
            retention_ttl_ns=100,
            permitted_future_skew_ns=5,
        )
    )


class PhysicalCameraPerceptionBoundaryTest(unittest.TestCase):
    def test_sealed_frame_and_health_cross_the_only_trust_boundary(self) -> None:
        bundle, admission = sealed_admission()
        trust = boundary(bundle)
        self.assertTrue(trust.authorize_physical_camera(admission))
        frame = trust.admit(
            admission.frame,
            now_ns=100,
            received_at_monotonic_ns=1,
        )
        health = trust.admit(
            admission.health,
            now_ns=100,
            received_at_monotonic_ns=2,
        )
        self.assertEqual(AdmissionStatus.ACCEPTED, frame.status)
        self.assertEqual(AdmissionStatus.ACCEPTED, health.status)
        self.assertEqual(0, trust.stats().tracked_physical_camera_count)

    def test_bare_or_replayed_physical_evidence_cannot_bypass_adapter(self) -> None:
        bundle, admission = sealed_admission()
        trust = boundary(bundle)
        bare = trust.admit(
            admission.frame,
            now_ns=100,
            received_at_monotonic_ns=1,
        )
        self.assertEqual(AdmissionReason.PHYSICAL_CAMERA_NOT_AUTHORIZED, bare.reason)
        self.assertTrue(trust.authorize_physical_camera(admission))
        accepted = trust.admit(
            admission.frame,
            now_ns=100,
            received_at_monotonic_ns=2,
        )
        replay = trust.admit(
            admission.frame,
            now_ns=100,
            received_at_monotonic_ns=3,
        )
        self.assertEqual(AdmissionStatus.ACCEPTED, accepted.status)
        self.assertEqual(AdmissionReason.PHYSICAL_CAMERA_NOT_AUTHORIZED, replay.reason)

    def test_wrong_calibration_requirement_cannot_authorize(self) -> None:
        bundle, admission = sealed_admission()
        wrong = replace(
            bundle.source.requirement(),
            calibration_id="camera-calibration-sha256-" + "1" * 64,
        )
        trust = PerceptionTrustBoundary(
            PerceptionTrustConfig(
                robot_id=bundle.source.robot_id,
                source_clock=ObservationClock.ROS_SYSTEM_TIME,
                sources=(PerceptionSourceContract(bundle.source.camera, bundle.source.provenance),),
                physical_camera_requirements=(wrong,),
            )
        )
        self.assertFalse(trust.authorize_physical_camera(admission))

    def test_physical_rgb_source_without_requirement_is_invalid_configuration(self) -> None:
        bundle = physical_camera_fixture_bundle()
        with self.assertRaises(PerceptionConfigurationError):
            PerceptionTrustConfig(
                robot_id=bundle.source.robot_id,
                source_clock=ObservationClock.ROS_SYSTEM_TIME,
                sources=(PerceptionSourceContract(bundle.source.camera, bundle.source.provenance),),
            )

    def test_authorizations_remain_bounded_under_unconsumed_flood(self) -> None:
        first_bundle, first = sealed_admission(100)
        trust = boundary(first_bundle)
        for index in range(100, 200):
            bundle, admission = sealed_admission(index)
            self.assertEqual(first_bundle.source, bundle.source)
            self.assertTrue(trust.authorize_physical_camera(admission))
        self.assertLessEqual(trust.stats().tracked_physical_camera_count, 64)


if __name__ == "__main__":
    unittest.main()
