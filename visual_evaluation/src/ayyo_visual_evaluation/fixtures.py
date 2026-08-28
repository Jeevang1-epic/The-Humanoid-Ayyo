"""Deterministic TEST FIXTURES for visual evaluator adversarial coverage."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import time

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualDetection,
    VisualFrameObservation,
    VisualInterpretationProducer,
    VisualModelCapability,
    VisualModelFormat,
    VisualModelProvenance,
    VisualModelSourceClassification,
    VisualProducerKind,
    VisualSemanticCategory,
)

from .dataset import InMemoryVisualRecordedSource
from .models import (
    VerifiedModelArtifact,
    VisualConfidenceSemantics,
    VisualDatasetCollectionProvenance,
    VisualEvaluationDatasetManifest,
    VisualEvaluationInput,
    VisualEvaluationPolicy,
    VisualEvaluationSample,
    VisualInputDimensionPolicyKind,
    VisualInputDimensionsPolicy,
    VISUAL_EVALUATION_INPUT_INTERFACE,
    VisualProducerManifest,
    VisualProducerManifestSource,
    VisualProducerResourcePolicy,
    VisualProducerResult,
    VisualProducerResultBatch,
)
from .registry import RegisteredVisualProducer, verify_model_artifact_bytes


FIXTURE_MODEL_BYTES = b"ayyo deterministic visual evaluation fixture model v1\n"
FIXTURE_RGB8 = bytes(range(24))
FIXTURE_IMPLEMENTATION_SHA256 = sha256(
    b"ayyo deterministic visual evaluation fixture implementation v1\n"
).hexdigest()
FIXTURE_CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
FIXTURE_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.visual-evaluation-camera.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.visual-evaluation-rgb8.v1",
)
FIXTURE_PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.evaluation.fixture.v1",
    VisualProducerKind.TEST_FIXTURE,
    "ayyo.visual.evaluation.fixture-model.v1",
    "ayyo.visual.evaluation.fixture-adapter.v1",
    "ayyo.visual-interpretation.v1",
)
FIXTURE_MODEL = VisualModelProvenance(
    model_id=FIXTURE_PRODUCER.model_id,
    model_version="1.0.0",
    producer_id=FIXTURE_PRODUCER.producer_id,
    artifact_sha256=sha256(FIXTURE_MODEL_BYTES).hexdigest(),
    model_format=VisualModelFormat.DETERMINISTIC_FIXTURE,
    capability=VisualModelCapability.BOUNDED_DETECTION,
    configuration_sha256=sha256(b"fixture configuration v1\n").hexdigest(),
    label_schema_id="ayyo.visual.fixture-labels.v1",
    label_schema_version="1.0.0",
    source_classification=VisualModelSourceClassification.TEST_FIXTURE,
    build_export_id="fixture.build.v1",
)


def fixture_frame(index: int = 0) -> VisualFrameObservation:
    return VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=FIXTURE_CAMERA,
        width=4,
        height=2,
        encoding="rgb8",
        step=12,
        data_size_bytes=len(FIXTURE_RGB8),
        is_bigendian=False,
        calibration_id="camera-calibration-sha256-" + "1" * 64,
        observed_at_ns=1_000_000_000 + index * 1_000_000,
        provenance=FIXTURE_PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )


def fixture_detection(
    frame: VisualFrameObservation,
    *,
    category: VisualSemanticCategory = VisualSemanticCategory.TEST_PATTERN,
    confidence: float | None = None,
) -> VisualDetection:
    return VisualDetection(
        source_visual_observation_id=frame.observation_id,
        category=category,
        label="synthetic.evaluation-marker.v1",
        region=ImageRegion2D(
            x_min=0.25,
            y_min=0.25,
            x_max=0.75,
            y_max=0.75,
        ),
        confidence=confidence,
    )


def fixture_manifest(*, maximum_results_per_sample: int = 3) -> VisualProducerManifest:
    return VisualProducerManifest(
        producer=FIXTURE_PRODUCER,
        producer_version="1.0.0",
        producer_implementation_sha256=FIXTURE_IMPLEMENTATION_SHA256,
        model=FIXTURE_MODEL,
        supported_categories=(
            VisualSemanticCategory.OBJECT,
            VisualSemanticCategory.TEST_PATTERN,
            VisualSemanticCategory.UNKNOWN,
        ),
        expected_input_interface=VISUAL_EVALUATION_INPUT_INTERFACE,
        expected_encodings=("rgb8",),
        dimensions=VisualInputDimensionsPolicy(
            VisualInputDimensionPolicyKind.EXACT,
            4,
            2,
        ),
        allowed_sensor_ids=(FIXTURE_CAMERA.sensor_id,),
        allowed_source_profiles=(FIXTURE_PROVENANCE,),
        confidence_semantics=VisualConfidenceSemantics.OPTIONAL_UNIT_INTERVAL,
        resources=VisualProducerResourcePolicy(
            timeout_ns=20_000_000,
            maximum_input_bytes=1_024,
            maximum_results_per_sample=maximum_results_per_sample,
            maximum_detections_per_result=8,
            maximum_label_length=64,
        ),
        result_schema_version="1.0.0",
        manifest_source=VisualProducerManifestSource.TEST_FIXTURE,
    )


def fixture_dataset(sample_count: int = 2) -> VisualEvaluationDatasetManifest:
    samples = []
    digest = sha256(FIXTURE_RGB8).hexdigest()
    for index in range(sample_count):
        frame = fixture_frame(index)
        samples.append(
            VisualEvaluationSample(
                sample_id=f"fixture.sample.{index:05d}",
                sequence_index=index,
                frame=frame,
                asset_reference="samples/shared.rgb8",
                asset_sha256=digest,
                asset_size_bytes=len(FIXTURE_RGB8),
                scenario_ids=("fixture.nominal.v1",),
                expected_detections=(fixture_detection(frame),),
            )
        )
    return VisualEvaluationDatasetManifest(
        dataset_id="ayyo.visual.fixture-dataset.v1",
        dataset_version="1.0.0",
        robot_id=AYYO_ROBOT_ID,
        sensor=FIXTURE_CAMERA,
        expected_optical_frame_id=FIXTURE_CAMERA.frame_id,
        source_profile=FIXTURE_PROVENANCE,
        collection=VisualDatasetCollectionProvenance(
            collection_id="ayyo.visual.fixture-collection.v1",
            collection_version="1.0.0",
            collector_id="ayyo.visual.fixture-collector.v1",
            source=FIXTURE_PROVENANCE,
        ),
        encoding="rgb8",
        width=4,
        height=2,
        calibration_id="camera-calibration-sha256-" + "1" * 64,
        annotation_schema_id="ayyo.visual.fixture-annotations.v1",
        annotation_schema_version="1.0.0",
        samples=tuple(samples),
    )


def fixture_policy(
    manifest: VisualProducerManifest,
    dataset: VisualEvaluationDatasetManifest,
    *,
    maximum_results_per_sample: int = 2,
    minimum_valid_result_basis_points: int = 10_000,
) -> VisualEvaluationPolicy:
    return VisualEvaluationPolicy(
        policy_id="ayyo.visual.fixture-policy.v1",
        policy_version="1.0.0",
        required_producer_manifest_sha256=manifest.manifest_sha256,
        required_model_provenance_sha256=manifest.model.provenance_sha256,
        required_dataset_id=dataset.dataset_id,
        required_dataset_version=dataset.dataset_version,
        required_dataset_manifest_sha256=dataset.manifest_sha256,
        required_result_schema_version=manifest.result_schema_version,
        maximum_timeout_count=0,
        maximum_producer_failure_count=0,
        maximum_malformed_result_count=0,
        maximum_duplicate_result_count=0,
        minimum_valid_result_basis_points=minimum_valid_result_basis_points,
        minimum_annotation_match_basis_points=10_000,
        maximum_p95_latency_ns=10_000_000,
        maximum_results_per_sample=maximum_results_per_sample,
        maximum_detections_per_result=8,
        maximum_label_length=64,
        allowed_categories=(
            VisualSemanticCategory.OBJECT,
            VisualSemanticCategory.TEST_PATTERN,
        ),
        confidence_semantics=VisualConfidenceSemantics.OPTIONAL_UNIT_INTERVAL,
    )


class GoodDeterministicFixtureProducer:
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        frame = evaluation_input.sample.frame
        return VisualProducerResultBatch(
            (
                VisualProducerResult(
                    source_frame=frame,
                    producer=FIXTURE_PRODUCER,
                    model_provenance_sha256=FIXTURE_MODEL.provenance_sha256,
                    result_schema_version="1.0.0",
                    result_at_ns=frame.observed_at_ns + 1_000_000,
                    detections=(fixture_detection(frame),),
                ),
            )
        )


class SlowFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ("_delay_seconds",)

    def __init__(self, delay_seconds: float = 0.25) -> None:
        self._delay_seconds = delay_seconds

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        time.sleep(self._delay_seconds)
        return super().produce(evaluation_input)


class ExceptionFixtureProducer:
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        raise RuntimeError("test fixture producer failure")


class WrongModelFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        valid = super().produce(evaluation_input).results[0]
        return VisualProducerResultBatch(
            (
                VisualProducerResult(
                    source_frame=valid.source_frame,
                    producer=valid.producer,
                    model_provenance_sha256="0" * 64,
                    result_schema_version=valid.result_schema_version,
                    result_at_ns=valid.result_at_ns,
                    detections=valid.detections,
                ),
            )
        )


class WrongSourceFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        wrong = fixture_frame(evaluation_input.sample.sequence_index + 10_000)
        return VisualProducerResultBatch(
            (
                VisualProducerResult(
                    source_frame=wrong,
                    producer=FIXTURE_PRODUCER,
                    model_provenance_sha256=FIXTURE_MODEL.provenance_sha256,
                    result_schema_version="1.0.0",
                    result_at_ns=wrong.observed_at_ns + 1,
                    detections=(fixture_detection(wrong),),
                ),
            )
        )


class DuplicateFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        result = super().produce(evaluation_input).results[0]
        return VisualProducerResultBatch((result, result))


class OversizedFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        result = super().produce(evaluation_input).results[0]
        variants = tuple(
            VisualProducerResult(
                source_frame=result.source_frame,
                producer=result.producer,
                model_provenance_sha256=result.model_provenance_sha256,
                result_schema_version=result.result_schema_version,
                result_at_ns=result.result_at_ns + index,
                detections=result.detections,
            )
            for index in range(3)
        )
        return VisualProducerResultBatch(variants)


class FutureResultFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        result = super().produce(evaluation_input).results[0]
        return VisualProducerResultBatch(
            (
                VisualProducerResult(
                    source_frame=result.source_frame,
                    producer=result.producer,
                    model_provenance_sha256=result.model_provenance_sha256,
                    result_schema_version=result.result_schema_version,
                    result_at_ns=(
                        result.source_frame.observed_at_ns + 20_000_001
                    ),
                    detections=result.detections,
                ),
            )
        )


class UnknownCategoryFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        frame = evaluation_input.sample.frame
        return VisualProducerResultBatch(
            (
                VisualProducerResult(
                    source_frame=frame,
                    producer=FIXTURE_PRODUCER,
                    model_provenance_sha256=FIXTURE_MODEL.provenance_sha256,
                    result_schema_version="1.0.0",
                    result_at_ns=frame.observed_at_ns + 1,
                    detections=(
                        fixture_detection(
                            frame,
                            category=VisualSemanticCategory.UNKNOWN,
                        ),
                    ),
                ),
            )
        )


class MalformedBoxFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        batch = super().produce(evaluation_input)
        region = batch.results[0].detections[0].region
        object.__setattr__(region, "x_min", float("nan"))
        return batch


class MalformedConfidenceFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ("_confidence",)

    def __init__(self, confidence: float = float("inf")) -> None:
        self._confidence = confidence

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        batch = super().produce(evaluation_input)
        detection = batch.results[0].detections[0]
        object.__setattr__(detection, "confidence", self._confidence)
        return batch


class OversizedLabelFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        batch = super().produce(evaluation_input)
        detection = batch.results[0].detections[0]
        object.__setattr__(detection, "label", "x" * 65)
        return batch


class OversizedDetectionFixtureProducer(GoodDeterministicFixtureProducer):
    __slots__ = ()

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch:
        batch = super().produce(evaluation_input)
        result = batch.results[0]
        detection = result.detections[0]
        object.__setattr__(result, "detections", (detection,) * 33)
        return batch


def fixture_registration(
    adapter=None,
    *,
    manifest: VisualProducerManifest | None = None,
) -> RegisteredVisualProducer:
    selected_manifest = fixture_manifest() if manifest is None else manifest
    verified: VerifiedModelArtifact = verify_model_artifact_bytes(
        selected_manifest.model,
        FIXTURE_MODEL_BYTES,
    )
    return RegisteredVisualProducer(
        manifest=selected_manifest,
        adapter=(
            GoodDeterministicFixtureProducer() if adapter is None else adapter
        ),
        verified_artifact=verified,
    )


@dataclass(frozen=True, slots=True)
class FixtureEvaluationBundle:
    dataset: VisualEvaluationDatasetManifest
    source: InMemoryVisualRecordedSource
    manifest: VisualProducerManifest
    policy: VisualEvaluationPolicy
    registration: RegisteredVisualProducer


def fixture_bundle(
    *,
    sample_count: int = 2,
    adapter=None,
) -> FixtureEvaluationBundle:
    dataset = fixture_dataset(sample_count)
    manifest = fixture_manifest()
    return FixtureEvaluationBundle(
        dataset=dataset,
        source=InMemoryVisualRecordedSource(
            {"samples/shared.rgb8": FIXTURE_RGB8}
        ),
        manifest=manifest,
        policy=fixture_policy(manifest, dataset),
        registration=fixture_registration(adapter, manifest=manifest),
    )
