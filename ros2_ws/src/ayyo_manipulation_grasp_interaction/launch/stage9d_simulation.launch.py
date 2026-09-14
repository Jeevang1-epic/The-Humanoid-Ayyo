# Copyright 2026 Ayyo Project Authors

"""Launch the explicit, non-actuating Stage 9D Gazebo profile."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    """Add only the fixed object, contact bridge, and detached hold fixture."""
    headless = LaunchConfiguration('headless')
    package_share = FindPackageShare('ayyo_manipulation_grasp_interaction')
    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare('ayyo_simulation'), 'launch', 'simulation.launch.py']
            )
        ),
        launch_arguments={
            'headless': headless,
            'use_meshes': 'false',
            'enable_control': 'true',
            'enable_manipulation_control': 'true',
            'enable_manipulation_support': 'true',
            'enable_stage9d_grasp_contact': 'true',
            'enable_development_control': 'false',
            'enable_world_model': 'false',
            'enable_localization': 'true',
            'enable_camera': 'false',
            'enable_depth_camera': 'false',
        }.items(),
    )
    spawn_object = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_stage9d_grasp_object',
        output='screen',
        parameters=[{
            'world': 'ayyo_foundation',
            'file': PathJoinSubstitution(
                [package_share, 'models', 'stage9d_grasp_object.sdf']
            ),
            'name': 'stage9d_grasp_object',
            'allow_renaming': False,
        }],
    )
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ayyo_stage9d_grasp_bridge',
        output='screen',
        parameters=[{
            'config_file': PathJoinSubstitution(
                [package_share, 'config', 'stage9d_bridge.yaml']
            )
        }],
    )
    return LaunchDescription([
        DeclareLaunchArgument(
            'headless',
            default_value='true',
            description='Run the explicit Stage 9D profile without Gazebo GUI.',
        ),
        simulation,
        bridge,
        TimerAction(period=3.0, actions=[spawn_object]),
    ])
