"""Public transport-neutral Ayyo head-audio foundation API."""

from .adapter import AudioLifecycleAdapter, AudioSourceRegistry
from .errors import (
    HeadAudioConfigurationError,
    HeadAudioError,
    HeadAudioLifecycleError,
    HeadAudioValidationError,
)
from .fixtures import (
    HEAD_MICROPHONE_SENSOR,
    TEST_AUDIO_PROVENANCE,
    TEST_AUDIO_SOURCE_ID,
    AudioFixtureBundle,
    audio_test_fixture_bundle,
    fixture_audio_bytes,
    fixture_audio_observation,
)
from .models import (
    AUDIO_INTERFACE,
    AUDIO_TOPIC,
    MAX_AUDIO_COUNT,
    MAX_AUDIO_SOURCES,
    PCM_S16LE,
    TEST_CHANNEL_COUNT,
    TEST_FRAME_COUNT,
    TEST_SAMPLE_RATE_HZ,
    AudioCaptureAdmission,
    AudioDiagnosticEvent,
    AudioDiagnostics,
    AudioLifecycleState,
    AudioSourceClassification,
    AudioSourceManifest,
    AudioTrustRequirement,
    audio_session_id,
    summarize_audio_payload,
)

__all__ = [name for name in globals() if not name.startswith("_")]
