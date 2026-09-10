from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import zipfile

import ayyo_approval_eligibility as public_api


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / 'approval_eligibility'
SOURCE_ROOT = PACKAGE_ROOT / 'src' / 'ayyo_approval_eligibility'
LOWER_PACKAGES = (
    'policy_registry',
    'promotion_control',
    'learning_evaluation',
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


def source_trees():
    return tuple(
        (path, ast.parse(path.read_text(encoding='utf-8'), filename=str(path)))
        for path in SOURCE_ROOT.glob('*.py')
    )


def test_distribution_has_one_exact_dependency_and_no_entrypoint():
    metadata = tomllib.loads((PACKAGE_ROOT / 'pyproject.toml').read_text())['project']

    assert metadata['name'] == 'ayyo-approval-eligibility'
    assert metadata['version'] == '0.1.0'
    assert metadata['requires-python'] == '>=3.12'
    assert metadata['dependencies'] == ['ayyo-policy-registry==0.1.0']
    assert 'scripts' not in metadata
    assert 'entry-points' not in metadata


def test_dependency_direction_extends_the_inert_learning_evidence_path():
    registry = tomllib.loads(
        (REPOSITORY_ROOT / 'policy_registry' / 'pyproject.toml').read_text()
    )['project']
    promotion = tomllib.loads(
        (REPOSITORY_ROOT / 'promotion_control' / 'pyproject.toml').read_text()
    )['project']
    learning = tomllib.loads(
        (REPOSITORY_ROOT / 'learning_evaluation' / 'pyproject.toml').read_text()
    )['project']

    assert registry['dependencies'] == ['ayyo-promotion-control==0.1.0']
    assert promotion['dependencies'] == ['ayyo-learning-evaluation==0.1.0']
    assert learning['dependencies'] == ['ayyo-teach-mode==0.1.0']
    for metadata in (registry, promotion, learning):
        assert not any(
            'approval-eligibility' in item for item in metadata.get('dependencies', [])
        )


def test_runtime_source_imports_only_stdlib_and_policy_registry():
    allowed_roots = {
        '__future__',
        'dataclasses',
        'enum',
        'hashlib',
        'json',
        're',
        'unicodedata',
        'ayyo_policy_registry',
    }
    imports = set()
    for _, tree in source_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split('.')[0])

    assert imports <= allowed_roots
    assert 'ayyo_promotion_control' not in imports
    assert 'ayyo_learning_evaluation' not in imports
    assert 'ayyo_teach_mode' not in imports


def test_lower_layers_ros_and_runtime_have_no_reverse_dependency():
    offenders = []
    for package in LOWER_PACKAGES:
        for source in (REPOSITORY_ROOT / package / 'src').rglob('*.py'):
            if 'ayyo_approval_eligibility' in source.read_text(encoding='utf-8'):
                offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
    for source in (REPOSITORY_ROOT / 'ros2_ws' / 'src').rglob('*'):
        if source.is_file() and source.suffix in {'.py', '.xml', '.txt'}:
            if 'ayyo_approval_eligibility' in source.read_text(
                encoding='utf-8', errors='ignore'
            ):
                offenders.append(str(source.relative_to(REPOSITORY_ROOT)))

    assert offenders == []


def test_runtime_has_no_io_process_network_thread_dynamic_model_or_ros_calls():
    forbidden_imports = {
        'asyncio',
        'concurrent',
        'importlib',
        'multiprocessing',
        'os',
        'pathlib',
        'pickle',
        'requests',
        'rclpy',
        'shutil',
        'socket',
        'sqlite3',
        'subprocess',
        'tensorflow',
        'threading',
        'torch',
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
        'start',
        'system',
        'write',
    }
    imports = set()
    calls = []
    for path, tree in source_trees():
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

    assert imports.isdisjoint(forbidden_imports)
    assert calls == []


def test_public_surface_has_eligibility_but_no_activation_or_execution_authority():
    required = {
        'AuthorityReference',
        'ApprovalRequest',
        'AuthorityApprovalEvidence',
        'ActivationEligibilityRequest',
        'ActivationEligibilityDecision',
        'evaluate_activation_eligibility',
        'canonical_approval_eligibility_artifact_json',
        'approval_eligibility_artifact_from_canonical_json',
    }
    forbidden = {
        'activate_policy',
        'authenticate_authority',
        'deploy_policy',
        'dispatch',
        'execute_policy',
        'install_policy',
        'load_model',
        'persist',
        'run_policy',
        'train',
    }

    assert required <= set(public_api.__all__)
    assert forbidden.isdisjoint(public_api.__all__)
    assert len(public_api.__all__) == len(set(public_api.__all__))


def test_models_expose_no_executable_payload_mutable_alias_or_runtime_fields():
    forbidden_fields = {
        'active_policy',
        'alias',
        'bytecode',
        'callback',
        'command',
        'current_policy',
        'executable',
        'latest',
        'model_weights',
        'path',
        'payload',
        'python_source',
        'runtime_handle',
        'shell',
        'url',
    }
    models = (
        public_api.AuthorityReference,
        public_api.ApprovalRequest,
        public_api.AuthorityApprovalEvidence,
        public_api.ActivationEligibilityRequest,
        public_api.ActivationEligibilityDecision,
    )

    for model in models:
        assert forbidden_fields.isdisjoint(model.__annotations__)


def test_wheel_contains_only_runtime_sources_and_exact_metadata():
    expected_sources = {
        'ayyo_approval_eligibility/__init__.py',
        'ayyo_approval_eligibility/canonical.py',
        'ayyo_approval_eligibility/errors.py',
        'ayyo_approval_eligibility/evaluation.py',
        'ayyo_approval_eligibility/models.py',
        'ayyo_approval_eligibility/serialization.py',
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package_copy = root / 'approval_eligibility'
        wheel_directory = root / 'wheel'
        shutil.copytree(
            PACKAGE_ROOT,
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
        assert result.returncode == 0, result.stderr
        wheels = tuple(wheel_directory.glob('*.whl'))
        assert len(wheels) == 1
        with zipfile.ZipFile(wheels[0]) as archive:
            names = archive.namelist()
            sources = {name for name in names if name.endswith('.py')}
            metadata_name = next(
                name for name in names if name.endswith('.dist-info/METADATA')
            )
            metadata = archive.read(metadata_name).decode('utf-8')
        assert sources == expected_sources
        assert 'Name: ayyo-approval-eligibility\n' in metadata
        requirements = [
            line.split(':', 1)[1].strip().replace(' ', '')
            for line in metadata.splitlines()
            if line.startswith('Requires-Dist:')
        ]
        assert requirements == ['ayyo-policy-registry==0.1.0']


def test_generated_artifacts_are_ignored_and_not_tracked():
    artifacts = (
        'approval_eligibility/build/lib/package.py',
        'approval_eligibility/dist/package.whl',
        'approval_eligibility/src/ayyo_approval_eligibility.egg-info/PKG-INFO',
    )
    for artifact in artifacts:
        ignored = subprocess.run(
            ['git', 'check-ignore', '--quiet', artifact],
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        assert ignored.returncode == 0
    tracked = subprocess.run(
        ['git', 'ls-files', '--', 'approval_eligibility/**'],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert not any('__pycache__' in item or '.egg-info' in item for item in tracked)
