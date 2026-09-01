"""Synchronous bounded lifecycle adapter for trusted microphone evidence."""

from __future__ import annotations

from threading import RLock

from ayyo_world_model import (
    AudioFrameObservation,
    SensorAvailability,
    SensorHealthObservation,
    rebuild_observation,
)

from .errors import (
    HeadAudioConfigurationError,
    HeadAudioLifecycleError,
    HeadAudioValidationError,
)
from .models import (
    MAX_AUDIO_COUNT,
    MAX_AUDIO_SOURCES,
    AudioCaptureAdmission,
    AudioDiagnosticEvent,
    AudioDiagnostics,
    AudioLifecycleState,
    AudioSourceManifest,
    AudioTrustRequirement,
    _issue_admission,
    audio_session_id,
)


class AudioSourceRegistry:
    """Hard-bounded explicit microphone producer allowlist."""

    __slots__ = ("_lock", "_sources")

    def __init__(self) -> None:
        self._sources: dict[str, AudioSourceManifest] = {}
        self._lock = RLock()

    def register(self, source: AudioSourceManifest) -> bool:
        if type(source) is not AudioSourceManifest:
            raise HeadAudioConfigurationError(
                "audio registry requires a typed source manifest"
            )
        with self._lock:
            existing = self._sources.get(source.source_id)
            if existing is not None:
                if existing == source:
                    return False
                raise HeadAudioConfigurationError(
                    "audio source identity conflicts with its registration"
                )
            if len(self._sources) >= MAX_AUDIO_SOURCES:
                raise HeadAudioConfigurationError(
                    "audio source registry reached its hard bound"
                )
            self._sources[source.source_id] = source
            return True

    def resolve(self, source_id: str) -> AudioSourceManifest:
        with self._lock:
            source = self._sources.get(source_id)
            if source is None:
                raise HeadAudioConfigurationError(
                    "audio source is not explicitly registered"
                )
            return source

    @property
    def source_count(self) -> int:
        with self._lock:
            return len(self._sources)


class AudioLifecycleAdapter:
    """Issue one-use sealed compact audio evidence in an active source epoch."""

    __slots__ = (
        "_accepted_count",
        "_diagnostics",
        "_duplicate_count",
        "_epoch",
        "_future_skew_ns",
        "_last_accepted_at_ns",
        "_lock",
        "_registry",
        "_rejected_count",
        "_retention_ns",
        "_session_id",
        "_source",
        "_state",
    )

    def __init__(
        self,
        registry: AudioSourceRegistry,
        *,
        retention_ns: int = 2_000_000_000,
        future_skew_ns: int = 50_000_000,
    ) -> None:
        if type(registry) is not AudioSourceRegistry:
            raise HeadAudioConfigurationError(
                "audio adapter requires an explicit source registry"
            )
        if (
            type(retention_ns) is not int
            or type(future_skew_ns) is not int
            or not 1 <= retention_ns <= 300_000_000_000
            or not 0 <= future_skew_ns <= 1_000_000_000
        ):
            raise HeadAudioConfigurationError("audio adapter time bounds are invalid")
        self._registry = registry
        self._retention_ns = retention_ns
        self._future_skew_ns = future_skew_ns
        self._source: AudioSourceManifest | None = None
        self._state = AudioLifecycleState.UNCONFIGURED
        self._session_id: str | None = None
        self._epoch = 0
        self._last_accepted_at_ns: int | None = None
        self._accepted_count = 0
        self._rejected_count = 0
        self._duplicate_count = 0
        self._lock = RLock()
        self._diagnostics = self._make_diagnostics(
            AudioDiagnosticEvent.UNCONFIGURED,
            SensorAvailability.UNAVAILABLE,
            observed_at_ns=0,
        )

    @staticmethod
    def _increment(value: int) -> int:
        return min(value + 1, MAX_AUDIO_COUNT)

    @property
    def state(self) -> AudioLifecycleState:
        with self._lock:
            return self._state

    @property
    def active_session_id(self) -> str | None:
        with self._lock:
            return self._session_id

    @property
    def source(self) -> AudioSourceManifest | None:
        with self._lock:
            return self._source

    @property
    def diagnostics(self) -> AudioDiagnostics:
        with self._lock:
            return self._diagnostics

    def _make_diagnostics(
        self,
        event: AudioDiagnosticEvent,
        availability: SensorAvailability,
        *,
        observed_at_ns: int,
    ) -> AudioDiagnostics:
        return AudioDiagnostics(
            source_id=(
                "audio.source.unconfigured.v1"
                if self._source is None
                else self._source.source_id
            ),
            session_id=self._session_id,
            lifecycle_state=self._state,
            event=event,
            sample_rate_hz=(
                None if self._source is None else self._source.sample_rate_hz
            ),
            channel_count=(
                None if self._source is None else self._source.channel_count
            ),
            encoding=None if self._source is None else self._source.encoding,
            availability=availability,
            accepted_count=self._accepted_count,
            rejected_count=self._rejected_count,
            duplicate_count=self._duplicate_count,
            dropped_count=0,
            error_count=self._rejected_count,
            retained_payload_bytes=0,
            observed_at_ns=observed_at_ns,
        )

    def _set_event(
        self,
        event: AudioDiagnosticEvent,
        availability: SensorAvailability,
        *,
        observed_at_ns: int,
    ) -> None:
        self._diagnostics = self._make_diagnostics(
            event,
            availability,
            observed_at_ns=observed_at_ns,
        )

    def configure(self, source_id: str) -> None:
        with self._lock:
            if self._state not in {
                AudioLifecycleState.UNCONFIGURED,
                AudioLifecycleState.INACTIVE,
            }:
                raise HeadAudioLifecycleError(
                    "audio source can only configure while inactive"
                )
            self._source = self._registry.resolve(source_id)
            self._session_id = None
            self._last_accepted_at_ns = None
            self._state = AudioLifecycleState.INACTIVE
            self._set_event(
                AudioDiagnosticEvent.CONFIGURED,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )

    def activate(self) -> str:
        with self._lock:
            if self._state is not AudioLifecycleState.INACTIVE or self._source is None:
                raise HeadAudioLifecycleError(
                    "audio source can only activate after configuration"
                )
            self._epoch = self._increment(self._epoch)
            self._session_id = audio_session_id(self._source.manifest_id, self._epoch)
            self._last_accepted_at_ns = None
            self._state = AudioLifecycleState.ACTIVE
            self._set_event(
                AudioDiagnosticEvent.CAPTURE_ACTIVE,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )
            return self._session_id

    def deactivate(self) -> None:
        with self._lock:
            if self._state is not AudioLifecycleState.ACTIVE:
                raise HeadAudioLifecycleError(
                    "audio source can only deactivate while active"
                )
            self._state = AudioLifecycleState.INACTIVE
            self._last_accepted_at_ns = None
            self._set_event(
                AudioDiagnosticEvent.LIFECYCLE_INACTIVE,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )
            self._session_id = None

    def cleanup(self) -> None:
        with self._lock:
            if self._state is AudioLifecycleState.ACTIVE:
                raise HeadAudioLifecycleError(
                    "audio source must deactivate before cleanup"
                )
            if self._state is AudioLifecycleState.FINALIZED:
                raise HeadAudioLifecycleError(
                    "finalized audio source cannot be cleaned up"
                )
            self._source = None
            self._session_id = None
            self._last_accepted_at_ns = None
            self._state = AudioLifecycleState.UNCONFIGURED
            self._set_event(
                AudioDiagnosticEvent.UNCONFIGURED,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )

    def shutdown(self) -> None:
        with self._lock:
            self._state = AudioLifecycleState.FINALIZED
            self._session_id = None
            self._last_accepted_at_ns = None
            self._set_event(
                AudioDiagnosticEvent.SHUTDOWN,
                SensorAvailability.UNAVAILABLE,
                observed_at_ns=0,
            )
            self._source = None

    def _reject(self, event: AudioDiagnosticEvent, observed_at_ns: int) -> None:
        self._rejected_count = self._increment(self._rejected_count)
        self._set_event(
            event,
            SensorAvailability.ERROR,
            observed_at_ns=observed_at_ns,
        )

    def submit(
        self,
        observation: AudioFrameObservation,
        *,
        now_ns: int,
    ) -> AudioCaptureAdmission | None:
        rebuilt = rebuild_observation(observation)
        if type(rebuilt) is not AudioFrameObservation:
            raise HeadAudioValidationError(
                "audio adapter input is not compact audio evidence"
            )
        with self._lock:
            if self._state is not AudioLifecycleState.ACTIVE:
                self._reject(
                    AudioDiagnosticEvent.LIFECYCLE_INACTIVE,
                    rebuilt.observed_at_ns,
                )
                return None
            assert self._source is not None
            assert self._session_id is not None
            requirement = self._source.requirement()
            if rebuilt.session_id != self._session_id:
                self._reject(
                    AudioDiagnosticEvent.SESSION_MISMATCH,
                    rebuilt.observed_at_ns,
                )
                return None
            if not requirement.matches_unsealed(rebuilt):
                event = (
                    AudioDiagnosticEvent.WRONG_FRAME
                    if rebuilt.sensor.sensor_id == self._source.microphone.sensor_id
                    and rebuilt.sensor.frame_id != self._source.microphone.frame_id
                    else AudioDiagnosticEvent.WRONG_FORMAT
                    if (
                        rebuilt.sample_rate_hz != self._source.sample_rate_hz
                        or rebuilt.channel_count != self._source.channel_count
                        or rebuilt.encoding != self._source.encoding
                    )
                    else AudioDiagnosticEvent.WRONG_SOURCE
                )
                self._reject(event, rebuilt.observed_at_ns)
                return None
            if type(now_ns) is not int or not 0 <= now_ns <= MAX_AUDIO_COUNT:
                raise HeadAudioValidationError("audio current source time is invalid")
            if (
                rebuilt.observed_at_ns > now_ns + self._future_skew_ns
                or rebuilt.result_at_ns > now_ns + self._future_skew_ns
            ):
                self._reject(
                    AudioDiagnosticEvent.FUTURE_FRAME,
                    rebuilt.observed_at_ns,
                )
                return None
            if rebuilt.observed_at_ns < now_ns - self._retention_ns:
                self._reject(
                    AudioDiagnosticEvent.STALE_FRAME,
                    rebuilt.observed_at_ns,
                )
                return None
            if self._last_accepted_at_ns is not None:
                if rebuilt.observed_at_ns < self._last_accepted_at_ns:
                    self._reject(
                        AudioDiagnosticEvent.SOURCE_CLOCK_REGRESSION,
                        rebuilt.observed_at_ns,
                    )
                    return None
                if rebuilt.observed_at_ns == self._last_accepted_at_ns:
                    self._duplicate_count = self._increment(self._duplicate_count)
                    self._set_event(
                        AudioDiagnosticEvent.DUPLICATE_FRAME,
                        SensorAvailability.DEGRADED,
                        observed_at_ns=rebuilt.observed_at_ns,
                    )
                    return None
            self._last_accepted_at_ns = rebuilt.observed_at_ns
            self._accepted_count = self._increment(self._accepted_count)
            self._set_event(
                AudioDiagnosticEvent.FRAME_ACCEPTED,
                SensorAvailability.AVAILABLE,
                observed_at_ns=rebuilt.observed_at_ns,
            )
            health = SensorHealthObservation(
                robot_id=rebuilt.robot_id,
                sensor=rebuilt.sensor,
                availability=SensorAvailability.AVAILABLE,
                observed_at_ns=rebuilt.observed_at_ns,
                provenance=rebuilt.provenance,
                evidence_detail="audio_capture_active",
            )
            return _issue_admission(
                frame=rebuilt,
                health=health,
                requirement=requirement,
                diagnostics=self._diagnostics,
            )
