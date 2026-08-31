#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Lifecycle-managed fixed body, health, and compact visual adapter."""

from __future__ import annotations

from hashlib import sha256
import time

from ayyo_depth_camera import (
    DEPTH_CAMERA_INFO_TOPIC,
    DEPTH_IMAGE_TOPIC,
    depth_simulation_bundle,
    depth_test_fixture_bundle,
    DepthCameraConfigurationError,
    DepthCameraLifecycleError,
    DepthCameraValidationError,
    DepthLifecycleAdapter,
    DepthLifecycleState,
    DepthSourceRegistry,
    HEAD_DEPTH_SENSOR,
    SIMULATION_DEPTH_PROVENANCE,
    TEST_DEPTH_PROVENANCE,
)
from ayyo_interfaces.srv import GetRobotBodyState
from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    DeterministicVisualReferenceAdapter,
    EvidenceFailureKind,
    PerceptionClockRegressionError,
    PerceptionConfigurationError,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
    REFERENCE_VISUAL_PRODUCER,
)
from ayyo_physical_camera import (
    FIXTURE_PROVENANCE as PHYSICAL_CAMERA_FIXTURE_PROVENANCE,
    physical_camera_fixture_bundle,
    PhysicalCameraConfigurationError,
    PhysicalCameraLifecycleAdapter,
    PhysicalCameraLifecycleError,
    PhysicalCameraLifecycleState,
    PhysicalCameraSourceRegistry,
    PhysicalCameraValidationError,
)
from ayyo_rgbd_fusion import (
    HEAD_RGBD_FUSION_SENSOR,
    RGBD_TEST_PROVENANCE,
    RgbdFusionConfigurationError,
    RgbdFusionLifecycleAdapter,
    RgbdFusionLifecycleError,
    RgbdFusionLifecycleState,
    RgbdFusionValidationError,
    rgbd_test_requirement,
)
from ayyo_visual_evaluation import (
    DeterministicFixtureInvoker,
    fixture_bundle_for_live_profile,
    fixture_detection,
    FixtureEvaluationBundle,
    VisualEvaluationConfigurationError,
    VisualEvaluationInput,
    VisualEvaluationReport,
    VisualEvaluationSample,
    VisualProducerEvaluator,
    VisualProducerRegistry,
)
from ayyo_working_memory import (
    IngestionStatus,
    WorkingMemory,
    WorkingMemoryClockRegressionError,
    WorkingMemoryConfig,
    WorkingMemoryConfigurationError,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    CovarianceMatrix,
    FreshnessState,
    ImuObservation,
    JointObservation,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotAvailability,
    RobotJointCatalog,
    RobotStateObservation,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    WorldModelFailureCode,
    WorldModelValidationError,
)
from builtin_interfaces.msg import Time
from depth_camera_adapter import (
    DepthCameraRosAdapterError,
    normalize_depth_camera_info,
    normalize_depth_image,
)
from diagnostic_msgs.msg import DiagnosticArray
from localization_diagnostics import (
    DiagnosticAdapterError,
    DiagnosticComponentContract,
    exact_lookup,
    LocalizationAdapterError,
    normalize_diagnostics,
    normalize_localization,
    odometry_transform,
)
from nav_msgs.msg import Odometry
from physical_camera_adapter import (
    normalize_physical_camera_info_metadata,
    normalize_physical_image_metadata,
    PhysicalCameraRosAdapterError,
)
import rclpy
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.lifecycle import LifecycleNode, State, TransitionCallbackReturn
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import CameraInfo, Image, Imu, JointState
from tf2_ros import Buffer
from visual_camera import (
    CAMERA_INFO_TOPIC,
    HEAD_CAMERA_SENSOR,
    IMAGE_TOPIC,
    message_time_ns,
    normalize_visual_pair,
    VisualCameraAdapterError,
)


JOINT_STATE_TOPIC = '/joint_states'
IMU_TOPIC = '/ayyo/imu/data'
LOCALIZATION_TOPIC = '/ayyo/localization/odometry'
DIAGNOSTICS_TOPIC = '/diagnostics'
QUERY_SERVICE = '/ayyo/world_model/get_robot_body_state'
SIMULATION_SOURCE_PROFILE = 'simulation_ros2_control_v1'
PHYSICAL_SOURCE_PROFILE = 'physical_ros2_control_v1'
PHYSICAL_CAMERA_FIXTURE_SOURCE_PROFILE = 'physical_camera_test_fixture_v1'
DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE = 'depth_camera_test_fixture_v1'
SOURCE_PROFILES = {
    SIMULATION_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.SIMULATION,
        source_id='ros.joint-states.simulation.ros2-control.v1',
        clock=ObservationClock.ROS_SIMULATION_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.joint-state.v1',
    ),
    PHYSICAL_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.joint-states.physical.ros2-control.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.joint-state.v1',
    ),
    PHYSICAL_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.joint-states.physical.test-fixture.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.joint-state.v1',
    ),
    DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.TEST_FIXTURE,
        source_id='ros.joint-states.depth.test-fixture.v1',
        clock=ObservationClock.TEST_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.joint-state.v1',
    ),
}
IMU_SOURCE_PROFILES = {
    SIMULATION_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.SIMULATION,
        source_id='ros.imu.simulation.gz-harmonic.v1',
        clock=ObservationClock.ROS_SIMULATION_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.imu.v1',
    ),
    PHYSICAL_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.imu.physical.standard-driver.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.imu.v1',
    ),
    PHYSICAL_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.imu.physical.test-fixture.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.imu.v1',
    ),
    DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.TEST_FIXTURE,
        source_id='ros.imu.depth.test-fixture.v1',
        clock=ObservationClock.TEST_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.imu.v1',
    ),
}
POSE_SOURCE_PROFILES = {
    SIMULATION_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.SIMULATION,
        source_id='ros.body-pose.simulation.localization.v1',
        clock=ObservationClock.ROS_SIMULATION_TIME,
        transport=ObservationTransport.ROS2,
        interface='nav-msgs.odometry-tf2.v1',
    ),
    PHYSICAL_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.body-pose.physical.localization.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='nav-msgs.odometry-tf2.v1',
    ),
    PHYSICAL_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.body-pose.physical.test-fixture.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='nav-msgs.odometry-tf2.v1',
    ),
    DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.TEST_FIXTURE,
        source_id='ros.body-pose.depth.test-fixture.v1',
        clock=ObservationClock.TEST_TIME,
        transport=ObservationTransport.ROS2,
        interface='nav-msgs.odometry-tf2.v1',
    ),
}
DIAGNOSTIC_SOURCE_PROFILES = {
    SIMULATION_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.SIMULATION,
        source_id='ros.diagnostics.simulation.test-fixture.v1',
        clock=ObservationClock.ROS_SIMULATION_TIME,
        transport=ObservationTransport.ROS2,
        interface='diagnostic-msgs.diagnostic-array.v1',
    ),
    PHYSICAL_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.diagnostics.physical.standard.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='diagnostic-msgs.diagnostic-array.v1',
    ),
    PHYSICAL_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.diagnostics.physical.test-fixture.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='diagnostic-msgs.diagnostic-array.v1',
    ),
    DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.TEST_FIXTURE,
        source_id='ros.diagnostics.depth.test-fixture.v1',
        clock=ObservationClock.TEST_TIME,
        transport=ObservationTransport.ROS2,
        interface='diagnostic-msgs.diagnostic-array.v1',
    ),
}
CAMERA_SOURCE_PROFILES = {
    SIMULATION_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.SIMULATION,
        source_id='ros.camera.head.simulation.gz-harmonic.v1',
        clock=ObservationClock.ROS_SIMULATION_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.image-camera-info.v1',
    ),
    PHYSICAL_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.camera.head.physical.standard-driver.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.image-camera-info.v1',
    ),
    PHYSICAL_CAMERA_FIXTURE_SOURCE_PROFILE: PHYSICAL_CAMERA_FIXTURE_PROVENANCE,
    DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.TEST_FIXTURE,
        source_id='ros.camera.head.rgb.depth.test-fixture.v1',
        clock=ObservationClock.TEST_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.image-camera-info.v1',
    ),
}
DEPTH_SOURCE_PROFILES = {
    SIMULATION_SOURCE_PROFILE: SIMULATION_DEPTH_PROVENANCE,
    PHYSICAL_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.camera.head.depth.physical.unconfigured.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.image-camera-info.depth.v1',
    ),
    PHYSICAL_CAMERA_FIXTURE_SOURCE_PROFILE: ObservationProvenance(
        source_kind=ObservationSourceKind.PHYSICAL_SENSOR,
        source_id='ros.camera.head.depth.physical.unconfigured.v1',
        clock=ObservationClock.ROS_SYSTEM_TIME,
        transport=ObservationTransport.ROS2,
        interface='sensor-msgs.image-camera-info.depth.v1',
    ),
    DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE: TEST_DEPTH_PROVENANCE,
}
JOINT_SENSOR = SensorIdentity(
    'ayyo.joint-state.body.v1',
    SensorKind.JOINT_STATE,
    'base_link',
)
IMU_SENSOR = SensorIdentity('ayyo.imu.body.v1', SensorKind.IMU, 'imu_link')
BODY_POSE_SENSOR = SensorIdentity(
    'ayyo.body-pose.localization.v1',
    SensorKind.BODY_POSE,
    'base_link',
)
DIAGNOSTIC_COMPONENTS = (
    DiagnosticComponentContract(
        'ayyo/proprioception/body_imu_source',
        IMU_SENSOR.sensor_id,
        IMU_SENSOR,
    ),
    DiagnosticComponentContract(
        'ayyo/proprioception/joint_state_source',
        JOINT_SENSOR.sensor_id,
        JOINT_SENSOR,
    ),
)


def _nanoseconds(seconds: int, nanoseconds: int) -> int:
    if type(seconds) is not int or type(nanoseconds) is not int:
        raise WorldModelValidationError(
            code=WorldModelFailureCode.MALFORMED_OBSERVATION,
            detail='ROS time fields must be integers',
        )
    if seconds < 0 or not 0 <= nanoseconds < 1_000_000_000:
        raise WorldModelValidationError(
            code=WorldModelFailureCode.MALFORMED_OBSERVATION,
            detail='ROS time fields are outside their canonical range',
        )
    return seconds * 1_000_000_000 + nanoseconds


def _assign_time(message, value_ns: int) -> None:
    message.sec = value_ns // 1_000_000_000
    message.nanosec = value_ns % 1_000_000_000


def normalize_joint_state(
    message: JointState,
    provenance: ObservationProvenance,
) -> RobotStateObservation:
    """Normalize one standard message without consulting ROS graph state."""
    if not isinstance(message, JointState):
        raise ValueError('body-state evidence must be sensor_msgs/JointState')
    if type(provenance) is not ObservationProvenance:
        raise ValueError('body-state evidence requires reviewed provenance')
    names = tuple(message.name)
    positions = tuple(message.position)
    velocities = tuple(message.velocity)
    efforts = tuple(message.effort)
    if not names or len(names) != len(positions):
        raise ValueError('joint names and positions must be non-empty and equal')
    if velocities and len(velocities) != len(names):
        raise ValueError('velocity array must be empty or match joint names')
    if efforts and len(efforts) != len(names):
        raise ValueError('effort array must be empty or match joint names')
    return RobotStateObservation(
        robot_id=AYYO_ROBOT_ID,
        joints=tuple(
            JointObservation(
                joint_name=name,
                position=positions[index],
                velocity=None if not velocities else velocities[index],
                effort=None if not efforts else efforts[index],
            )
            for index, name in enumerate(names)
        ),
        observed_at_ns=_nanoseconds(
            message.header.stamp.sec,
            message.header.stamp.nanosec,
        ),
        provenance=provenance,
        confidence=1.0,
    )


def _imu_estimate(
    vector,
    covariance_values,
    *,
    field_name: str,
) -> tuple[tuple[float, float, float] | None, CovarianceMatrix | None]:
    covariance = tuple(covariance_values)
    if len(covariance) != 9:
        raise ValueError(f'{field_name} covariance must contain exactly nine values')
    if covariance[0] == -1.0:
        return None, None
    estimate = (vector.x, vector.y, vector.z)
    supplied_covariance = (
        None
        if all(value == 0.0 for value in covariance)
        else CovarianceMatrix(3, covariance)
    )
    return estimate, supplied_covariance


def normalize_imu(
    message: Imu,
    provenance: ObservationProvenance,
) -> ImuObservation:
    """Decode ROS Imu semantics without fabricating unavailable estimates."""
    if not isinstance(message, Imu):
        raise ValueError('IMU evidence must be sensor_msgs/Imu')
    if type(provenance) is not ObservationProvenance:
        raise ValueError('IMU evidence requires reviewed provenance')
    if message.header.frame_id != IMU_SENSOR.frame_id:
        raise ValueError('IMU frame identity does not match the reviewed mount')
    orientation_covariance = tuple(message.orientation_covariance)
    if len(orientation_covariance) != 9:
        raise ValueError('orientation covariance must contain exactly nine values')
    if orientation_covariance[0] == -1.0:
        orientation = None
        supplied_orientation_covariance = None
    else:
        orientation = (
            message.orientation.x,
            message.orientation.y,
            message.orientation.z,
            message.orientation.w,
        )
        supplied_orientation_covariance = (
            None
            if all(value == 0.0 for value in orientation_covariance)
            else CovarianceMatrix(3, orientation_covariance)
        )
    angular_velocity, angular_velocity_covariance = _imu_estimate(
        message.angular_velocity,
        message.angular_velocity_covariance,
        field_name='angular velocity',
    )
    linear_acceleration, linear_acceleration_covariance = _imu_estimate(
        message.linear_acceleration,
        message.linear_acceleration_covariance,
        field_name='linear acceleration',
    )
    return ImuObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=IMU_SENSOR,
        orientation_xyzw=orientation,
        orientation_covariance=supplied_orientation_covariance,
        angular_velocity_xyz=angular_velocity,
        angular_velocity_covariance=angular_velocity_covariance,
        linear_acceleration_xyz=linear_acceleration,
        linear_acceleration_covariance=linear_acceleration_covariance,
        observed_at_ns=_nanoseconds(
            message.header.stamp.sec,
            message.header.stamp.nanosec,
        ),
        provenance=provenance,
        availability=SensorAvailability.AVAILABLE,
        quality=None,
    )


class AyyoWorldModelNode(LifecycleNode):
    """Own reviewed ROS normalization while cores remain transport-neutral."""

    def __init__(self) -> None:
        super().__init__('ayyo_world_model')
        self.declare_parameter('robot_description', '')
        self.declare_parameter('source_profile', 'unconfigured')
        self.declare_parameter('freshness_ms', 500)
        self.declare_parameter('retention_ttl_ms', 2000)
        self.declare_parameter('permitted_future_skew_ms', 50)
        self.declare_parameter('recent_evidence_capacity', 256)
        self.declare_parameter('environment_entity_capacity', 128)
        self.declare_parameter('pose_lookup_timeout_ms', 20)
        self.declare_parameter('enable_visual_reference_interpreter', False)
        self.declare_parameter(
            'enable_visual_producer_evaluation_fixture',
            False,
        )
        self.declare_parameter('enable_physical_camera_adapter', False)
        self.declare_parameter('physical_camera_profile', 'unconfigured')
        self.declare_parameter('enable_depth_camera_adapter', False)
        self.declare_parameter('depth_camera_profile', 'unconfigured')
        self.declare_parameter('enable_rgbd_fusion_adapter', False)
        self.declare_parameter('rgbd_fusion_profile', 'unconfigured')
        self._memory: WorkingMemory | None = None
        self._trust_boundary: PerceptionTrustBoundary | None = None
        self._provenance: ObservationProvenance | None = None
        self._imu_provenance: ObservationProvenance | None = None
        self._pose_provenance: ObservationProvenance | None = None
        self._diagnostic_provenance: ObservationProvenance | None = None
        self._camera_provenance: ObservationProvenance | None = None
        self._depth_provenance: ObservationProvenance | None = None
        self._camera_enabled = False
        self._depth_enabled = False
        self._rgbd_enabled = False
        self._physical_camera_adapter: PhysicalCameraLifecycleAdapter | None = None
        self._depth_camera_adapter: DepthLifecycleAdapter | None = None
        self._rgbd_fusion_adapter: RgbdFusionLifecycleAdapter | None = None
        self._visual_reference_adapter: (
            DeterministicVisualReferenceAdapter | None
        ) = None
        self._visual_evaluation_bundle: FixtureEvaluationBundle | None = None
        self._visual_evaluation_report: VisualEvaluationReport | None = None
        self._visual_evaluator: VisualProducerEvaluator | None = None
        self._visual_evaluated_this_activation = False
        self._joint_subscription = None
        self._imu_subscription = None
        self._localization_subscription = None
        self._diagnostics_subscription = None
        self._image_subscription = None
        self._camera_info_subscription = None
        self._depth_image_subscription = None
        self._depth_camera_info_subscription = None
        self._pending_image: Image | None = None
        self._pending_camera_info: CameraInfo | None = None
        self._pose_buffer: Buffer | None = None
        self._pose_lookup_timeout_ns = 0
        self._query_service = None
        self._active = False
        self._invalid_message_count = 0
        self._rejected_message_count = 0

    def _destroy_runtime_interfaces(self) -> None:
        if self._joint_subscription is not None:
            self.destroy_subscription(self._joint_subscription)
            self._joint_subscription = None
        if self._imu_subscription is not None:
            self.destroy_subscription(self._imu_subscription)
            self._imu_subscription = None
        if self._localization_subscription is not None:
            self.destroy_subscription(self._localization_subscription)
            self._localization_subscription = None
        if self._diagnostics_subscription is not None:
            self.destroy_subscription(self._diagnostics_subscription)
            self._diagnostics_subscription = None
        if self._image_subscription is not None:
            self.destroy_subscription(self._image_subscription)
            self._image_subscription = None
        if self._camera_info_subscription is not None:
            self.destroy_subscription(self._camera_info_subscription)
            self._camera_info_subscription = None
        if self._depth_image_subscription is not None:
            self.destroy_subscription(self._depth_image_subscription)
            self._depth_image_subscription = None
        if self._depth_camera_info_subscription is not None:
            self.destroy_subscription(self._depth_camera_info_subscription)
            self._depth_camera_info_subscription = None
        self._pending_image = None
        self._pending_camera_info = None
        self._pose_buffer = None
        if self._query_service is not None:
            self.destroy_service(self._query_service)
            self._query_service = None

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        del state
        try:
            profile_name = self.get_parameter('source_profile').value
            provenance = SOURCE_PROFILES.get(profile_name)
            imu_provenance = IMU_SOURCE_PROFILES.get(profile_name)
            pose_provenance = POSE_SOURCE_PROFILES.get(profile_name)
            diagnostic_provenance = DIAGNOSTIC_SOURCE_PROFILES.get(profile_name)
            camera_provenance = CAMERA_SOURCE_PROFILES.get(profile_name)
            depth_provenance = DEPTH_SOURCE_PROFILES.get(profile_name)
            if (
                provenance is None
                or imu_provenance is None
                or pose_provenance is None
                or diagnostic_provenance is None
                or camera_provenance is None
                or depth_provenance is None
            ):
                raise WorkingMemoryConfigurationError(
                    'source_profile must select one reviewed observation profile'
                )
            use_sim_time = bool(self.get_parameter('use_sim_time').value)
            if (
                provenance.clock is ObservationClock.ROS_SIMULATION_TIME
                and not use_sim_time
            ) or (
                provenance.clock is ObservationClock.ROS_SYSTEM_TIME
                and use_sim_time
            ):
                raise WorkingMemoryConfigurationError(
                    'source profile and ROS clock configuration disagree'
                )
            description = self.get_parameter('robot_description').value
            catalog = RobotJointCatalog.from_urdf(
                robot_id=AYYO_ROBOT_ID,
                robot_description=description,
            )
            pose_lookup_timeout_ms = int(
                self.get_parameter('pose_lookup_timeout_ms').value
            )
            if not 0 <= pose_lookup_timeout_ms <= 100:
                raise WorkingMemoryConfigurationError(
                    'pose lookup timeout must be between zero and 100 milliseconds'
                )
            self._pose_lookup_timeout_ns = pose_lookup_timeout_ms * 1_000_000
            enable_visual_reference = bool(
                self.get_parameter('enable_visual_reference_interpreter').value
            )
            enable_visual_evaluation = bool(
                self.get_parameter(
                    'enable_visual_producer_evaluation_fixture'
                ).value
            )
            enable_physical_camera = bool(
                self.get_parameter('enable_physical_camera_adapter').value
            )
            physical_camera_profile = self.get_parameter(
                'physical_camera_profile'
            ).value
            if enable_visual_reference and enable_visual_evaluation:
                raise WorkingMemoryConfigurationError(
                    'visual reference and evaluated fixture modes are mutually exclusive'
                )
            physical_camera_bundle = None
            physical_camera_adapter = None
            physical_camera_requirements = ()
            if enable_physical_camera:
                if (
                    profile_name != PHYSICAL_CAMERA_FIXTURE_SOURCE_PROFILE
                    or physical_camera_profile != 'test_fixture_v1'
                ):
                    raise PhysicalCameraConfigurationError(
                        'v1 physical camera adapter requires the explicit TEST fixture profile'
                    )
                if enable_visual_reference or enable_visual_evaluation:
                    raise PhysicalCameraConfigurationError(
                        'physical camera, visual reference, and evaluation '
                        'fixtures remain distinct'
                    )
                physical_camera_bundle = physical_camera_fixture_bundle()
                if physical_camera_bundle.source.provenance != camera_provenance:
                    raise PhysicalCameraConfigurationError(
                        'physical camera fixture provenance differs from composition'
                    )
                physical_registry = PhysicalCameraSourceRegistry()
                physical_registry.register(physical_camera_bundle.source)
                physical_camera_adapter = PhysicalCameraLifecycleAdapter(
                    physical_registry,
                    retention_ns=int(
                        self.get_parameter('retention_ttl_ms').value
                    )
                    * 1_000_000,
                    future_skew_ns=int(
                        self.get_parameter('permitted_future_skew_ms').value
                    )
                    * 1_000_000,
                )
                physical_camera_adapter.configure(
                    physical_camera_bundle.source.source_id,
                    physical_camera_bundle.calibration,
                )
                physical_camera_requirements = (
                    physical_camera_bundle.source.requirement(),
                )
            elif physical_camera_profile != 'unconfigured':
                raise PhysicalCameraConfigurationError(
                    'physical camera profile must remain unconfigured while disabled'
                )
            enable_depth_camera = bool(
                self.get_parameter('enable_depth_camera_adapter').value
            )
            depth_camera_profile = self.get_parameter(
                'depth_camera_profile'
            ).value
            depth_camera_bundle = None
            depth_camera_adapter = None
            depth_camera_requirements = ()
            if enable_depth_camera:
                if (
                    profile_name == SIMULATION_SOURCE_PROFILE
                    and depth_camera_profile == 'simulation_depth_v1'
                ):
                    depth_camera_bundle = depth_simulation_bundle()
                elif (
                    profile_name == DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE
                    and depth_camera_profile == 'test_fixture_v1'
                ):
                    depth_camera_bundle = depth_test_fixture_bundle()
                else:
                    raise DepthCameraConfigurationError(
                        'depth adapter requires one exact reviewed composition profile'
                    )
                if depth_camera_bundle.source.provenance != depth_provenance:
                    raise DepthCameraConfigurationError(
                        'depth source provenance differs from its composition'
                    )
                depth_registry = DepthSourceRegistry()
                depth_registry.register(depth_camera_bundle.source)
                depth_camera_adapter = DepthLifecycleAdapter(
                    depth_registry,
                    retention_ns=int(
                        self.get_parameter('retention_ttl_ms').value
                    )
                    * 1_000_000,
                    future_skew_ns=int(
                        self.get_parameter('permitted_future_skew_ms').value
                    )
                    * 1_000_000,
                )
                depth_camera_adapter.configure(
                    depth_camera_bundle.source.source_id,
                    depth_camera_bundle.calibration,
                )
                depth_camera_requirements = (
                    depth_camera_bundle.source.requirement(),
                )
            elif depth_camera_profile != 'unconfigured':
                raise DepthCameraConfigurationError(
                    'depth profile must remain unconfigured while disabled'
                )
            enable_rgbd_fusion = bool(
                self.get_parameter('enable_rgbd_fusion_adapter').value
            )
            rgbd_fusion_profile = self.get_parameter(
                'rgbd_fusion_profile'
            ).value
            rgbd_fusion_adapter = None
            rgbd_fusion_requirements = ()
            if enable_rgbd_fusion:
                if (
                    profile_name != DEPTH_CAMERA_FIXTURE_SOURCE_PROFILE
                    or rgbd_fusion_profile != 'exact_test_fixture_v1'
                    or depth_camera_bundle is None
                    or depth_camera_adapter is None
                    or physical_camera_adapter is not None
                ):
                    raise RgbdFusionConfigurationError(
                        'RGB-D v1 requires the exact TEST fixture composition'
                    )
                if enable_visual_reference or enable_visual_evaluation:
                    raise RgbdFusionConfigurationError(
                        'RGB-D and visual interpretation fixtures remain distinct'
                    )
                rgb_bundle = physical_camera_fixture_bundle()
                requirement = rgbd_test_requirement(
                    rgb_sensor=HEAD_CAMERA_SENSOR,
                    rgb_provenance=camera_provenance,
                    rgb_calibration_id=(
                        rgb_bundle.calibration.calibration.calibration_id
                    ),
                    depth_sensor=depth_camera_bundle.source.sensor,
                    depth_provenance=depth_camera_bundle.source.provenance,
                    depth_calibration_id=(
                        depth_camera_bundle.calibration.calibration.calibration_id
                    ),
                    depth_producer_id=depth_camera_bundle.source.producer_id,
                    depth_producer_implementation_sha256=(
                        depth_camera_bundle.source.producer_implementation_sha256
                    ),
                    depth_source_fingerprint_sha256=(
                        depth_camera_bundle.source.manifest_id.removeprefix(
                            'depth-camera-source-sha256-'
                        )
                    ),
                )
                retention_ns = int(
                    self.get_parameter('retention_ttl_ms').value
                ) * 1_000_000
                rgbd_fusion_adapter = RgbdFusionLifecycleAdapter(
                    pair_wait_ns=min(200_000_000, retention_ns // 2),
                    retention_ns=retention_ns,
                    future_skew_ns=int(
                        self.get_parameter('permitted_future_skew_ms').value
                    )
                    * 1_000_000,
                )
                rgbd_fusion_adapter.configure(requirement)
                rgbd_fusion_requirements = (requirement,)
            elif rgbd_fusion_profile != 'unconfigured':
                raise RgbdFusionConfigurationError(
                    'RGB-D profile must remain unconfigured while disabled'
                )
            camera_enabled = (
                camera_provenance.source_kind is ObservationSourceKind.SIMULATION
                or physical_camera_adapter is not None
                or rgbd_fusion_adapter is not None
            )
            visual_bundle = None
            visual_evaluator = None
            visual_report = None
            visual_requirements = ()
            if enable_visual_evaluation:
                visual_bundle = fixture_bundle_for_live_profile(
                    camera_provenance,
                    width=320,
                    height=240,
                )
                registry = VisualProducerRegistry()
                registry.register(visual_bundle.registration)
                visual_evaluator = VisualProducerEvaluator(
                    registry,
                    DeterministicFixtureInvoker(),
                    software_identities=(
                        'ayyo.visual-evaluation.core.v1',
                        'ayyo.world-model.ros-fixture-adapter.v1',
                    ),
                )
                outcome = visual_evaluator.evaluate(
                    producer_id=visual_bundle.manifest.producer.producer_id,
                    dataset=visual_bundle.dataset,
                    source=visual_bundle.source,
                    policy=visual_bundle.policy,
                    run_id='ayyo.ros-fixture.configure.v1',
                )
                if len(outcome.admissions) != 1:
                    raise VisualEvaluationConfigurationError(
                        'recorded fixture did not issue exactly one admission'
                    )
                visual_report = outcome.report
                visual_requirements = (outcome.admissions[0].requirement,)
            visual_producers = (
                (visual_bundle.manifest.producer,)
                if visual_bundle is not None
                else (
                    (REFERENCE_VISUAL_PRODUCER,)
                    if enable_visual_reference
                    else ()
                )
            )
            perception_sources = (
                PerceptionSourceContract(JOINT_SENSOR, provenance),
                PerceptionSourceContract(IMU_SENSOR, imu_provenance),
                PerceptionSourceContract(
                    BODY_POSE_SENSOR,
                    pose_provenance,
                    'odom',
                ),
                PerceptionSourceContract(
                    JOINT_SENSOR,
                    diagnostic_provenance,
                ),
                PerceptionSourceContract(
                    IMU_SENSOR,
                    diagnostic_provenance,
                ),
            ) + (
                (
                    PerceptionSourceContract(
                        HEAD_CAMERA_SENSOR,
                        camera_provenance,
                    ),
                )
                if camera_enabled
                else ()
            ) + (
                (
                    PerceptionSourceContract(
                        HEAD_DEPTH_SENSOR,
                        depth_provenance,
                    ),
                )
                if depth_camera_adapter is not None
                else ()
            ) + (
                (
                    PerceptionSourceContract(
                        HEAD_RGBD_FUSION_SENSOR,
                        RGBD_TEST_PROVENANCE,
                    ),
                )
                if rgbd_fusion_adapter is not None
                else ()
            )
            sensor_catalog = (
                JOINT_SENSOR,
                IMU_SENSOR,
                BODY_POSE_SENSOR,
                HEAD_CAMERA_SENSOR,
                HEAD_DEPTH_SENSOR,
            ) + (
                (HEAD_RGBD_FUSION_SENSOR,)
                if rgbd_fusion_adapter is not None
                else ()
            )
            allowed_provenance = (
                provenance,
                imu_provenance,
                pose_provenance,
                diagnostic_provenance,
                camera_provenance,
                depth_provenance,
            ) + (
                (RGBD_TEST_PROVENANCE,)
                if rgbd_fusion_adapter is not None
                else ()
            )
            self._memory = WorkingMemory(
                catalog,
                WorkingMemoryConfig(
                    robot_id=AYYO_ROBOT_ID,
                    source_clock=provenance.clock,
                    allowed_provenance=allowed_provenance,
                    sensors=tuple(
                        sorted(
                            sensor_catalog,
                            key=lambda item: item.sensor_id,
                        )
                    ),
                    freshness_ns=int(self.get_parameter('freshness_ms').value)
                    * 1_000_000,
                    retention_ttl_ns=int(
                        self.get_parameter('retention_ttl_ms').value
                    )
                    * 1_000_000,
                    permitted_future_skew_ns=int(
                        self.get_parameter('permitted_future_skew_ms').value
                    )
                    * 1_000_000,
                    recent_evidence_capacity=int(
                        self.get_parameter('recent_evidence_capacity').value
                    ),
                    environment_entity_capacity=int(
                        self.get_parameter('environment_entity_capacity').value
                    ),
                    visual_interpretation_producers=visual_producers,
                    visual_evaluation_requirements=visual_requirements,
                ),
            )
            self._trust_boundary = PerceptionTrustBoundary(
                PerceptionTrustConfig(
                    robot_id=AYYO_ROBOT_ID,
                    source_clock=provenance.clock,
                    sources=perception_sources,
                    freshness_ns=int(self.get_parameter('freshness_ms').value)
                    * 1_000_000,
                    retention_ttl_ns=int(
                        self.get_parameter('retention_ttl_ms').value
                    )
                    * 1_000_000,
                    permitted_future_skew_ns=int(
                        self.get_parameter('permitted_future_skew_ms').value
                    )
                    * 1_000_000,
                    visual_interpretation_producers=visual_producers,
                    visual_evaluation_requirements=visual_requirements,
                    physical_camera_requirements=physical_camera_requirements,
                    depth_camera_requirements=depth_camera_requirements,
                    rgbd_fusion_requirements=rgbd_fusion_requirements,
                )
            )
            self._provenance = provenance
            self._imu_provenance = imu_provenance
            self._pose_provenance = pose_provenance
            self._diagnostic_provenance = diagnostic_provenance
            self._camera_provenance = camera_provenance
            self._depth_provenance = depth_provenance
            self._camera_enabled = camera_enabled
            self._depth_enabled = depth_camera_adapter is not None
            self._rgbd_enabled = rgbd_fusion_adapter is not None
            self._physical_camera_adapter = physical_camera_adapter
            self._depth_camera_adapter = depth_camera_adapter
            self._rgbd_fusion_adapter = rgbd_fusion_adapter
            self._visual_reference_adapter = (
                DeterministicVisualReferenceAdapter()
                if enable_visual_reference
                else None
            )
            self._visual_evaluation_bundle = visual_bundle
            self._visual_evaluation_report = visual_report
            self._visual_evaluator = visual_evaluator
            self._visual_evaluated_this_activation = False
            self._query_service = self.create_service(
                GetRobotBodyState,
                QUERY_SERVICE,
                self._handle_query,
            )
            self._invalid_message_count = 0
            self._rejected_message_count = 0
            return TransitionCallbackReturn.SUCCESS
        except (
            PerceptionConfigurationError,
            PhysicalCameraConfigurationError,
            PhysicalCameraLifecycleError,
            PhysicalCameraValidationError,
            DepthCameraConfigurationError,
            DepthCameraLifecycleError,
            DepthCameraValidationError,
            RgbdFusionConfigurationError,
            RgbdFusionLifecycleError,
            RgbdFusionValidationError,
            VisualEvaluationConfigurationError,
            WorldModelValidationError,
            WorkingMemoryConfigurationError,
        ) as error:
            self.get_logger().error(f'World Model configure failed: {error}')
            self._memory = None
            self._trust_boundary = None
            self._provenance = None
            self._imu_provenance = None
            self._pose_provenance = None
            self._diagnostic_provenance = None
            self._camera_provenance = None
            self._depth_provenance = None
            self._camera_enabled = False
            self._depth_enabled = False
            self._rgbd_enabled = False
            self._physical_camera_adapter = None
            self._depth_camera_adapter = None
            self._rgbd_fusion_adapter = None
            self._visual_reference_adapter = None
            self._visual_evaluation_bundle = None
            self._visual_evaluation_report = None
            self._visual_evaluator = None
            self._visual_evaluated_this_activation = False
            self._destroy_runtime_interfaces()
            return TransitionCallbackReturn.FAILURE

    def on_activate(self, state: State) -> TransitionCallbackReturn:
        del state
        if (
            self._memory is None
            or self._trust_boundary is None
            or self._provenance is None
            or self._imu_provenance is None
            or self._pose_provenance is None
            or self._diagnostic_provenance is None
            or self._camera_provenance is None
            or self._depth_provenance is None
        ):
            return TransitionCallbackReturn.FAILURE
        if self._physical_camera_adapter is not None:
            try:
                self._physical_camera_adapter.activate()
            except PhysicalCameraLifecycleError as error:
                self.get_logger().error(
                    f'physical camera activation failed closed: {error}'
                )
                return TransitionCallbackReturn.FAILURE
        if self._depth_camera_adapter is not None:
            try:
                depth_session_id = self._depth_camera_adapter.activate()
            except DepthCameraLifecycleError as error:
                self.get_logger().error(
                    f'depth camera activation failed closed: {error}'
                )
                if (
                    self._physical_camera_adapter is not None
                    and self._physical_camera_adapter.state
                    is PhysicalCameraLifecycleState.ACTIVE
                ):
                    self._physical_camera_adapter.deactivate()
                return TransitionCallbackReturn.FAILURE
            if self._rgbd_fusion_adapter is not None:
                try:
                    self._rgbd_fusion_adapter.activate(
                        depth_session_id=depth_session_id
                    )
                except RgbdFusionLifecycleError as error:
                    self.get_logger().error(
                        f'RGB-D fusion activation failed closed: {error}'
                    )
                    self._depth_camera_adapter.deactivate()
                    if (
                        self._physical_camera_adapter is not None
                        and self._physical_camera_adapter.state
                        is PhysicalCameraLifecycleState.ACTIVE
                    ):
                        self._physical_camera_adapter.deactivate()
                    return TransitionCallbackReturn.FAILURE
        self._joint_subscription = self.create_subscription(
            JointState,
            JOINT_STATE_TOPIC,
            self._on_joint_state,
            qos_profile_sensor_data,
        )
        self._imu_subscription = self.create_subscription(
            Imu,
            IMU_TOPIC,
            self._on_imu,
            qos_profile_sensor_data,
        )
        self._pose_buffer = Buffer(
            cache_time=Duration(
                nanoseconds=self._trust_boundary.config.retention_ttl_ns
            )
        )
        self._localization_subscription = self.create_subscription(
            Odometry,
            LOCALIZATION_TOPIC,
            self._on_localization,
            qos_profile_sensor_data,
        )
        self._diagnostics_subscription = self.create_subscription(
            DiagnosticArray,
            DIAGNOSTICS_TOPIC,
            self._on_diagnostics,
            10,
        )
        if self._camera_enabled:
            self._image_subscription = self.create_subscription(
                Image,
                IMAGE_TOPIC,
                self._on_image,
                qos_profile_sensor_data,
            )
            self._camera_info_subscription = self.create_subscription(
                CameraInfo,
                CAMERA_INFO_TOPIC,
                self._on_camera_info,
                qos_profile_sensor_data,
            )
        if self._depth_enabled:
            self._depth_image_subscription = self.create_subscription(
                Image,
                DEPTH_IMAGE_TOPIC,
                self._on_depth_image,
                qos_profile_sensor_data,
            )
            self._depth_camera_info_subscription = self.create_subscription(
                CameraInfo,
                DEPTH_CAMERA_INFO_TOPIC,
                self._on_depth_camera_info,
                qos_profile_sensor_data,
            )
        self._visual_evaluated_this_activation = False
        self._active = True
        return TransitionCallbackReturn.SUCCESS

    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        del state
        self._active = False
        if self._joint_subscription is not None:
            self.destroy_subscription(self._joint_subscription)
            self._joint_subscription = None
        if self._imu_subscription is not None:
            self.destroy_subscription(self._imu_subscription)
            self._imu_subscription = None
        if self._localization_subscription is not None:
            self.destroy_subscription(self._localization_subscription)
            self._localization_subscription = None
        if self._diagnostics_subscription is not None:
            self.destroy_subscription(self._diagnostics_subscription)
            self._diagnostics_subscription = None
        if self._image_subscription is not None:
            self.destroy_subscription(self._image_subscription)
            self._image_subscription = None
        if self._camera_info_subscription is not None:
            self.destroy_subscription(self._camera_info_subscription)
            self._camera_info_subscription = None
        if self._depth_image_subscription is not None:
            self.destroy_subscription(self._depth_image_subscription)
            self._depth_image_subscription = None
        if self._depth_camera_info_subscription is not None:
            self.destroy_subscription(self._depth_camera_info_subscription)
            self._depth_camera_info_subscription = None
        self._pending_image = None
        self._pending_camera_info = None
        self._visual_evaluated_this_activation = False
        self._pose_buffer = None
        if (
            self._rgbd_fusion_adapter is not None
            and self._rgbd_fusion_adapter.state
            is RgbdFusionLifecycleState.ACTIVE
        ):
            self._rgbd_fusion_adapter.deactivate()
        if (
            self._physical_camera_adapter is not None
            and self._physical_camera_adapter.state
            is PhysicalCameraLifecycleState.ACTIVE
        ):
            self._physical_camera_adapter.deactivate()
            if self._memory is not None:
                self._memory.reset()
            if self._trust_boundary is not None:
                self._trust_boundary.reset()
        if (
            self._depth_camera_adapter is not None
            and self._depth_camera_adapter.state is DepthLifecycleState.ACTIVE
        ):
            self._depth_camera_adapter.deactivate()
            if self._memory is not None:
                self._memory.reset()
            if self._trust_boundary is not None:
                self._trust_boundary.reset()
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        del state
        self._active = False
        self._destroy_runtime_interfaces()
        if self._physical_camera_adapter is not None:
            if (
                self._physical_camera_adapter.state
                is PhysicalCameraLifecycleState.ACTIVE
            ):
                self._physical_camera_adapter.deactivate()
            self._physical_camera_adapter.cleanup()
        if self._depth_camera_adapter is not None:
            if self._depth_camera_adapter.state is DepthLifecycleState.ACTIVE:
                self._depth_camera_adapter.deactivate()
            self._depth_camera_adapter.cleanup()
        if self._rgbd_fusion_adapter is not None:
            if (
                self._rgbd_fusion_adapter.state
                is RgbdFusionLifecycleState.ACTIVE
            ):
                self._rgbd_fusion_adapter.deactivate()
            self._rgbd_fusion_adapter.cleanup()
        if self._memory is not None:
            self._memory.reset()
        if self._trust_boundary is not None:
            self._trust_boundary.reset()
        self._memory = None
        self._trust_boundary = None
        self._provenance = None
        self._imu_provenance = None
        self._pose_provenance = None
        self._diagnostic_provenance = None
        self._camera_provenance = None
        self._depth_provenance = None
        self._camera_enabled = False
        self._depth_enabled = False
        self._rgbd_enabled = False
        self._physical_camera_adapter = None
        self._depth_camera_adapter = None
        self._rgbd_fusion_adapter = None
        self._visual_reference_adapter = None
        self._visual_evaluation_bundle = None
        self._visual_evaluation_report = None
        self._visual_evaluator = None
        self._visual_evaluated_this_activation = False
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        del state
        self._active = False
        self._destroy_runtime_interfaces()
        if self._physical_camera_adapter is not None:
            self._physical_camera_adapter.shutdown()
        if self._depth_camera_adapter is not None:
            self._depth_camera_adapter.shutdown()
        if self._rgbd_fusion_adapter is not None:
            self._rgbd_fusion_adapter.shutdown()
        if self._memory is not None:
            self._memory.reset()
        if self._trust_boundary is not None:
            self._trust_boundary.reset()
        self._memory = None
        self._trust_boundary = None
        self._provenance = None
        self._imu_provenance = None
        self._pose_provenance = None
        self._diagnostic_provenance = None
        self._camera_provenance = None
        self._depth_provenance = None
        self._camera_enabled = False
        self._depth_enabled = False
        self._rgbd_enabled = False
        self._physical_camera_adapter = None
        self._depth_camera_adapter = None
        self._rgbd_fusion_adapter = None
        self._visual_reference_adapter = None
        self._visual_evaluation_bundle = None
        self._visual_evaluation_report = None
        self._visual_evaluator = None
        self._visual_evaluated_this_activation = False
        return TransitionCallbackReturn.SUCCESS

    def on_error(self, state: State) -> TransitionCallbackReturn:
        return self.on_cleanup(state)

    def _warn_bounded(self, category: str, detail: str) -> None:
        if category == 'invalid':
            self._invalid_message_count += 1
            count = self._invalid_message_count
        else:
            self._rejected_message_count += 1
            count = self._rejected_message_count
        if count == 1 or count % 100 == 0:
            self.get_logger().warning(
                f'{category} perception evidence count={count}: {detail}'
            )

    def _reset_evidence_epoch(self) -> None:
        if self._trust_boundary is not None:
            self._trust_boundary.reset()
        if self._memory is not None:
            self._memory.reset()
        self._visual_evaluated_this_activation = False

    def _admit_and_retain(self, observation):
        if self._trust_boundary is None or self._memory is None:
            return None
        now_ns = self.get_clock().now().nanoseconds
        receipt_ns = time.monotonic_ns()
        try:
            admission = self._trust_boundary.admit(
                observation,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt_ns,
            )
            if admission.status is AdmissionStatus.REJECTED:
                self._warn_bounded(
                    'rejected',
                    f'{admission.reason.value}: {admission.detail}',
                )
                return admission
            if admission.status is AdmissionStatus.DUPLICATE:
                return admission
            retained = self._memory.ingest(
                admission.observation,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt_ns,
            )
        except (PerceptionClockRegressionError, WorkingMemoryClockRegressionError):
            self.get_logger().warning(
                'ROS source clock regressed; discarded the temporary perception epoch'
            )
            self._reset_evidence_epoch()
            now_ns = self.get_clock().now().nanoseconds
            receipt_ns = time.monotonic_ns()
            admission = self._trust_boundary.admit(
                observation,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt_ns,
            )
            if admission.status is not AdmissionStatus.ACCEPTED:
                self._warn_bounded(
                    'rejected',
                    f'{admission.reason.value}: {admission.detail}',
                )
                return admission
            retained = self._memory.ingest(
                admission.observation,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt_ns,
            )
        if retained.status is IngestionStatus.REJECTED:
            self._warn_bounded(
                'rejected',
                f'{retained.reason.value}: {retained.detail}',
            )
        return admission

    def _on_joint_state(self, message: JointState) -> None:
        if not self._active or self._provenance is None:
            return
        try:
            observation = normalize_joint_state(message, self._provenance)
            self._admit_and_retain(observation)
        except (
            PerceptionConfigurationError,
            ValueError,
            WorldModelValidationError,
            WorkingMemoryConfigurationError,
        ) as error:
            self._warn_bounded('invalid', str(error))

    def _on_imu(self, message: Imu) -> None:
        if not self._active or self._imu_provenance is None:
            return
        try:
            observation = normalize_imu(message, self._imu_provenance)
            self._admit_and_retain(observation)
        except (
            PerceptionConfigurationError,
            ValueError,
            WorldModelValidationError,
            WorkingMemoryConfigurationError,
        ) as error:
            self._warn_bounded('invalid', str(error))

    def _on_image(self, message: Image) -> None:
        if not self._active or self._camera_provenance is None:
            return
        if self._physical_camera_adapter is not None:
            try:
                session_id = self._physical_camera_adapter.active_session_id
                source = self._physical_camera_adapter.source
                if session_id is None or source is None:
                    raise PhysicalCameraLifecycleError(
                        'physical camera callback has no active source session'
                    )
                previous_rejected = (
                    self._physical_camera_adapter.diagnostics.rejected_count
                )
                admission = self._physical_camera_adapter.submit_image(
                    normalize_physical_image_metadata(
                        message,
                        source,
                        session_id,
                    ),
                    now_ns=self.get_clock().now().nanoseconds,
                )
                self._handle_physical_camera_result(
                    admission,
                    previous_rejected=previous_rejected,
                )
            except (
                PerceptionConfigurationError,
                PhysicalCameraLifecycleError,
                PhysicalCameraRosAdapterError,
                PhysicalCameraValidationError,
                WorldModelValidationError,
                WorkingMemoryConfigurationError,
            ) as error:
                self._warn_bounded('invalid', str(error))
            return
        self._pending_image = message
        self._try_visual_pair()

    def _on_camera_info(self, message: CameraInfo) -> None:
        if not self._active or self._camera_provenance is None:
            return
        if self._physical_camera_adapter is not None:
            try:
                session_id = self._physical_camera_adapter.active_session_id
                source = self._physical_camera_adapter.source
                calibration = self._physical_camera_adapter.calibration
                if session_id is None or source is None or calibration is None:
                    raise PhysicalCameraLifecycleError(
                        'physical CameraInfo callback has no active calibrated session'
                    )
                previous_rejected = (
                    self._physical_camera_adapter.diagnostics.rejected_count
                )
                admission = self._physical_camera_adapter.submit_camera_info(
                    normalize_physical_camera_info_metadata(
                        message,
                        source,
                        session_id,
                        calibration,
                    ),
                    now_ns=self.get_clock().now().nanoseconds,
                )
                self._handle_physical_camera_result(
                    admission,
                    previous_rejected=previous_rejected,
                )
            except (
                PerceptionConfigurationError,
                PhysicalCameraLifecycleError,
                PhysicalCameraRosAdapterError,
                PhysicalCameraValidationError,
                WorldModelValidationError,
                WorkingMemoryConfigurationError,
            ) as error:
                self._warn_bounded('invalid', str(error))
            return
        self._pending_camera_info = message
        self._try_visual_pair()

    def _handle_physical_camera_result(
        self,
        admission,
        *,
        previous_rejected: int,
    ) -> None:
        if self._physical_camera_adapter is None:
            return
        diagnostics = self._physical_camera_adapter.diagnostics
        if admission is None:
            if diagnostics.rejected_count != previous_rejected:
                self._warn_bounded(
                    'rejected',
                    f'physical camera {diagnostics.event.value}',
                )
            return
        if self._trust_boundary is None or not self._trust_boundary.authorize_physical_camera(
            admission
        ):
            self._warn_bounded(
                'rejected',
                'sealed physical camera evidence did not match the trust policy',
            )
            return
        frame_result = self._admit_and_retain(admission.frame)
        if frame_result is None or frame_result.status is not AdmissionStatus.ACCEPTED:
            self._warn_bounded(
                'rejected',
                'sealed physical camera frame did not enter trusted state',
            )
            return
        health_result = self._admit_and_retain(admission.health)
        if health_result is None or health_result.status is not AdmissionStatus.ACCEPTED:
            self._warn_bounded(
                'rejected',
                'sealed physical camera diagnostics did not enter trusted state',
            )

    def _on_depth_image(self, message: Image) -> None:
        if not self._active or self._depth_camera_adapter is None:
            return
        try:
            session_id = self._depth_camera_adapter.active_session_id
            source = self._depth_camera_adapter.source
            if session_id is None or source is None:
                raise DepthCameraLifecycleError(
                    'depth callback has no active source session'
                )
            previous_rejected = self._depth_camera_adapter.diagnostics.rejected_count
            admission = self._depth_camera_adapter.submit_image(
                normalize_depth_image(message, source, session_id),
                now_ns=self.get_clock().now().nanoseconds,
            )
            self._handle_depth_camera_result(
                admission,
                previous_rejected=previous_rejected,
            )
        except (
            DepthCameraLifecycleError,
            DepthCameraRosAdapterError,
            DepthCameraValidationError,
            PerceptionConfigurationError,
            RgbdFusionLifecycleError,
            RgbdFusionValidationError,
            WorldModelValidationError,
            WorkingMemoryConfigurationError,
        ) as error:
            self._warn_bounded('invalid', str(error))

    def _on_depth_camera_info(self, message: CameraInfo) -> None:
        if not self._active or self._depth_camera_adapter is None:
            return
        try:
            session_id = self._depth_camera_adapter.active_session_id
            source = self._depth_camera_adapter.source
            calibration = self._depth_camera_adapter.calibration
            if session_id is None or source is None or calibration is None:
                raise DepthCameraLifecycleError(
                    'depth CameraInfo callback has no active calibrated session'
                )
            previous_rejected = self._depth_camera_adapter.diagnostics.rejected_count
            admission = self._depth_camera_adapter.submit_camera_info(
                normalize_depth_camera_info(
                    message,
                    source,
                    session_id,
                    calibration,
                ),
                now_ns=self.get_clock().now().nanoseconds,
            )
            self._handle_depth_camera_result(
                admission,
                previous_rejected=previous_rejected,
            )
        except (
            DepthCameraLifecycleError,
            DepthCameraRosAdapterError,
            DepthCameraValidationError,
            PerceptionConfigurationError,
            RgbdFusionLifecycleError,
            RgbdFusionValidationError,
            WorldModelValidationError,
            WorkingMemoryConfigurationError,
        ) as error:
            self._warn_bounded('invalid', str(error))

    def _handle_depth_camera_result(
        self,
        admission,
        *,
        previous_rejected: int,
    ) -> None:
        if self._depth_camera_adapter is None:
            return
        diagnostics = self._depth_camera_adapter.diagnostics
        if admission is None:
            if diagnostics.rejected_count != previous_rejected:
                self._warn_bounded(
                    'rejected',
                    f'depth camera {diagnostics.event.value}',
                )
            return
        if (
            self._trust_boundary is None
            or not self._trust_boundary.authorize_depth_camera(admission)
        ):
            self._warn_bounded(
                'rejected',
                'sealed depth evidence did not match the trust policy',
            )
            return
        frame_result = self._admit_and_retain(admission.frame)
        if frame_result is None or frame_result.status is not AdmissionStatus.ACCEPTED:
            self._warn_bounded(
                'rejected',
                'sealed depth frame did not enter trusted state',
            )
            return
        if self._rgbd_fusion_adapter is not None:
            previous_rgbd_rejected = (
                self._rgbd_fusion_adapter.diagnostics.rejected_count
            )
            fused = self._rgbd_fusion_adapter.submit_depth(
                admission.frame,
                now_ns=self.get_clock().now().nanoseconds,
            )
            self._handle_rgbd_fusion_result(
                fused,
                previous_rejected=previous_rgbd_rejected,
            )
        health_result = self._admit_and_retain(admission.health)
        if health_result is None or health_result.status is not AdmissionStatus.ACCEPTED:
            self._warn_bounded(
                'rejected',
                'sealed depth diagnostics did not enter trusted state',
            )

    def _handle_rgbd_fusion_result(
        self,
        admission,
        *,
        previous_rejected: int,
    ) -> None:
        if self._rgbd_fusion_adapter is None:
            return
        diagnostics = self._rgbd_fusion_adapter.diagnostics
        if admission is None:
            if diagnostics.rejected_count != previous_rejected:
                self._warn_bounded(
                    'rejected',
                    f'RGB-D fusion {diagnostics.event.value}',
                )
            return
        if (
            self._trust_boundary is None
            or not self._trust_boundary.authorize_rgbd_fusion(admission)
        ):
            self._warn_bounded(
                'rejected',
                'sealed RGB-D evidence did not match admitted components',
            )
            return
        result = self._admit_and_retain(admission.observation)
        if result is None or result.status is not AdmissionStatus.ACCEPTED:
            self._warn_bounded(
                'rejected',
                'sealed RGB-D observation did not enter trusted state',
            )

    def _evaluate_visual_frame(self, frame, rgb8: bytes) -> None:
        """Issue one sealed TEST-ONLY live result per lifecycle activation."""
        if (
            self._visual_evaluated_this_activation
            or self._visual_evaluator is None
            or self._visual_evaluation_bundle is None
            or self._visual_evaluation_report is None
            or self._trust_boundary is None
        ):
            return
        sample = VisualEvaluationSample(
            sample_id='fixture.qualified-live-frame.v1',
            sequence_index=0,
            frame=frame,
            asset_reference='live/ephemeral-not-retained.rgb8',
            asset_sha256=sha256(rgb8).hexdigest(),
            asset_size_bytes=len(rgb8),
            scenario_ids=('fixture.qualified-live-frame.v1',),
            expected_detections=(fixture_detection(frame),),
        )
        sealed = self._visual_evaluator.invoke_qualified_input(
            producer_id=self._visual_evaluation_bundle.manifest.producer.producer_id,
            evaluation_input=VisualEvaluationInput(sample=sample, rgb8=rgb8),
            policy=self._visual_evaluation_bundle.policy,
            qualified_report=self._visual_evaluation_report,
        )
        if not self._trust_boundary.authorize_evaluated_visual(sealed):
            self._warn_bounded(
                'rejected',
                'sealed visual evaluation did not bind to the admitted source',
            )
            return
        result = self._admit_and_retain(sealed.observation)
        if result is not None and result.status is AdmissionStatus.ACCEPTED:
            self._visual_evaluated_this_activation = True

    def _try_visual_pair(self) -> None:
        """Retain at most one raw image while matching exact acquisition time."""
        if (
            self._pending_image is None
            or self._pending_camera_info is None
            or self._camera_provenance is None
        ):
            return
        try:
            image_time = message_time_ns(self._pending_image)
            info_time = message_time_ns(self._pending_camera_info)
        except VisualCameraAdapterError as error:
            self._pending_image = None
            self._pending_camera_info = None
            self._warn_bounded('invalid', str(error))
            return
        if image_time < info_time:
            self._pending_image = None
            return
        if info_time < image_time:
            self._pending_camera_info = None
            return
        image = self._pending_image
        camera_info = self._pending_camera_info
        self._pending_image = None
        self._pending_camera_info = None
        try:
            observation = normalize_visual_pair(
                image,
                camera_info,
                self._camera_provenance,
            )
            admission = self._admit_and_retain(observation)
            if (
                self._rgbd_fusion_adapter is not None
                and admission is not None
                and admission.status is AdmissionStatus.ACCEPTED
            ):
                previous_rgbd_rejected = (
                    self._rgbd_fusion_adapter.diagnostics.rejected_count
                )
                fused = self._rgbd_fusion_adapter.submit_rgb(
                    admission.observation,
                    now_ns=self.get_clock().now().nanoseconds,
                )
                self._handle_rgbd_fusion_result(
                    fused,
                    previous_rejected=previous_rgbd_rejected,
                )
            if (
                self._visual_reference_adapter is not None
                and admission is not None
                and admission.status is AdmissionStatus.ACCEPTED
            ):
                interpretation = self._visual_reference_adapter.interpret(
                    admission.observation,
                    result_at_ns=max(
                        observation.observed_at_ns,
                        self.get_clock().now().nanoseconds,
                    ),
                )
                self._admit_and_retain(interpretation)
            if (
                self._visual_evaluator is not None
                and admission is not None
                and admission.status is AdmissionStatus.ACCEPTED
            ):
                self._evaluate_visual_frame(
                    admission.observation,
                    bytes(image.data),
                )
        except (
            PerceptionConfigurationError,
            RgbdFusionLifecycleError,
            RgbdFusionValidationError,
            VisualEvaluationConfigurationError,
            VisualCameraAdapterError,
            WorldModelValidationError,
            WorkingMemoryConfigurationError,
        ) as error:
            self._warn_bounded('invalid', str(error))

    def _report_pose_failure(self, failure: EvidenceFailureKind, detail: str) -> None:
        if self._trust_boundary is None or self._memory is None:
            return
        now_ns = self.get_clock().now().nanoseconds
        receipt_ns = time.monotonic_ns()
        result = self._trust_boundary.report_failure(
            sensor_id=BODY_POSE_SENSOR.sensor_id,
            failure=failure,
            observed_at_ns=now_ns,
            now_ns=now_ns,
            received_at_monotonic_ns=receipt_ns,
        )
        if result.status is AdmissionStatus.ACCEPTED:
            retained = self._memory.ingest(
                result.observation,
                now_ns=now_ns,
                received_at_monotonic_ns=receipt_ns,
            )
            if retained.status is IngestionStatus.REJECTED:
                self._warn_bounded('rejected', retained.detail)
        self._warn_bounded('invalid', f'{failure.value}: {detail}')

    def _on_localization(self, message: Odometry) -> None:
        if (
            not self._active
            or self._pose_provenance is None
            or self._pose_buffer is None
        ):
            return
        try:
            candidate = odometry_transform(message)
            normalize_localization(
                message,
                candidate,
                self._pose_provenance,
                BODY_POSE_SENSOR,
            )
            observed_at_ns = _nanoseconds(
                message.header.stamp.sec,
                message.header.stamp.nanosec,
            )
            self._pose_buffer.set_transform(
                candidate,
                self._pose_provenance.source_id,
            )
            resolved = exact_lookup(
                self._pose_buffer,
                observed_at_ns=observed_at_ns,
                timeout_ns=self._pose_lookup_timeout_ns,
            )
            observation = normalize_localization(
                message,
                resolved,
                self._pose_provenance,
                BODY_POSE_SENSOR,
            )
            admission = self._admit_and_retain(observation)
            if (
                admission is not None
                and admission.status is AdmissionStatus.REJECTED
                and admission.reason is AdmissionReason.STALE_OBSERVATION
            ):
                self._report_pose_failure(
                    EvidenceFailureKind.STALE_TRANSFORM,
                    'source transform was stale at admission',
                )
        except LocalizationAdapterError as error:
            self._report_pose_failure(error.failure, error.detail)
        except (
            PerceptionConfigurationError,
            ValueError,
            WorldModelValidationError,
            WorkingMemoryConfigurationError,
        ) as error:
            self._report_pose_failure(
                EvidenceFailureKind.MALFORMED_NUMERIC_POSE,
                str(error),
            )

    def _on_diagnostics(self, message: DiagnosticArray) -> None:
        if not self._active or self._diagnostic_provenance is None:
            return
        try:
            normalized = normalize_diagnostics(
                message,
                self._diagnostic_provenance,
                DIAGNOSTIC_COMPONENTS,
            )
            for component in normalized.ignored_components:
                self._warn_bounded(
                    'rejected',
                    f'unknown diagnostic component ignored: {component}',
                )
            for observation in normalized.observations:
                self._admit_and_retain(observation)
        except (DiagnosticAdapterError, ValueError, WorldModelValidationError) as error:
            self._warn_bounded('invalid', str(error))

    @staticmethod
    def _not_ready(response, detail: str):
        response.status = GetRobotBodyState.Response.NOT_READY
        response.detail = detail
        response.robot_id = AYYO_ROBOT_ID
        response.availability = GetRobotBodyState.Response.UNAVAILABLE
        return response

    @staticmethod
    def _availability_code(availability: SensorAvailability) -> int:
        return {
            SensorAvailability.UNAVAILABLE: GetRobotBodyState.Response.SENSOR_UNAVAILABLE,
            SensorAvailability.AVAILABLE: GetRobotBodyState.Response.SENSOR_AVAILABLE,
            SensorAvailability.DEGRADED: GetRobotBodyState.Response.SENSOR_DEGRADED,
            SensorAvailability.ERROR: GetRobotBodyState.Response.SENSOR_ERROR,
            SensorAvailability.STALE: GetRobotBodyState.Response.SENSOR_STALE,
        }[availability]

    def _handle_query(self, request, response):
        if request.robot_id != AYYO_ROBOT_ID:
            return self._not_ready(response, 'query robot identity is not canonical Ayyo')
        if (
            not self._active
            or self._memory is None
            or self._trust_boundary is None
            or self._provenance is None
        ):
            return self._not_ready(response, 'World Model observation adapter is not active')
        now_ns = self.get_clock().now().nanoseconds
        try:
            snapshot = self._memory.current_snapshot(now_ns=now_ns)
            stats = self._memory.stats(now_ns=now_ns)
            perception_stats = self._trust_boundary.stats()
        except WorkingMemoryClockRegressionError:
            self._reset_evidence_epoch()
            return self._not_ready(response, 'source clock regressed; temporary state reset')
        response.robot_id = snapshot.robot.robot_id
        _assign_time(response.queried_at, now_ns)
        response.known_joint_count = len(snapshot.robot.known_joint_names)
        response.environment_entity_count = len(snapshot.entities)
        response.recent_evidence_count = stats.recent_evidence_count
        response.current_visual_count = stats.current_visual_count
        response.current_depth_count = stats.current_depth_count
        response.current_fused_rgbd_count = stats.current_fused_rgbd_count
        response.current_visual_interpretation_count = (
            stats.current_visual_interpretation_count
        )
        response.perception_accepted_count = perception_stats.accepted_count
        response.perception_duplicate_count = perception_stats.duplicate_count
        response.perception_rejected_count = perception_stats.rejected_count
        for sensor_state in snapshot.robot.sensor_states:
            response.sensor_ids.append(sensor_state.sensor.sensor_id)
            response.sensor_kinds.append(sensor_state.sensor.kind.value)
            response.sensor_frame_ids.append(sensor_state.sensor.frame_id)
            response.sensor_availability.append(
                self._availability_code(sensor_state.availability)
            )
        health_by_sensor = {
            state.observation.sensor.sensor_id: state
            for state in snapshot.robot.sensor_health_states
        }
        for sensor_state in snapshot.robot.sensor_states:
            health = health_by_sensor.get(sensor_state.sensor.sensor_id)
            response.has_sensor_health.append(health is not None)
            if health is None:
                response.sensor_health_availability.append(
                    GetRobotBodyState.Response.SENSOR_UNAVAILABLE
                )
                response.sensor_health_freshness.append(
                    GetRobotBodyState.Response.FRESHNESS_UNKNOWN
                )
                response.sensor_health_observed_at.append(Time())
                response.sensor_health_observation_ids.append('')
                response.sensor_health_observation_fingerprints.append('')
                response.sensor_health_source_kinds.append('')
                response.sensor_health_source_ids.append('')
                response.sensor_health_source_clocks.append('')
                response.sensor_health_source_transports.append('')
                response.sensor_health_source_interfaces.append('')
                response.sensor_health_details.append('')
                continue
            observation = health.observation
            response.sensor_health_availability.append(
                self._availability_code(health.availability)
            )
            response.sensor_health_freshness.append(
                GetRobotBodyState.Response.FRESH
                if health.freshness is FreshnessState.FRESH
                else GetRobotBodyState.Response.STALE
            )
            observed_at = Time()
            _assign_time(observed_at, observation.observed_at_ns)
            response.sensor_health_observed_at.append(observed_at)
            response.sensor_health_observation_ids.append(observation.observation_id)
            response.sensor_health_observation_fingerprints.append(
                str(observation.fingerprint)
            )
            response.sensor_health_source_kinds.append(
                observation.provenance.source_kind.value
            )
            response.sensor_health_source_ids.append(
                observation.provenance.source_id
            )
            response.sensor_health_source_clocks.append(
                observation.provenance.clock.value
            )
            response.sensor_health_source_transports.append(
                observation.provenance.transport.value
            )
            response.sensor_health_source_interfaces.append(
                observation.provenance.interface
            )
            response.sensor_health_details.append(observation.evidence_detail)
        pose_sensor_state = next(
            (
                state
                for state in snapshot.robot.sensor_states
                if state.sensor == BODY_POSE_SENSOR
            ),
            None,
        )
        response.base_pose_sensor_id = BODY_POSE_SENSOR.sensor_id
        response.base_pose_availability = self._availability_code(
            SensorAvailability.UNAVAILABLE
            if pose_sensor_state is None
            else pose_sensor_state.availability
        )
        visual_sensor_state = next(
            (
                state
                for state in snapshot.robot.sensor_states
                if state.sensor == HEAD_CAMERA_SENSOR
            ),
            None,
        )
        response.visual_sensor_id = HEAD_CAMERA_SENSOR.sensor_id
        response.visual_frame_id = HEAD_CAMERA_SENSOR.frame_id
        response.visual_availability = self._availability_code(
            SensorAvailability.UNAVAILABLE
            if visual_sensor_state is None
            else visual_sensor_state.availability
        )
        depth_sensor_state = next(
            (
                state
                for state in snapshot.robot.sensor_states
                if state.sensor == HEAD_DEPTH_SENSOR
            ),
            None,
        )
        response.depth_sensor_id = HEAD_DEPTH_SENSOR.sensor_id
        response.depth_frame_id = HEAD_DEPTH_SENSOR.frame_id
        response.depth_availability = self._availability_code(
            SensorAvailability.UNAVAILABLE
            if depth_sensor_state is None
            else depth_sensor_state.availability
        )
        rgbd_sensor_state = next(
            (
                state
                for state in snapshot.robot.sensor_states
                if state.sensor == HEAD_RGBD_FUSION_SENSOR
            ),
            None,
        )
        response.rgbd_sensor_id = HEAD_RGBD_FUSION_SENSOR.sensor_id
        response.rgbd_frame_id = HEAD_RGBD_FUSION_SENSOR.frame_id
        response.rgbd_availability = self._availability_code(
            SensorAvailability.UNAVAILABLE
            if rgbd_sensor_state is None
            else rgbd_sensor_state.availability
        )
        if snapshot.robot.availability is RobotAvailability.UNAVAILABLE:
            return self._not_ready(response, 'no unexpired robot joint evidence is available')
        response.status = GetRobotBodyState.Response.READY
        response.detail = 'current body state projected from accepted observations'
        response.snapshot_id = snapshot.snapshot_id
        response.snapshot_fingerprint = str(snapshot.version)
        response.availability = (
            GetRobotBodyState.Response.AVAILABLE
            if snapshot.robot.availability is RobotAvailability.AVAILABLE
            else GetRobotBodyState.Response.PARTIAL
        )
        response.source_kind = self._provenance.source_kind.value
        response.source_id = self._provenance.source_id
        response.source_clock = self._provenance.clock.value
        response.source_transport = self._provenance.transport.value
        response.source_interface = self._provenance.interface
        for joint in snapshot.robot.joints:
            response.joint_names.append(joint.joint.joint_name)
            response.positions.append(joint.joint.position)
            response.has_velocity.append(joint.joint.velocity is not None)
            response.velocities.append(
                0.0 if joint.joint.velocity is None else joint.joint.velocity
            )
            response.has_effort.append(joint.joint.effort is not None)
            response.efforts.append(0.0 if joint.joint.effort is None else joint.joint.effort)
            time_message = Time()
            _assign_time(time_message, joint.observed_at_ns)
            response.joint_observed_at.append(time_message)
            response.joint_confidence.append(joint.confidence)
            response.joint_freshness.append(
                GetRobotBodyState.Response.FRESH
                if joint.freshness.value == 'fresh'
                else GetRobotBodyState.Response.STALE
            )
            response.joint_observation_ids.append(joint.observation_id)
        if snapshot.robot.imu_states:
            imu = snapshot.robot.imu_states[0]
            observation = imu.observation
            response.has_imu = True
            response.imu_sensor_id = observation.sensor.sensor_id
            response.imu_frame_id = observation.sensor.frame_id
            response.imu_availability = self._availability_code(imu.availability)
            response.imu_freshness = (
                GetRobotBodyState.Response.FRESH
                if imu.freshness is FreshnessState.FRESH
                else GetRobotBodyState.Response.STALE
            )
            _assign_time(response.imu_observed_at, observation.observed_at_ns)
            response.imu_observation_id = observation.observation_id
            response.imu_observation_fingerprint = str(observation.fingerprint)
            response.imu_source_kind = observation.provenance.source_kind.value
            response.imu_source_id = observation.provenance.source_id
            response.imu_source_clock = observation.provenance.clock.value
            response.imu_source_transport = observation.provenance.transport.value
            response.imu_source_interface = observation.provenance.interface
            if observation.orientation_xyzw is not None:
                response.has_imu_orientation = True
                response.imu_orientation_xyzw = list(observation.orientation_xyzw)
            if observation.orientation_covariance is not None:
                response.has_imu_orientation_covariance = True
                response.imu_orientation_covariance = list(
                    observation.orientation_covariance.values
                )
            if observation.angular_velocity_xyz is not None:
                response.has_imu_angular_velocity = True
                response.imu_angular_velocity_xyz = list(
                    observation.angular_velocity_xyz
                )
            if observation.angular_velocity_covariance is not None:
                response.has_imu_angular_velocity_covariance = True
                response.imu_angular_velocity_covariance = list(
                    observation.angular_velocity_covariance.values
                )
            if observation.linear_acceleration_xyz is not None:
                response.has_imu_linear_acceleration = True
                response.imu_linear_acceleration_xyz = list(
                    observation.linear_acceleration_xyz
                )
            if observation.linear_acceleration_covariance is not None:
                response.has_imu_linear_acceleration_covariance = True
                response.imu_linear_acceleration_covariance = list(
                    observation.linear_acceleration_covariance.values
                )
            if observation.quality is not None:
                response.has_imu_quality = True
                response.imu_quality = observation.quality
        if snapshot.robot.base_pose is not None:
            pose = snapshot.robot.base_pose
            response.has_base_pose = True
            if pose.sensor is not None:
                response.base_pose_sensor_id = pose.sensor.sensor_id
            response.base_pose_availability = self._availability_code(
                pose.availability
            )
            response.base_pose_freshness = (
                GetRobotBodyState.Response.FRESH
                if pose.freshness is FreshnessState.FRESH
                else GetRobotBodyState.Response.STALE
            )
            _assign_time(response.base_pose_observed_at, pose.observed_at_ns)
            response.base_pose_source_frame_id = pose.pose.frame_id
            response.base_pose_target_frame_id = pose.pose.child_frame_id
            response.base_pose_translation_xyz = list(pose.pose.position_xyz)
            response.base_pose_orientation_xyzw = list(pose.pose.orientation_xyzw)
            if pose.covariance is not None:
                response.has_base_pose_covariance = True
                response.base_pose_covariance = list(pose.covariance.values)
            response.base_pose_observation_id = pose.observation_id
            if pose.observation_fingerprint is not None:
                response.base_pose_observation_fingerprint = str(
                    pose.observation_fingerprint
                )
            response.base_pose_source_kind = pose.provenance.source_kind.value
            response.base_pose_source_id = pose.provenance.source_id
            response.base_pose_source_clock = pose.provenance.clock.value
            response.base_pose_source_transport = pose.provenance.transport.value
            response.base_pose_source_interface = pose.provenance.interface
            if pose.confidence is not None:
                response.has_base_pose_quality = True
                response.base_pose_quality = pose.confidence
        if snapshot.robot.visual_states:
            visual = snapshot.robot.visual_states[0]
            observation = visual.observation
            response.has_visual_frame = True
            response.visual_sensor_id = observation.sensor.sensor_id
            response.visual_frame_id = observation.sensor.frame_id
            response.visual_availability = self._availability_code(
                visual.availability
            )
            response.visual_freshness = (
                GetRobotBodyState.Response.FRESH
                if visual.freshness is FreshnessState.FRESH
                else GetRobotBodyState.Response.STALE
            )
            _assign_time(response.visual_observed_at, observation.observed_at_ns)
            response.visual_width = observation.width
            response.visual_height = observation.height
            response.visual_encoding = observation.encoding
            response.visual_step = observation.step
            response.visual_data_size_bytes = observation.data_size_bytes
            response.visual_is_bigendian = observation.is_bigendian
            response.visual_calibration_id = observation.calibration_id
            response.visual_observation_id = observation.observation_id
            response.visual_observation_fingerprint = str(observation.fingerprint)
            response.visual_source_kind = observation.provenance.source_kind.value
            response.visual_source_id = observation.provenance.source_id
            response.visual_source_clock = observation.provenance.clock.value
            response.visual_source_transport = observation.provenance.transport.value
            response.visual_source_interface = observation.provenance.interface
        if snapshot.robot.depth_states:
            depth = snapshot.robot.depth_states[0]
            observation = depth.observation
            response.has_depth_frame = True
            response.depth_sensor_id = observation.sensor.sensor_id
            response.depth_frame_id = observation.sensor.frame_id
            response.depth_availability = self._availability_code(depth.availability)
            response.depth_freshness = (
                GetRobotBodyState.Response.FRESH
                if depth.freshness is FreshnessState.FRESH
                else GetRobotBodyState.Response.STALE
            )
            _assign_time(response.depth_observed_at, observation.observed_at_ns)
            response.depth_width = observation.width
            response.depth_height = observation.height
            response.depth_encoding = observation.encoding
            response.depth_step = observation.step
            response.depth_data_size_bytes = observation.data_size_bytes
            response.depth_is_bigendian = observation.is_bigendian
            response.depth_calibration_id = observation.calibration_id
            response.depth_calibration_record_id = (
                observation.calibration_record_id
            )
            response.depth_source_manifest_id = observation.source_manifest_id
            response.depth_session_id = observation.session_id
            response.depth_valid_count = observation.valid_depth_count
            response.depth_invalid_count = observation.invalid_depth_count
            response.depth_minimum_m = observation.minimum_depth_m
            response.depth_maximum_m = observation.maximum_depth_m
            response.depth_payload_sha256 = observation.payload_sha256
            response.depth_observation_id = observation.observation_id
            response.depth_observation_fingerprint = str(observation.fingerprint)
            response.depth_source_kind = observation.provenance.source_kind.value
            response.depth_source_id = observation.provenance.source_id
            response.depth_source_clock = observation.provenance.clock.value
            response.depth_source_transport = observation.provenance.transport.value
            response.depth_source_interface = observation.provenance.interface
        if snapshot.robot.fused_rgbd_states:
            fused = snapshot.robot.fused_rgbd_states[0]
            observation = fused.observation
            rgb = observation.rgb_observation
            depth = observation.depth_observation
            response.has_fused_rgbd = True
            response.rgbd_sensor_id = observation.sensor.sensor_id
            response.rgbd_frame_id = observation.sensor.frame_id
            response.rgbd_availability = self._availability_code(
                fused.availability
            )
            response.rgbd_freshness = (
                GetRobotBodyState.Response.FRESH
                if fused.freshness is FreshnessState.FRESH
                else GetRobotBodyState.Response.STALE
            )
            _assign_time(response.rgbd_observed_at, observation.observed_at_ns)
            _assign_time(response.rgbd_result_at, observation.result_at_ns)
            response.rgbd_pair_id = observation.pair_id
            response.rgbd_pairing_policy_id = observation.pairing_policy_id
            response.rgbd_pairing_policy_version = (
                observation.pairing_policy_version
            )
            response.rgbd_synchronization_session_id = (
                observation.synchronization_session_id
            )
            response.rgbd_spatial_registration_validated = False
            response.rgbd_observation_id = observation.observation_id
            response.rgbd_observation_fingerprint = str(
                observation.fingerprint
            )
            response.rgbd_source_kind = observation.provenance.source_kind.value
            response.rgbd_source_id = observation.provenance.source_id
            response.rgbd_source_clock = observation.provenance.clock.value
            response.rgbd_source_transport = observation.provenance.transport.value
            response.rgbd_source_interface = observation.provenance.interface
            response.rgbd_rgb_observation_id = rgb.observation_id
            response.rgbd_rgb_observation_fingerprint = str(rgb.fingerprint)
            response.rgbd_rgb_producer_id = observation.rgb_producer_id
            response.rgbd_rgb_sensor_id = rgb.sensor.sensor_id
            response.rgbd_rgb_camera_frame_id = observation.rgb_camera_frame_id
            response.rgbd_rgb_optical_frame_id = rgb.sensor.frame_id
            response.rgbd_rgb_calibration_id = rgb.calibration_id
            response.rgbd_rgb_source_fingerprint_sha256 = (
                observation.rgb_source_fingerprint_sha256
            )
            response.rgbd_rgb_session_id = observation.rgb_session_id
            response.rgbd_rgb_source_kind = rgb.provenance.source_kind.value
            response.rgbd_rgb_source_id = rgb.provenance.source_id
            response.rgbd_rgb_source_clock = rgb.provenance.clock.value
            response.rgbd_rgb_source_transport = rgb.provenance.transport.value
            response.rgbd_rgb_source_interface = rgb.provenance.interface
            response.rgbd_depth_observation_id = depth.observation_id
            response.rgbd_depth_observation_fingerprint = str(
                depth.fingerprint
            )
            response.rgbd_depth_producer_id = observation.depth_producer_id
            response.rgbd_depth_sensor_id = depth.sensor.sensor_id
            response.rgbd_depth_camera_frame_id = (
                observation.depth_camera_frame_id
            )
            response.rgbd_depth_optical_frame_id = depth.sensor.frame_id
            response.rgbd_depth_calibration_id = depth.calibration_id
            response.rgbd_depth_source_fingerprint_sha256 = (
                observation.depth_source_fingerprint_sha256
            )
            response.rgbd_depth_session_id = observation.depth_session_id
            response.rgbd_depth_source_kind = depth.provenance.source_kind.value
            response.rgbd_depth_source_id = depth.provenance.source_id
            response.rgbd_depth_source_clock = depth.provenance.clock.value
            response.rgbd_depth_source_transport = (
                depth.provenance.transport.value
            )
            response.rgbd_depth_source_interface = depth.provenance.interface
        if snapshot.robot.visual_interpretation_states:
            interpretation = snapshot.robot.visual_interpretation_states[0]
            observation = interpretation.observation
            response.has_visual_interpretation = True
            response.visual_interpretation_sensor_id = observation.sensor.sensor_id
            response.visual_interpretation_reference_frame_id = (
                observation.reference_frame_id
            )
            response.visual_interpretation_availability = self._availability_code(
                interpretation.availability
            )
            response.visual_interpretation_freshness = (
                GetRobotBodyState.Response.FRESH
                if interpretation.freshness is FreshnessState.FRESH
                else GetRobotBodyState.Response.STALE
            )
            _assign_time(
                response.visual_interpretation_source_observed_at,
                observation.observed_at_ns,
            )
            _assign_time(
                response.visual_interpretation_result_at,
                observation.result_at_ns,
            )
            response.visual_interpretation_observation_id = (
                observation.observation_id
            )
            response.visual_interpretation_observation_fingerprint = str(
                observation.fingerprint
            )
            response.visual_interpretation_source_visual_observation_id = (
                observation.source_visual_observation_id
            )
            response.visual_interpretation_source_visual_fingerprint = str(
                observation.source_visual_fingerprint
            )
            response.visual_interpretation_producer_id = (
                observation.producer.producer_id
            )
            response.visual_interpretation_producer_kind = (
                observation.producer.kind.value
            )
            response.visual_interpretation_model_id = observation.producer.model_id
            response.visual_interpretation_adapter_id = (
                observation.producer.adapter_id
            )
            response.visual_interpretation_interface = (
                observation.producer.interface
            )
            evaluation = observation.evaluation_reference
            if evaluation is not None:
                model = evaluation.model
                response.has_visual_evaluation = True
                response.visual_interpretation_producer_version = (
                    evaluation.producer_version
                )
                response.visual_interpretation_producer_implementation_sha256 = (
                    evaluation.producer_implementation_sha256
                )
                response.visual_interpretation_producer_manifest_sha256 = (
                    evaluation.producer_manifest_sha256
                )
                response.visual_interpretation_model_version = model.model_version
                response.visual_interpretation_model_artifact_sha256 = (
                    model.artifact_sha256
                )
                response.visual_interpretation_model_format = model.model_format.value
                response.visual_interpretation_model_capability = (
                    model.capability.value
                )
                response.visual_interpretation_model_configuration_sha256 = (
                    model.configuration_sha256
                )
                response.visual_interpretation_model_label_schema_id = (
                    model.label_schema_id
                )
                response.visual_interpretation_model_label_schema_version = (
                    model.label_schema_version
                )
                response.visual_interpretation_model_source_classification = (
                    model.source_classification.value
                )
                response.visual_interpretation_model_has_build_export_id = (
                    model.build_export_id is not None
                )
                response.visual_interpretation_model_build_export_id = (
                    '' if model.build_export_id is None else model.build_export_id
                )
                response.visual_interpretation_model_provenance_sha256 = (
                    model.provenance_sha256
                )
                response.visual_interpretation_dataset_id = evaluation.dataset_id
                response.visual_interpretation_dataset_version = (
                    evaluation.dataset_version
                )
                response.visual_interpretation_dataset_manifest_sha256 = (
                    evaluation.dataset_manifest_sha256
                )
                response.visual_interpretation_policy_id = evaluation.policy_id
                response.visual_interpretation_policy_version = (
                    evaluation.policy_version
                )
                response.visual_interpretation_policy_sha256 = (
                    evaluation.policy_sha256
                )
                response.visual_interpretation_report_semantic_sha256 = (
                    evaluation.report_semantic_sha256
                )
                response.visual_interpretation_result_schema_version = (
                    evaluation.result_schema_version
                )
                response.visual_interpretation_mechanical_decision = (
                    evaluation.decision.value
                )
            response.visual_interpretation_source_kind = (
                observation.provenance.source_kind.value
            )
            response.visual_interpretation_source_id = (
                observation.provenance.source_id
            )
            response.visual_interpretation_source_clock = (
                observation.provenance.clock.value
            )
            response.visual_interpretation_source_transport = (
                observation.provenance.transport.value
            )
            response.visual_interpretation_source_interface = (
                observation.provenance.interface
            )
            response.visual_detection_count = len(observation.detections)
            for detection in observation.detections:
                response.visual_detection_ids.append(detection.detection_id)
                response.visual_detection_categories.append(
                    detection.category.value
                )
                response.visual_detection_labels.append(detection.label)
                response.visual_detection_coordinate_spaces.append(
                    detection.region.coordinate_space.value
                )
                response.visual_detection_x_min.append(detection.region.x_min)
                response.visual_detection_y_min.append(detection.region.y_min)
                response.visual_detection_x_max.append(detection.region.x_max)
                response.visual_detection_y_max.append(detection.region.y_max)
                response.visual_detection_has_confidence.append(
                    detection.confidence is not None
                )
                response.visual_detection_confidence.append(
                    0.0 if detection.confidence is None else detection.confidence
                )
        return response


def main() -> None:
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = AyyoWorldModelNode()
    executor = SingleThreadedExecutor()
    exit_code = 0
    configured = False
    try:
        if node.trigger_configure() is not TransitionCallbackReturn.SUCCESS:
            raise RuntimeError('World Model lifecycle configure transition failed')
        configured = True
        if node.trigger_activate() is not TransitionCallbackReturn.SUCCESS:
            raise RuntimeError('World Model lifecycle activate transition failed')
        executor.add_node(node)
        executor.spin()
    except (ExternalShutdownException, KeyboardInterrupt):
        pass
    except RuntimeError as error:
        node.get_logger().error(str(error))
        exit_code = 1
    finally:
        if node._active:
            node.trigger_deactivate()
        if configured:
            node.trigger_cleanup()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
