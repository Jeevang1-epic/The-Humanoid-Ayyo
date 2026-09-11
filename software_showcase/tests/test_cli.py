from io import StringIO

from ayyo_software_showcase import (
    ShowcaseReport,
    showcase_artifact_from_canonical_json,
    verify_showcase_report,
)
from ayyo_software_showcase.cli import main


def invoke(*arguments):
    stdout = StringIO()
    stderr = StringIO()
    status = main(arguments, stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()


def test_list_is_deterministic_and_preserves_truthful_labels():
    first = invoke("list")
    second = invoke("list")

    assert first == second
    assert first[0] == 0
    assert first[2] == ""
    assert "ros-gazebo-simulation-foundations" in first[1]
    assert "simulation" in first[1]
    assert "development_only" in first[1]
    assert "physical-hardware-validation" in first[1]
    assert "not_physically_validated" in first[1]


def test_inspect_shows_evidence_and_explicit_non_claims():
    status, output, error = invoke("inspect", "future-activation-eligibility")

    assert status == 0
    assert error == ""
    assert "CLASSIFICATION: implemented, inert_evidence_only" in output
    assert "ActivationEligibilityDecision" in output
    assert "provenance: public-api.ayyo_approval_eligibility.v1" in output
    assert "DOES NOT PROVE:" in output
    assert "policy_activation" in output
    assert "runtime_dispatch" in output


def test_unknown_inspection_returns_concise_failure_without_output():
    status, output, error = invoke("inspect", "unknown-capability")

    assert status == 2
    assert output == ""
    assert error == "error: unknown showcase capability: unknown-capability\n"


def test_report_command_is_deterministic_machine_readable_and_verified():
    first = invoke("report")
    second = invoke("report")

    assert first == second
    assert first[0] == 0
    assert first[2] == ""
    artifact = showcase_artifact_from_canonical_json(first[1].rstrip("\n"))
    assert type(artifact) is ShowcaseReport
    assert verify_showcase_report(artifact)


def test_verify_command_is_deterministic_and_has_no_runtime_side_effect_claim():
    first = invoke("verify")
    second = invoke("verify")

    assert first == second
    assert first[0] == 0
    assert first[1].startswith("VERIFIED software-showcase-manifest-sha256-")
    assert first[2] == ""
