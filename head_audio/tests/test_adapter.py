from __future__ import annotations

from dataclasses import replace

import pytest

from ayyo_head_audio import (
    AudioDiagnosticEvent,
    AudioLifecycleState,
    AudioSourceRegistry,
    HeadAudioConfigurationError,
    HeadAudioLifecycleError,
    audio_test_fixture_bundle,
    fixture_audio_observation,
)
from ayyo_world_model import SensorAvailability

from helpers import configured_audio_adapter


def test_registry_is_idempotent_and_conflicts_fail_closed() -> None:
    bundle, registry, _ = configured_audio_adapter()
    assert not registry.register(bundle.source)
    with pytest.raises(HeadAudioConfigurationError, match="conflicts"):
        registry.register(
            replace(bundle.source, producer_version="2.0.0", manifest_id=None)
        )
    with pytest.raises(HeadAudioConfigurationError, match="not explicitly"):
        registry.resolve("ros.audio.head.unknown.v1")


def test_active_adapter_issues_compact_sealed_admission_and_health() -> None:
    bundle, _, adapter = configured_audio_adapter()
    session = adapter.activate()
    admission = adapter.submit(
        fixture_audio_observation(bundle, session, 1_000), now_ns=1_000
    )
    assert admission is not None
    assert admission.frame.session_id == session
    assert admission.health.availability is SensorAvailability.AVAILABLE
    assert admission.diagnostics.retained_payload_bytes == 0
    assert admission.diagnostics.event is AudioDiagnosticEvent.FRAME_ACCEPTED
    assert adapter.diagnostics.accepted_count == 1


def test_inactive_old_session_and_reactivation_are_isolated() -> None:
    bundle, _, adapter = configured_audio_adapter()
    first = adapter.activate()
    adapter.deactivate()
    assert adapter.submit(
        fixture_audio_observation(bundle, first, 1_000), now_ns=1_000
    ) is None
    second = adapter.activate()
    assert second != first
    assert adapter.submit(
        fixture_audio_observation(bundle, first, 1_001), now_ns=1_001
    ) is None
    assert adapter.submit(
        fixture_audio_observation(bundle, second, 1_002), now_ns=1_002
    ) is not None


def test_wrong_source_fields_reject_without_poisoning_recovery() -> None:
    bundle, _, adapter = configured_audio_adapter()
    session = adapter.activate()
    wrong = fixture_audio_observation(
        bundle, session, 1_000, producer_id="ayyo.audio.spoofed.v1"
    )
    assert adapter.submit(wrong, now_ns=1_000) is None
    assert adapter.diagnostics.event is AudioDiagnosticEvent.WRONG_SOURCE
    assert adapter.submit(
        fixture_audio_observation(bundle, session, 1_001), now_ns=1_001
    ) is not None


def test_stale_future_regressed_and_duplicate_evidence_fail_closed() -> None:
    bundle = audio_test_fixture_bundle()
    registry = AudioSourceRegistry()
    registry.register(bundle.source)
    from ayyo_head_audio import AudioLifecycleAdapter

    adapter = AudioLifecycleAdapter(registry, retention_ns=1_000, future_skew_ns=10)
    adapter.configure(bundle.source.source_id)
    session = adapter.activate()
    assert adapter.submit(
        fixture_audio_observation(bundle, session, 1_000), now_ns=2_001
    ) is None
    assert adapter.diagnostics.event is AudioDiagnosticEvent.STALE_FRAME
    assert adapter.submit(
        fixture_audio_observation(bundle, session, 2_020), now_ns=2_000
    ) is None
    assert adapter.diagnostics.event is AudioDiagnosticEvent.FUTURE_FRAME
    assert adapter.submit(
        fixture_audio_observation(bundle, session, 2_000), now_ns=2_000
    ) is not None
    assert adapter.submit(
        fixture_audio_observation(bundle, session, 2_000), now_ns=2_000
    ) is None
    assert adapter.diagnostics.event is AudioDiagnosticEvent.DUPLICATE_FRAME
    assert adapter.submit(
        fixture_audio_observation(bundle, session, 1_999), now_ns=2_000
    ) is None
    assert adapter.diagnostics.event is AudioDiagnosticEvent.SOURCE_CLOCK_REGRESSION


def test_active_source_identity_cannot_be_reconfigured() -> None:
    bundle, _, adapter = configured_audio_adapter()
    adapter.activate()
    with pytest.raises(HeadAudioLifecycleError, match="inactive"):
        adapter.configure(bundle.source.source_id)


def test_deactivation_cleanup_and_shutdown_release_all_session_state() -> None:
    _, _, adapter = configured_audio_adapter()
    adapter.activate()
    adapter.deactivate()
    assert adapter.active_session_id is None
    adapter.cleanup()
    assert adapter.state is AudioLifecycleState.UNCONFIGURED
    assert adapter.source is None
    adapter.shutdown()
    assert adapter.state is AudioLifecycleState.FINALIZED
    assert adapter.source is None
    assert adapter.active_session_id is None
    assert adapter.diagnostics.retained_payload_bytes == 0
    with pytest.raises(HeadAudioLifecycleError):
        adapter.activate()
