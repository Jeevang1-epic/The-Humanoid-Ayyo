"""Immutable physical-camera source, calibration, and admission contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import re

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    CameraCalibration,
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
    VisualFrameObservation,
    rebuild_observation,
)

from .errors import PhysicalCameraConfigurationError, PhysicalCameraValidationError


MAX_PHYSICAL_CAMERA_SOURCES = 16
MAX_PHYSICAL_CAMERA_PENDING_PAIRS = 8
MAX_PHYSICAL_CAMERA_IDENTIFIER_LENGTH = 128
MAX_PHYSICAL_CAMERA_DETAIL_LENGTH = 512
MAX_PHYSICAL_CAMERA_COUNT = (1 << 63) - 1
IMAGE_TOPIC = "/ayyo/camera/head/image_raw"
CAMERA_INFO_TOPIC = "/ayyo/camera/head/camera_info"

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_FRAME = re.compile(r"^[A-Za-z][A-Za-z0-9_/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CALIBRATION_ID = re.compile(r"^camera-calibration-sha256-[0-9a-f]{64}$")
_CALIBRATION_RECORD_ID = re.compile(
    r"^physical-camera-calibration-sha256-[0-9a-f]{64}$"
)
_SOURCE_MANIFEST_ID = re.compile(r"^physical-camera-source-sha256-[0-9a-f]{64}$")
_SESSION_ID = re.compile(r"^physical-camera-session-sha256-[0-9a-f]{64}$")


def _fail(detail: str) -> None:
    raise PhysicalCameraValidationError(detail)


def _identifier(value: object, field_name: str, *, maximum: int = 128) -> str:
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
    encoded = json.dumps(
        document,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return sha256(encoded).hexdigest()


def _bounded_topic(value: object, expected: str, field_name: str) -> str:
    if type(value) is not str or value != expected:
        _fail(f"{field_name} must equal the reviewed Ayyo camera topic")
    return value


class PhysicalCameraSourceClassification(StrEnum):
    TEST_FIXTURE = "test_fixture"
    PROJECT_REVIEWED_DEVICE = "project_reviewed_device"


class PhysicalCameraCalibrationSource(StrEnum):
    TEST_FIXTURE = "test_fixture"
    PROJECT_FILE = "project_file"
    DEVICE_REPORTED = "device_reported"
    MANUFACTURER_RECORD = "manufacturer_record"


class PhysicalCameraCalibrationState(StrEnum):
    UNKNOWN = "unknown"
    VALID = "valid"
    INVALID = "invalid"


class PhysicalCameraLifecycleState(StrEnum):
    UNCONFIGURED = "unconfigured"
    INACTIVE = "inactive"
    ACTIVE = "active"
    FINALIZED = "finalized"


class PhysicalCameraDiagnosticEvent(StrEnum):
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
    DEVICE_ERROR = "device_error"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True, init=False)
class PhysicalCameraCalibration:
    """One valid calibration bound to an exact camera and physical source."""

    camera: SensorIdentity
    source_id: str
    camera_frame_id: str
    optical_frame_id: str
    calibration_version: str
    calibration_source: PhysicalCameraCalibrationSource
    import_identity: str | None
    calibration: CameraCalibration
    calibration_record_id: str

    def __init__(
        self,
        *,
        camera: SensorIdentity,
        source_id: str,
        camera_frame_id: str,
        optical_frame_id: str,
        calibration_version: str,
        calibration_source: PhysicalCameraCalibrationSource,
        calibration: CameraCalibration,
        import_identity: str | None = None,
        calibration_record_id: str | None = None,
    ) -> None:
        if type(camera) is not SensorIdentity or camera.kind is not SensorKind.RGB_CAMERA:
            _fail("physical calibration requires one typed RGB camera")
        _identifier(source_id, "physical calibration source_id")
        camera_frame = _frame(camera_frame_id, "physical camera frame")
        optical_frame = _frame(optical_frame_id, "physical optical frame")
        if optical_frame != camera.frame_id:
            _fail("physical calibration optical frame must equal the camera identity frame")
        if camera_frame == optical_frame:
            _fail("camera and optical frames must remain distinct")
        _identifier(calibration_version, "calibration version")
        if not isinstance(calibration_source, PhysicalCameraCalibrationSource):
            _fail("calibration source classification must be typed")
        if import_identity is not None:
            _identifier(import_identity, "calibration import identity")
        if type(calibration) is not CameraCalibration:
            _fail("physical calibration requires validated CameraCalibration metadata")
        supported_lengths = {
            "plumb_bob": {0, 5},
            "rational_polynomial": {8},
            "equidistant": {4},
        }
        lengths = supported_lengths.get(calibration.distortion_model)
        if lengths is None or len(calibration.d) not in lengths:
            _fail("physical calibration distortion model or coefficient count is unsupported")
        document: dict[str, object] = {
            "calibration_id": calibration.calibration_id,
            "calibration_source": calibration_source.value,
            "calibration_version": calibration_version,
            "camera": camera.document(),
            "camera_frame_id": camera_frame,
            "import_identity": import_identity,
            "optical_frame_id": optical_frame,
            "schema": "ayyo.physical-camera-calibration.v1",
            "source_id": source_id,
        }
        derived = f"physical-camera-calibration-sha256-{_canonical_sha256(document)}"
        if calibration_record_id is not None and calibration_record_id != derived:
            _fail("physical calibration record identity does not match its content")
        object.__setattr__(self, "camera", camera)
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "camera_frame_id", camera_frame)
        object.__setattr__(self, "optical_frame_id", optical_frame)
        object.__setattr__(self, "calibration_version", calibration_version)
        object.__setattr__(self, "calibration_source", calibration_source)
        object.__setattr__(self, "import_identity", import_identity)
        object.__setattr__(self, "calibration", calibration)
        object.__setattr__(self, "calibration_record_id", derived)

    def document(self) -> dict[str, object]:
        return {
            "calibration_id": self.calibration.calibration_id,
            "calibration_record_id": self.calibration_record_id,
            "calibration_source": self.calibration_source.value,
            "calibration_version": self.calibration_version,
            "camera": self.camera.document(),
            "camera_frame_id": self.camera_frame_id,
            "height": self.calibration.height,
            "import_identity": self.import_identity,
            "optical_frame_id": self.optical_frame_id,
            "source_id": self.source_id,
            "width": self.calibration.width,
        }


@dataclass(frozen=True, slots=True, init=False)
class PhysicalCameraSourceManifest:
    """Explicit allowlisted physical-source and driver-neutral adapter identity."""

    source_id: str
    robot_id: str
    camera: SensorIdentity
    adapter_id: str
    adapter_version: str
    adapter_implementation_sha256: str
    provenance: ObservationProvenance
    classification: PhysicalCameraSourceClassification
    device_serial: str | None
    device_fingerprint_sha256: str | None
    camera_frame_id: str
    encodings: tuple[str, ...]
    minimum_width: int
    maximum_width: int
    minimum_height: int
    maximum_height: int
    image_topic: str
    camera_info_topic: str
    calibration_id: str
    calibration_record_id: str
    manifest_id: str

    def __init__(
        self,
        *,
        source_id: str,
        robot_id: str,
        camera: SensorIdentity,
        adapter_id: str,
        adapter_version: str,
        adapter_implementation_sha256: str,
        provenance: ObservationProvenance,
        classification: PhysicalCameraSourceClassification,
        camera_frame_id: str,
        encodings: tuple[str, ...],
        minimum_width: int,
        maximum_width: int,
        minimum_height: int,
        maximum_height: int,
        calibration_id: str,
        calibration_record_id: str,
        device_serial: str | None = None,
        device_fingerprint_sha256: str | None = None,
        image_topic: str = IMAGE_TOPIC,
        camera_info_topic: str = CAMERA_INFO_TOPIC,
        manifest_id: str | None = None,
    ) -> None:
        _identifier(source_id, "physical camera source_id")
        _identifier(robot_id, "physical camera robot_id")
        if robot_id != AYYO_ROBOT_ID:
            _fail("physical camera source must bind canonical Ayyo")
        if type(camera) is not SensorIdentity or camera.kind is not SensorKind.RGB_CAMERA:
            _fail("physical source requires one typed RGB camera")
        _identifier(adapter_id, "physical camera adapter_id")
        _identifier(adapter_version, "physical camera adapter version")
        implementation = _digest(
            adapter_implementation_sha256,
            "physical camera adapter implementation",
        )
        if (
            type(provenance) is not ObservationProvenance
            or provenance.source_kind is not ObservationSourceKind.PHYSICAL_SENSOR
            or provenance.clock is not ObservationClock.ROS_SYSTEM_TIME
            or provenance.transport is not ObservationTransport.ROS2
            or provenance.source_id != source_id
            or provenance.interface != "sensor-msgs.image-camera-info.v1"
        ):
            _fail("physical source provenance must be the exact reviewed ROS system-time profile")
        if not isinstance(classification, PhysicalCameraSourceClassification):
            _fail("physical source classification must be typed")
        if device_serial is not None:
            if (
                type(device_serial) is not str
                or not device_serial
                or device_serial != device_serial.strip()
                or len(device_serial) > MAX_PHYSICAL_CAMERA_IDENTIFIER_LENGTH
                or re.fullmatch(r"[A-Za-z0-9._:-]+", device_serial) is None
            ):
                _fail("device serial must be absent or bounded explicit device text")
        if device_fingerprint_sha256 is not None:
            _digest(device_fingerprint_sha256, "physical device fingerprint")
        camera_frame = _frame(camera_frame_id, "physical camera frame")
        if camera_frame == camera.frame_id:
            _fail("physical camera and optical frame identities must remain distinct")
        if (
            type(encodings) is not tuple
            or not encodings
            or len(encodings) > 4
            or any(type(value) is not str for value in encodings)
            or encodings != tuple(sorted(set(encodings)))
            or encodings != ("rgb8",)
        ):
            _fail("v1 physical camera encoding allowlist must be exactly rgb8")
        dimensions = (minimum_width, maximum_width, minimum_height, maximum_height)
        if any(type(value) is not int for value in dimensions) or not (
            1 <= minimum_width <= maximum_width <= MAX_CAMERA_DIMENSION
            and 1 <= minimum_height <= maximum_height <= MAX_CAMERA_DIMENSION
            and maximum_width * maximum_height <= 16_777_216
        ):
            _fail("physical camera geometry bounds are invalid")
        _bounded_topic(image_topic, IMAGE_TOPIC, "image topic")
        _bounded_topic(camera_info_topic, CAMERA_INFO_TOPIC, "CameraInfo topic")
        if type(calibration_id) is not str or _CALIBRATION_ID.fullmatch(calibration_id) is None:
            _fail("physical source calibration identity is malformed")
        if (
            type(calibration_record_id) is not str
            or _CALIBRATION_RECORD_ID.fullmatch(calibration_record_id) is None
        ):
            _fail("physical source calibration record identity is malformed")
        document: dict[str, object] = {
            "adapter_id": adapter_id,
            "adapter_implementation_sha256": implementation,
            "adapter_version": adapter_version,
            "calibration_id": calibration_id,
            "calibration_record_id": calibration_record_id,
            "camera": camera.document(),
            "camera_frame_id": camera_frame,
            "camera_info_topic": camera_info_topic,
            "classification": classification.value,
            "device_fingerprint_sha256": device_fingerprint_sha256,
            "device_serial": device_serial,
            "encodings": list(encodings),
            "image_topic": image_topic,
            "maximum_height": maximum_height,
            "maximum_width": maximum_width,
            "minimum_height": minimum_height,
            "minimum_width": minimum_width,
            "provenance": provenance.document(),
            "robot_id": robot_id,
            "schema": "ayyo.physical-camera-source.v1",
            "source_id": source_id,
        }
        derived = f"physical-camera-source-sha256-{_canonical_sha256(document)}"
        if manifest_id is not None and manifest_id != derived:
            _fail("physical source manifest identity does not match its content")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "robot_id", robot_id)
        object.__setattr__(self, "camera", camera)
        object.__setattr__(self, "adapter_id", adapter_id)
        object.__setattr__(self, "adapter_version", adapter_version)
        object.__setattr__(self, "adapter_implementation_sha256", implementation)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "classification", classification)
        object.__setattr__(self, "device_serial", device_serial)
        object.__setattr__(
            self,
            "device_fingerprint_sha256",
            device_fingerprint_sha256,
        )
        object.__setattr__(self, "camera_frame_id", camera_frame)
        object.__setattr__(self, "encodings", encodings)
        object.__setattr__(self, "minimum_width", minimum_width)
        object.__setattr__(self, "maximum_width", maximum_width)
        object.__setattr__(self, "minimum_height", minimum_height)
        object.__setattr__(self, "maximum_height", maximum_height)
        object.__setattr__(self, "image_topic", image_topic)
        object.__setattr__(self, "camera_info_topic", camera_info_topic)
        object.__setattr__(self, "calibration_id", calibration_id)
        object.__setattr__(self, "calibration_record_id", calibration_record_id)
        object.__setattr__(self, "manifest_id", derived)

    def requirement(self) -> PhysicalCameraTrustRequirement:
        return PhysicalCameraTrustRequirement(
            source_id=self.source_id,
            robot_id=self.robot_id,
            camera=self.camera,
            adapter_id=self.adapter_id,
            adapter_implementation_sha256=self.adapter_implementation_sha256,
            provenance=self.provenance,
            classification=self.classification,
            calibration_id=self.calibration_id,
            calibration_record_id=self.calibration_record_id,
            source_manifest_id=self.manifest_id,
        )


@dataclass(frozen=True, slots=True)
class PhysicalCameraTrustRequirement:
    source_id: str
    robot_id: str
    camera: SensorIdentity
    adapter_id: str
    adapter_implementation_sha256: str
    provenance: ObservationProvenance
    classification: PhysicalCameraSourceClassification
    calibration_id: str
    calibration_record_id: str
    source_manifest_id: str

    def __post_init__(self) -> None:
        _identifier(self.source_id, "physical trust source_id")
        _identifier(self.robot_id, "physical trust robot_id")
        if type(self.camera) is not SensorIdentity or self.camera.kind is not SensorKind.RGB_CAMERA:
            _fail("physical trust requirement camera is invalid")
        _identifier(self.adapter_id, "physical trust adapter_id")
        _digest(self.adapter_implementation_sha256, "physical trust adapter implementation")
        if (
            type(self.provenance) is not ObservationProvenance
            or self.provenance.source_kind is not ObservationSourceKind.PHYSICAL_SENSOR
            or self.provenance.source_id != self.source_id
        ):
            _fail("physical trust provenance is invalid")
        if not isinstance(self.classification, PhysicalCameraSourceClassification):
            _fail("physical trust source classification is invalid")
        if _CALIBRATION_ID.fullmatch(self.calibration_id) is None:
            _fail("physical trust calibration identity is invalid")
        if _CALIBRATION_RECORD_ID.fullmatch(self.calibration_record_id) is None:
            _fail("physical trust calibration record identity is invalid")
        if _SOURCE_MANIFEST_ID.fullmatch(self.source_manifest_id) is None:
            _fail("physical trust source manifest identity is invalid")

    def matches_unsealed(self, frame: VisualFrameObservation) -> bool:
        return (
            type(frame) is VisualFrameObservation
            and frame.robot_id == self.robot_id
            and frame.sensor == self.camera
            and frame.provenance == self.provenance
            and frame.calibration_id == self.calibration_id
        )

    def matches(self, admission: PhysicalCameraAdmission) -> bool:
        return (
            type(admission) is PhysicalCameraAdmission
            and admission.requirement == self
            and admission.frame.robot_id == self.robot_id
            and admission.frame.sensor == self.camera
            and admission.frame.provenance == self.provenance
            and admission.frame.calibration_id == self.calibration_id
        )


@dataclass(frozen=True, slots=True)
class PhysicalCameraImageMetadata:
    source_id: str
    session_id: str
    robot_id: str
    camera: SensorIdentity
    frame_id: str
    observed_at_ns: int
    width: int
    height: int
    encoding: str
    step: int
    data_size_bytes: int
    is_bigendian: bool
    provenance: ObservationProvenance

    def __post_init__(self) -> None:
        _identifier(self.source_id, "physical image source_id")
        if type(self.session_id) is not str or _SESSION_ID.fullmatch(self.session_id) is None:
            _fail("physical image session identity is malformed")
        _identifier(self.robot_id, "physical image robot_id")
        if type(self.camera) is not SensorIdentity or self.camera.kind is not SensorKind.RGB_CAMERA:
            _fail("physical image camera identity is invalid")
        _frame(self.frame_id, "physical image frame")
        if (
            type(self.observed_at_ns) is not int
            or not 1 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _fail("physical image acquisition time is invalid")
        if (
            type(self.width) is not int
            or type(self.height) is not int
            or not 1 <= self.width <= MAX_CAMERA_DIMENSION
            or not 1 <= self.height <= MAX_CAMERA_DIMENSION
        ):
            _fail("physical image dimensions are invalid")
        if type(self.encoding) is not str or len(self.encoding) > 32:
            _fail("physical image encoding metadata is invalid")
        if (
            type(self.step) is not int
            or type(self.data_size_bytes) is not int
            or not 1 <= self.step <= MAX_IMAGE_DATA_BYTES
            or self.data_size_bytes != self.step * self.height
            or self.data_size_bytes > MAX_IMAGE_DATA_BYTES
        ):
            _fail("physical image stride or byte-count metadata is invalid")
        if type(self.is_bigendian) is not bool:
            _fail("physical image endian metadata is invalid")
        if type(self.provenance) is not ObservationProvenance:
            _fail("physical image provenance is required")


@dataclass(frozen=True, slots=True)
class PhysicalCameraInfoMetadata:
    source_id: str
    session_id: str
    robot_id: str
    camera: SensorIdentity
    frame_id: str
    observed_at_ns: int
    calibration: PhysicalCameraCalibration
    provenance: ObservationProvenance

    def __post_init__(self) -> None:
        _identifier(self.source_id, "physical CameraInfo source_id")
        if type(self.session_id) is not str or _SESSION_ID.fullmatch(self.session_id) is None:
            _fail("physical CameraInfo session identity is malformed")
        _identifier(self.robot_id, "physical CameraInfo robot_id")
        if type(self.camera) is not SensorIdentity or self.camera.kind is not SensorKind.RGB_CAMERA:
            _fail("physical CameraInfo camera identity is invalid")
        _frame(self.frame_id, "physical CameraInfo frame")
        if (
            type(self.observed_at_ns) is not int
            or not 1 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS
        ):
            _fail("physical CameraInfo acquisition time is invalid")
        if type(self.calibration) is not PhysicalCameraCalibration:
            _fail("physical CameraInfo requires validated calibration")
        if type(self.provenance) is not ObservationProvenance:
            _fail("physical CameraInfo provenance is required")


@dataclass(frozen=True, slots=True)
class PhysicalCameraDiagnostics:
    source_id: str
    session_id: str | None
    lifecycle_state: PhysicalCameraLifecycleState
    calibration_state: PhysicalCameraCalibrationState
    event: PhysicalCameraDiagnosticEvent
    availability: SensorAvailability
    source_available: bool
    acquisition_active: bool
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    evicted_count: int
    pending_image_count: int
    pending_camera_info_count: int
    observed_frequency_millihz: int | None
    dropped_frame_count: int | None
    observed_at_ns: int

    def __post_init__(self) -> None:
        _identifier(self.source_id, "physical diagnostics source_id")
        if self.session_id is not None and _SESSION_ID.fullmatch(self.session_id) is None:
            _fail("physical diagnostics session identity is malformed")
        if not isinstance(self.lifecycle_state, PhysicalCameraLifecycleState):
            _fail("physical diagnostics lifecycle state is invalid")
        if not isinstance(self.calibration_state, PhysicalCameraCalibrationState):
            _fail("physical diagnostics calibration state is invalid")
        if not isinstance(self.event, PhysicalCameraDiagnosticEvent):
            _fail("physical diagnostics event is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _fail("physical diagnostics availability is invalid")
        counts = (
            self.accepted_count,
            self.rejected_count,
            self.duplicate_count,
            self.evicted_count,
            self.pending_image_count,
            self.pending_camera_info_count,
        )
        if any(type(value) is not int or not 0 <= value <= MAX_PHYSICAL_CAMERA_COUNT for value in counts):
            _fail("physical diagnostics counters are invalid")
        if self.pending_image_count > MAX_PHYSICAL_CAMERA_PENDING_PAIRS or self.pending_camera_info_count > MAX_PHYSICAL_CAMERA_PENDING_PAIRS:
            _fail("physical diagnostics pending counts exceed their hard bound")
        if self.observed_frequency_millihz is not None and (
            type(self.observed_frequency_millihz) is not int
            or not 0 <= self.observed_frequency_millihz <= 1_000_000_000
        ):
            _fail("physical diagnostics observed frequency is invalid")
        if self.dropped_frame_count is not None and (
            type(self.dropped_frame_count) is not int or self.dropped_frame_count < 0
        ):
            _fail("physical diagnostics dropped-frame count is invalid")
        if type(self.observed_at_ns) is not int or not 0 <= self.observed_at_ns <= MAX_OBSERVATION_TIME_NS:
            _fail("physical diagnostics source time is invalid")

    def evidence_detail(self) -> str:
        session = "unknown" if self.session_id is None else self.session_id
        value = (
            f"physical_camera:{self.event.value}:lifecycle={self.lifecycle_state.value}:"
            f"calibration={self.calibration_state.value}:session={session}:"
            f"accepted={self.accepted_count}:rejected={self.rejected_count}"
        )
        if len(value) > MAX_PHYSICAL_CAMERA_DETAIL_LENGTH:
            _fail("physical diagnostics detail exceeds its bound")
        return value


_ADMISSION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class PhysicalCameraAdmission:
    """One sealed physical frame and compact health fact issued by the adapter."""

    frame: VisualFrameObservation
    health: SensorHealthObservation
    requirement: PhysicalCameraTrustRequirement
    session_id: str
    diagnostics: PhysicalCameraDiagnostics

    def __init__(
        self,
        *,
        frame: VisualFrameObservation,
        health: SensorHealthObservation,
        requirement: PhysicalCameraTrustRequirement,
        session_id: str,
        diagnostics: PhysicalCameraDiagnostics,
        _seal: object,
    ) -> None:
        if _seal is not _ADMISSION_SEAL:
            raise PhysicalCameraConfigurationError(
                "physical camera admissions can only be issued by the lifecycle adapter"
            )
        rebuilt_frame = rebuild_observation(frame)
        rebuilt_health = rebuild_observation(health)
        if type(rebuilt_frame) is not VisualFrameObservation:
            _fail("physical admission frame is invalid")
        if type(rebuilt_health) is not SensorHealthObservation:
            _fail("physical admission health evidence is invalid")
        if type(requirement) is not PhysicalCameraTrustRequirement:
            _fail("physical admission requirement is invalid")
        if _SESSION_ID.fullmatch(session_id) is None or diagnostics.session_id != session_id:
            _fail("physical admission session identity is invalid")
        if (
            not requirement.matches_unsealed(rebuilt_frame)
            or rebuilt_health.sensor != rebuilt_frame.sensor
            or rebuilt_health.provenance != rebuilt_frame.provenance
            or rebuilt_health.observed_at_ns != rebuilt_frame.observed_at_ns
        ):
            _fail("physical admission evidence does not match its exact requirement")
        object.__setattr__(self, "frame", rebuilt_frame)
        object.__setattr__(self, "health", rebuilt_health)
        object.__setattr__(self, "requirement", requirement)
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "diagnostics", diagnostics)


def _issue_admission(
    *,
    frame: VisualFrameObservation,
    health: SensorHealthObservation,
    requirement: PhysicalCameraTrustRequirement,
    session_id: str,
    diagnostics: PhysicalCameraDiagnostics,
) -> PhysicalCameraAdmission:
    return PhysicalCameraAdmission(
        frame=frame,
        health=health,
        requirement=requirement,
        session_id=session_id,
        diagnostics=diagnostics,
        _seal=_ADMISSION_SEAL,
    )


def physical_camera_session_id(manifest_id: str, epoch: int) -> str:
    if _SOURCE_MANIFEST_ID.fullmatch(manifest_id) is None:
        _fail("physical camera session manifest identity is invalid")
    if type(epoch) is not int or not 1 <= epoch <= MAX_PHYSICAL_CAMERA_COUNT:
        _fail("physical camera session epoch is invalid")
    digest = _canonical_sha256(
        {
            "epoch": epoch,
            "manifest_id": manifest_id,
            "schema": "ayyo.physical-camera-session.v1",
        }
    )
    return f"physical-camera-session-sha256-{digest}"
