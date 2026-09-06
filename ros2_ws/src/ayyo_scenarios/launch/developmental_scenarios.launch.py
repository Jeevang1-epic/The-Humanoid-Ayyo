# Copyright 2026 Ayyo Project Authors

"""Fixed development/test launch profiles for Stage-6 scenarios."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


_PROFILES = {
    'development_control': {
        'enable_anonymous_semantic_test_fixture': 'false',
        'enable_camera': 'false',
        'enable_control': 'true',
        'enable_development_control': 'true',
        'enable_localization': 'false',
        'enable_visual_reference_interpreter': 'false',
        'enable_world_model': 'true',
    },
    'observation': {
        'enable_anonymous_semantic_test_fixture': 'true',
        'enable_camera': 'true',
        'enable_control': 'true',
        'enable_development_control': 'false',
        'enable_localization': 'true',
        'enable_visual_reference_interpreter': 'true',
        'enable_world_model': 'true',
    },
    'sensor_absence': {
        'enable_anonymous_semantic_test_fixture': 'false',
        'enable_camera': 'false',
        'enable_control': 'true',
        'enable_development_control': 'false',
        'enable_localization': 'true',
        'enable_visual_reference_interpreter': 'false',
        'enable_world_model': 'true',
    },
}


def _compose_profile(context):
    profile = LaunchConfiguration('profile').perform(context)
    if profile not in _PROFILES:
        allowed = ', '.join(sorted(_PROFILES))
        raise RuntimeError(f'profile must be one of: {allowed}')
    arguments = dict(_PROFILES[profile])
    arguments['headless'] = LaunchConfiguration('headless')
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution(
                    [
                        FindPackageShare('ayyo_simulation'),
                        'launch',
                        'simulation.launch.py',
                    ]
                )
            ),
            launch_arguments=arguments.items(),
        )
    ]


def generate_launch_description() -> LaunchDescription:
    """Compose one reviewed profile; no arbitrary topics or commands are accepted."""
    start_rviz = LaunchConfiguration('start_rviz')
    rviz_config = PathJoinSubstitution(
        [FindPackageShare('ayyo_description'), 'rviz', 'ayyo.rviz']
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                'profile',
                default_value='observation',
                description=(
                    'Fixed profile: observation, development_control, or sensor_absence.'
                ),
            ),
            DeclareLaunchArgument(
                'headless',
                default_value='true',
                description='Run the authoritative Gazebo server without its GUI.',
            ),
            DeclareLaunchArgument(
                'start_rviz',
                default_value='false',
                description='Optional manual-only RViz inspection; never automated PASS evidence.',
            ),
            OpaqueFunction(function=_compose_profile),
            Node(
                package='rviz2',
                executable='rviz2',
                name='ayyo_scenario_rviz',
                arguments=['-d', rviz_config],
                parameters=[{'use_sim_time': True}],
                output='screen',
                condition=IfCondition(start_rviz),
            ),
        ]
    )
