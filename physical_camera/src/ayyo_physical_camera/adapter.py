"""Bounded driver-neutral physical-camera registration and lifecycle adapter."""

from __future__ import annotations

from threading import RLock

from ayyo_world_model import (
    SensorAvailability,
    SensorHealthObservation,
    VisualFrameObservation,
)

from .errors import (
    PhysicalCameraConfigurationError,
    PhysicalCameraLifecycleError,
    PhysicalCameraValidationError,
)
from .models import (
    MAX_PHYSICAL_CAMERA_COUNT,
    MAX_PHYSICAL_CAMERA_PENDING_PAIRS,
    MAX_PHYSICAL_CAMERA_SOURCES,
    PhysicalCameraAdmission,
    PhysicalCameraCalibration,
    PhysicalCameraCalibrationState,
    PhysicalCameraDiagnosticEvent,
    PhysicalCameraDiagnostics,
    PhysicalCameraImageMetadata,
    PhysicalCameraInfoMetadata,
    PhysicalCameraLifecycleState,
    PhysicalCameraSourceManifest,
    _issue_admission,
    physical_camera_session_id,
)


class PhysicalCameraSourceRegistry:
    """Small explicit allowlist; metadata never selects executable code."""

    __slots__ = ("_sources", "_lock")

    def __init__(self) -> None:
        self._sources: dict[str, PhysicalCameraSourceManifest] = {}
        self._lock = RLock()

    def register(self, source: PhysicalCameraSourceManifest) -> bool:
        if type(source) is not PhysicalCameraSourceManifest:
            raise PhysicalCameraConfigurationError(
                "physical camera registry requires a typed source manifest"
            )
        with self._lock:
            existing = self._sources.get(source.source_id)
            if existing is not None:
                if existing == source:
                    return False
                raise PhysicalCameraConfigurationError(
                    "physical camera source identity conflicts with its registration"
                )
            if len(self._sources) >= MAX_PHYSICAL_CAMERA_SOURCES:
                raise PhysicalCameraConfigurationError(
                    "physical camera source registry reached its hard bound"
                )
            self._sources[source.source_id] = source
            return True

    def resolve(self, source_id: str) -> PhysicalCameraSourceManifest:
        with self._lock:
            source = self._sources.get(source_id)
            if source is None:
                raise PhysicalCameraConfigurationError(
                    "physical camera source is not explicitly registered"
                )
            return source

    @property
    def source_count(self) -> int:
        with self._lock:
            return len(self._sources)


class PhysicalCameraLifecycleAdapter:
    """Pair metadata and issue sealed evidence only during an active source epoch."""

    __slots__ = (
        "_accepted_count",
        "_calibration",
        "_diagnostics",
        "_duplicate_count",
        "_epoch",
        "_evicted_count",
        "_future_skew_ns",
        "_last_accepted_at_ns",
        "_last_interval_ns",
        "_lock",
        "_pair_wait_ns",
        "_pending_camera_info",
        "_pending_images",
        "_registry",
        "_rejected_count",
        "_retention_ns",
        "_session_id",
        "_source",
        "_state",
    )

    def __init__(
        self,
        registry: PhysicalCameraSourceRegistry,
        *,
        pair_wait_ns: int = 200_000_000,
        retention_ns: int = 2_000_000_000,
        future_skew_ns: int = 50_000_000,
    ) -> None:
        if type(registry) is not PhysicalCameraSourceRegistry:
            raise PhysicalCameraConfigurationError(
                "physical camera adapter requires an explicit source registry"
            )
        if (
            type(pair_wait_ns) is not int
            or type(retention_ns) is not int
            or type(future_skew_ns) is not int
            or not 0 <= pair_wait_ns <= 1_000_000_000
            or not pair_wait_ns < retention_ns <= 300_000_000_000
            or not 0 <= future_skew_ns <= 1_000_000_000
        ):
            raise PhysicalCameraConfigurationError(
                "physical camera time bounds are invalid"
            )
        self._registry = registry
        self._pair_wait_ns = pair_wait_ns
        self._retention_ns = retention_ns
        self._future_skew_ns = future_skew_ns
        self._source: PhysicalCameraSourceManifest | None = None
        self._calibration: PhysicalCameraCalibration | None = None
        self._state = PhysicalCameraLifecycleState.UNCONFIGURED
        self._session_id: str | None = None
        self._epoch = 0
        self._pending_images: dict[int, PhysicalCameraImageMetadata] = {}
        self._pending_camera_info: dict[int, PhysicalCameraInfoMetadata] = {}
        self._last_accepted_at_ns: int | None = None
        self._last_interval_ns: int | None = None
        self._accepted_count = 0
        self._rejected_count = 0
        self._duplicate_count = 0
        self._evicted_count = 0
        self._diagnostics = self._make_diagnostics(
            PhysicalCameraDiagnosticEvent.UNCONFIGURED,
            SensorAvailability.UNAVAILABLE,
            observed_at_ns=0,
        )
        self._lock = RLock()

    @property
    def state(self) -> PhysicalCameraLifecycleState:
        with self._lock:
            return self._state

    @property
    def active_session_id(self) -> str | None:
        with self._lock:
            return self._session_id

    @property
    def source(self) -> PhysicalCameraSourceManifest | None:
        with self._lock:
            return self._source

    @property
    def calibration(self) -> PhysicalCameraCalibration | None:
        with self._lock:
            return self._calibration

    @property
    def diagnostics(self) -> PhysicalCameraDiagnostics:
        with self._lock:
            return self._diagnostics

    @staticmethod
    def _increment(value: int) -> int:
        return min(value + 1, MAX_PHYSICAL_CAMERA_COUNT)

    def _calibration_state(self) -> PhysicalCameraCalibrationState:
        return (
            PhysicalCameraCalibrationState.VALID
            if self._calibration is not None
            else PhysicalCameraCalibrationState.UNKNOWN
        )

    def _make_diagnostics(
        self,
        event: PhysicalCameraDiagnosticEvent,
        availability: SensorAvailability,
        *,
        observed_at_ns: int,
    ) -> PhysicalCameraDiagnostics:
        source_id = (
            "physical.camera.unconfigured.v1"
            if self._source is None
            else self._source.source_id
        )
        frequency = None
        if self._last_interval_ns is not None and self._last_interval_ns > 0:
            frequency = min(1_000_000_000, 1_000_000_000_000 // self._last_interval_ns)
        return PhysicalCameraDiagnostics(
            source_id=source_id,
            session_id=self._session_id,
            lifecycle_state=self._state,
            calibration_state=self._calibration_state(),
            event=event,
            availability=availability,
            source_available=self._source is not None,
            acquisition_active=self._state is PhysicalCameraLifecycleState.ACTIVE,
            accepted_count=self._accepted_count,
            rejected_count=self._rejected_count,
            duplicate_count=self._duplicate_count,
            evicted_count=self._evicted_count,
            pending_image_count=len(self._pending_images),
            pending_camera_info_count=len(self._pending_camera_info),
            observed_frequency_millihz=frequency,
            dropped_frame_count=None,
            observed_at_ns=observed_at_ns,
        )

    def _set_event(
        self,
        event: PhysicalCameraDiagnosticEvent,
        availability: SensorAvailability,
        *,
        observed_at_ns: int,
    ) -> None:
        self._diagnostics = self._make_diagnostics(
            event,
            availability,
            observed_at_ns=observed_at_ns,
        )

    def configure(
        self,
        source_id: str,
        calibration: PhysicalCameraCalibration | None,
    ) -> None:
        with self._lock:
            if self._state not in {
                PhysicalCameraLifecycleState.UNCONFIGURED,
                PhysicalCameraLifecycleState.INACTIVE,
            }:
                raise PhysicalCameraLifecycleError(
                    "physical camera can only configure while unconfigured or inactive"
                )
            source = self._registry.resolve(source_id)
            if calibration is None:
                self._source = source
                self._calibration = None
                self._state = PhysicalCameraLifecycleState.INACTIVE
                self._session_id = None
                self._set_event(
                    PhysicalCameraDiagnosticEvent.CALIBRATION_MISSING,
                    SensorAvailability.UNAVAILABLE,
                    observed_at_ns=0,
                )
                return
            if type(calibration) is not PhysicalCameraCalibration:
                raise PhysicalCameraConfigurationError(
                    "physical camera calibration must be typed or explicitly unknown"
                )
            if (
                calibration.camera != source.camera
                or calibration.source_id != source.source_id
                or calibration.camera_frame_id != source.camera_frame_id
                or calibration.optical_frame_id != source.camera.frame_id
                or calibration.calibration.calibration_id != source.calibration_id
                or calibration.calibration_record_id != source.calibration_record_id
                or not source.minimum_width
                <= calibration.calibration.width
                <= source.maximum_width
                or not source.minimum_height
                <= calibration.calibration.height
                <= source.maximum_height
            ):
                raise PhysicalCameraConfigurationError(
                    "physical calibration does not match the exact registered source"
                )
            self._source = source
            self._calibration = calibration
            self._state = PhysicalCameraLifecycleState.INACTIVE
            self._session_id = None
            self._clear_pending()
            self._set_event(
                PhysicalCameraDiagnosticEvent.CONFIGURED,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )

    def activate(self) -> str:
        with self._lock:
            if self._state is not PhysicalCameraLifecycleState.INACTIVE:
                raise PhysicalCameraLifecycleError(
                    "physical camera can only activate from inactive"
                )
            if self._source is None or self._calibration is None:
                raise PhysicalCameraLifecycleError(
                    "physical camera cannot activate without reviewed calibration"
                )
            self._epoch = self._increment(self._epoch)
            self._session_id = physical_camera_session_id(
                self._source.manifest_id,
                self._epoch,
            )
            self._state = PhysicalCameraLifecycleState.ACTIVE
            self._clear_pending()
            self._last_accepted_at_ns = None
            self._last_interval_ns = None
            self._set_event(
                PhysicalCameraDiagnosticEvent.ACQUISITION_ACTIVE,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )
            return self._session_id

    def deactivate(self) -> None:
        with self._lock:
            if self._state is not PhysicalCameraLifecycleState.ACTIVE:
                raise PhysicalCameraLifecycleError(
                    "physical camera can only deactivate from active"
                )
            self._state = PhysicalCameraLifecycleState.INACTIVE
            self._clear_pending()
            self._set_event(
                PhysicalCameraDiagnosticEvent.LIFECYCLE_INACTIVE,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )
            self._session_id = None

    def cleanup(self) -> None:
        with self._lock:
            if self._state is PhysicalCameraLifecycleState.ACTIVE:
                raise PhysicalCameraLifecycleError(
                    "physical camera must deactivate before cleanup"
                )
            if self._state is PhysicalCameraLifecycleState.FINALIZED:
                raise PhysicalCameraLifecycleError(
                    "finalized physical camera cannot be cleaned up"
                )
            self._clear_pending()
            self._source = None
            self._calibration = None
            self._session_id = None
            self._last_accepted_at_ns = None
            self._last_interval_ns = None
            self._state = PhysicalCameraLifecycleState.UNCONFIGURED
            self._set_event(
                PhysicalCameraDiagnosticEvent.UNCONFIGURED,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )

    def shutdown(self) -> None:
        with self._lock:
            self._clear_pending()
            self._state = PhysicalCameraLifecycleState.FINALIZED
            self._session_id = None
            self._set_event(
                PhysicalCameraDiagnosticEvent.SHUTDOWN,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )
            self._source = None
            self._calibration = None

    def _clear_pending(self) -> None:
        self._pending_images.clear()
        self._pending_camera_info.clear()

    def _reject(
        self,
        event: PhysicalCameraDiagnosticEvent,
        *,
        observed_at_ns: int,
        availability: SensorAvailability = SensorAvailability.ERROR,
    ) -> None:
        self._rejected_count = self._increment(self._rejected_count)
        self._set_event(event, availability, observed_at_ns=observed_at_ns)

    def _validate_common(self, value, *, now_ns: int) -> bool:
        if self._state is not PhysicalCameraLifecycleState.ACTIVE:
            self._reject(
                PhysicalCameraDiagnosticEvent.LIFECYCLE_INACTIVE,
                observed_at_ns=0,
                availability=SensorAvailability.UNAVAILABLE,
            )
            return False
        if self._source is None or self._calibration is None or self._session_id is None:
            self._reject(
                PhysicalCameraDiagnosticEvent.DEVICE_ERROR,
                observed_at_ns=0,
            )
            return False
        if type(now_ns) is not int or not 0 <= now_ns <= (1 << 63) - 1:
            raise PhysicalCameraValidationError(
                "physical camera current source time is invalid"
            )
        if value.session_id != self._session_id:
            self._reject(
                PhysicalCameraDiagnosticEvent.SESSION_MISMATCH,
                observed_at_ns=value.observed_at_ns,
            )
            return False
        if (
            value.source_id != self._source.source_id
            or value.robot_id != self._source.robot_id
            or value.camera != self._source.camera
            or value.provenance != self._source.provenance
        ):
            self._reject(
                PhysicalCameraDiagnosticEvent.WRONG_SOURCE,
                observed_at_ns=value.observed_at_ns,
            )
            return False
        if value.frame_id != self._source.camera.frame_id:
            self._reject(
                PhysicalCameraDiagnosticEvent.WRONG_FRAME,
                observed_at_ns=value.observed_at_ns,
            )
            return False
        if value.observed_at_ns > now_ns + self._future_skew_ns:
            self._reject(
                PhysicalCameraDiagnosticEvent.FUTURE_FRAME,
                observed_at_ns=value.observed_at_ns,
                availability=SensorAvailability.ERROR,
            )
            return False
        if value.observed_at_ns < now_ns - self._retention_ns:
            self._reject(
                PhysicalCameraDiagnosticEvent.STALE_FRAME,
                observed_at_ns=value.observed_at_ns,
                availability=SensorAvailability.STALE,
            )
            return False
        if self._last_accepted_at_ns is not None:
            if value.observed_at_ns < self._last_accepted_at_ns:
                self._reject(
                    PhysicalCameraDiagnosticEvent.SOURCE_CLOCK_REGRESSION,
                    observed_at_ns=value.observed_at_ns,
                )
                return False
            if value.observed_at_ns == self._last_accepted_at_ns:
                self._duplicate_count = self._increment(self._duplicate_count)
                self._set_event(
                    PhysicalCameraDiagnosticEvent.REPEATED_TIMESTAMP,
                    SensorAvailability.DEGRADED,
                    observed_at_ns=value.observed_at_ns,
                )
                return False
        return True

    def _evict_pending(self, newest_ns: int) -> None:
        cutoff = newest_ns - self._pair_wait_ns
        for pending in (self._pending_images, self._pending_camera_info):
            expired = tuple(time_ns for time_ns in pending if time_ns < cutoff)
            for time_ns in expired:
                del pending[time_ns]
                self._evicted_count = self._increment(self._evicted_count)
            while len(pending) > MAX_PHYSICAL_CAMERA_PENDING_PAIRS:
                del pending[min(pending)]
                self._evicted_count = self._increment(self._evicted_count)
        if self._evicted_count:
            self._set_event(
                PhysicalCameraDiagnosticEvent.PENDING_EVICTED,
                SensorAvailability.DEGRADED,
                observed_at_ns=newest_ns,
            )

    def submit_image(
        self,
        image: PhysicalCameraImageMetadata,
        *,
        now_ns: int,
    ) -> PhysicalCameraAdmission | None:
        if type(image) is not PhysicalCameraImageMetadata:
            raise PhysicalCameraValidationError(
                "physical camera image metadata must be typed"
            )
        with self._lock:
            if not self._validate_common(image, now_ns=now_ns):
                return None
            assert self._source is not None
            if (
                image.encoding not in self._source.encodings
                or image.step < image.width * 3
            ):
                self._reject(
                    PhysicalCameraDiagnosticEvent.UNSUPPORTED_ENCODING,
                    observed_at_ns=image.observed_at_ns,
                )
                return None
            if not (
                self._source.minimum_width <= image.width <= self._source.maximum_width
                and self._source.minimum_height <= image.height <= self._source.maximum_height
            ):
                self._reject(
                    PhysicalCameraDiagnosticEvent.WRONG_DIMENSIONS,
                    observed_at_ns=image.observed_at_ns,
                )
                return None
            existing = self._pending_images.get(image.observed_at_ns)
            if existing is not None:
                if existing == image:
                    self._duplicate_count = self._increment(self._duplicate_count)
                else:
                    self._rejected_count = self._increment(self._rejected_count)
                self._set_event(
                    PhysicalCameraDiagnosticEvent.REPEATED_TIMESTAMP,
                    SensorAvailability.DEGRADED,
                    observed_at_ns=image.observed_at_ns,
                )
                return None
            self._pending_images[image.observed_at_ns] = image
            self._evict_pending(image.observed_at_ns)
            self._set_event(
                self._diagnostics.event,
                self._diagnostics.availability,
                observed_at_ns=image.observed_at_ns,
            )
            return self._try_pair(image.observed_at_ns)

    def submit_camera_info(
        self,
        camera_info: PhysicalCameraInfoMetadata,
        *,
        now_ns: int,
    ) -> PhysicalCameraAdmission | None:
        if type(camera_info) is not PhysicalCameraInfoMetadata:
            raise PhysicalCameraValidationError(
                "physical CameraInfo metadata must be typed"
            )
        with self._lock:
            if not self._validate_common(camera_info, now_ns=now_ns):
                return None
            assert self._calibration is not None
            if camera_info.calibration != self._calibration:
                self._reject(
                    PhysicalCameraDiagnosticEvent.CALIBRATION_INVALID,
                    observed_at_ns=camera_info.observed_at_ns,
                )
                return None
            existing = self._pending_camera_info.get(camera_info.observed_at_ns)
            if existing is not None:
                if existing == camera_info:
                    self._duplicate_count = self._increment(self._duplicate_count)
                else:
                    self._rejected_count = self._increment(self._rejected_count)
                self._set_event(
                    PhysicalCameraDiagnosticEvent.REPEATED_TIMESTAMP,
                    SensorAvailability.DEGRADED,
                    observed_at_ns=camera_info.observed_at_ns,
                )
                return None
            self._pending_camera_info[camera_info.observed_at_ns] = camera_info
            self._evict_pending(camera_info.observed_at_ns)
            self._set_event(
                self._diagnostics.event,
                self._diagnostics.availability,
                observed_at_ns=camera_info.observed_at_ns,
            )
            return self._try_pair(camera_info.observed_at_ns)

    def _try_pair(self, observed_at_ns: int) -> PhysicalCameraAdmission | None:
        image = self._pending_images.get(observed_at_ns)
        camera_info = self._pending_camera_info.get(observed_at_ns)
        if image is None or camera_info is None:
            return None
        del self._pending_images[observed_at_ns]
        del self._pending_camera_info[observed_at_ns]
        assert self._source is not None
        assert self._calibration is not None
        assert self._session_id is not None
        calibration = camera_info.calibration.calibration
        if image.width != calibration.width or image.height != calibration.height:
            self._reject(
                PhysicalCameraDiagnosticEvent.PAIR_MISMATCH,
                observed_at_ns=observed_at_ns,
            )
            return None
        frame = VisualFrameObservation(
            robot_id=self._source.robot_id,
            sensor=self._source.camera,
            width=image.width,
            height=image.height,
            encoding=image.encoding,
            step=image.step,
            data_size_bytes=image.data_size_bytes,
            is_bigendian=image.is_bigendian,
            calibration_id=calibration.calibration_id,
            observed_at_ns=observed_at_ns,
            provenance=self._source.provenance,
            availability=SensorAvailability.AVAILABLE,
        )
        if self._last_accepted_at_ns is not None:
            self._last_interval_ns = observed_at_ns - self._last_accepted_at_ns
        self._last_accepted_at_ns = observed_at_ns
        self._accepted_count = self._increment(self._accepted_count)
        self._set_event(
            PhysicalCameraDiagnosticEvent.FRAME_ACCEPTED,
            SensorAvailability.AVAILABLE,
            observed_at_ns=observed_at_ns,
        )
        diagnostics = self._diagnostics
        health = SensorHealthObservation(
            robot_id=self._source.robot_id,
            sensor=self._source.camera,
            availability=diagnostics.availability,
            observed_at_ns=observed_at_ns,
            provenance=self._source.provenance,
            evidence_detail=diagnostics.evidence_detail(),
        )
        return _issue_admission(
            frame=frame,
            health=health,
            requirement=self._source.requirement(),
            session_id=self._session_id,
            diagnostics=diagnostics,
        )
