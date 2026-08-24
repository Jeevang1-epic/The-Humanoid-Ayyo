# Copyright 2026 Ayyo Project Authors

"""Strict fixed-frame localization and reviewed diagnostics normalization."""

from __future__ import annotations

from dataclasses import dataclass
import json

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.duration import Duration
from rclpy.time import Time as RclpyTime
from tf2_ros import (
    ConnectivityException,
    ExtrapolationException,
    InvalidArgumentException,
    LookupException,
    TimeoutException,
)

from ayyo_perception import EvidenceFailureKind
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    BodyPoseObservation,
    CovarianceMatrix,
    ObservationProvenance,
    Pose3D,
    SensorAvailability,
    SensorHealthObservation,
    SensorIdentity,
    SensorKind,
)


LOCALIZATION_REFERENCE_FRAME = 'odom'
LOCALIZATION_BODY_FRAME = 'base_link'
MAX_POSE_LOOKUP_TIMEOUT_NS = 100_000_000
MAX_DIAGNOSTIC_STATUS_COUNT = 16
MAX_DIAGNOSTIC_VALUES = 16
MAX_DIAGNOSTIC_TEXT = 256
MAX_DIAGNOSTIC_DETAIL = 1_024


class LocalizationAdapterError(ValueError):
    """One fixed localization request or result is invalid."""

    def __init__(self, failure: EvidenceFailureKind, detail: str) -> None:
        self.failure = failure
        self.detail = detail
        super().__init__(f'{failure.value}: {detail}')


class DiagnosticAdapterError(ValueError):
    """One reviewed diagnostic array is malformed or conflicting."""


@dataclass(frozen=True, slots=True)
class DiagnosticComponentContract:
    name: str
    hardware_id: str
    sensor: SensorIdentity

    def __post_init__(self) -> None:
        if (
            type(self.name) is not str
            or not self.name
            or self.name != self.name.strip()
            or len(self.name) > MAX_DIAGNOSTIC_TEXT
        ):
            raise DiagnosticAdapterError('diagnostic component name is invalid')
        if self.hardware_id != self.sensor.sensor_id:
            raise DiagnosticAdapterError(
                'diagnostic hardware identity must equal the reviewed sensor identity'
            )


@dataclass(frozen=True, slots=True)
class DiagnosticNormalizationResult:
    observations: tuple[SensorHealthObservation, ...]
    ignored_components: tuple[str, ...]


def _nanoseconds(seconds: object, nanoseconds: object) -> int:
    if (
        type(seconds) is not int
        or type(nanoseconds) is not int
        or seconds < 0
        or not 0 <= nanoseconds < 1_000_000_000
    ):
        raise ValueError('ROS timestamp is outside its canonical range')
    return seconds * 1_000_000_000 + nanoseconds


def _unknown_covariance(values) -> CovarianceMatrix | None:
    covariance = tuple(values)
    if len(covariance) != 36:
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_COVARIANCE,
            'body-pose covariance must contain exactly 36 values',
        )
    if all(value == 0.0 for value in covariance):
        return None
    try:
        return CovarianceMatrix(6, covariance)
    except ValueError as error:
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_COVARIANCE,
            'body-pose covariance is invalid',
        ) from error


def odometry_transform(message: Odometry) -> TransformStamped:
    """Create only the exact reviewed transform carried by standard odometry."""
    if not isinstance(message, Odometry):
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'localization evidence must be nav_msgs/Odometry',
        )
    if (
        message.header.frame_id != LOCALIZATION_REFERENCE_FRAME
        or message.child_frame_id != LOCALIZATION_BODY_FRAME
    ):
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'localization evidence must use exact odom to base_link frames',
        )
    try:
        observed_at_ns = _nanoseconds(
            message.header.stamp.sec,
            message.header.stamp.nanosec,
        )
    except ValueError as error:
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'localization timestamp is malformed',
        ) from error
    if observed_at_ns == 0:
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'zero localization time is reserved by TF2 for latest and is not exact',
        )
    result = TransformStamped()
    result.header = message.header
    result.child_frame_id = message.child_frame_id
    result.transform.translation.x = message.pose.pose.position.x
    result.transform.translation.y = message.pose.pose.position.y
    result.transform.translation.z = message.pose.pose.position.z
    result.transform.rotation = message.pose.pose.orientation
    return result


def exact_lookup(
    buffer,
    *,
    observed_at_ns: int,
    timeout_ns: int,
) -> TransformStamped:
    """Request one exact timestamp; never use TF2's latest-time sentinel."""
    if type(observed_at_ns) is not int or observed_at_ns <= 0:
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'lookup timestamp must be positive exact integer nanoseconds',
        )
    if (
        type(timeout_ns) is not int
        or not 0 <= timeout_ns <= MAX_POSE_LOOKUP_TIMEOUT_NS
    ):
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'lookup timeout exceeds its deterministic bound',
        )
    try:
        result = buffer.lookup_transform(
            LOCALIZATION_REFERENCE_FRAME,
            LOCALIZATION_BODY_FRAME,
            RclpyTime(nanoseconds=observed_at_ns),
            timeout=Duration(nanoseconds=timeout_ns),
        )
    except ConnectivityException as error:
        raise LocalizationAdapterError(
            EvidenceFailureKind.FRAME_LOOKUP_CONNECTIVITY,
            'reviewed localization frames are disconnected',
        ) from error
    except ExtrapolationException as error:
        raise LocalizationAdapterError(
            EvidenceFailureKind.FRAME_LOOKUP_EXTRAPOLATION,
            'the exact requested transform time is unavailable',
        ) from error
    except TimeoutException as error:
        raise LocalizationAdapterError(
            EvidenceFailureKind.FRAME_LOOKUP_TIMEOUT,
            'exact transform lookup exceeded its bounded timeout',
        ) from error
    except InvalidArgumentException as error:
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'TF2 rejected the fixed frame request',
        ) from error
    except LookupException as error:
        raise LocalizationAdapterError(
            EvidenceFailureKind.FRAME_LOOKUP_UNAVAILABLE,
            'the exact reviewed transform is unavailable',
        ) from error
    if (
        result.header.frame_id != LOCALIZATION_REFERENCE_FRAME
        or result.child_frame_id != LOCALIZATION_BODY_FRAME
        or _nanoseconds(result.header.stamp.sec, result.header.stamp.nanosec)
        != observed_at_ns
    ):
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'TF2 result changed the reviewed frames or exact requested timestamp',
        )
    return result


def normalize_localization(
    message: Odometry,
    transform: TransformStamped,
    provenance: ObservationProvenance,
    sensor: SensorIdentity,
) -> BodyPoseObservation:
    """Normalize a lookup-confirmed pose without fabricating uncertainty."""
    if not isinstance(message, Odometry) or not isinstance(transform, TransformStamped):
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'localization normalization requires typed ROS evidence',
        )
    if (
        type(sensor) is not SensorIdentity
        or sensor.kind is not SensorKind.BODY_POSE
        or sensor.sensor_id != 'ayyo.body-pose.localization.v1'
        or sensor.frame_id != LOCALIZATION_BODY_FRAME
    ):
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'localization sensor identity is not the reviewed body-pose contract',
        )
    observed_at_ns = _nanoseconds(
        message.header.stamp.sec,
        message.header.stamp.nanosec,
    )
    if (
        transform.header.frame_id != LOCALIZATION_REFERENCE_FRAME
        or transform.child_frame_id != LOCALIZATION_BODY_FRAME
        or _nanoseconds(transform.header.stamp.sec, transform.header.stamp.nanosec)
        != observed_at_ns
    ):
        raise LocalizationAdapterError(
            EvidenceFailureKind.INVALID_FRAME_REQUEST,
            'lookup result does not match the exact reviewed odometry request',
        )
    try:
        pose = Pose3D(
            LOCALIZATION_REFERENCE_FRAME,
            LOCALIZATION_BODY_FRAME,
            (
                transform.transform.translation.x,
                transform.transform.translation.y,
                transform.transform.translation.z,
            ),
            (
                transform.transform.rotation.x,
                transform.transform.rotation.y,
                transform.transform.rotation.z,
                transform.transform.rotation.w,
            ),
        )
    except ValueError as error:
        detail = str(error)
        failure = (
            EvidenceFailureKind.INVALID_QUATERNION
            if 'quaternion' in detail
            else EvidenceFailureKind.MALFORMED_NUMERIC_POSE
        )
        raise LocalizationAdapterError(failure, 'lookup pose values are invalid') from error
    return BodyPoseObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=sensor,
        pose=pose,
        covariance=_unknown_covariance(message.pose.covariance),
        observed_at_ns=observed_at_ns,
        provenance=provenance,
        availability=SensorAvailability.AVAILABLE,
        quality=None,
    )


def _bounded_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or len(value) > MAX_DIAGNOSTIC_TEXT
        or '\x00' in value
    ):
        raise DiagnosticAdapterError(f'{field_name} must be bounded non-NUL text')
    return value


def normalize_diagnostics(
    message: DiagnosticArray,
    provenance: ObservationProvenance,
    contracts: tuple[DiagnosticComponentContract, ...],
) -> DiagnosticNormalizationResult:
    """Map only exact reviewed components; values remain inert evidence text."""
    if not isinstance(message, DiagnosticArray):
        raise DiagnosticAdapterError('health evidence must be DiagnosticArray')
    if type(provenance) is not ObservationProvenance:
        raise DiagnosticAdapterError('diagnostics require reviewed provenance')
    if (
        type(contracts) is not tuple
        or not contracts
        or len({item.name for item in contracts}) != len(contracts)
        or len({item.sensor.sensor_id for item in contracts}) != len(contracts)
    ):
        raise DiagnosticAdapterError('diagnostic contracts must be unique and bounded')
    if len(message.status) > MAX_DIAGNOSTIC_STATUS_COUNT:
        raise DiagnosticAdapterError('diagnostic status collection exceeds its bound')
    observed_at_ns = _nanoseconds(
        message.header.stamp.sec,
        message.header.stamp.nanosec,
    )
    by_name = {item.name: item for item in contracts}
    known_hardware = {item.hardware_id for item in contracts}
    accepted: dict[str, SensorHealthObservation] = {}
    ignored: set[str] = set()
    availability_by_level = {
        DiagnosticStatus.OK: SensorAvailability.AVAILABLE,
        DiagnosticStatus.WARN: SensorAvailability.DEGRADED,
        DiagnosticStatus.ERROR: SensorAvailability.ERROR,
        DiagnosticStatus.STALE: SensorAvailability.STALE,
    }
    for status in message.status:
        name = _bounded_text(status.name, 'diagnostic component name')
        hardware_id = _bounded_text(status.hardware_id, 'diagnostic hardware ID')
        contract = by_name.get(name)
        if contract is None:
            if hardware_id in known_hardware:
                raise DiagnosticAdapterError(
                    'known hardware identity cannot substitute its reviewed component name'
                )
            ignored.add(name)
            continue
        if hardware_id != contract.hardware_id:
            raise DiagnosticAdapterError(
                'diagnostic hardware identity does not match its reviewed sensor'
            )
        availability = availability_by_level.get(status.level)
        if availability is None:
            raise DiagnosticAdapterError('diagnostic level is outside standard ROS semantics')
        if len(status.values) > MAX_DIAGNOSTIC_VALUES:
            raise DiagnosticAdapterError('diagnostic key/value collection exceeds its bound')
        pairs = tuple(
            sorted(
                (
                    _bounded_text(item.key, 'diagnostic key'),
                    _bounded_text(item.value, 'diagnostic value'),
                )
                for item in status.values
            )
        )
        if len({key for key, _ in pairs}) != len(pairs):
            raise DiagnosticAdapterError('diagnostic keys must be unique')
        detail = json.dumps(
            {
                'message': _bounded_text(status.message, 'diagnostic message'),
                'values': [list(item) for item in pairs],
            },
            ensure_ascii=True,
            separators=(',', ':'),
            sort_keys=True,
        )
        if len(detail) > MAX_DIAGNOSTIC_DETAIL:
            raise DiagnosticAdapterError('diagnostic detail exceeds its aggregate bound')
        observation = SensorHealthObservation(
            robot_id=AYYO_ROBOT_ID,
            sensor=contract.sensor,
            availability=availability,
            observed_at_ns=observed_at_ns,
            provenance=provenance,
            evidence_detail=detail,
        )
        current = accepted.get(contract.sensor.sensor_id)
        if current is not None and current != observation:
            raise DiagnosticAdapterError(
                'duplicate diagnostic component carries conflicting state'
            )
        accepted[contract.sensor.sensor_id] = observation
    return DiagnosticNormalizationResult(
        observations=tuple(accepted[key] for key in sorted(accepted)),
        ignored_components=tuple(sorted(ignored)),
    )
