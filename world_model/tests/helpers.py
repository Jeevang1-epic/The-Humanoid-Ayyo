from __future__ import annotations

from ayyo_world_model import (
    AYYO_ROBOT_ID,
    JointContract,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotJointCatalog,
)


TEST_PROVENANCE = ObservationProvenance(
    source_kind=ObservationSourceKind.TEST_FIXTURE,
    source_id="test.world-model.v1",
    clock=ObservationClock.TEST_TIME,
    transport=ObservationTransport.DIRECT,
    interface="direct.robot-state.v1",
)


def catalog() -> RobotJointCatalog:
    return RobotJointCatalog(
        robot_id=AYYO_ROBOT_ID,
        joints=(
            JointContract("fixed_sensor_joint", "fixed", None, None, None, None),
            JointContract("head_pitch_joint", "revolute", -0.6, 0.6, 1.0, 4.0),
            JointContract("neck_yaw_joint", "revolute", -1.2, 1.2, 1.5, 8.0),
        ),
    )


def urdf() -> str:
    return """<?xml version='1.0'?>
<robot name='ayyo'>
  <link name='base_link'/>
  <link name='neck_link'/>
  <link name='head_link'/>
  <joint name='fixed_sensor_joint' type='fixed'>
    <parent link='base_link'/><child link='neck_link'/>
  </joint>
  <joint name='neck_yaw_joint' type='revolute'>
    <parent link='neck_link'/><child link='head_link'/>
    <limit lower='-1.2' upper='1.2' velocity='1.5' effort='8.0'/>
  </joint>
</robot>"""
