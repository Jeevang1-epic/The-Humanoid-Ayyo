"""Display the authoritative Ayyo description in RViz without simulation."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
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
    """Build the RViz-only development launch graph."""
    use_meshes = LaunchConfiguration('use_meshes')
    use_gui = LaunchConfiguration('use_joint_state_publisher_gui')
    start_rviz = LaunchConfiguration('start_rviz')
    use_sim_time = LaunchConfiguration('use_sim_time')

    xacro_file = PathJoinSubstitution(
        [FindPackageShare('ayyo_description'), 'urdf', 'ayyo.urdf.xacro']
    )
    rviz_config = PathJoinSubstitution(
        [FindPackageShare('ayyo_description'), 'rviz', 'ayyo.rviz']
    )
    robot_description = ParameterValue(
        Command(
            [
                FindExecutable(name='xacro'),
                ' ',
                xacro_file,
                ' use_meshes:=',
                use_meshes,
                ' simulation_mode:=false',
            ]
        ),
        value_type=str,
    )
    description_parameters = {
        'robot_description': robot_description,
        'use_sim_time': use_sim_time,
    }

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                'use_meshes',
                default_value='false',
                description='Use reviewed final meshes instead of development proxies.',
            ),
            DeclareLaunchArgument(
                'use_joint_state_publisher_gui',
                default_value='false',
                description='Start the interactive joint-state development GUI.',
            ),
            DeclareLaunchArgument(
                'start_rviz',
                default_value='true',
                description='Start RViz2 with the tracked Ayyo configuration.',
            ),
            DeclareLaunchArgument(
                'use_sim_time',
                default_value='false',
                description='Use a simulation clock for ROS nodes.',
            ),
            Node(
                package='robot_state_publisher',
                executable='robot_state_publisher',
                name='ayyo_robot_state_publisher',
                output='screen',
                parameters=[description_parameters],
            ),
            Node(
                package='joint_state_publisher',
                executable='joint_state_publisher',
                name='ayyo_joint_state_publisher',
                output='screen',
                parameters=[description_parameters],
                condition=UnlessCondition(use_gui),
            ),
            Node(
                package='joint_state_publisher_gui',
                executable='joint_state_publisher_gui',
                name='ayyo_joint_state_publisher_gui',
                output='screen',
                parameters=[description_parameters],
                condition=IfCondition(use_gui),
            ),
            Node(
                package='rviz2',
                executable='rviz2',
                name='ayyo_rviz',
                output='screen',
                arguments=['-d', rviz_config],
                parameters=[{'use_sim_time': use_sim_time}],
                condition=IfCondition(start_rviz),
            ),
        ]
    )
