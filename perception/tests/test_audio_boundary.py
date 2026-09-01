from __future__ import annotations

from dataclasses import replace

import pytest

from ayyo_head_audio import (
    AudioLifecycleAdapter,
    AudioSourceRegistry,
    audio_test_fixture_bundle,
    fixture_audio_observation,
)
from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    PerceptionConfigurationError,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_world_model import AYYO_ROBOT_ID, ObservationClock


def sealed(observed_at_ns: int = 1_000):
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
    return bundle, adapter, admission


def trust(bundle) -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=bundle.source.provenance.clock,
            sources=(
                PerceptionSourceContract(
                    bundle.source.microphone,
                    bundle.source.provenance,
                ),
            ),
            audio_requirements=(bundle.source.requirement(),),
            freshness_ns=500,
            retention_ttl_ns=2_000,
            permitted_future_skew_ns=10,
        )
    )


def test_every_microphone_source_requires_exact_adapter_requirement() -> None:
    bundle = audio_test_fixture_bundle()
    with pytest.raises(PerceptionConfigurationError, match="every audio source requires"):
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            sources=(
                PerceptionSourceContract(
                    bundle.source.microphone, bundle.source.provenance
                ),
            ),
        )


def test_bare_audio_observation_cannot_bypass_sealed_authorization() -> None:
    bundle, _, admission = sealed()
    result = trust(bundle).admit(
        admission.frame, now_ns=1_000, received_at_monotonic_ns=1
    )
    assert result.status is AdmissionStatus.REJECTED
    assert result.reason is AdmissionReason.AUDIO_NOT_AUTHORIZED


def test_sealed_audio_frame_and_health_are_each_consumed_once() -> None:
    bundle, _, admission = sealed()
    boundary = trust(bundle)
    assert boundary.authorize_audio(admission)
    frame = boundary.admit(
        admission.frame, now_ns=1_000, received_at_monotonic_ns=1
    )
    health = boundary.admit(
        admission.health, now_ns=1_000, received_at_monotonic_ns=2
    )
    assert frame.status is AdmissionStatus.ACCEPTED
    assert health.status is AdmissionStatus.ACCEPTED
    replay = boundary.admit(
        admission.frame, now_ns=1_000, received_at_monotonic_ns=3
    )
    assert replay.reason is AdmissionReason.AUDIO_NOT_AUTHORIZED
    assert boundary.stats().tracked_audio_count == 0


def test_reset_discards_unused_audio_authorization() -> None:
    bundle, _, admission = sealed()
    boundary = trust(bundle)
    assert boundary.authorize_audio(admission)
    boundary.reset()
    result = boundary.admit(
        admission.frame, now_ns=1_000, received_at_monotonic_ns=1
    )
    assert result.reason is AdmissionReason.AUDIO_NOT_AUTHORIZED


def test_spoofed_producer_and_requirement_are_not_authorized() -> None:
    bundle, _, admission = sealed()
    forged_requirement = replace(
        admission.requirement,
        producer_id="ayyo.audio.spoofed.v1",
    )
    object.__setattr__(admission, "requirement", forged_requirement)
    assert not trust(bundle).authorize_audio(admission)


def test_old_session_cannot_gain_authority_after_reactivation() -> None:
    bundle, adapter, first_admission = sealed()
    adapter.deactivate()
    second_session = adapter.activate()
    second_admission = adapter.submit(
        fixture_audio_observation(bundle, second_session, 1_001), now_ns=1_001
    )
    assert second_admission is not None
    assert adapter.submit(first_admission.frame, now_ns=1_001) is None
    boundary = trust(bundle)
    assert boundary.authorize_audio(second_admission)
    result = boundary.admit(
        first_admission.frame, now_ns=1_001, received_at_monotonic_ns=1
    )
    assert result.reason is AdmissionReason.AUDIO_NOT_AUTHORIZED


def test_rejected_bypass_does_not_poison_later_valid_audio() -> None:
    bundle, _, admission = sealed()
    boundary = trust(bundle)
    assert boundary.admit(
        admission.frame, now_ns=1_000, received_at_monotonic_ns=1
    ).status is AdmissionStatus.REJECTED
    assert boundary.authorize_audio(admission)
    assert boundary.admit(
        admission.frame, now_ns=1_000, received_at_monotonic_ns=2
    ).status is AdmissionStatus.ACCEPTED


def test_audio_authorizations_remain_hard_bounded() -> None:
    bundle = audio_test_fixture_bundle()
    boundary = trust(bundle)
    for index in range(40):
        registry = AudioSourceRegistry()
        registry.register(bundle.source)
        adapter = AudioLifecycleAdapter(registry)
        adapter.configure(bundle.source.source_id)
        session = adapter.activate()
        admission = adapter.submit(
            fixture_audio_observation(bundle, session, 10_000 + index),
            now_ns=10_000 + index,
        )
        assert admission is not None
        assert boundary.authorize_audio(admission)
    assert boundary.stats().tracked_audio_count <= 64
