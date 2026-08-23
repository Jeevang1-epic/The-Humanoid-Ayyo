# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def launch_tree() -> ast.AST:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    return ast.parse(source)


def constant_keyword(call: ast.Call, name: str) -> object:
    keyword = next(item for item in call.keywords if item.arg == name)
    assert isinstance(keyword.value, ast.Constant)
    return keyword.value.value


def production_source_text() -> str:
    production_paths = (
        PACKAGE_ROOT / 'CMakeLists.txt',
        PACKAGE_ROOT / 'package.xml',
        *sorted((PACKAGE_ROOT / 'config').rglob('*')),
        *sorted((PACKAGE_ROOT / 'launch').rglob('*')),
        *sorted((PACKAGE_ROOT / 'worlds').rglob('*')),
    )
    return '\n'.join(
        path.read_text(encoding='utf-8')
        for path in production_paths
        if path.is_file() and '__pycache__' not in path.parts
    )


def test_world_is_valid_sdformat() -> None:
    world_path = PACKAGE_ROOT / 'worlds' / 'ayyo_foundation.sdf'
    result = subprocess.run(
        ['gz', 'sdf', '-k', str(world_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'Valid.\n'


def test_world_has_only_required_harmonic_systems() -> None:
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'ayyo_foundation.sdf').getroot()
    assert root.get('version') == '1.10'
    world = root.find('world')
    assert world is not None and world.get('name') == 'ayyo_foundation'
    plugins = {
        (plugin.get('filename'), plugin.get('name'))
        for plugin in world.findall('plugin')
    }
    assert plugins == {
        ('gz-sim-physics-system', 'gz::sim::systems::Physics'),
        ('gz-sim-scene-broadcaster-system', 'gz::sim::systems::SceneBroadcaster'),
        ('gz-sim-user-commands-system', 'gz::sim::systems::UserCommands'),
    }


def test_world_contains_only_environment_models() -> None:
    root = ET.parse(PACKAGE_ROOT / 'worlds' / 'ayyo_foundation.sdf').getroot()
    models = root.findall('./world/model')
    assert [model.get('name') for model in models] == ['ground_plane']
    assert models[0].findtext('static') == 'true'


def test_no_gazebo_classic_api_is_present() -> None:
    source_text = production_source_text()
    for forbidden in ('gazebo_msgs', 'gazebo_ros', 'libgazebo'):
        assert forbidden not in source_text


def test_bridge_allowlist_contains_only_simulation_clock() -> None:
    config = yaml.safe_load(
        (PACKAGE_ROOT / 'config' / 'ros_gz_bridge.yaml').read_text(
            encoding='utf-8'
        )
    )
    assert config == [
        {
            'ros_topic_name': '/clock',
            'gz_topic_name': '/clock',
            'ros_type_name': 'rosgraph_msgs/msg/Clock',
            'gz_type_name': 'gz.msgs.Clock',
            'direction': 'GZ_TO_ROS',
            'lazy': False,
            'publisher_queue': 10,
            'subscriber_queue': 10,
        }
    ]


def test_launch_uses_bounded_simulation_nodes() -> None:
    tree = launch_tree()
    node_calls = [
        call
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == 'Node'
    ]
    assert {constant_keyword(call, 'package') for call in node_calls} == {
        'joint_state_publisher',
        'robot_state_publisher',
        'ros_gz_bridge',
        'ros_gz_sim',
    }
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert 'rviz2' not in source
    assert 'controller_manager' not in source


def test_launch_spawns_authoritative_description_as_static() -> None:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert "FindPackageShare('ayyo_description')" in source
    assert "'ayyo.urdf.xacro'" in source
    assert "' simulation_mode:=true simulation_static:=true'" in source
    assert "'topic': 'robot_description'" in source
    assert "'allow_renaming': False" in source


def test_launch_defaults_to_headless_proxy_ground_contact() -> None:
    tree = launch_tree()
    defaults: dict[str, object] = {}
    for call in ast.walk(tree):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == 'DeclareLaunchArgument'
        ):
            continue
        assert isinstance(call.args[0], ast.Constant)
        default = next(
            (keyword.value for keyword in call.keywords if keyword.arg == 'default_value'),
            None,
        )
        if isinstance(default, ast.Constant):
            defaults[call.args[0].value] = default.value
    assert defaults['headless'] == 'true'
    assert defaults['use_meshes'] == 'false'
    assert defaults['spawn_z'] == '0.95'


def test_simulation_package_has_no_authorization_layer_dependency() -> None:
    manifest = ET.parse(PACKAGE_ROOT / 'package.xml').getroot()
    dependencies = {
        element.text
        for element in manifest
        if element.tag.endswith('depend') and element.text
    }
    assert not dependencies & {
        'ayyo_executive',
        'ayyo_memory',
        'ayyo_memory_validation',
        'ayyo_personal_context',
        'ayyo_runtime_bridge',
        'ayyo_safety',
        'ayyo_skill_manager',
    }
    assert 'ayyo_description' in dependencies


def test_simulation_installs_only_owned_resources() -> None:
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'DIRECTORY config launch worlds' in cmake
    assert 'ament_python_install_package' not in cmake


def test_owned_python_sources_retain_project_copyright() -> None:
    for relative_path in (
        'launch/simulation.launch.py',
        'test/test_simulation.py',
    ):
        source = (PACKAGE_ROOT / relative_path).read_text(encoding='utf-8')
        assert 'Copyright 2026 Ayyo Project Authors' in source


def test_headless_smoke_script_checks_complete_lifecycle() -> None:
    script = (REPOSITORY_ROOT / 'scripts' / 'smoke_simulation.sh').read_text(
        encoding='utf-8'
    )
    for expected in (
        'validate_description.py',
        'simulation.launch.py',
        'ros2 node list',
        'ros2 topic echo --once /tf',
        'ros2 topic echo --once /clock',
        'gz model --list',
        'kill -INT',
        'simulation processes shut down cleanly',
    ):
        assert expected in script
    assert 'headless:=true' in script
    assert 'rviz2' not in script


def test_simulation_source_has_no_runtime_dispatch_surface() -> None:
    source_text = production_source_text()
    for forbidden in ('RuntimeBridge', 'RuntimeDispatcher', 'rclpy.action'):
        assert forbidden not in source_text
