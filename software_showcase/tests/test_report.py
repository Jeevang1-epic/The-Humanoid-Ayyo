from dataclasses import replace

import pytest

from ayyo_software_showcase import (
    ShowcaseCheck,
    ShowcaseCheckOutcome,
    ShowcaseClassification,
    ShowcaseManifest,
    ShowcaseReport,
    ShowcaseReportError,
    build_showcase_manifest,
    capability_by_id,
    generate_showcase_report,
    verify_showcase_catalog,
    verify_showcase_report,
)


def _replace_capability(manifest, index, capability):
    capabilities = list(manifest.capabilities)
    capabilities[index] = capability
    return ShowcaseManifest(
        title=manifest.title,
        summary=manifest.summary,
        capabilities=capabilities,
        evidence=manifest.evidence,
    )


def test_report_is_deterministic_complete_and_authoritatively_verified():
    first = generate_showcase_report()
    second = generate_showcase_report()

    assert first == second
    assert first.report_id == second.report_id
    assert len(first.checks) == len(first.manifest.capabilities)
    assert verify_showcase_report(first)


def test_report_outcomes_preserve_implemented_and_unavailable_distinction():
    report = generate_showcase_report()
    outcomes = {item.capability_id: item.outcome for item in report.checks}

    assert outcomes["future-activation-eligibility"] is (
        ShowcaseCheckOutcome.SUPPORTED_BY_PUBLIC_CONTRACT
    )
    assert outcomes["production-policy-activation"] is (
        ShowcaseCheckOutcome.EXPLICITLY_UNAVAILABLE
    )
    assert outcomes["physical-hardware-validation"] is (
        ShowcaseCheckOutcome.EXPLICITLY_UNAVAILABLE
    )


def test_future_activation_eligibility_cannot_become_active_state():
    report = generate_showcase_report()
    capability = capability_by_id(
        report.manifest, "future-activation-eligibility"
    )
    activation = capability_by_id(
        report.manifest, "production-policy-activation"
    )

    assert ShowcaseClassification.IMPLEMENTED in capability.classifications
    assert "policy_activation" in {item.value for item in capability.does_not_prove}
    assert ShowcaseClassification.NOT_YET_IMPLEMENTED in activation.classifications
    for artifact in (capability, activation, report):
        for attribute in (
            "activate",
            "deploy",
            "execute",
            "install",
            "load_model",
            "runtime_dispatch",
        ):
            assert not hasattr(artifact, attribute)


def test_unknown_claim_substitution_is_structurally_visible_and_not_reportable():
    manifest = build_showcase_manifest()
    source = manifest.capabilities[0]
    substituted = replace(
        source,
        capability_id="invented-production-capability",
        title="Invented production capability",
    )
    altered = _replace_capability(manifest, 0, substituted)

    assert not verify_showcase_catalog(altered)
    with pytest.raises(ShowcaseReportError, match="reviewed live"):
        generate_showcase_report(altered)


def test_valid_but_unrelated_evidence_substitution_is_not_reportable():
    manifest = build_showcase_manifest()
    source = manifest.capabilities[12]
    unrelated_id = manifest.capabilities[11].evidence_ids[0]
    substituted = replace(source, evidence_ids=(unrelated_id,))
    altered = _replace_capability(manifest, 12, substituted)

    assert not verify_showcase_catalog(altered)
    with pytest.raises(ShowcaseReportError, match="reviewed live"):
        generate_showcase_report(altered)


def test_check_substitution_and_positive_unavailable_claim_fail_closed():
    report = generate_showcase_report()
    checks = list(report.checks)
    checks[0] = replace(
        checks[0], capability_fingerprint=checks[1].capability_fingerprint
    )
    with pytest.raises(ShowcaseReportError, match="exact capability"):
        ShowcaseReport(manifest=report.manifest, checks=checks)

    unavailable = report.manifest.capabilities[-1]
    forged = ShowcaseCheck(
        capability_id=unavailable.capability_id,
        capability_fingerprint=unavailable.capability_fingerprint,
        outcome=ShowcaseCheckOutcome.SUPPORTED_BY_PUBLIC_CONTRACT,
        evidence_ids=unavailable.evidence_ids,
    )
    checks = list(report.checks)
    checks[-1] = forged
    with pytest.raises(ShowcaseReportError, match="exact capability"):
        ShowcaseReport(manifest=report.manifest, checks=checks)


def test_in_memory_report_identity_tampering_is_rejected():
    report = generate_showcase_report()
    object.__setattr__(report, "report_id", "tampered-report")

    assert not verify_showcase_report(report)
