import pytest

from ayyo_learning_evaluation import verify_candidate_policy, verify_evaluation_report
from ayyo_promotion_control import (
    PromotionDecisionStatus,
    verify_promotion_decision,
)
from ayyo_teach_mode import verify_episode
from ayyo_policy_registry import (
    CandidateRegistrationError,
    RegistrationStatus,
    resolve_policy_version,
    verify_registration_result,
)

from helpers import fixture_registration_bundle, register_bundle


def test_stage_seven_evidence_reaches_an_inert_registered_version_and_stops():
    bundle = fixture_registration_bundle('cross-layer')

    assert all(
        verify_episode(episode)
        for episode in (
            *bundle['corpus'].candidate_evidence.episodes,
            *bundle['corpus'].holdout_evaluation.episodes,
        )
    )
    assert verify_candidate_policy(bundle['candidate'])
    assert verify_evaluation_report(bundle['report'])
    assert bundle['report'].corpus == bundle['corpus']
    assert bundle['report'].trial_evidence
    assert verify_promotion_decision(bundle['decision'])
    assert bundle['decision'].status is PromotionDecisionStatus.ELIGIBLE

    result = register_bundle(bundle)
    record = result.registered_version

    assert result.status is RegistrationStatus.REGISTERED
    assert verify_registration_result(result)
    assert resolve_policy_version(
        result.updated_snapshot,
        policy_family_id=bundle['candidate'].policy_family_id,
        semantic_version_value=bundle['candidate'].semantic_version,
    ) == record
    assert record.candidate_evidence_set_id == (
        bundle['corpus'].candidate_evidence.evidence_set_id
    )
    assert record.holdout_evidence_set_id == (
        bundle['corpus'].holdout_evaluation.evidence_set_id
    )
    assert record.evaluation_report_id == bundle['report'].report_id
    assert record.promotion_decision_id == bundle['decision'].decision_id
    assert not any(
        hasattr(record, name)
        for name in ('execute', 'activate', 'deploy', 'load_model', 'dispatch')
    )


def test_cross_layer_report_substitution_fails_before_registry_state_changes():
    bundle = fixture_registration_bundle('integration-expected')
    alternate = fixture_registration_bundle('integration-substituted')
    original_snapshot = bundle['snapshot']
    bundle['report'] = alternate['report']

    with pytest.raises(CandidateRegistrationError):
        register_bundle(bundle)

    assert bundle['snapshot'] == original_snapshot
    assert bundle['snapshot'].registered_versions == ()
