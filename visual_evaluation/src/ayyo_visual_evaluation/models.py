"""Immutable bounded contracts for visual producer evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
import re

from ayyo_world_model import (
    MAX_CAMERA_DIMENSION,
    MAX_IMAGE_DATA_BYTES,
    MAX_OBSERVATION_TIME_NS,
    MAX_VISUAL_DETECTIONS,
    MAX_VISUAL_LABEL_LENGTH,
    ObservationProvenance,
    ObservationSourceKind,
    SensorIdentity,
    SensorKind,
    VisualDetection,
    VisualEvaluationDecision,
    VisualEvaluationReference,
    VisualEvaluationRequirement,
    VisualFrameObservation,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
    VisualModelProvenance,
    VisualSemanticCategory,
)

from ._canonical import (
    CanonicalValue,
    bounded_int,
    fingerprint,
    identifier,
    semver,
    sha256_hex,
)
from .errors import VisualEvaluationConfigurationError


VISUAL_EVALUATION_SCHEMA_VERSION = 1
VISUAL_EVALUATION_INPUT_INTERFACE = "ayyo.visual-evaluation-input.v1"
MAX_DATASET_SAMPLES = 8_192
MAX_DATASET_BYTES = 128 * 1_024 * 1_024
MAX_SCENARIO_IDS = 16
MAX_REGISTERED_PRODUCERS = 16
MAX_RESULTS_PER_SAMPLE = 8
MAX_EVALUATION_TIMEOUT_NS = 60_000_000_000
MAX_EVALUATION_REASON_COUNTS = 64
MAX_EVALUATION_TEXT = 256
MAX_EVALUATION_SOFTWARE_IDENTITIES = 16

_CALIBRATION_ID = re.compile(r"^camera-calibration-sha256-[0-9a-f]{64}$")
_OBSERVATION_ID = re.compile(r"^world-observation-[0-9a-f]{64}$")


def _enum_value(value: object, expected_type: type[StrEnum], field_name: str) -> str:
    if not isinstance(value, expected_type):
        raise VisualEvaluationConfigurationError(f"{field_name} must be typed")
    return value.value


def _relative_asset_reference(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_EVALUATION_TEXT
        or not value.isascii()
        or "\\" in value
        or "\x00" in value
    ):
        raise VisualEvaluationConfigurationError(
            "asset reference must be bounded canonical relative POSIX text"
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != value
    ):
        raise VisualEvaluationConfigurationError(
            "asset reference cannot be absolute, traverse, or contain aliases"
        )
    return value


class VisualInputDimensionPolicyKind(StrEnum):
    EXACT = "exact"


class VisualConfidenceSemantics(StrEnum):
    ABSENT = "absent"
    OPTIONAL_UNIT_INTERVAL = "optional_unit_interval"
    REQUIRED_UNIT_INTERVAL = "required_unit_interval"


class VisualProducerManifestSource(StrEnum):
    TEST_FIXTURE = "test_fixture"
    PROJECT_CANDIDATE = "project_candidate"
    EXTERNAL_CANDIDATE = "external_candidate"


class VisualInvocationStatus(StrEnum):
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    PRODUCER_FAILED = "producer_failed"
    CLEANUP_FAILED = "cleanup_failed"


class VisualSampleEvaluationStatus(StrEnum):
    VALID = "valid"
    REJECTED = "rejected"


class VisualAdmissionEvidenceKind(StrEnum):
    RECORDED_EVALUATION_SAMPLE = "recorded_evaluation_sample"
    QUALIFIED_LIVE_FRAME = "qualified_live_frame"


class VisualEvaluationReason(StrEnum):
    ACCEPTED = "accepted"
    DATASET_IDENTITY_MISMATCH = "dataset_identity_mismatch"
    PRODUCER_IDENTITY_MISMATCH = "producer_identity_mismatch"
    MODEL_PROVENANCE_MISMATCH = "model_provenance_mismatch"
    SOURCE_LOAD_FAILED = "source_load_failed"
    PRODUCER_TIMEOUT = "producer_timeout"
    PRODUCER_FAILURE = "producer_failure"
    PROCESS_CLEANUP_FAILED = "process_cleanup_failed"
    MALFORMED_RESULT = "malformed_result"
    DUPLICATE_RESULT = "duplicate_result"
    RESULT_COLLECTION_OVERSIZED = "result_collection_oversized"
    SOURCE_OBSERVATION_MISMATCH = "source_observation_mismatch"
    RESULT_TIME_INVALID = "result_time_invalid"
    RESULT_SCHEMA_MISMATCH = "result_schema_mismatch"
    CATEGORY_NOT_ALLOWED = "category_not_allowed"
    CONFIDENCE_SEMANTICS_MISMATCH = "confidence_semantics_mismatch"
    DETECTION_COUNT_EXCEEDED = "detection_count_exceeded"
    LABEL_LENGTH_EXCEEDED = "label_length_exceeded"
    ANNOTATION_MISMATCH = "annotation_mismatch"
    VALID_RESULT_PERCENTAGE_BELOW_MINIMUM = (
        "valid_result_percentage_below_minimum"
    )
    ANNOTATION_MATCH_PERCENTAGE_BELOW_MINIMUM = (
        "annotation_match_percentage_below_minimum"
    )
    MALFORMED_RESULT_LIMIT_EXCEEDED = "malformed_result_limit_exceeded"
    TIMEOUT_LIMIT_EXCEEDED = "timeout_limit_exceeded"
    PRODUCER_FAILURE_LIMIT_EXCEEDED = "producer_failure_limit_exceeded"
    DUPLICATE_RESULT_LIMIT_EXCEEDED = "duplicate_result_limit_exceeded"
    P95_LATENCY_EXCEEDED = "p95_latency_exceeded"


@dataclass(frozen=True, slots=True)
class VisualInputDimensionsPolicy:
    kind: VisualInputDimensionPolicyKind
    width: int
    height: int

    def __post_init__(self) -> None:
        _enum_value(self.kind, VisualInputDimensionPolicyKind, "dimension policy")
        bounded_int(self.width, "input width", minimum=1, maximum=MAX_CAMERA_DIMENSION)
        bounded_int(
            self.height,
            "input height",
            minimum=1,
            maximum=MAX_CAMERA_DIMENSION,
        )
        if self.width * self.height > 16_777_216:
            raise VisualEvaluationConfigurationError(
                "input dimensions exceed the reviewed pixel bound"
            )

    def document(self) -> dict[str, CanonicalValue]:
        return {"height": self.height, "kind": self.kind.value, "width": self.width}


@dataclass(frozen=True, slots=True)
class VisualProducerResourcePolicy:
    timeout_ns: int
    maximum_input_bytes: int
    maximum_results_per_sample: int
    maximum_detections_per_result: int
    maximum_label_length: int

    def __post_init__(self) -> None:
        bounded_int(
            self.timeout_ns,
            "producer timeout",
            minimum=1,
            maximum=MAX_EVALUATION_TIMEOUT_NS,
        )
        bounded_int(
            self.maximum_input_bytes,
            "maximum input bytes",
            minimum=1,
            maximum=MAX_IMAGE_DATA_BYTES,
        )
        bounded_int(
            self.maximum_results_per_sample,
            "maximum results per sample",
            minimum=1,
            maximum=MAX_RESULTS_PER_SAMPLE,
        )
        bounded_int(
            self.maximum_detections_per_result,
            "maximum detections per result",
            minimum=0,
            maximum=MAX_VISUAL_DETECTIONS,
        )
        bounded_int(
            self.maximum_label_length,
            "maximum label length",
            minimum=1,
            maximum=MAX_VISUAL_LABEL_LENGTH,
        )

    def document(self) -> dict[str, CanonicalValue]:
        return {
            "maximum_detections_per_result": self.maximum_detections_per_result,
            "maximum_input_bytes": self.maximum_input_bytes,
            "maximum_label_length": self.maximum_label_length,
            "maximum_results_per_sample": self.maximum_results_per_sample,
            "timeout_ns": self.timeout_ns,
        }


@dataclass(frozen=True, slots=True)
class VisualProducerManifest:
    producer: VisualInterpretationProducer
    producer_version: str
    producer_implementation_sha256: str
    model: VisualModelProvenance
    supported_categories: tuple[VisualSemanticCategory, ...]
    expected_input_interface: str
    expected_encodings: tuple[str, ...]
    dimensions: VisualInputDimensionsPolicy
    allowed_sensor_ids: tuple[str, ...]
    allowed_source_profiles: tuple[ObservationProvenance, ...]
    confidence_semantics: VisualConfidenceSemantics
    resources: VisualProducerResourcePolicy
    result_schema_version: str
    manifest_source: VisualProducerManifestSource
    manifest_sha256: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if type(self.producer) is not VisualInterpretationProducer:
            raise VisualEvaluationConfigurationError(
                "producer manifest requires an exact visual producer identity"
            )
        version = semver(self.producer_version, "producer version")
        implementation = sha256_hex(
            self.producer_implementation_sha256,
            "producer implementation fingerprint",
        )
        if type(self.model) is not VisualModelProvenance:
            raise VisualEvaluationConfigurationError(
                "producer manifest requires typed model provenance"
            )
        if (
            self.model.producer_id != self.producer.producer_id
            or self.model.model_id != self.producer.model_id
        ):
            raise VisualEvaluationConfigurationError(
                "producer and model identities must agree exactly"
            )
        if (
            type(self.supported_categories) is not tuple
            or not self.supported_categories
            or len(self.supported_categories) > len(VisualSemanticCategory)
            or any(
                not isinstance(item, VisualSemanticCategory)
                for item in self.supported_categories
            )
        ):
            raise VisualEvaluationConfigurationError(
                "supported categories must be a bounded typed tuple"
            )
        categories = tuple(
            sorted(set(self.supported_categories), key=lambda item: item.value)
        )
        if categories != self.supported_categories:
            raise VisualEvaluationConfigurationError(
                "supported categories must be unique and sorted"
            )
        input_interface = identifier(
            self.expected_input_interface,
            "expected input interface",
        )
        if input_interface != VISUAL_EVALUATION_INPUT_INTERFACE:
            raise VisualEvaluationConfigurationError(
                "producer input interface must be the fixed normalized evaluator contract"
            )
        if (
            type(self.expected_encodings) is not tuple
            or self.expected_encodings != ("rgb8",)
        ):
            raise VisualEvaluationConfigurationError(
                "v1 evaluated visual producers require exactly rgb8 input"
            )
        if type(self.dimensions) is not VisualInputDimensionsPolicy:
            raise VisualEvaluationConfigurationError(
                "producer dimensions policy must be typed"
            )
        if (
            type(self.allowed_sensor_ids) is not tuple
            or not self.allowed_sensor_ids
            or len(self.allowed_sensor_ids) > 8
        ):
            raise VisualEvaluationConfigurationError(
                "allowed camera identities must be a bounded tuple"
            )
        sensor_ids = tuple(
            identifier(item, "allowed camera identity")
            for item in self.allowed_sensor_ids
        )
        if sensor_ids != tuple(sorted(set(sensor_ids))):
            raise VisualEvaluationConfigurationError(
                "allowed camera identities must be unique and sorted"
            )
        if (
            type(self.allowed_source_profiles) is not tuple
            or not self.allowed_source_profiles
            or len(self.allowed_source_profiles) > 8
            or any(
                type(item) is not ObservationProvenance
                for item in self.allowed_source_profiles
            )
        ):
            raise VisualEvaluationConfigurationError(
                "allowed source profiles must be a bounded typed tuple"
            )
        source_profiles = tuple(
            sorted(
                set(self.allowed_source_profiles),
                key=lambda item: (
                    item.source_kind.value,
                    item.source_id,
                    item.clock.value,
                    item.transport.value,
                    item.interface,
                ),
            )
        )
        if source_profiles != self.allowed_source_profiles:
            raise VisualEvaluationConfigurationError(
                "allowed source profiles must be unique and sorted"
            )
        _enum_value(
            self.confidence_semantics,
            VisualConfidenceSemantics,
            "confidence semantics",
        )
        if type(self.resources) is not VisualProducerResourcePolicy:
            raise VisualEvaluationConfigurationError(
                "producer resource policy must be typed"
            )
        schema_version = semver(self.result_schema_version, "result schema version")
        _enum_value(
            self.manifest_source,
            VisualProducerManifestSource,
            "producer manifest source",
        )
        document = self.document(include_fingerprint=False)
        derived = fingerprint(document)
        if self.manifest_sha256 is not None and self.manifest_sha256 != derived:
            raise VisualEvaluationConfigurationError(
                "producer manifest fingerprint does not match its content"
            )
        object.__setattr__(self, "producer_version", version)
        object.__setattr__(self, "producer_implementation_sha256", implementation)
        object.__setattr__(self, "expected_input_interface", input_interface)
        object.__setattr__(self, "result_schema_version", schema_version)
        object.__setattr__(self, "manifest_sha256", derived)

    def document(self, *, include_fingerprint: bool = True) -> dict[str, CanonicalValue]:
        result: dict[str, CanonicalValue] = {
            "allowed_sensor_ids": list(self.allowed_sensor_ids),
            "allowed_source_profiles": [
                item.document() for item in self.allowed_source_profiles
            ],
            "confidence_semantics": self.confidence_semantics.value,
            "dimensions": self.dimensions.document(),
            "expected_encodings": list(self.expected_encodings),
            "expected_input_interface": self.expected_input_interface,
            "manifest_source": self.manifest_source.value,
            "model_provenance_sha256": self.model.provenance_sha256,
            "producer": self.producer.document(),
            "producer_implementation_sha256": self.producer_implementation_sha256,
            "producer_version": self.producer_version,
            "resources": self.resources.document(),
            "result_schema_version": self.result_schema_version,
            "schema": "ayyo.visual-producer-manifest.v1",
            "supported_categories": [
                item.value for item in self.supported_categories
            ],
        }
        if include_fingerprint:
            result["manifest_sha256"] = self.manifest_sha256
        return result


@dataclass(frozen=True, slots=True)
class VerifiedModelArtifact:
    model_provenance_sha256: str
    artifact_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        sha256_hex(self.model_provenance_sha256, "model provenance fingerprint")
        sha256_hex(self.artifact_sha256, "model artifact fingerprint")
        bounded_int(
            self.size_bytes,
            "model artifact size",
            minimum=1,
            maximum=MAX_DATASET_BYTES,
        )


@dataclass(frozen=True, slots=True)
class VisualDatasetCollectionProvenance:
    collection_id: str
    collection_version: str
    collector_id: str
    source: ObservationProvenance

    def __post_init__(self) -> None:
        identifier(self.collection_id, "collection identity")
        semver(self.collection_version, "collection version")
        identifier(self.collector_id, "collector identity")
        if type(self.source) is not ObservationProvenance:
            raise VisualEvaluationConfigurationError(
                "collection provenance requires one exact source profile"
            )

    def document(self) -> dict[str, CanonicalValue]:
        return {
            "collection_id": self.collection_id,
            "collection_version": self.collection_version,
            "collector_id": self.collector_id,
            "source": self.source.document(),
        }


@dataclass(frozen=True, slots=True)
class VisualEvaluationSample:
    sample_id: str
    sequence_index: int
    frame: VisualFrameObservation
    asset_reference: str
    asset_sha256: str
    asset_size_bytes: int
    scenario_ids: tuple[str, ...] = ()
    expected_detections: tuple[VisualDetection, ...] = ()
    sample_sha256: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        identifier(self.sample_id, "evaluation sample identity")
        bounded_int(
            self.sequence_index,
            "sample sequence index",
            maximum=MAX_DATASET_SAMPLES - 1,
        )
        if type(self.frame) is not VisualFrameObservation:
            raise VisualEvaluationConfigurationError(
                "evaluation sample requires immutable visual-frame metadata"
            )
        reference = _relative_asset_reference(self.asset_reference)
        asset_digest = sha256_hex(self.asset_sha256, "sample asset fingerprint")
        bounded_int(
            self.asset_size_bytes,
            "sample asset size",
            minimum=1,
            maximum=MAX_IMAGE_DATA_BYTES,
        )
        if self.asset_size_bytes != self.frame.data_size_bytes:
            raise VisualEvaluationConfigurationError(
                "sample asset size must match its visual-frame metadata"
            )
        if (
            type(self.scenario_ids) is not tuple
            or len(self.scenario_ids) > MAX_SCENARIO_IDS
        ):
            raise VisualEvaluationConfigurationError(
                "sample scenarios exceed their bound"
            )
        scenarios = tuple(
            identifier(item, "scenario identity") for item in self.scenario_ids
        )
        if scenarios != tuple(sorted(set(scenarios))):
            raise VisualEvaluationConfigurationError(
                "scenario identities must be unique and sorted"
            )
        if (
            type(self.expected_detections) is not tuple
            or len(self.expected_detections) > MAX_VISUAL_DETECTIONS
            or any(type(item) is not VisualDetection for item in self.expected_detections)
        ):
            raise VisualEvaluationConfigurationError(
                "sample annotations must be bounded typed detections"
            )
        detections = tuple(
            sorted(self.expected_detections, key=lambda item: item.detection_id)
        )
        ids = tuple(item.detection_id for item in detections)
        if (
            len(ids) != len(set(ids))
            or any(
                item.source_visual_observation_id != self.frame.observation_id
                for item in detections
            )
        ):
            raise VisualEvaluationConfigurationError(
                "sample annotations must be unique and reference its exact frame"
            )
        object.__setattr__(self, "asset_reference", reference)
        object.__setattr__(self, "asset_sha256", asset_digest)
        object.__setattr__(self, "expected_detections", detections)
        derived = fingerprint(self.document(include_fingerprint=False))
        if self.sample_sha256 is not None and self.sample_sha256 != derived:
            raise VisualEvaluationConfigurationError(
                "evaluation sample fingerprint does not match its content"
            )
        object.__setattr__(self, "sample_sha256", derived)

    def document(self, *, include_fingerprint: bool = True) -> dict[str, CanonicalValue]:
        result: dict[str, CanonicalValue] = {
            "asset_reference": self.asset_reference,
            "asset_sha256": self.asset_sha256,
            "asset_size_bytes": self.asset_size_bytes,
            "expected_detections": [
                item.document() for item in self.expected_detections
            ],
            "frame_fingerprint": str(self.frame.fingerprint),
            "frame_observation_id": self.frame.observation_id,
            "sample_id": self.sample_id,
            "scenario_ids": list(self.scenario_ids),
            "schema": "ayyo.visual-evaluation-sample.v1",
            "sequence_index": self.sequence_index,
        }
        if include_fingerprint:
            result["sample_sha256"] = self.sample_sha256
        return result


@dataclass(frozen=True, slots=True)
class VisualEvaluationDatasetManifest:
    dataset_id: str
    dataset_version: str
    robot_id: str
    sensor: SensorIdentity
    expected_optical_frame_id: str
    source_profile: ObservationProvenance
    collection: VisualDatasetCollectionProvenance
    encoding: str
    width: int
    height: int
    calibration_id: str
    annotation_schema_id: str
    annotation_schema_version: str
    samples: tuple[VisualEvaluationSample, ...]
    manifest_sha256: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        identifier(self.dataset_id, "dataset identity")
        semver(self.dataset_version, "dataset version")
        identifier(self.robot_id, "dataset robot identity")
        if type(self.sensor) is not SensorIdentity or self.sensor.kind is not SensorKind.RGB_CAMERA:
            raise VisualEvaluationConfigurationError(
                "dataset requires one exact RGB camera identity"
            )
        if self.expected_optical_frame_id != self.sensor.frame_id:
            raise VisualEvaluationConfigurationError(
                "dataset optical frame must match the exact camera frame"
            )
        if type(self.source_profile) is not ObservationProvenance:
            raise VisualEvaluationConfigurationError(
                "dataset source profile must be typed"
            )
        if (
            type(self.collection) is not VisualDatasetCollectionProvenance
            or self.collection.source != self.source_profile
        ):
            raise VisualEvaluationConfigurationError(
                "collection and dataset source provenance must agree exactly"
            )
        if self.encoding != "rgb8":
            raise VisualEvaluationConfigurationError(
                "v1 visual evaluation supports only rgb8 datasets"
            )
        bounded_int(self.width, "dataset width", minimum=1, maximum=MAX_CAMERA_DIMENSION)
        bounded_int(self.height, "dataset height", minimum=1, maximum=MAX_CAMERA_DIMENSION)
        if type(self.calibration_id) is not str or _CALIBRATION_ID.fullmatch(
            self.calibration_id
        ) is None:
            raise VisualEvaluationConfigurationError(
                "dataset calibration identity is malformed"
            )
        identifier(self.annotation_schema_id, "annotation schema identity")
        semver(self.annotation_schema_version, "annotation schema version")
        if (
            type(self.samples) is not tuple
            or not self.samples
            or len(self.samples) > MAX_DATASET_SAMPLES
            or any(type(item) is not VisualEvaluationSample for item in self.samples)
        ):
            raise VisualEvaluationConfigurationError(
                "dataset samples must be a nonempty bounded typed tuple"
            )
        samples = tuple(
            sorted(self.samples, key=lambda item: (item.sequence_index, item.sample_id))
        )
        sample_ids = tuple(item.sample_id for item in samples)
        indexes = tuple(item.sequence_index for item in samples)
        if len(sample_ids) != len(set(sample_ids)):
            raise VisualEvaluationConfigurationError(
                "duplicate evaluation sample identities are forbidden"
            )
        if indexes != tuple(range(len(samples))):
            raise VisualEvaluationConfigurationError(
                "sample sequence indexes must be contiguous from zero"
            )
        observed_times = tuple(item.frame.observed_at_ns for item in samples)
        if observed_times != tuple(sorted(set(observed_times))):
            raise VisualEvaluationConfigurationError(
                "sample source times must be unique and strictly increasing"
            )
        total_bytes = 0
        for sample in samples:
            frame = sample.frame
            if (
                frame.robot_id != self.robot_id
                or frame.sensor != self.sensor
                or frame.sensor.frame_id != self.expected_optical_frame_id
                or frame.provenance != self.source_profile
                or frame.encoding != self.encoding
                or frame.width != self.width
                or frame.height != self.height
                or frame.calibration_id != self.calibration_id
            ):
                raise VisualEvaluationConfigurationError(
                    "sample metadata conflicts with its immutable dataset manifest"
                )
            total_bytes += sample.asset_size_bytes
            if total_bytes > MAX_DATASET_BYTES:
                raise VisualEvaluationConfigurationError(
                    "dataset assets exceed their aggregate byte bound"
                )
        object.__setattr__(self, "samples", samples)
        derived = fingerprint(self.document(include_fingerprint=False))
        if self.manifest_sha256 is not None and self.manifest_sha256 != derived:
            raise VisualEvaluationConfigurationError(
                "dataset manifest fingerprint does not match its content"
            )
        object.__setattr__(self, "manifest_sha256", derived)

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    def document(self, *, include_fingerprint: bool = True) -> dict[str, CanonicalValue]:
        result: dict[str, CanonicalValue] = {
            "annotation_schema_id": self.annotation_schema_id,
            "annotation_schema_version": self.annotation_schema_version,
            "calibration_id": self.calibration_id,
            "collection": self.collection.document(),
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "encoding": self.encoding,
            "expected_optical_frame_id": self.expected_optical_frame_id,
            "height": self.height,
            "robot_id": self.robot_id,
            "sample_count": self.sample_count,
            "samples": [item.document() for item in self.samples],
            "schema": "ayyo.visual-evaluation-dataset.v1",
            "sensor": self.sensor.document(),
            "source_profile": self.source_profile.document(),
            "width": self.width,
        }
        if include_fingerprint:
            result["manifest_sha256"] = self.manifest_sha256
        return result


@dataclass(frozen=True, slots=True)
class VisualProducerResult:
    source_frame: VisualFrameObservation
    producer: VisualInterpretationProducer
    model_provenance_sha256: str
    result_schema_version: str
    result_at_ns: int
    detections: tuple[VisualDetection, ...]
    result_sha256: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if type(self.source_frame) is not VisualFrameObservation:
            raise VisualEvaluationConfigurationError(
                "producer result requires exact source-frame metadata"
            )
        if type(self.producer) is not VisualInterpretationProducer:
            raise VisualEvaluationConfigurationError(
                "producer result requires exact producer identity"
            )
        sha256_hex(self.model_provenance_sha256, "result model provenance")
        semver(self.result_schema_version, "result schema version")
        bounded_int(
            self.result_at_ns,
            "producer result source time",
            minimum=self.source_frame.observed_at_ns,
            maximum=MAX_OBSERVATION_TIME_NS,
        )
        if (
            type(self.detections) is not tuple
            or len(self.detections) > MAX_VISUAL_DETECTIONS
            or any(type(item) is not VisualDetection for item in self.detections)
        ):
            raise VisualEvaluationConfigurationError(
                "producer detections must be a bounded typed tuple"
            )
        detections = tuple(sorted(self.detections, key=lambda item: item.detection_id))
        ids = tuple(item.detection_id for item in detections)
        if (
            len(ids) != len(set(ids))
            or any(
                item.source_visual_observation_id
                != self.source_frame.observation_id
                for item in detections
            )
        ):
            raise VisualEvaluationConfigurationError(
                "producer detections must be unique and reference the exact source"
            )
        object.__setattr__(self, "detections", detections)
        derived = fingerprint(self.document(include_fingerprint=False))
        if self.result_sha256 is not None and self.result_sha256 != derived:
            raise VisualEvaluationConfigurationError(
                "producer result fingerprint does not match its content"
            )
        object.__setattr__(self, "result_sha256", derived)

    def document(self, *, include_fingerprint: bool = True) -> dict[str, CanonicalValue]:
        result: dict[str, CanonicalValue] = {
            "detections": [item.document() for item in self.detections],
            "model_provenance_sha256": self.model_provenance_sha256,
            "producer": self.producer.document(),
            "result_at_ns": self.result_at_ns,
            "result_schema_version": self.result_schema_version,
            "schema": "ayyo.visual-producer-result.v1",
            "source_visual_fingerprint": str(self.source_frame.fingerprint),
            "source_visual_observation_id": self.source_frame.observation_id,
        }
        if include_fingerprint:
            result["result_sha256"] = self.result_sha256
        return result


@dataclass(frozen=True, slots=True)
class VisualProducerResultBatch:
    results: tuple[VisualProducerResult, ...]

    def __post_init__(self) -> None:
        if (
            type(self.results) is not tuple
            or len(self.results) > MAX_RESULTS_PER_SAMPLE
            or any(type(item) is not VisualProducerResult for item in self.results)
        ):
            raise VisualEvaluationConfigurationError(
                "producer result collection is malformed or oversized"
            )


@dataclass(frozen=True, slots=True)
class VisualEvaluationInput:
    sample: VisualEvaluationSample
    rgb8: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.sample) is not VisualEvaluationSample or type(self.rgb8) is not bytes:
            raise VisualEvaluationConfigurationError(
                "evaluation input requires one typed sample and immutable bytes"
            )
        if len(self.rgb8) != self.sample.asset_size_bytes:
            raise VisualEvaluationConfigurationError(
                "evaluation input byte count differs from the sample manifest"
            )
        from hashlib import sha256

        if sha256(self.rgb8).hexdigest() != self.sample.asset_sha256:
            raise VisualEvaluationConfigurationError(
                "evaluation input bytes differ from their immutable digest"
            )


@dataclass(frozen=True, slots=True)
class VisualInvocationResult:
    status: VisualInvocationStatus
    latency_ns: int
    batch: VisualProducerResultBatch | None
    owned_survivor_pids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _enum_value(self.status, VisualInvocationStatus, "invocation status")
        bounded_int(
            self.latency_ns,
            "invocation latency",
            maximum=MAX_OBSERVATION_TIME_NS,
        )
        if self.status is VisualInvocationStatus.COMPLETED:
            if type(self.batch) is not VisualProducerResultBatch:
                raise VisualEvaluationConfigurationError(
                    "completed invocation requires a typed result batch"
                )
        elif self.batch is not None:
            raise VisualEvaluationConfigurationError(
                "failed invocation cannot expose producer results"
            )
        if (
            type(self.owned_survivor_pids) is not tuple
            or len(self.owned_survivor_pids) > 64
            or any(type(item) is not int or item <= 0 for item in self.owned_survivor_pids)
            or self.owned_survivor_pids
            != tuple(sorted(set(self.owned_survivor_pids)))
        ):
            raise VisualEvaluationConfigurationError(
                "owned survivor identities must be bounded unique process IDs"
            )
        if (
            self.status is not VisualInvocationStatus.CLEANUP_FAILED
            and self.owned_survivor_pids
        ):
            raise VisualEvaluationConfigurationError(
                "only cleanup failure may report owned survivors"
            )


@dataclass(frozen=True, slots=True)
class VisualEvaluationPolicy:
    policy_id: str
    policy_version: str
    required_producer_manifest_sha256: str
    required_model_provenance_sha256: str
    required_dataset_id: str
    required_dataset_version: str
    required_dataset_manifest_sha256: str
    required_result_schema_version: str
    maximum_timeout_count: int
    maximum_producer_failure_count: int
    maximum_malformed_result_count: int
    maximum_duplicate_result_count: int
    minimum_valid_result_basis_points: int
    minimum_annotation_match_basis_points: int
    maximum_p95_latency_ns: int
    maximum_results_per_sample: int
    maximum_detections_per_result: int
    maximum_label_length: int
    allowed_categories: tuple[VisualSemanticCategory, ...]
    confidence_semantics: VisualConfidenceSemantics
    policy_sha256: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        identifier(self.policy_id, "evaluation policy identity")
        semver(self.policy_version, "evaluation policy version")
        for value, name in (
            (self.required_producer_manifest_sha256, "required producer manifest"),
            (self.required_model_provenance_sha256, "required model provenance"),
            (self.required_dataset_manifest_sha256, "required dataset manifest"),
        ):
            sha256_hex(value, name)
        identifier(self.required_dataset_id, "required dataset identity")
        semver(self.required_dataset_version, "required dataset version")
        semver(self.required_result_schema_version, "required result schema version")
        for value, name in (
            (self.maximum_timeout_count, "maximum timeout count"),
            (self.maximum_producer_failure_count, "maximum producer failure count"),
            (self.maximum_malformed_result_count, "maximum malformed result count"),
            (self.maximum_duplicate_result_count, "maximum duplicate result count"),
        ):
            bounded_int(value, name, maximum=MAX_DATASET_SAMPLES)
        for value, name in (
            (self.minimum_valid_result_basis_points, "minimum valid result percentage"),
            (
                self.minimum_annotation_match_basis_points,
                "minimum annotation match percentage",
            ),
        ):
            bounded_int(value, name, maximum=10_000)
        bounded_int(
            self.maximum_p95_latency_ns,
            "maximum p95 latency",
            minimum=1,
            maximum=MAX_EVALUATION_TIMEOUT_NS,
        )
        bounded_int(
            self.maximum_results_per_sample,
            "policy maximum results per sample",
            minimum=1,
            maximum=MAX_RESULTS_PER_SAMPLE,
        )
        bounded_int(
            self.maximum_detections_per_result,
            "policy maximum detections per result",
            maximum=MAX_VISUAL_DETECTIONS,
        )
        bounded_int(
            self.maximum_label_length,
            "policy maximum label length",
            minimum=1,
            maximum=MAX_VISUAL_LABEL_LENGTH,
        )
        if (
            type(self.allowed_categories) is not tuple
            or not self.allowed_categories
            or any(
                not isinstance(item, VisualSemanticCategory)
                for item in self.allowed_categories
            )
        ):
            raise VisualEvaluationConfigurationError(
                "policy categories must be a bounded typed tuple"
            )
        categories = tuple(
            sorted(set(self.allowed_categories), key=lambda item: item.value)
        )
        if categories != self.allowed_categories:
            raise VisualEvaluationConfigurationError(
                "policy categories must be unique and sorted"
            )
        _enum_value(
            self.confidence_semantics,
            VisualConfidenceSemantics,
            "policy confidence semantics",
        )
        derived = fingerprint(self.document(include_fingerprint=False))
        if self.policy_sha256 is not None and self.policy_sha256 != derived:
            raise VisualEvaluationConfigurationError(
                "evaluation policy fingerprint does not match its content"
            )
        object.__setattr__(self, "policy_sha256", derived)

    def document(self, *, include_fingerprint: bool = True) -> dict[str, CanonicalValue]:
        result: dict[str, CanonicalValue] = {
            "allowed_categories": [item.value for item in self.allowed_categories],
            "confidence_semantics": self.confidence_semantics.value,
            "maximum_detections_per_result": self.maximum_detections_per_result,
            "maximum_duplicate_result_count": self.maximum_duplicate_result_count,
            "maximum_label_length": self.maximum_label_length,
            "maximum_malformed_result_count": self.maximum_malformed_result_count,
            "maximum_p95_latency_ns": self.maximum_p95_latency_ns,
            "maximum_producer_failure_count": self.maximum_producer_failure_count,
            "maximum_results_per_sample": self.maximum_results_per_sample,
            "maximum_timeout_count": self.maximum_timeout_count,
            "minimum_annotation_match_basis_points": (
                self.minimum_annotation_match_basis_points
            ),
            "minimum_valid_result_basis_points": (
                self.minimum_valid_result_basis_points
            ),
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "required_dataset_id": self.required_dataset_id,
            "required_dataset_manifest_sha256": (
                self.required_dataset_manifest_sha256
            ),
            "required_dataset_version": self.required_dataset_version,
            "required_model_provenance_sha256": (
                self.required_model_provenance_sha256
            ),
            "required_producer_manifest_sha256": (
                self.required_producer_manifest_sha256
            ),
            "required_result_schema_version": self.required_result_schema_version,
            "schema": "ayyo.visual-evaluation-policy.v1",
        }
        if include_fingerprint:
            result["policy_sha256"] = self.policy_sha256
        return result


@dataclass(frozen=True, slots=True)
class VisualReasonCount:
    reason: VisualEvaluationReason
    count: int

    def __post_init__(self) -> None:
        _enum_value(self.reason, VisualEvaluationReason, "evaluation reason")
        bounded_int(self.count, "evaluation reason count", minimum=1)

    def document(self) -> dict[str, CanonicalValue]:
        return {"count": self.count, "reason": self.reason.value}


@dataclass(frozen=True, slots=True)
class VisualSampleEvaluationRecord:
    sample_id: str
    sample_sha256: str
    source_visual_observation_id: str
    status: VisualSampleEvaluationStatus
    reason: VisualEvaluationReason
    latency_ns: int
    result_count: int
    result_sha256s: tuple[str, ...]
    annotation_matched: bool

    def __post_init__(self) -> None:
        identifier(self.sample_id, "evaluation record sample identity")
        sha256_hex(self.sample_sha256, "evaluation record sample fingerprint")
        if (
            type(self.source_visual_observation_id) is not str
            or _OBSERVATION_ID.fullmatch(self.source_visual_observation_id) is None
        ):
            raise VisualEvaluationConfigurationError(
                "evaluation record source identity is malformed"
            )
        _enum_value(self.status, VisualSampleEvaluationStatus, "sample status")
        _enum_value(self.reason, VisualEvaluationReason, "sample reason")
        bounded_int(
            self.latency_ns,
            "sample latency",
            maximum=MAX_OBSERVATION_TIME_NS,
        )
        bounded_int(
            self.result_count,
            "sample result count",
            maximum=MAX_RESULTS_PER_SAMPLE,
        )
        if (
            type(self.result_sha256s) is not tuple
            or len(self.result_sha256s) != self.result_count
        ):
            raise VisualEvaluationConfigurationError(
                "sample result fingerprints do not match the result count"
            )
        hashes = tuple(
            sha256_hex(value, "sample result fingerprint")
            for value in self.result_sha256s
        )
        if hashes != tuple(sorted(hashes)):
            raise VisualEvaluationConfigurationError(
                "sample result fingerprints must be sorted"
            )
        if type(self.annotation_matched) is not bool:
            raise VisualEvaluationConfigurationError(
                "sample annotation decision must be boolean"
            )
        if self.status is VisualSampleEvaluationStatus.VALID:
            if self.reason is not VisualEvaluationReason.ACCEPTED or not hashes:
                raise VisualEvaluationConfigurationError(
                    "valid sample records require accepted nonempty results"
                )
        elif self.reason is VisualEvaluationReason.ACCEPTED:
            raise VisualEvaluationConfigurationError(
                "rejected sample record cannot claim acceptance"
            )

    def document(self) -> dict[str, CanonicalValue]:
        return {
            "annotation_matched": self.annotation_matched,
            "latency_ns": self.latency_ns,
            "reason": self.reason.value,
            "result_count": self.result_count,
            "result_sha256s": list(self.result_sha256s),
            "sample_id": self.sample_id,
            "sample_sha256": self.sample_sha256,
            "source_visual_observation_id": self.source_visual_observation_id,
            "status": self.status.value,
        }

    def semantic_document(self) -> dict[str, CanonicalValue]:
        """Exclude measured invocation latency from semantic identity."""
        document = self.document()
        del document["latency_ns"]
        return document


@dataclass(frozen=True, slots=True)
class VisualEvaluationMetrics:
    source_sample_count: int
    attempted_count: int
    admitted_count: int
    rejected_count: int
    valid_result_count: int
    annotation_match_count: int
    producer_failure_count: int
    timeout_count: int
    malformed_result_count: int
    duplicate_result_count: int
    result_count: int
    minimum_latency_ns: int | None
    maximum_latency_ns: int | None
    mean_latency_ns: int | None
    p50_latency_ns: int | None
    p95_latency_ns: int | None
    p99_latency_ns: int | None
    throughput_sample_count: int
    throughput_elapsed_ns: int
    reason_counts: tuple[VisualReasonCount, ...]
    traced_python_current_bytes: int | None = None
    traced_python_peak_bytes: int | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.source_sample_count, "source sample count"),
            (self.attempted_count, "attempted count"),
            (self.admitted_count, "admitted count"),
            (self.rejected_count, "rejected count"),
            (self.valid_result_count, "valid result count"),
            (self.annotation_match_count, "annotation match count"),
            (self.producer_failure_count, "producer failure count"),
            (self.timeout_count, "timeout count"),
            (self.malformed_result_count, "malformed result count"),
            (self.duplicate_result_count, "duplicate result count"),
            (self.result_count, "result count"),
            (self.throughput_sample_count, "throughput sample count"),
        ):
            bounded_int(value, name, maximum=MAX_DATASET_SAMPLES * MAX_RESULTS_PER_SAMPLE)
        bounded_int(
            self.throughput_elapsed_ns,
            "throughput elapsed time",
            maximum=MAX_OBSERVATION_TIME_NS,
        )
        if self.source_sample_count != self.attempted_count:
            raise VisualEvaluationConfigurationError(
                "v1 evaluation attempts every dataset sample exactly once"
            )
        if self.admitted_count + self.rejected_count != self.attempted_count:
            raise VisualEvaluationConfigurationError(
                "admitted and rejected counts must cover all attempted samples"
            )
        if self.valid_result_count > self.attempted_count:
            raise VisualEvaluationConfigurationError(
                "valid result count exceeds attempted samples"
            )
        if self.annotation_match_count > self.valid_result_count:
            raise VisualEvaluationConfigurationError(
                "annotation matches exceed valid results"
            )
        latency_values = (
            self.minimum_latency_ns,
            self.maximum_latency_ns,
            self.mean_latency_ns,
            self.p50_latency_ns,
            self.p95_latency_ns,
            self.p99_latency_ns,
        )
        if self.attempted_count == 0:
            if any(value is not None for value in latency_values):
                raise VisualEvaluationConfigurationError(
                    "empty evaluation cannot claim latency metrics"
                )
        elif any(type(value) is not int or value < 0 for value in latency_values):
            raise VisualEvaluationConfigurationError(
                "nonempty evaluation requires nonnegative integer latency metrics"
            )
        if (
            type(self.reason_counts) is not tuple
            or len(self.reason_counts) > MAX_EVALUATION_REASON_COUNTS
            or any(type(item) is not VisualReasonCount for item in self.reason_counts)
        ):
            raise VisualEvaluationConfigurationError(
                "evaluation reason counts must be bounded and typed"
            )
        reasons = tuple(item.reason.value for item in self.reason_counts)
        if reasons != tuple(sorted(set(reasons))):
            raise VisualEvaluationConfigurationError(
                "evaluation reason counts must be unique and sorted"
            )
        for value, name in (
            (self.traced_python_current_bytes, "traced Python current bytes"),
            (self.traced_python_peak_bytes, "traced Python peak bytes"),
        ):
            if value is not None:
                bounded_int(value, name, maximum=(1 << 63) - 1)
        if (
            self.traced_python_current_bytes is not None
            and self.traced_python_peak_bytes is not None
            and self.traced_python_current_bytes > self.traced_python_peak_bytes
        ):
            raise VisualEvaluationConfigurationError(
                "traced current Python memory cannot exceed traced peak"
            )

    def document(self) -> dict[str, CanonicalValue]:
        return {
            "admitted_count": self.admitted_count,
            "annotation_match_count": self.annotation_match_count,
            "attempted_count": self.attempted_count,
            "duplicate_result_count": self.duplicate_result_count,
            "malformed_result_count": self.malformed_result_count,
            "maximum_latency_ns": self.maximum_latency_ns,
            "mean_latency_ns": self.mean_latency_ns,
            "minimum_latency_ns": self.minimum_latency_ns,
            "p50_latency_ns": self.p50_latency_ns,
            "p95_latency_ns": self.p95_latency_ns,
            "p99_latency_ns": self.p99_latency_ns,
            "producer_failure_count": self.producer_failure_count,
            "reason_counts": [item.document() for item in self.reason_counts],
            "rejected_count": self.rejected_count,
            "result_count": self.result_count,
            "source_sample_count": self.source_sample_count,
            "throughput_elapsed_ns": self.throughput_elapsed_ns,
            "throughput_sample_count": self.throughput_sample_count,
            "timeout_count": self.timeout_count,
            "traced_python_current_bytes": self.traced_python_current_bytes,
            "traced_python_peak_bytes": self.traced_python_peak_bytes,
            "valid_result_count": self.valid_result_count,
        }

    def semantic_document(self) -> dict[str, CanonicalValue]:
        """Stable counts only; latency, throughput, and tracemalloc are execution data."""
        return {
            "admitted_count": self.admitted_count,
            "annotation_match_count": self.annotation_match_count,
            "attempted_count": self.attempted_count,
            "duplicate_result_count": self.duplicate_result_count,
            "malformed_result_count": self.malformed_result_count,
            "producer_failure_count": self.producer_failure_count,
            "reason_counts": [item.document() for item in self.reason_counts],
            "rejected_count": self.rejected_count,
            "result_count": self.result_count,
            "source_sample_count": self.source_sample_count,
            "timeout_count": self.timeout_count,
            "valid_result_count": self.valid_result_count,
        }


@dataclass(frozen=True, slots=True)
class VisualEvaluationReport:
    run_id: str
    producer_id: str
    producer_version: str
    producer_implementation_sha256: str
    producer_manifest_sha256: str
    model: VisualModelProvenance
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str
    policy_id: str
    policy_version: str
    policy_sha256: str
    result_schema_version: str
    started_at_monotonic_ns: int
    completed_at_monotonic_ns: int
    metrics: VisualEvaluationMetrics
    records: tuple[VisualSampleEvaluationRecord, ...]
    decision: VisualEvaluationDecision
    decision_reasons: tuple[VisualEvaluationReason, ...]
    software_identities: tuple[str, ...]
    semantic_sha256: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        identifier(self.run_id, "evaluation run identity", maximum=192)
        identifier(self.producer_id, "evaluation producer identity")
        semver(self.producer_version, "evaluation producer version")
        sha256_hex(
            self.producer_implementation_sha256,
            "evaluation producer implementation",
        )
        sha256_hex(self.producer_manifest_sha256, "evaluation producer manifest")
        if type(self.model) is not VisualModelProvenance:
            raise VisualEvaluationConfigurationError(
                "evaluation report requires model provenance"
            )
        if self.model.producer_id != self.producer_id:
            raise VisualEvaluationConfigurationError(
                "evaluation report producer and model provenance disagree"
            )
        identifier(self.dataset_id, "evaluation dataset identity")
        semver(self.dataset_version, "evaluation dataset version")
        sha256_hex(self.dataset_manifest_sha256, "evaluation dataset manifest")
        identifier(self.policy_id, "evaluation policy identity")
        semver(self.policy_version, "evaluation policy version")
        sha256_hex(self.policy_sha256, "evaluation policy fingerprint")
        semver(self.result_schema_version, "evaluation result schema version")
        bounded_int(
            self.started_at_monotonic_ns,
            "evaluation monotonic start",
            maximum=MAX_OBSERVATION_TIME_NS,
        )
        bounded_int(
            self.completed_at_monotonic_ns,
            "evaluation monotonic completion",
            minimum=self.started_at_monotonic_ns,
            maximum=MAX_OBSERVATION_TIME_NS,
        )
        if type(self.metrics) is not VisualEvaluationMetrics:
            raise VisualEvaluationConfigurationError(
                "evaluation report metrics must be typed"
            )
        if (
            type(self.records) is not tuple
            or len(self.records) != self.metrics.source_sample_count
            or any(type(item) is not VisualSampleEvaluationRecord for item in self.records)
        ):
            raise VisualEvaluationConfigurationError(
                "evaluation report records must cover the dataset exactly"
            )
        record_ids = tuple(item.sample_id for item in self.records)
        if record_ids != tuple(sorted(set(record_ids))):
            raise VisualEvaluationConfigurationError(
                "evaluation records must be unique and sorted by sample identity"
            )
        if not isinstance(self.decision, VisualEvaluationDecision):
            raise VisualEvaluationConfigurationError(
                "evaluation decision must be typed"
            )
        if (
            type(self.decision_reasons) is not tuple
            or len(self.decision_reasons) > MAX_EVALUATION_REASON_COUNTS
            or any(
                not isinstance(item, VisualEvaluationReason)
                for item in self.decision_reasons
            )
        ):
            raise VisualEvaluationConfigurationError(
                "evaluation decision reasons must be bounded and typed"
            )
        reasons = tuple(
            sorted(set(self.decision_reasons), key=lambda item: item.value)
        )
        if reasons != self.decision_reasons:
            raise VisualEvaluationConfigurationError(
                "evaluation decision reasons must be unique and sorted"
            )
        if (
            type(self.software_identities) is not tuple
            or not self.software_identities
            or len(self.software_identities) > MAX_EVALUATION_SOFTWARE_IDENTITIES
        ):
            raise VisualEvaluationConfigurationError(
                "software provenance must be a nonempty bounded tuple"
            )
        software = tuple(
            identifier(item, "evaluation software identity", maximum=192)
            for item in self.software_identities
        )
        if software != tuple(sorted(set(software))):
            raise VisualEvaluationConfigurationError(
                "software identities must be unique and sorted"
            )
        valid_records = tuple(
            item
            for item in self.records
            if item.status is VisualSampleEvaluationStatus.VALID
        )
        reason_counts: dict[VisualEvaluationReason, int] = {}
        for record in self.records:
            reason_counts[record.reason] = reason_counts.get(record.reason, 0) + 1
        expected_reason_counts = tuple(
            VisualReasonCount(reason, count)
            for reason, count in sorted(
                reason_counts.items(), key=lambda item: item[0].value
            )
        )
        malformed_reasons = {
            VisualEvaluationReason.PRODUCER_IDENTITY_MISMATCH,
            VisualEvaluationReason.MODEL_PROVENANCE_MISMATCH,
            VisualEvaluationReason.MALFORMED_RESULT,
            VisualEvaluationReason.RESULT_COLLECTION_OVERSIZED,
            VisualEvaluationReason.SOURCE_OBSERVATION_MISMATCH,
            VisualEvaluationReason.RESULT_TIME_INVALID,
            VisualEvaluationReason.RESULT_SCHEMA_MISMATCH,
            VisualEvaluationReason.CATEGORY_NOT_ALLOWED,
            VisualEvaluationReason.CONFIDENCE_SEMANTICS_MISMATCH,
            VisualEvaluationReason.DETECTION_COUNT_EXCEEDED,
            VisualEvaluationReason.LABEL_LENGTH_EXCEEDED,
        }
        if (
            self.metrics.valid_result_count != len(valid_records)
            or self.metrics.annotation_match_count
            != sum(item.annotation_matched for item in valid_records)
            or self.metrics.result_count
            != sum(item.result_count for item in self.records)
            or self.metrics.timeout_count
            != sum(
                item.reason is VisualEvaluationReason.PRODUCER_TIMEOUT
                for item in self.records
            )
            or self.metrics.producer_failure_count
            != sum(
                item.reason
                in {
                    VisualEvaluationReason.PRODUCER_FAILURE,
                    VisualEvaluationReason.PROCESS_CLEANUP_FAILED,
                }
                for item in self.records
            )
            or self.metrics.duplicate_result_count
            != sum(
                item.reason is VisualEvaluationReason.DUPLICATE_RESULT
                for item in self.records
            )
            or self.metrics.malformed_result_count
            != sum(item.reason in malformed_reasons for item in self.records)
            or self.metrics.reason_counts != expected_reason_counts
        ):
            raise VisualEvaluationConfigurationError(
                "evaluation metrics do not match immutable sample records"
            )
        latencies = tuple(sorted(item.latency_ns for item in self.records))
        if latencies:
            def percentile(percent: int) -> int:
                index = max(0, (percent * len(latencies) + 99) // 100 - 1)
                return latencies[index]

            expected_latencies = (
                latencies[0],
                latencies[-1],
                sum(latencies) // len(latencies),
                percentile(50),
                percentile(95),
                percentile(99),
            )
            actual_latencies = (
                self.metrics.minimum_latency_ns,
                self.metrics.maximum_latency_ns,
                self.metrics.mean_latency_ns,
                self.metrics.p50_latency_ns,
                self.metrics.p95_latency_ns,
                self.metrics.p99_latency_ns,
            )
            if actual_latencies != expected_latencies:
                raise VisualEvaluationConfigurationError(
                    "evaluation latency metrics do not match sample records"
                )
        meets = self.decision is VisualEvaluationDecision.MEETS_MECHANICAL_POLICY
        expected_admitted = len(valid_records) if meets else 0
        if (
            self.metrics.admitted_count != expected_admitted
            or self.metrics.rejected_count
            != self.metrics.attempted_count - expected_admitted
            or self.metrics.throughput_sample_count != self.metrics.attempted_count
            or self.metrics.throughput_elapsed_ns
            != self.completed_at_monotonic_ns - self.started_at_monotonic_ns
        ):
            raise VisualEvaluationConfigurationError(
                "evaluation admission or throughput counts are inconsistent"
            )
        if meets == bool(self.decision_reasons):
            raise VisualEvaluationConfigurationError(
                "mechanical decision and decision reasons disagree"
            )
        derived = fingerprint(self.semantic_document())
        if self.semantic_sha256 is not None and self.semantic_sha256 != derived:
            raise VisualEvaluationConfigurationError(
                "evaluation semantic fingerprint does not match its content"
            )
        object.__setattr__(self, "semantic_sha256", derived)

    def semantic_document(self) -> dict[str, CanonicalValue]:
        """Exclude run/timing/resource measurements that vary by execution."""
        return {
            "decision": self.decision.value,
            "decision_reasons": [item.value for item in self.decision_reasons],
            "dataset_id": self.dataset_id,
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "dataset_version": self.dataset_version,
            "metrics": self.metrics.semantic_document(),
            "model_provenance_sha256": self.model.provenance_sha256,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "policy_version": self.policy_version,
            "producer_id": self.producer_id,
            "producer_implementation_sha256": (
                self.producer_implementation_sha256
            ),
            "producer_manifest_sha256": self.producer_manifest_sha256,
            "producer_version": self.producer_version,
            "records": [item.semantic_document() for item in self.records],
            "result_schema_version": self.result_schema_version,
            "schema": "ayyo.visual-evaluation-report.v1",
            "software_identities": list(self.software_identities),
        }


_ADMISSION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class EvaluatedVisualAdmission:
    """Evaluator-issued handoff; bare producer output is never authorization."""

    observation: VisualInterpretationObservation
    producer_result: VisualProducerResult
    report: VisualEvaluationReport
    reference: VisualEvaluationReference
    requirement: VisualEvaluationRequirement
    evidence_kind: VisualAdmissionEvidenceKind

    def __init__(
        self,
        *,
        observation: VisualInterpretationObservation,
        producer_result: VisualProducerResult,
        report: VisualEvaluationReport,
        reference: VisualEvaluationReference,
        requirement: VisualEvaluationRequirement,
        evidence_kind: VisualAdmissionEvidenceKind,
        _seal: object,
    ) -> None:
        if _seal is not _ADMISSION_SEAL:
            raise VisualEvaluationConfigurationError(
                "evaluated admission can only be issued by the evaluator"
            )
        if (
            type(observation) is not VisualInterpretationObservation
            or type(producer_result) is not VisualProducerResult
            or type(report) is not VisualEvaluationReport
            or type(reference) is not VisualEvaluationReference
            or type(requirement) is not VisualEvaluationRequirement
        ):
            raise VisualEvaluationConfigurationError(
                "evaluated admission requires exact typed evidence and provenance"
            )
        if not isinstance(evidence_kind, VisualAdmissionEvidenceKind):
            raise VisualEvaluationConfigurationError(
                "evaluated admission evidence kind must be typed"
            )
        if report.decision is not VisualEvaluationDecision.MEETS_MECHANICAL_POLICY:
            raise VisualEvaluationConfigurationError(
                "failed evaluation cannot issue an admission"
            )
        if observation.evaluation_reference != reference:
            raise VisualEvaluationConfigurationError(
                "admitted observation and evaluation reference disagree"
            )
        if (
            observation.robot_id != producer_result.source_frame.robot_id
            or observation.sensor != producer_result.source_frame.sensor
            or observation.reference_frame_id
            != producer_result.source_frame.sensor.frame_id
            or observation.source_visual_observation_id
            != producer_result.source_frame.observation_id
            or observation.source_visual_fingerprint
            != producer_result.source_frame.fingerprint
            or observation.observed_at_ns
            != producer_result.source_frame.observed_at_ns
            or observation.result_at_ns != producer_result.result_at_ns
            or observation.producer != producer_result.producer
            or observation.detections != producer_result.detections
            or observation.provenance != producer_result.source_frame.provenance
        ):
            raise VisualEvaluationConfigurationError(
                "admitted observation differs from its evaluated producer result"
            )
        if report.semantic_sha256 != reference.report_semantic_sha256:
            raise VisualEvaluationConfigurationError(
                "admission report and compact reference disagree"
            )
        if not requirement.matches(observation.producer, reference):
            raise VisualEvaluationConfigurationError(
                "admission does not satisfy its exact evaluation requirement"
            )
        matching_records = tuple(
            record
            for record in report.records
            if record.source_visual_observation_id
            == producer_result.source_frame.observation_id
            and producer_result.result_sha256 in record.result_sha256s
            and record.status is VisualSampleEvaluationStatus.VALID
        )
        if (
            evidence_kind is VisualAdmissionEvidenceKind.RECORDED_EVALUATION_SAMPLE
            and len(matching_records) != 1
        ):
            raise VisualEvaluationConfigurationError(
                "admission result is absent from the mechanically valid report records"
            )
        object.__setattr__(self, "observation", observation)
        object.__setattr__(self, "producer_result", producer_result)
        object.__setattr__(self, "report", report)
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "requirement", requirement)
        object.__setattr__(self, "evidence_kind", evidence_kind)


def _issue_evaluated_admission(
    *,
    observation: VisualInterpretationObservation,
    producer_result: VisualProducerResult,
    report: VisualEvaluationReport,
    reference: VisualEvaluationReference,
    requirement: VisualEvaluationRequirement,
    evidence_kind: VisualAdmissionEvidenceKind,
) -> EvaluatedVisualAdmission:
    return EvaluatedVisualAdmission(
        observation=observation,
        producer_result=producer_result,
        report=report,
        reference=reference,
        requirement=requirement,
        evidence_kind=evidence_kind,
        _seal=_ADMISSION_SEAL,
    )


@dataclass(frozen=True, slots=True)
class VisualEvaluationOutcome:
    report: VisualEvaluationReport
    admissions: tuple[EvaluatedVisualAdmission, ...]

    def __post_init__(self) -> None:
        if type(self.report) is not VisualEvaluationReport:
            raise VisualEvaluationConfigurationError(
                "evaluation outcome requires one immutable report"
            )
        if (
            type(self.admissions) is not tuple
            or any(
                type(item) is not EvaluatedVisualAdmission
                for item in self.admissions
            )
        ):
            raise VisualEvaluationConfigurationError(
                "evaluation outcome admissions must be a typed tuple"
            )
        meets = (
            self.report.decision
            is VisualEvaluationDecision.MEETS_MECHANICAL_POLICY
        )
        if meets and len(self.admissions) != self.report.metrics.admitted_count:
            raise VisualEvaluationConfigurationError(
                "passing evaluation must expose exactly its admitted observations"
            )
        if not meets and self.admissions:
            raise VisualEvaluationConfigurationError(
                "failed mechanical evaluation cannot expose admissions"
            )
        if any(item.report != self.report for item in self.admissions):
            raise VisualEvaluationConfigurationError(
                "all admissions must bind the exact outcome report"
            )
        observation_ids = tuple(item.observation.observation_id for item in self.admissions)
        if observation_ids != tuple(sorted(set(observation_ids))):
            raise VisualEvaluationConfigurationError(
                "outcome admissions must be unique and sorted by observation identity"
            )

    @property
    def observations(self) -> tuple[VisualInterpretationObservation, ...]:
        return tuple(item.observation for item in self.admissions)
