# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

from sensor_msgs.msg import Imu, JointState


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
INTERFACES_ROOT = REPOSITORY_ROOT / 'ros2_ws' / 'src' / 'ayyo_interfaces'
SIMULATION_ROOT = REPOSITORY_ROOT / 'ros2_ws' / 'src' / 'ayyo_simulation'


def script_source(name: str) -> str:
    return (PACKAGE_ROOT / 'scripts' / name).read_text(encoding='utf-8')


def adapter_module():
    path = PACKAGE_ROOT / 'scripts' / 'world_model_node.py'
    spec = importlib.util.spec_from_file_location('ayyo_world_model_node_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_only_service_contract_is_bounded_and_typed() -> None:
    interface = (INTERFACES_ROOT / 'srv' / 'GetRobotBodyState.srv').read_text(
        encoding='utf-8'
    )
    for field in (
        'string robot_id',
        'string snapshot_id',
        'string snapshot_fingerprint',
        'builtin_interfaces/Time queried_at',
        'string[] joint_names',
        'float64[] positions',
        'builtin_interfaces/Time[] joint_observed_at',
        'float64[] joint_confidence',
        'uint8[] joint_freshness',
        'string[] joint_observation_ids',
        'uint32 recent_evidence_count',
        'string[] sensor_ids',
        'bool has_imu',
        'float64[] imu_orientation_xyzw',
        'bool has_imu_orientation_covariance',
        'uint8 base_pose_availability',
        'uint32 perception_rejected_count',
    ):
        assert field in interface
    assert interface.count('---') == 1
    assert 'string expression' not in interface
    assert 'string query' not in interface


def test_adapter_uses_managed_lifecycle_and_no_background_polling() -> None:
    source = script_source('world_model_node.py')
    assert 'class AyyoWorldModelNode(LifecycleNode)' in source
    for callback in (
        'on_configure',
        'on_activate',
        'on_deactivate',
        'on_cleanup',
        'on_shutdown',
        'on_error',
    ):
        assert f'def {callback}' in source
    assert 'create_timer' not in source
    assert 'Thread(' not in source
    assert 'SingleThreadedExecutor' in source
    assert source.index('trigger_deactivate') < source.index('trigger_cleanup')
    assert source.index('trigger_cleanup') < source.index('destroy_node()')


def test_adapter_subscribes_only_to_fixed_standard_proprioceptive_interfaces() -> None:
    source = script_source('world_model_node.py')
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
    assert assignments['JOINT_STATE_TOPIC'] == '/joint_states'
    assert assignments['IMU_TOPIC'] == '/ayyo/imu/data'
    assert assignments['QUERY_SERVICE'] == '/ayyo/world_model/get_robot_body_state'
    assert 'create_subscription(' in source
    assert 'JOINT_STATE_TOPIC' in source
    assert 'IMU_TOPIC' in source
    assert 'qos_profile_sensor_data' in source
    assert 'get_topic_names_and_types' not in source
    assert "declare_parameter('topic'" not in source
    assert 'eval(' not in source
    assert 'exec(' not in source
    assert 'subprocess' not in source


def test_standard_joint_state_normalization_is_typed_and_partial_safe() -> None:
    module = adapter_module()
    message = JointState()
    message.header.stamp.sec = 2
    message.header.stamp.nanosec = 3
    message.name = ['neck_yaw_joint', 'head_pitch_joint']
    message.position = [0.1, 0.2]
    message.effort = [0.3, 0.4]
    observation = module.normalize_joint_state(
        message,
        module.SOURCE_PROFILES[module.SIMULATION_SOURCE_PROFILE],
    )
    assert observation.observed_at_ns == 2_000_000_003
    assert [item.joint_name for item in observation.joints] == [
        'head_pitch_joint',
        'neck_yaw_joint',
    ]
    assert all(item.velocity is None for item in observation.joints)
    assert observation.provenance.source_kind.value == 'simulation'


def test_malformed_joint_state_shapes_fail_before_working_memory() -> None:
    module = adapter_module()
    message = JointState()
    message.name = ['neck_yaw_joint']
    message.position = []
    provenance = module.SOURCE_PROFILES[module.SIMULATION_SOURCE_PROFILE]
    try:
        module.normalize_joint_state(message, provenance)
    except ValueError as error:
        assert 'names and positions' in str(error)
    else:
        raise AssertionError('malformed standard joint state was normalized')


def test_standard_imu_normalization_preserves_ros_unavailable_and_unknown_semantics() -> None:
    module = adapter_module()
    message = Imu()
    message.header.stamp.sec = 2
    message.header.stamp.nanosec = 3
    message.header.frame_id = 'imu_link'
    message.orientation.w = 1.0
    message.angular_velocity.x = 0.1
    message.linear_acceleration.z = 9.81
    observation = module.normalize_imu(
        message,
        module.IMU_SOURCE_PROFILES[module.SIMULATION_SOURCE_PROFILE],
    )
    assert observation.observed_at_ns == 2_000_000_003
    assert observation.sensor == module.IMU_SENSOR
    assert observation.orientation_xyzw == (0.0, 0.0, 0.0, 1.0)
    assert observation.orientation_covariance is None
    assert observation.angular_velocity_covariance is None
    assert observation.quality is None

    message.orientation_covariance[0] = -1.0
    unavailable_orientation = module.normalize_imu(
        message,
        module.IMU_SOURCE_PROFILES[module.SIMULATION_SOURCE_PROFILE],
    )
    assert unavailable_orientation.orientation_xyzw is None
    assert unavailable_orientation.orientation_covariance is None


def test_malformed_imu_frame_numbers_and_covariance_fail_before_admission() -> None:
    module = adapter_module()
    provenance = module.IMU_SOURCE_PROFILES[module.SIMULATION_SOURCE_PROFILE]
    message = Imu()
    message.header.frame_id = 'other_imu_link'
    message.orientation.w = 1.0
    try:
        module.normalize_imu(message, provenance)
    except ValueError as error:
        assert 'frame identity' in str(error)
    else:
        raise AssertionError('wrong IMU frame was normalized')

    message.header.frame_id = 'imu_link'
    message.angular_velocity.x = float('nan')
    try:
        module.normalize_imu(message, provenance)
    except module.WorldModelValidationError:
        pass
    else:
        raise AssertionError('non-finite IMU evidence was normalized')

    message.angular_velocity.x = 0.0
    message.orientation_covariance[0] = -0.1
    try:
        module.normalize_imu(message, provenance)
    except module.WorldModelValidationError as error:
        assert error.code.value == 'malformed_covariance'
    else:
        raise AssertionError('negative IMU variance was normalized')


def test_all_explicitly_unavailable_imu_fields_do_not_create_measurement() -> None:
    module = adapter_module()
    message = Imu()
    message.header.frame_id = 'imu_link'
    message.orientation_covariance[0] = -1.0
    message.angular_velocity_covariance[0] = -1.0
    message.linear_acceleration_covariance[0] = -1.0
    try:
        module.normalize_imu(
            message,
            module.IMU_SOURCE_PROFILES[module.SIMULATION_SOURCE_PROFILE],
        )
    except module.WorldModelValidationError as error:
        assert 'at least one supplied estimate' in error.detail
    else:
        raise AssertionError('fully unavailable IMU became a measurement')


def test_simulation_and_physical_profiles_cannot_masquerade_as_each_other() -> None:
    source = script_source('world_model_node.py')
    for expected in (
        "SIMULATION_SOURCE_PROFILE = 'simulation_ros2_control_v1'",
        "PHYSICAL_SOURCE_PROFILE = 'physical_ros2_control_v1'",
        'source_kind=ObservationSourceKind.SIMULATION',
        'source_kind=ObservationSourceKind.PHYSICAL_SENSOR',
        'clock=ObservationClock.ROS_SIMULATION_TIME',
        'clock=ObservationClock.ROS_SYSTEM_TIME',
        "'source profile and ROS clock configuration disagree'",
    ):
        assert expected in source
    assert 'gazebo' not in source.lower()
    assert 'gz_' not in source


def test_adapter_learns_only_from_observation_not_control_request() -> None:
    source = script_source('world_model_node.py')
    for forbidden in (
        'SetDevelopmentJointPosition',
        'SimulationControlCommand',
        'ayyo_neck_position_controller',
        '/commands',
        'controller_manager',
    ):
        assert forbidden not in source
    assert 'RobotStateObservation' in source
    assert 'JointState' in source
    assert 'ImuObservation' in source
    assert 'PerceptionTrustBoundary' in source
    assert '_admit_and_retain(observation)' in source


def test_wrapper_installs_single_owned_core_packages_and_fixed_clients() -> None:
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert '../../../world_model/src/ayyo_world_model' in cmake
    assert '../../../working_memory/src/ayyo_working_memory' in cmake
    assert '../../../perception/src/ayyo_perception' in cmake
    assert 'scripts/world_model_node.py' in cmake
    assert 'scripts/body_state_query.py' in cmake
    assert not (PACKAGE_ROOT / 'ayyo_world_model').exists()
    assert not (PACKAGE_ROOT / 'ayyo_working_memory').exists()
    assert not (PACKAGE_ROOT / 'ayyo_perception').exists()


def test_ros_dependency_boundary_has_no_cognition_or_durable_memory() -> None:
    manifest = ET.parse(PACKAGE_ROOT / 'package.xml').getroot()
    dependencies = {
        element.text
        for element in manifest
        if element.tag.endswith('depend') and element.text
    }
    assert {'ayyo_interfaces', 'builtin_interfaces', 'rclpy', 'sensor_msgs'} <= dependencies
    assert not dependencies & {
        'ayyo_executive',
        'ayyo_memory',
        'ayyo_memory_validation',
        'ayyo_personal_context',
        'ayyo_runtime_bridge',
        'ayyo_safety',
        'ayyo_skill_manager',
    }


def test_query_client_has_one_fixed_read_only_endpoint_and_bounded_waits() -> None:
    source = script_source('body_state_query.py')
    assert "QUERY_SERVICE = '/ayyo/world_model/get_robot_body_state'" in source
    assert 'wait_for_service(timeout_sec=5.0)' in source
    assert 'spin_until_future_complete(node, future, timeout_sec=5.0)' in source
    assert '--topic' not in source
    assert '--service' not in source
    assert '--action' not in source


def test_simulation_launch_keeps_adapter_opt_in_and_pins_simulation_profile() -> None:
    source = (SIMULATION_ROOT / 'launch' / 'simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert "enable_world_model = LaunchConfiguration('enable_world_model')" in source
    assert "'enable_world_model',\n                default_value='false'" in source
    assert "package='ayyo_world_model'" in source
    assert "{'source_profile': 'simulation_ros2_control_v1'}" in source
    assert 'condition=IfCondition(enable_world_model)' in source


def test_integration_smoke_proves_feedback_identity_and_clean_shutdown() -> None:
    source = (REPOSITORY_ROOT / 'scripts' / 'smoke_world_model.sh').read_text(
        encoding='utf-8'
    )
    for expected in (
        'enable_world_model:=true',
        'ros2 lifecycle get /ayyo_world_model',
        'body_state_query.py',
        '--robot-id other.robot.v1',
        'development_command.py --position 0.1',
        'joint_observation_ids',
        'snapshot_id',
        'kill -INT',
        'shut down cleanly',
    ):
        assert expected in source
    assert 'ros2 topic pub' not in source
    assert (REPOSITORY_ROOT / 'scripts' / 'smoke_world_model.sh').stat().st_mode & 0o111


def test_perception_smoke_proves_actual_imu_trust_path_and_lifecycle() -> None:
    path = REPOSITORY_ROOT / 'scripts' / 'smoke_perception.sh'
    source = path.read_text(encoding='utf-8')
    for expected in (
        'enable_world_model:=true',
        'ros2 lifecycle get /ayyo_world_model',
        'body_state_query.py',
        'ayyo.imu.body.v1',
        'imu_link',
        'ros_simulation_time',
        'base_pose_availability',
        'ros2 lifecycle set /ayyo_world_model deactivate',
        'ros2 lifecycle set /ayyo_world_model activate',
        'kill -INT',
    ):
        assert expected in source
    assert 'ros2 topic pub' not in source
    assert path.stat().st_mode & 0o111


def test_owned_sources_retain_project_copyright() -> None:
    for relative in (
        'scripts/body_state_query.py',
        'scripts/world_model_node.py',
        'test/test_ros_adapter.py',
    ):
        assert 'Copyright 2026 Ayyo Project Authors' in (
            PACKAGE_ROOT / relative
        ).read_text(encoding='utf-8')
