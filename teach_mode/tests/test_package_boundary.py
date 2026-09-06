from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_teach_mode


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LOWER_PACKAGES = (
    'developmental_scenarios',
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


class TeachModePackageBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.package_root = REPOSITORY_ROOT / 'teach_mode'
        self.source_root = self.package_root / 'src'

    def source_trees(self):
        return tuple(
            (path, ast.parse(path.read_text(encoding='utf-8'), filename=str(path)))
            for path in self.source_root.rglob('*.py')
        )

    def test_lower_packages_do_not_import_teach_mode(self):
        offenders = []
        for package in LOWER_PACKAGES:
            for source in (REPOSITORY_ROOT / package / 'src').rglob('*.py'):
                if 'ayyo_teach_mode' in source.read_text(encoding='utf-8'):
                    offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
        self.assertEqual([], offenders)

    def test_core_has_only_the_reviewed_lower_layer_dependency(self):
        ayyo_imports = set()
        forbidden_roots = {
            'builtin_interfaces',
            'gazebo',
            'launch',
            'rclpy',
            'rosbag2_py',
            'sensor_msgs',
            'sqlite3',
        }
        imports = set()
        for _, tree in self.source_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split('.')[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split('.')[0]]
                else:
                    continue
                imports.update(names)
                ayyo_imports.update(name for name in names if name.startswith('ayyo_'))
        self.assertEqual({'ayyo_developmental_scenarios'}, ayyo_imports)
        self.assertEqual(set(), imports & forbidden_roots)

    def test_core_has_no_process_network_storage_or_dynamic_loading(self):
        forbidden_imports = {
            'importlib',
            'os',
            'pathlib',
            'requests',
            'shutil',
            'socket',
            'subprocess',
            'urllib',
        }
        forbidden_calls = {
            '__import__',
            'compile',
            'eval',
            'exec',
            'import_module',
            'open',
            'popen',
            'system',
        }
        imports = set()
        calls = []
        for path, tree in self.source_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split('.')[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split('.')[0])
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        name = node.func.attr
                        if name == 'compile':
                            continue
                    else:
                        continue
                    if name in forbidden_calls:
                        calls.append((path.name, node.lineno, name))
        self.assertEqual(set(), imports & forbidden_imports)
        self.assertEqual([], calls)

    def test_public_api_has_no_learning_execution_or_persistence_surface(self):
        forbidden = {
            'apply',
            'create_memory',
            'dispatch',
            'execute',
            'fit',
            'learn',
            'persist',
            'promote',
            'replay_and_execute',
            'rollback',
            'run_action',
            'train',
        }
        self.assertEqual(set(), set(ayyo_teach_mode.__all__) & forbidden)
        for name in ayyo_teach_mode.__all__:
            self.assertTrue(hasattr(ayyo_teach_mode, name), name)

    def test_episode_models_cannot_retain_raw_sensor_payloads_or_callbacks(self):
        forbidden_fields = {
            'audio',
            'callback',
            'command',
            'depth',
            'executable',
            'image',
            'metadata',
            'payload',
            'pixels',
            'ros_messages',
            'samples',
        }
        public_models = (
            ayyo_teach_mode.DemonstrationEpisode,
            ayyo_teach_mode.DemonstrationEvent,
            ayyo_teach_mode.DemonstrationObservationReference,
            ayyo_teach_mode.DemonstrationActionReference,
            ayyo_teach_mode.DemonstrationOutcome,
        )
        for model in public_models:
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    set(), set(model.__annotations__) & forbidden_fields
                )

    def test_pyproject_declares_one_exact_transport_neutral_dependency(self):
        with (self.package_root / 'pyproject.toml').open('rb') as stream:
            project = tomllib.load(stream)['project']
        self.assertEqual(
            ['ayyo-developmental-scenarios==0.1.0'], project['dependencies']
        )
        self.assertEqual('>=3.12', project['requires-python'])
        self.assertNotIn('scripts', project)
        self.assertNotIn('entry-points', project)

    def test_wheel_contains_only_teach_mode_runtime_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_copy = root / 'teach_mode'
            wheel_directory = root / 'wheel'
            shutil.copytree(
                self.package_root,
                package_copy,
                ignore=shutil.ignore_patterns('__pycache__', '*.egg-info', 'build', 'dist'),
            )
            wheel_directory.mkdir()
            result = subprocess.run(
                [
                    'python3',
                    '-m',
                    'pip',
                    'wheel',
                    '--no-build-isolation',
                    '--no-deps',
                    '--wheel-dir',
                    str(wheel_directory),
                    str(package_copy),
                ],
                cwd=REPOSITORY_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            wheels = tuple(wheel_directory.glob('*.whl'))
            self.assertEqual(1, len(wheels))
            with zipfile.ZipFile(wheels[0]) as archive:
                names = archive.namelist()
                metadata_name = next(
                    name for name in names if name.endswith('.dist-info/METADATA')
                )
                metadata = archive.read(metadata_name).decode('utf-8')
            self.assertTrue(
                all(
                    name.startswith('ayyo_teach_mode/')
                    for name in names
                    if name.endswith('.py')
                )
            )
            self.assertIn('Name: ayyo-teach-mode\n', metadata)
            requirements = [
                line.split(':', 1)[1].strip().replace(' ', '')
                for line in metadata.splitlines()
                if line.startswith('Requires-Dist:')
            ]
            self.assertEqual(['ayyo-developmental-scenarios==0.1.0'], requirements)

    def test_build_artifacts_are_ignored_and_untracked(self):
        for artifact in (
            'teach_mode/build/lib/package.py',
            'teach_mode/dist/package.whl',
            'teach_mode/src/ayyo_teach_mode.egg-info/PKG-INFO',
        ):
            ignored = subprocess.run(
                ['git', 'check-ignore', '--quiet', artifact],
                cwd=REPOSITORY_ROOT,
                check=False,
            )
            self.assertEqual(0, ignored.returncode)
        tracked = subprocess.run(
            ['git', 'ls-files', '--', 'teach_mode/**'],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(
            [],
            [
                path
                for path in tracked
                if path.endswith(('.pyc', '.whl'))
                or '/build/' in path
                or '/dist/' in path
                or '.egg-info/' in path
            ],
        )


if __name__ == '__main__':
    unittest.main()
