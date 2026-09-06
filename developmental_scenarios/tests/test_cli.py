import argparse
import ast
from io import StringIO
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from ayyo_developmental_scenarios import (
    build_scenario_manifest,
    canonical_manifest_json,
    SCENARIO_CATALOG,
)
import ayyo_developmental_scenarios.cli as cli


def invoke(*arguments):
    output = StringIO()
    errors = StringIO()
    status = cli.main(list(arguments), stdout=output, stderr=errors)
    return status, output.getvalue(), errors.getvalue()


class ScenarioInspectionCliTest(unittest.TestCase):
    def test_cli_exposes_exact_command_surface(self):
        parser = cli._parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertEqual(
            {'describe', 'list', 'manifest', 'verify'},
            set(subparsers.choices),
        )

    def test_list_exits_zero_and_is_deterministic(self):
        first = invoke('list')
        second = invoke('list')
        self.assertEqual(0, first[0])
        self.assertEqual('', first[2])
        self.assertEqual(first, second)

    def test_list_contains_each_catalog_scenario_once_in_order(self):
        _, output, _ = invoke('list')
        listed_ids = tuple(line.split(' | ', 1)[0] for line in output.splitlines())
        expected_ids = tuple(item.scenario_id for item in SCENARIO_CATALOG)
        self.assertEqual(expected_ids, listed_ids)
        self.assertEqual(len(listed_ids), len(set(listed_ids)))

    def test_list_exposes_required_metadata(self):
        _, output, _ = invoke('list')
        for field in (
            'version=',
            'category=',
            'profile=',
            'authority=',
            'expected=',
            'fingerprint=',
        ):
            self.assertIn(field, output)

    def test_describe_known_scenario_exits_zero(self):
        scenario_id = 'optional-visual-source-absent'
        status, output, errors = invoke('describe', scenario_id)
        self.assertEqual(0, status)
        self.assertEqual('', errors)
        self.assertIn(f'scenario_id: {scenario_id}\n', output)
        self.assertIn('launch_profile: sensor_absence\n', output)

    def test_describe_renders_ordered_steps_assertions_and_timeouts(self):
        _, output, _ = invoke('describe', 'embodied-observation-baseline')
        self.assertIn('steps:\n  1. id=gazebo-ready', output)
        self.assertIn('operation=wait_for_gazebo', output)
        self.assertIn('timeout_ms=30000', output)
        self.assertIn('assertions:\n  1. id=gazebo-running', output)

    def test_describe_unknown_scenario_fails_closed(self):
        status, output, errors = invoke('describe', 'not-a-reviewed-scenario')
        self.assertEqual(2, status)
        self.assertEqual('', output)
        self.assertEqual('error: unknown reviewed scenario ID\n', errors)

    def test_manifest_exits_zero_with_parseable_complete_json(self):
        status, output, errors = invoke('manifest')
        document = json.loads(output)
        self.assertEqual(0, status)
        self.assertEqual('', errors)
        self.assertEqual(len(SCENARIO_CATALOG), document['scenario_count'])
        self.assertEqual(len(SCENARIO_CATALOG), len(document['scenarios']))

    def test_manifest_cli_uses_exact_canonical_serializer(self):
        _, output, _ = invoke('manifest')
        expected = canonical_manifest_json(build_scenario_manifest()) + '\n'
        self.assertEqual(expected.encode('utf-8'), output.encode('utf-8'))

    def test_verify_exits_zero_for_current_catalog(self):
        status, output, errors = invoke('verify')
        self.assertEqual(0, status)
        self.assertEqual('', errors)
        self.assertIn('verified 6 scenarios manifest=', output)

    def test_verify_returns_nonzero_for_integrity_failure(self):
        invalid = (SCENARIO_CATALOG[0], SCENARIO_CATALOG[0])
        with mock.patch.object(cli, 'SCENARIO_CATALOG', invalid):
            status, output, errors = invoke('verify')
        self.assertEqual(1, status)
        self.assertEqual('', output)
        self.assertIn('duplicate_scenario_id', errors)

    def test_cli_source_has_no_process_or_runtime_imports(self):
        source = Path(cli.__file__).read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported_roots = {
            alias.name.split('.', 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            imported_roots.isdisjoint(
                {'launch', 'os', 'rclpy', 'subprocess'}
            )
        )

    def test_cli_commands_make_no_process_calls(self):
        with (
            mock.patch.object(subprocess, 'run', side_effect=AssertionError),
            mock.patch.object(subprocess, 'Popen', side_effect=AssertionError),
            mock.patch('os.system', side_effect=AssertionError),
        ):
            self.assertEqual(0, invoke('list')[0])
            self.assertEqual(
                0,
                invoke('describe', 'embodied-observation-baseline')[0],
            )
            self.assertEqual(0, invoke('manifest')[0])
            self.assertEqual(0, invoke('verify')[0])


if __name__ == '__main__':
    unittest.main()
