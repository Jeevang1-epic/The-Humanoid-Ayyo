# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from nav_msgs.msg import Odometry
from sensor_msgs.msg import CameraInfo, Image, Imu, JointState
from tf2_ros import (
    ConnectivityException,
    ExtrapolationException,
    InvalidArgumentException,
    LookupException,
    TimeoutException,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
INTERFACES_ROOT = REPOSITORY_ROOT / 'ros2_ws' / 'src' / 'ayyo_interfaces'
SIMULATION_ROOT = REPOSITORY_ROOT / 'ros2_ws' / 'src' / 'ayyo_simulation'


def script_source(name: str) -> str:
    return (PACKAGE_ROOT / 'scripts' / name).read_text(encoding='utf-8')


def adapter_module():
    scripts = str(PACKAGE_ROOT / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    path = PACKAGE_ROOT / 'scripts' / 'world_model_node.py'
    spec = importlib.util.spec_from_file_location('ayyo_world_model_node_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def support_module():
    path = PACKAGE_ROOT / 'scripts' / 'localization_diagnostics.py'
    spec = importlib.util.spec_from_file_location('ayyo_localization_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def visual_module():
    path = PACKAGE_ROOT / 'scripts' / 'visual_camera.py'
    spec = importlib.util.spec_from_file_location('ayyo_visual_camera_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def physical_camera_module():
    path = PACKAGE_ROOT / 'scripts' / 'physical_camera_adapter.py'
    spec = importlib.util.spec_from_file_location('ayyo_physical_camera_ros_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def depth_camera_module():
    path = PACKAGE_ROOT / 'scripts' / 'depth_camera_adapter.py'
    spec = importlib.util.spec_from_file_location('ayyo_depth_camera_ros_test', path)
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
        'string base_pose_source_id',
        'bool[] has_sensor_health',
        'string[] sensor_health_details',
        'uint32 perception_rejected_count',
        'uint32 current_visual_count',
        'bool has_visual_frame',
        'string visual_calibration_id',
        'string visual_observation_fingerprint',
        'uint32 current_depth_count',
        'bool has_depth_frame',
        'string depth_sensor_id',
        'string depth_frame_id',
        'string depth_encoding',
        'string depth_calibration_id',
        'string depth_calibration_record_id',
        'string depth_source_manifest_id',
        'string depth_session_id',
        'uint32 depth_valid_count',
        'uint32 depth_invalid_count',
        'float64 depth_minimum_m',
        'float64 depth_maximum_m',
        'string depth_payload_sha256',
        'string depth_observation_fingerprint',
        'uint32 current_fused_rgbd_count',
        'bool has_fused_rgbd',
        'string rgbd_pair_id',
        'string rgbd_pairing_policy_id',
        'string rgbd_synchronization_session_id',
        'bool rgbd_spatial_registration_validated',
        'string rgbd_rgb_source_fingerprint_sha256',
        'string rgbd_depth_source_fingerprint_sha256',
        'uint32 current_visual_interpretation_count',
        'bool has_visual_interpretation',
        'string visual_interpretation_source_visual_observation_id',
        'string visual_interpretation_producer_kind',
        'bool has_visual_evaluation',
        'string visual_interpretation_producer_version',
        'string visual_interpretation_producer_implementation_sha256',
        'string visual_interpretation_model_artifact_sha256',
        'string visual_interpretation_model_provenance_sha256',
        'string visual_interpretation_dataset_manifest_sha256',
        'string visual_interpretation_policy_sha256',
        'string visual_interpretation_report_semantic_sha256',
        'string visual_interpretation_mechanical_decision',
        'uint32 visual_detection_count',
        'bool[] visual_detection_has_confidence',
    ):
        assert field in interface
    assert interface.count('---') == 1
    assert 'string expression' not in interface
    assert 'string query' not in interface
    assert 'string visual_interpretation_report_json' not in interface
    assert 'uint8[] visual_interpretation_pixels' not in interface
    assert 'uint8[] depth_data' not in interface
    assert 'float32[] depth_pixels' not in interface
    assert 'uint8[] rgbd_data' not in interface


def test_query_exposes_only_compact_evaluation_and_model_provenance() -> None:
    source = script_source('body_state_query.py')
    for field in (
        'artifact_sha256',
        'dataset_manifest_sha256',
        'model_provenance_sha256',
        'policy_sha256',
        'producer_manifest_sha256',
        'report_semantic_sha256',
    ):
        assert field in source
    for forbidden in ('pixels', 'report_json', 'latency_ns', 'asset_reference'):
        assert forbidden not in source


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
    assert assignments['LOCALIZATION_TOPIC'] == '/ayyo/localization/odometry'
    assert assignments['DIAGNOSTICS_TOPIC'] == '/diagnostics'
    assert assignments['QUERY_SERVICE'] == '/ayyo/world_model/get_robot_body_state'
    assert 'create_subscription(' in source
    assert 'JOINT_STATE_TOPIC' in source
    assert 'IMU_TOPIC' in source
    assert 'LOCALIZATION_TOPIC' in source
    assert 'DIAGNOSTICS_TOPIC' in source
    visual = script_source('visual_camera.py')
    assert "IMAGE_TOPIC = '/ayyo/camera/head/image_raw'" in visual
    assert "CAMERA_INFO_TOPIC = '/ayyo/camera/head/camera_info'" in visual
    assert 'Image' in source
    assert 'CameraInfo' in source
    assert 'qos_profile_sensor_data' in source
    assert 'get_topic_names_and_types' not in source
    assert "declare_parameter('topic'" not in source
    assert 'eval(' not in source
    assert 'exec(' not in source
    assert 'subprocess' not in source


def localization_message(*, frame='odom', child='base_link', nanosec=5) -> Odometry:
    message = Odometry()
    message.header.stamp.sec = 2
    message.header.stamp.nanosec = nanosec
    message.header.frame_id = frame
    message.child_frame_id = child
    message.pose.pose.position.x = 1.0
    message.pose.pose.position.y = 2.0
    message.pose.pose.position.z = 3.0
    message.pose.pose.orientation.w = 1.0
    return message


def test_localization_normalization_preserves_exact_frames_and_unknown_covariance() -> None:
    adapter = adapter_module()
    support = support_module()
    message = localization_message()
    transform = support.odometry_transform(message)
    observation = support.normalize_localization(
        message,
        transform,
        adapter.POSE_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE],
        adapter.BODY_POSE_SENSOR,
    )
    assert observation.pose.frame_id == 'odom'
    assert observation.pose.child_frame_id == 'base_link'
    assert observation.pose.position_xyz == (1.0, 2.0, 3.0)
    assert observation.covariance is None
    assert observation.quality is None


def test_localization_wrong_frames_zero_time_and_malformed_pose_fail_closed() -> None:
    adapter = adapter_module()
    support = support_module()
    for message in (
        localization_message(frame='map'),
        localization_message(child='pelvis_link'),
    ):
        try:
            support.odometry_transform(message)
        except support.LocalizationAdapterError as error:
            assert error.failure.value == 'invalid_frame_request'
        else:
            raise AssertionError('wrong localization frame was accepted')

    zero = localization_message(nanosec=0)
    zero.header.stamp.sec = 0
    try:
        support.odometry_transform(zero)
    except support.LocalizationAdapterError as error:
        assert 'latest' in error.detail
    else:
        raise AssertionError('TF2 latest-time sentinel was accepted as exact time')

    malformed = localization_message()
    malformed.pose.pose.position.x = float('nan')
    transform = support.odometry_transform(malformed)
    try:
        support.normalize_localization(
            malformed,
            transform,
            adapter.POSE_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE],
            adapter.BODY_POSE_SENSOR,
        )
    except support.LocalizationAdapterError as error:
        assert error.failure.value == 'malformed_numeric_pose'
    else:
        raise AssertionError('non-finite localization was accepted')


def test_localization_invalid_quaternion_and_covariance_are_distinct() -> None:
    adapter = adapter_module()
    support = support_module()
    message = localization_message()
    message.pose.pose.orientation.w = 0.0
    transform = support.odometry_transform(message)
    try:
        support.normalize_localization(
            message,
            transform,
            adapter.POSE_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE],
            adapter.BODY_POSE_SENSOR,
        )
    except support.LocalizationAdapterError as error:
        assert error.failure.value == 'invalid_quaternion'
    else:
        raise AssertionError('invalid localization quaternion was accepted')

    message = localization_message()
    message.pose.covariance[0] = -1.0
    transform = support.odometry_transform(message)
    try:
        support.normalize_localization(
            message,
            transform,
            adapter.POSE_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE],
            adapter.BODY_POSE_SENSOR,
        )
    except support.LocalizationAdapterError as error:
        assert error.failure.value == 'invalid_covariance'
    else:
        raise AssertionError('invalid localization covariance was accepted')


def test_exact_lookup_never_requests_latest_or_changes_frames() -> None:
    support = support_module()
    expected = support.odometry_transform(localization_message())

    class Buffer:
        def lookup_transform(self, target, source, stamp, *, timeout):
            assert target == 'odom'
            assert source == 'base_link'
            assert stamp.nanoseconds == 2_000_000_005
            assert stamp.nanoseconds != 0
            assert timeout.nanoseconds == 20_000_000
            return expected

    result = support.exact_lookup(
        Buffer(),
        observed_at_ns=2_000_000_005,
        timeout_ns=20_000_000,
    )
    assert result is expected


def test_exact_lookup_rejects_malformed_result_timestamp_as_typed_failure() -> None:
    support = support_module()
    malformed = support.odometry_transform(localization_message())
    malformed.header.stamp.nanosec = 1_000_000_000

    class Buffer:
        def lookup_transform(self, target, source, stamp, *, timeout):
            return malformed

    try:
        support.exact_lookup(
            Buffer(),
            observed_at_ns=2_000_000_005,
            timeout_ns=20_000_000,
        )
    except support.LocalizationAdapterError as error:
        assert error.failure.value == 'invalid_frame_request'
        assert 'timestamp' in error.detail
    else:
        raise AssertionError('malformed TF2 result timestamp was accepted')


def test_tf2_failures_are_typed_without_pose_fallback() -> None:
    support = support_module()
    expected = {
        LookupException: 'frame_lookup_unavailable',
        ConnectivityException: 'frame_lookup_connectivity',
        ExtrapolationException: 'frame_lookup_extrapolation',
        TimeoutException: 'frame_lookup_timeout',
        InvalidArgumentException: 'invalid_frame_request',
    }
    for exception, failure in expected.items():
        class Buffer:
            def lookup_transform(self, target, source, stamp, *, timeout):
                raise exception('failure')

        try:
            support.exact_lookup(
                Buffer(),
                observed_at_ns=1,
                timeout_ns=0,
            )
        except support.LocalizationAdapterError as error:
            assert error.failure.value == failure
        else:
            raise AssertionError(f'{exception.__name__} fabricated a pose')


def diagnostic_message(*, level=DiagnosticStatus.OK, name=None, hardware_id=None):
    adapter = adapter_module()
    message = DiagnosticArray()
    message.header.stamp.sec = 2
    status = DiagnosticStatus()
    status.level = level
    status.name = name or 'ayyo/proprioception/body_imu_source'
    status.hardware_id = hardware_id or adapter.IMU_SENSOR.sensor_id
    status.message = 'reviewed fixture'
    status.values = [KeyValue(key='temperature', value='nominal')]
    message.status = [status]
    return message


def test_standard_diagnostic_levels_map_conservatively() -> None:
    adapter = adapter_module()
    support = support_module()
    expected = {
        DiagnosticStatus.OK: 'available',
        DiagnosticStatus.WARN: 'degraded',
        DiagnosticStatus.ERROR: 'error',
        DiagnosticStatus.STALE: 'stale',
    }
    for level, availability in expected.items():
        result = support.normalize_diagnostics(
            diagnostic_message(level=level),
            adapter.DIAGNOSTIC_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE],
            adapter.DIAGNOSTIC_COMPONENTS,
        )
        assert result.observations[0].availability.value == availability
        assert 'temperature' in result.observations[0].evidence_detail


def test_unknown_diagnostic_is_ignored_but_identity_substitution_is_rejected() -> None:
    adapter = adapter_module()
    support = support_module()
    unknown = diagnostic_message(name='other/component', hardware_id='other.hardware')
    result = support.normalize_diagnostics(
        unknown,
        adapter.DIAGNOSTIC_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE],
        adapter.DIAGNOSTIC_COMPONENTS,
    )
    assert result.observations == ()
    assert result.ignored_components == ('other/component',)

    wrong_identity = diagnostic_message(hardware_id='other.hardware')
    try:
        support.normalize_diagnostics(
            wrong_identity,
            adapter.DIAGNOSTIC_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE],
            adapter.DIAGNOSTIC_COMPONENTS,
        )
    except support.DiagnosticAdapterError as error:
        assert 'hardware identity' in str(error)
    else:
        raise AssertionError('wrong diagnostic hardware identity was accepted')


def test_unknown_diagnostic_payloads_remain_bounded_before_ignore() -> None:
    adapter = adapter_module()
    support = support_module()
    provenance = adapter.DIAGNOSTIC_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE]
    unknown = diagnostic_message(name='other/component', hardware_id='other.hardware')
    unknown.status[0].values = [KeyValue(key=str(index), value='x') for index in range(17)]
    try:
        support.normalize_diagnostics(
            unknown,
            provenance,
            adapter.DIAGNOSTIC_COMPONENTS,
        )
    except support.DiagnosticAdapterError as error:
        assert 'exceeds its bound' in str(error)
    else:
        raise AssertionError('oversized unknown diagnostic bypassed input bounds')


def test_conflicting_malformed_and_oversized_diagnostics_are_rejected() -> None:
    adapter = adapter_module()
    support = support_module()
    provenance = adapter.DIAGNOSTIC_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE]
    malformed = diagnostic_message(level=255)
    conflicting = diagnostic_message(level=DiagnosticStatus.OK)
    second = diagnostic_message(level=DiagnosticStatus.ERROR).status[0]
    conflicting.status.append(second)
    oversized = diagnostic_message()
    oversized.status[0].message = 'x' * 257
    for message in (malformed, conflicting, oversized):
        try:
            support.normalize_diagnostics(
                message,
                provenance,
                adapter.DIAGNOSTIC_COMPONENTS,
            )
        except support.DiagnosticAdapterError:
            pass
        else:
            raise AssertionError('invalid diagnostic array was accepted')


def test_diagnostic_text_remains_inert_evidence_and_absence_stays_absent() -> None:
    adapter = adapter_module()
    support = support_module()
    provenance = adapter.DIAGNOSTIC_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE]
    empty = DiagnosticArray()
    empty.header.stamp.sec = 2
    assert support.normalize_diagnostics(
        empty,
        provenance,
        adapter.DIAGNOSTIC_COMPONENTS,
    ).observations == ()
    message = diagnostic_message()
    message.status[0].message = '$(touch /tmp/never) ${approved} /commands'
    observation = support.normalize_diagnostics(
        message,
        provenance,
        adapter.DIAGNOSTIC_COMPONENTS,
    ).observations[0]
    assert '/commands' in observation.evidence_detail
    assert observation.availability.value == 'available'


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


def camera_messages(*, stamp=2_000_000_003, frame='head_camera_optical_frame'):
    image = Image()
    image.header.stamp.sec = stamp // 1_000_000_000
    image.header.stamp.nanosec = stamp % 1_000_000_000
    image.header.frame_id = frame
    image.width = 2
    image.height = 1
    image.encoding = 'rgb8'
    image.is_bigendian = 0
    image.step = 6
    image.data = [1, 2, 3, 4, 5, 6]
    info = CameraInfo()
    info.header.stamp.sec = image.header.stamp.sec
    info.header.stamp.nanosec = image.header.stamp.nanosec
    info.header.frame_id = frame
    info.width = image.width
    info.height = image.height
    info.distortion_model = 'plumb_bob'
    info.d = []
    info.k = [2.0, 0.0, 1.0, 0.0, 2.0, 0.5, 0.0, 0.0, 1.0]
    info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    info.p = [2.0, 0.0, 1.0, 0.0, 0.0, 2.0, 0.5, 0.0, 0.0, 0.0, 1.0, 0.0]
    return image, info


def test_visual_pair_normalizes_only_compact_exact_time_metadata() -> None:
    adapter = adapter_module()
    support = visual_module()
    image, info = camera_messages()
    observation = support.normalize_visual_pair(
        image,
        info,
        adapter.CAMERA_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE],
    )
    assert observation.sensor == support.HEAD_CAMERA_SENSOR
    assert observation.observed_at_ns == 2_000_000_003
    assert (observation.width, observation.height, observation.encoding) == (
        2,
        1,
        'rgb8',
    )
    assert observation.data_size_bytes == 6
    assert observation.calibration_id.startswith('camera-calibration-sha256-')
    assert not hasattr(observation, 'data')


def test_visual_pair_rejects_frames_time_dimensions_encoding_and_buffer_shape() -> None:
    adapter = adapter_module()
    support = visual_module()
    provenance = adapter.CAMERA_SOURCE_PROFILES[adapter.SIMULATION_SOURCE_PROFILE]
    cases = []
    image, info = camera_messages(frame='')
    cases.append((image, info))
    image, info = camera_messages(frame='head_camera_frame')
    cases.append((image, info))
    image, info = camera_messages(stamp=0)
    cases.append((image, info))
    image, info = camera_messages()
    info.header.stamp.nanosec += 1
    cases.append((image, info))
    image, info = camera_messages()
    info.width = 3
    cases.append((image, info))
    image, info = camera_messages()
    image.encoding = 'bgr8'
    cases.append((image, info))
    image, info = camera_messages()
    image.step = 5
    cases.append((image, info))
    image, info = camera_messages()
    image.data = []
    cases.append((image, info))
    for image, info in cases:
        try:
            support.normalize_visual_pair(image, info, provenance)
        except (support.VisualCameraAdapterError, adapter.WorldModelValidationError):
            pass
        else:
            raise AssertionError('malformed visual pair was accepted')


def test_camera_info_rejects_nonfinite_malformed_and_all_zero_calibration() -> None:
    support = visual_module()
    invalid = []
    _, info = camera_messages()
    info.k[0] = float('nan')
    invalid.append(info)
    _, info = camera_messages()
    info.k = [0.0] * 9
    invalid.append(info)
    _, info = camera_messages()
    info.d = [0.0] * 17
    invalid.append(info)
    _, info = camera_messages()
    info.roi.x_offset = 2
    info.roi.width = 1
    info.roi.height = 1
    invalid.append(info)
    for info in invalid:
        try:
            support.normalize_camera_info(info)
        except Exception as error:
            assert type(error).__name__ in {
                'VisualCameraAdapterError',
                'WorldModelValidationError',
            }
        else:
            raise AssertionError('malformed CameraInfo was accepted')


def test_physical_camera_ros_metadata_requires_exact_configured_calibration() -> None:
    from ayyo_physical_camera import physical_camera_fixture_bundle

    support = physical_camera_module()
    bundle = physical_camera_fixture_bundle()
    calibration = bundle.calibration.calibration
    image = Image()
    image.header.stamp.sec = 2
    image.header.stamp.nanosec = 3
    image.header.frame_id = bundle.source.camera.frame_id
    image.width = calibration.width
    image.height = calibration.height
    image.encoding = 'rgb8'
    image.step = calibration.width * 3
    image.data = bytes(image.step * image.height)
    info = CameraInfo()
    info.header = image.header
    info.width = calibration.width
    info.height = calibration.height
    info.distortion_model = calibration.distortion_model
    info.d = list(calibration.d)
    info.k = list(calibration.k)
    info.r = list(calibration.r)
    info.p = list(calibration.p)
    session = 'physical-camera-session-sha256-' + '1' * 64
    image_metadata = support.normalize_physical_image_metadata(
        image,
        bundle.source,
        session,
    )
    info_metadata = support.normalize_physical_camera_info_metadata(
        info,
        bundle.source,
        session,
        bundle.calibration,
    )
    assert image_metadata.observed_at_ns == 2_000_000_003
    assert image_metadata.data_size_bytes == calibration.width * calibration.height * 3
    assert info_metadata.calibration == bundle.calibration
    info.k[0] += 1.0
    try:
        support.normalize_physical_camera_info_metadata(
            info,
            bundle.source,
            session,
            bundle.calibration,
        )
    except support.PhysicalCameraRosAdapterError:
        pass
    else:
        raise AssertionError('changed physical CameraInfo was accepted')


def depth_messages(*, stamp=2_000_000_003, frame=None, encoding='16UC1'):
    from ayyo_depth_camera import depth_test_fixture_bundle, fixture_depth_bytes

    bundle = depth_test_fixture_bundle()
    calibration = bundle.calibration.calibration
    frame_id = bundle.source.sensor.frame_id if frame is None else frame
    image = Image()
    image.header.stamp.sec = stamp // 1_000_000_000
    image.header.stamp.nanosec = stamp % 1_000_000_000
    image.header.frame_id = frame_id
    image.width = calibration.width
    image.height = calibration.height
    image.encoding = encoding
    image.is_bigendian = 0
    image.step = calibration.width * (2 if encoding == '16UC1' else 4)
    image.data = fixture_depth_bytes(
        calibration.width,
        calibration.height,
        encoding=encoding,
    )
    info = CameraInfo()
    info.header = image.header
    info.width = calibration.width
    info.height = calibration.height
    info.distortion_model = calibration.distortion_model
    info.d = list(calibration.d)
    info.k = list(calibration.k)
    info.r = list(calibration.r)
    info.p = list(calibration.p)
    info.binning_x = calibration.binning_x
    info.binning_y = calibration.binning_y
    (
        info.roi.x_offset,
        info.roi.y_offset,
        info.roi.width,
        info.roi.height,
        info.roi.do_rectify,
    ) = calibration.roi
    return bundle, image, info


def test_depth_ros_normalization_is_exact_compact_and_calibration_bound() -> None:
    support = depth_camera_module()
    bundle, image, info = depth_messages()
    session = 'depth-camera-session-sha256-' + '1' * 64
    image_metadata = support.normalize_depth_image(image, bundle.source, session)
    info_metadata = support.normalize_depth_camera_info(
        info,
        bundle.source,
        session,
        bundle.calibration,
    )
    assert image_metadata.observed_at_ns == 2_000_000_003
    assert image_metadata.valid_depth_count == 8
    assert image_metadata.invalid_depth_count == 0
    assert image_metadata.minimum_depth_m == 1.0
    assert image_metadata.maximum_depth_m == 1.7
    assert info_metadata.calibration == bundle.calibration
    assert not hasattr(image_metadata, 'data')


def test_depth_ros_normalization_rejects_wrong_frame_and_malformed_payload() -> None:
    support = depth_camera_module()
    session = 'depth-camera-session-sha256-' + '2' * 64
    cases = []
    bundle, image, _ = depth_messages(frame='head_camera_optical_frame')
    cases.append((bundle, image))
    bundle, image, _ = depth_messages()
    image.encoding = 'mono16'
    cases.append((bundle, image))
    bundle, image, _ = depth_messages()
    image.step -= 1
    cases.append((bundle, image))
    bundle, image, _ = depth_messages()
    image.data = image.data[:-1]
    cases.append((bundle, image))
    bundle, image, _ = depth_messages()
    image.data = []
    cases.append((bundle, image))
    for bundle, image in cases:
        try:
            support.normalize_depth_image(image, bundle.source, session)
        except support.DepthCameraRosAdapterError:
            pass
        else:
            raise AssertionError('malformed depth Image was accepted')


def test_depth_ros_camera_info_rejects_frame_or_calibration_conflict() -> None:
    support = depth_camera_module()
    session = 'depth-camera-session-sha256-' + '3' * 64
    bundle, _, info = depth_messages(frame='head_camera_optical_frame')
    try:
        support.normalize_depth_camera_info(
            info,
            bundle.source,
            session,
            bundle.calibration,
        )
    except support.DepthCameraRosAdapterError:
        pass
    else:
        raise AssertionError('wrong depth CameraInfo frame was accepted')
    bundle, _, info = depth_messages()
    info.k[0] += 1.0
    try:
        support.normalize_depth_camera_info(
            info,
            bundle.source,
            session,
            bundle.calibration,
        )
    except support.DepthCameraRosAdapterError:
        pass
    else:
        raise AssertionError('changed depth CameraInfo was accepted')


def test_visual_pairing_retains_at_most_one_raw_message_without_worker() -> None:
    source = script_source('world_model_node.py')
    for expected in (
        'self._pending_image: Image | None = None',
        'self._pending_camera_info: CameraInfo | None = None',
        'def _try_visual_pair',
        'self._pending_image = None',
        'self._pending_camera_info = None',
    ):
        assert expected in source
    assert 'message_filters' not in source
    assert 'create_timer' not in source


def test_evaluated_visual_fixture_is_sealed_bounded_and_lifecycle_scoped() -> None:
    source = script_source('world_model_node.py')
    for expected in (
        "declare_parameter(\n            'enable_visual_producer_evaluation_fixture'",
        'fixture_bundle_for_live_profile(',
        'VisualProducerEvaluator(',
        'DeterministicFixtureInvoker()',
        'authorize_evaluated_visual(sealed)',
        'self._visual_evaluated_this_activation = True',
        "'visual reference and evaluated fixture modes are mutually exclusive'",
    ):
        assert expected in source
    assert source.count('self._visual_evaluated_this_activation = False') >= 5
    assert 'OwnedProcessVisualProducerInvoker' not in source


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
        "source_id='ros.camera.head.simulation.gz-harmonic.v1'",
        "source_id='ros.camera.head.physical.standard-driver.v1'",
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
    assert '../../../physical_camera/src/ayyo_physical_camera' in cmake
    assert '../../../depth_camera/src/ayyo_depth_camera' in cmake
    assert '../../../visual_evaluation/src/ayyo_visual_evaluation' in cmake
    assert '../../../working_memory/src/ayyo_working_memory' in cmake
    assert '../../../perception/src/ayyo_perception' in cmake
    assert 'scripts/world_model_node.py' in cmake
    assert 'scripts/body_state_query.py' in cmake
    assert 'scripts/localization_diagnostics.py' in cmake
    assert 'scripts/physical_camera_adapter.py' in cmake
    assert 'scripts/physical_camera_fixture_node.py' in cmake
    assert 'scripts/depth_camera_adapter.py' in cmake
    assert 'scripts/depth_camera_fixture_node.py' in cmake
    assert 'scripts/visual_camera.py' in cmake
    assert not (PACKAGE_ROOT / 'ayyo_world_model').exists()
    assert not (PACKAGE_ROOT / 'ayyo_working_memory').exists()
    assert not (PACKAGE_ROOT / 'ayyo_perception').exists()


def test_physical_camera_fixture_composition_is_explicit_and_default_off() -> None:
    source = (
        SIMULATION_ROOT / 'launch' / 'physical_camera_fixture.launch.py'
    ).read_text(encoding='utf-8')
    for expected in (
        "'enable_physical_camera_fixture',",
        "default_value='false'",
        "'physical_camera_profile',",
        "default_value='unconfigured'",
        "'source_profile': 'physical_camera_test_fixture_v1'",
        "'enable_physical_camera_adapter': enable_fixture",
        "executable='physical_camera_fixture_node.py'",
        'condition=IfCondition(enable_fixture)',
    ):
        assert expected in source
    for forbidden in ('gz sim', 'ros_gz', 'controller_manager', '/commands'):
        assert forbidden not in source


def test_depth_fixture_composition_is_explicit_default_off_and_authority_free() -> None:
    source = (
        SIMULATION_ROOT / 'launch' / 'head_depth_fixture.launch.py'
    ).read_text(encoding='utf-8')
    for expected in (
        "'enable_head_depth_fixture',",
        "default_value='false'",
        "'depth_camera_profile',",
        "default_value='unconfigured'",
        "'source_profile': 'depth_camera_test_fixture_v1'",
        "'enable_depth_camera_adapter': enable_fixture",
        "executable='depth_camera_fixture_node.py'",
        'condition=IfCondition(enable_fixture)',
    ):
        assert expected in source
    for forbidden in ('gz sim', 'ros_gz', 'controller_manager', '/commands'):
        assert forbidden not in source


def test_physical_camera_adapter_is_sealed_lifecycle_scoped_and_query_compact() -> None:
    source = script_source('world_model_node.py')
    for expected in (
        "declare_parameter('enable_physical_camera_adapter', False)",
        "declare_parameter('physical_camera_profile', 'unconfigured')",
        'PhysicalCameraLifecycleAdapter(',
        'authorize_physical_camera(',
        'normalize_physical_image_metadata(',
        'normalize_physical_camera_info_metadata(',
        'self._physical_camera_adapter.deactivate()',
        'self._memory.reset()',
        'self._trust_boundary.reset()',
        'self._physical_camera_adapter.cleanup()',
        'self._physical_camera_adapter.shutdown()',
    ):
        assert expected in source
    interface = (INTERFACES_ROOT / 'srv' / 'GetRobotBodyState.srv').read_text(
        encoding='utf-8'
    )
    assert 'string visual_calibration_id' in interface
    assert 'string[] sensor_health_details' in interface
    assert 'float64[] camera_calibration_matrix' not in interface
    assert 'uint8[] visual_pixels' not in interface


def test_depth_adapter_is_sealed_lifecycle_scoped_and_query_compact() -> None:
    source = script_source('world_model_node.py')
    for expected in (
        "declare_parameter('enable_depth_camera_adapter', False)",
        "declare_parameter('depth_camera_profile', 'unconfigured')",
        'DepthLifecycleAdapter(',
        'authorize_depth_camera(',
        'normalize_depth_image(',
        'normalize_depth_camera_info(',
        'self._depth_camera_adapter.deactivate()',
        'self._memory.reset()',
        'self._trust_boundary.reset()',
        'self._depth_camera_adapter.cleanup()',
        'self._depth_camera_adapter.shutdown()',
    ):
        assert expected in source
    query = script_source('body_state_query.py')
    for expected in (
        "'depth_frame': (",
        "'payload_sha256': response.depth_payload_sha256",
        "'source_manifest_id': response.depth_source_manifest_id",
        "'session_id': response.depth_session_id",
        "'valid_count': response.depth_valid_count",
    ):
        assert expected in query
    for forbidden in ('depth_pixels', "'data':", 'point_cloud'):
        assert forbidden not in query


def test_rgbd_fusion_is_exact_lifecycle_scoped_and_query_compact() -> None:
    source = script_source('world_model_node.py')
    for expected in (
        "declare_parameter('enable_rgbd_fusion_adapter', False)",
        "declare_parameter('rgbd_fusion_profile', 'unconfigured')",
        "rgbd_fusion_profile != 'exact_test_fixture_v1'",
        'RgbdFusionLifecycleAdapter(',
        'authorize_rgbd_fusion(',
        'submit_rgb(',
        'submit_depth(',
        'self._rgbd_fusion_adapter.deactivate()',
        'self._rgbd_fusion_adapter.cleanup()',
        'self._rgbd_fusion_adapter.shutdown()',
    ):
        assert expected in source
    physical_handler = source.split(
        'def _handle_physical_camera_result', 1
    )[1].split('def _on_depth_image', 1)[0]
    depth_handler = source.split(
        'def _handle_depth_camera_result', 1
    )[1].split('def _handle_rgbd_fusion_result', 1)[0]
    assert 'submit_depth(' not in physical_handler
    assert 'submit_depth(' in depth_handler
    query = script_source('body_state_query.py')
    for expected in (
        "'fused_rgbd': (",
        "'pair_id': response.rgbd_pair_id",
        "'spatial_registration_validated': (",
        "'synchronization_session_id': (",
        "'source_fingerprint_sha256': (",
    ):
        assert expected in query
    for forbidden in ('rgbd_pixels', "'data':", 'point_cloud', 'pointcloud'):
        assert forbidden not in query.lower()


def test_rgbd_fixture_is_explicit_default_off_and_authority_free() -> None:
    launch = (
        SIMULATION_ROOT / 'launch' / 'head_rgbd_fusion_fixture.launch.py'
    ).read_text(encoding='utf-8')
    fixture = script_source('rgbd_fusion_fixture_node.py')
    for expected in (
        "'enable_head_rgbd_fusion_fixture',",
        "default_value='false'",
        "'rgbd_fusion_profile',",
        "default_value='unconfigured'",
        "'enable_depth_camera_adapter': enable_fixture",
        "'enable_rgbd_fusion_adapter': enable_fixture",
        "executable='rgbd_fusion_fixture_node.py'",
        'condition=IfCondition(enable_fixture)',
    ):
        assert expected in launch
    for topic in (
        'IMAGE_TOPIC',
        'CAMERA_INFO_TOPIC',
        'DEPTH_IMAGE_TOPIC',
        'DEPTH_CAMERA_INFO_TOPIC',
    ):
        assert topic in fixture
    for forbidden in ('gz sim', 'ros_gz', 'controller_manager', '/commands'):
        assert forbidden not in launch
        assert forbidden not in fixture
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'ayyo_rgbd_fusion' in cmake
    assert 'scripts/rgbd_fusion_fixture_node.py' in cmake
    assert (
        PACKAGE_ROOT / 'scripts' / 'rgbd_fusion_fixture_node.py'
    ).stat().st_mode & 0o111


def test_rgbd_smoke_proves_exact_pairing_lifecycle_and_teardown() -> None:
    path = REPOSITORY_ROOT / 'scripts' / 'smoke_head_rgbd_fusion.sh'
    source = path.read_text(encoding='utf-8')
    for expected in (
        'head_rgbd_fusion_fixture.launch.py',
        'enable_head_rgbd_fusion_fixture:=false',
        'enable_head_rgbd_fusion_fixture:=true',
        'rgbd_fusion_profile:=exact_test_fixture_v1',
        'rgbd-pair-sha256-',
        'ayyo.rgbd.exact-source-time.v1',
        'spatial_registration_validated',
        'current_fused_rgbd_count',
        'ros2 lifecycle set /ayyo_world_model deactivate',
        'ros2 lifecycle set /ayyo_world_model activate',
        'ayyo_smoke_shutdown_owned_launch',
        'owned-process set and isolated ROS graph are empty',
    ):
        assert expected in source
    for forbidden in ('pkill', 'killall', 'ros2 topic pub'):
        assert forbidden not in source
    assert path.stat().st_mode & 0o111


def test_ros_dependency_boundary_has_no_cognition_or_durable_memory() -> None:
    manifest = ET.parse(PACKAGE_ROOT / 'package.xml').getroot()
    dependencies = {
        element.text
        for element in manifest
        if element.tag.endswith('depend') and element.text
    }
    assert {
        'ayyo_interfaces',
        'builtin_interfaces',
        'diagnostic_msgs',
        'geometry_msgs',
        'nav_msgs',
        'rclpy',
        'sensor_msgs',
        'tf2_ros',
    } <= dependencies
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
    assert "'source_profile': 'simulation_ros2_control_v1'" in source
    assert (
        "'enable_visual_reference_interpreter',\n                default_value='false'"
        in source
    )
    assert (
        "'enable_visual_producer_evaluation_fixture',\n"
        "                default_value='false'"
        in source
    )
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
        'smoke_processes.sh',
        'ayyo_smoke_shutdown_owned_launch',
        'owned-process set is empty',
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
        'ayyo_smoke_shutdown_owned_launch',
    ):
        assert expected in source
    assert 'ros2 topic pub' not in source
    assert path.stat().st_mode & 0o111


def test_localization_diagnostics_smoke_uses_only_bounded_test_fixture() -> None:
    smoke_path = REPOSITORY_ROOT / 'scripts' / 'smoke_localization_diagnostics.sh'
    fixture_path = REPOSITORY_ROOT / 'scripts' / 'perception_test_fixture.py'
    smoke = smoke_path.read_text(encoding='utf-8')
    fixture = fixture_path.read_text(encoding='utf-8')
    for expected in (
        'enable_localization:=true',
        'body_state_query.py',
        'perception_test_fixture.py',
        '--scenario unknown_diagnostic',
        '--scenario wrong_localization_frame',
        "'joint ok' 'imu warn' 'imu error' 'imu stale'",
        '--verify-query',
        'development_command.py --position 0.1',
        'remaining_nodes',
        '200 + ($$ % 20)',
        'ayyo_smoke_shutdown_owned_launch',
    ):
        assert expected in smoke
    for expected in (
        'TEST-ONLY',
        "DIAGNOSTICS_TOPIC = '/diagnostics'",
        "LOCALIZATION_TOPIC = '/ayyo/localization/odometry'",
        "QUERY_SERVICE = '/ayyo/world_model/get_robot_body_state'",
        "choices=('imu', 'joint')",
        'time.monotonic() + 12.0',
    ):
        assert expected in fixture
    for forbidden in ('eval(', 'exec(', 'subprocess', 'ros2 topic pub'):
        assert forbidden not in fixture
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'perception_test_fixture.py' not in cmake
    assert smoke_path.stat().st_mode & 0o111
    assert fixture_path.stat().st_mode & 0o111


def test_visual_smoke_proves_real_fixed_trust_path_and_bounded_fixture() -> None:
    smoke_path = REPOSITORY_ROOT / 'scripts' / 'smoke_visual_camera.sh'
    fixture_path = REPOSITORY_ROOT / 'scripts' / 'visual_test_fixture.py'
    smoke = smoke_path.read_text(encoding='utf-8')
    fixture = fixture_path.read_text(encoding='utf-8')
    for expected in (
        'enable_camera:=true',
        '--scenario verify_stream',
        '--scenario adversarial_contracts',
        '--scenario wrong_frame',
        'head_camera_optical_frame',
        'data_size_bytes',
        'camera-calibration-sha256-',
        'ros.camera.head.simulation.gz-harmonic.v1',
        'development_command.py --position 0.1',
        'ros2 lifecycle set /ayyo_world_model deactivate',
        'current_visual_count',
        'remaining_nodes',
        'ayyo_smoke_shutdown_owned_launch',
    ):
        assert expected in smoke
    for expected in (
        'TEST-ONLY',
        "IMAGE_TOPIC = '/ayyo/camera/head/image_raw'",
        "CAMERA_INFO_TOPIC = '/ayyo/camera/head/camera_info'",
        "choices=('adversarial_contracts', 'verify_stream', 'wrong_frame')",
        'time.monotonic() + 12.0',
    ):
        assert expected in fixture
    for forbidden in ('eval(', 'exec(', 'subprocess', 'ros2 topic pub'):
        assert forbidden not in fixture
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'visual_test_fixture.py' not in cmake
    assert smoke_path.stat().st_mode & 0o111
    assert fixture_path.stat().st_mode & 0o111


def test_interpreted_visual_smoke_is_synthetic_bounded_and_process_owned() -> None:
    smoke_path = REPOSITORY_ROOT / 'scripts' / 'smoke_visual_perception.sh'
    fixture_path = (
        REPOSITORY_ROOT / 'scripts' / 'visual_interpretation_test_fixture.py'
    )
    smoke = smoke_path.read_text(encoding='utf-8')
    fixture = fixture_path.read_text(encoding='utf-8')
    for expected in (
        'enable_visual_reference_interpreter:=true',
        'visual_interpretation',
        'synthetic.test-pattern.v1',
        'confidence"] is None',
        'tracked_visual_source_count',
        'ros2 lifecycle set /ayyo_world_model deactivate',
        'ayyo_smoke_shutdown_owned_launch',
        'remaining_nodes',
    ):
        assert expected in smoke
    for expected in (
        'TEST-ONLY',
        'DeterministicVisualReferenceAdapter',
        'range(3, 1003)',
        'recent_evidence_capacity=16',
        "'pixels' not in state_text",
    ):
        assert expected in fixture
    for forbidden in ('rclpy', 'sensor_msgs', 'subprocess', 'ayyo_memory'):
        assert forbidden not in fixture
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'visual_interpretation_test_fixture.py' not in cmake
    assert smoke_path.stat().st_mode & 0o111
    assert fixture_path.stat().st_mode & 0o111


def test_evaluated_visual_smoke_is_adversarial_bounded_and_process_owned() -> None:
    smoke_path = (
        REPOSITORY_ROOT / 'scripts' / 'smoke_visual_producer_evaluation.sh'
    )
    fixture_path = (
        REPOSITORY_ROOT
        / 'scripts'
        / 'visual_producer_evaluation_test_fixture.py'
    )
    smoke = smoke_path.read_text(encoding='utf-8')
    fixture = fixture_path.read_text(encoding='utf-8')
    for expected in (
        'enable_visual_producer_evaluation_fixture:=true',
        'world_model_retention_ttl_ms:=10000',
        'enable_visual_reference_interpreter:=false',
        'VISUAL_EVALUATION_FIXTURE_RESULT=',
        'cycle_count',
        'report_semantic_sha256',
        'ros2 lifecycle set /ayyo_world_model deactivate',
        'ayyo_smoke_start_owned_launch',
        'ayyo_smoke_shutdown_owned_launch',
        'leftover owned process set=[]',
    ):
        assert expected in smoke
    for expected in (
        'TEST-ONLY',
        'CYCLE_COUNT = 5_000',
        'WrongModelFixtureProducer',
        'WrongSourceFixtureProducer',
        'MalformedBoxFixtureProducer',
        'SlowFixtureProducer',
        'tracemalloc.get_traced_memory()',
        'authorize_evaluated_visual(last_sealed)',
    ):
        assert expected in fixture
    for forbidden in ('rclpy', 'sensor_msgs', 'ayyo_memory', 'shell=True'):
        assert forbidden not in fixture
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'visual_producer_evaluation_test_fixture.py' not in cmake


def test_physical_camera_smoke_is_default_off_adversarial_and_process_owned() -> None:
    smoke_path = REPOSITORY_ROOT / 'scripts' / 'smoke_physical_camera_foundation.sh'
    fixture_path = (
        REPOSITORY_ROOT / 'scripts' / 'physical_camera_foundation_test_fixture.py'
    )
    smoke = smoke_path.read_text(encoding='utf-8')
    fixture = fixture_path.read_text(encoding='utf-8')
    for expected in (
        'physical_camera_fixture.launch.py',
        'enable_physical_camera_fixture:=false',
        'enable_physical_camera_fixture:=true',
        'physical_camera_profile:=test_fixture_v1',
        '--scenario wrong_frame',
        '--scenario malformed_calibration',
        'ros2 lifecycle set /ayyo_world_model deactivate',
        'ros2 lifecycle set /ayyo_world_model activate',
        'ayyo_smoke_shutdown_owned_launch',
        'owned-process set and isolated ROS graph are empty',
    ):
        assert expected in smoke
    for expected in (
        'CYCLE_COUNT = 5_000',
        'bare_perception_bypass_rejected',
        'malformed_calibration_rejected',
        'simulation_spoof_rejected',
        'tracemalloc.start()',
    ):
        assert expected in fixture
    assert smoke_path.stat().st_mode & 0o111
    assert fixture_path.stat().st_mode & 0o111
    assert 'pkill' not in smoke
    assert 'ros2 topic pub' not in smoke


def test_head_depth_smoke_is_nonempty_adversarial_bounded_and_process_owned() -> None:
    smoke_path = REPOSITORY_ROOT / 'scripts' / 'smoke_head_depth_rgbd.sh'
    fixture_path = REPOSITORY_ROOT / 'scripts' / 'head_depth_rgbd_test_fixture.py'
    smoke = smoke_path.read_text(encoding='utf-8')
    fixture = fixture_path.read_text(encoding='utf-8')
    for expected in (
        'head_depth_fixture.launch.py',
        'enable_head_depth_fixture:=false',
        'enable_head_depth_fixture:=true',
        'depth_camera_profile:=test_fixture_v1',
        'sensor_msgs/msg/Image',
        'sensor_msgs/msg/CameraInfo',
        '--scenario wrong_frame',
        '--scenario malformed_payload',
        'valid_count',
        'payload_sha256',
        'ros2 lifecycle set /ayyo_world_model deactivate',
        'ros2 lifecycle set /ayyo_world_model activate',
        'ayyo_smoke_shutdown_owned_launch',
        'owned-process set and isolated ROS graph are empty',
    ):
        assert expected in smoke
    for expected in (
        'CYCLE_COUNT = 5_000',
        'bare_perception_bypass_rejected',
        'recorded_live_substitution_rejected',
        'simulation_spoof_rejected',
        'spoofed_physical_rejected',
        'tracemalloc.start()',
        "choices=('offline', 'wrong_frame', 'malformed_payload')",
    ):
        assert expected in fixture
    for forbidden in ('pkill', 'ros2 topic pub', 'PointCloud2'):
        assert forbidden not in smoke
    assert smoke_path.stat().st_mode & 0o111
    assert fixture_path.stat().st_mode & 0o111
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'head_depth_rgbd_test_fixture.py' not in cmake


def test_owned_sources_retain_project_copyright() -> None:
    for relative in (
        'scripts/body_state_query.py',
        'scripts/depth_camera_adapter.py',
        'scripts/depth_camera_fixture_node.py',
        'scripts/localization_diagnostics.py',
        'scripts/physical_camera_adapter.py',
        'scripts/physical_camera_fixture_node.py',
        'scripts/visual_camera.py',
        'scripts/world_model_node.py',
        'test/test_ros_adapter.py',
    ):
        assert 'Copyright 2026 Ayyo Project Authors' in (
            PACKAGE_ROOT / relative
        ).read_text(encoding='utf-8')
