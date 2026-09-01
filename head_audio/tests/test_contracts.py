from __future__ import annotations

from dataclasses import replace
import math

import pytest

from ayyo_head_audio import (
    AUDIO_INTERFACE,
    AUDIO_TOPIC,
    HEAD_MICROPHONE_SENSOR,
    PCM_S16LE,
    TEST_AUDIO_SOURCE_ID,
    AudioCaptureAdmission,
    AudioSourceClassification,
    HeadAudioValidationError,
    audio_test_fixture_bundle,
    fixture_audio_bytes,
    fixture_audio_observation,
    summarize_audio_payload,
)
from ayyo_world_model import (
    ObservationSourceKind,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    WorldModelValidationError,
)


SESSION = "audio-session-sha256-" + "1" * 64


def test_audio_identity_format_and_topic_are_exact() -> None:
    assert HEAD_MICROPHONE_SENSOR.sensor_id == "ayyo.microphone.head.v1"
    assert HEAD_MICROPHONE_SENSOR.kind is SensorKind.MICROPHONE
    assert HEAD_MICROPHONE_SENSOR.frame_id == "head_microphone_frame"
    assert AUDIO_TOPIC == "/ayyo/audio/head/microphone/raw"
    assert AUDIO_INTERFACE == "ayyo-interfaces.audio-frame.v1"
    source = audio_test_fixture_bundle().source
    assert source.sample_rate_hz == 16_000
    assert source.channel_count == 1
    assert source.encoding == PCM_S16LE


def test_manifest_identity_is_content_derived_and_deterministic() -> None:
    first = audio_test_fixture_bundle().source
    second = audio_test_fixture_bundle().source
    assert first == second
    assert first.manifest_id.startswith("audio-source-sha256-")
    with pytest.raises(HeadAudioValidationError, match="does not match"):
        replace(first, manifest_id="audio-source-sha256-" + "0" * 64)


def test_test_identity_cannot_substitute_simulated_or_physical_provenance() -> None:
    source = audio_test_fixture_bundle().source
    assert source.classification is AudioSourceClassification.TEST_FIXTURE
    assert source.provenance.source_kind is ObservationSourceKind.TEST_FIXTURE
    with pytest.raises(HeadAudioValidationError, match="cannot substitute"):
        replace(
            source,
            classification=AudioSourceClassification.SIMULATION,
            manifest_id=None,
        )
    with pytest.raises(HeadAudioValidationError, match="cannot claim"):
        replace(source, device_serial="spoofed", manifest_id=None)


def test_payload_is_compacted_and_raw_bytes_are_never_retained() -> None:
    payload = fixture_audio_bytes()
    frame = fixture_audio_observation(
        audio_test_fixture_bundle(), SESSION, 10_000, data=payload
    )
    assert frame.data_size_bytes == len(payload)
    assert frame.sample_count == frame.frame_count == 160
    assert frame.duration_ns == 10_000_000
    assert frame.availability is SensorAvailability.AVAILABLE
    assert 0 <= frame.rms_amplitude <= frame.peak_amplitude / 32_768
    assert not hasattr(frame, "data")
    assert "data" not in frame.payload_document()


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"data": b""}, "nonempty"),
        ({"data": b"\x00"}, "alignment"),
        ({"data": bytes(322)}, "hard bound"),
        ({"encoding": "pcm_f32le"}, "encoding"),
        ({"sample_rate_hz": 0}, "sample rate"),
        ({"sample_rate_hz": 48_000}, "sample rate"),
        ({"channel_count": 0}, "channel count"),
        ({"channel_count": 2}, "channel count"),
        ({"source_id": "ros.audio.head.spoofed.v1"}, "source identity"),
        ({"frame_id": "spoofed_microphone_frame"}, "frame conflicts"),
        ({"claimed_payload_sha256": "0" * 64}, "fingerprint"),
    ],
)
def test_malformed_payload_and_identity_fail_closed(
    overrides: dict[str, object], match: str
) -> None:
    bundle = audio_test_fixture_bundle()
    with pytest.raises(HeadAudioValidationError, match=match):
        fixture_audio_observation(bundle, SESSION, 10_000, **overrides)


@pytest.mark.parametrize("result_at_ns", [0, -1])
def test_result_time_cannot_precede_acquisition(result_at_ns: int) -> None:
    with pytest.raises(WorldModelValidationError, match="times"):
        fixture_audio_observation(
            audio_test_fixture_bundle(), SESSION, 1, result_at_ns=result_at_ns
        )


def test_nonfinite_or_impossible_metrics_fail_closed() -> None:
    frame = fixture_audio_observation(audio_test_fixture_bundle(), SESSION, 10_000)
    with pytest.raises(WorldModelValidationError, match="finite"):
        replace(frame, rms_amplitude=math.nan, observation_id=None, fingerprint=None)
    with pytest.raises(WorldModelValidationError, match="physical bound"):
        replace(frame, rms_amplitude=1.0, observation_id=None, fingerprint=None)


def test_conflicting_microphone_identity_reaches_no_trusted_contract() -> None:
    bundle = audio_test_fixture_bundle()
    spoofed = SensorIdentity(
        "ayyo.microphone.spoofed.v1", SensorKind.MICROPHONE, "head_microphone_frame"
    )
    frame = summarize_audio_payload(
        source=bundle.source,
        session_id=SESSION,
        observed_at_ns=10_000,
        result_at_ns=10_000,
        frame_count=160,
        data=fixture_audio_bytes(),
        microphone=spoofed,
    )
    assert not bundle.source.requirement().matches_unsealed(frame)


def test_admission_seal_is_not_publicly_constructible() -> None:
    frame = fixture_audio_observation(audio_test_fixture_bundle(), SESSION, 10_000)
    with pytest.raises(TypeError):
        AudioCaptureAdmission(  # type: ignore[call-arg]
            frame=frame,
            health=None,
            requirement=audio_test_fixture_bundle().source.requirement(),
            diagnostics=None,
        )


def test_fixture_source_is_obviously_test_only() -> None:
    source = audio_test_fixture_bundle().source
    assert source.source_id == TEST_AUDIO_SOURCE_ID
    assert source.provenance.source_kind is ObservationSourceKind.TEST_FIXTURE
    assert source.device_serial is None
    assert source.device_fingerprint_sha256 is None
