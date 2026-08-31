# Copyright 2026 Ayyo Project Authors

"""Default-off hardware-free exact-time RGB-D fusion TEST composition."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    """Compose TEST evidence only; no simulator, driver, or motion authority."""
    enable_fixture = LaunchConfiguration('enable_head_rgbd_fusion_fixture')
    depth_profile = LaunchConfiguration('depth_camera_profile')
    fusion_profile = LaunchConfiguration('rgbd_fusion_profile')
    retention_ttl_ms = LaunchConfiguration('world_model_retention_ttl_ms')
    xacro_file = PathJoinSubstitution(
        [FindPackageShare('ayyo_description'), 'urdf', 'ayyo.urdf.xacro']
    )
    robot_description = ParameterValue(
        Command(
            [
                FindExecutable(name='xacro'),
                ' ',
                xacro_file,
                ' use_meshes:=false simulation_mode:=false',
            ]
        ),
        value_type=str,
    )
    description_parameters = {
        'robot_description': robot_description,
        'use_sim_time': False,
    }
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                'enable_head_rgbd_fusion_fixture',
                default_value='false',
                description='Enable the explicit TEST-only RGB-D source.',
            ),
            DeclareLaunchArgument(
                'depth_camera_profile',
                default_value='unconfigured',
                description='Select the exact reviewed depth TEST profile.',
            ),
            DeclareLaunchArgument(
                'rgbd_fusion_profile',
                default_value='unconfigured',
                description='Select the exact reviewed fusion TEST profile.',
            ),
            DeclareLaunchArgument(
                'world_model_retention_ttl_ms',
                default_value='2000',
                description='Bound temporary evidence retention in milliseconds.',
            ),
            Node(
                package='ayyo_world_model',
                executable='world_model_node.py',
                name='ayyo_world_model',
                output='screen',
                parameters=[
                    description_parameters,
                    {
                        'source_profile': 'depth_camera_test_fixture_v1',
                        'enable_depth_camera_adapter': enable_fixture,
                        'depth_camera_profile': depth_profile,
                        'enable_rgbd_fusion_adapter': enable_fixture,
                        'rgbd_fusion_profile': fusion_profile,
                        'retention_ttl_ms': ParameterValue(
                            retention_ttl_ms,
                            value_type=int,
                        ),
                    },
                ],
            ),
            Node(
                package='robot_state_publisher',
                executable='robot_state_publisher',
                name='ayyo_head_rgbd_robot_state_publisher',
                output='screen',
                parameters=[description_parameters],
                condition=IfCondition(enable_fixture),
            ),
            Node(
                package='joint_state_publisher',
                executable='joint_state_publisher',
                name='ayyo_head_rgbd_joint_test_fixture',
                output='screen',
                parameters=[description_parameters],
                condition=IfCondition(enable_fixture),
            ),
            Node(
                package='ayyo_world_model',
                executable='rgbd_fusion_fixture_node.py',
                name='ayyo_head_rgbd_fusion_test_fixture',
                output='screen',
                parameters=[{'use_sim_time': False}],
                condition=IfCondition(enable_fixture),
            ),
        ]
    )
