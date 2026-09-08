from __future__ import annotations

import ast
from pathlib import Path
import tomllib

import ayyo_promotion_control as public_api


PACKAGE_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PACKAGE_ROOT / 'src' / 'ayyo_promotion_control'


def test_distribution_has_one_explicit_upstream_dependency_and_no_entrypoint():
    metadata = tomllib.loads((PACKAGE_ROOT / 'pyproject.toml').read_text())

    assert metadata['project']['name'] == 'ayyo-promotion-control'
    assert metadata['project']['version'] == '0.1.0'
    assert metadata['project']['requires-python'] == '>=3.12'
    assert metadata['project']['dependencies'] == ['ayyo-learning-evaluation==0.1.0']
    assert 'scripts' not in metadata['project']
    assert 'entry-points' not in metadata['project']


def test_dependency_direction_remains_promotion_to_learning_to_teach():
    repository = PACKAGE_ROOT.parent
    learning = tomllib.loads((repository / 'learning_evaluation' / 'pyproject.toml').read_text())
    teach = tomllib.loads((repository / 'teach_mode' / 'pyproject.toml').read_text())

    assert learning['project']['dependencies'] == ['ayyo-teach-mode==0.1.0']
    assert not any('promotion' in item for item in learning['project']['dependencies'])
    assert not any('promotion' in item for item in teach['project'].get('dependencies', []))


def test_runtime_source_imports_only_stdlib_and_learning_evaluation():
    allowed_roots = {
        '__future__',
        'dataclasses',
        'enum',
        'hashlib',
        'json',
        're',
        'unicodedata',
        'ayyo_learning_evaluation',
    }
    imports = set()
    for source_path in SOURCE_ROOT.glob('*.py'):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split('.')[0])

    assert imports <= allowed_roots
    assert 'ayyo_teach_mode' not in imports


def test_runtime_source_has_no_io_process_network_thread_or_dynamic_code_calls():
    forbidden_calls = {
        'eval',
        'exec',
        'open',
        'builtins.compile',
        'os.system',
        'os.popen',
        'subprocess.run',
        'subprocess.Popen',
        'threading.Thread',
        'multiprocessing.Process',
        'asyncio.create_task',
        'urllib.request.urlopen',
        'requests.request',
        'socket.connect',
    }
    observed = set()
    for source_path in SOURCE_ROOT.glob('*.py'):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                observed.add(ast.unparse(node.func))

    assert observed.isdisjoint(forbidden_calls)


def test_public_surface_is_explicit_and_contains_no_runtime_authority():
    required = {
        'CandidatePromotionRequest',
        'PromotionCriteria',
        'PromotionDecision',
        'KnownGoodPolicyReference',
        'RollbackCriteria',
        'RollbackRequest',
        'RollbackDecision',
        'evaluate_promotion',
        'evaluate_rollback',
        'canonical_control_artifact_json',
        'control_artifact_from_canonical_json',
    }
    forbidden = {
        'install_policy',
        'execute_policy',
        'promote_policy',
        'rollback_policy',
        'dispatch',
        'train',
        'load_model',
    }

    assert required <= set(public_api.__all__)
    assert forbidden.isdisjoint(public_api.__all__)
    assert set(public_api.__all__) == {name for name in public_api.__all__}
