from dataclasses import FrozenInstanceError

import pytest

from ayyo_policy_registry import (
    PolicyRegistrySnapshot,
    PolicyResolutionError,
    RegistrationStatus,
    resolve_policy_version,
    resolve_registered_policy,
    verify_policy_registry_snapshot,
    verify_registered_policy_version,
    verify_registration_request,
    verify_registration_result,
)

from helpers import fixture_registration_bundle, register_bundle


def test_empty_snapshot_is_deterministic_immutable_and_verified():
    first = PolicyRegistrySnapshot()
    second = PolicyRegistrySnapshot([])

    assert first == second
    assert first.registered_versions == ()
    assert verify_policy_registry_snapshot(first)
    with pytest.raises(FrozenInstanceError):
        first.snapshot_id = 'changed'


def test_registration_request_is_exact_deterministic_and_immutable():
    first = fixture_registration_bundle('deterministic')['registration_request']
    second = fixture_registration_bundle('deterministic')['registration_request']

    assert first == second
    assert first.registration_request_id == first.recompute_registration_request_id()
    assert first.registration_request_fingerprint == first.recompute_fingerprint()
    assert verify_registration_request(first)
    with pytest.raises(FrozenInstanceError):
        first.note = 'changed'


def test_valid_registration_preserves_the_complete_identity_chain():
    bundle = fixture_registration_bundle('valid')
    result = register_bundle(bundle)
    record = result.registered_version

    assert result.status is RegistrationStatus.REGISTERED
    assert result.previous_snapshot == bundle['snapshot']
    assert result.updated_snapshot.registered_versions == (record,)
    assert (record.candidate_id, record.candidate_fingerprint) == (
        bundle['candidate'].candidate_id,
        bundle['candidate'].candidate_fingerprint,
    )
    assert (record.evaluation_report_id, record.evaluation_report_fingerprint) == (
        bundle['report'].report_id,
        bundle['report'].report_fingerprint,
    )
    assert (record.promotion_criteria_id, record.promotion_criteria_fingerprint) == (
        bundle['criteria'].criteria_id,
        bundle['criteria'].criteria_fingerprint,
    )
    assert (record.promotion_request_id, record.promotion_request_fingerprint) == (
        bundle['promotion_request'].request_id,
        bundle['promotion_request'].request_fingerprint,
    )
    assert (record.promotion_decision_id, record.promotion_decision_fingerprint) == (
        bundle['decision'].decision_id,
        bundle['decision'].decision_fingerprint,
    )
    assert record.semantic_version == bundle['candidate'].semantic_version
    assert record.policy_family_id == bundle['candidate'].policy_family_id
    assert verify_registered_policy_version(record)
    assert verify_policy_registry_snapshot(result.updated_snapshot)
    assert verify_registration_result(result)


def test_registered_record_and_result_are_immutable():
    result = register_bundle(fixture_registration_bundle('immutable'))

    with pytest.raises(FrozenInstanceError):
        result.registered_version.semantic_version = '9.9.9'
    with pytest.raises(FrozenInstanceError):
        result.updated_snapshot.registered_versions = ()
    with pytest.raises(FrozenInstanceError):
        result.status = RegistrationStatus.ALREADY_REGISTERED


def test_snapshot_copies_mutable_caller_sequence():
    record = register_bundle(fixture_registration_bundle('copy')).registered_version
    caller_versions = [record]
    snapshot = PolicyRegistrySnapshot(caller_versions)

    caller_versions.clear()

    assert snapshot.registered_versions == (record,)
    assert verify_policy_registry_snapshot(snapshot)


def test_read_only_resolution_requires_exact_identity_or_version():
    result = register_bundle(fixture_registration_bundle('resolution'))
    record = result.registered_version
    snapshot = result.updated_snapshot

    assert resolve_registered_policy(
        snapshot,
        record_id=record.record_id,
        record_fingerprint=record.record_fingerprint,
    ) is record
    assert resolve_policy_version(
        snapshot,
        policy_family_id=record.policy_family_id,
        semantic_version_value=record.semantic_version,
    ) is record
    assert resolve_registered_policy(
        snapshot,
        record_id='unknown-record',
        record_fingerprint='unknown-record-sha256-' + '0' * 64,
    ) is None
    assert resolve_policy_version(
        snapshot,
        policy_family_id=record.policy_family_id,
        semantic_version_value='9.9.9',
    ) is None


@pytest.mark.parametrize(
    ('function_name', 'arguments'),
    [
        ('record', {'record_id': '../bad', 'record_fingerprint': 'bad'}),
        ('version', {'policy_family_id': 'bad family', 'semantic_version_value': 'latest'}),
    ],
)
def test_resolution_rejects_malformed_lookup(function_name, arguments):
    snapshot = PolicyRegistrySnapshot()

    with pytest.raises(PolicyResolutionError):
        if function_name == 'record':
            resolve_registered_policy(snapshot, **arguments)
        else:
            resolve_policy_version(snapshot, **arguments)


def test_registry_exposes_no_active_or_latest_pointer():
    snapshot = register_bundle(fixture_registration_bundle('no-pointer')).updated_snapshot

    assert not hasattr(snapshot, 'active_policy')
    assert not hasattr(snapshot, 'latest_policy')
    assert not hasattr(snapshot, 'current_policy')
