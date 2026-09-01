"""Immutable source, format, diagnostic, and sealed audio contracts."""

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
    AudioFrameObservation,
    MAX_AUDIO_DATA_BYTES,
    MAX_AUDIO_FRAME_COUNT,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorHealthObservation,
    SensorIdentity,
    SensorKind,
    rebuild_observation,
)

from .errors import HeadAudioConfigurationError, HeadAudioValidationError


AUDIO_TOPIC = "/ayyo/audio/head/microphone/raw"
AUDIO_INTERFACE = "ayyo-interfaces.audio-frame.v1"
MAX_AUDIO_SOURCES = 16
MAX_AUDIO_COUNT = (1 << 63) - 1
PCM_S16LE = "pcm_s16le"
TEST_SAMPLE_RATE_HZ = 16_000
TEST_CHANNEL_COUNT = 1
TEST_FRAME_COUNT = 160

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_FRAME = re.compile(r"^[A-Za-z][A-Za-z0-9_/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_ID = re.compile(r"^audio-source-sha256-[0-9a-f]{64}$")
_SESSION_ID = re.compile(r"^audio-session-sha256-[0-9a-f]{64}$")


def _fail(detail: str) -> None:
    raise HeadAudioValidationError(detail)


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
        _fail(f"{field_name} must be one bounded canonical frame")
    return value


def _digest(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _canonical_sha256(document: dict[str, object]) -> str:
    encoded = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return sha256(encoded).hexdigest()


class AudioSourceClassification(StrEnum):
    TEST_FIXTURE = "test_fixture"
    SIMULATION = "simulation"
    RECORDED_FIXTURE = "recorded_fixture"
    PROJECT_REVIEWED_DEVICE = "project_reviewed_device"


class AudioLifecycleState(StrEnum):
    UNCONFIGURED = "unconfigured"
    INACTIVE = "inactive"
    ACTIVE = "active"
    FINALIZED = "finalized"


class AudioDiagnosticEvent(StrEnum):
    UNCONFIGURED = "unconfigured"
    CONFIGURED = "configured"
    CAPTURE_ACTIVE = "capture_active"
    FRAME_ACCEPTED = "frame_accepted"
    LIFECYCLE_INACTIVE = "lifecycle_inactive"
    SESSION_MISMATCH = "session_mismatch"
    WRONG_SOURCE = "wrong_source"
    WRONG_FRAME = "wrong_frame"
    WRONG_FORMAT = "wrong_format"
    FUTURE_FRAME = "future_frame"
    STALE_FRAME = "stale_frame"
    SOURCE_CLOCK_REGRESSION = "source_clock_regression"
    DUPLICATE_FRAME = "duplicate_frame"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True, init=False)
class AudioSourceManifest:
    source_id: str
    robot_id: str
    microphone: SensorIdentity
    producer_id: str
    producer_version: str
    producer_implementation_sha256: str
    provenance: ObservationProvenance
    classification: AudioSourceClassification
    mount_frame_id: str
    sample_rate_hz: int
    channel_count: int
    encoding: str
    maximum_frame_count: int
    maximum_duration_ns: int
    maximum_payload_bytes: int
    topic: str
    device_serial: str | None
    device_fingerprint_sha256: str | None
    manifest_id: str

    def __init__(
        self,
        *,
        source_id: str,
        robot_id: str,
        microphone: SensorIdentity,
        producer_id: str,
        producer_version: str,
        producer_implementation_sha256: str,
        provenance: ObservationProvenance,
        classification: AudioSourceClassification,
        mount_frame_id: str,
        sample_rate_hz: int,
        channel_count: int,
        encoding: str,
        maximum_frame_count: int,
        maximum_duration_ns: int,
        maximum_payload_bytes: int,
        topic: str = AUDIO_TOPIC,
        device_serial: str | None = None,
        device_fingerprint_sha256: str | None = None,
        manifest_id: str | None = None,
    ) -> None:
        _identifier(source_id, "audio source_id")
        _identifier(robot_id, "audio robot_id")
        if robot_id != AYYO_ROBOT_ID:
            _fail("audio source must bind canonical Ayyo")
        if (
            type(microphone) is not SensorIdentity
            or microphone.kind is not SensorKind.MICROPHONE
        ):
            _fail("audio source requires one typed microphone")
        _identifier(producer_id, "audio producer_id")
        _identifier(producer_version, "audio producer version")
        _digest(producer_implementation_sha256, "audio producer implementation")
        if type(provenance) is not ObservationProvenance:
            _fail("audio source provenance must be typed")
        if provenance.source_id != source_id or provenance.interface != AUDIO_INTERFACE:
            _fail("audio provenance must bind the exact source and interface")
        if not isinstance(classification, AudioSourceClassification):
            _fail("audio source classification must be typed")
        expected_kind = {
            AudioSourceClassification.TEST_FIXTURE: ObservationSourceKind.TEST_FIXTURE,
            AudioSourceClassification.SIMULATION: ObservationSourceKind.SIMULATION,
            AudioSourceClassification.RECORDED_FIXTURE: ObservationSourceKind.RECORDED_DATA,
            AudioSourceClassification.PROJECT_REVIEWED_DEVICE: (
                ObservationSourceKind.PHYSICAL_SENSOR
            ),
        }[classification]
        if provenance.source_kind is not expected_kind:
            _fail("audio source classification and provenance cannot substitute")
        expected_transport = (
            ObservationTransport.RECORDED
            if classification is AudioSourceClassification.RECORDED_FIXTURE
            else ObservationTransport.ROS2
        )
        if provenance.transport is not expected_transport:
            _fail("audio source classification and transport cannot substitute")
        mount = _frame(mount_frame_id, "audio mount frame")
        if mount != microphone.frame_id:
            _fail("audio mount frame conflicts with microphone identity")
        if sample_rate_hz != TEST_SAMPLE_RATE_HZ:
            _fail("audio v1 supports only the reviewed 16 kHz format")
        if channel_count != TEST_CHANNEL_COUNT or encoding != PCM_S16LE:
            _fail("audio v1 supports only mono pcm_s16le")
        if (
            type(maximum_frame_count) is not int
            or not 1 <= maximum_frame_count <= MAX_AUDIO_FRAME_COUNT
            or type(maximum_duration_ns) is not int
            or not 1 <= maximum_duration_ns <= 1_000_000_000
            or type(maximum_payload_bytes) is not int
            or not 1 <= maximum_payload_bytes <= MAX_AUDIO_DATA_BYTES
            or maximum_payload_bytes != maximum_frame_count * channel_count * 2
            or maximum_duration_ns
            != maximum_frame_count * 1_000_000_000 // sample_rate_hz
        ):
            _fail("audio source resource bounds are inconsistent")
        if topic != AUDIO_TOPIC:
            _fail("audio topic must equal the reviewed canonical interface")
        if device_serial is not None:
            if (
                type(device_serial) is not str
                or not device_serial
                or len(device_serial) > 128
                or re.fullmatch(r"[A-Za-z0-9._:-]+", device_serial) is None
            ):
                _fail("audio device serial is malformed")
        if device_fingerprint_sha256 is not None:
            _digest(device_fingerprint_sha256, "audio device fingerprint")
        if classification is not AudioSourceClassification.PROJECT_REVIEWED_DEVICE and (
            device_serial is not None or device_fingerprint_sha256 is not None
        ):
            _fail("non-physical audio profiles cannot claim device identity")
        document: dict[str, object] = {
            "channel_count": channel_count,
            "classification": classification.value,
            "device_fingerprint_sha256": device_fingerprint_sha256,
            "device_serial": device_serial,
            "encoding": encoding,
            "maximum_duration_ns": maximum_duration_ns,
            "maximum_frame_count": maximum_frame_count,
            "maximum_payload_bytes": maximum_payload_bytes,
            "microphone": microphone.document(),
            "mount_frame_id": mount,
            "producer_id": producer_id,
            "producer_implementation_sha256": producer_implementation_sha256,
            "producer_version": producer_version,
            "provenance": provenance.document(),
            "robot_id": robot_id,
            "sample_rate_hz": sample_rate_hz,
            "schema": "ayyo.audio-source.v1",
            "source_id": source_id,
            "topic": topic,
        }
        derived = f"audio-source-sha256-{_canonical_sha256(document)}"
        if manifest_id is not None and manifest_id != derived:
            _fail("audio source manifest identity does not match its content")
        for field_name, value in (
            ("source_id", source_id),
            ("robot_id", robot_id),
            ("microphone", microphone),
            ("producer_id", producer_id),
            ("producer_version", producer_version),
            ("producer_implementation_sha256", producer_implementation_sha256),
            ("provenance", provenance),
            ("classification", classification),
            ("mount_frame_id", mount),
            ("sample_rate_hz", sample_rate_hz),
            ("channel_count", channel_count),
            ("encoding", encoding),
            ("maximum_frame_count", maximum_frame_count),
            ("maximum_duration_ns", maximum_duration_ns),
            ("maximum_payload_bytes", maximum_payload_bytes),
            ("topic", topic),
            ("device_serial", device_serial),
            ("device_fingerprint_sha256", device_fingerprint_sha256),
            ("manifest_id", derived),
        ):
            object.__setattr__(self, field_name, value)

    def requirement(self) -> AudioTrustRequirement:
        return AudioTrustRequirement(
            source_id=self.source_id,
            robot_id=self.robot_id,
            microphone=self.microphone,
            producer_id=self.producer_id,
            producer_implementation_sha256=self.producer_implementation_sha256,
            provenance=self.provenance,
            source_manifest_id=self.manifest_id,
            sample_rate_hz=self.sample_rate_hz,
            channel_count=self.channel_count,
            encoding=self.encoding,
            maximum_frame_count=self.maximum_frame_count,
            maximum_payload_bytes=self.maximum_payload_bytes,
        )


@dataclass(frozen=True, slots=True)
class AudioTrustRequirement:
    source_id: str
    robot_id: str
    microphone: SensorIdentity
    producer_id: str
    producer_implementation_sha256: str
    provenance: ObservationProvenance
    source_manifest_id: str
    sample_rate_hz: int
    channel_count: int
    encoding: str
    maximum_frame_count: int
    maximum_payload_bytes: int

    def __post_init__(self) -> None:
        _identifier(self.source_id, "audio requirement source")
        _identifier(self.robot_id, "audio requirement robot")
        if (
            type(self.microphone) is not SensorIdentity
            or self.microphone.kind is not SensorKind.MICROPHONE
            or type(self.provenance) is not ObservationProvenance
            or self.provenance.source_id != self.source_id
        ):
            _fail("audio requirement source identity is invalid")
        _identifier(self.producer_id, "audio requirement producer")
        _digest(
            self.producer_implementation_sha256,
            "audio requirement implementation",
        )
        if _MANIFEST_ID.fullmatch(self.source_manifest_id) is None:
            _fail("audio requirement manifest identity is malformed")
        if (
            self.sample_rate_hz != TEST_SAMPLE_RATE_HZ
            or self.channel_count != TEST_CHANNEL_COUNT
            or self.encoding != PCM_S16LE
            or not 1 <= self.maximum_frame_count <= MAX_AUDIO_FRAME_COUNT
            or self.maximum_payload_bytes
            != self.maximum_frame_count * self.channel_count * 2
        ):
            _fail("audio requirement format or bounds are invalid")

    def matches_unsealed(self, frame: AudioFrameObservation) -> bool:
        return (
            type(frame) is AudioFrameObservation
            and frame.robot_id == self.robot_id
            and frame.sensor == self.microphone
            and frame.producer_id == self.producer_id
            and frame.source_manifest_id == self.source_manifest_id
            and frame.sample_rate_hz == self.sample_rate_hz
            and frame.channel_count == self.channel_count
            and frame.encoding == self.encoding
            and frame.frame_count <= self.maximum_frame_count
            and frame.data_size_bytes <= self.maximum_payload_bytes
            and frame.provenance == self.provenance
        )

    def matches(self, admission: AudioCaptureAdmission) -> bool:
        return (
            type(admission) is AudioCaptureAdmission
            and admission.requirement == self
            and self.matches_unsealed(admission.frame)
        )


@dataclass(frozen=True, slots=True)
class AudioDiagnostics:
    source_id: str
    session_id: str | None
    lifecycle_state: AudioLifecycleState
    event: AudioDiagnosticEvent
    sample_rate_hz: int | None
    channel_count: int | None
    encoding: str | None
    availability: SensorAvailability
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    dropped_count: int
    error_count: int
    retained_payload_bytes: int
    observed_at_ns: int

    def __post_init__(self) -> None:
        _identifier(self.source_id, "audio diagnostics source")
        if self.session_id is not None and _SESSION_ID.fullmatch(self.session_id) is None:
            _fail("audio diagnostics session is malformed")
        if not isinstance(self.lifecycle_state, AudioLifecycleState) or not isinstance(
            self.event, AudioDiagnosticEvent
        ):
            _fail("audio diagnostics lifecycle/event is invalid")
        if self.sample_rate_hz is not None and self.sample_rate_hz != TEST_SAMPLE_RATE_HZ:
            _fail("audio diagnostics sample rate is invalid")
        if self.channel_count is not None and self.channel_count != TEST_CHANNEL_COUNT:
            _fail("audio diagnostics channel count is invalid")
        if self.encoding is not None and self.encoding != PCM_S16LE:
            _fail("audio diagnostics encoding is invalid")
        if not isinstance(self.availability, SensorAvailability):
            _fail("audio diagnostics availability is invalid")
        counters = (
            self.accepted_count,
            self.rejected_count,
            self.duplicate_count,
            self.dropped_count,
            self.error_count,
            self.retained_payload_bytes,
            self.observed_at_ns,
        )
        if any(type(value) is not int or not 0 <= value <= MAX_AUDIO_COUNT for value in counters):
            _fail("audio diagnostics counters are invalid")
        if self.retained_payload_bytes != 0:
            _fail("audio diagnostics cannot report retained raw payload")


_ADMISSION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class AudioCaptureAdmission:
    frame: AudioFrameObservation
    health: SensorHealthObservation
    requirement: AudioTrustRequirement
    diagnostics: AudioDiagnostics

    def __init__(
        self,
        *,
        frame: AudioFrameObservation,
        health: SensorHealthObservation,
        requirement: AudioTrustRequirement,
        diagnostics: AudioDiagnostics,
        _seal: object,
    ) -> None:
        if _seal is not _ADMISSION_SEAL:
            _fail("audio admissions may only be issued by the lifecycle adapter")
        rebuilt_frame = rebuild_observation(frame)
        rebuilt_health = rebuild_observation(health)
        if (
            type(rebuilt_frame) is not AudioFrameObservation
            or type(rebuilt_health) is not SensorHealthObservation
            or type(requirement) is not AudioTrustRequirement
            or type(diagnostics) is not AudioDiagnostics
            or not requirement.matches_unsealed(rebuilt_frame)
            or rebuilt_health.robot_id != rebuilt_frame.robot_id
            or rebuilt_health.sensor != rebuilt_frame.sensor
            or rebuilt_health.provenance != rebuilt_frame.provenance
            or rebuilt_health.observed_at_ns != rebuilt_frame.observed_at_ns
        ):
            _fail("sealed audio admission fields do not agree")
        object.__setattr__(self, "frame", rebuilt_frame)
        object.__setattr__(self, "health", rebuilt_health)
        object.__setattr__(self, "requirement", requirement)
        object.__setattr__(self, "diagnostics", diagnostics)


def _issue_admission(**values) -> AudioCaptureAdmission:
    return AudioCaptureAdmission(_seal=_ADMISSION_SEAL, **values)


def audio_session_id(manifest_id: str, epoch: int) -> str:
    if type(manifest_id) is not str or _MANIFEST_ID.fullmatch(manifest_id) is None:
        raise HeadAudioConfigurationError("audio session requires a manifest identity")
    if type(epoch) is not int or not 1 <= epoch <= MAX_AUDIO_COUNT:
        raise HeadAudioConfigurationError("audio session epoch is invalid")
    digest = sha256(f"{manifest_id}|{epoch}".encode("ascii")).hexdigest()
    return f"audio-session-sha256-{digest}"


def summarize_audio_payload(
    *,
    source: AudioSourceManifest,
    session_id: str,
    observed_at_ns: int,
    result_at_ns: int,
    frame_count: int,
    data: bytes,
    frame_id: str | None = None,
    source_id: str | None = None,
    producer_id: str | None = None,
    microphone: SensorIdentity | None = None,
    sample_rate_hz: int | None = None,
    channel_count: int | None = None,
    encoding: str | None = None,
    provenance: ObservationProvenance | None = None,
    source_manifest_id: str | None = None,
    claimed_payload_sha256: str | None = None,
) -> AudioFrameObservation:
    """Validate and compact one bounded PCM payload without retaining bytes."""
    if type(source) is not AudioSourceManifest:
        _fail("audio summarization requires one typed source manifest")
    if type(data) is not bytes or not data:
        _fail("audio payload must be nonempty immutable bytes")
    if len(data) > source.maximum_payload_bytes or len(data) > MAX_AUDIO_DATA_BYTES:
        _fail("audio payload exceeds its reviewed hard bound")
    selected_rate = source.sample_rate_hz if sample_rate_hz is None else sample_rate_hz
    selected_channels = source.channel_count if channel_count is None else channel_count
    selected_encoding = source.encoding if encoding is None else encoding
    if selected_encoding != source.encoding or len(data) % 2 != 0:
        _fail("audio payload encoding or byte alignment is unsupported")
    if (
        type(frame_count) is not int
        or not 1 <= frame_count <= source.maximum_frame_count
    ):
        _fail("audio frame count is outside its reviewed hard bound")
    if selected_rate != source.sample_rate_hz:
        _fail("audio payload sample rate conflicts with its source manifest")
    if selected_channels != source.channel_count:
        _fail("audio payload channel count conflicts with its source manifest")
    sample_count = len(data) // 2
    if frame_count * selected_channels != sample_count:
        _fail("audio frame/sample count conflicts with payload length")
    values = tuple(value[0] for value in struct.iter_unpack("<h", data))
    if len(values) != sample_count:
        _fail("audio sample decoding was inconsistent")
    peak = max(abs(value) for value in values)
    rms = math.sqrt(
        sum((value / 32_768.0) ** 2 for value in values) / sample_count
    )
    if not math.isfinite(rms):
        _fail("audio RMS summary is not finite")
    digest = sha256(data).hexdigest()
    if claimed_payload_sha256 is not None and claimed_payload_sha256 != digest:
        _fail("audio payload fingerprint does not match its bytes")
    selected_frame = source.mount_frame_id if frame_id is None else frame_id
    if selected_frame != source.mount_frame_id:
        _fail("audio payload frame conflicts with its source manifest")
    selected_source_id = source.source_id if source_id is None else source_id
    if selected_source_id != source.source_id:
        _fail("audio payload source identity conflicts with its manifest")
    return AudioFrameObservation(
        robot_id=source.robot_id,
        sensor=source.microphone if microphone is None else microphone,
        producer_id=source.producer_id if producer_id is None else producer_id,
        source_manifest_id=(
            source.manifest_id
            if source_manifest_id is None
            else source_manifest_id
        ),
        session_id=session_id,
        sample_rate_hz=selected_rate,
        channel_count=selected_channels,
        encoding=selected_encoding,
        frame_count=frame_count,
        sample_count=sample_count,
        duration_ns=frame_count * 1_000_000_000 // selected_rate,
        data_size_bytes=len(data),
        peak_amplitude=peak,
        rms_amplitude=rms,
        payload_sha256=digest,
        observed_at_ns=observed_at_ns,
        result_at_ns=result_at_ns,
        provenance=source.provenance if provenance is None else provenance,
        availability=SensorAvailability.AVAILABLE,
    )
