"""Immutable exact-time RGB-D policy, admission, and diagnostics contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import re

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    DepthFrameObservation,
    FusedRgbdObservation,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
    rebuild_observation,
)

from .errors import RgbdFusionConfigurationError


MAX_RGBD_PENDING_PER_STREAM = 8
MAX_RGBD_COUNT = (1 << 63) - 1
RGBD_PAIRING_POLICY_ID = "ayyo.rgbd.exact-source-time.v1"
RGBD_PAIRING_POLICY_VERSION = "1.0.0"
RGBD_INTERFACE = "ayyo.compact-fused-rgbd.v1"
HEAD_RGBD_FUSION_SENSOR = SensorIdentity(
    "ayyo.camera.head.rgbd.fusion.v1",
    SensorKind.RGBD_FUSION,
    "head_camera_frame",
)
RGBD_TEST_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "ayyo.rgbd.head.test-synchronizer.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    RGBD_INTERFACE,
)

_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_FRAME = re.compile(r"^[A-Za-z][A-Za-z0-9_/-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CALIBRATION_ID = re.compile(r"^camera-calibration-sha256-[0-9a-f]{64}$")


def _fail(detail: str) -> None:
    raise RgbdFusionConfigurationError(detail)


def _identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 256
        or _IDENTIFIER.fullmatch(value) is None
    ):
        _fail(f"{field_name} must be one bounded canonical identifier")
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
        _fail(f"{field_name} must be one canonical SHA-256 digest")
    return value


def _canonical_sha256(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return sha256(encoded).hexdigest()


class RgbdFusionLifecycleState(StrEnum):
    UNCONFIGURED = "unconfigured"
    INACTIVE = "inactive"
    ACTIVE = "active"
    FINALIZED = "finalized"


class RgbdFusionEvent(StrEnum):
    UNCONFIGURED = "unconfigured"
    CONFIGURED = "configured"
    ACTIVE = "active"
    PAIR_ACCEPTED = "pair_accepted"
    MISSING_COUNTERPART = "missing_counterpart"
    WRONG_COMPONENT = "wrong_component"
    SESSION_MISMATCH = "session_mismatch"
    TIMESTAMP_MISMATCH = "timestamp_mismatch"
    FUTURE_EVIDENCE = "future_evidence"
    STALE_EVIDENCE = "stale_evidence"
    REGRESSED_EVIDENCE = "regressed_evidence"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    PENDING_EVICTED = "pending_evicted"
    INACTIVE = "inactive"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True, init=False)
class RgbdFusionRequirement:
    """Exact reviewed source, producer, frame, and calibration relationship."""

    robot_id: str
    fusion_sensor: SensorIdentity
    rgb_sensor: SensorIdentity
    depth_sensor: SensorIdentity
    rgb_provenance: ObservationProvenance
    depth_provenance: ObservationProvenance
    fusion_provenance: ObservationProvenance
    rgb_producer_id: str
    depth_producer_id: str
    rgb_producer_implementation_sha256: str
    depth_producer_implementation_sha256: str
    rgb_source_fingerprint_sha256: str
    depth_source_fingerprint_sha256: str
    rgb_camera_frame_id: str
    depth_camera_frame_id: str
    rgb_calibration_id: str
    depth_calibration_id: str
    pairing_policy_id: str
    pairing_policy_version: str
    requirement_id: str

    def __init__(
        self,
        *,
        robot_id: str,
        fusion_sensor: SensorIdentity,
        rgb_sensor: SensorIdentity,
        depth_sensor: SensorIdentity,
        rgb_provenance: ObservationProvenance,
        depth_provenance: ObservationProvenance,
        fusion_provenance: ObservationProvenance,
        rgb_producer_id: str,
        depth_producer_id: str,
        rgb_producer_implementation_sha256: str,
        depth_producer_implementation_sha256: str,
        rgb_source_fingerprint_sha256: str,
        depth_source_fingerprint_sha256: str,
        rgb_camera_frame_id: str,
        depth_camera_frame_id: str,
        rgb_calibration_id: str,
        depth_calibration_id: str,
        pairing_policy_id: str = RGBD_PAIRING_POLICY_ID,
        pairing_policy_version: str = RGBD_PAIRING_POLICY_VERSION,
        requirement_id: str | None = None,
    ) -> None:
        _identifier(robot_id, "RGB-D robot identity")
        if robot_id != AYYO_ROBOT_ID:
            _fail("RGB-D v1 must bind canonical Ayyo")
        if (
            type(fusion_sensor) is not SensorIdentity
            or fusion_sensor.kind is not SensorKind.RGBD_FUSION
            or type(rgb_sensor) is not SensorIdentity
            or rgb_sensor.kind is not SensorKind.RGB_CAMERA
            or type(depth_sensor) is not SensorIdentity
            or depth_sensor.kind is not SensorKind.DEPTH_CAMERA
        ):
            _fail("RGB-D requirement sensor identities are invalid")
        provenances = (rgb_provenance, depth_provenance, fusion_provenance)
        if any(type(item) is not ObservationProvenance for item in provenances):
            _fail("RGB-D requirement provenance must be typed")
        if not (
            rgb_provenance.clock
            is depth_provenance.clock
            is fusion_provenance.clock
        ):
            _fail("RGB-D sources must share one explicit acquisition clock")
        _identifier(rgb_producer_id, "RGB producer identity")
        _identifier(depth_producer_id, "depth producer identity")
        _digest(rgb_producer_implementation_sha256, "RGB producer implementation")
        _digest(depth_producer_implementation_sha256, "depth producer implementation")
        _digest(rgb_source_fingerprint_sha256, "RGB source fingerprint")
        _digest(depth_source_fingerprint_sha256, "depth source fingerprint")
        rgb_mount = _frame(rgb_camera_frame_id, "RGB camera frame")
        depth_mount = _frame(depth_camera_frame_id, "depth camera frame")
        if rgb_mount == rgb_sensor.frame_id or depth_mount == depth_sensor.frame_id:
            _fail("RGB-D mount and optical frame identities must remain distinct")
        if (
            type(rgb_calibration_id) is not str
            or _CALIBRATION_ID.fullmatch(rgb_calibration_id) is None
            or type(depth_calibration_id) is not str
            or _CALIBRATION_ID.fullmatch(depth_calibration_id) is None
        ):
            _fail("RGB-D calibration identities are malformed")
        _identifier(pairing_policy_id, "RGB-D pairing policy")
        _identifier(pairing_policy_version, "RGB-D pairing policy version")
        document: dict[str, object] = {
            "depth_calibration_id": depth_calibration_id,
            "depth_camera_frame_id": depth_mount,
            "depth_producer_id": depth_producer_id,
            "depth_producer_implementation_sha256": depth_producer_implementation_sha256,
            "depth_provenance": depth_provenance.document(),
            "depth_sensor": depth_sensor.document(),
            "depth_source_fingerprint_sha256": depth_source_fingerprint_sha256,
            "fusion_provenance": fusion_provenance.document(),
            "fusion_sensor": fusion_sensor.document(),
            "pairing_policy_id": pairing_policy_id,
            "pairing_policy_version": pairing_policy_version,
            "rgb_calibration_id": rgb_calibration_id,
            "rgb_camera_frame_id": rgb_mount,
            "rgb_producer_id": rgb_producer_id,
            "rgb_producer_implementation_sha256": rgb_producer_implementation_sha256,
            "rgb_provenance": rgb_provenance.document(),
            "rgb_sensor": rgb_sensor.document(),
            "rgb_source_fingerprint_sha256": rgb_source_fingerprint_sha256,
            "robot_id": robot_id,
            "schema": "ayyo.rgbd-fusion-requirement.v1",
        }
        derived = f"rgbd-requirement-sha256-{_canonical_sha256(document)}"
        if requirement_id is not None and requirement_id != derived:
            _fail("RGB-D requirement identity does not match its content")
        for field_name, value in (
            ("robot_id", robot_id),
            ("fusion_sensor", fusion_sensor),
            ("rgb_sensor", rgb_sensor),
            ("depth_sensor", depth_sensor),
            ("rgb_provenance", rgb_provenance),
            ("depth_provenance", depth_provenance),
            ("fusion_provenance", fusion_provenance),
            ("rgb_producer_id", rgb_producer_id),
            ("depth_producer_id", depth_producer_id),
            ("rgb_producer_implementation_sha256", rgb_producer_implementation_sha256),
            ("depth_producer_implementation_sha256", depth_producer_implementation_sha256),
            ("rgb_source_fingerprint_sha256", rgb_source_fingerprint_sha256),
            ("depth_source_fingerprint_sha256", depth_source_fingerprint_sha256),
            ("rgb_camera_frame_id", rgb_mount),
            ("depth_camera_frame_id", depth_mount),
            ("rgb_calibration_id", rgb_calibration_id),
            ("depth_calibration_id", depth_calibration_id),
            ("pairing_policy_id", pairing_policy_id),
            ("pairing_policy_version", pairing_policy_version),
            ("requirement_id", derived),
        ):
            object.__setattr__(self, field_name, value)

    def matches_rgb(self, frame: VisualFrameObservation) -> bool:
        return (
            type(frame) is VisualFrameObservation
            and frame.robot_id == self.robot_id
            and frame.sensor == self.rgb_sensor
            and frame.provenance == self.rgb_provenance
            and frame.calibration_id == self.rgb_calibration_id
            and frame.availability is SensorAvailability.AVAILABLE
        )

    def matches_depth(self, frame: DepthFrameObservation) -> bool:
        return (
            type(frame) is DepthFrameObservation
            and frame.robot_id == self.robot_id
            and frame.sensor == self.depth_sensor
            and frame.provenance == self.depth_provenance
            and frame.calibration_id == self.depth_calibration_id
            and frame.source_manifest_id
            == f"depth-camera-source-sha256-{self.depth_source_fingerprint_sha256}"
            and frame.availability is SensorAvailability.AVAILABLE
        )

    def matches_fused(self, observation: FusedRgbdObservation) -> bool:
        return (
            type(observation) is FusedRgbdObservation
            and observation.robot_id == self.robot_id
            and observation.sensor == self.fusion_sensor
            and observation.rgb_observation.sensor == self.rgb_sensor
            and observation.depth_observation.sensor == self.depth_sensor
            and observation.rgb_observation.provenance == self.rgb_provenance
            and observation.depth_observation.provenance == self.depth_provenance
            and observation.provenance == self.fusion_provenance
            and observation.rgb_producer_id == self.rgb_producer_id
            and observation.depth_producer_id == self.depth_producer_id
            and observation.rgb_source_fingerprint_sha256
            == self.rgb_source_fingerprint_sha256
            and observation.depth_source_fingerprint_sha256
            == self.depth_source_fingerprint_sha256
            and observation.rgb_camera_frame_id == self.rgb_camera_frame_id
            and observation.depth_camera_frame_id == self.depth_camera_frame_id
            and observation.rgb_observation.calibration_id
            == self.rgb_calibration_id
            and observation.depth_observation.calibration_id
            == self.depth_calibration_id
            and observation.pairing_policy_id == self.pairing_policy_id
            and observation.pairing_policy_version
            == self.pairing_policy_version
        )


@dataclass(frozen=True, slots=True)
class RgbdFusionDiagnostics:
    lifecycle_state: RgbdFusionLifecycleState
    event: RgbdFusionEvent
    synchronization_session_id: str | None
    rgb_session_id: str | None
    depth_session_id: str | None
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    evicted_count: int
    pending_rgb_count: int
    pending_depth_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle_state, RgbdFusionLifecycleState):
            _fail("RGB-D diagnostics lifecycle is invalid")
        if not isinstance(self.event, RgbdFusionEvent):
            _fail("RGB-D diagnostics event is invalid")
        for value in (
            self.accepted_count,
            self.rejected_count,
            self.duplicate_count,
            self.evicted_count,
            self.pending_rgb_count,
            self.pending_depth_count,
        ):
            if type(value) is not int or not 0 <= value <= MAX_RGBD_COUNT:
                _fail("RGB-D diagnostics counts are invalid")
        if (
            self.pending_rgb_count > MAX_RGBD_PENDING_PER_STREAM
            or self.pending_depth_count > MAX_RGBD_PENDING_PER_STREAM
        ):
            _fail("RGB-D diagnostics pending state exceeds its hard bound")


_ADMISSION_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class RgbdFusionAdmission:
    observation: FusedRgbdObservation
    requirement: RgbdFusionRequirement
    diagnostics: RgbdFusionDiagnostics

    def __init__(
        self,
        *,
        observation: FusedRgbdObservation,
        requirement: RgbdFusionRequirement,
        diagnostics: RgbdFusionDiagnostics,
        _seal: object,
    ) -> None:
        if _seal is not _ADMISSION_SEAL:
            _fail("RGB-D admissions may only be issued by the lifecycle synchronizer")
        rebuilt = rebuild_observation(observation)
        if type(rebuilt) is not FusedRgbdObservation:
            _fail("RGB-D admission observation is invalid")
        if type(requirement) is not RgbdFusionRequirement:
            _fail("RGB-D admission requirement is invalid")
        if rebuilt.sensor != requirement.fusion_sensor:
            _fail("RGB-D admission sensor differs from its requirement")
        object.__setattr__(self, "observation", rebuilt)
        object.__setattr__(self, "requirement", requirement)
        object.__setattr__(self, "diagnostics", diagnostics)


def _issue_admission(
    observation: FusedRgbdObservation,
    requirement: RgbdFusionRequirement,
    diagnostics: RgbdFusionDiagnostics,
) -> RgbdFusionAdmission:
    return RgbdFusionAdmission(
        observation=observation,
        requirement=requirement,
        diagnostics=diagnostics,
        _seal=_ADMISSION_SEAL,
    )


def rgbd_test_requirement(
    *,
    rgb_sensor: SensorIdentity,
    rgb_provenance: ObservationProvenance,
    rgb_calibration_id: str,
    depth_sensor: SensorIdentity,
    depth_provenance: ObservationProvenance,
    depth_calibration_id: str,
    depth_producer_id: str,
    depth_producer_implementation_sha256: str,
    depth_source_fingerprint_sha256: str,
) -> RgbdFusionRequirement:
    """Build the reviewed deterministic TEST-only pairing requirement."""
    rgb_source_fingerprint = _canonical_sha256(
        {
            "producer_id": "ayyo.rgbd.rgb-test-adapter.v1",
            "provenance": rgb_provenance.document(),
            "sensor": rgb_sensor.document(),
            "schema": "ayyo.rgbd-rgb-source.v1",
        }
    )
    return RgbdFusionRequirement(
        robot_id=AYYO_ROBOT_ID,
        fusion_sensor=HEAD_RGBD_FUSION_SENSOR,
        rgb_sensor=rgb_sensor,
        depth_sensor=depth_sensor,
        rgb_provenance=rgb_provenance,
        depth_provenance=depth_provenance,
        fusion_provenance=RGBD_TEST_PROVENANCE,
        rgb_producer_id="ayyo.rgbd.rgb-test-adapter.v1",
        depth_producer_id=depth_producer_id,
        rgb_producer_implementation_sha256="b" * 64,
        depth_producer_implementation_sha256=depth_producer_implementation_sha256,
        rgb_source_fingerprint_sha256=rgb_source_fingerprint,
        depth_source_fingerprint_sha256=depth_source_fingerprint_sha256,
        rgb_camera_frame_id="head_camera_frame",
        depth_camera_frame_id="head_depth_camera_frame",
        rgb_calibration_id=rgb_calibration_id,
        depth_calibration_id=depth_calibration_id,
    )
