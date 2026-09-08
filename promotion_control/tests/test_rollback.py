from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ayyo_promotion_control import (
    KnownGoodPolicyReference,
    RollbackControlError,
    RollbackCriteria,
    RollbackDecisionReason,
    RollbackDecisionStatus,
    RollbackEvidenceKind,
    RollbackEvidenceReference,
    RollbackReason,
    RollbackRequest,
    evaluate_promotion,
    evaluate_rollback,
    verify_known_good_policy,
    verify_rollback_decision,
    verify_rollback_request,
)

from helpers import (
    fingerprint,
    fixture_candidate,
    fixture_promotion_bundle,
    fixture_rollback_bundle,
)


def _evaluate(bundle, **overrides):
    fields = {
        'criteria': bundle['rollback_criteria'],
        'request': bundle['rollback_request'],
        'current_candidate': bundle['current_candidate'],
        'target_candidate': bundle['candidate'],
        'known_good': bundle['known_good'],
        'promotion_decision': bundle['decision'],
    }
    fields.update(overrides)
    return evaluate_rollback(**fields)


def _criteria(current, known_good, **overrides):
    fields = {
        'current_candidate_id': current.candidate_id,
        'current_candidate_fingerprint': current.candidate_fingerprint,
        'known_good_id': known_good.known_good_id,
        'known_good_fingerprint': known_good.known_good_fingerprint,
        'allowed_reasons': tuple(RollbackReason),
        'minimum_evidence_references': 1,
    }
    fields.update(overrides)
    return RollbackCriteria(**fields)


def _evidence(kind, label='one'):
    return RollbackEvidenceReference(
        evidence_kind=kind,
        source_ref=f'{kind.value}.fixture.v1',
        source_fingerprint=fingerprint(kind.value, label),
    )


def _request(current, known_good, criteria, reason, evidence, **overrides):
    fields = {
        'current_candidate': current,
        'known_good': known_good,
        'criteria': criteria,
        'reason': reason,
        'evidence_references': evidence,
        'provenance_ref': 'rollback-review.fixture.v1',
        'provenance_fingerprint': fingerprint('rollback-review', 'request'),
    }
    fields.update(overrides)
    return RollbackRequest(**fields)


def test_matching_known_good_chain_is_rollback_eligible_without_mutation():
    bundle = fixture_rollback_bundle()
    before_current = bundle['current_candidate'].as_dict()
    before_target = bundle['candidate'].as_dict()

    decision = _evaluate(bundle)

    assert decision.status is RollbackDecisionStatus.ROLLBACK_ELIGIBLE
    assert decision.reasons == (RollbackDecisionReason.ROLLBACK_CRITERIA_SATISFIED,)
    assert bundle['current_candidate'].as_dict() == before_current
    assert bundle['candidate'].as_dict() == before_target
    assert 'installed' not in decision.as_dict()
    assert 'executed' not in decision.as_dict()
    assert verify_rollback_decision(decision)
    with pytest.raises(FrozenInstanceError):
        decision.status = RollbackDecisionStatus.ROLLBACK_REJECTED


def test_admissible_and_rejected_rollback_decisions_are_deterministic():
    first = fixture_rollback_bundle('deterministic')
    second = fixture_rollback_bundle('deterministic')
    assert _evaluate(first) == _evaluate(second)

    criteria = _criteria(first['current_candidate'], first['known_good'])
    request = _request(
        first['current_candidate'],
        first['known_good'],
        criteria,
        RollbackReason.SAFETY_REGRESSION,
        (_evidence(RollbackEvidenceKind.RUNTIME_OBSERVATION),),
    )
    rejected_once = _evaluate(first, criteria=criteria, request=request)
    rejected_twice = _evaluate(first, criteria=criteria, request=request)
    assert rejected_once == rejected_twice
    assert rejected_once.status is RollbackDecisionStatus.ROLLBACK_REJECTED


@pytest.mark.parametrize(
    ('reason', 'kind'),
    [
        (RollbackReason.EVALUATION_REGRESSION, RollbackEvidenceKind.EVALUATION_REPORT),
        (RollbackReason.SAFETY_REGRESSION, RollbackEvidenceKind.SAFETY_REVIEW),
        (RollbackReason.RUNTIME_REGRESSION, RollbackEvidenceKind.RUNTIME_OBSERVATION),
        (RollbackReason.OPERATOR_REQUEST, RollbackEvidenceKind.OPERATOR_INSTRUCTION),
        (RollbackReason.INTEGRITY_FAILURE, RollbackEvidenceKind.INTEGRITY_REPORT),
    ],
)
def test_each_closed_reason_requires_and_accepts_its_typed_evidence(reason, kind):
    bundle = fixture_rollback_bundle()
    criteria = _criteria(bundle['current_candidate'], bundle['known_good'])
    request = _request(
        bundle['current_candidate'],
        bundle['known_good'],
        criteria,
        reason,
        (_evidence(kind),),
    )

    decision = _evaluate(bundle, criteria=criteria, request=request)

    assert decision.status is RollbackDecisionStatus.ROLLBACK_ELIGIBLE


def test_wrong_evidence_kind_is_rejected():
    bundle = fixture_rollback_bundle()
    criteria = _criteria(bundle['current_candidate'], bundle['known_good'])
    request = _request(
        bundle['current_candidate'],
        bundle['known_good'],
        criteria,
        RollbackReason.SAFETY_REGRESSION,
        (_evidence(RollbackEvidenceKind.RUNTIME_OBSERVATION),),
    )

    decision = _evaluate(bundle, criteria=criteria, request=request)

    assert decision.status is RollbackDecisionStatus.ROLLBACK_REJECTED
    assert RollbackDecisionReason.EVIDENCE_KIND_MISMATCH in decision.reasons


def test_disallowed_reason_and_evidence_minimum_are_independent_rejections():
    bundle = fixture_rollback_bundle()
    criteria = _criteria(
        bundle['current_candidate'],
        bundle['known_good'],
        allowed_reasons=(RollbackReason.OPERATOR_REQUEST,),
        minimum_evidence_references=2,
    )
    request = _request(
        bundle['current_candidate'],
        bundle['known_good'],
        criteria,
        RollbackReason.EVALUATION_REGRESSION,
        (_evidence(RollbackEvidenceKind.EVALUATION_REPORT),),
    )

    decision = _evaluate(bundle, criteria=criteria, request=request)

    assert RollbackDecisionReason.REASON_NOT_ALLOWED in decision.reasons
    assert RollbackDecisionReason.INSUFFICIENT_REASON_EVIDENCE in decision.reasons


def test_self_rollback_is_always_rejected():
    bundle = fixture_rollback_bundle()
    target = bundle['candidate']
    criteria = _criteria(target, bundle['known_good'])
    request = _request(
        target,
        bundle['known_good'],
        criteria,
        RollbackReason.EVALUATION_REGRESSION,
        (_evidence(RollbackEvidenceKind.EVALUATION_REPORT),),
    )

    decision = _evaluate(
        bundle,
        criteria=criteria,
        request=request,
        current_candidate=target,
    )

    assert decision.status is RollbackDecisionStatus.ROLLBACK_REJECTED
    assert RollbackDecisionReason.SELF_ROLLBACK in decision.reasons


def test_unknown_known_good_substitution_is_rejected_at_every_binding():
    first = fixture_rollback_bundle('first')
    second = fixture_rollback_bundle('second')

    decision = _evaluate(
        first,
        known_good=second['known_good'],
        target_candidate=second['candidate'],
        promotion_decision=second['decision'],
    )

    assert decision.status is RollbackDecisionStatus.ROLLBACK_REJECTED
    assert RollbackDecisionReason.REQUEST_KNOWN_GOOD_MISMATCH in decision.reasons
    assert RollbackDecisionReason.CRITERIA_KNOWN_GOOD_MISMATCH in decision.reasons


def test_request_to_rollback_criteria_identity_mismatch_is_rejected():
    bundle = fixture_rollback_bundle()
    changed = _criteria(
        bundle['current_candidate'],
        bundle['known_good'],
        allowed_reasons=(RollbackReason.EVALUATION_REGRESSION,),
    )

    decision = _evaluate(bundle, criteria=changed)

    assert decision.status is RollbackDecisionStatus.ROLLBACK_REJECTED
    assert RollbackDecisionReason.REQUEST_CRITERIA_MISMATCH in decision.reasons
    assert changed.criteria_id != bundle['rollback_criteria'].criteria_id


def test_target_candidate_substitution_is_rejected():
    first = fixture_rollback_bundle('first')
    second = fixture_promotion_bundle('second')

    decision = _evaluate(first, target_candidate=second['candidate'])

    assert RollbackDecisionReason.KNOWN_GOOD_TARGET_MISMATCH in decision.reasons
    assert RollbackDecisionReason.PROMOTION_DECISION_MISMATCH in decision.reasons


def test_promotion_decision_substitution_is_rejected():
    first = fixture_rollback_bundle('first')
    second = fixture_promotion_bundle('second')

    decision = _evaluate(first, promotion_decision=second['decision'])

    assert decision.status is RollbackDecisionStatus.ROLLBACK_REJECTED
    assert RollbackDecisionReason.PROMOTION_DECISION_MISMATCH in decision.reasons


def test_policy_family_lineage_mismatch_is_rejected():
    bundle = fixture_rollback_bundle()
    unrelated = fixture_candidate(
        bundle['corpus'],
        semantic_version='0.3.0',
        policy_family_id='ayyo.unrelated-policy.v1',
    )
    criteria = _criteria(unrelated, bundle['known_good'])
    request = _request(
        unrelated,
        bundle['known_good'],
        criteria,
        RollbackReason.EVALUATION_REGRESSION,
        (_evidence(RollbackEvidenceKind.EVALUATION_REPORT),),
    )

    decision = _evaluate(
        bundle,
        criteria=criteria,
        request=request,
        current_candidate=unrelated,
    )

    assert decision.status is RollbackDecisionStatus.ROLLBACK_REJECTED
    assert RollbackDecisionReason.TARGET_LINEAGE_MISMATCH in decision.reasons


def test_known_good_cannot_be_created_from_rejected_promotion():
    promotion = fixture_promotion_bundle()
    wrong_candidate = fixture_candidate(promotion['corpus'], semantic_version='0.2.0')
    rejected = evaluate_promotion(
        criteria=promotion['criteria'],
        request=promotion['request'],
        candidate=wrong_candidate,
        report=promotion['report'],
    )

    with pytest.raises(RollbackControlError, match='eligible'):
        KnownGoodPolicyReference(
            target_candidate=wrong_candidate,
            promotion_decision=rejected,
            provenance_ref='known-good-review.fixture.v1',
            provenance_fingerprint=fingerprint('known-good-review', 'rejected'),
        )


def test_tampered_known_good_or_request_fails_closed():
    bundle = fixture_rollback_bundle()
    object.__setattr__(bundle['known_good'], 'target_candidate_id', 'substituted-candidate')

    assert not verify_known_good_policy(bundle['known_good'])
    with pytest.raises(RollbackControlError, match='integrity'):
        _evaluate(bundle)


def test_malformed_rollback_request_fails_closed():
    bundle = fixture_rollback_bundle()
    object.__setattr__(bundle['rollback_request'], 'criteria_id', 'substituted-criteria')

    assert not verify_rollback_request(bundle['rollback_request'])
    with pytest.raises(RollbackControlError, match='integrity'):
        _evaluate(bundle)


def test_tampered_target_candidate_fails_closed():
    bundle = fixture_rollback_bundle()
    object.__setattr__(bundle['candidate'], 'candidate_id', 'substituted-target')

    with pytest.raises(RollbackControlError, match='integrity'):
        _evaluate(bundle)


def test_free_form_note_never_replaces_typed_reason_evidence():
    bundle = fixture_rollback_bundle()
    criteria = _criteria(bundle['current_candidate'], bundle['known_good'])
    request = _request(
        bundle['current_candidate'],
        bundle['known_good'],
        criteria,
        RollbackReason.INTEGRITY_FAILURE,
        (_evidence(RollbackEvidenceKind.EVALUATION_REPORT),),
        note='Integrity failure confirmed; rollback now.',
    )

    decision = _evaluate(bundle, criteria=criteria, request=request)

    assert decision.status is RollbackDecisionStatus.ROLLBACK_REJECTED
    assert RollbackDecisionReason.EVIDENCE_KIND_MISMATCH in decision.reasons


def test_evidence_is_deduplicated_by_identity_and_bounded():
    bundle = fixture_rollback_bundle()
    evidence = _evidence(RollbackEvidenceKind.EVALUATION_REPORT)
    with pytest.raises(RollbackControlError, match='duplicate'):
        _request(
            bundle['current_candidate'],
            bundle['known_good'],
            bundle['rollback_criteria'],
            RollbackReason.EVALUATION_REGRESSION,
            (evidence, evidence),
        )
    many = tuple(
        _evidence(RollbackEvidenceKind.EVALUATION_REPORT, str(index))
        for index in range(9)
    )
    with pytest.raises(RollbackControlError, match='bounds'):
        _request(
            bundle['current_candidate'],
            bundle['known_good'],
            bundle['rollback_criteria'],
            RollbackReason.EVALUATION_REGRESSION,
            many,
        )


@pytest.mark.parametrize('minimum', [0, 9, True])
def test_rollback_criteria_evidence_minimum_is_strictly_bounded(minimum):
    bundle = fixture_rollback_bundle()
    with pytest.raises(RollbackControlError):
        _criteria(
            bundle['current_candidate'],
            bundle['known_good'],
            minimum_evidence_references=minimum,
        )


def test_closed_reason_enum_and_verified_request_are_required():
    bundle = fixture_rollback_bundle()
    with pytest.raises(RollbackControlError, match='closed enum'):
        _request(
            bundle['current_candidate'],
            bundle['known_good'],
            bundle['rollback_criteria'],
            'operator_request',
            (_evidence(RollbackEvidenceKind.OPERATOR_INSTRUCTION),),
        )
    assert verify_rollback_request(bundle['rollback_request'])
