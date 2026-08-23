#!/usr/bin/env python3
"""Deterministically expand and validate the Ayyo robot description."""

from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


EXPECTED_MAJOR_FRAMES = frozenset(
    {
        'base_link',
        'pelvis_link',
        'torso_link',
        'chest_link',
        'neck_link',
        'head_link',
        'head_camera_frame',
        'left_shoulder_mount_link',
        'left_upper_arm_link',
        'left_elbow_link',
        'left_forearm_link',
        'left_wrist_link',
        'left_hand_link',
        'right_shoulder_mount_link',
        'right_upper_arm_link',
        'right_elbow_link',
        'right_forearm_link',
        'right_wrist_link',
        'right_hand_link',
        'left_hip_mount_link',
        'left_thigh_link',
        'left_knee_link',
        'left_shin_link',
        'left_ankle_link',
        'left_foot_link',
        'right_hip_mount_link',
        'right_thigh_link',
        'right_knee_link',
        'right_shin_link',
        'right_ankle_link',
        'right_foot_link',
    }
)


class DescriptionValidationError(ValueError):
    """Raised when the expanded robot description violates an invariant."""


def expand_xacro(xacro_path: Path, *mappings: str) -> str:
    executable = shutil.which('xacro')
    if executable is None:
        raise DescriptionValidationError('xacro executable is not available')
    result = subprocess.run(
        [executable, str(xacro_path), *mappings],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DescriptionValidationError(
            f'xacro expansion failed: {result.stderr.strip()}'
        )
    return result.stdout


def parse_robot(xml_text: str) -> ET.Element:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise DescriptionValidationError(f'invalid URDF XML: {error}') from error
    if root.tag != 'robot' or root.get('name') != 'ayyo':
        expected_name = repr('ayyo')
        raise DescriptionValidationError(
            f'root element must be robot name={expected_name}'
        )
    return root


def _three_finite_numbers(value: str | None) -> bool:
    if value is None:
        return False
    fields = value.split()
    if len(fields) != 3:
        return False
    try:
        return all(math.isfinite(float(field)) for field in fields)
    except ValueError:
        return False


def validate_tree(robot: ET.Element) -> tuple[int, int, int]:
    errors: list[str] = []
    links = robot.findall('link')
    joints = robot.findall('joint')
    link_names = [link.get('name', '') for link in links]
    joint_names = [joint.get('name', '') for joint in joints]

    if not link_names or any(not name for name in link_names):
        errors.append('every link must have a non-empty name')
    if len(link_names) != len(set(link_names)):
        errors.append('link names must be unique')
    if not joint_names or any(not name for name in joint_names):
        errors.append('every joint must have a non-empty name')
    if len(joint_names) != len(set(joint_names)):
        errors.append('joint names must be unique')

    link_set = set(link_names)
    missing_frames = sorted(EXPECTED_MAJOR_FRAMES - link_set)
    if missing_frames:
        missing_frame_list = ', '.join(missing_frames)
        errors.append(f'missing expected frames: {missing_frame_list}')

    parents_by_child: dict[str, list[str]] = {name: [] for name in link_names}
    children_by_parent: dict[str, list[str]] = {name: [] for name in link_names}
    movable_count = 0
    for joint in joints:
        joint_name = joint.get('name', '<unnamed>')
        parent_element = joint.find('parent')
        child_element = joint.find('child')
        parent = None if parent_element is None else parent_element.get('link')
        child = None if child_element is None else child_element.get('link')
        if parent not in link_set or child not in link_set:
            errors.append(f'{joint_name} has an unknown parent or child')
            continue
        if parent == child:
            errors.append(f'{joint_name} cannot parent a link to itself')
            continue
        parents_by_child[child].append(parent)
        children_by_parent[parent].append(child)

        origin = joint.find('origin')
        if origin is None or not _three_finite_numbers(origin.get('xyz')):
            errors.append(f'{joint_name} must have a finite xyz origin')
        if origin is None or not _three_finite_numbers(origin.get('rpy')):
            errors.append(f'{joint_name} must have a finite rpy origin')

        joint_type = joint.get('type')
        if joint_type == 'fixed':
            continue
        if joint_type != 'revolute':
            errors.append(f'{joint_name} has unsupported joint type {joint_type!r}')
            continue
        movable_count += 1
        axis = joint.find('axis')
        if axis is None or not _three_finite_numbers(axis.get('xyz')):
            errors.append(f'{joint_name} must have a finite three-component axis')
        else:
            values = [float(field) for field in axis.get('xyz', '').split()]
            if math.isclose(sum(value * value for value in values), 0.0):
                errors.append(f'{joint_name} axis cannot be zero')
        limit = joint.find('limit')
        required_limit_fields = ('lower', 'upper', 'effort', 'velocity')
        if limit is None or any(limit.get(field) is None for field in required_limit_fields):
            errors.append(f'{joint_name} must define lower, upper, effort, and velocity')
        else:
            try:
                lower, upper, effort, velocity = (
                    float(limit.get(field, 'nan')) for field in required_limit_fields
                )
            except ValueError:
                errors.append(f'{joint_name} limits must be numeric')
            else:
                if not all(math.isfinite(value) for value in (lower, upper, effort, velocity)):
                    errors.append(f'{joint_name} limits must be finite')
                elif lower >= upper or effort <= 0.0 or velocity <= 0.0:
                    errors.append(f'{joint_name} has an invalid limit contract')

    roots = sorted(name for name, parents in parents_by_child.items() if not parents)
    if roots != ['base_link']:
        errors.append(f'canonical root must be base_link; found {roots}')
    for name, parents in parents_by_child.items():
        if name != 'base_link' and len(parents) != 1:
            errors.append(f'{name} must have exactly one parent')

    visited: set[str] = set()
    active: set[str] = set()

    def visit(link_name: str) -> None:
        if link_name in active:
            errors.append(f'cycle detected at {link_name}')
            return
        if link_name in visited:
            return
        active.add(link_name)
        for child_name in children_by_parent.get(link_name, []):
            visit(child_name)
        active.remove(link_name)
        visited.add(link_name)

    if 'base_link' in link_set:
        visit('base_link')
    unreachable = sorted(link_set - visited)
    if unreachable:
        unreachable_list = ', '.join(unreachable)
        errors.append(f'links are unreachable from base_link: {unreachable_list}')

    for element in robot.iter():
        if element.tag.startswith('{http://www.ros.org/wiki/xacro}'):
            errors.append('expanded URDF must not contain Xacro elements')
        for value in element.attrib.values():
            if value.startswith('/') or value.startswith('file://') or '/home/' in value:
                errors.append(f'absolute local path is forbidden: {value}')

    if errors:
        raise DescriptionValidationError('; '.join(errors))
    return len(links), len(joints), movable_count


def validate_mesh_contract(package_root: Path, mesh_robot: ET.Element) -> int:
    contract_path = package_root / 'meshes' / 'mesh_contract.json'
    contract = json.loads(contract_path.read_text(encoding='utf-8'))
    if contract.get('status') != 'final_assets_not_present':
        raise DescriptionValidationError('mesh contract must truthfully report missing assets')
    if contract.get('runtime_scale') != [1, 1, 1]:
        raise DescriptionValidationError('mesh runtime scale must remain one after normalization')
    parts = contract.get('parts')
    if not isinstance(parts, list) or len(parts) != len(set(parts)):
        raise DescriptionValidationError('mesh part names must be a unique list')

    visual_parts: set[str] = set()
    collision_parts: set[str] = set()
    for mesh in mesh_robot.iter('mesh'):
        filename = mesh.get('filename', '')
        if filename.startswith('package://ayyo_description/meshes/visual/'):
            visual_parts.add(Path(filename).stem)
        elif filename.startswith('package://ayyo_description/meshes/collision/'):
            collision_parts.add(Path(filename).stem)
        else:
            raise DescriptionValidationError(f'unsupported mesh URI: {filename}')
        if mesh.get('scale') != '1 1 1':
            raise DescriptionValidationError(f'mesh must use normalized scale: {filename}')
    expected_parts = set(parts)
    if visual_parts != expected_parts or collision_parts != expected_parts:
        raise DescriptionValidationError('mesh bindings must exactly match the manifest')
    return len(expected_parts)


def validate_with_urdfdom(xml_text: str) -> None:
    executable = shutil.which('check_urdf')
    if executable is None:
        raise DescriptionValidationError('check_urdf executable is not available')
    with tempfile.TemporaryDirectory(prefix='ayyo-description-') as directory:
        urdf_path = Path(directory) / 'ayyo.urdf'
        urdf_path.write_text(xml_text, encoding='utf-8')
        result = subprocess.run(
            [executable, str(urdf_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise DescriptionValidationError(
            f'urdfdom validation failed: {result.stderr.strip()}'
        )


def validate_package(package_root: Path) -> tuple[int, int, int, int]:
    xacro_path = package_root / 'urdf' / 'ayyo.urdf.xacro'
    first_expansion = expand_xacro(xacro_path)
    second_expansion = expand_xacro(xacro_path)
    if first_expansion != second_expansion:
        raise DescriptionValidationError('default Xacro expansion is not deterministic')
    proxy_robot = parse_robot(first_expansion)
    link_count, joint_count, movable_count = validate_tree(proxy_robot)
    validate_with_urdfdom(first_expansion)

    mesh_robot = parse_robot(expand_xacro(xacro_path, 'use_meshes:=true'))
    validate_tree(mesh_robot)
    mesh_count = validate_mesh_contract(package_root, mesh_robot)

    simulation_robot = parse_robot(
        expand_xacro(
            xacro_path,
            'simulation_mode:=true',
            'simulation_static:=true',
        )
    )
    validate_tree(simulation_robot)
    static = simulation_robot.find('./gazebo/static')
    if static is None or static.text != 'true':
        raise DescriptionValidationError('simulation mode must default to a static model')
    if simulation_robot.find('.//plugin') is not None:
        raise DescriptionValidationError('foundation description must not load plugins')
    if simulation_robot.find('ros2_control') is not None:
        raise DescriptionValidationError('foundation description must not activate ros2_control')
    return link_count, joint_count, movable_count, mesh_count


def main() -> int:
    package_root = Path(__file__).resolve().parents[1]
    try:
        links, joints, movable, meshes = validate_package(package_root)
    except (DescriptionValidationError, OSError, json.JSONDecodeError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print(
        'PASS: Ayyo description '
        f'({links} links, {joints} joints, {movable} movable, {meshes} mesh contracts)'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
