from ayyo_approval_eligibility import (
    ActivationEligibilityReason,
    ActivationEligibilityStatus,
    verify_activation_eligibility_decision,
)

from helpers import fixture_approval_bundle


def test_complete_learning_evidence_path_stops_at_future_activation_eligibility():
    bundle = fixture_approval_bundle('integration')
    record = bundle['registered_version']
    request = bundle['approval_request']
    decision = bundle['decision']

    assert request.candidate_id == record.candidate_id
    assert request.registry_record_id == record.record_id
    assert request.registration_request_id == record.registration_request_id
    assert request.promotion_decision_id == record.promotion_decision_id
    assert decision.status is (
        ActivationEligibilityStatus.ELIGIBLE_FOR_FUTURE_ACTIVATION
    )
    assert decision.reasons == (
        ActivationEligibilityReason.ELIGIBILITY_REQUIREMENTS_SATISFIED,
    )
    assert verify_activation_eligibility_decision(decision)
    for operation in (
        'activate',
        'authenticate',
        'deploy',
        'dispatch',
        'execute',
        'install',
        'load_model',
        'persist',
        'run',
        'train',
    ):
        assert not hasattr(decision, operation)
