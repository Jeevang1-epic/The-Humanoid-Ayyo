"""Bounded lifecycle adapter for exact-time head-depth evidence."""

from __future__ import annotations

from threading import RLock

from ayyo_world_model import (
    DepthFrameObservation,
    SensorAvailability,
    SensorHealthObservation,
)

from .errors import (
    DepthCameraConfigurationError,
    DepthCameraLifecycleError,
    DepthCameraValidationError,
)
from .models import (
    MAX_DEPTH_CAMERA_SOURCES,
    MAX_DEPTH_COUNT,
    MAX_DEPTH_PENDING_PAIRS,
    DepthCameraAdmission,
    DepthCameraCalibration,
    DepthCalibrationState,
    DepthCameraInfoMetadata,
    DepthDiagnosticEvent,
    DepthDiagnostics,
    DepthImageMetadata,
    DepthLifecycleState,
    DepthSourceManifest,
    _issue_admission,
    depth_camera_session_id,
)


class DepthSourceRegistry:
    """Small explicit source allowlist; manifests never select executable code."""

    __slots__ = ("_lock", "_sources")

    def __init__(self) -> None:
        self._sources: dict[str, DepthSourceManifest] = {}
        self._lock = RLock()

    def register(self, source: DepthSourceManifest) -> bool:
        if type(source) is not DepthSourceManifest:
            raise DepthCameraConfigurationError("depth registry requires a typed manifest")
        with self._lock:
            existing = self._sources.get(source.source_id)
            if existing is not None:
                if existing == source:
                    return False
                raise DepthCameraConfigurationError(
                    "depth source identity conflicts with its registration"
                )
            if len(self._sources) >= MAX_DEPTH_CAMERA_SOURCES:
                raise DepthCameraConfigurationError(
                    "depth source registry reached its hard bound"
                )
            self._sources[source.source_id] = source
            return True

    def resolve(self, source_id: str) -> DepthSourceManifest:
        with self._lock:
            source = self._sources.get(source_id)
            if source is None:
                raise DepthCameraConfigurationError(
                    "depth source is not explicitly registered"
                )
            return source

    @property
    def source_count(self) -> int:
        with self._lock:
            return len(self._sources)


class DepthLifecycleAdapter:
    """Issue sealed compact depth evidence only during one active source epoch."""

    __slots__ = (
        "_accepted_count",
        "_calibration",
        "_diagnostics",
        "_duplicate_count",
        "_epoch",
        "_evicted_count",
        "_future_skew_ns",
        "_last_accepted_at_ns",
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
        registry: DepthSourceRegistry,
        *,
        pair_wait_ns: int = 200_000_000,
        retention_ns: int = 2_000_000_000,
        future_skew_ns: int = 50_000_000,
    ) -> None:
        if type(registry) is not DepthSourceRegistry:
            raise DepthCameraConfigurationError("depth adapter requires an explicit registry")
        if (
            type(pair_wait_ns) is not int
            or type(retention_ns) is not int
            or type(future_skew_ns) is not int
            or not 0 <= pair_wait_ns <= 1_000_000_000
            or not pair_wait_ns < retention_ns <= 300_000_000_000
            or not 0 <= future_skew_ns <= 1_000_000_000
        ):
            raise DepthCameraConfigurationError("depth adapter time bounds are invalid")
        self._registry = registry
        self._pair_wait_ns = pair_wait_ns
        self._retention_ns = retention_ns
        self._future_skew_ns = future_skew_ns
        self._source: DepthSourceManifest | None = None
        self._calibration: DepthCameraCalibration | None = None
        self._state = DepthLifecycleState.UNCONFIGURED
        self._session_id: str | None = None
        self._epoch = 0
        self._pending_images: dict[int, DepthImageMetadata] = {}
        self._pending_camera_info: dict[int, DepthCameraInfoMetadata] = {}
        self._last_accepted_at_ns: int | None = None
        self._accepted_count = 0
        self._rejected_count = 0
        self._duplicate_count = 0
        self._evicted_count = 0
        self._lock = RLock()
        self._diagnostics = self._make_diagnostics(
            DepthDiagnosticEvent.UNCONFIGURED,
            SensorAvailability.UNAVAILABLE,
            observed_at_ns=0,
        )

    @property
    def state(self) -> DepthLifecycleState:
        with self._lock:
            return self._state

    @property
    def active_session_id(self) -> str | None:
        with self._lock:
            return self._session_id

    @property
    def source(self) -> DepthSourceManifest | None:
        with self._lock:
            return self._source

    @property
    def calibration(self) -> DepthCameraCalibration | None:
        with self._lock:
            return self._calibration

    @property
    def diagnostics(self) -> DepthDiagnostics:
        with self._lock:
            return self._diagnostics

    @staticmethod
    def _increment(value: int) -> int:
        return min(value + 1, MAX_DEPTH_COUNT)

    def _make_diagnostics(
        self,
        event: DepthDiagnosticEvent,
        availability: SensorAvailability,
        *,
        observed_at_ns: int,
    ) -> DepthDiagnostics:
        return DepthDiagnostics(
            source_id=(
                "depth.camera.unconfigured.v1"
                if self._source is None
                else self._source.source_id
            ),
            session_id=self._session_id,
            lifecycle_state=self._state,
            calibration_state=(
                DepthCalibrationState.VALID
                if self._calibration is not None
                else DepthCalibrationState.UNKNOWN
            ),
            event=event,
            availability=availability,
            accepted_count=self._accepted_count,
            rejected_count=self._rejected_count,
            duplicate_count=self._duplicate_count,
            evicted_count=self._evicted_count,
            pending_image_count=len(self._pending_images),
            pending_camera_info_count=len(self._pending_camera_info),
            observed_at_ns=observed_at_ns,
        )

    def _set_event(
        self,
        event: DepthDiagnosticEvent,
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
        calibration: DepthCameraCalibration | None,
    ) -> None:
        with self._lock:
            if self._state not in {DepthLifecycleState.UNCONFIGURED, DepthLifecycleState.INACTIVE}:
                raise DepthCameraLifecycleError(
                    "depth camera can only configure while unconfigured or inactive"
                )
            source = self._registry.resolve(source_id)
            self._source = source
            self._session_id = None
            self._clear_pending()
            if calibration is None:
                self._calibration = None
                self._state = DepthLifecycleState.INACTIVE
                self._set_event(
                    DepthDiagnosticEvent.CALIBRATION_MISSING,
                    SensorAvailability.UNAVAILABLE,
                    observed_at_ns=0,
                )
                return
            if type(calibration) is not DepthCameraCalibration:
                raise DepthCameraConfigurationError("depth calibration must be typed")
            if (
                calibration.sensor != source.sensor
                or calibration.source_id != source.source_id
                or calibration.mount_frame_id != source.mount_frame_id
                or calibration.optical_frame_id != source.sensor.frame_id
                or calibration.calibration.calibration_id != source.calibration_id
                or calibration.calibration_record_id != source.calibration_record_id
                or not source.minimum_width <= calibration.calibration.width <= source.maximum_width
                or not source.minimum_height <= calibration.calibration.height <= source.maximum_height
            ):
                raise DepthCameraConfigurationError(
                    "depth calibration does not match the exact source"
                )
            self._calibration = calibration
            self._state = DepthLifecycleState.INACTIVE
            self._set_event(
                DepthDiagnosticEvent.CONFIGURED,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )

    def activate(self) -> str:
        with self._lock:
            if self._state is not DepthLifecycleState.INACTIVE:
                raise DepthCameraLifecycleError("depth camera can only activate from inactive")
            if self._source is None or self._calibration is None:
                raise DepthCameraLifecycleError(
                    "depth camera cannot activate without reviewed calibration"
                )
            self._epoch = self._increment(self._epoch)
            self._session_id = depth_camera_session_id(
                self._source.manifest_id,
                self._epoch,
            )
            self._state = DepthLifecycleState.ACTIVE
            self._clear_pending()
            self._last_accepted_at_ns = None
            self._set_event(
                DepthDiagnosticEvent.ACQUISITION_ACTIVE,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )
            return self._session_id

    def deactivate(self) -> None:
        with self._lock:
            if self._state is not DepthLifecycleState.ACTIVE:
                raise DepthCameraLifecycleError("depth camera can only deactivate from active")
            self._state = DepthLifecycleState.INACTIVE
            self._clear_pending()
            self._last_accepted_at_ns = None
            self._set_event(
                DepthDiagnosticEvent.LIFECYCLE_INACTIVE,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )
            self._session_id = None

    def cleanup(self) -> None:
        with self._lock:
            if self._state is DepthLifecycleState.ACTIVE:
                raise DepthCameraLifecycleError("depth camera must deactivate before cleanup")
            if self._state is DepthLifecycleState.FINALIZED:
                raise DepthCameraLifecycleError("finalized depth camera cannot be cleaned up")
            self._clear_pending()
            self._source = None
            self._calibration = None
            self._session_id = None
            self._last_accepted_at_ns = None
            self._state = DepthLifecycleState.UNCONFIGURED
            self._set_event(
                DepthDiagnosticEvent.UNCONFIGURED,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )

    def shutdown(self) -> None:
        with self._lock:
            self._clear_pending()
            self._state = DepthLifecycleState.FINALIZED
            self._session_id = None
            self._last_accepted_at_ns = None
            self._set_event(
                DepthDiagnosticEvent.SHUTDOWN,
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
        event: DepthDiagnosticEvent,
        *,
        observed_at_ns: int,
        availability: SensorAvailability = SensorAvailability.ERROR,
    ) -> None:
        self._rejected_count = self._increment(self._rejected_count)
        self._set_event(event, availability, observed_at_ns=observed_at_ns)

    def _validate_common(self, value, *, now_ns: int) -> bool:
        if self._state is not DepthLifecycleState.ACTIVE:
            self._reject(
                DepthDiagnosticEvent.LIFECYCLE_INACTIVE,
                observed_at_ns=0,
                availability=SensorAvailability.UNAVAILABLE,
            )
            return False
        if self._source is None or self._calibration is None or self._session_id is None:
            self._reject(DepthDiagnosticEvent.MALFORMED_INPUT, observed_at_ns=0)
            return False
        if type(now_ns) is not int or not 0 <= now_ns <= MAX_DEPTH_COUNT:
            raise DepthCameraValidationError("depth current source time is invalid")
        if value.session_id != self._session_id:
            self._reject(
                DepthDiagnosticEvent.SESSION_MISMATCH,
                observed_at_ns=value.observed_at_ns,
            )
            return False
        if (
            value.source_id != self._source.source_id
            or value.robot_id != self._source.robot_id
            or value.sensor != self._source.sensor
            or value.provenance != self._source.provenance
        ):
            self._reject(
                DepthDiagnosticEvent.WRONG_SOURCE,
                observed_at_ns=value.observed_at_ns,
            )
            return False
        if value.frame_id != self._source.sensor.frame_id:
            self._reject(
                DepthDiagnosticEvent.WRONG_FRAME,
                observed_at_ns=value.observed_at_ns,
            )
            return False
        if value.observed_at_ns > now_ns + self._future_skew_ns:
            self._reject(
                DepthDiagnosticEvent.FUTURE_FRAME,
                observed_at_ns=value.observed_at_ns,
            )
            return False
        if value.observed_at_ns < now_ns - self._retention_ns:
            self._reject(
                DepthDiagnosticEvent.STALE_FRAME,
                observed_at_ns=value.observed_at_ns,
                availability=SensorAvailability.STALE,
            )
            return False
        if self._last_accepted_at_ns is not None:
            if value.observed_at_ns < self._last_accepted_at_ns:
                self._reject(
                    DepthDiagnosticEvent.SOURCE_CLOCK_REGRESSION,
                    observed_at_ns=value.observed_at_ns,
                )
                return False
            if value.observed_at_ns == self._last_accepted_at_ns:
                self._duplicate_count = self._increment(self._duplicate_count)
                self._set_event(
                    DepthDiagnosticEvent.REPEATED_TIMESTAMP,
                    SensorAvailability.DEGRADED,
                    observed_at_ns=value.observed_at_ns,
                )
                return False
        return True

    def _evict_pending(self, newest_ns: int) -> None:
        cutoff = newest_ns - self._pair_wait_ns
        evicted_before = self._evicted_count
        for pending in (self._pending_images, self._pending_camera_info):
            for time_ns in tuple(time_ns for time_ns in pending if time_ns < cutoff):
                del pending[time_ns]
                self._evicted_count = self._increment(self._evicted_count)
            while len(pending) > MAX_DEPTH_PENDING_PAIRS:
                del pending[min(pending)]
                self._evicted_count = self._increment(self._evicted_count)
        if self._evicted_count != evicted_before:
            self._set_event(
                DepthDiagnosticEvent.PENDING_EVICTED,
                SensorAvailability.DEGRADED,
                observed_at_ns=newest_ns,
            )

    def submit_image(
        self,
        image: DepthImageMetadata,
        *,
        now_ns: int,
    ) -> DepthCameraAdmission | None:
        if type(image) is not DepthImageMetadata:
            raise DepthCameraValidationError("depth image metadata must be typed")
        with self._lock:
            if not self._validate_common(image, now_ns=now_ns):
                return None
            assert self._source is not None
            if image.encoding not in self._source.encodings:
                self._reject(
                    DepthDiagnosticEvent.UNSUPPORTED_ENCODING,
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
                    DepthDiagnosticEvent.REPEATED_TIMESTAMP,
                    SensorAvailability.DEGRADED,
                    observed_at_ns=image.observed_at_ns,
                )
                return None
            self._pending_images[image.observed_at_ns] = image
            self._evict_pending(image.observed_at_ns)
            return self._try_pair(image.observed_at_ns)

    def submit_camera_info(
        self,
        camera_info: DepthCameraInfoMetadata,
        *,
        now_ns: int,
    ) -> DepthCameraAdmission | None:
        if type(camera_info) is not DepthCameraInfoMetadata:
            raise DepthCameraValidationError("depth CameraInfo metadata must be typed")
        with self._lock:
            if not self._validate_common(camera_info, now_ns=now_ns):
                return None
            if camera_info.calibration != self._calibration:
                self._reject(
                    DepthDiagnosticEvent.CALIBRATION_INVALID,
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
                    DepthDiagnosticEvent.REPEATED_TIMESTAMP,
                    SensorAvailability.DEGRADED,
                    observed_at_ns=camera_info.observed_at_ns,
                )
                return None
            self._pending_camera_info[camera_info.observed_at_ns] = camera_info
            self._evict_pending(camera_info.observed_at_ns)
            return self._try_pair(camera_info.observed_at_ns)

    def _try_pair(self, observed_at_ns: int) -> DepthCameraAdmission | None:
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
                DepthDiagnosticEvent.PAIR_MISMATCH,
                observed_at_ns=observed_at_ns,
            )
            return None
        frame = DepthFrameObservation(
            robot_id=self._source.robot_id,
            sensor=self._source.sensor,
            width=image.width,
            height=image.height,
            encoding=image.encoding,
            step=image.step,
            data_size_bytes=image.data_size_bytes,
            is_bigendian=image.is_bigendian,
            calibration_id=calibration.calibration_id,
            calibration_record_id=self._calibration.calibration_record_id,
            source_manifest_id=self._source.manifest_id,
            session_id=self._session_id,
            valid_depth_count=image.valid_depth_count,
            invalid_depth_count=image.invalid_depth_count,
            minimum_depth_m=image.minimum_depth_m,
            maximum_depth_m=image.maximum_depth_m,
            payload_sha256=image.payload_sha256,
            observed_at_ns=observed_at_ns,
            provenance=self._source.provenance,
            availability=(
                SensorAvailability.DEGRADED
                if image.invalid_depth_count
                else SensorAvailability.AVAILABLE
            ),
        )
        self._last_accepted_at_ns = observed_at_ns
        self._accepted_count = self._increment(self._accepted_count)
        self._set_event(
            DepthDiagnosticEvent.FRAME_ACCEPTED,
            frame.availability,
            observed_at_ns=observed_at_ns,
        )
        diagnostics = self._diagnostics
        health = SensorHealthObservation(
            robot_id=self._source.robot_id,
            sensor=self._source.sensor,
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
