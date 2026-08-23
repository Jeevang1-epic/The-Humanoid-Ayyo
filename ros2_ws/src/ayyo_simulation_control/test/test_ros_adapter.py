# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from ayyo_simulation_control import (
    CONTROLLED_JOINT_ALLOWLIST,
    UrdfJointLimitCatalog,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
INTERFACES_ROOT = REPOSITORY_ROOT / 'ros2_ws' / 'src' / 'ayyo_interfaces'


def script_source(name: str) -> str:
    return (PACKAGE_ROOT / 'scripts' / name).read_text(encoding='utf-8')


def test_authoritative_description_drives_runtime_limit_catalog() -> None:
    xacro_path = (
        REPOSITORY_ROOT
        / 'ros2_ws'
        / 'src'
        / 'ayyo_description'
        / 'urdf'
        / 'ayyo.urdf.xacro'
    )
    result = subprocess.run(
        ['xacro', str(xacro_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    catalog = UrdfJointLimitCatalog(result.stdout)
    assert catalog.allowlist == CONTROLLED_JOINT_ALLOWLIST == ('neck_yaw_joint',)
    assert len(catalog.joints) == 34
    neck = catalog.contract_for('neck_yaw_joint')
    assert neck is not None
    assert (neck.lower, neck.upper) == (-1.2, 1.2)


def test_development_service_contract_is_typed_and_auditable() -> None:
    interface = (
        INTERFACES_ROOT / 'srv' / 'SetDevelopmentJointPosition.srv'
    ).read_text(encoding='utf-8')
    for field in (
        'uint8 command_type',
        'string[] joint_names',
        'float64[] positions',
        'builtin_interfaces/Time issued_at',
        'builtin_interfaces/Duration valid_for',
        'string injection_id',
        'string command_fingerprint',
        'string result_fingerprint',
        'bool has_state_feedback',
        'float64 initial_position',
        'float64 final_position',
    ):
        assert field in interface
    assert interface.count('---') == 1


def test_ros_adapter_uses_only_reviewed_static_ros_names() -> None:
    source = script_source('simulation_control_node.py')
    tree = ast.parse(source)
    assignments = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance((target := node.targets[0]), ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    assert assignments['CONTROLLER_MANAGER'] == '/controller_manager'
    assert assignments['POSITION_CONTROLLER'] == 'ayyo_neck_position_controller'
    assert assignments['SERVICE_NAME'] == '/ayyo/development/set_joint_position'
    assert 'rclpy.action' not in source
    assert 'subprocess' not in source
    assert 'eval(' not in source
    assert 'exec(' not in source
    assert 'except Exception' not in source
    assert 'create_timer' not in source
    assert 'def _refresh_lifecycle(self)' in source
    assert 'ListControllers' in source
    assert 'ListHardwareComponents' in source


def test_ros_adapter_drains_callbacks_before_context_shutdown() -> None:
    source = script_source('simulation_control_node.py')
    assert 'class DrainingMultiThreadedExecutor' in source
    assert 'self._executor.shutdown(wait=True)' in source
    assert 'future.result()' in source
    assert 'SignalHandlerOptions.NO' in source
    assert source.index('node.close()') < source.index('executor.shutdown()')
    assert source.index('executor.shutdown()') < source.index('node.destroy_node()')
    assert source.index('node.destroy_node()') < source.index('rclpy.shutdown()')


def test_development_client_cannot_select_ros_endpoints() -> None:
    source = script_source('development_command.py')
    assert "SERVICE_NAME = '/ayyo/development/set_joint_position'" in source
    assert "INJECTION_ID = 'development.simulation.control.v1'" in source
    assert '--topic' not in source
    assert '--service' not in source
    assert '--action' not in source
    assert 'subprocess' not in source


def test_ros_wrapper_installs_single_owned_core_and_scripts() -> None:
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert '../../../simulation_control/src/ayyo_simulation_control' in cmake
    assert 'scripts/development_command.py' in cmake
    assert 'scripts/simulation_control_node.py' in cmake
    assert not (PACKAGE_ROOT / 'ayyo_simulation_control').exists()


def test_ros_wrapper_dependency_boundary_is_downstream_only() -> None:
    manifest = ET.parse(PACKAGE_ROOT / 'package.xml').getroot()
    dependencies = {
        element.text
        for element in manifest
        if element.tag.endswith('depend') and element.text
    }
    assert {
        'ayyo_interfaces',
        'controller_manager_msgs',
        'rclpy',
        'sensor_msgs',
        'std_msgs',
    } <= dependencies
    assert not dependencies & {
        'ayyo_executive',
        'ayyo_memory',
        'ayyo_memory_validation',
        'ayyo_personal_context',
        'ayyo_safety',
        'ayyo_skill_manager',
    }


def test_owned_python_sources_retain_project_copyright() -> None:
    for relative_path in (
        'scripts/development_command.py',
        'scripts/simulation_control_node.py',
        'test/test_ros_adapter.py',
    ):
        assert 'Copyright 2026 Ayyo Project Authors' in (
            PACKAGE_ROOT / relative_path
        ).read_text(encoding='utf-8')
