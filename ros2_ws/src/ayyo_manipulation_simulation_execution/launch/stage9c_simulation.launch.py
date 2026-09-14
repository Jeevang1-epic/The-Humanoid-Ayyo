# Copyright 2026 Ayyo Project Authors

"""Launch the explicit Stage 9C Gazebo profile without sending any goal."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    """Enable only the reviewed simulation arm controller infrastructure."""
    headless = LaunchConfiguration('headless')
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
            'enable_development_control': 'false',
            'enable_world_model': 'false',
            'enable_localization': 'true',
            'enable_camera': 'false',
            'enable_depth_camera': 'false',
        }.items(),
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                'headless',
                default_value='true',
                description='Run the explicit Stage 9C profile without Gazebo GUI.',
            ),
            simulation,
        ]
    )
