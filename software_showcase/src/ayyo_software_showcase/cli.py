"""Small deterministic developer-facing showcase inspector."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence, TextIO

from .catalog import build_showcase_manifest, capability_by_id
from .errors import UnknownShowcaseCapabilityError
from .report import generate_showcase_report, verify_showcase_report
from .serialization import canonical_showcase_artifact_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ayyo-showcase")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list reviewed capability claims")
    inspect_parser = subparsers.add_parser(
        "inspect", help="inspect one exact capability"
    )
    inspect_parser.add_argument("capability_id")
    subparsers.add_parser("report", help="emit the canonical showcase report")
    subparsers.add_parser("verify", help="verify the live manifest and report")
    return parser


def _list_text() -> str:
    manifest = build_showcase_manifest()
    return "\n".join(
        "\t".join(
            (
                capability.capability_id,
                ",".join(item.value for item in capability.classifications),
                capability.title,
            )
        )
        for capability in manifest.capabilities
    )


def _inspect_text(capability_id: str) -> str:
    manifest = build_showcase_manifest()
    capability = capability_by_id(manifest, capability_id)
    evidence = {
        item.evidence_id: item for item in manifest.evidence
    }
    lines = [
        f"CAPABILITY: {capability.capability_id}",
        f"TITLE: {capability.title}",
        "CLASSIFICATION: "
        + ", ".join(item.value for item in capability.classifications),
        f"SUMMARY: {capability.summary}",
        "EVIDENCE:",
    ]
    for evidence_id in capability.evidence_ids:
        reference = evidence[evidence_id]
        schema = (
            ""
            if reference.schema_id is None
            else f" [{reference.schema_id} {reference.schema_version}]"
        )
        lines.append(
            f"- {reference.contract_module}.{reference.contract_symbol}{schema}"
        )
        lines.append(
            "  provenance: "
            f"{reference.provenance_ref} {reference.provenance_fingerprint}"
        )
    lines.append("DOES NOT PROVE:")
    lines.extend(f"- {item.value}" for item in capability.does_not_prove)
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    arguments = _parser().parse_args(argv)
    if arguments.command == "list":
        stdout.write(_list_text() + "\n")
        return 0
    if arguments.command == "inspect":
        try:
            output = _inspect_text(arguments.capability_id)
        except UnknownShowcaseCapabilityError as error:
            stderr.write(f"error: {error}\n")
            return 2
        stdout.write(output + "\n")
        return 0
    if arguments.command == "report":
        stdout.write(canonical_showcase_artifact_json(generate_showcase_report()) + "\n")
        return 0
    report = generate_showcase_report()
    if not verify_showcase_report(report):
        stderr.write("error: live showcase verification failed\n")
        return 1
    stdout.write(
        f"VERIFIED {report.manifest.manifest_id} {report.report_id}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
