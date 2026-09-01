from __future__ import annotations

from ayyo_head_audio import (
    AudioLifecycleAdapter,
    AudioSourceRegistry,
    audio_test_fixture_bundle,
)


def configured_audio_adapter() -> tuple:
    bundle = audio_test_fixture_bundle()
    registry = AudioSourceRegistry()
    assert registry.register(bundle.source)
    adapter = AudioLifecycleAdapter(registry)
    adapter.configure(bundle.source.source_id)
    return bundle, registry, adapter
