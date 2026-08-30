# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import ast
import os
from pathlib import Path
import signal
import subprocess
import xml.etree.ElementTree as ET

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROCESS_HELPER = REPOSITORY_ROOT / 'scripts' / 'smoke_processes.sh'
SESSION_LAUNCHER = REPOSITORY_ROOT / 'scripts' / 'smoke_session.py'


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


def run_process_helper(script: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            'AYYO_SMOKE_SHUTDOWN_ATTEMPTS': '10',
            'AYYO_SMOKE_SHUTDOWN_DELAY_SECONDS': '0.02',
        }
    )
    return subprocess.run(
        ['bash', '-c', script],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )


def test_smoke_process_helper_requires_exact_dedicated_ownership() -> None:
    source = PROCESS_HELPER.read_text(encoding='utf-8')
    launcher_source = SESSION_LAUNCHER.read_text(encoding='utf-8')
    assert 'AYYO_SMOKE_RUN_ID' in source
    assert 'smoke_session.py' in source
    assert 'os.setsid()' in launcher_source
    assert 'signal.SIGINT, signal.SIG_DFL' in launcher_source
    assert 'pkill' not in source
    assert 'killall' not in source
    assert '/proc/[0-9]*/environ' in source


def test_owned_graceful_shutdown_does_not_touch_unrelated_process() -> None:
    unrelated = subprocess.Popen(['sleep', '30'])
    try:
        result = run_process_helper(
            f"""
set -euo pipefail
launch_pid=""
source "{PROCESS_HELPER}"
ayyo_smoke_start_owned_launch /dev/null python3 -c '
import signal
import sys
import time
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
time.sleep(30)
'
ayyo_smoke_shutdown_owned_launch
[[ "$ayyo_smoke_shutdown_escalated" -eq 0 ]]
[[ -z "$(ayyo_smoke_owned_pids)" ]]
kill -0 {unrelated.pid}
"""
        )
        assert result.returncode == 0, result.stderr
        assert unrelated.poll() is None
    finally:
        unrelated.send_signal(signal.SIGTERM)
        unrelated.wait(timeout=5)


def test_owned_shutdown_uses_scoped_term_escalation() -> None:
    result = run_process_helper(
        f"""
set -euo pipefail
launch_pid=""
source "{PROCESS_HELPER}"
ready_file="$(mktemp -t ayyo-smoke-term-ready.XXXXXX)"
rm -f "$ready_file"
trap 'rm -f "$ready_file"' EXIT
ayyo_smoke_start_owned_launch /dev/null python3 -c '
import pathlib
import signal
import sys
import time
signal.signal(signal.SIGINT, signal.SIG_IGN)
pathlib.Path(sys.argv[1]).touch()
time.sleep(30)
' "$ready_file"
for _ in {{1..100}}; do
  [[ -f "$ready_file" ]] && break
  sleep 0.01
done
[[ -f "$ready_file" ]]
ayyo_smoke_shutdown_owned_launch
[[ "$ayyo_smoke_shutdown_escalated" -eq 1 ]]
[[ -z "$(ayyo_smoke_owned_pids)" ]]
"""
    )
    assert result.returncode == 0, result.stderr
    assert 'graceful launch shutdown left these owned processes' in result.stderr


def test_owned_shutdown_fails_after_scoped_forced_cleanup() -> None:
    result = run_process_helper(
        f"""
set -euo pipefail
launch_pid=""
source "{PROCESS_HELPER}"
ayyo_smoke_start_owned_launch /dev/null python3 -c '
import signal
import time
signal.signal(signal.SIGINT, signal.SIG_IGN)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(30)
'
owned_pid="$launch_pid"
set +e
ayyo_smoke_shutdown_owned_launch
shutdown_status="$?"
set -e
[[ "$shutdown_status" -ne 0 ]]
! kill -0 "$owned_pid" 2>/dev/null
"""
    )
    assert result.returncode == 0, result.stderr
    assert 'smoke must fail' in result.stderr


def test_early_failure_trap_still_removes_owned_processes() -> None:
    result = run_process_helper(
        f"""
set -euo pipefail
launch_pid=""
source "{PROCESS_HELPER}"
cleanup() {{
  status="$?"
  trap - EXIT
  ayyo_smoke_shutdown_owned_launch || status=1
  exit "$status"
}}
trap cleanup EXIT
ayyo_smoke_start_owned_launch /dev/null python3 -c '
import signal
import time
signal.signal(signal.SIGINT, signal.SIG_IGN)
time.sleep(30)
'
exit 7
"""
    )
    assert result.returncode == 7, result.stderr
    assert 'graceful launch shutdown left these owned processes' in result.stderr


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
        ('gz-sim-imu-system', 'gz::sim::systems::Imu'),
        ('gz-sim-sensors-system', 'gz::sim::systems::Sensors'),
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


def test_bridge_allowlist_contains_only_reviewed_observation_topics() -> None:
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
        },
        {
            'ros_topic_name': '/ayyo/imu/data',
            'gz_topic_name': '/ayyo/imu/data',
            'ros_type_name': 'sensor_msgs/msg/Imu',
            'gz_type_name': 'gz.msgs.IMU',
            'direction': 'GZ_TO_ROS',
            'lazy': False,
            'publisher_queue': 10,
            'subscriber_queue': 10,
        },
        {
            'ros_topic_name': '/ayyo/localization/odometry',
            'gz_topic_name': '/ayyo/localization/ground_truth/odometry',
            'ros_type_name': 'nav_msgs/msg/Odometry',
            'gz_type_name': 'gz.msgs.Odometry',
            'direction': 'GZ_TO_ROS',
            'lazy': False,
            'publisher_queue': 10,
            'subscriber_queue': 10,
        },
    ]
    camera_config = yaml.safe_load(
        (PACKAGE_ROOT / 'config' / 'ros_gz_camera_bridge.yaml').read_text(
            encoding='utf-8'
        )
    )
    assert camera_config == [
        {
            'ros_topic_name': '/ayyo/camera/head/camera_info',
            'gz_topic_name': '/ayyo/camera/head/camera_info',
            'ros_type_name': 'sensor_msgs/msg/CameraInfo',
            'gz_type_name': 'gz.msgs.CameraInfo',
            'direction': 'GZ_TO_ROS',
            'lazy': False,
            'publisher_queue': 2,
            'subscriber_queue': 2,
        }
    ]
    depth_camera_config = yaml.safe_load(
        (PACKAGE_ROOT / 'config' / 'ros_gz_depth_camera_bridge.yaml').read_text(
            encoding='utf-8'
        )
    )
    assert depth_camera_config == [
        {
            'ros_topic_name': '/ayyo/camera/head/depth/camera_info',
            'gz_topic_name': '/ayyo/camera/head/depth/camera_info',
            'ros_type_name': 'sensor_msgs/msg/CameraInfo',
            'gz_type_name': 'gz.msgs.CameraInfo',
            'direction': 'GZ_TO_ROS',
            'lazy': False,
            'publisher_queue': 2,
            'subscriber_queue': 2,
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
        'ayyo_world_model',
        'controller_manager',
        'joint_state_publisher',
        'robot_state_publisher',
        'ros_gz_bridge',
        'ros_gz_image',
        'ros_gz_sim',
        'ayyo_simulation_control',
    }
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert 'rviz2' not in source
    assert 'condition=UnlessCondition(enable_control)' in source


def test_launch_owns_gazebo_without_shell_child_or_generic_wrapper() -> None:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert source.count('gazebo_server = ExecuteProcess(') == 1
    assert source.count('gazebo_graphical = ExecuteProcess(') == 1
    assert source.count('shell=False') == 2
    assert source.count('on_exit=Shutdown()') == 2
    assert source.count('additional_env=gazebo_environment') == 2
    assert "'GZ_SIM_SYSTEM_PLUGIN_PATH'" in source
    assert "os.environ.get('LD_LIBRARY_PATH', '')" in source
    assert "FindExecutable(name='gz')" in source
    assert 'IncludeLaunchDescription' not in source
    assert 'gz_sim.launch.py' not in source
    assert 'shell=True' not in source


def test_launch_spawns_authoritative_description_as_static() -> None:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert "FindPackageShare('ayyo_description')" in source
    assert "'ayyo.urdf.xacro'" in source
    assert "' simulation_mode:=true simulation_static:=true'" in source
    assert "' simulation_control:='" in source
    assert "' simulation_localization:='" in source
    assert "' simulation_camera:='" in source
    assert "' simulation_depth_camera:='" in source
    assert "' simulation_controller_config:='" in source
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
    assert defaults['enable_control'] == 'false'
    assert defaults['enable_development_control'] == 'false'
    assert defaults['enable_world_model'] == 'false'
    assert defaults['enable_localization'] == 'false'
    assert defaults['enable_camera'] == 'false'
    assert defaults['enable_depth_camera'] == 'false'
    assert defaults['enable_visual_reference_interpreter'] == 'false'
    assert defaults['enable_visual_producer_evaluation_fixture'] == 'false'
    assert defaults['world_model_retention_ttl_ms'] == '2000'
    assert defaults['use_meshes'] == 'false'
    assert defaults['spawn_z'] == '0.95'


def test_controller_configuration_is_exactly_one_position_joint() -> None:
    config = yaml.safe_load(
        (PACKAGE_ROOT / 'config' / 'controllers.yaml').read_text(encoding='utf-8')
    )
    manager = config['controller_manager']['ros__parameters']
    assert manager['update_rate'] == 100
    assert manager['use_sim_time'] is True
    assert manager['enforce_command_limits'] is True
    assert manager['joint_state_broadcaster']['type'] == (
        'joint_state_broadcaster/JointStateBroadcaster'
    )
    assert manager['ayyo_neck_position_controller']['type'] == (
        'forward_command_controller/ForwardCommandController'
    )
    controller = config['ayyo_neck_position_controller']['ros__parameters']
    assert controller == {
        'use_sim_time': True,
        'joints': ['neck_yaw_joint'],
        'interface_name': 'position',
    }
    broadcaster = config['joint_state_broadcaster']['ros__parameters']
    assert len(broadcaster['joints']) == 18
    assert len(set(broadcaster['joints'])) == 18
    assert broadcaster['interfaces'] == ['position', 'velocity', 'effort']


def test_control_lifecycle_is_spawn_then_state_then_position() -> None:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert 'target_action=spawn_ayyo' in source
    assert 'on_exit=[joint_state_broadcaster_spawner]' in source
    assert 'target_action=joint_state_broadcaster_spawner' in source
    assert 'on_exit=[position_controller_spawner]' in source
    assert 'target_action=position_controller_spawner' in source
    assert 'on_exit=[development_control_node]' in source
    assert source.count('condition=IfCondition(enable_control)') == 2
    assert 'AndSubstitution(enable_control, enable_development_control)' in source


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
    assert 'ayyo_simulation_control' in dependencies
    assert 'ayyo_world_model' in dependencies
    assert {
        'controller_manager',
        'forward_command_controller',
        'gz_ros2_control',
        'joint_state_broadcaster',
        'ros_gz_image',
    } <= dependencies


def test_camera_bridges_are_one_way_fixed_and_default_off() -> None:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert "enable_camera = LaunchConfiguration('enable_camera')" in source
    assert "arguments=['/ayyo/camera/head/image_raw']" in source
    assert "'ros_gz_camera_bridge.yaml'" in source
    assert "name='ayyo_head_camera_image_bridge'" in source
    assert "name='ayyo_head_camera_info_bridge'" in source
    assert source.count('condition=IfCondition(enable_camera)') == 2
    assert 'GZ_TO_ROS' in (
        PACKAGE_ROOT / 'config' / 'ros_gz_camera_bridge.yaml'
    ).read_text(encoding='utf-8')
    assert 'ROS_TO_GZ' not in source


def test_depth_camera_bridges_are_one_way_fixed_and_default_off() -> None:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert "enable_depth_camera = LaunchConfiguration('enable_depth_camera')" in source
    assert "arguments=['/ayyo/camera/head/depth/image_raw']" in source
    assert "'ros_gz_depth_camera_bridge.yaml'" in source
    assert "name='ayyo_head_depth_image_bridge'" in source
    assert "name='ayyo_head_depth_camera_info_bridge'" in source
    assert source.count('condition=IfCondition(enable_depth_camera)') == 2
    assert 'GZ_TO_ROS' in (
        PACKAGE_ROOT / 'config' / 'ros_gz_depth_camera_bridge.yaml'
    ).read_text(encoding='utf-8')
    assert 'ROS_TO_GZ' not in source


def test_synthetic_visual_interpreter_is_explicit_and_default_off() -> None:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert (
        'enable_visual_reference_interpreter = LaunchConfiguration('
        in source
    )
    assert "'enable_visual_reference_interpreter'" in source
    assert "default_value='false'" in source
    assert "'enable_visual_reference_interpreter': (" in source


def test_evaluated_visual_fixture_is_explicit_and_default_off() -> None:
    source = (PACKAGE_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert (
        'enable_visual_producer_evaluation_fixture = LaunchConfiguration('
        in source
    )
    assert "'enable_visual_producer_evaluation_fixture'" in source
    assert "default_value='false'" in source
    assert "'enable_visual_producer_evaluation_fixture': (" in source


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
        'smoke_processes.sh',
        'ayyo_smoke_shutdown_owned_launch',
        'owned-process set is empty after bounded shutdown',
        'unable to convert call argument',
    ):
        assert expected in script
    assert 'headless:=true' in script
    assert 'rviz2' not in script


def test_controlled_smoke_uses_only_typed_motion_path() -> None:
    path = REPOSITORY_ROOT / 'scripts' / 'smoke_simulation_control.sh'
    script = path.read_text(encoding='utf-8')
    for expected in (
        'enable_control:=true',
        'enable_development_control:=true',
        'ros2 control list_controllers',
        'ros2 control list_hardware_interfaces',
        'Publisher count: 1',
        'development_command.py --position 0.1',
        'development_command.py --position 1.3',
        'has_state_feedback',
        'above_maximum',
        'smoke_processes.sh',
        'ayyo_smoke_shutdown_owned_launch',
        'exception was never retrieved',
        'readonly wait_deadline_seconds=60',
        'timeout --signal=INT --kill-after=5 30',
    ):
        assert expected in script
    assert 'ros2 topic pub' not in script
    assert '/ayyo_neck_position_controller/commands' not in script
    assert path.stat().st_mode & 0o111


def test_simulation_source_has_no_runtime_dispatch_surface() -> None:
    source_text = production_source_text()
    for forbidden in ('RuntimeBridge', 'RuntimeDispatcher', 'rclpy.action'):
        assert forbidden not in source_text
