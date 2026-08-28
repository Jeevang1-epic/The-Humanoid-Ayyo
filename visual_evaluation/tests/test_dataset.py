from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from ayyo_visual_evaluation import (
    FIXTURE_PROVENANCE,
    FIXTURE_RGB8,
    InMemoryVisualRecordedSource,
    RootedRawRgb8VisualSource,
    VisualDatasetError,
    VisualEvaluationConfigurationError,
    fixture_dataset,
    fixture_detection,
)
from ayyo_world_model import (
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
)


class RecordedVisualDatasetTest(unittest.TestCase):
    def test_manifest_order_is_canonical_and_mutation_changes_identity(self) -> None:
        dataset = fixture_dataset(3)
        reordered = replace(
            dataset,
            samples=tuple(reversed(dataset.samples)),
            manifest_sha256=None,
        )
        self.assertEqual(dataset.manifest_sha256, reordered.manifest_sha256)
        changed_sample = replace(
            dataset.samples[0],
            scenario_ids=("fixture.changed.v1",),
            sample_sha256=None,
        )
        changed = replace(
            dataset,
            samples=(changed_sample,) + dataset.samples[1:],
            manifest_sha256=None,
        )
        self.assertNotEqual(dataset.manifest_sha256, changed.manifest_sha256)

    def test_duplicate_conflicting_sample_and_time_regression_fail(self) -> None:
        dataset = fixture_dataset(2)
        with self.assertRaises(VisualEvaluationConfigurationError):
            replace(
                dataset,
                samples=(dataset.samples[0], dataset.samples[0]),
                manifest_sha256=None,
            )
        regressed = replace(
            dataset.samples[1],
            frame=dataset.samples[0].frame,
            expected_detections=(fixture_detection(dataset.samples[0].frame),),
            sample_sha256=None,
        )
        with self.assertRaises(VisualEvaluationConfigurationError):
            replace(
                dataset,
                samples=(dataset.samples[0], regressed),
                manifest_sha256=None,
            )

    def test_path_traversal_and_absolute_references_fail_at_contract(self) -> None:
        sample = fixture_dataset(1).samples[0]
        for malicious in ("../escape.rgb8", "/tmp/escape.rgb8", "a/./b.rgb8", "a\\b"):
            with self.subTest(malicious=malicious), self.assertRaises(
                VisualEvaluationConfigurationError
            ):
                replace(sample, asset_reference=malicious, sample_sha256=None)

    def test_in_memory_source_rejects_missing_and_bad_content(self) -> None:
        dataset = fixture_dataset(1)
        sample = dataset.samples[0]
        with self.assertRaises(VisualDatasetError):
            InMemoryVisualRecordedSource({"different.rgb8": FIXTURE_RGB8}).load(
                dataset, sample
            )
        with self.assertRaises(VisualDatasetError):
            InMemoryVisualRecordedSource(
                {sample.asset_reference: b"x" * len(FIXTURE_RGB8)}
            ).load(dataset, sample)

    def test_rooted_source_reads_exact_raw_rgb8_and_rejects_symlink(self) -> None:
        dataset = fixture_dataset(1)
        sample = dataset.samples[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "samples"
            assets.mkdir()
            target = assets / "shared.rgb8"
            target.write_bytes(FIXTURE_RGB8)
            loaded = RootedRawRgb8VisualSource(root).load(dataset, sample)
            self.assertEqual(FIXTURE_RGB8, loaded.rgb8)
            target.unlink()
            outside = root / "outside.rgb8"
            outside.write_bytes(FIXTURE_RGB8)
            target.symlink_to(outside)
            with self.assertRaises(VisualDatasetError):
                RootedRawRgb8VisualSource(root).load(dataset, sample)

    def test_wrong_digest_and_missing_file_fail_closed(self) -> None:
        dataset = fixture_dataset(1)
        sample = dataset.samples[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "samples").mkdir()
            source = RootedRawRgb8VisualSource(root)
            with self.assertRaises(VisualDatasetError):
                source.load(dataset, sample)
            (root / sample.asset_reference).write_bytes(
                bytes(reversed(FIXTURE_RGB8))
            )
            self.assertEqual(
                len(FIXTURE_RGB8),
                len(bytes(reversed(FIXTURE_RGB8))),
            )
            self.assertNotEqual(
                sample.asset_sha256,
                sha256(bytes(reversed(FIXTURE_RGB8))).hexdigest(),
            )
            with self.assertRaises(VisualDatasetError):
                source.load(dataset, sample)

    def test_same_kind_wrong_source_profile_cannot_retain_dataset_identity(self) -> None:
        dataset = fixture_dataset(1)
        substituted = ObservationProvenance(
            ObservationSourceKind.TEST_FIXTURE,
            "test.substituted-camera.v1",
            ObservationClock.TEST_TIME,
            ObservationTransport.DIRECT,
            FIXTURE_PROVENANCE.interface,
        )
        with self.assertRaises(VisualEvaluationConfigurationError):
            replace(
                dataset,
                source_profile=substituted,
                manifest_sha256=dataset.manifest_sha256,
            )


if __name__ == "__main__":
    unittest.main()
