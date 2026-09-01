"""Lifecycle-managed bounded exact-acquisition-time RGB-D synchronizer."""

from __future__ import annotations

from hashlib import sha256
from threading import RLock

from ayyo_world_model import (
    DepthFrameObservation,
    FusedRgbdObservation,
    SensorAvailability,
    VisualFrameObservation,
    rebuild_observation,
)

from .errors import (
    RgbdFusionConfigurationError,
    RgbdFusionLifecycleError,
    RgbdFusionValidationError,
)
from .models import (
    MAX_RGBD_COUNT,
    MAX_RGBD_PENDING_PER_STREAM,
    RgbdFusionAdmission,
    RgbdFusionDiagnostics,
    RgbdFusionEvent,
    RgbdFusionLifecycleState,
    RgbdFusionRequirement,
    _issue_admission,
)


def _session(prefix: str, requirement_id: str, epoch: int) -> str:
    digest = sha256(f"{prefix}|{requirement_id}|{epoch}".encode("ascii")).hexdigest()
    return f"{prefix}-sha256-{digest}"


class RgbdFusionLifecycleAdapter:
    """Pair compact observations by exact trusted source time within hard bounds."""

    __slots__ = (
        "_accepted_count",
        "_depth_session_id",
        "_duplicate_count",
        "_epoch",
        "_evicted_count",
        "_future_skew_ns",
        "_last_accepted_at_ns",
        "_last_depth_at_ns",
        "_last_rgb_at_ns",
        "_lock",
        "_pair_wait_ns",
        "_pending_depth",
        "_pending_rgb",
        "_rejected_count",
        "_requirement",
        "_retention_ns",
        "_rgb_session_id",
        "_state",
        "_synchronization_session_id",
        "_event",
    )

    def __init__(
        self,
        *,
        pair_wait_ns: int = 200_000_000,
        retention_ns: int = 2_000_000_000,
        future_skew_ns: int = 50_000_000,
    ) -> None:
        if (
            type(pair_wait_ns) is not int
            or type(retention_ns) is not int
            or type(future_skew_ns) is not int
            or not 0 <= pair_wait_ns < retention_ns <= 300_000_000_000
            or not 0 <= future_skew_ns <= 1_000_000_000
        ):
            raise RgbdFusionConfigurationError("RGB-D synchronization bounds are invalid")
        self._pair_wait_ns = pair_wait_ns
        self._retention_ns = retention_ns
        self._future_skew_ns = future_skew_ns
        self._requirement: RgbdFusionRequirement | None = None
        self._state = RgbdFusionLifecycleState.UNCONFIGURED
        self._epoch = 0
        self._rgb_session_id: str | None = None
        self._depth_session_id: str | None = None
        self._synchronization_session_id: str | None = None
        self._pending_rgb: dict[int, VisualFrameObservation] = {}
        self._pending_depth: dict[int, DepthFrameObservation] = {}
        self._last_accepted_at_ns: int | None = None
        self._last_rgb_at_ns: int | None = None
        self._last_depth_at_ns: int | None = None
        self._accepted_count = 0
        self._rejected_count = 0
        self._duplicate_count = 0
        self._evicted_count = 0
        self._event = RgbdFusionEvent.UNCONFIGURED
        self._lock = RLock()

    @property
    def state(self) -> RgbdFusionLifecycleState:
        with self._lock:
            return self._state

    @property
    def requirement(self) -> RgbdFusionRequirement | None:
        with self._lock:
            return self._requirement

    @property
    def active_rgb_session_id(self) -> str | None:
        with self._lock:
            return self._rgb_session_id

    @property
    def active_synchronization_session_id(self) -> str | None:
        with self._lock:
            return self._synchronization_session_id

    @property
    def diagnostics(self) -> RgbdFusionDiagnostics:
        with self._lock:
            return RgbdFusionDiagnostics(
                lifecycle_state=self._state,
                event=self._event,
                synchronization_session_id=self._synchronization_session_id,
                rgb_session_id=self._rgb_session_id,
                depth_session_id=self._depth_session_id,
                accepted_count=self._accepted_count,
                rejected_count=self._rejected_count,
                duplicate_count=self._duplicate_count,
                evicted_count=self._evicted_count,
                pending_rgb_count=len(self._pending_rgb),
                pending_depth_count=len(self._pending_depth),
            )

    @staticmethod
    def _increment(value: int) -> int:
        return min(value + 1, MAX_RGBD_COUNT)

    def configure(self, requirement: RgbdFusionRequirement) -> None:
        if type(requirement) is not RgbdFusionRequirement:
            raise RgbdFusionConfigurationError("RGB-D synchronization requirement is invalid")
        with self._lock:
            if self._state not in {
                RgbdFusionLifecycleState.UNCONFIGURED,
                RgbdFusionLifecycleState.INACTIVE,
            }:
                raise RgbdFusionLifecycleError(
                    "RGB-D synchronizer cannot configure while active"
                )
            self._requirement = requirement
            self._state = RgbdFusionLifecycleState.INACTIVE
            self._clear_pending()
            self._event = RgbdFusionEvent.CONFIGURED

    def activate(self, *, depth_session_id: str) -> tuple[str, str]:
        with self._lock:
            if (
                self._state is not RgbdFusionLifecycleState.INACTIVE
                or self._requirement is None
            ):
                raise RgbdFusionLifecycleError(
                    "RGB-D synchronizer can only activate when configured"
                )
            if type(depth_session_id) is not str or not depth_session_id:
                raise RgbdFusionLifecycleError(
                    "RGB-D activation requires the active depth session"
                )
            self._epoch = self._increment(self._epoch)
            self._rgb_session_id = _session(
                "rgbd-rgb-session",
                self._requirement.requirement_id,
                self._epoch,
            )
            self._synchronization_session_id = _session(
                "rgbd-synchronization-session",
                self._requirement.requirement_id,
                self._epoch,
            )
            self._depth_session_id = depth_session_id
            self._last_accepted_at_ns = None
            self._clear_pending()
            self._state = RgbdFusionLifecycleState.ACTIVE
            self._event = RgbdFusionEvent.ACTIVE
            return self._rgb_session_id, self._synchronization_session_id

    def deactivate(self) -> None:
        with self._lock:
            if self._state is not RgbdFusionLifecycleState.ACTIVE:
                raise RgbdFusionLifecycleError(
                    "RGB-D synchronizer can only deactivate while active"
                )
            self._clear_pending()
            self._rgb_session_id = None
            self._depth_session_id = None
            self._synchronization_session_id = None
            self._last_accepted_at_ns = None
            self._state = RgbdFusionLifecycleState.INACTIVE
            self._event = RgbdFusionEvent.INACTIVE

    def cleanup(self) -> None:
        with self._lock:
            if self._state is RgbdFusionLifecycleState.ACTIVE:
                raise RgbdFusionLifecycleError(
                    "RGB-D synchronizer must deactivate before cleanup"
                )
            if self._state is RgbdFusionLifecycleState.FINALIZED:
                raise RgbdFusionLifecycleError("finalized RGB-D synchronizer cannot clean up")
            self._clear_pending()
            self._requirement = None
            self._state = RgbdFusionLifecycleState.UNCONFIGURED
            self._event = RgbdFusionEvent.UNCONFIGURED

    def shutdown(self) -> None:
        with self._lock:
            self._clear_pending()
            self._requirement = None
            self._rgb_session_id = None
            self._depth_session_id = None
            self._synchronization_session_id = None
            self._last_accepted_at_ns = None
            self._state = RgbdFusionLifecycleState.FINALIZED
            self._event = RgbdFusionEvent.SHUTDOWN

    def _clear_pending(self) -> None:
        self._pending_rgb.clear()
        self._pending_depth.clear()
        self._last_rgb_at_ns = None
        self._last_depth_at_ns = None

    def _reject(self, event: RgbdFusionEvent) -> None:
        self._rejected_count = self._increment(self._rejected_count)
        self._event = event

    def _validate_time(self, observed_at_ns: int, now_ns: int) -> bool:
        if type(now_ns) is not int or now_ns < 0:
            raise RgbdFusionValidationError("RGB-D current source time is invalid")
        if observed_at_ns > now_ns + self._future_skew_ns:
            self._reject(RgbdFusionEvent.FUTURE_EVIDENCE)
            return False
        if observed_at_ns < now_ns - self._retention_ns:
            self._reject(RgbdFusionEvent.STALE_EVIDENCE)
            return False
        if self._last_accepted_at_ns is not None:
            if observed_at_ns < self._last_accepted_at_ns:
                self._reject(RgbdFusionEvent.REGRESSED_EVIDENCE)
                return False
            if observed_at_ns == self._last_accepted_at_ns:
                self._duplicate_count = self._increment(self._duplicate_count)
                self._event = RgbdFusionEvent.DUPLICATE_EVIDENCE
                return False
        return True

    def _evict_pending(self, newest_ns: int) -> None:
        evicted_before = self._evicted_count
        cutoff = newest_ns - self._pair_wait_ns
        for pending in (self._pending_rgb, self._pending_depth):
            for time_ns in tuple(value for value in pending if value < cutoff):
                del pending[time_ns]
                self._evicted_count = self._increment(self._evicted_count)
            while len(pending) > MAX_RGBD_PENDING_PER_STREAM:
                del pending[min(pending)]
                self._evicted_count = self._increment(self._evicted_count)
        if self._evicted_count != evicted_before:
            self._event = RgbdFusionEvent.PENDING_EVICTED

    def _validate_stream_time(
        self,
        observed_at_ns: int,
        last_observed_at_ns: int | None,
    ) -> bool:
        if last_observed_at_ns is None:
            return True
        if observed_at_ns < last_observed_at_ns:
            self._reject(RgbdFusionEvent.REGRESSED_EVIDENCE)
            return False
        if observed_at_ns == last_observed_at_ns:
            self._duplicate_count = self._increment(self._duplicate_count)
            self._event = RgbdFusionEvent.DUPLICATE_EVIDENCE
            return False
        return True

    def submit_rgb(
        self,
        observation: VisualFrameObservation,
        *,
        now_ns: int,
    ) -> RgbdFusionAdmission | None:
        rebuilt = rebuild_observation(observation)
        if type(rebuilt) is not VisualFrameObservation:
            raise RgbdFusionValidationError("RGB-D RGB input is not a compact RGB observation")
        with self._lock:
            if self._state is not RgbdFusionLifecycleState.ACTIVE:
                self._reject(RgbdFusionEvent.INACTIVE)
                return None
            assert self._requirement is not None
            if not self._requirement.matches_rgb(rebuilt):
                self._reject(RgbdFusionEvent.WRONG_COMPONENT)
                return None
            if not self._validate_time(rebuilt.observed_at_ns, now_ns):
                return None
            existing = self._pending_rgb.get(rebuilt.observed_at_ns)
            if existing is not None:
                if existing == rebuilt:
                    self._duplicate_count = self._increment(self._duplicate_count)
                else:
                    self._reject(RgbdFusionEvent.DUPLICATE_EVIDENCE)
                return None
            if not self._validate_stream_time(
                rebuilt.observed_at_ns,
                self._last_rgb_at_ns,
            ):
                return None
            self._pending_rgb[rebuilt.observed_at_ns] = rebuilt
            self._last_rgb_at_ns = rebuilt.observed_at_ns
            self._evict_pending(rebuilt.observed_at_ns)
            return self._try_pair(rebuilt.observed_at_ns, result_at_ns=now_ns)

    def submit_depth(
        self,
        observation: DepthFrameObservation,
        *,
        now_ns: int,
    ) -> RgbdFusionAdmission | None:
        rebuilt = rebuild_observation(observation)
        if type(rebuilt) is not DepthFrameObservation:
            raise RgbdFusionValidationError("RGB-D depth input is not a compact depth observation")
        with self._lock:
            if self._state is not RgbdFusionLifecycleState.ACTIVE:
                self._reject(RgbdFusionEvent.INACTIVE)
                return None
            assert self._requirement is not None
            if not self._requirement.matches_depth(rebuilt):
                self._reject(RgbdFusionEvent.WRONG_COMPONENT)
                return None
            if rebuilt.session_id != self._depth_session_id:
                self._reject(RgbdFusionEvent.SESSION_MISMATCH)
                return None
            if not self._validate_time(rebuilt.observed_at_ns, now_ns):
                return None
            existing = self._pending_depth.get(rebuilt.observed_at_ns)
            if existing is not None:
                if existing == rebuilt:
                    self._duplicate_count = self._increment(self._duplicate_count)
                else:
                    self._reject(RgbdFusionEvent.DUPLICATE_EVIDENCE)
                return None
            if not self._validate_stream_time(
                rebuilt.observed_at_ns,
                self._last_depth_at_ns,
            ):
                return None
            self._pending_depth[rebuilt.observed_at_ns] = rebuilt
            self._last_depth_at_ns = rebuilt.observed_at_ns
            self._evict_pending(rebuilt.observed_at_ns)
            return self._try_pair(rebuilt.observed_at_ns, result_at_ns=now_ns)

    def _try_pair(self, observed_at_ns: int, *, result_at_ns: int) -> RgbdFusionAdmission | None:
        rgb = self._pending_rgb.get(observed_at_ns)
        depth = self._pending_depth.get(observed_at_ns)
        if rgb is None or depth is None:
            self._event = RgbdFusionEvent.MISSING_COUNTERPART
            return None
        del self._pending_rgb[observed_at_ns]
        del self._pending_depth[observed_at_ns]
        assert self._requirement is not None
        assert self._rgb_session_id is not None
        assert self._depth_session_id is not None
        assert self._synchronization_session_id is not None
        observation = FusedRgbdObservation(
            robot_id=self._requirement.robot_id,
            sensor=self._requirement.fusion_sensor,
            rgb_observation=rgb,
            depth_observation=depth,
            rgb_producer_id=self._requirement.rgb_producer_id,
            depth_producer_id=self._requirement.depth_producer_id,
            rgb_source_fingerprint_sha256=(
                self._requirement.rgb_source_fingerprint_sha256
            ),
            depth_source_fingerprint_sha256=(
                self._requirement.depth_source_fingerprint_sha256
            ),
            rgb_session_id=self._rgb_session_id,
            depth_session_id=self._depth_session_id,
            rgb_camera_frame_id=self._requirement.rgb_camera_frame_id,
            depth_camera_frame_id=self._requirement.depth_camera_frame_id,
            pairing_policy_id=self._requirement.pairing_policy_id,
            pairing_policy_version=self._requirement.pairing_policy_version,
            synchronization_session_id=self._synchronization_session_id,
            result_at_ns=max(result_at_ns, observed_at_ns),
            provenance=self._requirement.fusion_provenance,
            availability=SensorAvailability.AVAILABLE,
        )
        self._last_accepted_at_ns = observed_at_ns
        self._accepted_count = self._increment(self._accepted_count)
        self._event = RgbdFusionEvent.PAIR_ACCEPTED
        return _issue_admission(observation, self._requirement, self.diagnostics)
