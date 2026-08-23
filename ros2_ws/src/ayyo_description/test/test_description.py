from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / 'scripts'))

from validate_description import (  # noqa: E402
    DescriptionValidationError,
    expand_xacro,
    EXPECTED_MAJOR_FRAMES,
    parse_robot,
    validate_mesh_contract,
    validate_package,
    validate_tree,
)


@pytest.fixture(scope='module')
def proxy_xml() -> str:
    return expand_xacro(PACKAGE_ROOT / 'urdf' / 'ayyo.urdf.xacro')


@pytest.fixture(scope='module')
def proxy_robot(proxy_xml: str) -> ET.Element:
    return parse_robot(proxy_xml)


def test_complete_validation_command_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(PACKAGE_ROOT / 'scripts' / 'validate_description.py')],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        'PASS: Ayyo description (35 links, 34 joints, 18 movable, '
        '33 mesh contracts)\n'
    )


def test_default_expansion_is_byte_deterministic() -> None:
    xacro_path = PACKAGE_ROOT / 'urdf' / 'ayyo.urdf.xacro'
    assert expand_xacro(xacro_path) == expand_xacro(xacro_path)


def test_canonical_topology(proxy_robot: ET.Element) -> None:
    assert validate_tree(proxy_robot) == (35, 34, 18)


def test_expected_major_frames_are_present(proxy_robot: ET.Element) -> None:
    links = {link.get('name') for link in proxy_robot.findall('link')}
    assert EXPECTED_MAJOR_FRAMES <= links


def test_every_movable_joint_has_axis_and_limit_contract(proxy_robot: ET.Element) -> None:
    movable = [joint for joint in proxy_robot.findall('joint') if joint.get('type') != 'fixed']
    assert len(movable) == 18
    assert all(joint.find('axis') is not None for joint in movable)
    assert all(joint.find('limit') is not None for joint in movable)


def test_duplicate_link_fails_loudly(proxy_robot: ET.Element) -> None:
    duplicate = ET.fromstring(ET.tostring(proxy_robot, encoding='unicode'))
    duplicate.append(ET.Element('link', {'name': 'head_link'}))
    with pytest.raises(DescriptionValidationError, match='link names must be unique'):
        validate_tree(duplicate)


def test_self_parent_fails_loudly(proxy_robot: ET.Element) -> None:
    invalid = ET.fromstring(ET.tostring(proxy_robot, encoding='unicode'))
    joint = invalid.find('joint')
    assert joint is not None
    child = joint.find('child')
    parent = joint.find('parent')
    assert child is not None and parent is not None
    parent.set('link', child.get('link', ''))
    with pytest.raises(DescriptionValidationError, match='cannot parent a link to itself'):
        validate_tree(invalid)


def test_invalid_axis_fails_loudly(proxy_robot: ET.Element) -> None:
    invalid = ET.fromstring(ET.tostring(proxy_robot, encoding='unicode'))
    axis = invalid.find("./joint[@type='revolute']/axis")
    assert axis is not None
    axis.set('xyz', '0 0 0')
    with pytest.raises(DescriptionValidationError, match='axis cannot be zero'):
        validate_tree(invalid)


def test_absolute_asset_path_fails_loudly(proxy_robot: ET.Element) -> None:
    invalid = ET.fromstring(ET.tostring(proxy_robot, encoding='unicode'))
    geometry = invalid.find('./link/visual/geometry')
    assert geometry is not None
    geometry.clear()
    ET.SubElement(geometry, 'mesh', {'filename': '/tmp/not-portable.stl'})
    with pytest.raises(DescriptionValidationError, match='absolute local path'):
        validate_tree(invalid)


def test_proxy_mode_has_primitives_not_meshes(proxy_robot: ET.Element) -> None:
    assert proxy_robot.find('.//mesh') is None
    assert len(proxy_robot.findall('.//visual/geometry/box')) == 33
    assert len(proxy_robot.findall('.//collision/geometry/box')) == 33


def test_mesh_mode_exactly_matches_manifest() -> None:
    robot = parse_robot(
        expand_xacro(PACKAGE_ROOT / 'urdf' / 'ayyo.urdf.xacro', 'use_meshes:=true')
    )
    assert validate_mesh_contract(PACKAGE_ROOT, robot) == 33
    assert robot.find('.//visual/geometry/box') is None
    assert robot.find('.//collision/geometry/box') is None


def test_simulation_mode_is_static_and_plugin_free() -> None:
    robot = parse_robot(
        expand_xacro(
            PACKAGE_ROOT / 'urdf' / 'ayyo.urdf.xacro',
            'simulation_mode:=true',
        )
    )
    assert robot.findtext('./gazebo/static') == 'true'
    assert robot.find('.//plugin') is None
    assert robot.find('ros2_control') is None


def test_ros2_control_contract_is_dormant_and_complete(proxy_robot: ET.Element) -> None:
    source = ET.parse(PACKAGE_ROOT / 'urdf' / 'ayyo_ros2_control.xacro').getroot()
    contract_joints = {
        element.get('name')
        for element in source.iter()
        if element.tag.endswith('controlled_joint') and element.get('name')
    }
    movable_joints = {
        joint.get('name')
        for joint in proxy_robot.findall('joint')
        if joint.get('type') == 'revolute'
    }
    assert contract_joints == movable_joints
    assert proxy_robot.find('ros2_control') is None


def test_left_and_right_contracts_are_name_symmetric(proxy_robot: ET.Element) -> None:
    link_names = {link.get('name') for link in proxy_robot.findall('link')}
    joint_names = {joint.get('name') for joint in proxy_robot.findall('joint')}
    for name in link_names:
        if name and name.startswith('left_'):
            assert 'right_' + name.removeprefix('left_') in link_names
    for name in joint_names:
        if name and name.startswith('left_'):
            assert 'right_' + name.removeprefix('left_') in joint_names


def test_mesh_contract_truthfully_reports_absent_final_assets() -> None:
    contract = json.loads(
        (PACKAGE_ROOT / 'meshes' / 'mesh_contract.json').read_text(encoding='utf-8')
    )
    assert contract['status'] == 'final_assets_not_present'
    assert not list((PACKAGE_ROOT / 'meshes' / 'visual').glob('*.dae'))
    assert not list((PACKAGE_ROOT / 'meshes' / 'collision').glob('*.stl'))


def test_description_package_has_no_cognition_dependency() -> None:
    manifest = ET.parse(PACKAGE_ROOT / 'package.xml').getroot()
    dependencies = {
        element.text
        for element in manifest
        if element.tag.endswith('depend') and element.text
    }
    assert not dependencies & {
        'ayyo_executive',
        'ayyo_memory',
        'ayyo_memory_validation',
        'ayyo_personal_context',
        'ayyo_runtime_bridge',
        'ayyo_safety',
        'ayyo_skill_manager',
    }


def test_package_resources_are_declared_for_installation() -> None:
    cmake = (PACKAGE_ROOT / 'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'DIRECTORY meshes urdf' in cmake
    assert 'scripts/validate_description.py' in cmake


def test_validation_api_reports_expected_counts() -> None:
    assert validate_package(PACKAGE_ROOT) == (35, 34, 18, 33)
