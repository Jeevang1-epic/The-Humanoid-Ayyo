"""Read-only command-line inspection for the fixed Stage-6 scenario catalog."""

from __future__ import annotations

import argparse
import sys
from typing import TextIO

from .catalog import scenario_by_id, SCENARIO_CATALOG
from .errors import InvalidScenarioDefinitionError
from .manifest import (
    build_scenario_manifest,
    canonical_manifest_json,
    verify_scenario_catalog,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='ayyo-scenarios',
        description='Inspect and verify the fixed Stage-6 scenario catalog.',
    )
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List reviewed scenarios in canonical order.')
    describe = commands.add_parser('describe', help='Describe one reviewed scenario.')
    describe.add_argument('scenario_id')
    commands.add_parser('manifest', help='Emit the canonical catalog manifest JSON.')
    commands.add_parser('verify', help='Verify pure-local catalog integrity.')
    return parser


def _list_text() -> str:
    manifest = build_scenario_manifest(SCENARIO_CATALOG)
    return '\n'.join(
        ' | '.join(
            (
                entry.scenario_id,
                f'version={entry.scenario_version}',
                f'category={entry.category.value}',
                f'profile={entry.launch_profile.value}',
                f'authority={entry.authority.value}',
                f'expected={entry.expected_safe_outcome}',
                f'fingerprint={entry.scenario_fingerprint}',
            )
        )
        for entry in manifest.entries
    )


def _describe_text(scenario_id: str) -> str:
    definition = scenario_by_id(scenario_id)
    lines = [
        f'scenario_id: {definition.scenario_id}',
        f'version: {definition.version}',
        f'fingerprint: {definition.fingerprint}',
        f'category: {definition.category.value}',
        f'description: {definition.description}',
        f'launch_profile: {definition.launch_profile.value}',
        f'authority: {definition.authority.value}',
        f'expected_safe_outcome: {definition.expected_safe_outcome}',
        'steps:',
    ]
    lines.extend(
        (
            f'  {index}. id={step.step_id} operation={step.operation.value} '
            f'timeout_ms={step.timeout_ms} assertions={",".join(step.assertion_ids)}'
        )
        for index, step in enumerate(definition.steps, start=1)
    )
    lines.append('assertions:')
    lines.extend(
        (
            f'  {index}. id={assertion.assertion_id} '
            f'required={str(assertion.required).lower()} '
            f'description={assertion.description}'
        )
        for index, assertion in enumerate(definition.assertions, start=1)
    )
    return '\n'.join(lines)


def main(
    arguments: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run one fixed read-only inspection command and return its exit status."""
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    options = _parser().parse_args(sys.argv[1:] if arguments is None else arguments)
    if options.command == 'list':
        print(_list_text(), file=output)
        return 0
    if options.command == 'describe':
        try:
            description = _describe_text(options.scenario_id)
        except InvalidScenarioDefinitionError:
            print('error: unknown reviewed scenario ID', file=errors)
            return 2
        print(description, file=output)
        return 0
    if options.command == 'manifest':
        print(
            canonical_manifest_json(build_scenario_manifest(SCENARIO_CATALOG)),
            file=output,
        )
        return 0
    if options.command == 'verify':
        result = verify_scenario_catalog(SCENARIO_CATALOG)
        if not result.valid:
            reasons = ','.join(item.value for item in result.reasons)
            print(f'error: scenario catalog integrity failed: {reasons}', file=errors)
            return 1
        print(
            f'verified {result.scenario_count} scenarios '
            f'manifest={result.manifest_fingerprint}',
            file=output,
        )
        return 0
    raise RuntimeError('argparse accepted an unknown scenario command')


if __name__ == '__main__':
    raise SystemExit(main())
