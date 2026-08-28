from __future__ import annotations

from dataclasses import replace
import unittest

from ayyo_world_model import (
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
)
from ayyo_visual_evaluation import (
    EvaluatedVisualAdmission,
    FIXTURE_MODEL,
    FIXTURE_MODEL_BYTES,
    GoodDeterministicFixtureProducer,
    VisualEvaluationConfigurationError,
    VisualProducerRegistrationError,
    VisualProducerRegistry,
    fixture_bundle,
    fixture_bundle_for_live_profile,
    fixture_manifest,
    fixture_registration,
    verify_model_artifact_bytes,
)


class VisualEvaluationContractTest(unittest.TestCase):
    def test_equivalent_manifests_have_identical_fingerprints(self) -> None:
        self.assertEqual(
            fixture_manifest().manifest_sha256,
            fixture_manifest().manifest_sha256,
        )

    def test_manifest_mutation_changes_identity_and_claimed_old_identity_fails(self) -> None:
        original = fixture_manifest()
        changed = replace(
            original,
            producer_version="1.0.1",
            manifest_sha256=None,
        )
        self.assertNotEqual(original.manifest_sha256, changed.manifest_sha256)
        with self.assertRaises(VisualEvaluationConfigurationError):
            replace(changed, manifest_sha256=original.manifest_sha256)

    def test_model_artifact_is_verified_from_bytes_not_a_path_or_claim(self) -> None:
        verified = verify_model_artifact_bytes(FIXTURE_MODEL, FIXTURE_MODEL_BYTES)
        self.assertEqual(FIXTURE_MODEL.artifact_sha256, verified.artifact_sha256)
        with self.assertRaises(VisualProducerRegistrationError):
            verify_model_artifact_bytes(FIXTURE_MODEL, b"changed fixture model")

    def test_registry_is_bounded_exact_and_conflicts_fail_closed(self) -> None:
        registry = VisualProducerRegistry()
        registration = fixture_registration()
        self.assertTrue(registry.register(registration))
        self.assertFalse(registry.register(registration))
        conflicting = fixture_registration(
            GoodDeterministicFixtureProducer(),
            manifest=replace(
                registration.manifest,
                producer_version="1.0.1",
                manifest_sha256=None,
            ),
        )
        with self.assertRaises(VisualProducerRegistrationError):
            registry.register(conflicting)

    def test_admission_constructor_is_sealed(self) -> None:
        bundle = fixture_bundle(sample_count=1)
        with self.assertRaises(TypeError):
            EvaluatedVisualAdmission()  # type: ignore[call-arg]
        # Possessing manifest and producer fixtures alone does not expose the seal.
        self.assertFalse(hasattr(bundle.registration, "issue_admission"))

    def test_live_profile_fixture_keeps_recorded_and_live_provenance_distinct(self) -> None:
        live = ObservationProvenance(
            ObservationSourceKind.SIMULATION,
            "ros.camera.head.simulation.test.v1",
            ObservationClock.ROS_SIMULATION_TIME,
            ObservationTransport.ROS2,
            "sensor-msgs.image-camera-info.v1",
        )
        bundle = fixture_bundle_for_live_profile(
            live,
            width=32,
            height=24,
        )
        self.assertNotEqual(live, bundle.dataset.source_profile)
        self.assertIn(live, bundle.manifest.allowed_source_profiles)
        self.assertEqual((32, 24), (bundle.dataset.width, bundle.dataset.height))
        self.assertEqual(32 * 24 * 3, bundle.source.total_bytes)
        with self.assertRaises(ValueError):
            fixture_bundle_for_live_profile(live, width=100_000, height=100_000)


if __name__ == "__main__":
    unittest.main()
