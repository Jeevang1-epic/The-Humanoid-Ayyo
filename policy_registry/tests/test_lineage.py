import pytest

from ayyo_policy_registry import (
    MAX_POLICY_FAMILIES,
    MAX_REGISTERED_VERSIONS,
    CandidateRegistrationError,
    PolicyRegistrySnapshot,
    PolicyRegistrySnapshotError,
    RegisteredPolicyVersionError,
    VersionLineageError,
)

from helpers import (
    fingerprint,
    fixture_registration_bundle,
    rebuild_registered_version,
    register_bundle,
)


def test_explicit_registered_parent_establishes_exact_lineage():
    parent_bundle = fixture_registration_bundle('parent', semantic_version='1.0.0')
    parent_result = register_bundle(parent_bundle)
    parent = parent_result.registered_version
    child_bundle = fixture_registration_bundle(
        'child',
        semantic_version='1.1.0',
        parent_candidate_id=parent.candidate_id,
        parent_candidate_fingerprint=parent.candidate_fingerprint,
    )

    child_result = register_bundle(child_bundle, parent_result.updated_snapshot)
    child = child_result.registered_version

    assert (child.parent_candidate_id, child.parent_candidate_fingerprint) == (
        parent.candidate_id,
        parent.candidate_fingerprint,
    )
    assert set(child_result.updated_snapshot.registered_versions) == {parent, child}


def test_semantic_version_order_does_not_infer_parentage():
    newer = fixture_registration_bundle('newer-root', semantic_version='9.0.0')
    older = fixture_registration_bundle('older-root', semantic_version='1.0.0')
    first = register_bundle(newer)
    second = register_bundle(older, first.updated_snapshot)

    assert all(
        record.parent_candidate_id is None
        for record in second.updated_snapshot.registered_versions
    )


def test_unregistered_parent_is_rejected():
    child = fixture_registration_bundle(
        'missing-parent',
        semantic_version='2.0.0',
        parent_candidate_id='missing-parent',
        parent_candidate_fingerprint=fingerprint('missing-parent', 'one'),
    )

    with pytest.raises(VersionLineageError, match='not registered'):
        register_bundle(child)


def test_parent_from_another_policy_family_is_rejected():
    parent = fixture_registration_bundle(
        'family-parent', policy_family_id='ayyo.family-one.v1'
    )
    parent_result = register_bundle(parent)
    child = fixture_registration_bundle(
        'family-child',
        semantic_version='0.2.0',
        policy_family_id='ayyo.family-two.v1',
        parent_candidate_id=parent['candidate'].candidate_id,
        parent_candidate_fingerprint=parent['candidate'].candidate_fingerprint,
    )

    with pytest.raises(VersionLineageError, match='different policy family'):
        register_bundle(child, parent_result.updated_snapshot)


@pytest.mark.parametrize(
    ('field_name', 'replacement'),
    [
        ('input_contract_id', 'ayyo.other-input.v1'),
        ('input_contract_version', '2.0.0'),
        ('output_contract_id', 'ayyo.other-output.v1'),
        ('output_contract_version', '2.0.0'),
    ],
)
def test_parent_with_incompatible_contract_is_rejected(field_name, replacement):
    parent = fixture_registration_bundle('contract-parent')
    parent_result = register_bundle(parent)
    arguments = {
        'semantic_version': '0.2.0',
        'parent_candidate_id': parent['candidate'].candidate_id,
        'parent_candidate_fingerprint': parent['candidate'].candidate_fingerprint,
        field_name: replacement,
    }
    child = fixture_registration_bundle('contract-child', **arguments)

    with pytest.raises(VersionLineageError, match='incompatible policy contracts'):
        register_bundle(child, parent_result.updated_snapshot)


def test_self_parent_record_is_rejected_before_snapshot_creation():
    record = register_bundle(fixture_registration_bundle('self-parent')).registered_version

    with pytest.raises(RegisteredPolicyVersionError, match='parent itself'):
        rebuild_registered_version(
            record,
            parent_candidate_id=record.candidate_id,
            parent_candidate_fingerprint=record.candidate_fingerprint,
        )


def test_direct_lineage_cycle_is_rejected():
    first = register_bundle(
        fixture_registration_bundle('cycle-a', semantic_version='1.0.0')
    ).registered_version
    second = register_bundle(
        fixture_registration_bundle('cycle-b', semantic_version='2.0.0')
    ).registered_version
    first_id = ('candidate-a', fingerprint('candidate', 'a'))
    second_id = ('candidate-b', fingerprint('candidate', 'b'))
    first = rebuild_registered_version(
        first,
        candidate_id=first_id[0],
        candidate_fingerprint=first_id[1],
        parent_candidate_id=second_id[0],
        parent_candidate_fingerprint=second_id[1],
    )
    second = rebuild_registered_version(
        second,
        candidate_id=second_id[0],
        candidate_fingerprint=second_id[1],
        parent_candidate_id=first_id[0],
        parent_candidate_fingerprint=first_id[1],
    )

    with pytest.raises(PolicyRegistrySnapshotError, match='cycle'):
        PolicyRegistrySnapshot((first, second))


def test_snapshot_rejects_wrong_parent_fingerprint():
    parent = register_bundle(fixture_registration_bundle('wrong-parent')).registered_version
    child = register_bundle(
        fixture_registration_bundle('unrelated-child', semantic_version='0.2.0')
    ).registered_version
    child = rebuild_registered_version(
        child,
        parent_candidate_id=parent.candidate_id,
        parent_candidate_fingerprint=fingerprint('wrong-parent', 'fingerprint'),
    )

    with pytest.raises(PolicyRegistrySnapshotError, match='not present'):
        PolicyRegistrySnapshot((parent, child))


def test_snapshot_order_is_canonical_and_input_order_is_not_semantic():
    first = register_bundle(
        fixture_registration_bundle(
            'order-one', semantic_version='1.0.0', policy_family_id='ayyo.family-b.v1'
        )
    ).registered_version
    second = register_bundle(
        fixture_registration_bundle(
            'order-two', semantic_version='1.0.0', policy_family_id='ayyo.family-a.v1'
        )
    ).registered_version

    assert PolicyRegistrySnapshot((first, second)) == PolicyRegistrySnapshot((second, first))


def test_snapshot_rejects_duplicate_record_and_candidate():
    record = register_bundle(fixture_registration_bundle('duplicate')).registered_version

    with pytest.raises(PolicyRegistrySnapshotError, match='duplicate registry record'):
        PolicyRegistrySnapshot((record, record))


def test_snapshot_enforces_registered_version_bound():
    base = register_bundle(fixture_registration_bundle('version-bound')).registered_version
    records = tuple(
        rebuild_registered_version(
            base,
            candidate_id=f'candidate-{index}',
            candidate_fingerprint=fingerprint('candidate', str(index)),
            semantic_version=f'{index}.0.0',
        )
        for index in range(MAX_REGISTERED_VERSIONS + 1)
    )

    with pytest.raises(PolicyRegistrySnapshotError, match='version count'):
        PolicyRegistrySnapshot(records)


def test_snapshot_enforces_policy_family_bound():
    base = register_bundle(fixture_registration_bundle('family-bound')).registered_version
    records = tuple(
        rebuild_registered_version(
            base,
            candidate_id=f'family-candidate-{index}',
            candidate_fingerprint=fingerprint('family-candidate', str(index)),
            policy_family_id=f'ayyo.family-{index}.v1',
        )
        for index in range(MAX_POLICY_FAMILIES + 1)
    )

    with pytest.raises(PolicyRegistrySnapshotError, match='policy-family count'):
        PolicyRegistrySnapshot(records)


def test_snapshot_rejects_conflicting_version_even_for_structurally_valid_records():
    first = register_bundle(fixture_registration_bundle('conflict-one')).registered_version
    second = rebuild_registered_version(
        first,
        candidate_id='different-candidate',
        candidate_fingerprint=fingerprint('different-candidate', 'one'),
    )

    with pytest.raises(PolicyRegistrySnapshotError, match='conflicting semantic version'):
        PolicyRegistrySnapshot((first, second))
