#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Lifecycle-managed fixed proprioception, localization, and health adapter."""

from __future__ import annotations

import time

from ayyo_interfaces.srv import GetRobotBodyState
from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    EvidenceFailureKind,
    PerceptionClockRegressionError,
    PerceptionConfigurationError,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
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
from diagnostic_msgs.msg import DiagnosticArray
from localization_diagnostics import (
    DiagnosticAdapterError,
    DiagnosticComponentContract,
    LocalizationAdapterError,
    exact_lookup,
    normalize_diagnostics,
    normalize_localization,
    odometry_transform,
)
from nav_msgs.msg import Odometry
import rclpy
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.lifecycle import LifecycleNode, State, TransitionCallbackReturn
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Imu, JointState
from tf2_ros import Buffer


JOINT_STATE_TOPIC = '/joint_states'
IMU_TOPIC = '/ayyo/imu/data'
LOCALIZATION_TOPIC = '/ayyo/localization/odometry'
DIAGNOSTICS_TOPIC = '/diagnostics'
QUERY_SERVICE = '/ayyo/world_model/get_robot_body_state'
SIMULATION_SOURCE_PROFILE = 'simulation_ros2_control_v1'
PHYSICAL_SOURCE_PROFILE = 'physical_ros2_control_v1'
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
        self._memory: WorkingMemory | None = None
        self._trust_boundary: PerceptionTrustBoundary | None = None
        self._provenance: ObservationProvenance | None = None
        self._imu_provenance: ObservationProvenance | None = None
        self._pose_provenance: ObservationProvenance | None = None
        self._diagnostic_provenance: ObservationProvenance | None = None
        self._joint_subscription = None
        self._imu_subscription = None
        self._localization_subscription = None
        self._diagnostics_subscription = None
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
            if (
                provenance is None
                or imu_provenance is None
                or pose_provenance is None
                or diagnostic_provenance is None
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
            self._memory = WorkingMemory(
                catalog,
                WorkingMemoryConfig(
                    robot_id=AYYO_ROBOT_ID,
                    source_clock=provenance.clock,
                    allowed_provenance=(
                        provenance,
                        imu_provenance,
                        pose_provenance,
                        diagnostic_provenance,
                    ),
                    sensors=tuple(
                        sorted(
                            (JOINT_SENSOR, IMU_SENSOR, BODY_POSE_SENSOR),
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
                ),
            )
            self._trust_boundary = PerceptionTrustBoundary(
                PerceptionTrustConfig(
                    robot_id=AYYO_ROBOT_ID,
                    source_clock=provenance.clock,
                    sources=(
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
                )
            )
            self._provenance = provenance
            self._imu_provenance = imu_provenance
            self._pose_provenance = pose_provenance
            self._diagnostic_provenance = diagnostic_provenance
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
        ):
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
        self._pose_buffer = None
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        del state
        self._active = False
        self._destroy_runtime_interfaces()
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
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        del state
        self._active = False
        self._destroy_runtime_interfaces()
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
                f'{category} proprioceptive evidence count={count}: {detail}'
            )

    def _reset_evidence_epoch(self) -> None:
        if self._trust_boundary is not None:
            self._trust_boundary.reset()
        if self._memory is not None:
            self._memory.reset()

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
