from dataclasses import FrozenInstanceError, replace

import pytest

from ayyo_software_showcase import (
    ShowcaseCapability,
    ShowcaseCapabilityError,
    ShowcaseClassification,
    ShowcaseManifest,
    ShowcaseManifestError,
    ShowcaseNonClaim,
    UnknownShowcaseCapabilityError,
    build_showcase_manifest,
    capability_by_id,
    verify_showcase_capability,
    verify_showcase_catalog,
    verify_showcase_evidence,
    verify_showcase_manifest,
)


def test_live_manifest_is_deterministic_immutable_and_verified():
    first = build_showcase_manifest()
    second = build_showcase_manifest()

    assert first == second
    assert first.manifest_id == second.manifest_id
    assert first.manifest_fingerprint == second.manifest_fingerprint
    assert verify_showcase_manifest(first)
    assert verify_showcase_catalog(first)
    assert all(verify_showcase_capability(item) for item in first.capabilities)
    assert all(verify_showcase_evidence(item) for item in first.evidence)
    with pytest.raises(FrozenInstanceError):
        first.title = "changed"


def test_catalog_covers_reviewed_software_and_explicit_unavailable_boundaries():
    manifest = build_showcase_manifest()
    expected = {
        "perception-and-sensor-evidence",
        "world-model-and-working-memory",
        "bounded-memory-review",
        "context-executive-and-safety",
        "skill-and-runtime-eligibility",
        "ros-gazebo-simulation-foundations",
        "developmental-scenario-harness",
        "teach-mode-evidence",
        "offline-candidate-evaluation",
        "promotion-and-rollback-eligibility",
        "immutable-policy-registry",
        "human-authority-approval-evidence",
        "future-activation-eligibility",
        "production-policy-activation",
        "physical-hardware-validation",
    }

    assert {item.capability_id for item in manifest.capabilities} == expected
    assert tuple(item.sequence_index for item in manifest.capabilities) == tuple(
        range(len(expected))
    )


def test_every_capability_has_one_truthful_primary_classification_and_evidence():
    manifest = build_showcase_manifest()
    evidence_ids = {item.evidence_id for item in manifest.evidence}

    for capability in manifest.capabilities:
        primary = {
            ShowcaseClassification.IMPLEMENTED,
            ShowcaseClassification.NOT_YET_IMPLEMENTED,
        }.intersection(capability.classifications)
        assert len(primary) == 1
        assert capability.evidence_ids
        assert set(capability.evidence_ids) <= evidence_ids
        assert capability.does_not_prove


def test_classification_rejects_duplicates_and_contradictory_primary_states():
    manifest = build_showcase_manifest()
    source = manifest.capabilities[0]

    with pytest.raises(ShowcaseCapabilityError):
        replace(
            source,
            classifications=(
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.IMPLEMENTED,
            ),
        )
    with pytest.raises(ShowcaseCapabilityError):
        replace(
            source,
            classifications=(
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.NOT_YET_IMPLEMENTED,
            ),
        )


def test_capability_rejects_duplicate_evidence_and_non_claims():
    source = build_showcase_manifest().capabilities[0]

    with pytest.raises(ShowcaseCapabilityError):
        replace(source, evidence_ids=(source.evidence_ids[0],) * 2)
    with pytest.raises(ShowcaseCapabilityError):
        replace(
            source,
            does_not_prove=(ShowcaseNonClaim.PHYSICAL_VALIDATION,) * 2,
        )


def test_manifest_rejects_duplicate_capabilities_and_evidence():
    source = build_showcase_manifest()

    with pytest.raises(ShowcaseManifestError):
        ShowcaseManifest(
            title=source.title,
            summary=source.summary,
            capabilities=source.capabilities + (source.capabilities[-1],),
            evidence=source.evidence,
        )
    with pytest.raises(ShowcaseManifestError):
        ShowcaseManifest(
            title=source.title,
            summary=source.summary,
            capabilities=source.capabilities,
            evidence=source.evidence + (source.evidence[-1],),
        )


def test_caller_sequences_are_snapshotted_before_later_mutation():
    source = build_showcase_manifest()
    capabilities = list(source.capabilities)
    evidence = list(source.evidence)
    rebuilt = ShowcaseManifest(
        title=source.title,
        summary=source.summary,
        capabilities=capabilities,
        evidence=evidence,
    )

    capabilities.clear()
    evidence.clear()

    assert rebuilt == source
    assert verify_showcase_catalog(rebuilt)


def test_unknown_capability_lookup_fails_closed():
    manifest = build_showcase_manifest()

    with pytest.raises(UnknownShowcaseCapabilityError, match="unknown"):
        capability_by_id(manifest, "policy-is-active")
    with pytest.raises(UnknownShowcaseCapabilityError, match="unknown"):
        capability_by_id(manifest, "INVALID CAPABILITY")


def test_models_expose_no_active_execution_or_runtime_handle_state():
    forbidden = {
        "active_policy",
        "installed_policy",
        "latest_policy",
        "model_weights",
        "runtime_handle",
        "ros_client",
        "command",
        "executable",
    }
    for model in (ShowcaseCapability, ShowcaseManifest):
        assert forbidden.isdisjoint(model.__annotations__)
