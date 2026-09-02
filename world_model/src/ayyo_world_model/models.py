"""Immutable observations and projected embodied world-state records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
import re
from typing import Mapping, TypeAlias

from .canonical import JSONValue, copy_json, copy_mapping, sha256_document
from .errors import (
    ObservationIdentityError,
    SnapshotIdentityError,
    WorldModelFailureCode,
    WorldModelValidationError,
)


WORLD_MODEL_SCHEMA_VERSION = 1
AYYO_ROBOT_ID = "ayyo.robot.v1"
MAX_OBSERVATION_ITEMS = 128
MAX_ENVIRONMENT_ENTITIES = 256
MAX_OBSERVATION_TIME_NS = (1 << 63) - 1
MAX_SENSOR_IDENTITIES = 32
MAX_CAMERA_DIMENSION = 4_096
MAX_CAMERA_PIXELS = 16_777_216
MAX_IMAGE_DATA_BYTES = 64 * 1_024 * 1_024
MAX_AUDIO_FRAME_COUNT = 16_000
MAX_AUDIO_DATA_BYTES = 32_000
MAX_VISUAL_DETECTIONS = 32
MAX_VISUAL_INTERPRETATION_PRODUCERS = 16
MAX_VISUAL_LABEL_LENGTH = 64
MAX_VISUAL_PRODUCER_ID_LENGTH = 128
MAX_VISUAL_SOURCE_REFERENCES = 64
MAX_VISUAL_EVALUATION_REQUIREMENTS = 16
MAX_SEMANTIC_EVIDENCE_ITEMS = MAX_VISUAL_DETECTIONS
MAX_SEMANTIC_EVIDENCE_STATES = MAX_VISUAL_SOURCE_REFERENCES
QUATERNION_NORM_TOLERANCE = 1e-6

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_FRAME = re.compile(r"^[A-Za-z][A-Za-z0-9_/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CALIBRATION_ID = re.compile(r"^camera-calibration-sha256-[0-9a-f]{64}$")
_DEPTH_CALIBRATION_RECORD_ID = re.compile(
    r"^depth-camera-calibration-sha256-[0-9a-f]{64}$"
)
_DEPTH_SOURCE_MANIFEST_ID = re.compile(
    r"^depth-camera-source-sha256-[0-9a-f]{64}$"
)
_DEPTH_SESSION_ID = re.compile(r"^depth-camera-session-sha256-[0-9a-f]{64}$")
_AUDIO_SOURCE_MANIFEST_ID = re.compile(
    r"^audio-source-sha256-[0-9a-f]{64}$"
)
_AUDIO_SESSION_ID = re.compile(r"^audio-session-sha256-[0-9a-f]{64}$")
_OBSERVATION_ID = re.compile(r"^world-observation-[0-9a-f]{64}$")
_SEMANTIC_OBSERVATION_ID = re.compile(
    r"^(person|object)-observation-sha256-[0-9a-f]{64}$"
)
_VISUAL_DETECTION_ID = re.compile(
    r"^visual-detection-sha256-[0-9a-f]{64}$"
)


def _invalid(code: WorldModelFailureCode, detail: str) -> None:
    raise WorldModelValidationError(code, detail)


def canonical_identifier(value: object, field_name: str, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _IDENTIFIER.fullmatch(value) is None
    ):
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must be a bounded lowercase ASCII identifier",
        )
    return value


def _frame_id(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 256
        or _FRAME.fullmatch(value) is None
        or "//" in value
        or value.endswith("/")
    ):
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} is not a bounded canonical frame identifier",
        )
    return value


def _finite(value: object, field_name: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must be a finite real number",
        )
    result = float(value)
    return 0.0 if result == 0.0 else result


def _vector(
    value: object,
    field_name: str,
    *,
    dimension: int,
) -> tuple[float, ...]:
    if type(value) is not tuple or len(value) != dimension:
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must contain exactly {dimension} values",
        )
    return tuple(_finite(item, field_name) for item in value)


def _quaternion(value: object, field_name: str) -> tuple[float, float, float, float]:
    raw = _vector(value, field_name, dimension=4)
    norm = math.sqrt(sum(item * item for item in raw))
    if norm == 0.0 or abs(norm - 1.0) > QUATERNION_NORM_TOLERANCE:
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must be a normalized non-zero quaternion",
        )
    normalized = tuple(item / norm for item in raw)
    # q and -q encode the same rotation. Select one representation so semantic
    # identity does not depend on a producer's quaternion sign convention.
    for item in reversed(normalized):
        if item == 0.0:
            continue
        if item < 0.0:
            normalized = tuple(-component for component in normalized)
        break
    canonical = tuple(0.0 if component == 0.0 else component for component in normalized)
    return canonical  # type: ignore[return-value]


def _confidence(value: object) -> float:
    result = _finite(value, "confidence")
    if not 0.0 <= result <= 1.0:
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            "confidence must be between 0.0 and 1.0",
        )
    return result


class ObservationSourceKind(StrEnum):
    SIMULATION = "simulation"
    PHYSICAL_SENSOR = "physical_sensor"
    RECORDED_DATA = "recorded_data"
    TEST_FIXTURE = "test_fixture"


class ObservationClock(StrEnum):
    ROS_SIMULATION_TIME = "ros_simulation_time"
    ROS_SYSTEM_TIME = "ros_system_time"
    RECORDED_TIME = "recorded_time"
    TEST_TIME = "test_time"


class ObservationTransport(StrEnum):
    ROS2 = "ros2"
    DIRECT = "direct"
    RECORDED = "recorded"


class SensorKind(StrEnum):
    JOINT_STATE = "joint_state"
    IMU = "imu"
    BODY_POSE = "body_pose"
    RGB_CAMERA = "rgb_camera"
    DEPTH_CAMERA = "depth_camera"
    RGBD_FUSION = "rgbd_fusion"
    MICROPHONE = "microphone"


class SensorAvailability(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    ERROR = "error"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class VisualCoordinateSpace(StrEnum):
    NORMALIZED_IMAGE = "normalized_image"


class VisualSemanticCategory(StrEnum):
    TEST_PATTERN = "test_pattern"
    OBJECT = "object"
    PERSON = "person"
    SURFACE = "surface"
    LANDMARK = "landmark"
    OBSTACLE = "obstacle"
    UNKNOWN = "unknown"


class SemanticEvidenceKind(StrEnum):
    """Anonymous semantic meanings that may enter temporary world state."""

    PERSON = "person"
    OBJECT = "object"


class VisualProducerKind(StrEnum):
    TEST_FIXTURE = "test_fixture"
    SIMULATION_PROCESSOR = "simulation_processor"
    PHYSICAL_PROCESSOR = "physical_processor"
    RECORDED_PROCESSOR = "recorded_processor"


class VisualModelFormat(StrEnum):
    DETERMINISTIC_FIXTURE = "deterministic_fixture"
    ONNX = "onnx"
    TENSORFLOW_LITE = "tensorflow_lite"
    TORCHSCRIPT = "torchscript"
    OTHER_REVIEWED = "other_reviewed"


class VisualModelCapability(StrEnum):
    BOUNDED_DETECTION = "bounded_detection"
    CLASSIFICATION = "classification"
    KEYPOINTS = "keypoints"
    OCR = "ocr"
    SCENE_LABELS = "scene_labels"


class VisualModelSourceClassification(StrEnum):
    TEST_FIXTURE = "test_fixture"
    EVALUATION_CANDIDATE = "evaluation_candidate"
    PROJECT_REVIEWED_ARTIFACT = "project_reviewed_artifact"


class VisualEvaluationDecision(StrEnum):
    MEETS_MECHANICAL_POLICY = "meets_mechanical_policy"
    DOES_NOT_MEET_MECHANICAL_POLICY = "does_not_meet_mechanical_policy"


_CLOCK_BY_SOURCE = {
    ObservationSourceKind.SIMULATION: ObservationClock.ROS_SIMULATION_TIME,
    ObservationSourceKind.PHYSICAL_SENSOR: ObservationClock.ROS_SYSTEM_TIME,
    ObservationSourceKind.RECORDED_DATA: ObservationClock.RECORDED_TIME,
    ObservationSourceKind.TEST_FIXTURE: ObservationClock.TEST_TIME,
}


@dataclass(frozen=True, slots=True)
class ObservationProvenance:
    source_kind: ObservationSourceKind
    source_id: str
    clock: ObservationClock
    transport: ObservationTransport
    interface: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, ObservationSourceKind):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "source_kind must be an ObservationSourceKind",
            )
        if not isinstance(self.clock, ObservationClock):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "clock must be an ObservationClock",
            )
        if not isinstance(self.transport, ObservationTransport):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "transport must be an ObservationTransport",
            )
        try:
            canonical_identifier(self.source_id, "provenance source_id")
            canonical_identifier(self.interface, "provenance interface")
        except WorldModelValidationError as error:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                error.detail,
            ) from error
        if self.clock is not _CLOCK_BY_SOURCE[self.source_kind]:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "source kind and source clock do not match",
            )
        if (
            self.source_kind is ObservationSourceKind.RECORDED_DATA
            and self.transport is not ObservationTransport.RECORDED
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "recorded evidence must use the recorded transport",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "clock": self.clock.value,
            "interface": self.interface,
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "transport": self.transport.value,
        }


@dataclass(frozen=True, slots=True)
class SensorIdentity:
    sensor_id: str
    kind: SensorKind
    frame_id: str

    def __post_init__(self) -> None:
        canonical_identifier(self.sensor_id, "sensor_id")
        if not isinstance(self.kind, SensorKind):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "sensor kind must be a SensorKind",
            )
        _frame_id(self.frame_id, "sensor frame_id")

    def document(self) -> dict[str, JSONValue]:
        return {
            "frame_id": self.frame_id,
            "kind": self.kind.value,
            "sensor_id": self.sensor_id,
        }


@dataclass(frozen=True, slots=True)
class VisualInterpretationProducer:
    """Exact identity of one bounded visual-result producer and adapter."""

    producer_id: str
    kind: VisualProducerKind
    model_id: str
    adapter_id: str
    interface: str

    def __post_init__(self) -> None:
        canonical_identifier(
            self.producer_id,
            "visual producer_id",
            maximum=MAX_VISUAL_PRODUCER_ID_LENGTH,
        )
        if not isinstance(self.kind, VisualProducerKind):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual producer kind must be typed",
            )
        for value, field_name in (
            (self.model_id, "visual model_id"),
            (self.adapter_id, "visual adapter_id"),
            (self.interface, "visual producer interface"),
        ):
            canonical_identifier(
                value,
                field_name,
                maximum=MAX_VISUAL_PRODUCER_ID_LENGTH,
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "adapter_id": self.adapter_id,
            "interface": self.interface,
            "kind": self.kind.value,
            "model_id": self.model_id,
            "producer_id": self.producer_id,
        }


def _sha256_digest(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            f"{field_name} must be a lowercase SHA-256 digest",
        )
    return value


@dataclass(frozen=True, slots=True, init=False)
class VisualModelProvenance:
    """Immutable model-artifact identity; never a mutable filesystem path."""

    model_id: str
    model_version: str
    producer_id: str
    artifact_sha256: str
    model_format: VisualModelFormat
    capability: VisualModelCapability
    configuration_sha256: str
    label_schema_id: str
    label_schema_version: str
    source_classification: VisualModelSourceClassification
    build_export_id: str | None
    provenance_sha256: str

    def __init__(
        self,
        *,
        model_id: str,
        model_version: str,
        producer_id: str,
        artifact_sha256: str,
        model_format: VisualModelFormat,
        capability: VisualModelCapability,
        configuration_sha256: str,
        label_schema_id: str,
        label_schema_version: str,
        source_classification: VisualModelSourceClassification,
        build_export_id: str | None = None,
        provenance_sha256: str | None = None,
    ) -> None:
        for value, field_name in (
            (model_id, "visual model_id"),
            (model_version, "visual model_version"),
            (producer_id, "visual model producer_id"),
            (label_schema_id, "visual label_schema_id"),
            (label_schema_version, "visual label_schema_version"),
        ):
            canonical_identifier(
                value,
                field_name,
                maximum=MAX_VISUAL_PRODUCER_ID_LENGTH,
            )
        artifact = _sha256_digest(artifact_sha256, "visual model artifact")
        configuration = _sha256_digest(
            configuration_sha256,
            "visual model configuration",
        )
        if not isinstance(model_format, VisualModelFormat):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual model format must be typed",
            )
        if not isinstance(capability, VisualModelCapability):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual model capability must be typed",
            )
        if not isinstance(source_classification, VisualModelSourceClassification):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual model source classification must be typed",
            )
        if build_export_id is not None:
            canonical_identifier(
                build_export_id,
                "visual model build/export identity",
                maximum=MAX_VISUAL_PRODUCER_ID_LENGTH,
            )
        document: dict[str, JSONValue] = {
            "artifact_sha256": artifact,
            "build_export_id": build_export_id,
            "capability": capability.value,
            "configuration_sha256": configuration,
            "label_schema_id": label_schema_id,
            "label_schema_version": label_schema_version,
            "model_format": model_format.value,
            "model_id": model_id,
            "model_version": model_version,
            "producer_id": producer_id,
            "schema": "ayyo.visual-model-provenance.v1",
            "source_classification": source_classification.value,
        }
        derived = sha256_document(document)
        if provenance_sha256 is not None and provenance_sha256 != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "visual model provenance fingerprint does not match its content",
            )
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "model_version", model_version)
        object.__setattr__(self, "producer_id", producer_id)
        object.__setattr__(self, "artifact_sha256", artifact)
        object.__setattr__(self, "model_format", model_format)
        object.__setattr__(self, "capability", capability)
        object.__setattr__(self, "configuration_sha256", configuration)
        object.__setattr__(self, "label_schema_id", label_schema_id)
        object.__setattr__(self, "label_schema_version", label_schema_version)
        object.__setattr__(self, "source_classification", source_classification)
        object.__setattr__(self, "build_export_id", build_export_id)
        object.__setattr__(self, "provenance_sha256", derived)

    def document(self) -> dict[str, JSONValue]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "build_export_id": self.build_export_id,
            "capability": self.capability.value,
            "configuration_sha256": self.configuration_sha256,
            "label_schema_id": self.label_schema_id,
            "label_schema_version": self.label_schema_version,
            "model_format": self.model_format.value,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "producer_id": self.producer_id,
            "provenance_sha256": self.provenance_sha256,
            "source_classification": self.source_classification.value,
        }


@dataclass(frozen=True, slots=True)
class VisualEvaluationReference:
    """Compact mechanically-evaluated provenance carried by trusted evidence."""

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
    report_semantic_sha256: str
    result_schema_version: str
    decision: VisualEvaluationDecision

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.producer_version, "visual producer version"),
            (self.dataset_id, "visual evaluation dataset_id"),
            (self.dataset_version, "visual evaluation dataset_version"),
            (self.policy_id, "visual evaluation policy_id"),
            (self.policy_version, "visual evaluation policy_version"),
            (self.result_schema_version, "visual result schema version"),
        ):
            canonical_identifier(
                value,
                field_name,
                maximum=MAX_VISUAL_PRODUCER_ID_LENGTH,
            )
        for value, field_name in (
            (
                self.producer_implementation_sha256,
                "visual producer implementation",
            ),
            (self.producer_manifest_sha256, "visual producer manifest"),
            (self.dataset_manifest_sha256, "visual dataset manifest"),
            (self.policy_sha256, "visual evaluation policy"),
            (self.report_semantic_sha256, "visual evaluation report"),
        ):
            _sha256_digest(value, field_name)
        if type(self.model) is not VisualModelProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual evaluation model provenance must be typed",
            )
        if self.decision is not VisualEvaluationDecision.MEETS_MECHANICAL_POLICY:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "only mechanically eligible evidence may carry an evaluation reference",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "dataset_version": self.dataset_version,
            "decision": self.decision.value,
            "model": self.model.document(),
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "policy_version": self.policy_version,
            "producer_implementation_sha256": (
                self.producer_implementation_sha256
            ),
            "producer_manifest_sha256": self.producer_manifest_sha256,
            "producer_version": self.producer_version,
            "report_semantic_sha256": self.report_semantic_sha256,
            "result_schema_version": self.result_schema_version,
        }


def visual_evaluation_reference_sha256(
    reference: VisualEvaluationReference | None,
) -> str | None:
    """Return the compact deterministic identity of evaluated provenance."""
    if reference is None:
        return None
    if type(reference) is not VisualEvaluationReference:
        _invalid(
            WorldModelFailureCode.MALFORMED_OBSERVATION,
            "visual evaluation reference must be typed",
        )
    return sha256_document(reference.document())


@dataclass(frozen=True, slots=True)
class VisualEvaluationRequirement:
    """Exact allowlist binding for one evaluated producer and policy."""

    producer_id: str
    producer_version: str
    producer_implementation_sha256: str
    producer_manifest_sha256: str
    model_provenance_sha256: str
    model_artifact_sha256: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str
    policy_id: str
    policy_version: str
    policy_sha256: str
    report_semantic_sha256: str
    result_schema_version: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.producer_id, "required visual producer_id"),
            (self.producer_version, "required visual producer version"),
            (self.dataset_id, "required visual dataset_id"),
            (self.dataset_version, "required visual dataset_version"),
            (self.policy_id, "required visual policy_id"),
            (self.policy_version, "required visual policy_version"),
            (self.result_schema_version, "required visual result schema version"),
        ):
            canonical_identifier(
                value,
                field_name,
                maximum=MAX_VISUAL_PRODUCER_ID_LENGTH,
            )
        for value, field_name in (
            (
                self.producer_implementation_sha256,
                "required visual producer implementation",
            ),
            (self.producer_manifest_sha256, "required visual producer manifest"),
            (self.model_provenance_sha256, "required visual model provenance"),
            (self.model_artifact_sha256, "required visual model artifact"),
            (self.dataset_manifest_sha256, "required visual dataset manifest"),
            (self.policy_sha256, "required visual evaluation policy"),
            (self.report_semantic_sha256, "required visual evaluation report"),
        ):
            _sha256_digest(value, field_name)

    def matches(
        self,
        producer: VisualInterpretationProducer,
        reference: VisualEvaluationReference,
    ) -> bool:
        return (
            type(producer) is VisualInterpretationProducer
            and type(reference) is VisualEvaluationReference
            and producer.producer_id == self.producer_id
            and reference.model.producer_id == producer.producer_id
            and reference.model.model_id == producer.model_id
            and reference.producer_version == self.producer_version
            and reference.producer_implementation_sha256
            == self.producer_implementation_sha256
            and reference.producer_manifest_sha256
            == self.producer_manifest_sha256
            and reference.model.provenance_sha256
            == self.model_provenance_sha256
            and reference.model.artifact_sha256 == self.model_artifact_sha256
            and reference.dataset_id == self.dataset_id
            and reference.dataset_version == self.dataset_version
            and reference.dataset_manifest_sha256
            == self.dataset_manifest_sha256
            and reference.policy_id == self.policy_id
            and reference.policy_version == self.policy_version
            and reference.policy_sha256 == self.policy_sha256
            and reference.report_semantic_sha256
            == self.report_semantic_sha256
            and reference.result_schema_version == self.result_schema_version
            and reference.decision
            is VisualEvaluationDecision.MEETS_MECHANICAL_POLICY
        )


@dataclass(frozen=True, slots=True, init=False)
class ImageRegion2D:
    """Canonical normalized image-space region: left/top inclusive, right/bottom exclusive."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    coordinate_space: VisualCoordinateSpace

    def __init__(
        self,
        *,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
        coordinate_space: VisualCoordinateSpace = VisualCoordinateSpace.NORMALIZED_IMAGE,
    ) -> None:
        if coordinate_space is not VisualCoordinateSpace.NORMALIZED_IMAGE:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "v1 visual regions require normalized image coordinates",
            )
        left = _finite(x_min, "visual region x_min")
        top = _finite(y_min, "visual region y_min")
        right = _finite(x_max, "visual region x_max")
        bottom = _finite(y_max, "visual region y_max")
        if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual region must be a positive normalized in-image rectangle",
            )
        object.__setattr__(self, "x_min", left)
        object.__setattr__(self, "y_min", top)
        object.__setattr__(self, "x_max", right)
        object.__setattr__(self, "y_max", bottom)
        object.__setattr__(self, "coordinate_space", coordinate_space)

    def document(self) -> dict[str, JSONValue]:
        return {
            "coordinate_space": self.coordinate_space.value,
            "x_max": self.x_max,
            "x_min": self.x_min,
            "y_max": self.y_max,
            "y_min": self.y_min,
        }


@dataclass(frozen=True, slots=True, init=False)
class VisualDetection:
    """One bounded interpretation result tied to an exact admitted source frame."""

    source_visual_observation_id: str
    category: VisualSemanticCategory
    label: str
    region: ImageRegion2D
    confidence: float | None
    detection_id: str

    def __init__(
        self,
        *,
        source_visual_observation_id: str,
        category: VisualSemanticCategory,
        label: str,
        region: ImageRegion2D,
        confidence: float | None = None,
        detection_id: str | None = None,
    ) -> None:
        if (
            type(source_visual_observation_id) is not str
            or _OBSERVATION_ID.fullmatch(source_visual_observation_id) is None
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual detection source-frame identity is malformed",
            )
        if not isinstance(category, VisualSemanticCategory):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual detection category must be typed",
            )
        canonical_identifier(
            label,
            "visual detection label",
            maximum=MAX_VISUAL_LABEL_LENGTH,
        )
        if type(region) is not ImageRegion2D:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual detection region must be typed",
            )
        confidence_value = None if confidence is None else _confidence(confidence)
        document: dict[str, JSONValue] = {
            "category": category.value,
            "confidence": confidence_value,
            "label": label,
            "region": region.document(),
            "schema": "ayyo.visual-detection.v1",
            "source_visual_observation_id": source_visual_observation_id,
        }
        derived_id = f"visual-detection-sha256-{sha256_document(document)}"
        if detection_id is not None and detection_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "visual detection identity does not match its content",
            )
        object.__setattr__(
            self,
            "source_visual_observation_id",
            source_visual_observation_id,
        )
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "region", region)
        object.__setattr__(self, "confidence", confidence_value)
        object.__setattr__(self, "detection_id", derived_id)

    def document(self) -> dict[str, JSONValue]:
        return {
            "category": self.category.value,
            "confidence": self.confidence,
            "detection_id": self.detection_id,
            "label": self.label,
            "region": self.region.document(),
            "source_visual_observation_id": self.source_visual_observation_id,
        }


@dataclass(frozen=True, slots=True, init=False)
class SemanticEvidenceItem:
    """One anonymous frame-local semantic fact, never a persistent entity."""

    kind: SemanticEvidenceKind
    source_semantic_observation_id: str
    source_detection_id: str
    region: ImageRegion2D
    confidence: float | None
    category: str | None

    def __init__(
        self,
        *,
        kind: SemanticEvidenceKind,
        source_semantic_observation_id: str,
        source_detection_id: str,
        region: ImageRegion2D,
        confidence: float | None,
        category: str | None = None,
    ) -> None:
        if not isinstance(kind, SemanticEvidenceKind):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence kind must be typed",
            )
        if (
            type(source_semantic_observation_id) is not str
            or _SEMANTIC_OBSERVATION_ID.fullmatch(
                source_semantic_observation_id
            )
            is None
            or not source_semantic_observation_id.startswith(
                f"{kind.value}-observation-sha256-"
            )
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic source-observation identity is malformed",
            )
        if (
            type(source_detection_id) is not str
            or _VISUAL_DETECTION_ID.fullmatch(source_detection_id) is None
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic source-detection identity is malformed",
            )
        if type(region) is not ImageRegion2D:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence region must be typed",
            )
        confidence_value = None if confidence is None else _confidence(confidence)
        if kind is SemanticEvidenceKind.PERSON:
            if category is not None:
                _invalid(
                    WorldModelFailureCode.MALFORMED_OBSERVATION,
                    "anonymous person evidence cannot carry an object category",
                )
            category_value = None
        else:
            category_value = canonical_identifier(
                category,
                "semantic object category",
                maximum=MAX_VISUAL_LABEL_LENGTH,
            )
            if category_value == SemanticEvidenceKind.PERSON.value:
                _invalid(
                    WorldModelFailureCode.MALFORMED_OBSERVATION,
                    "object evidence cannot substitute for person evidence",
                )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(
            self,
            "source_semantic_observation_id",
            source_semantic_observation_id,
        )
        object.__setattr__(self, "source_detection_id", source_detection_id)
        object.__setattr__(self, "region", region)
        object.__setattr__(self, "confidence", confidence_value)
        object.__setattr__(self, "category", category_value)

    def document(self) -> dict[str, JSONValue]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "kind": self.kind.value,
            "region": self.region.document(),
            "source_detection_id": self.source_detection_id,
            "source_semantic_observation_id": (
                self.source_semantic_observation_id
            ),
        }


@dataclass(frozen=True, slots=True, init=False)
class CameraCalibration:
    """Bounded standard camera calibration metadata, never pixel storage."""

    width: int
    height: int
    distortion_model: str
    d: tuple[float, ...]
    k: tuple[float, ...]
    r: tuple[float, ...]
    p: tuple[float, ...]
    binning_x: int
    binning_y: int
    roi: tuple[int, int, int, int, bool]
    calibration_id: str

    def __init__(
        self,
        *,
        width: int,
        height: int,
        distortion_model: str,
        d: tuple[float, ...],
        k: tuple[float, ...],
        r: tuple[float, ...],
        p: tuple[float, ...],
        binning_x: int = 0,
        binning_y: int = 0,
        roi: tuple[int, int, int, int, bool] = (0, 0, 0, 0, False),
        calibration_id: str | None = None,
    ) -> None:
        if (
            type(width) is not int
            or type(height) is not int
            or not 1 <= width <= MAX_CAMERA_DIMENSION
            or not 1 <= height <= MAX_CAMERA_DIMENSION
            or width * height > MAX_CAMERA_PIXELS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "camera calibration dimensions are outside reviewed bounds",
            )
        if (
            type(distortion_model) is not str
            or not distortion_model
            or len(distortion_model) > 64
            or _IDENTIFIER.fullmatch(distortion_model) is None
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "camera distortion model must be bounded canonical text",
            )
        if type(d) is not tuple or len(d) > 16:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "camera distortion vector exceeds its bound",
            )
        distortion = tuple(_finite(value, "camera distortion") for value in d)
        matrices: list[tuple[float, ...]] = []
        for values, size, field_name in (
            (k, 9, "camera intrinsic matrix"),
            (r, 9, "camera rectification matrix"),
            (p, 12, "camera projection matrix"),
        ):
            if type(values) is not tuple or len(values) != size:
                _invalid(
                    WorldModelFailureCode.MALFORMED_OBSERVATION,
                    f"{field_name} must contain exactly {size} values",
                )
            finite_values = tuple(_finite(value, field_name) for value in values)
            if all(value == 0.0 for value in finite_values):
                _invalid(
                    WorldModelFailureCode.MALFORMED_OBSERVATION,
                    f"{field_name} cannot be an all-zero calibration claim",
                )
            matrices.append(finite_values)
        intrinsic, rectification, projection = matrices
        if intrinsic[0] <= 0.0 or intrinsic[4] <= 0.0 or intrinsic[8] == 0.0:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "camera intrinsic focal lengths and homogeneous scale must be positive",
            )
        if projection[0] <= 0.0 or projection[5] <= 0.0 or projection[10] == 0.0:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "camera projection focal lengths and homogeneous scale must be positive",
            )
        for value, field_name in ((binning_x, "binning_x"), (binning_y, "binning_y")):
            if type(value) is not int or not 0 <= value <= MAX_CAMERA_DIMENSION:
                _invalid(
                    WorldModelFailureCode.MALFORMED_OBSERVATION,
                    f"camera {field_name} is outside its bound",
                )
        if (
            type(roi) is not tuple
            or len(roi) != 5
            or any(type(value) is not int for value in roi[:4])
            or type(roi[4]) is not bool
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "camera ROI metadata is malformed",
            )
        x_offset, y_offset, roi_width, roi_height, do_rectify = roi
        if (
            min(x_offset, y_offset, roi_width, roi_height) < 0
            or x_offset > width
            or y_offset > height
            or roi_width > width - x_offset
            or roi_height > height - y_offset
            or ((roi_width == 0) != (roi_height == 0))
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "camera ROI lies outside the calibrated image",
            )
        document: dict[str, JSONValue] = {
            "binning_x": binning_x,
            "binning_y": binning_y,
            "d": list(distortion),
            "distortion_model": distortion_model,
            "height": height,
            "k": list(intrinsic),
            "p": list(projection),
            "r": list(rectification),
            "roi": [x_offset, y_offset, roi_width, roi_height, do_rectify],
            "schema": "ayyo.camera-calibration.v1",
            "width": width,
        }
        derived_id = f"camera-calibration-sha256-{sha256_document(document)}"
        if calibration_id is not None and calibration_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "camera calibration identity does not match its metadata",
            )
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "distortion_model", distortion_model)
        object.__setattr__(self, "d", distortion)
        object.__setattr__(self, "k", intrinsic)
        object.__setattr__(self, "r", rectification)
        object.__setattr__(self, "p", projection)
        object.__setattr__(self, "binning_x", binning_x)
        object.__setattr__(self, "binning_y", binning_y)
        object.__setattr__(
            self,
            "roi",
            (x_offset, y_offset, roi_width, roi_height, do_rectify),
        )
        object.__setattr__(self, "calibration_id", derived_id)


@dataclass(frozen=True, slots=True)
class CovarianceMatrix:
    """A supplied 3x3 or 6x6 covariance; absence is represented by None."""

    dimension: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if type(self.dimension) is not int or self.dimension not in {3, 6}:
            _invalid(
                WorldModelFailureCode.MALFORMED_COVARIANCE,
                "covariance dimension must be exactly three or six",
            )
        if type(self.values) is not tuple or len(self.values) != self.dimension**2:
            _invalid(
                WorldModelFailureCode.MALFORMED_COVARIANCE,
                "covariance value count does not match its square dimension",
            )
        try:
            values = tuple(_finite(item, "covariance value") for item in self.values)
        except WorldModelValidationError as error:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_COVARIANCE,
                error.detail,
            ) from error
        for row in range(self.dimension):
            diagonal = values[row * self.dimension + row]
            if diagonal < 0.0:
                _invalid(
                    WorldModelFailureCode.MALFORMED_COVARIANCE,
                    "covariance diagonal cannot contain negative variance",
                )
            for column in range(row + 1, self.dimension):
                left = values[row * self.dimension + column]
                right = values[column * self.dimension + row]
                scale = max(1.0, abs(left), abs(right))
                if abs(left - right) > 1e-9 * scale:
                    _invalid(
                        WorldModelFailureCode.MALFORMED_COVARIANCE,
                        "covariance matrix must be symmetric",
                    )
        # A covariance must be positive semidefinite. A bounded LDLᵀ check is
        # dependency-free and accepts zero-variance axes only when their
        # remaining coupled residual is also zero within numerical tolerance.
        scale = max(1.0, *(abs(value) for value in values))
        tolerance = 1e-12 * scale
        lower = [[0.0] * self.dimension for _ in range(self.dimension)]
        diagonal = [0.0] * self.dimension
        for row in range(self.dimension):
            lower[row][row] = 1.0
            for column in range(row):
                residual = values[row * self.dimension + column] - sum(
                    lower[row][index]
                    * diagonal[index]
                    * lower[column][index]
                    for index in range(column)
                )
                if abs(diagonal[column]) <= tolerance:
                    if abs(residual) > tolerance:
                        _invalid(
                            WorldModelFailureCode.MALFORMED_COVARIANCE,
                            "covariance matrix is not positive semidefinite",
                        )
                    lower[row][column] = 0.0
                else:
                    lower[row][column] = residual / diagonal[column]
            pivot = values[row * self.dimension + row] - sum(
                lower[row][index] ** 2 * diagonal[index]
                for index in range(row)
            )
            if pivot < -tolerance:
                _invalid(
                    WorldModelFailureCode.MALFORMED_COVARIANCE,
                    "covariance matrix is not positive semidefinite",
                )
            diagonal[row] = 0.0 if abs(pivot) <= tolerance else pivot
        object.__setattr__(self, "values", values)

    def document(self) -> dict[str, JSONValue]:
        return {"dimension": self.dimension, "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class Pose3D:
    frame_id: str
    child_frame_id: str
    position_xyz: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        _frame_id(self.frame_id, "pose frame_id")
        _frame_id(self.child_frame_id, "pose child_frame_id")
        if self.frame_id == self.child_frame_id:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "pose frames must be distinct",
            )
        position = _vector(self.position_xyz, "pose position", dimension=3)
        orientation = _quaternion(self.orientation_xyzw, "pose orientation")
        object.__setattr__(self, "position_xyz", position)
        object.__setattr__(self, "orientation_xyzw", orientation)

    def document(self) -> dict[str, JSONValue]:
        return {
            "child_frame_id": self.child_frame_id,
            "frame_id": self.frame_id,
            "orientation_xyzw": list(self.orientation_xyzw),
            "position_xyz": list(self.position_xyz),
        }


@dataclass(frozen=True, slots=True)
class JointObservation:
    joint_name: str
    position: float
    velocity: float | None = None
    effort: float | None = None

    def __post_init__(self) -> None:
        canonical_identifier(self.joint_name, "joint_name")
        object.__setattr__(self, "position", _finite(self.position, "joint position"))
        if self.velocity is not None:
            object.__setattr__(
                self,
                "velocity",
                _finite(self.velocity, "joint velocity"),
            )
        if self.effort is not None:
            object.__setattr__(self, "effort", _finite(self.effort, "joint effort"))

    def document(self) -> dict[str, JSONValue]:
        return {
            "effort": self.effort,
            "joint_name": self.joint_name,
            "position": self.position,
            "velocity": self.velocity,
        }


class WorldEntityKind(StrEnum):
    OBJECT = "object"
    PERSON = "person"
    SURFACE = "surface"
    LANDMARK = "landmark"
    OBSTACLE = "obstacle"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WorldEntityIdentity:
    entity_id: str
    kind: WorldEntityKind

    def __post_init__(self) -> None:
        canonical_identifier(self.entity_id, "entity_id")
        if not isinstance(self.kind, WorldEntityKind):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "entity kind must be a WorldEntityKind",
            )


class ObservationFingerprintKind(StrEnum):
    ROBOT_STATE = "robot_state"
    IMU = "imu"
    BODY_POSE = "body_pose"
    SENSOR_HEALTH = "sensor_health"
    VISUAL_FRAME = "visual_frame"
    DEPTH_FRAME = "depth_frame"
    FUSED_RGBD = "fused_rgbd"
    AUDIO_FRAME = "audio_frame"
    VISUAL_INTERPRETATION = "visual_interpretation"
    SEMANTIC_EVIDENCE = "semantic_evidence"
    ENVIRONMENT_ENTITY = "environment_entity"


@dataclass(frozen=True, slots=True)
class ObservationFingerprint:
    kind: ObservationFingerprintKind
    digest: str
    algorithm: str = "sha256"
    schema_version: int = WORLD_MODEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ObservationFingerprintKind):
            _invalid(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "observation fingerprint kind is invalid",
            )
        if self.algorithm != "sha256" or self.schema_version != WORLD_MODEL_SCHEMA_VERSION:
            _invalid(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "observation fingerprint format is unsupported",
            )
        if type(self.digest) is not str or _SHA256.fullmatch(self.digest) is None:
            _invalid(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "observation fingerprint digest is malformed",
            )

    def __str__(self) -> str:
        return f"{self.kind.value}:sha256:{self.digest}"


def _observation_document(
    *,
    kind: ObservationFingerprintKind,
    robot_id: str,
    observed_at_ns: int,
    provenance: ObservationProvenance,
    confidence: float | None,
    payload: dict[str, JSONValue],
) -> dict[str, JSONValue]:
    return {
        "confidence": confidence,
        "kind": kind.value,
        "observed_at_ns": observed_at_ns,
        "payload": payload,
        "provenance": provenance.document(),
        "robot_id": robot_id,
        "schema": "ayyo.world-model.observation.v1",
    }


@dataclass(frozen=True, slots=True, init=False)
class RobotStateObservation:
    robot_id: str
    joints: tuple[JointObservation, ...]
    base_pose: Pose3D | None
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        joints: tuple[JointObservation, ...],
        observed_at_ns: int,
        provenance: ObservationProvenance,
        confidence: float,
        base_pose: Pose3D | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(joints) is not tuple or len(joints) > MAX_OBSERVATION_ITEMS:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "robot observation joint collection is invalid or oversized",
            )
        if not joints and base_pose is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "robot observation must contain a joint or base pose",
            )
        if any(type(joint) is not JointObservation for joint in joints):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "robot observation joints must be typed JointObservation values",
            )
        canonical_joints = tuple(sorted(joints, key=lambda item: item.joint_name))
        if len({item.joint_name for item in canonical_joints}) != len(canonical_joints):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "robot observation contains duplicate joint names",
            )
        if base_pose is not None and type(base_pose) is not Pose3D:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "base_pose must be a Pose3D when provided",
            )
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "observation provenance is required",
            )
        confidence_value = _confidence(confidence)
        document = _observation_document(
            kind=ObservationFingerprintKind.ROBOT_STATE,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=confidence_value,
            payload={
                "base_pose": None if base_pose is None else base_pose.document(),
                "joints": [joint.document() for joint in canonical_joints],
            },
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.ROBOT_STATE,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "robot observation fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "robot observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "joints", canonical_joints)
        object.__setattr__(self, "base_pose", base_pose)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "confidence", confidence_value)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)


@dataclass(frozen=True, slots=True, init=False)
class ImuObservation:
    robot_id: str
    sensor: SensorIdentity
    orientation_xyzw: tuple[float, float, float, float] | None
    orientation_covariance: CovarianceMatrix | None
    angular_velocity_xyz: tuple[float, float, float] | None
    angular_velocity_covariance: CovarianceMatrix | None
    linear_acceleration_xyz: tuple[float, float, float] | None
    linear_acceleration_covariance: CovarianceMatrix | None
    observed_at_ns: int
    provenance: ObservationProvenance
    availability: SensorAvailability
    quality: float | None
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        observed_at_ns: int,
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        orientation_xyzw: tuple[float, float, float, float] | None = None,
        orientation_covariance: CovarianceMatrix | None = None,
        angular_velocity_xyz: tuple[float, float, float] | None = None,
        angular_velocity_covariance: CovarianceMatrix | None = None,
        linear_acceleration_xyz: tuple[float, float, float] | None = None,
        linear_acceleration_covariance: CovarianceMatrix | None = None,
        quality: float | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(sensor) is not SensorIdentity or sensor.kind is not SensorKind.IMU:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "IMU evidence requires a typed IMU sensor identity",
            )
        orientation = (
            None
            if orientation_xyzw is None
            else _quaternion(orientation_xyzw, "IMU orientation")
        )
        angular_velocity = (
            None
            if angular_velocity_xyz is None
            else _vector(angular_velocity_xyz, "IMU angular velocity", dimension=3)
        )
        linear_acceleration = (
            None
            if linear_acceleration_xyz is None
            else _vector(
                linear_acceleration_xyz,
                "IMU linear acceleration",
                dimension=3,
            )
        )
        covariance_pairs = (
            (orientation, orientation_covariance, "orientation"),
            (angular_velocity, angular_velocity_covariance, "angular velocity"),
            (linear_acceleration, linear_acceleration_covariance, "linear acceleration"),
        )
        for estimate, covariance, field_name in covariance_pairs:
            if covariance is not None and (
                type(covariance) is not CovarianceMatrix or covariance.dimension != 3
            ):
                _invalid(
                    WorldModelFailureCode.MALFORMED_COVARIANCE,
                    f"IMU {field_name} covariance must be a 3x3 covariance",
                )
            if covariance is not None and estimate is None:
                _invalid(
                    WorldModelFailureCode.MALFORMED_COVARIANCE,
                    f"IMU {field_name} covariance cannot exist without an estimate",
                )
        if all(value is None for value in (orientation, angular_velocity, linear_acceleration)):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "IMU evidence must contain at least one supplied estimate",
            )
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "IMU provenance is required",
            )
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "measurement-bearing IMU evidence must be available or degraded",
            )
        quality_value = None if quality is None else _confidence(quality)
        payload: dict[str, JSONValue] = {
            "angular_velocity_covariance": (
                None
                if angular_velocity_covariance is None
                else angular_velocity_covariance.document()
            ),
            "angular_velocity_xyz": (
                None if angular_velocity is None else list(angular_velocity)
            ),
            "availability": availability.value,
            "linear_acceleration_covariance": (
                None
                if linear_acceleration_covariance is None
                else linear_acceleration_covariance.document()
            ),
            "linear_acceleration_xyz": (
                None if linear_acceleration is None else list(linear_acceleration)
            ),
            "orientation_covariance": (
                None
                if orientation_covariance is None
                else orientation_covariance.document()
            ),
            "orientation_xyzw": None if orientation is None else list(orientation),
            "quality": quality_value,
            "sensor": sensor.document(),
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.IMU,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=quality_value,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.IMU,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "IMU observation fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "IMU observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "orientation_xyzw", orientation)
        object.__setattr__(self, "orientation_covariance", orientation_covariance)
        object.__setattr__(self, "angular_velocity_xyz", angular_velocity)
        object.__setattr__(self, "angular_velocity_covariance", angular_velocity_covariance)
        object.__setattr__(self, "linear_acceleration_xyz", linear_acceleration)
        object.__setattr__(self, "linear_acceleration_covariance", linear_acceleration_covariance)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "quality", quality_value)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)

    def payload_document(self) -> dict[str, JSONValue]:
        return {
            "angular_velocity_covariance": (
                None
                if self.angular_velocity_covariance is None
                else self.angular_velocity_covariance.document()
            ),
            "angular_velocity_xyz": (
                None
                if self.angular_velocity_xyz is None
                else list(self.angular_velocity_xyz)
            ),
            "availability": self.availability.value,
            "linear_acceleration_covariance": (
                None
                if self.linear_acceleration_covariance is None
                else self.linear_acceleration_covariance.document()
            ),
            "linear_acceleration_xyz": (
                None
                if self.linear_acceleration_xyz is None
                else list(self.linear_acceleration_xyz)
            ),
            "orientation_covariance": (
                None
                if self.orientation_covariance is None
                else self.orientation_covariance.document()
            ),
            "orientation_xyzw": (
                None if self.orientation_xyzw is None else list(self.orientation_xyzw)
            ),
            "quality": self.quality,
            "sensor": self.sensor.document(),
        }


@dataclass(frozen=True, slots=True, init=False)
class AudioFrameObservation:
    """Compact trusted microphone capture metadata; sample bytes are absent."""

    robot_id: str
    sensor: SensorIdentity
    producer_id: str
    source_manifest_id: str
    session_id: str
    sample_rate_hz: int
    channel_count: int
    encoding: str
    frame_count: int
    sample_count: int
    duration_ns: int
    data_size_bytes: int
    peak_amplitude: int
    rms_amplitude: float
    payload_sha256: str
    observed_at_ns: int
    result_at_ns: int
    provenance: ObservationProvenance
    availability: SensorAvailability
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        producer_id: str,
        source_manifest_id: str,
        session_id: str,
        sample_rate_hz: int,
        channel_count: int,
        encoding: str,
        frame_count: int,
        sample_count: int,
        duration_ns: int,
        data_size_bytes: int,
        peak_amplitude: int,
        rms_amplitude: float,
        payload_sha256: str,
        observed_at_ns: int,
        result_at_ns: int,
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "audio robot_id")
        if (
            type(sensor) is not SensorIdentity
            or sensor.kind is not SensorKind.MICROPHONE
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio evidence requires one typed microphone identity",
            )
        canonical_identifier(producer_id, "audio producer_id")
        if (
            type(source_manifest_id) is not str
            or _AUDIO_SOURCE_MANIFEST_ID.fullmatch(source_manifest_id) is None
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "audio source manifest identity is malformed",
            )
        if (
            type(session_id) is not str
            or _AUDIO_SESSION_ID.fullmatch(session_id) is None
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "audio lifecycle session identity is malformed",
            )
        if type(sample_rate_hz) is not int or not 8_000 <= sample_rate_hz <= 48_000:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio sample rate is outside the reviewed bound",
            )
        if channel_count != 1 or encoding != "pcm_s16le":
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio v1 requires mono signed 16-bit little-endian PCM",
            )
        if (
            type(frame_count) is not int
            or type(sample_count) is not int
            or not 1 <= frame_count <= MAX_AUDIO_FRAME_COUNT
            or sample_count != frame_count * channel_count
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio frame/sample counts are inconsistent or unbounded",
            )
        expected_duration_ns = frame_count * 1_000_000_000 // sample_rate_hz
        if (
            type(duration_ns) is not int
            or duration_ns != expected_duration_ns
            or not 0 < duration_ns <= 1_000_000_000
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio duration is inconsistent with its reviewed format",
            )
        if (
            type(data_size_bytes) is not int
            or data_size_bytes != sample_count * 2
            or not 1 <= data_size_bytes <= MAX_AUDIO_DATA_BYTES
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio byte count is inconsistent or exceeds its hard bound",
            )
        if type(peak_amplitude) is not int or not 0 <= peak_amplitude <= 32_768:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio peak amplitude is invalid",
            )
        rms = _finite(rms_amplitude, "audio RMS amplitude")
        if not 0.0 <= rms <= 1.0 or rms > peak_amplitude / 32_768.0 + 1e-12:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio RMS amplitude is outside its physical bound",
            )
        if type(payload_sha256) is not str or _SHA256.fullmatch(payload_sha256) is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio payload fingerprint is malformed",
            )
        if (
            type(observed_at_ns) is not int
            or not 1 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
            or type(result_at_ns) is not int
            or not observed_at_ns <= result_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "audio acquisition/result times are invalid",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "audio provenance is required",
            )
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "measurement-bearing audio must be available or degraded",
            )
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "channel_count": channel_count,
            "data_size_bytes": data_size_bytes,
            "duration_ns": duration_ns,
            "encoding": encoding,
            "frame_count": frame_count,
            "payload_sha256": payload_sha256,
            "peak_amplitude": peak_amplitude,
            "producer_id": producer_id,
            "result_at_ns": result_at_ns,
            "rms_amplitude": rms,
            "sample_count": sample_count,
            "sample_rate_hz": sample_rate_hz,
            "sensor": sensor.document(),
            "session_id": session_id,
            "source_manifest_id": source_manifest_id,
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.AUDIO_FRAME,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=None,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.AUDIO_FRAME,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "audio fingerprint does not match its compact metadata",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "audio observation ID does not match its compact metadata",
            )
        for field_name, value in (
            ("robot_id", robot_id),
            ("sensor", sensor),
            ("producer_id", producer_id),
            ("source_manifest_id", source_manifest_id),
            ("session_id", session_id),
            ("sample_rate_hz", sample_rate_hz),
            ("channel_count", channel_count),
            ("encoding", encoding),
            ("frame_count", frame_count),
            ("sample_count", sample_count),
            ("duration_ns", duration_ns),
            ("data_size_bytes", data_size_bytes),
            ("peak_amplitude", peak_amplitude),
            ("rms_amplitude", rms),
            ("payload_sha256", payload_sha256),
            ("observed_at_ns", observed_at_ns),
            ("result_at_ns", result_at_ns),
            ("provenance", provenance),
            ("availability", availability),
            ("observation_id", derived_id),
            ("fingerprint", derived),
        ):
            object.__setattr__(self, field_name, value)

    def payload_document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "channel_count": self.channel_count,
            "data_size_bytes": self.data_size_bytes,
            "duration_ns": self.duration_ns,
            "encoding": self.encoding,
            "frame_count": self.frame_count,
            "payload_sha256": self.payload_sha256,
            "peak_amplitude": self.peak_amplitude,
            "producer_id": self.producer_id,
            "result_at_ns": self.result_at_ns,
            "rms_amplitude": self.rms_amplitude,
            "sample_count": self.sample_count,
            "sample_rate_hz": self.sample_rate_hz,
            "sensor": self.sensor.document(),
            "session_id": self.session_id,
            "source_manifest_id": self.source_manifest_id,
        }


@dataclass(frozen=True, slots=True, init=False)
class VisualFrameObservation:
    """Compact evidence that one RGB frame was acquired; pixel bytes are absent."""

    robot_id: str
    sensor: SensorIdentity
    width: int
    height: int
    encoding: str
    step: int
    data_size_bytes: int
    is_bigendian: bool
    calibration_id: str
    observed_at_ns: int
    provenance: ObservationProvenance
    availability: SensorAvailability
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        width: int,
        height: int,
        encoding: str,
        step: int,
        data_size_bytes: int,
        is_bigendian: bool,
        calibration_id: str,
        observed_at_ns: int,
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if (
            type(sensor) is not SensorIdentity
            or sensor.kind is not SensorKind.RGB_CAMERA
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual evidence requires a typed RGB camera identity",
            )
        if (
            type(width) is not int
            or type(height) is not int
            or not 1 <= width <= MAX_CAMERA_DIMENSION
            or not 1 <= height <= MAX_CAMERA_DIMENSION
            or width * height > MAX_CAMERA_PIXELS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual frame dimensions are outside reviewed bounds",
            )
        if encoding != "rgb8":
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "v1 visual evidence accepts only the reviewed rgb8 encoding",
            )
        if (
            type(step) is not int
            or step < width * 3
            or step > MAX_IMAGE_DATA_BYTES
            or type(data_size_bytes) is not int
            or data_size_bytes != step * height
            or not 1 <= data_size_bytes <= MAX_IMAGE_DATA_BYTES
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual frame row stride or byte-count metadata is inconsistent",
            )
        if type(is_bigendian) is not bool:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual frame endian metadata must be boolean",
            )
        if type(calibration_id) is not str or _CALIBRATION_ID.fullmatch(
            calibration_id
        ) is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual frame calibration identity is malformed",
            )
        if (
            type(observed_at_ns) is not int
            or not 1 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual acquisition time must be nonzero bounded source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "visual frame provenance is required",
            )
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "measurement-bearing visual evidence must be available or degraded",
            )
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "calibration_id": calibration_id,
            "data_size_bytes": data_size_bytes,
            "encoding": encoding,
            "height": height,
            "is_bigendian": is_bigendian,
            "sensor": sensor.document(),
            "step": step,
            "width": width,
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.VISUAL_FRAME,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=None,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.VISUAL_FRAME,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "visual frame fingerprint does not match its metadata",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "visual frame observation ID does not match its metadata",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "encoding", encoding)
        object.__setattr__(self, "step", step)
        object.__setattr__(self, "data_size_bytes", data_size_bytes)
        object.__setattr__(self, "is_bigendian", is_bigendian)
        object.__setattr__(self, "calibration_id", calibration_id)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)

    def payload_document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "calibration_id": self.calibration_id,
            "data_size_bytes": self.data_size_bytes,
            "encoding": self.encoding,
            "height": self.height,
            "is_bigendian": self.is_bigendian,
            "sensor": self.sensor.document(),
            "step": self.step,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True, init=False)
class DepthFrameObservation:
    """Compact trusted depth reference; the source pixel buffer is absent."""

    robot_id: str
    sensor: SensorIdentity
    width: int
    height: int
    encoding: str
    step: int
    data_size_bytes: int
    is_bigendian: bool
    calibration_id: str
    calibration_record_id: str
    source_manifest_id: str
    session_id: str
    valid_depth_count: int
    invalid_depth_count: int
    minimum_depth_m: float
    maximum_depth_m: float
    payload_sha256: str
    observed_at_ns: int
    provenance: ObservationProvenance
    availability: SensorAvailability
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        width: int,
        height: int,
        encoding: str,
        step: int,
        data_size_bytes: int,
        is_bigendian: bool,
        calibration_id: str,
        calibration_record_id: str,
        source_manifest_id: str,
        session_id: str,
        valid_depth_count: int,
        invalid_depth_count: int,
        minimum_depth_m: float,
        maximum_depth_m: float,
        payload_sha256: str,
        observed_at_ns: int,
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if (
            type(sensor) is not SensorIdentity
            or sensor.kind is not SensorKind.DEPTH_CAMERA
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth evidence requires a typed depth camera identity",
            )
        if (
            type(width) is not int
            or type(height) is not int
            or not 1 <= width <= MAX_CAMERA_DIMENSION
            or not 1 <= height <= MAX_CAMERA_DIMENSION
            or width * height > MAX_CAMERA_PIXELS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth frame dimensions are outside reviewed bounds",
            )
        bytes_per_pixel = {"16UC1": 2, "32FC1": 4}.get(encoding)
        if bytes_per_pixel is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth encoding is outside the reviewed v1 allowlist",
            )
        if (
            type(step) is not int
            or step < width * bytes_per_pixel
            or step > MAX_IMAGE_DATA_BYTES
            or type(data_size_bytes) is not int
            or data_size_bytes != step * height
            or not 1 <= data_size_bytes <= MAX_IMAGE_DATA_BYTES
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth row stride or byte-count metadata is inconsistent",
            )
        if type(is_bigendian) is not bool:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth endian metadata must be boolean",
            )
        if type(calibration_id) is not str or _CALIBRATION_ID.fullmatch(
            calibration_id
        ) is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth calibration identity is malformed",
            )
        if (
            type(calibration_record_id) is not str
            or _DEPTH_CALIBRATION_RECORD_ID.fullmatch(calibration_record_id) is None
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth calibration record identity is malformed",
            )
        if (
            type(source_manifest_id) is not str
            or _DEPTH_SOURCE_MANIFEST_ID.fullmatch(source_manifest_id) is None
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "depth source manifest identity is malformed",
            )
        if type(session_id) is not str or _DEPTH_SESSION_ID.fullmatch(session_id) is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "depth source session identity is malformed",
            )
        pixel_count = width * height
        if (
            type(valid_depth_count) is not int
            or type(invalid_depth_count) is not int
            or not 1 <= valid_depth_count <= pixel_count
            or not 0 <= invalid_depth_count < pixel_count
            or valid_depth_count + invalid_depth_count != pixel_count
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth validity summary is inconsistent with frame geometry",
            )
        minimum = _finite(minimum_depth_m, "minimum depth")
        maximum = _finite(maximum_depth_m, "maximum depth")
        if not 0.0 < minimum <= maximum <= 10_000.0:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth range summary is invalid",
            )
        if type(payload_sha256) is not str or _SHA256.fullmatch(payload_sha256) is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth payload fingerprint is malformed",
            )
        if (
            type(observed_at_ns) is not int
            or not 1 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "depth acquisition time must be nonzero bounded source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "depth provenance is required",
            )
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "measurement-bearing depth evidence must be available or degraded",
            )
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "calibration_id": calibration_id,
            "calibration_record_id": calibration_record_id,
            "data_size_bytes": data_size_bytes,
            "encoding": encoding,
            "height": height,
            "invalid_depth_count": invalid_depth_count,
            "is_bigendian": is_bigendian,
            "maximum_depth_m": maximum,
            "minimum_depth_m": minimum,
            "payload_sha256": payload_sha256,
            "sensor": sensor.document(),
            "session_id": session_id,
            "source_manifest_id": source_manifest_id,
            "step": step,
            "valid_depth_count": valid_depth_count,
            "width": width,
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.DEPTH_FRAME,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=None,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.DEPTH_FRAME,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "depth frame fingerprint does not match its metadata",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "depth frame observation ID does not match its metadata",
            )
        for field_name, value in (
            ("robot_id", robot_id),
            ("sensor", sensor),
            ("width", width),
            ("height", height),
            ("encoding", encoding),
            ("step", step),
            ("data_size_bytes", data_size_bytes),
            ("is_bigendian", is_bigendian),
            ("calibration_id", calibration_id),
            ("calibration_record_id", calibration_record_id),
            ("source_manifest_id", source_manifest_id),
            ("session_id", session_id),
            ("valid_depth_count", valid_depth_count),
            ("invalid_depth_count", invalid_depth_count),
            ("minimum_depth_m", minimum),
            ("maximum_depth_m", maximum),
            ("payload_sha256", payload_sha256),
            ("observed_at_ns", observed_at_ns),
            ("provenance", provenance),
            ("availability", availability),
            ("observation_id", derived_id),
            ("fingerprint", derived),
        ):
            object.__setattr__(self, field_name, value)

    def payload_document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "calibration_id": self.calibration_id,
            "calibration_record_id": self.calibration_record_id,
            "data_size_bytes": self.data_size_bytes,
            "encoding": self.encoding,
            "height": self.height,
            "invalid_depth_count": self.invalid_depth_count,
            "is_bigendian": self.is_bigendian,
            "maximum_depth_m": self.maximum_depth_m,
            "minimum_depth_m": self.minimum_depth_m,
            "payload_sha256": self.payload_sha256,
            "sensor": self.sensor.document(),
            "session_id": self.session_id,
            "source_manifest_id": self.source_manifest_id,
            "step": self.step,
            "valid_depth_count": self.valid_depth_count,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True, init=False)
class FusedRgbdObservation:
    """Immutable temporal RGB-D pair; both component records remain compact."""

    robot_id: str
    sensor: SensorIdentity
    rgb_observation: VisualFrameObservation
    depth_observation: DepthFrameObservation
    rgb_producer_id: str
    depth_producer_id: str
    rgb_source_fingerprint_sha256: str
    depth_source_fingerprint_sha256: str
    rgb_session_id: str
    depth_session_id: str
    rgb_camera_frame_id: str
    depth_camera_frame_id: str
    pairing_policy_id: str
    pairing_policy_version: str
    synchronization_session_id: str
    pair_id: str
    observed_at_ns: int
    result_at_ns: int
    provenance: ObservationProvenance
    availability: SensorAvailability
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        rgb_observation: VisualFrameObservation,
        depth_observation: DepthFrameObservation,
        rgb_producer_id: str,
        depth_producer_id: str,
        rgb_source_fingerprint_sha256: str,
        depth_source_fingerprint_sha256: str,
        rgb_session_id: str,
        depth_session_id: str,
        rgb_camera_frame_id: str,
        depth_camera_frame_id: str,
        pairing_policy_id: str,
        pairing_policy_version: str,
        synchronization_session_id: str,
        result_at_ns: int,
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        pair_id: str | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "RGB-D robot_id")
        if type(sensor) is not SensorIdentity or sensor.kind is not SensorKind.RGBD_FUSION:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "fused RGB-D evidence requires one typed fusion identity",
            )
        rgb = rebuild_observation(rgb_observation)
        depth = rebuild_observation(depth_observation)
        if type(rgb) is not VisualFrameObservation or type(depth) is not DepthFrameObservation:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "fused RGB-D evidence requires compact RGB and depth observations",
            )
        if rgb.robot_id != robot_id or depth.robot_id != robot_id:
            _invalid(
                WorldModelFailureCode.WRONG_ROBOT_IDENTITY,
                "fused RGB-D components must belong to the same robot",
            )
        if rgb.observed_at_ns != depth.observed_at_ns:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "v1 fused RGB-D components require exact source acquisition time",
            )
        canonical_identifier(rgb_producer_id, "RGB-D RGB producer")
        canonical_identifier(depth_producer_id, "RGB-D depth producer")
        if (
            type(rgb_source_fingerprint_sha256) is not str
            or _SHA256.fullmatch(rgb_source_fingerprint_sha256) is None
            or type(depth_source_fingerprint_sha256) is not str
            or _SHA256.fullmatch(depth_source_fingerprint_sha256) is None
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "RGB-D source fingerprints must be canonical SHA-256 digests",
            )
        canonical_identifier(rgb_session_id, "RGB-D RGB session")
        canonical_identifier(depth_session_id, "RGB-D depth session")
        canonical_identifier(
            synchronization_session_id,
            "RGB-D synchronization session",
        )
        rgb_mount = _frame_id(rgb_camera_frame_id, "RGB camera frame")
        depth_mount = _frame_id(depth_camera_frame_id, "depth camera frame")
        if rgb_mount == rgb.sensor.frame_id or depth_mount == depth.sensor.frame_id:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "RGB-D mount and optical frame identities must remain distinct",
            )
        canonical_identifier(pairing_policy_id, "RGB-D pairing policy")
        canonical_identifier(pairing_policy_version, "RGB-D pairing policy version")
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "fused RGB-D provenance is required",
            )
        if not (
            rgb.provenance.clock
            is depth.provenance.clock
            is provenance.clock
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "RGB-D components and fusion result must share one reviewed clock",
            )
        observed_at_ns = rgb.observed_at_ns
        if (
            type(result_at_ns) is not int
            or not observed_at_ns <= result_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "RGB-D result time must not precede source acquisition",
            )
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "fused RGB-D evidence must be available or degraded",
            )
        pair_document: dict[str, JSONValue] = {
            "depth_observation_id": depth.observation_id,
            "depth_producer_id": depth_producer_id,
            "depth_session_id": depth_session_id,
            "depth_source_fingerprint_sha256": depth_source_fingerprint_sha256,
            "observed_at_ns": observed_at_ns,
            "pairing_policy_id": pairing_policy_id,
            "pairing_policy_version": pairing_policy_version,
            "rgb_observation_id": rgb.observation_id,
            "rgb_producer_id": rgb_producer_id,
            "rgb_session_id": rgb_session_id,
            "rgb_source_fingerprint_sha256": rgb_source_fingerprint_sha256,
            "schema": "ayyo.rgbd-pair.v1",
            "synchronization_session_id": synchronization_session_id,
        }
        derived_pair_id = f"rgbd-pair-sha256-{sha256_document(pair_document)}"
        if pair_id is not None and pair_id != derived_pair_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "RGB-D pair identity does not match its exact component evidence",
            )
        payload: dict[str, JSONValue] = {
            "depth_camera_frame_id": depth_mount,
            "depth_observation": {
                "fingerprint": str(depth.fingerprint),
                "observation_id": depth.observation_id,
                "payload": depth.payload_document(),
                "provenance": depth.provenance.document(),
            },
            "depth_producer_id": depth_producer_id,
            "depth_session_id": depth_session_id,
            "depth_source_fingerprint_sha256": depth_source_fingerprint_sha256,
            "pair_id": derived_pair_id,
            "pairing_policy_id": pairing_policy_id,
            "pairing_policy_version": pairing_policy_version,
            "result_at_ns": result_at_ns,
            "rgb_camera_frame_id": rgb_mount,
            "rgb_observation": {
                "fingerprint": str(rgb.fingerprint),
                "observation_id": rgb.observation_id,
                "payload": rgb.payload_document(),
                "provenance": rgb.provenance.document(),
            },
            "rgb_producer_id": rgb_producer_id,
            "rgb_session_id": rgb_session_id,
            "rgb_source_fingerprint_sha256": rgb_source_fingerprint_sha256,
            "sensor": sensor.document(),
            "spatial_registration_validated": False,
            "synchronization_session_id": synchronization_session_id,
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.FUSED_RGBD,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=None,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.FUSED_RGBD,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "fused RGB-D fingerprint does not match its metadata",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "fused RGB-D observation ID does not match its metadata",
            )
        for field_name, value in (
            ("robot_id", robot_id),
            ("sensor", sensor),
            ("rgb_observation", rgb),
            ("depth_observation", depth),
            ("rgb_producer_id", rgb_producer_id),
            ("depth_producer_id", depth_producer_id),
            ("rgb_source_fingerprint_sha256", rgb_source_fingerprint_sha256),
            ("depth_source_fingerprint_sha256", depth_source_fingerprint_sha256),
            ("rgb_session_id", rgb_session_id),
            ("depth_session_id", depth_session_id),
            ("rgb_camera_frame_id", rgb_mount),
            ("depth_camera_frame_id", depth_mount),
            ("pairing_policy_id", pairing_policy_id),
            ("pairing_policy_version", pairing_policy_version),
            ("synchronization_session_id", synchronization_session_id),
            ("pair_id", derived_pair_id),
            ("observed_at_ns", observed_at_ns),
            ("result_at_ns", result_at_ns),
            ("provenance", provenance),
            ("availability", availability),
            ("observation_id", derived_id),
            ("fingerprint", derived),
        ):
            object.__setattr__(self, field_name, value)

    def payload_document(self) -> dict[str, JSONValue]:
        return {
            "depth_camera_frame_id": self.depth_camera_frame_id,
            "depth_observation": {
                "fingerprint": str(self.depth_observation.fingerprint),
                "observation_id": self.depth_observation.observation_id,
                "payload": self.depth_observation.payload_document(),
                "provenance": self.depth_observation.provenance.document(),
            },
            "depth_producer_id": self.depth_producer_id,
            "depth_session_id": self.depth_session_id,
            "depth_source_fingerprint_sha256": self.depth_source_fingerprint_sha256,
            "pair_id": self.pair_id,
            "pairing_policy_id": self.pairing_policy_id,
            "pairing_policy_version": self.pairing_policy_version,
            "result_at_ns": self.result_at_ns,
            "rgb_camera_frame_id": self.rgb_camera_frame_id,
            "rgb_observation": {
                "fingerprint": str(self.rgb_observation.fingerprint),
                "observation_id": self.rgb_observation.observation_id,
                "payload": self.rgb_observation.payload_document(),
                "provenance": self.rgb_observation.provenance.document(),
            },
            "rgb_producer_id": self.rgb_producer_id,
            "rgb_session_id": self.rgb_session_id,
            "rgb_source_fingerprint_sha256": self.rgb_source_fingerprint_sha256,
            "sensor": self.sensor.document(),
            "spatial_registration_validated": False,
            "synchronization_session_id": self.synchronization_session_id,
        }


@dataclass(frozen=True, slots=True, init=False)
class VisualInterpretationObservation:
    """Bounded semantic evidence derived from one exact admitted visual frame."""

    robot_id: str
    sensor: SensorIdentity
    reference_frame_id: str
    source_visual_observation_id: str
    source_visual_fingerprint: ObservationFingerprint
    observed_at_ns: int
    result_at_ns: int
    producer: VisualInterpretationProducer
    evaluation_reference: VisualEvaluationReference | None
    detections: tuple[VisualDetection, ...]
    provenance: ObservationProvenance
    availability: SensorAvailability
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        reference_frame_id: str,
        source_visual_observation_id: str,
        source_visual_fingerprint: ObservationFingerprint,
        observed_at_ns: int,
        result_at_ns: int,
        producer: VisualInterpretationProducer,
        detections: tuple[VisualDetection, ...],
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        evaluation_reference: VisualEvaluationReference | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if (
            type(sensor) is not SensorIdentity
            or sensor.kind is not SensorKind.RGB_CAMERA
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual interpretation requires a typed RGB camera identity",
            )
        frame = _frame_id(reference_frame_id, "visual interpretation frame")
        if frame != sensor.frame_id:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual interpretation frame must match its camera optical frame",
            )
        if (
            type(source_visual_observation_id) is not str
            or _OBSERVATION_ID.fullmatch(source_visual_observation_id) is None
            or type(source_visual_fingerprint) is not ObservationFingerprint
            or source_visual_fingerprint.kind
            is not ObservationFingerprintKind.VISUAL_FRAME
            or source_visual_observation_id
            != f"world-observation-{source_visual_fingerprint.digest}"
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual interpretation source-frame identity is inconsistent",
            )
        if (
            type(observed_at_ns) is not int
            or type(result_at_ns) is not int
            or not 0 <= observed_at_ns <= result_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual source/result timestamps are malformed or reversed",
            )
        if type(producer) is not VisualInterpretationProducer:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual interpretation producer must be typed",
            )
        if evaluation_reference is not None:
            if type(evaluation_reference) is not VisualEvaluationReference:
                _invalid(
                    WorldModelFailureCode.MALFORMED_OBSERVATION,
                    "visual evaluation reference must be typed",
                )
            if (
                evaluation_reference.model.producer_id != producer.producer_id
                or evaluation_reference.model.model_id != producer.model_id
            ):
                _invalid(
                    WorldModelFailureCode.MALFORMED_OBSERVATION,
                    "visual producer and evaluated model provenance disagree",
                )
        if (
            type(detections) is not tuple
            or len(detections) > MAX_VISUAL_DETECTIONS
            or any(type(item) is not VisualDetection for item in detections)
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual interpretation detections are invalid or oversized",
            )
        canonical_detections = tuple(
            sorted(detections, key=lambda item: item.detection_id)
        )
        detection_ids = tuple(item.detection_id for item in canonical_detections)
        if (
            len(detection_ids) != len(set(detection_ids))
            or any(
                item.source_visual_observation_id
                != source_visual_observation_id
                for item in canonical_detections
            )
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual detections must be unique and reference the same source frame",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "visual interpretation source provenance is required",
            )
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "visual interpretation must be available or degraded",
            )
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "detections": [item.document() for item in canonical_detections],
            "producer": producer.document(),
            "reference_frame_id": frame,
            "result_at_ns": result_at_ns,
            "sensor": sensor.document(),
            "source_visual_fingerprint": str(source_visual_fingerprint),
            "source_visual_observation_id": source_visual_observation_id,
        }
        if evaluation_reference is not None:
            payload["evaluation_reference"] = evaluation_reference.document()
        document = _observation_document(
            kind=ObservationFingerprintKind.VISUAL_INTERPRETATION,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=None,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.VISUAL_INTERPRETATION,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "visual interpretation fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "visual interpretation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "reference_frame_id", frame)
        object.__setattr__(
            self,
            "source_visual_observation_id",
            source_visual_observation_id,
        )
        object.__setattr__(
            self,
            "source_visual_fingerprint",
            source_visual_fingerprint,
        )
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "result_at_ns", result_at_ns)
        object.__setattr__(self, "producer", producer)
        object.__setattr__(self, "evaluation_reference", evaluation_reference)
        object.__setattr__(self, "detections", canonical_detections)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)

    def payload_document(self) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "availability": self.availability.value,
            "detections": [item.document() for item in self.detections],
            "producer": self.producer.document(),
            "reference_frame_id": self.reference_frame_id,
            "result_at_ns": self.result_at_ns,
            "sensor": self.sensor.document(),
            "source_visual_fingerprint": str(self.source_visual_fingerprint),
            "source_visual_observation_id": self.source_visual_observation_id,
        }
        if self.evaluation_reference is not None:
            payload["evaluation_reference"] = self.evaluation_reference.document()
        return payload


def _semantic_source_observation_id(
    *,
    item: SemanticEvidenceItem,
    robot_id: str,
    sensor: SensorIdentity,
    reference_frame_id: str,
    source_visual_observation_id: str,
    source_interpretation_observation_id: str,
    observed_at_ns: int,
    result_at_ns: int,
    provenance: ObservationProvenance,
) -> str:
    document: dict[str, JSONValue] = {
        "confidence": item.confidence,
        "kind": item.kind.value,
        "observed_at_ns": observed_at_ns,
        "provenance": provenance.document(),
        "reference_frame_id": reference_frame_id,
        "region": item.region.document(),
        "result_at_ns": result_at_ns,
        "robot_id": robot_id,
        "schema": f"ayyo.{item.kind.value}-observation.v1",
        "sensor": sensor.document(),
        "source_detection": {
            "visual_detection_id": item.source_detection_id,
            "visual_interpretation_observation_id": (
                source_interpretation_observation_id
            ),
        },
        "source_visual_observation_id": source_visual_observation_id,
    }
    if item.kind is SemanticEvidenceKind.OBJECT:
        document["category"] = item.category
    return (
        f"{item.kind.value}-observation-sha256-"
        f"{sha256_document(document)}"
    )


@dataclass(frozen=True, slots=True, init=False)
class SemanticEvidenceObservation:
    """A conservative non-empty set of anonymous facts from one interpretation."""

    robot_id: str
    sensor: SensorIdentity
    reference_frame_id: str
    source_visual_observation_id: str
    source_visual_fingerprint: ObservationFingerprint
    source_interpretation_observation_id: str
    source_interpretation_fingerprint: ObservationFingerprint
    observed_at_ns: int
    result_at_ns: int
    producer: VisualInterpretationProducer
    evaluation_reference_sha256: str | None
    items: tuple[SemanticEvidenceItem, ...]
    provenance: ObservationProvenance
    availability: SensorAvailability
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        reference_frame_id: str,
        source_visual_observation_id: str,
        source_visual_fingerprint: ObservationFingerprint,
        source_interpretation_observation_id: str,
        source_interpretation_fingerprint: ObservationFingerprint,
        observed_at_ns: int,
        result_at_ns: int,
        producer: VisualInterpretationProducer,
        evaluation_reference_sha256: str | None,
        items: tuple[SemanticEvidenceItem, ...],
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if (
            type(sensor) is not SensorIdentity
            or sensor.kind is not SensorKind.RGB_CAMERA
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence requires a typed RGB camera identity",
            )
        frame = _frame_id(reference_frame_id, "semantic evidence frame")
        if frame != sensor.frame_id:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence frame must match its camera optical frame",
            )
        if (
            type(source_visual_observation_id) is not str
            or _OBSERVATION_ID.fullmatch(source_visual_observation_id) is None
            or type(source_visual_fingerprint) is not ObservationFingerprint
            or source_visual_fingerprint.kind
            is not ObservationFingerprintKind.VISUAL_FRAME
            or source_visual_observation_id
            != f"world-observation-{source_visual_fingerprint.digest}"
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence source-frame identity is inconsistent",
            )
        if (
            type(source_interpretation_observation_id) is not str
            or _OBSERVATION_ID.fullmatch(source_interpretation_observation_id)
            is None
            or type(source_interpretation_fingerprint)
            is not ObservationFingerprint
            or source_interpretation_fingerprint.kind
            is not ObservationFingerprintKind.VISUAL_INTERPRETATION
            or source_interpretation_observation_id
            != f"world-observation-{source_interpretation_fingerprint.digest}"
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence source-interpretation identity is inconsistent",
            )
        if (
            type(observed_at_ns) is not int
            or type(result_at_ns) is not int
            or not 0 <= observed_at_ns <= result_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic source/result timestamps are malformed or reversed",
            )
        if type(producer) is not VisualInterpretationProducer:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence producer must be typed",
            )
        evaluation_digest = (
            None
            if evaluation_reference_sha256 is None
            else _sha256_digest(
                evaluation_reference_sha256,
                "semantic evaluation reference",
            )
        )
        if (
            type(items) is not tuple
            or not items
            or len(items) > MAX_SEMANTIC_EVIDENCE_ITEMS
            or any(type(item) is not SemanticEvidenceItem for item in items)
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence items must be a non-empty bounded typed tuple",
            )
        canonical_items = tuple(
            sorted(
                items,
                key=lambda item: (
                    item.source_detection_id,
                    item.source_semantic_observation_id,
                ),
            )
        )
        semantic_ids = tuple(
            item.source_semantic_observation_id for item in canonical_items
        )
        detection_ids = tuple(
            item.source_detection_id for item in canonical_items
        )
        if (
            len(semantic_ids) != len(set(semantic_ids))
            or len(detection_ids) != len(set(detection_ids))
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence sources must be unique within one interpretation",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "semantic evidence provenance is required",
            )
        for item in canonical_items:
            expected_source_id = _semantic_source_observation_id(
                item=item,
                robot_id=robot_id,
                sensor=sensor,
                reference_frame_id=frame,
                source_visual_observation_id=source_visual_observation_id,
                source_interpretation_observation_id=(
                    source_interpretation_observation_id
                ),
                observed_at_ns=observed_at_ns,
                result_at_ns=result_at_ns,
                provenance=provenance,
            )
            if item.source_semantic_observation_id != expected_source_id:
                raise ObservationIdentityError(
                    WorldModelFailureCode.IDENTITY_MISMATCH,
                    "semantic source-observation identity does not match projected content",
                )
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "semantic evidence must be available or degraded",
            )
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "evaluation_reference_sha256": evaluation_digest,
            "items": [item.document() for item in canonical_items],
            "producer": producer.document(),
            "reference_frame_id": frame,
            "result_at_ns": result_at_ns,
            "sensor": sensor.document(),
            "source_interpretation_fingerprint": str(
                source_interpretation_fingerprint
            ),
            "source_interpretation_observation_id": (
                source_interpretation_observation_id
            ),
            "source_visual_fingerprint": str(source_visual_fingerprint),
            "source_visual_observation_id": source_visual_observation_id,
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.SEMANTIC_EVIDENCE,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=None,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.SEMANTIC_EVIDENCE,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "semantic evidence fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "semantic evidence observation ID does not match its content",
            )
        for field_name, value in (
            ("robot_id", robot_id),
            ("sensor", sensor),
            ("reference_frame_id", frame),
            ("source_visual_observation_id", source_visual_observation_id),
            ("source_visual_fingerprint", source_visual_fingerprint),
            (
                "source_interpretation_observation_id",
                source_interpretation_observation_id,
            ),
            (
                "source_interpretation_fingerprint",
                source_interpretation_fingerprint,
            ),
            ("observed_at_ns", observed_at_ns),
            ("result_at_ns", result_at_ns),
            ("producer", producer),
            ("evaluation_reference_sha256", evaluation_digest),
            ("items", canonical_items),
            ("provenance", provenance),
            ("availability", availability),
            ("observation_id", derived_id),
            ("fingerprint", derived),
        ):
            object.__setattr__(self, field_name, value)

    def payload_document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "evaluation_reference_sha256": self.evaluation_reference_sha256,
            "items": [item.document() for item in self.items],
            "producer": self.producer.document(),
            "reference_frame_id": self.reference_frame_id,
            "result_at_ns": self.result_at_ns,
            "sensor": self.sensor.document(),
            "source_interpretation_fingerprint": str(
                self.source_interpretation_fingerprint
            ),
            "source_interpretation_observation_id": (
                self.source_interpretation_observation_id
            ),
            "source_visual_fingerprint": str(self.source_visual_fingerprint),
            "source_visual_observation_id": self.source_visual_observation_id,
        }


@dataclass(frozen=True, slots=True, init=False)
class BodyPoseObservation:
    robot_id: str
    sensor: SensorIdentity
    pose: Pose3D
    covariance: CovarianceMatrix | None
    observed_at_ns: int
    provenance: ObservationProvenance
    availability: SensorAvailability
    quality: float | None
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        pose: Pose3D,
        observed_at_ns: int,
        provenance: ObservationProvenance,
        availability: SensorAvailability,
        covariance: CovarianceMatrix | None = None,
        quality: float | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(sensor) is not SensorIdentity or sensor.kind is not SensorKind.BODY_POSE:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "body-pose evidence requires a typed body-pose source identity",
            )
        if type(pose) is not Pose3D or pose.child_frame_id != sensor.frame_id:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "body-pose target frame must match its reviewed sensor contract",
            )
        if covariance is not None and (
            type(covariance) is not CovarianceMatrix or covariance.dimension != 6
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_COVARIANCE,
                "body pose covariance must be a 6x6 covariance",
            )
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.MALFORMED_PROVENANCE, "pose provenance is required")
        if availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "measurement-bearing pose evidence must be available or degraded",
            )
        quality_value = None if quality is None else _confidence(quality)
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "covariance": None if covariance is None else covariance.document(),
            "pose": pose.document(),
            "quality": quality_value,
            "sensor": sensor.document(),
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.BODY_POSE,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=quality_value,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.BODY_POSE,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "body-pose fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "body-pose observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "pose", pose)
        object.__setattr__(self, "covariance", covariance)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "quality", quality_value)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)


@dataclass(frozen=True, slots=True, init=False)
class SensorHealthObservation:
    robot_id: str
    sensor: SensorIdentity
    availability: SensorAvailability
    observed_at_ns: int
    provenance: ObservationProvenance
    evidence_detail: str
    observation_id: str
    fingerprint: ObservationFingerprint

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        availability: SensorAvailability,
        observed_at_ns: int,
        provenance: ObservationProvenance,
        evidence_detail: str = "",
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(sensor) is not SensorIdentity:
            _invalid(WorldModelFailureCode.MALFORMED_OBSERVATION, "sensor identity is required")
        if not isinstance(availability, SensorAvailability):
            _invalid(WorldModelFailureCode.MALFORMED_OBSERVATION, "sensor availability is invalid")
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.MALFORMED_PROVENANCE, "health provenance is required")
        if (
            type(evidence_detail) is not str
            or len(evidence_detail) > 1_024
            or "\x00" in evidence_detail
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "sensor health detail must be bounded text",
            )
        payload: dict[str, JSONValue] = {
            "availability": availability.value,
            "evidence_detail": evidence_detail,
            "sensor": sensor.document(),
        }
        document = _observation_document(
            kind=ObservationFingerprintKind.SENSOR_HEALTH,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=None,
            payload=payload,
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.SENSOR_HEALTH,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "health fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "health observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "evidence_detail", evidence_detail)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)


@dataclass(frozen=True, slots=True, init=False)
class EnvironmentEntityObservation:
    robot_id: str
    entity: WorldEntityIdentity
    pose: Pose3D | None
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float
    observation_id: str
    fingerprint: ObservationFingerprint
    _properties: JSONValue = field(repr=False, compare=False)
    _canonical_properties: str = field(repr=False)

    def __init__(
        self,
        *,
        robot_id: str,
        entity: WorldEntityIdentity,
        properties: Mapping[str, JSONValue],
        observed_at_ns: int,
        provenance: ObservationProvenance,
        confidence: float,
        pose: Pose3D | None = None,
        observation_id: str | None = None,
        fingerprint: ObservationFingerprint | None = None,
    ) -> None:
        canonical_identifier(robot_id, "robot_id")
        if type(entity) is not WorldEntityIdentity:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "environment observation entity must be typed",
            )
        if pose is not None and type(pose) is not Pose3D:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "environment pose must be a Pose3D when provided",
            )
        copied = copy_mapping(properties, field_name="environment properties")
        if not copied and pose is None:
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "environment observation must contain bounded evidence",
            )
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(
                WorldModelFailureCode.MALFORMED_OBSERVATION,
                "observed_at_ns must be non-negative integer source time",
            )
        if type(provenance) is not ObservationProvenance:
            _invalid(
                WorldModelFailureCode.MALFORMED_PROVENANCE,
                "observation provenance is required",
            )
        confidence_value = _confidence(confidence)
        document = _observation_document(
            kind=ObservationFingerprintKind.ENVIRONMENT_ENTITY,
            robot_id=robot_id,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            confidence=confidence_value,
            payload={
                "entity_id": entity.entity_id,
                "entity_kind": entity.kind.value,
                "pose": None if pose is None else pose.document(),
                "properties": copied,
            },
        )
        derived = ObservationFingerprint(
            kind=ObservationFingerprintKind.ENVIRONMENT_ENTITY,
            digest=sha256_document(document),
        )
        derived_id = f"world-observation-{derived.digest}"
        if fingerprint is not None and fingerprint != derived:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "environment observation fingerprint does not match its content",
            )
        if observation_id is not None and observation_id != derived_id:
            raise ObservationIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "environment observation ID does not match its content",
            )
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "entity", entity)
        object.__setattr__(self, "pose", pose)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "confidence", confidence_value)
        object.__setattr__(self, "observation_id", derived_id)
        object.__setattr__(self, "fingerprint", derived)
        object.__setattr__(self, "_properties", copied)
        object.__setattr__(self, "_canonical_properties", sha256_document(copied))

    @property
    def properties(self) -> dict[str, JSONValue]:
        copied = copy_json(self._properties, field_name="environment properties")
        assert type(copied) is dict
        return copied


Observation: TypeAlias = (
    RobotStateObservation
    | ImuObservation
    | AudioFrameObservation
    | VisualFrameObservation
    | DepthFrameObservation
    | FusedRgbdObservation
    | VisualInterpretationObservation
    | SemanticEvidenceObservation
    | BodyPoseObservation
    | SensorHealthObservation
    | EnvironmentEntityObservation
)


def rebuild_observation(observation: Observation) -> Observation:
    if type(observation) is RobotStateObservation:
        return RobotStateObservation(
            robot_id=observation.robot_id,
            joints=observation.joints,
            base_pose=observation.base_pose,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            confidence=observation.confidence,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is EnvironmentEntityObservation:
        return EnvironmentEntityObservation(
            robot_id=observation.robot_id,
            entity=observation.entity,
            pose=observation.pose,
            properties=observation.properties,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            confidence=observation.confidence,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is ImuObservation:
        return ImuObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            orientation_xyzw=observation.orientation_xyzw,
            orientation_covariance=observation.orientation_covariance,
            angular_velocity_xyz=observation.angular_velocity_xyz,
            angular_velocity_covariance=observation.angular_velocity_covariance,
            linear_acceleration_xyz=observation.linear_acceleration_xyz,
            linear_acceleration_covariance=observation.linear_acceleration_covariance,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            quality=observation.quality,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is AudioFrameObservation:
        return AudioFrameObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            producer_id=observation.producer_id,
            source_manifest_id=observation.source_manifest_id,
            session_id=observation.session_id,
            sample_rate_hz=observation.sample_rate_hz,
            channel_count=observation.channel_count,
            encoding=observation.encoding,
            frame_count=observation.frame_count,
            sample_count=observation.sample_count,
            duration_ns=observation.duration_ns,
            data_size_bytes=observation.data_size_bytes,
            peak_amplitude=observation.peak_amplitude,
            rms_amplitude=observation.rms_amplitude,
            payload_sha256=observation.payload_sha256,
            observed_at_ns=observation.observed_at_ns,
            result_at_ns=observation.result_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is VisualFrameObservation:
        return VisualFrameObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            width=observation.width,
            height=observation.height,
            encoding=observation.encoding,
            step=observation.step,
            data_size_bytes=observation.data_size_bytes,
            is_bigendian=observation.is_bigendian,
            calibration_id=observation.calibration_id,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is DepthFrameObservation:
        return DepthFrameObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            width=observation.width,
            height=observation.height,
            encoding=observation.encoding,
            step=observation.step,
            data_size_bytes=observation.data_size_bytes,
            is_bigendian=observation.is_bigendian,
            calibration_id=observation.calibration_id,
            calibration_record_id=observation.calibration_record_id,
            source_manifest_id=observation.source_manifest_id,
            session_id=observation.session_id,
            valid_depth_count=observation.valid_depth_count,
            invalid_depth_count=observation.invalid_depth_count,
            minimum_depth_m=observation.minimum_depth_m,
            maximum_depth_m=observation.maximum_depth_m,
            payload_sha256=observation.payload_sha256,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is FusedRgbdObservation:
        return FusedRgbdObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            rgb_observation=observation.rgb_observation,
            depth_observation=observation.depth_observation,
            rgb_producer_id=observation.rgb_producer_id,
            depth_producer_id=observation.depth_producer_id,
            rgb_source_fingerprint_sha256=(
                observation.rgb_source_fingerprint_sha256
            ),
            depth_source_fingerprint_sha256=(
                observation.depth_source_fingerprint_sha256
            ),
            rgb_session_id=observation.rgb_session_id,
            depth_session_id=observation.depth_session_id,
            rgb_camera_frame_id=observation.rgb_camera_frame_id,
            depth_camera_frame_id=observation.depth_camera_frame_id,
            pairing_policy_id=observation.pairing_policy_id,
            pairing_policy_version=observation.pairing_policy_version,
            synchronization_session_id=observation.synchronization_session_id,
            result_at_ns=observation.result_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            pair_id=observation.pair_id,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is VisualInterpretationObservation:
        return VisualInterpretationObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            reference_frame_id=observation.reference_frame_id,
            source_visual_observation_id=(
                observation.source_visual_observation_id
            ),
            source_visual_fingerprint=observation.source_visual_fingerprint,
            observed_at_ns=observation.observed_at_ns,
            result_at_ns=observation.result_at_ns,
            producer=observation.producer,
            detections=observation.detections,
            provenance=observation.provenance,
            availability=observation.availability,
            evaluation_reference=observation.evaluation_reference,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is SemanticEvidenceObservation:
        return SemanticEvidenceObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            reference_frame_id=observation.reference_frame_id,
            source_visual_observation_id=(
                observation.source_visual_observation_id
            ),
            source_visual_fingerprint=observation.source_visual_fingerprint,
            source_interpretation_observation_id=(
                observation.source_interpretation_observation_id
            ),
            source_interpretation_fingerprint=(
                observation.source_interpretation_fingerprint
            ),
            observed_at_ns=observation.observed_at_ns,
            result_at_ns=observation.result_at_ns,
            producer=observation.producer,
            evaluation_reference_sha256=(
                observation.evaluation_reference_sha256
            ),
            items=observation.items,
            provenance=observation.provenance,
            availability=observation.availability,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is BodyPoseObservation:
        return BodyPoseObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            pose=observation.pose,
            covariance=observation.covariance,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            availability=observation.availability,
            quality=observation.quality,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    if type(observation) is SensorHealthObservation:
        return SensorHealthObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            availability=observation.availability,
            observed_at_ns=observation.observed_at_ns,
            provenance=observation.provenance,
            evidence_detail=observation.evidence_detail,
            observation_id=observation.observation_id,
            fingerprint=observation.fingerprint,
        )
    _invalid(
        WorldModelFailureCode.MALFORMED_OBSERVATION,
        "observation has an unsupported concrete type",
    )


class FreshnessState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"


class RobotAvailability(StrEnum):
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    AVAILABLE = "available"


@dataclass(frozen=True, slots=True)
class ObservedJointState:
    joint: JointObservation
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float
    freshness: FreshnessState
    observation_id: str
    observation_fingerprint: ObservationFingerprint

    def __post_init__(self) -> None:
        if type(self.joint) is not JointObservation:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint state is untyped")
        if (
            type(self.observed_at_ns) is not int
            or not 0 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint time is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint provenance is invalid")
        _confidence(self.confidence)
        if not isinstance(self.freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint freshness is invalid")
        if not self.observation_id.startswith("world-observation-"):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "joint evidence ID is invalid")
        if type(self.observation_fingerprint) is not ObservationFingerprint:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "joint evidence fingerprint is invalid",
            )
        if self.observation_id.removeprefix("world-observation-") != (
            self.observation_fingerprint.digest
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "joint evidence ID and fingerprint disagree",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "confidence": self.confidence,
            "freshness": self.freshness.value,
            "joint": self.joint.document(),
            "observation_fingerprint": str(self.observation_fingerprint),
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "provenance": self.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedPoseState:
    pose: Pose3D
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float | None
    freshness: FreshnessState
    observation_id: str
    sensor: SensorIdentity | None = None
    covariance: CovarianceMatrix | None = None
    availability: SensorAvailability = SensorAvailability.AVAILABLE
    observation_fingerprint: ObservationFingerprint | None = None

    def __post_init__(self) -> None:
        if type(self.pose) is not Pose3D:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose state is untyped")
        if (
            type(self.observed_at_ns) is not int
            or not 0 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose time is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose provenance is invalid")
        if self.confidence is not None:
            _confidence(self.confidence)
        if not isinstance(self.freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose freshness is invalid")
        if (
            type(self.observation_id) is not str
            or re.fullmatch(r"world-observation-[0-9a-f]{64}", self.observation_id)
            is None
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose evidence ID is invalid")
        if self.sensor is not None and (
            type(self.sensor) is not SensorIdentity
            or self.sensor.kind is not SensorKind.BODY_POSE
            or self.pose.child_frame_id != self.sensor.frame_id
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose sensor is invalid")
        if self.covariance is not None and (
            type(self.covariance) is not CovarianceMatrix
            or self.covariance.dimension != 6
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose covariance is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose availability is invalid")
        if self.observation_fingerprint is not None:
            if type(self.observation_fingerprint) is not ObservationFingerprint:
                _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "pose fingerprint is invalid")
            if self.observation_id.removeprefix("world-observation-") != (
                self.observation_fingerprint.digest
            ):
                _invalid(
                    WorldModelFailureCode.SNAPSHOT_INVARIANT,
                    "pose evidence ID and fingerprint disagree",
                )

    def document(self) -> dict[str, JSONValue]:
        return {
            "confidence": self.confidence,
            "freshness": self.freshness.value,
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "pose": self.pose.document(),
            "provenance": self.provenance.document(),
            "sensor": None if self.sensor is None else self.sensor.document(),
            "covariance": (
                None if self.covariance is None else self.covariance.document()
            ),
            "availability": self.availability.value,
            "observation_fingerprint": (
                None
                if self.observation_fingerprint is None
                else str(self.observation_fingerprint)
            ),
        }


@dataclass(frozen=True, slots=True)
class ObservedImuState:
    observation: ImuObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not ImuObservation:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU state is untyped")
        if not isinstance(self.freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU freshness is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU availability is invalid")
        if self.freshness is FreshnessState.STALE and (
            self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale IMU evidence must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "payload": self.observation.payload_document(),
            "provenance": self.observation.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedAudioState:
    observation: AudioFrameObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not AudioFrameObservation:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "audio state is untyped",
            )
        if not isinstance(self.freshness, FreshnessState):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "audio freshness is invalid",
            )
        if not isinstance(self.availability, SensorAvailability):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "audio availability is invalid",
            )
        if (
            self.freshness is FreshnessState.STALE
            and self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale audio evidence must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "payload": self.observation.payload_document(),
            "provenance": self.observation.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedDepthState:
    observation: DepthFrameObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not DepthFrameObservation:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "depth state is untyped",
            )
        if not isinstance(self.freshness, FreshnessState):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "depth freshness is invalid",
            )
        if not isinstance(self.availability, SensorAvailability):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "depth availability is invalid",
            )
        if (
            self.freshness is FreshnessState.STALE
            and self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale depth evidence must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "payload": self.observation.payload_document(),
            "provenance": self.observation.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedFusedRgbdState:
    observation: FusedRgbdObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not FusedRgbdObservation:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "fused RGB-D state is untyped",
            )
        if not isinstance(self.freshness, FreshnessState):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "fused RGB-D freshness is invalid",
            )
        if not isinstance(self.availability, SensorAvailability):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "fused RGB-D availability is invalid",
            )
        if (
            self.freshness is FreshnessState.STALE
            and self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale fused RGB-D evidence must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "payload": self.observation.payload_document(),
            "provenance": self.observation.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedVisualState:
    observation: VisualFrameObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not VisualFrameObservation:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual state is untyped",
            )
        if not isinstance(self.freshness, FreshnessState):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual freshness is invalid",
            )
        if not isinstance(self.availability, SensorAvailability):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual availability is invalid",
            )
        if self.freshness is FreshnessState.STALE and (
            self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale visual evidence must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "payload": self.observation.payload_document(),
            "provenance": self.observation.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedVisualInterpretationState:
    observation: VisualInterpretationObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not VisualInterpretationObservation:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual interpretation state is untyped",
            )
        if not isinstance(self.freshness, FreshnessState):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual interpretation freshness is invalid",
            )
        if not isinstance(self.availability, SensorAvailability):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual interpretation availability is invalid",
            )
        if (
            self.freshness is FreshnessState.STALE
            and self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale visual interpretation must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "payload": self.observation.payload_document(),
            "provenance": self.observation.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedSemanticEvidenceState:
    """Freshness-qualified anonymous semantic evidence from one interpretation."""

    observation: SemanticEvidenceObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not SemanticEvidenceObservation:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "semantic evidence state is untyped",
            )
        if not isinstance(self.freshness, FreshnessState):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "semantic evidence freshness is invalid",
            )
        if not isinstance(self.availability, SensorAvailability):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "semantic evidence availability is invalid",
            )
        if (
            self.freshness is FreshnessState.STALE
            and self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale semantic evidence must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "payload": self.observation.payload_document(),
            "provenance": self.observation.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class ObservedSensorHealthState:
    observation: SensorHealthObservation
    freshness: FreshnessState
    availability: SensorAvailability

    def __post_init__(self) -> None:
        if type(self.observation) is not SensorHealthObservation:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor health state is untyped")
        if not isinstance(self.freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor health freshness is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor health availability is invalid")
        if self.freshness is FreshnessState.STALE and (
            self.availability is not SensorAvailability.STALE
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "stale sensor health evidence must be explicitly marked stale",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "evidence_detail": self.observation.evidence_detail,
            "fingerprint": str(self.observation.fingerprint),
            "freshness": self.freshness.value,
            "observation_id": self.observation.observation_id,
            "observed_at_ns": self.observation.observed_at_ns,
            "provenance": self.observation.provenance.document(),
            "sensor": self.observation.sensor.document(),
        }


@dataclass(frozen=True, slots=True)
class SensorAvailabilityState:
    sensor: SensorIdentity
    availability: SensorAvailability
    observed_at_ns: int | None
    provenance: ObservationProvenance | None
    observation_id: str | None

    def __post_init__(self) -> None:
        if type(self.sensor) is not SensorIdentity:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor state identity is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor state is invalid")
        evidence = (self.observed_at_ns, self.provenance, self.observation_id)
        if self.availability is SensorAvailability.UNAVAILABLE and all(
            item is None for item in evidence
        ):
            return
        if any(item is None for item in evidence):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "evidence-backed sensor state requires complete provenance",
            )
        if type(self.observed_at_ns) is not int or not 0 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor state time is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor state provenance is invalid")
        if (
            type(self.observation_id) is not str
            or re.fullmatch(r"world-observation-[0-9a-f]{64}", self.observation_id)
            is None
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor evidence ID is invalid")

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "provenance": None if self.provenance is None else self.provenance.document(),
            "sensor": self.sensor.document(),
        }


@dataclass(frozen=True, slots=True)
class RobotBodyState:
    robot_id: str
    known_joint_names: tuple[str, ...]
    joints: tuple[ObservedJointState, ...]
    base_pose: ObservedPoseState | None
    availability: RobotAvailability
    imu_states: tuple[ObservedImuState, ...] = ()
    audio_states: tuple[ObservedAudioState, ...] = ()
    depth_states: tuple[ObservedDepthState, ...] = ()
    fused_rgbd_states: tuple[ObservedFusedRgbdState, ...] = ()
    visual_states: tuple[ObservedVisualState, ...] = ()
    visual_interpretation_states: tuple[
        ObservedVisualInterpretationState, ...
    ] = ()
    sensor_states: tuple[SensorAvailabilityState, ...] = ()
    sensor_health_states: tuple[ObservedSensorHealthState, ...] = ()

    def __post_init__(self) -> None:
        canonical_identifier(self.robot_id, "robot body identity")
        expected = tuple(sorted(set(self.known_joint_names)))
        if self.known_joint_names != expected:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "known joints must be unique and sorted",
            )
        for joint_name in self.known_joint_names:
            canonical_identifier(joint_name, "known joint name")
        if any(type(item) is not ObservedJointState for item in self.joints):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "robot joints must be ObservedJointState values",
            )
        if self.base_pose is not None and type(self.base_pose) is not ObservedPoseState:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "robot base pose must be an ObservedPoseState",
            )
        actual = tuple(item.joint.joint_name for item in self.joints)
        if actual != tuple(sorted(set(actual))) or not set(actual) <= set(expected):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "observed joints must be unique, sorted, and known",
            )
        expected_availability = (
            RobotAvailability.UNAVAILABLE
            if not actual
            else RobotAvailability.AVAILABLE
            if len(actual) == len(expected)
            else RobotAvailability.PARTIAL
        )
        if self.availability is not expected_availability:
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "body availability does not match observed joint coverage",
            )
        if any(type(item) is not ObservedImuState for item in self.imu_states):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU states must be typed")
        imu_ids = tuple(item.observation.sensor.sensor_id for item in self.imu_states)
        if imu_ids != tuple(sorted(set(imu_ids))):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "IMU states must be unique and sorted")
        if any(type(item) is not ObservedAudioState for item in self.audio_states):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "audio states must be typed",
            )
        audio_ids = tuple(
            item.observation.sensor.sensor_id for item in self.audio_states
        )
        if audio_ids != tuple(sorted(set(audio_ids))):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "audio states must be unique and sorted",
            )
        if any(type(item) is not ObservedDepthState for item in self.depth_states):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "depth states must be typed",
            )
        depth_ids = tuple(
            item.observation.sensor.sensor_id for item in self.depth_states
        )
        if depth_ids != tuple(sorted(set(depth_ids))):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "depth states must be unique and sorted",
            )
        if any(
            type(item) is not ObservedFusedRgbdState
            for item in self.fused_rgbd_states
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "fused RGB-D states must be typed",
            )
        fused_ids = tuple(
            item.observation.sensor.sensor_id for item in self.fused_rgbd_states
        )
        if fused_ids != tuple(sorted(set(fused_ids))):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "fused RGB-D states must be unique and sorted",
            )
        if any(type(item) is not ObservedVisualState for item in self.visual_states):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual states must be typed",
            )
        visual_ids = tuple(
            item.observation.sensor.sensor_id for item in self.visual_states
        )
        if visual_ids != tuple(sorted(set(visual_ids))):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual states must be unique and sorted",
            )
        if any(
            type(item) is not ObservedVisualInterpretationState
            for item in self.visual_interpretation_states
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual interpretation states must be typed",
            )
        interpretation_keys = tuple(
            (
                item.observation.sensor.sensor_id,
                item.observation.producer.producer_id,
            )
            for item in self.visual_interpretation_states
        )
        if interpretation_keys != tuple(sorted(set(interpretation_keys))):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "visual interpretation states must be unique and sorted",
            )
        if any(type(item) is not SensorAvailabilityState for item in self.sensor_states):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor states must be typed")
        sensor_ids = tuple(item.sensor.sensor_id for item in self.sensor_states)
        if sensor_ids != tuple(sorted(set(sensor_ids))):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "sensor states must be unique and sorted")
        if any(
            type(item) is not ObservedSensorHealthState
            for item in self.sensor_health_states
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "sensor health states must be typed",
            )
        health_ids = tuple(
            item.observation.sensor.sensor_id for item in self.sensor_health_states
        )
        if health_ids != tuple(sorted(set(health_ids))) or not set(health_ids) <= set(
            sensor_ids
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "sensor health states must be unique, sorted, and expected",
            )

    def document(self) -> dict[str, JSONValue]:
        return {
            "availability": self.availability.value,
            "base_pose": None if self.base_pose is None else self.base_pose.document(),
            "joints": [item.document() for item in self.joints],
            "known_joint_names": list(self.known_joint_names),
            "robot_id": self.robot_id,
            "imu_states": [item.document() for item in self.imu_states],
            "audio_states": [item.document() for item in self.audio_states],
            "depth_states": [item.document() for item in self.depth_states],
            "fused_rgbd_states": [
                item.document() for item in self.fused_rgbd_states
            ],
            "visual_states": [item.document() for item in self.visual_states],
            "visual_interpretation_states": [
                item.document() for item in self.visual_interpretation_states
            ],
            "sensor_states": [item.document() for item in self.sensor_states],
            "sensor_health_states": [
                item.document() for item in self.sensor_health_states
            ],
        }


@dataclass(frozen=True, slots=True, init=False)
class WorldEntity:
    identity: WorldEntityIdentity
    pose: Pose3D | None
    observed_at_ns: int
    provenance: ObservationProvenance
    confidence: float
    freshness: FreshnessState
    observation_id: str
    _properties: JSONValue = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        identity: WorldEntityIdentity,
        pose: Pose3D | None,
        properties: Mapping[str, JSONValue],
        observed_at_ns: int,
        provenance: ObservationProvenance,
        confidence: float,
        freshness: FreshnessState,
        observation_id: str,
    ) -> None:
        if type(identity) is not WorldEntityIdentity:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity identity is invalid")
        if pose is not None and type(pose) is not Pose3D:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity pose is invalid")
        if (
            type(observed_at_ns) is not int
            or not 0 <= observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity time is invalid")
        if type(provenance) is not ObservationProvenance:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity provenance is invalid")
        copied = copy_mapping(properties, field_name="world entity properties")
        if not isinstance(freshness, FreshnessState):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity freshness is invalid")
        if (
            type(observation_id) is not str
            or re.fullmatch(r"world-observation-[0-9a-f]{64}", observation_id) is None
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "entity evidence ID is invalid")
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "pose", pose)
        object.__setattr__(self, "observed_at_ns", observed_at_ns)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "confidence", _confidence(confidence))
        object.__setattr__(self, "freshness", freshness)
        object.__setattr__(self, "observation_id", observation_id)
        object.__setattr__(self, "_properties", copied)

    @property
    def properties(self) -> dict[str, JSONValue]:
        copied = copy_json(self._properties, field_name="world entity properties")
        assert type(copied) is dict
        return copied

    def document(self) -> dict[str, JSONValue]:
        return {
            "confidence": self.confidence,
            "entity_id": self.identity.entity_id,
            "entity_kind": self.identity.kind.value,
            "freshness": self.freshness.value,
            "observation_id": self.observation_id,
            "observed_at_ns": self.observed_at_ns,
            "pose": None if self.pose is None else self.pose.document(),
            "properties": self.properties,
            "provenance": self.provenance.document(),
        }


@dataclass(frozen=True, slots=True)
class WorldModelVersion:
    digest: str
    algorithm: str = "sha256"
    schema_version: int = WORLD_MODEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.algorithm != "sha256" or self.schema_version != WORLD_MODEL_SCHEMA_VERSION:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot version is unsupported")
        if type(self.digest) is not str or _SHA256.fullmatch(self.digest) is None:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot digest is malformed")

    def __str__(self) -> str:
        return f"world_snapshot:sha256:{self.digest}"


@dataclass(frozen=True, slots=True, init=False)
class WorldSnapshot:
    snapshot_id: str
    captured_at_ns: int
    robot: RobotBodyState
    entities: tuple[WorldEntity, ...]
    semantic_states: tuple[ObservedSemanticEvidenceState, ...]
    version: WorldModelVersion

    def __init__(
        self,
        *,
        captured_at_ns: int,
        robot: RobotBodyState,
        entities: tuple[WorldEntity, ...],
        semantic_states: tuple[ObservedSemanticEvidenceState, ...] = (),
        snapshot_id: str | None = None,
        version: WorldModelVersion | None = None,
    ) -> None:
        if (
            type(captured_at_ns) is not int
            or not 0 <= captured_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot time is invalid")
        if type(robot) is not RobotBodyState:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot robot state is invalid")
        if type(entities) is not tuple or len(entities) > MAX_ENVIRONMENT_ENTITIES:
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot entities are invalid")
        if any(type(item) is not WorldEntity for item in entities):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "snapshot entities must be typed WorldEntity values",
            )
        ordered = tuple(sorted(entities, key=lambda item: item.identity.entity_id))
        if len({item.identity.entity_id for item in ordered}) != len(ordered):
            _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot entity IDs repeat")
        if (
            type(semantic_states) is not tuple
            or len(semantic_states) > MAX_SEMANTIC_EVIDENCE_STATES
            or any(
                type(item) is not ObservedSemanticEvidenceState
                for item in semantic_states
            )
        ):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "snapshot semantic evidence states are invalid",
            )
        ordered_semantics = tuple(
            sorted(
                semantic_states,
                key=lambda item: (
                    item.observation.sensor.sensor_id,
                    item.observation.producer.producer_id,
                    item.observation.observed_at_ns,
                    item.observation.result_at_ns,
                    item.observation.observation_id,
                ),
            )
        )
        semantic_ids = tuple(
            item.observation.observation_id for item in ordered_semantics
        )
        if len(semantic_ids) != len(set(semantic_ids)):
            _invalid(
                WorldModelFailureCode.SNAPSHOT_INVARIANT,
                "snapshot semantic evidence identities repeat",
            )
        document: dict[str, JSONValue] = {
            "entities": [item.document() for item in ordered],
            "robot": robot.document(),
            "semantic_states": [
                item.document() for item in ordered_semantics
            ],
            "schema": "ayyo.world-model.snapshot.v1",
        }
        derived = WorldModelVersion(sha256_document(document))
        derived_id = f"world-snapshot-{derived.digest}"
        if version is not None and version != derived:
            raise SnapshotIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "snapshot version does not match world state",
            )
        if snapshot_id is not None and snapshot_id != derived_id:
            raise SnapshotIdentityError(
                WorldModelFailureCode.IDENTITY_MISMATCH,
                "snapshot ID does not match world state",
            )
        object.__setattr__(self, "captured_at_ns", captured_at_ns)
        object.__setattr__(self, "robot", robot)
        object.__setattr__(self, "entities", ordered)
        object.__setattr__(self, "semantic_states", ordered_semantics)
        object.__setattr__(self, "version", derived)
        object.__setattr__(self, "snapshot_id", derived_id)

    def get_entity(self, entity_id: str) -> WorldEntity | None:
        canonical_identifier(entity_id, "entity query")
        return next(
            (entity for entity in self.entities if entity.identity.entity_id == entity_id),
            None,
        )


def rebuild_snapshot(snapshot: WorldSnapshot) -> WorldSnapshot:
    if type(snapshot) is not WorldSnapshot:
        _invalid(WorldModelFailureCode.SNAPSHOT_INVARIANT, "snapshot has an unsupported type")
    return WorldSnapshot(
        captured_at_ns=snapshot.captured_at_ns,
        robot=snapshot.robot,
        entities=snapshot.entities,
        semantic_states=snapshot.semantic_states,
        snapshot_id=snapshot.snapshot_id,
        version=snapshot.version,
    )
