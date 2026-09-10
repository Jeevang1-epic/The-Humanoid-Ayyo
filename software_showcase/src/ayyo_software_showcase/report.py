"""Pure authoritative generation and verification of showcase reports."""

from __future__ import annotations

from .catalog import build_showcase_manifest, verify_showcase_catalog
from .errors import ShowcaseReportError
from .models import (
    ShowcaseCheck,
    ShowcaseCheckOutcome,
    ShowcaseClassification,
    ShowcaseManifest,
    ShowcaseReport,
    verify_showcase_check,
)


def generate_showcase_report(
    manifest: ShowcaseManifest | None = None,
) -> ShowcaseReport:
    """Generate evidence checks only for the exact reviewed in-process catalog."""
    manifest = build_showcase_manifest() if manifest is None else manifest
    if not verify_showcase_catalog(manifest):
        raise ShowcaseReportError(
            "showcase reporting accepts only the reviewed live v1 catalog"
        )
    checks = tuple(
        ShowcaseCheck(
            capability_id=capability.capability_id,
            capability_fingerprint=capability.capability_fingerprint,
            outcome=(
                ShowcaseCheckOutcome.EXPLICITLY_UNAVAILABLE
                if ShowcaseClassification.NOT_YET_IMPLEMENTED
                in capability.classifications
                else ShowcaseCheckOutcome.SUPPORTED_BY_PUBLIC_CONTRACT
            ),
            evidence_ids=capability.evidence_ids,
        )
        for capability in manifest.capabilities
    )
    return ShowcaseReport(manifest=manifest, checks=checks)


def verify_showcase_report(report: object) -> bool:
    """Rebuild and authoritatively regenerate the report; fail closed."""
    if type(report) is not ShowcaseReport:
        return False
    try:
        if not verify_showcase_catalog(report.manifest):
            return False
        if any(not verify_showcase_check(item) for item in report.checks):
            return False
        rebuilt = ShowcaseReport(manifest=report.manifest, checks=report.checks)
        authoritative = generate_showcase_report(report.manifest)
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == report and authoritative == report
