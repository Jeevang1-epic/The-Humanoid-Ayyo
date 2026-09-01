"""Deterministic TEST microphone source; it never claims physical hardware."""

from __future__ import annotations

from dataclasses import dataclass
import struct

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    AudioFrameObservation,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorIdentity,
    SensorKind,
)

from .models import (
    AUDIO_INTERFACE,
    PCM_S16LE,
    TEST_CHANNEL_COUNT,
    TEST_FRAME_COUNT,
    TEST_SAMPLE_RATE_HZ,
    AudioSourceClassification,
    AudioSourceManifest,
    summarize_audio_payload,
)


HEAD_MICROPHONE_SENSOR = SensorIdentity(
    "ayyo.microphone.head.v1",
    SensorKind.MICROPHONE,
    "head_microphone_frame",
)
TEST_AUDIO_SOURCE_ID = "ros.audio.head.test-fixture.v1"
TEST_AUDIO_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    TEST_AUDIO_SOURCE_ID,
    ObservationClock.TEST_TIME,
    ObservationTransport.ROS2,
    AUDIO_INTERFACE,
)


@dataclass(frozen=True, slots=True)
class AudioFixtureBundle:
    source: AudioSourceManifest


def audio_test_fixture_bundle() -> AudioFixtureBundle:
    return AudioFixtureBundle(
        source=AudioSourceManifest(
            source_id=TEST_AUDIO_SOURCE_ID,
            robot_id=AYYO_ROBOT_ID,
            microphone=HEAD_MICROPHONE_SENSOR,
            producer_id="ayyo.audio.test-adapter.v1",
            producer_version="1.0.0",
            producer_implementation_sha256="a" * 64,
            provenance=TEST_AUDIO_PROVENANCE,
            classification=AudioSourceClassification.TEST_FIXTURE,
            mount_frame_id=HEAD_MICROPHONE_SENSOR.frame_id,
            sample_rate_hz=TEST_SAMPLE_RATE_HZ,
            channel_count=TEST_CHANNEL_COUNT,
            encoding=PCM_S16LE,
            maximum_frame_count=TEST_FRAME_COUNT,
            maximum_duration_ns=10_000_000,
            maximum_payload_bytes=TEST_FRAME_COUNT * 2,
        )
    )


def fixture_audio_bytes(frame_count: int = TEST_FRAME_COUNT) -> bytes:
    if type(frame_count) is not int or not 1 <= frame_count <= TEST_FRAME_COUNT:
        raise ValueError("fixture audio frame count is outside its TEST bound")
    samples = tuple(((index * 257) % 8_001) - 4_000 for index in range(frame_count))
    return struct.pack(f"<{frame_count}h", *samples)


def fixture_audio_observation(
    bundle: AudioFixtureBundle,
    session_id: str,
    observed_at_ns: int,
    *,
    result_at_ns: int | None = None,
    data: bytes | None = None,
    **overrides,
) -> AudioFrameObservation:
    payload = fixture_audio_bytes() if data is None else data
    return summarize_audio_payload(
        source=bundle.source,
        session_id=session_id,
        observed_at_ns=observed_at_ns,
        result_at_ns=(
            observed_at_ns if result_at_ns is None else result_at_ns
        ),
        frame_count=len(payload) // 2,
        data=payload,
        **overrides,
    )
