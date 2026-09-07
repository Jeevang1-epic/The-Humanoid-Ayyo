from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_learning_evaluation


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LOWER_PACKAGES = (
    'teach_mode',
    'developmental_scenarios',
    'memory',
    'memory_validation',
    'memory_consolidation',
    'personal_context',
    'working_memory',
    'world_model',
    'executive',
    'safety_kernel',
    'skill_manager',
    'runtime_bridge',
    'simulation_control',
    'perception',
    'visual_evaluation',
    'physical_camera',
    'depth_camera',
    'rgbd_fusion',
    'head_audio',
)


class LearningEvaluationPackageBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.package_root = REPOSITORY_ROOT / 'learning_evaluation'
        self.source_root = self.package_root / 'src'

    def source_trees(self):
        return tuple(
            (path, ast.parse(path.read_text(encoding='utf-8'), filename=str(path)))
            for path in self.source_root.rglob('*.py')
        )

    def test_only_allowed_upper_stage_dependency_is_imported(self):
        ayyo_imports = set()
        forbidden_roots = {
            'builtin_interfaces', 'gazebo', 'launch', 'rclpy', 'rosbag2_py',
            'sensor_msgs', 'sqlite3', 'torch', 'torchrl', 'tensorflow', 'jax',
            'numpy', 'sklearn',
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
                ayyo_imports.update(item for item in names if item.startswith('ayyo_'))
        self.assertEqual({'ayyo_teach_mode'}, ayyo_imports)
        self.assertEqual(set(), imports & forbidden_roots)

    def test_lower_packages_have_no_reverse_dependency(self):
        offenders = []
        for package in LOWER_PACKAGES:
            for source in (REPOSITORY_ROOT / package / 'src').rglob('*.py'):
                if 'ayyo_learning_evaluation' in source.read_text(encoding='utf-8'):
                    offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
        self.assertEqual([], offenders)

    def test_no_ros_package_depends_on_learning_evaluation(self):
        offenders = []
        for source in (REPOSITORY_ROOT / 'ros2_ws' / 'src').rglob('*'):
            if source.is_file() and source.suffix in {'.py', '.xml', '.txt'}:
                if 'ayyo_learning_evaluation' in source.read_text(encoding='utf-8', errors='ignore'):
                    offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
        self.assertEqual([], offenders)

    def test_no_process_network_storage_dynamic_loading_or_background_workers(self):
        forbidden_imports = {
            'asyncio', 'concurrent', 'importlib', 'multiprocessing', 'os', 'pathlib',
            'requests', 'shutil', 'socket', 'sqlite3', 'subprocess', 'threading', 'urllib',
        }
        forbidden_calls = {
            '__import__', 'compile', 'eval', 'exec', 'import_module', 'open', 'popen',
            'system', 'start', 'write',
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
                    else:
                        continue
                    if name == 'compile' and isinstance(node.func, ast.Attribute):
                        continue
                    if name in forbidden_calls:
                        calls.append((path.name, node.lineno, name))
        self.assertEqual(set(), imports & forbidden_imports)
        self.assertEqual([], calls)

    def test_public_api_has_no_execution_training_promotion_or_mutation_surface(self):
        forbidden = {
            'act', 'apply', 'dispatch', 'execute', 'fit', 'infer', 'learn', 'load_model',
            'persist', 'predict', 'promote', 'rollback', 'run', 'step', 'train', 'update_model',
        }
        self.assertEqual(set(), forbidden & set(ayyo_learning_evaluation.__all__))
        for name in ayyo_learning_evaluation.__all__:
            self.assertTrue(hasattr(ayyo_learning_evaluation, name), name)

    def test_models_expose_no_raw_executable_or_authority_payload(self):
        forbidden = {
            'audio', 'bytecode', 'callback', 'command', 'executable', 'image',
            'model_weights', 'path', 'payload', 'pixels', 'python_source', 'samples',
            'shell', 'url',
        }
        models = (
            ayyo_learning_evaluation.DemonstrationEvaluationCorpus,
            ayyo_learning_evaluation.DemonstrationEpisodeReference,
            ayyo_learning_evaluation.CandidatePolicyManifest,
            ayyo_learning_evaluation.InertArtifactReference,
            ayyo_learning_evaluation.OfflineTrialResult,
            ayyo_learning_evaluation.OfflineEvaluationReport,
        )
        for model in models:
            with self.subTest(model=model.__name__):
                self.assertEqual(set(), forbidden & set(model.__annotations__))

    def test_pyproject_has_one_exact_runtime_dependency(self):
        with (self.package_root / 'pyproject.toml').open('rb') as stream:
            project = tomllib.load(stream)['project']
        self.assertEqual('ayyo-learning-evaluation', project['name'])
        self.assertEqual(['ayyo-teach-mode==0.1.0'], project['dependencies'])
        self.assertEqual('>=3.12', project['requires-python'])
        self.assertNotIn('scripts', project)
        self.assertNotIn('entry-points', project)

    def test_wheel_contains_only_intended_runtime_and_metadata(self):
        expected_sources = {
            'ayyo_learning_evaluation/__init__.py',
            'ayyo_learning_evaluation/candidate.py',
            'ayyo_learning_evaluation/candidate_serialization.py',
            'ayyo_learning_evaluation/canonical.py',
            'ayyo_learning_evaluation/corpus.py',
            'ayyo_learning_evaluation/corpus_serialization.py',
            'ayyo_learning_evaluation/errors.py',
            'ayyo_learning_evaluation/evaluation.py',
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_copy = root / 'learning_evaluation'
            wheel_directory = root / 'wheel'
            shutil.copytree(
                self.package_root,
                package_copy,
                ignore=shutil.ignore_patterns('__pycache__', '*.egg-info', 'build', 'dist'),
            )
            wheel_directory.mkdir()
            result = subprocess.run(
                [
                    'python3', '-m', 'pip', 'wheel', '--no-build-isolation', '--no-deps',
                    '--wheel-dir', str(wheel_directory), str(package_copy),
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
                sources = {name for name in names if name.endswith('.py')}
                metadata_name = next(name for name in names if name.endswith('.dist-info/METADATA'))
                metadata = archive.read(metadata_name).decode('utf-8')
            self.assertEqual(expected_sources, sources)
            self.assertIn('Name: ayyo-learning-evaluation\n', metadata)
            requirements = [
                line.split(':', 1)[1].strip().replace(' ', '')
                for line in metadata.splitlines()
                if line.startswith('Requires-Dist:')
            ]
            self.assertEqual(['ayyo-teach-mode==0.1.0'], requirements)

    def test_build_artifacts_are_ignored_and_untracked(self):
        for artifact in (
            'learning_evaluation/build/lib/package.py',
            'learning_evaluation/dist/package.whl',
            'learning_evaluation/src/ayyo_learning_evaluation.egg-info/PKG-INFO',
        ):
            ignored = subprocess.run(
                ['git', 'check-ignore', '--quiet', artifact], cwd=REPOSITORY_ROOT, check=False
            )
            self.assertEqual(0, ignored.returncode)
        tracked = subprocess.run(
            ['git', 'ls-files', '--', 'learning_evaluation/**'],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual([], [item for item in tracked if '__pycache__' in item or '.egg-info' in item])


if __name__ == '__main__':
    unittest.main()
