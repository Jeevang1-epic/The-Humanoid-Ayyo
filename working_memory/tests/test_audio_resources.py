from __future__ import annotations

from ayyo_head_audio import (
    AudioLifecycleAdapter,
    AudioSourceRegistry,
    audio_test_fixture_bundle,
    fixture_audio_observation,
)
from ayyo_working_memory import (
    IngestionReason,
    IngestionStatus,
    StateKey,
    StateKeyKind,
    WorkingMemory,
    WorkingMemoryConfig,
    WorkingMemoryFreshness,
)
from ayyo_world_model import AYYO_ROBOT_ID, JointContract, RobotJointCatalog


def frame_at(observed_at_ns: int):
    bundle = audio_test_fixture_bundle()
    registry = AudioSourceRegistry()
    registry.register(bundle.source)
    adapter = AudioLifecycleAdapter(registry)
    adapter.configure(bundle.source.source_id)
    session = adapter.activate()
    admission = adapter.submit(
        fixture_audio_observation(bundle, session, observed_at_ns),
        now_ns=observed_at_ns,
    )
    assert admission is not None
    return bundle, admission.frame


def memory(bundle, *, recent_capacity: int = 4) -> WorkingMemory:
    catalog = RobotJointCatalog(
        robot_id=AYYO_ROBOT_ID,
        joints=(
            JointContract("neck_yaw_joint", "revolute", -1.2, 1.2, 1.5, 8.0),
        ),
    )
    return WorkingMemory(
        catalog,
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=bundle.source.provenance.clock,
            allowed_provenance=(bundle.source.provenance,),
            sensors=(bundle.source.microphone,),
            freshness_ns=10,
            retention_ttl_ns=100,
            permitted_future_skew_ns=0,
            recent_evidence_capacity=recent_capacity,
            environment_entity_capacity=1,
        ),
    )


def test_compact_audio_enters_current_memory_and_world_projection() -> None:
    bundle, frame = frame_at(1_000)
    store = memory(bundle)
    result = store.ingest(frame, now_ns=1_000, received_at_monotonic_ns=1)
    assert result.status is IngestionStatus.ACCEPTED
    assert result.updated_keys == (
        StateKey(StateKeyKind.ROBOT_AUDIO, bundle.source.microphone.sensor_id),
    )
    snapshot = store.current_snapshot(now_ns=1_000)
    assert len(snapshot.robot.audio_states) == 1
    assert snapshot.robot.audio_states[0].observation == frame
    assert not hasattr(snapshot.robot.audio_states[0].observation, "data")
    assert store.stats(now_ns=1_000).current_audio_count == 1


def test_duplicate_audio_does_not_grow_memory() -> None:
    bundle, frame = frame_at(1_000)
    store = memory(bundle)
    assert store.ingest(
        frame, now_ns=1_000, received_at_monotonic_ns=1
    ).status is IngestionStatus.ACCEPTED
    duplicate = store.ingest(
        frame, now_ns=1_000, received_at_monotonic_ns=2
    )
    assert duplicate.status is IngestionStatus.DUPLICATE
    assert duplicate.reason is IngestionReason.DUPLICATE_OBSERVATION
    stats = store.stats(now_ns=1_000)
    assert stats.current_audio_count == 1
    assert stats.recent_evidence_count == 1


def test_recent_audio_history_is_hard_bounded() -> None:
    bundle, _ = frame_at(1_000)
    store = memory(bundle, recent_capacity=3)
    for index in range(10):
        _, frame = frame_at(1_000 + index)
        assert store.ingest(
            frame,
            now_ns=1_000 + index,
            received_at_monotonic_ns=index,
        ).status is IngestionStatus.ACCEPTED
    stats = store.stats(now_ns=1_009)
    assert stats.current_audio_count == 1
    assert stats.recent_evidence_count == 3
    assert stats.retained_unique_observation_count == 3


def test_stale_audio_disappears_and_cannot_resurrect() -> None:
    bundle, frame = frame_at(1_000)
    store = memory(bundle)
    store.ingest(frame, now_ns=1_000, received_at_monotonic_ns=1)
    assert store.current_snapshot(now_ns=1_101).robot.audio_states == ()
    rejected = store.ingest(frame, now_ns=1_101, received_at_monotonic_ns=2)
    assert rejected.reason is IngestionReason.EXPIRED_OBSERVATION


def test_audio_freshness_uses_source_acquisition_time() -> None:
    bundle, frame = frame_at(1_000)
    store = memory(bundle)
    key = StateKey(StateKeyKind.ROBOT_AUDIO, bundle.source.microphone.sensor_id)
    store.ingest(frame, now_ns=1_000, received_at_monotonic_ns=1)
    assert store.query_freshness(
        key, now_ns=1_011
    ).freshness is WorkingMemoryFreshness.STALE
    assert store.query_freshness(
        key, now_ns=1_101
    ).freshness is WorkingMemoryFreshness.UNKNOWN


def test_reset_clears_audio_and_time_epoch() -> None:
    bundle, frame = frame_at(1_000)
    store = memory(bundle)
    store.ingest(frame, now_ns=1_000, received_at_monotonic_ns=1)
    store.reset()
    assert store.current_snapshot(now_ns=1).robot.audio_states == ()
    assert store.stats(now_ns=1).current_audio_count == 0
