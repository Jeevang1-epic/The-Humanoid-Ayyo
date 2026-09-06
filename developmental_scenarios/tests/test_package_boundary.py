import ast
from pathlib import Path
import unittest

import ayyo_developmental_scenarios


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LOWER_PACKAGES = (
    'perception',
    'world_model',
    'working_memory',
    'memory',
    'memory_validation',
    'personal_context',
    'executive',
    'safety_kernel',
    'skill_manager',
    'runtime_bridge',
    'simulation_control',
)


class ScenarioPackageBoundaryTest(unittest.TestCase):
    def test_lower_layers_do_not_import_scenario_package(self):
        offenders = []
        for package in LOWER_PACKAGES:
            for source in (REPOSITORY_ROOT / package / 'src').rglob('*.py'):
                if 'ayyo_developmental_scenarios' in source.read_text(encoding='utf-8'):
                    offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
        self.assertEqual([], offenders)

    def test_public_package_exports_only_contracts_and_explicit_operations(self):
        self.assertFalse(hasattr(ayyo_developmental_scenarios, 'run_shell'))
        self.assertFalse(hasattr(ayyo_developmental_scenarios, 'execute_command'))
        self.assertFalse(hasattr(ayyo_developmental_scenarios, 'persist'))

    def test_scenario_core_has_no_subprocess_eval_exec_or_dynamic_import(self):
        root = REPOSITORY_ROOT / 'developmental_scenarios' / 'src'
        forbidden_calls = {'eval', 'exec', '__import__'}
        findings = []
        for source in root.rglob('*.py'):
            tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or '']
                    )
                    if 'subprocess' in names or 'importlib' in names:
                        findings.append((source.name, 'dynamic process/import'))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in forbidden_calls:
                        findings.append((source.name, node.func.id))
        self.assertEqual([], findings)

    def test_no_production_lower_layer_mentions_scenario_ros_package(self):
        offenders = []
        for package in LOWER_PACKAGES:
            package_root = REPOSITORY_ROOT / package
            for source in package_root.rglob('*'):
                if source.is_file() and source.suffix in {'.py', '.toml', '.xml'}:
                    if 'ayyo_scenarios' in source.read_text(encoding='utf-8'):
                        offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
        self.assertEqual([], offenders)


if __name__ == '__main__':
    unittest.main()
