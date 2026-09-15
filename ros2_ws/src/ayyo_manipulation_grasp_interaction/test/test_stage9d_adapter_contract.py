# Copyright 2026 P. Jeevan Kumar

from __future__ import annotations

import ast
from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SIMULATION_ROOT = REPOSITORY_ROOT / 'ros2_ws/src/ayyo_simulation'


def test_ordinary_simulation_remains_default_off() -> None:
    source = (SIMULATION_ROOT / 'launch/simulation.launch.py').read_text()
    assert "'enable_stage9d_grasp_contact'" in source
    declaration = source[source.rindex("'enable_stage9d_grasp_contact'"):]
    assert "default_value='false'" in declaration[:500]
    assert 'stage9d_grasp_object' not in source
    foundation = (SIMULATION_ROOT / 'worlds/ayyo_foundation.sdf').read_text()
    assert 'gz-sim-contact-system' not in foundation
    assert 'stage9d_grasp_object' not in foundation


def test_stage9d_launch_is_explicit_and_non_actuating() -> None:
    source = (PACKAGE_ROOT / 'launch/stage9d_simulation.launch.py').read_text()
    assert "'enable_stage9d_grasp_contact': 'true'" in source
    assert "'enable_development_control': 'false'" in source
    assert "'allow_renaming': False" in source
    assert "'x': -0.07774664053275518" in source
    assert "'y': 0.19" in source
    assert "'z': 0.5757939902418903" in source
    assert "'P': 0.2" in source
    assert "'stage9d_grasp_object'" in source
    assert 'stage9d_interaction.py' not in source
    assert 'FollowJointTrajectory' not in source


def test_bridge_has_only_five_fixed_directional_seams() -> None:
    entries = yaml.safe_load(
        (PACKAGE_ROOT / 'config/stage9d_bridge.yaml').read_text(encoding='utf-8')
    )
    assert [(item['ros_topic_name'], item['direction']) for item in entries] == [
        ('/ayyo/stage9d/grasp_object/contacts', 'GZ_TO_ROS'),
        ('/ayyo/stage9d/grasp_fixture/entity_poses', 'GZ_TO_ROS'),
        ('/ayyo/stage9d/grasp_fixture/state', 'GZ_TO_ROS'),
        ('/ayyo/stage9d/grasp_fixture/attach', 'ROS_TO_GZ'),
        ('/ayyo/stage9d/grasp_fixture/detach', 'ROS_TO_GZ'),
    ]
    assert entries[0]['ros_type_name'] == 'ros_gz_interfaces/msg/Contacts'
    assert entries[0]['gz_type_name'] == 'gz.msgs.Contacts'
    assert entries[1]['ros_type_name'] == 'tf2_msgs/msg/TFMessage'
    assert entries[1]['gz_type_name'] == 'gz.msgs.Pose_V'
    assert all('/ayyo/stage9d/' in item['ros_topic_name'] for item in entries)


def test_object_sdf_is_the_one_dynamic_reviewed_primitive() -> None:
    root = ET.parse(PACKAGE_ROOT / 'models/stage9d_grasp_object.sdf').getroot()
    model = root.find('model')
    assert model is not None and model.get('name') == 'stage9d_grasp_object'
    assert model.findtext('static') == 'false'
    assert model.findtext('pose') == (
        '-0.07774664053275518 0.19 0.5757939902418903 0 0.2 0'
    )
    link = model.find("link[@name='stage9d_grasp_object_link']")
    assert link is not None
    assert link.findtext('gravity') == 'true'
    assert link.findtext('inertial/mass') == '0.05'
    collision = link.find("collision[@name='stage9d_grasp_object_collision']")
    assert collision is not None
    assert collision.findtext('geometry/box/size') == '0.03 0.03 0.02'
    sensor = link.find("sensor[@name='stage9d_grasp_contact']")
    assert sensor is not None and sensor.get('type') == 'contact'
    assert sensor.findtext('contact/topic') == (
        '/ayyo/stage9d/grasp_object/contacts'
    )
    assert root.find('.//plugin[@name="gz::sim::systems::OdometryPublisher"]') is None


def test_fixture_has_no_configurable_target_or_early_attachment() -> None:
    source = (PACKAGE_ROOT / 'src/stage9d_grasp_fixture.cpp').read_text()
    assert 'constexpr char kRobotModel[] = "ayyo"' in source
    assert 'constexpr char kPhysicalHandLink[] = "left_wrist_link"' in source
    assert 'left_wrist_link_fixed_joint_lump__left_hand_link_collision_1' in source
    assert 'constexpr char kObjectModel[] = "stage9d_grasp_object"' in source
    assert 'bool attached_{false}' in source
    assert 'fresh_contact && this->Aligned(ecm)' in source
    assert 'DetachableJoint' in source
    assert 'constexpr double kPregraspPreloadForceZ = 0.55' in source
    assert 'ExternalWorldWrenchCmd' in source
    assert 'Advertise<gz::msgs::Pose_V>(kPoseTopic)' in source
    assert 'this->EndEffectorPose(ecm)' in source
    assert 'gz::sim::worldPose(this->object_link_entity_, ecm)' in source
    assert 'pregrasp_preload_active_{true}' in source
    assert 'this->pregrasp_preload_active_ = false' in source
    assert '_sdf->Get' not in source
    assert 'RequestRemoveEntity(this->joint_entity_)' in source


def test_adapter_has_no_generic_command_or_retry_surface() -> None:
    source = (PACKAGE_ROOT / 'scripts/stage9d_interaction.py').read_text()
    tree = ast.parse(source)
    assert 'argparse' not in source
    assert 'MoveGroup' not in source
    assert 'Popen' not in source
    assert 'shell=True' not in source
    assert 'retry' not in source.lower()
    assert 'FollowJointTrajectory' not in source
    assert 'importlib' not in source
    assert 'import stage9c_execution as stage9c' in source
    assert 'stage9c.reviewed_moveit_reports(' in source
    subprocess_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == 'subprocess'
    ]
    assert len(subprocess_calls) == 1
    assert all(
        keyword.arg in {'input', 'check', 'capture_output', 'text', 'timeout'}
        for keyword in subprocess_calls[0].keywords
    )


def test_stage9c_controller_contract_is_not_duplicated_or_changed() -> None:
    package_text = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in PACKAGE_ROOT.rglob('*')
        if path.is_file()
        and 'test' not in path.parts
        and path.suffix in {'.py', '.cpp', '.yaml', '.sdf'}
    )
    assert '/ayyo_left_arm_trajectory_controller/follow_joint_trajectory' not in (
        package_text
    )
    assert 'ayyo_left_arm_trajectory_controller' not in package_text
