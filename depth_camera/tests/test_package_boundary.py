from __future__ import annotations

import ast
from pathlib import Path
import tomllib

import ayyo_depth_camera


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / 'src' / 'ayyo_depth_camera'


def test_core_has_no_ros_gazebo_control_network_or_persistence_dependency() -> None:
    forbidden = {
        'ayyo_executive',
        'ayyo_memory',
        'ayyo_safety',
        'ayyo_skill_manager',
        'gazebo',
        'gz',
        'rclpy',
        'requests',
        'sensor_msgs',
        'socket',
        'sqlite3',
        'subprocess',
    }
    imported: set[str] = set()
    for path in SOURCE_ROOT.glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split('.')[0])
            assert not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {'eval', 'exec', '__import__'}
            )
    assert not imported & forbidden


def test_only_world_model_runtime_dependency_is_declared() -> None:
    with (PACKAGE_ROOT / 'pyproject.toml').open('rb') as stream:
        project = tomllib.load(stream)['project']
    assert project['dependencies'] == ['ayyo-world-model==0.1.0']


def test_public_exports_are_importable() -> None:
    assert ayyo_depth_camera.__all__
    assert all(hasattr(ayyo_depth_camera, name) for name in ayyo_depth_camera.__all__)
