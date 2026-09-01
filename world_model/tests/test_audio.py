from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import math

import pytest

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    AudioFrameObservation,
    ObservationIdentityError,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    WorldModelProjector,
    WorldModelValidationError,
    rebuild_observation,
)

from helpers import TEST_PROVENANCE, catalog


AUDIO_SENSOR = SensorIdentity(
    "ayyo.microphone.head.v1", SensorKind.MICROPHONE, "head_microphone_frame"
)


def audio(**overrides) -> AudioFrameObservation:
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": AUDIO_SENSOR,
        "producer_id": "ayyo.audio.test-adapter.v1",
        "source_manifest_id": "audio-source-sha256-" + "1" * 64,
        "session_id": "audio-session-sha256-" + "2" * 64,
        "sample_rate_hz": 16_000,
        "channel_count": 1,
        "encoding": "pcm_s16le",
        "frame_count": 160,
        "sample_count": 160,
        "duration_ns": 10_000_000,
        "data_size_bytes": 320,
        "peak_amplitude": 4_000,
        "rms_amplitude": 0.07,
        "payload_sha256": "3" * 64,
        "observed_at_ns": 100,
        "result_at_ns": 101,
        "provenance": TEST_PROVENANCE,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return AudioFrameObservation(**values)


def test_audio_observation_is_compact_immutable_and_rebuildable() -> None:
    observation = audio()
    assert observation == rebuild_observation(observation)
    assert not hasattr(observation, "data")
    assert "data" not in observation.payload_document()
    with pytest.raises(FrozenInstanceError):
        observation.frame_count = 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"sensor": SensorIdentity("bad.audio.v1", SensorKind.IMU, "bad_frame")},
        {"sample_rate_hz": 0},
        {"sample_rate_hz": 96_000},
        {"channel_count": 2},
        {"encoding": "pcm_f32le"},
        {"frame_count": 0, "sample_count": 0, "duration_ns": 0, "data_size_bytes": 0},
        {"sample_count": 159},
        {"duration_ns": 9_000_000},
        {"data_size_bytes": 319},
        {"peak_amplitude": 32_769},
        {"rms_amplitude": math.nan},
        {"rms_amplitude": math.inf},
        {"payload_sha256": "bad"},
        {"result_at_ns": 99},
        {"session_id": "audio-session-sha256-" + "g" * 64},
    ],
)
def test_audio_observation_rejects_malformed_compact_state(overrides) -> None:
    with pytest.raises(WorldModelValidationError):
        audio(**overrides)


def test_audio_identity_substitution_is_rejected() -> None:
    with pytest.raises(ObservationIdentityError):
        audio(observation_id="world-observation-" + "0" * 64)


def test_projector_exposes_non_mutating_compact_audio_state() -> None:
    observation = audio()
    projector = WorldModelProjector(catalog(), (AUDIO_SENSOR,))
    arguments = dict(
        now_ns=100,
        fresh_for_ns=10,
        joint_evidence={},
        pose_evidence=None,
        entity_evidence={},
        audio_evidence={AUDIO_SENSOR.sensor_id: observation},
    )
    first = projector.project(**arguments)
    second = projector.project(**arguments)
    assert first == second
    assert len(first.robot.audio_states) == 1
    document = first.robot.document()
    payload = document["audio_states"][0]["payload"]
    assert payload["payload_sha256"] == "3" * 64
    assert "data" not in payload


def test_projector_rejects_audio_key_identity_conflict() -> None:
    alternate = SensorIdentity(
        "ayyo.microphone.alternate.v1",
        SensorKind.MICROPHONE,
        "alternate_microphone_frame",
    )
    projector = WorldModelProjector(catalog(), (AUDIO_SENSOR, alternate))
    with pytest.raises(WorldModelValidationError, match="key and sensor"):
        projector.project(
            now_ns=100,
            fresh_for_ns=10,
            joint_evidence={},
            pose_evidence=None,
            entity_evidence={},
            audio_evidence={alternate.sensor_id: audio()},
        )


def test_audio_state_contains_no_control_authority() -> None:
    forbidden = {"command", "execute", "motion", "movement", "skill", "safety"}
    assert not forbidden & set(audio().payload_document())
