"""Immutable head-depth identity, calibration, and admission contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import math
import re
import struct

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    CameraCalibration,
    DepthFrameObservation,
    MAX_CAMERA_DIMENSION,
    MAX_IMAGE_DATA_BYTES,
    MAX_OBSERVATION_TIME_NS,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorHealthObservation,
    SensorIdentity,
    SensorKind,
    rebuild_observation,
)

from .errors import DepthCameraConfigurationError, DepthCameraValidationError


MAX_DEPTH_CAMERA_SOURCES = 16
MAX_DEPTH_PENDING_PAIRS = 8
MAX_DEPTH_COUNT = (1 << 63) - 1
DEPTH_IMAGE_TOPIC = "/ayyo/camera/head/depth/image_raw"
DEPTH_CAMERA_INFO_TOPIC = "/ayyo/camera/head/depth/camera_info"
DEPTH_INTERFACE = "sensor-msgs.image-camera-info.depth.v1"

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_FRAME = re.compile(r"^[A-Za-z][A-Za-z0-9_/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CALIBRATION_ID = re.compile(r"^camera-calibration-sha256-[0-9a-f]{64}$")
_CALIBRATION_RECORD_ID = re.compile(
    r"^depth-camera-calibration-sha256-[0-9a-f]{64}$"
)
_SOURCE_MANIFEST_ID = re.compile(r"^depth-camera-source-sha256-[0-9a-f]{64}$")
_SESSION_ID = re.compile(r"^depth-camera-session-sha256-[0-9a-f]{64}$")


def _fail(detail: str) -> None:
    raise DepthCameraValidationError(detail)


def _identifier(value: object, field_name: str, maximum: int = 128) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _IDENTIFIER.fullmatch(value) is None
    ):
        _fail(f"{field_name} must be a bounded lowercase ASCII identifier")
    return value


def _frame(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 256
        or _FRAME.fullmatch(value) is None
        or "//" in value
        or value.endswith("/")
    ):
        _fail(f"{field_name} must be a bounded canonical frame")
    return value


def _digest(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _canonical_sha256(document: dict[str, object]) -> str:
    return sha256(
        json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()


class DepthSourceClassification(StrEnum):
    TEST_FIXTURE = "test_fixture"
    SIMULATION = "simulation"
    RECORDED_FIXTURE = "recorded_fixture"
    PROJECT_REVIEWED_DEVICE = "project_reviewed_device"


class DepthCalibrationSource(StrEnum):
    TEST_FIXTURE = "test_fixture"
    SIMULATION_MODEL = "simulation_model"
    PROJECT_FILE = "project_file"
    DEVICE_REPORTED = "device_reported"


class DepthCalibrationState(StrEnum):
    UNKNOWN = "unknown"
    VALID = "valid"
    INVALID = "invalid"


class DepthLifecycleState(StrEnum):
    UNCONFIGURED = "unconfigured"
    INACTIVE = "inactive"
    ACTIVE = "active"
    FINALIZED = "finalized"


class DepthDiagnosticEvent(StrEnum):
    UNCONFIGURED = "unconfigured"
    CALIBRATION_MISSING = "calibration_missing"
    CONFIGURED = "configured"
    ACQUISITION_ACTIVE = "acquisition_active"
    FRAME_ACCEPTED = "frame_accepted"
    LIFECYCLE_INACTIVE = "lifecycle_inactive"
    SESSION_MISMATCH = "session_mismatch"
    WRONG_SOURCE = "wrong_source"
    WRONG_FRAME = "wrong_frame"
    WRONG_DIMENSIONS = "wrong_dimensions"
    UNSUPPORTED_ENCODING = "unsupported_encoding"
    CALIBRATION_INVALID = "calibration_invalid"
    PAIR_MISMATCH = "pair_mismatch"
    STALE_FRAME = "stale_frame"
    FUTURE_FRAME = "future_frame"
    SOURCE_CLOCK_REGRESSION = "source_clock_regression"
    REPEATED_TIMESTAMP = "repeated_timestamp"
    PENDING_EVICTED = "pending_evicted"
    MALFORMED_INPUT = "malformed_input"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True, init=False)
class DepthCameraCalibration:
    sensor: SensorIdentity
    source_id: str
    mount_frame_id: str
    optical_frame_id: str
    calibration_version: str
    calibration_source: DepthCalibrationSource
    import_identity: str | None
    calibration: CameraCalibration
    calibration_record_id: str

    def __init__(
        self,
        *,
        sensor: SensorIdentity,
        source_id: str,
        mount_frame_id: str,
        optical_frame_id: str,
        calibration_version: str,
        calibration_source: DepthCalibrationSource,
        calibration: CameraCalibration,
        import_identity: str | None = None,
        calibration_record_id: str | None = None,
    ) -> None:
        if type(sensor) is not SensorIdentity or sensor.kind is not SensorKind.DEPTH_CAMERA:
            _fail("depth calibration requires one typed depth camera")
        _identifier(source_id, "depth calibration source_id")
        mount = _frame(mount_frame_id, "depth mount frame")
        optical = _frame(optical_frame_id, "depth optical frame")
        if optical != sensor.frame_id or mount == optical:
            _fail("depth calibration frames conflict with the sensor identity")
        _identifier(calibration_version, "depth calibration version")
        if not isinstance(calibration_source, DepthCalibrationSource):
            _fail("depth calibration source classification must be typed")
        if import_identity is not None:
            _identifier(import_identity, "depth calibration import identity")
        if type(calibration) is not CameraCalibration:
            _fail("depth calibration requires validated CameraInfo metadata")
        supported_lengths = {
            "plumb_bob": {0, 5},
            "rational_polynomial": {8},
            "equidistant": {4},
        }
        if len(calibration.d) not in supported_lengths.get(
            calibration.distortion_model, set()
        ):
            _fail("depth calibration distortion model or coefficient count is unsupported")
        document: dict[str, object] = {
            "calibration_id": calibration.calibration_id,
            "calibration_source": calibration_source.value,
            "calibration_version": calibration_version,
            "import_identity": import_identity,
            "mount_frame_id": mount,
            "optical_frame_id": optical,
            "schema": "ayyo.depth-camera-calibration.v1",
            "sensor": sensor.document(),
            "source_id": source_id,
        }
        derived = f"depth-camera-calibration-sha256-{_canonical_sha256(document)}"
        if calibration_record_id is not None and calibration_record_id != derived:
            _fail("depth calibration record identity does not match its content")
        object.__setattr__(self, "sensor", sensor)
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "mount_frame_id", mount)
        object.__setattr__(self, "optical_frame_id", optical)
        object.__setattr__(self, "calibration_version", calibration_version)
        object.__setattr__(self, "calibration_source", calibration_source)
        object.__setattr__(self, "import_identity", import_identity)
        object.__setattr__(self, "calibration", calibration)
        object.__setattr__(self, "calibration_record_id", derived)


@dataclass(frozen=True, slots=True, init=False)
class DepthSourceManifest:
    source_id: str
    robot_id: str
    sensor: SensorIdentity
    producer_id: str
    producer_version: str
    producer_implementation_sha256: str
    provenance: ObservationProvenance
    classification: DepthSourceClassification
    mount_frame_id: str
    encodings: tuple[str, ...]
    minimum_width: int
    maximum_width: int
    minimum_height: int
    maximum_height: int
    minimum_depth_m: float
    maximum_depth_m: float
    image_topic: str
    camera_info_topic: str
    calibration_id: str
    calibration_record_id: str
    device_serial: str | None
    device_fingerprint_sha256: str | None
    manifest_id: str

    def __init__(
        self,
        *,
        source_id: str,
        robot_id: str,
        sensor: SensorIdentity,
        producer_id: str,
        producer_version: str,
        producer_implementation_sha256: str,
        provenance: ObservationProvenance,
        classification: DepthSourceClassification,
        mount_frame_id: str,
        encodings: tuple[str, ...],
        minimum_width: int,
        maximum_width: int,
        minimum_height: int,
        maximum_height: int,
        minimum_depth_m: float,
        maximum_depth_m: float,
        calibration_id: str,
        calibration_record_id: str,
        device_serial: str | None = None,
        device_fingerprint_sha256: str | None = None,
        image_topic: str = DEPTH_IMAGE_TOPIC,
        camera_info_topic: str = DEPTH_CAMERA_INFO_TOPIC,
        manifest_id: str | None = None,
    ) -> None:
        _identifier(source_id, "depth source_id")
        _identifier(robot_id, "depth robot_id")
        if robot_id != AYYO_ROBOT_ID:
            _fail("depth source must bind canonical Ayyo")
        if type(sensor) is not SensorIdentity or sensor.kind is not SensorKind.DEPTH_CAMERA:
            _fail("depth source requires one typed depth camera")
        _identifier(producer_id, "depth producer_id")
        _identifier(producer_version, "depth producer version")
        implementation = _digest(
            producer_implementation_sha256,
            "depth producer implementation",
        )
        if type(provenance) is not ObservationProvenance:
            _fail("depth source provenance must be typed")
        if provenance.source_id != source_id or provenance.interface != DEPTH_INTERFACE:
            _fail("depth provenance must bind the exact source and reviewed interface")
        if not isinstance(classification, DepthSourceClassification):
            _fail("depth source classification must be typed")
        expected_source_kind = {
            DepthSourceClassification.TEST_FIXTURE: ObservationSourceKind.TEST_FIXTURE,
            DepthSourceClassification.SIMULATION: ObservationSourceKind.SIMULATION,
            DepthSourceClassification.RECORDED_FIXTURE: ObservationSourceKind.RECORDED_DATA,
            DepthSourceClassification.PROJECT_REVIEWED_DEVICE: ObservationSourceKind.PHYSICAL_SENSOR,
        }[classification]
        if provenance.source_kind is not expected_source_kind:
            _fail("depth source classification and provenance kind cannot substitute")
        expected_transport = (
            ObservationTransport.RECORDED
            if classification is DepthSourceClassification.RECORDED_FIXTURE
            else ObservationTransport.ROS2
        )
        if provenance.transport is not expected_transport:
            _fail("depth source classification and transport cannot substitute")
        mount = _frame(mount_frame_id, "depth mount frame")
        if mount == sensor.frame_id:
            _fail("depth mount and optical frames must remain distinct")
        if (
            type(encodings) is not tuple
            or not encodings
            or encodings != tuple(sorted(set(encodings)))
            or not set(encodings) <= {"16UC1", "32FC1"}
        ):
            _fail("depth encoding allowlist must be a nonempty canonical subset")
        dimensions = (minimum_width, maximum_width, minimum_height, maximum_height)
        if any(type(value) is not int for value in dimensions) or not (
            1 <= minimum_width <= maximum_width <= MAX_CAMERA_DIMENSION
            and 1 <= minimum_height <= maximum_height <= MAX_CAMERA_DIMENSION
            and maximum_width * maximum_height <= 16_777_216
        ):
            _fail("depth geometry bounds are invalid")
        if (
            type(minimum_depth_m) not in {int, float}
            or type(maximum_depth_m) not in {int, float}
            or not math.isfinite(minimum_depth_m)
            or not math.isfinite(maximum_depth_m)
            or not 0.0 < minimum_depth_m < maximum_depth_m <= 10_000.0
        ):
            _fail("depth metric range is invalid")
        minimum_depth = float(minimum_depth_m)
        maximum_depth = float(maximum_depth_m)
        if image_topic != DEPTH_IMAGE_TOPIC or camera_info_topic != DEPTH_CAMERA_INFO_TOPIC:
            _fail("depth topics must equal the reviewed canonical ROS interfaces")
        if type(calibration_id) is not str or _CALIBRATION_ID.fullmatch(calibration_id) is None:
            _fail("depth source calibration identity is malformed")
        if (
            type(calibration_record_id) is not str
            or _CALIBRATION_RECORD_ID.fullmatch(calibration_record_id) is None
        ):
            _fail("depth source calibration record identity is malformed")
        if device_serial is not None:
            if (
                type(device_serial) is not str
                or not device_serial
                or len(device_serial) > 128
                or re.fullmatch(r"[A-Za-z0-9._:-]+", device_serial) is None
            ):
                _fail("depth device serial is malformed")
        if device_fingerprint_sha256 is not None:
            _digest(device_fingerprint_sha256, "depth device fingerprint")
        if classification is not DepthSourceClassification.PROJECT_REVIEWED_DEVICE and (
            device_serial is not None or device_fingerprint_sha256 is not None
        ):
            _fail("non-physical depth profiles cannot claim physical device identity")
        document: dict[str, object] = {
            "calibration_id": calibration_id,
            "calibration_record_id": calibration_record_id,
            "camera_info_topic": camera_info_topic,
            "classification": classification.value,
            "device_fingerprint_sha256": device_fingerprint_sha256,
            "device_serial": device_serial,
            "encodings": list(encodings),
            "image_topic": image_topic,
            "maximum_depth_m": maximum_depth,
            "maximum_height": maximum_height,
            "maximum_width": maximum_width,
            "minimum_depth_m": minimum_depth,
            "minimum_height": minimum_height,
            "minimum_width": minimum_width,
            "mount_frame_id": mount,
            "producer_id": producer_id,
            "producer_implementation_sha256": implementation,
            "producer_version": producer_version,
            "provenance": provenance.document(),
            "robot_id": robot_id,
            "schema": "ayyo.depth-camera-source.v1",
            "sensor": sensor.document(),
            "source_id": source_id,
        }
        derived = f"depth-camera-source-sha256-{_canonical_sha256(document)}"
        if manifest_id is not None and manifest_id != derived:
            _fail("depth source manifest identity does not match its content")
        for field_name, value in (
            ("source_id", source_id),
            ("robot_id", robot_id),
            ("sensor", sensor),
            ("producer_id", producer_id),
            ("producer_version", producer_version),
            ("producer_implementation_sha256", implementation),
            ("provenance", provenance),
            ("classification", classification),
            ("mount_frame_id", mount),
            ("encodings", encodings),
            ("minimum_width", minimum_width),
            ("maximum_width", maximum_width),
            ("minimum_height", minimum_height),
            ("maximum_height", maximum_height),
            ("minimum_depth_m", minimum_depth),
            ("maximum_depth_m", maximum_depth),
            ("image_topic", image_topic),
            ("camera_info_topic", camera_info_topic),
            ("calibration_id", calibration_id),
            ("calibration_record_id", calibration_record_id),
            ("device_serial", device_serial),
            ("device_fingerprint_sha256", device_fingerprint_sha256),
            ("manifest_id", derived),
        ):
            object.__setattr__(self, field_name, value)

    def requirement(self) -> DepthTrustRequirement:
        return DepthTrustRequirement(
            source_id=self.source_id,
            robot_id=self.robot_id,
            sensor=self.sensor,
            producer_id=self.producer_id,
            producer_implementation_sha256=self.producer_implementation_sha256,
            provenance=self.provenance,
            classification=self.classification,
            calibration_id=self.calibration_id,
            calibration_record_id=self.calibration_record_id,
            source_manifest_id=self.manifest_id,
        )


@dataclass(frozen=True, slots=True)
class DepthTrustRequirement:
    source_id: str
    robot_id: str
    sensor: SensorIdentity
    producer_id: str
    producer_implementation_sha256: str
    provenance: ObservationProvenance
    classification: DepthSourceClassification
    calibration_id: str
    calibration_record_id: str
    source_manifest_id: str

    def __post_init__(self) -> None:
        _identifier(self.source_id, "depth trust source_id")
        _identifier(self.robot_id, "depth trust robot_id")
        if type(self.sensor) is not SensorIdentity or self.sensor.kind is not SensorKind.DEPTH_CAMERA:
            _fail("depth trust sensor is invalid")
        _identifier(self.producer_id, "depth trust producer_id")
        _digest(self.producer_implementation_sha256, "depth trust producer implementation")
        if type(self.provenance) is not ObservationProvenance or self.provenance.source_id != self.source_id:
            _fail("depth trust provenance is invalid")
        if not isinstance(self.classification, DepthSourceClassification):
            _fail("depth trust source classification is invalid")
        if _CALIBRATION_ID.fullmatch(self.calibration_id) is None:
            _fail("depth trust calibration identity is invalid")
        if _CALIBRATION_RECORD_ID.fullmatch(self.calibration_record_id) is None:
            _fail("depth trust calibration record identity is invalid")
        if _SOURCE_MANIFEST_ID.fullmatch(self.source_manifest_id) is None:
            _fail("depth trust source manifest identity is invalid")

    def matches_unsealed(self, frame: DepthFrameObservation) -> bool:
        return (
            type(frame) is DepthFrameObservation
            and frame.robot_id == self.robot_id
            and frame.sensor == self.sensor
            and frame.provenance == self.provenance
            and frame.calibration_id == self.calibration_id
            and frame.calibration_record_id == self.calibration_record_id
            and frame.source_manifest_id == self.source_manifest_id
        )

    def matches(self, admission: DepthCameraAdmission) -> bool:
        return (
            type(admission) is DepthCameraAdmission
            and admission.requirement == self
            and self.matches_unsealed(admission.frame)
        )


@dataclass(frozen=True, slots=True)
class DepthImageMetadata:
    source_id: str
    session_id: str
    robot_id: str
    sensor: SensorIdentity
    frame_id: str
    observed_at_ns: int
    width: int
    height: int
    encoding: str
    step: int
    data_size_bytes: int
    is_bigendian: bool
    valid_depth_count: int
    invalid_depth_count: int
    minimum_depth_m: float
    maximum_depth_m: float
    payload_sha256: str
    provenance: ObservationProvenance

    def __post_init__(self) -> None:
        _identifier(self.source_id, "depth image source_id")
        if type(self.session_id) is not str or _SESSION_ID.fullmatch(self.session_id) is None:
            _fail("depth image session identity is malformed")
        _identifier(self.robot_id, "depth image robot_id")
        if type(self.sensor) is not SensorIdentity or self.sensor.kind is not SensorKind.DEPTH_CAMERA:
            _fail("depth image sensor identity is invalid")
        _frame(self.frame_id, "depth image frame")
        if type(self.observed_at_ns) is not int or not 1 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS:
            _fail("depth image acquisition time is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _fail("depth image provenance is required")
        if type(self.width) is not int or type(self.height) is not int:
            _fail("depth image dimensions are invalid")
        if type(self.step) is not int or type(self.data_size_bytes) is not int:
            _fail("depth image byte metadata is invalid")
        if type(self.is_bigendian) is not bool:
            _fail("depth image endian metadata is invalid")
        _digest(self.payload_sha256, "depth image payload fingerprint")
        if (
            type(self.valid_depth_count) is not int
            or type(self.invalid_depth_count) is not int
            or self.valid_depth_count < 1
            or self.invalid_depth_count < 0
            or self.valid_depth_count + self.invalid_depth_count != self.width * self.height
        ):
            _fail("depth image validity summary is invalid")
        if not (
            type(self.minimum_depth_m) is float
            and type(self.maximum_depth_m) is float
            and math.isfinite(self.minimum_depth_m)
            and math.isfinite(self.maximum_depth_m)
            and 0.0 < self.minimum_depth_m <= self.maximum_depth_m
        ):
            _fail("depth image range summary is invalid")


@dataclass(frozen=True, slots=True)
class DepthCameraInfoMetadata:
    source_id: str
    session_id: str
    robot_id: str
    sensor: SensorIdentity
    frame_id: str
    observed_at_ns: int
    calibration: DepthCameraCalibration
    provenance: ObservationProvenance

    def __post_init__(self) -> None:
        _identifier(self.source_id, "depth CameraInfo source_id")
        if type(self.session_id) is not str or _SESSION_ID.fullmatch(self.session_id) is None:
            _fail("depth CameraInfo session identity is malformed")
        _identifier(self.robot_id, "depth CameraInfo robot_id")
        if type(self.sensor) is not SensorIdentity or self.sensor.kind is not SensorKind.DEPTH_CAMERA:
            _fail("depth CameraInfo sensor identity is invalid")
        _frame(self.frame_id, "depth CameraInfo frame")
        if type(self.observed_at_ns) is not int or not 1 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS:
            _fail("depth CameraInfo acquisition time is invalid")
        if type(self.calibration) is not DepthCameraCalibration:
            _fail("depth CameraInfo calibration is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _fail("depth CameraInfo provenance is required")


@dataclass(frozen=True, slots=True)
class DepthDiagnostics:
    source_id: str
    session_id: str | None
    lifecycle_state: DepthLifecycleState
    calibration_state: DepthCalibrationState
    event: DepthDiagnosticEvent
    availability: SensorAvailability
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    evicted_count: int
    pending_image_count: int
    pending_camera_info_count: int
    observed_at_ns: int

    def __post_init__(self) -> None:
        _identifier(self.source_id, "depth diagnostics source_id")
        if self.session_id is not None and _SESSION_ID.fullmatch(self.session_id) is None:
            _fail("depth diagnostics session identity is malformed")
        if not isinstance(self.lifecycle_state, DepthLifecycleState):
            _fail("depth diagnostics lifecycle is invalid")
        if not isinstance(self.calibration_state, DepthCalibrationState):
            _fail("depth diagnostics calibration state is invalid")
        if not isinstance(self.event, DepthDiagnosticEvent):
            _fail("depth diagnostics event is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _fail("depth diagnostics availability is invalid")
        counts = (
            self.accepted_count,
            self.rejected_count,
            self.duplicate_count,
            self.evicted_count,
            self.pending_image_count,
            self.pending_camera_info_count,
        )
        if any(type(value) is not int or not 0 <= value <= MAX_DEPTH_COUNT for value in counts):
            _fail("depth diagnostics counters are invalid")
        if self.pending_image_count > MAX_DEPTH_PENDING_PAIRS or self.pending_camera_info_count > MAX_DEPTH_PENDING_PAIRS:
            _fail("depth diagnostics pending counts exceed their hard bound")
        if type(self.observed_at_ns) is not int or not 0 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS:
            _fail("depth diagnostics time is invalid")

    def evidence_detail(self) -> str:
        session = "unknown" if self.session_id is None else self.session_id
        return (
            f"depth_camera:{self.event.value}:lifecycle={self.lifecycle_state.value}:"
            f"calibration={self.calibration_state.value}:session={session}:"
            f"accepted={self.accepted_count}:rejected={self.rejected_count}"
        )


_ADMISSION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class DepthCameraAdmission:
    frame: DepthFrameObservation
    health: SensorHealthObservation
    requirement: DepthTrustRequirement
    session_id: str
    diagnostics: DepthDiagnostics

    def __init__(
        self,
        *,
        frame: DepthFrameObservation,
        health: SensorHealthObservation,
        requirement: DepthTrustRequirement,
        session_id: str,
        diagnostics: DepthDiagnostics,
        _seal: object,
    ) -> None:
        if _seal is not _ADMISSION_SEAL:
            raise DepthCameraConfigurationError(
                "depth admissions can only be issued by the lifecycle adapter"
            )
        rebuilt_frame = rebuild_observation(frame)
        rebuilt_health = rebuild_observation(health)
        if type(rebuilt_frame) is not DepthFrameObservation or type(rebuilt_health) is not SensorHealthObservation:
            _fail("depth admission evidence is invalid")
        if type(requirement) is not DepthTrustRequirement:
            _fail("depth admission requirement is invalid")
        if _SESSION_ID.fullmatch(session_id) is None or diagnostics.session_id != session_id:
            _fail("depth admission session identity is invalid")
        if (
            rebuilt_frame.session_id != session_id
            or not requirement.matches_unsealed(rebuilt_frame)
            or rebuilt_health.sensor != rebuilt_frame.sensor
            or rebuilt_health.provenance != rebuilt_frame.provenance
            or rebuilt_health.observed_at_ns != rebuilt_frame.observed_at_ns
        ):
            _fail("depth admission does not match its exact requirement")
        object.__setattr__(self, "frame", rebuilt_frame)
        object.__setattr__(self, "health", rebuilt_health)
        object.__setattr__(self, "requirement", requirement)
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "diagnostics", diagnostics)


def _issue_admission(**values) -> DepthCameraAdmission:
    return DepthCameraAdmission(_seal=_ADMISSION_SEAL, **values)


def depth_camera_session_id(manifest_id: str, epoch: int) -> str:
    if _SOURCE_MANIFEST_ID.fullmatch(manifest_id) is None:
        _fail("depth session manifest identity is invalid")
    if type(epoch) is not int or not 1 <= epoch <= MAX_DEPTH_COUNT:
        _fail("depth session epoch is invalid")
    digest = _canonical_sha256(
        {
            "epoch": epoch,
            "manifest_id": manifest_id,
            "schema": "ayyo.depth-camera-session.v1",
        }
    )
    return f"depth-camera-session-sha256-{digest}"


def summarize_depth_image(
    *,
    source: DepthSourceManifest,
    session_id: str,
    observed_at_ns: int,
    frame_id: str,
    width: int,
    height: int,
    encoding: str,
    step: int,
    is_bigendian: bool,
    data: bytes,
) -> DepthImageMetadata:
    """Validate one raw buffer, return compact statistics, and retain no pixels."""
    if type(source) is not DepthSourceManifest:
        _fail("depth image requires one reviewed source")
    if type(data) is not bytes or not data:
        _fail("depth image payload must be nonempty immutable bytes")
    if len(data) > MAX_IMAGE_DATA_BYTES:
        _fail("depth image payload exceeds its hard bound")
    bytes_per_pixel = {"16UC1": 2, "32FC1": 4}.get(encoding)
    if bytes_per_pixel is None or encoding not in source.encodings:
        _fail("depth image encoding is not allowed by its source")
    if (
        type(width) is not int
        or type(height) is not int
        or not source.minimum_width <= width <= source.maximum_width
        or not source.minimum_height <= height <= source.maximum_height
    ):
        _fail("depth image dimensions are outside source bounds")
    if type(step) is not int or step < width * bytes_per_pixel or len(data) != step * height:
        _fail("depth image step or byte count is inconsistent")
    if type(is_bigendian) is not bool:
        _fail("depth image endian flag must be boolean")
    endian = ">" if is_bigendian else "<"
    valid: list[float] = []
    invalid_count = 0
    for row in range(height):
        start = row * step
        row_data = data[start : start + width * bytes_per_pixel]
        if encoding == "16UC1":
            values = struct.unpack(f"{endian}{width}H", row_data)
            metric_values = (value * 0.001 for value in values)
        else:
            values = struct.unpack(f"{endian}{width}f", row_data)
            metric_values = iter(values)
        for value in metric_values:
            if math.isnan(value):
                if encoding != "32FC1":
                    _fail("NaN is forbidden for integer depth")
                invalid_count += 1
                continue
            if not math.isfinite(value) or value < 0.0:
                _fail("depth payload contains negative or infinite depth")
            if value == 0.0:
                invalid_count += 1
                continue
            if not source.minimum_depth_m <= value <= source.maximum_depth_m:
                _fail("depth payload contains a value outside the reviewed metric range")
            valid.append(float(value))
    if not valid:
        _fail("depth payload contains no valid measurement")
    return DepthImageMetadata(
        source_id=source.source_id,
        session_id=session_id,
        robot_id=source.robot_id,
        sensor=source.sensor,
        frame_id=frame_id,
        observed_at_ns=observed_at_ns,
        width=width,
        height=height,
        encoding=encoding,
        step=step,
        data_size_bytes=len(data),
        is_bigendian=is_bigendian,
        valid_depth_count=len(valid),
        invalid_depth_count=invalid_count,
        minimum_depth_m=min(valid),
        maximum_depth_m=max(valid),
        payload_sha256=sha256(data).hexdigest(),
        provenance=source.provenance,
    )
