"""Explicit caller-controlled demonstration capture sessions."""

from __future__ import annotations

from .errors import DemonstrationSessionError
from .models import (
    DemonstrationCapturePolicy,
    DemonstrationCaptureResult,
    DemonstrationEpisode,
    DemonstrationEvent,
    DemonstrationOutcome,
    DemonstrationProvenance,
    DemonstrationSourceKind,
    DemonstrationSourceTimeRange,
    MAX_EVENTS_PER_EPISODE,
)


class DemonstrationCaptureSession:
    """Collect only events explicitly supplied by one caller, then seal them."""

    __slots__ = (
        '_events',
        '_finished',
        '_policy',
        '_provenance',
        '_robot_id',
        '_source_kind',
        '_source_time',
    )

    def __init__(
        self,
        *,
        policy: DemonstrationCapturePolicy,
        source_kind: DemonstrationSourceKind,
        robot_id: str | None,
        source_time: DemonstrationSourceTimeRange,
        provenance: DemonstrationProvenance,
    ) -> None:
        self._policy = policy
        self._source_kind = source_kind
        self._robot_id = robot_id
        self._source_time = source_time
        self._provenance = provenance
        self._events: list[DemonstrationEvent] = []
        self._finished = False

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def is_finished(self) -> bool:
        return self._finished

    def append(self, event: DemonstrationEvent) -> None:
        """Append one exact immutable event in caller-declared order."""
        if self._finished:
            raise DemonstrationSessionError('a finished capture session is sealed')
        if type(event) is not DemonstrationEvent:
            raise DemonstrationSessionError('capture accepts only typed events')
        if len(self._events) >= MAX_EVENTS_PER_EPISODE:
            raise DemonstrationSessionError('capture exceeds the event bound')
        if event.sequence_index != len(self._events):
            raise DemonstrationSessionError(
                'capture event index must equal the next explicit sequence index'
            )
        if any(item.event_id == event.event_id for item in self._events):
            raise DemonstrationSessionError('capture event IDs must be unique')
        self._events.append(event)

    def finish(self, outcome: DemonstrationOutcome) -> DemonstrationCaptureResult:
        """Seal the explicit event sequence into an immutable deterministic result."""
        if self._finished:
            raise DemonstrationSessionError('a capture session can finish only once')
        if type(outcome) is not DemonstrationOutcome:
            raise DemonstrationSessionError('capture requires one typed explicit outcome')
        if not self._events:
            raise DemonstrationSessionError('an empty capture session cannot finish')
        episode = DemonstrationEpisode(
            source_kind=self._source_kind,
            robot_id=self._robot_id,
            source_time=self._source_time,
            provenance=self._provenance,
            events=tuple(self._events),
            outcome=outcome,
            capture_policy=self._policy,
        )
        self._finished = True
        return DemonstrationCaptureResult(episode)


class DemonstrationRecorder:
    """Factory for explicit sessions; it performs no background collection."""

    __slots__ = ('_policy',)

    def __init__(self, policy: DemonstrationCapturePolicy | None = None) -> None:
        resolved = policy or DemonstrationCapturePolicy()
        if type(resolved) is not DemonstrationCapturePolicy:
            raise DemonstrationSessionError('recorder policy has an invalid type')
        self._policy = resolved

    @property
    def policy(self) -> DemonstrationCapturePolicy:
        return self._policy

    def begin(
        self,
        *,
        source_kind: DemonstrationSourceKind,
        robot_id: str | None,
        source_time: DemonstrationSourceTimeRange,
        provenance: DemonstrationProvenance,
    ) -> DemonstrationCaptureSession:
        """Begin an inert session from exact caller-supplied source semantics."""
        return DemonstrationCaptureSession(
            policy=self._policy,
            source_kind=source_kind,
            robot_id=robot_id,
            source_time=source_time,
            provenance=provenance,
        )
