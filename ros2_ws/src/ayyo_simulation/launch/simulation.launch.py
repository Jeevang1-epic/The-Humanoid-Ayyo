# Copyright 2026 Ayyo Project Authors

"""Spawn the authoritative Ayyo description in Gazebo Harmonic."""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    RegisterEventHandler,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    AndSubstitution,
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    """Build the non-actuating Gazebo development launch graph."""
    headless = LaunchConfiguration('headless')
    enable_control = LaunchConfiguration('enable_control')
    enable_development_control = LaunchConfiguration('enable_development_control')
    enable_world_model = LaunchConfiguration('enable_world_model')
    enable_localization = LaunchConfiguration('enable_localization')
    enable_camera = LaunchConfiguration('enable_camera')
    use_meshes = LaunchConfiguration('use_meshes')
    spawn_x = LaunchConfiguration('spawn_x')
    spawn_y = LaunchConfiguration('spawn_y')
    spawn_z = LaunchConfiguration('spawn_z')
    spawn_yaw = LaunchConfiguration('spawn_yaw')

    world_file = PathJoinSubstitution(
        [FindPackageShare('ayyo_simulation'), 'worlds', 'ayyo_foundation.sdf']
    )
    bridge_config = PathJoinSubstitution(
        [FindPackageShare('ayyo_simulation'), 'config', 'ros_gz_bridge.yaml']
    )
    camera_bridge_config = PathJoinSubstitution(
        [
            FindPackageShare('ayyo_simulation'),
            'config',
            'ros_gz_camera_bridge.yaml',
        ]
    )
    controller_config = PathJoinSubstitution(
        [FindPackageShare('ayyo_simulation'), 'config', 'controllers.yaml']
    )
    xacro_file = PathJoinSubstitution(
        [FindPackageShare('ayyo_description'), 'urdf', 'ayyo.urdf.xacro']
    )
    robot_description = ParameterValue(
        Command(
            [
                FindExecutable(name='xacro'),
                ' ',
                xacro_file,
                ' use_meshes:=',
                use_meshes,
                ' simulation_mode:=true simulation_static:=true',
                ' simulation_control:=',
                enable_control,
                ' simulation_localization:=',
                enable_localization,
                ' simulation_camera:=',
                enable_camera,
                ' simulation_controller_config:=',
                controller_config,
            ]
        ),
        value_type=str,
    )
    description_parameters = {
        'robot_description': robot_description,
        'use_sim_time': True,
    }
    gazebo_launch = PathJoinSubstitution(
        [FindPackageShare('ros_gz_sim'), 'launch', 'gz_sim.launch.py']
    )

    gazebo_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(gazebo_launch),
        launch_arguments={
            'gz_args': ['-r -s ', world_file],
            'on_exit_shutdown': 'true',
        }.items(),
        condition=IfCondition(headless),
    )
    gazebo_graphical = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(gazebo_launch),
        launch_arguments={
            'gz_args': ['-r ', world_file],
            'on_exit_shutdown': 'true',
        }.items(),
        condition=UnlessCondition(headless),
    )
    spawn_ayyo = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_ayyo',
        output='screen',
        parameters=[
            {
                'world': 'ayyo_foundation',
                'topic': 'robot_description',
                'name': 'ayyo',
                'allow_renaming': False,
                'x': spawn_x,
                'y': spawn_y,
                'z': spawn_z,
                'Y': spawn_yaw,
            }
        ],
    )
    joint_state_broadcaster_spawner = Node(
        package='controller_manager',
        executable='spawner',
        name='spawn_joint_state_broadcaster',
        output='screen',
        arguments=[
            'joint_state_broadcaster',
            '--controller-manager',
            '/controller_manager',
            '--controller-manager-timeout',
            '30',
            '--switch-timeout',
            '30',
        ],
        condition=IfCondition(enable_control),
    )
    position_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        name='spawn_ayyo_neck_position_controller',
        output='screen',
        arguments=[
            'ayyo_neck_position_controller',
            '--controller-manager',
            '/controller_manager',
            '--controller-manager-timeout',
            '30',
            '--switch-timeout',
            '30',
        ],
        condition=IfCondition(enable_control),
    )
    development_control_node = Node(
        package='ayyo_simulation_control',
        executable='simulation_control_node.py',
        name='ayyo_simulation_control',
        output='screen',
        parameters=[
            description_parameters,
            {'development_injection_enabled': True},
        ],
        condition=IfCondition(
            AndSubstitution(enable_control, enable_development_control)
        ),
    )
    world_model_node = Node(
        package='ayyo_world_model',
        executable='world_model_node.py',
        name='ayyo_world_model',
        output='screen',
        parameters=[
            description_parameters,
            {'source_profile': 'simulation_ros2_control_v1'},
        ],
        condition=IfCondition(enable_world_model),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                'headless',
                default_value='true',
                description='Run only the Gazebo server for automated smoke tests.',
            ),
            DeclareLaunchArgument(
                'use_meshes',
                default_value='false',
                description='Use reviewed final meshes instead of development proxies.',
            ),
            DeclareLaunchArgument(
                'enable_control',
                default_value='false',
                description=(
                    'Activate the one-joint gz_ros2_control development foundation.'
                ),
            ),
            DeclareLaunchArgument(
                'enable_development_control',
                default_value='false',
                description=(
                    'Expose the typed development-only command service; requires control.'
                ),
            ),
            DeclareLaunchArgument(
                'enable_world_model',
                default_value='false',
                description=(
                    'Activate the fixed lifecycle-managed body-state observer.'
                ),
            ),
            DeclareLaunchArgument(
                'enable_localization',
                default_value='false',
                description=(
                    'Expose simulation-only ground-truth odom to base_link evidence.'
                ),
            ),
            DeclareLaunchArgument(
                'enable_camera',
                default_value='false',
                description=(
                    'Expose the simulation-only head RGB observation source.'
                ),
            ),
            DeclareLaunchArgument('spawn_x', default_value='0.0'),
            DeclareLaunchArgument('spawn_y', default_value='0.0'),
            DeclareLaunchArgument(
                'spawn_z',
                default_value='0.95',
                description='Base-link height that places proxy feet on the ground.',
            ),
            DeclareLaunchArgument('spawn_yaw', default_value='0.0'),
            gazebo_server,
            gazebo_graphical,
            Node(
                package='robot_state_publisher',
                executable='robot_state_publisher',
                name='ayyo_sim_robot_state_publisher',
                output='screen',
                parameters=[description_parameters],
            ),
            world_model_node,
            Node(
                package='joint_state_publisher',
                executable='joint_state_publisher',
                name='ayyo_sim_joint_state_publisher',
                output='screen',
                parameters=[description_parameters],
                condition=UnlessCondition(enable_control),
            ),
            Node(
                package='ros_gz_bridge',
                executable='parameter_bridge',
                name='ayyo_clock_bridge',
                output='screen',
                parameters=[{'config_file': bridge_config}],
            ),
            Node(
                package='ros_gz_image',
                executable='image_bridge',
                name='ayyo_head_camera_image_bridge',
                output='screen',
                arguments=['/ayyo/camera/head/image_raw'],
                parameters=[{'use_sim_time': True}],
                condition=IfCondition(enable_camera),
            ),
            Node(
                package='ros_gz_bridge',
                executable='parameter_bridge',
                name='ayyo_head_camera_info_bridge',
                output='screen',
                parameters=[{'config_file': camera_bridge_config}],
                condition=IfCondition(enable_camera),
            ),
            TimerAction(period=2.0, actions=[spawn_ayyo]),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=spawn_ayyo,
                    on_exit=[joint_state_broadcaster_spawner],
                )
            ),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=joint_state_broadcaster_spawner,
                    on_exit=[position_controller_spawner],
                )
            ),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=position_controller_spawner,
                    on_exit=[development_control_node],
                )
            ),
        ]
    )
