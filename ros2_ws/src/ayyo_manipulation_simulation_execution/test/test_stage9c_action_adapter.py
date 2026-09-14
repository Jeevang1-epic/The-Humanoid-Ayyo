from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from ament_index_python.packages import get_package_prefix, get_package_share_directory

from ayyo_manipulation_planning import moveit_collision_proof_from_canonical_json
from ayyo_manipulation_simulation_execution import SimulationAuthority


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE_ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_goal_mapping_is_exact_position_only() -> None:
    adapter = _load('stage9c_execution')
    goal = SimpleNamespace(
        joint_names=('a', 'b', 'c', 'd'),
        points=(
            SimpleNamespace(positions=(0.0, 0.1, 0.2, 0.3), time_from_start=0.0),
            SimpleNamespace(positions=(0.4, 0.5, 0.6, 0.7), time_from_start=2.5),
        ),
    )
    message = adapter._goal_message(goal)
    assert tuple(message.trajectory.joint_names) == goal.joint_names
    assert [tuple(point.positions) for point in message.trajectory.points] == [
        item.positions for item in goal.points
    ]
    assert all(not point.velocities for point in message.trajectory.points)
    assert all(not point.accelerations for point in message.trajectory.points)
    assert message.trajectory.points[-1].time_from_start.sec == 2
    assert message.trajectory.points[-1].time_from_start.nanosec == 500_000_000


def test_adapter_has_one_fixed_action_and_no_alternate_command_surface() -> None:
    source = (SCRIPTS / 'stage9c_execution.py').read_text(encoding='utf-8')
    assert source.count('send_goal_async(') == 1
    assert 'create_publisher' not in source
    assert 'MoveGroup' not in source
    assert 'FollowJointTrajectory' in source
    assert 'STAGE9C_ACTION_ENDPOINT' in source
    assert 'replacement' not in source.lower()
    assert "'/ayyo/localization/odometry'" in source
    assert "'/robot_description'" in source
    assert 'STAGE9C_WHOLE_BODY_JOINT_NAMES' in source
    assert 'evaluate_whole_body_stability(' in source
    assert 'wait_for_support_fixture()' in source


def test_stage9c_launch_enables_only_explicit_support_and_pose_evidence() -> None:
    source = (SCRIPTS.parent / 'launch' / 'stage9c_simulation.launch.py').read_text(
        encoding='utf-8'
    )
    assert "'enable_manipulation_support': 'true'" in source
    assert "'enable_localization': 'true'" in source
    assert "'enable_manipulation_control': 'true'" in source
    assert "'enable_development_control': 'false'" in source
    assert "'enable_world_model': 'false'" in source


def test_support_fixture_attestation_waits_for_transient_description(
    monkeypatch,
) -> None:
    adapter = _load('stage9c_execution')
    client = SimpleNamespace(_support_fixture_active=False)
    spins = 0

    def spin_once(node, timeout_sec):
        nonlocal spins
        del timeout_sec
        spins += 1
        if spins == 2:
            node._support_fixture_active = True

    monkeypatch.setattr(adapter.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(adapter.rclpy, 'spin_once', spin_once)
    assert adapter.Stage9CClient.wait_for_support_fixture(client)
    assert spins == 2


def test_final_state_observation_waits_for_correlated_convergence(monkeypatch) -> None:
    adapter = _load('stage9c_execution')
    target = (0.3, 0.4, 0.8, 0.2)
    states = iter(
        (
            SimpleNamespace(sequence=4, positions=(0.1, 0.1, 0.3, 0.1)),
            SimpleNamespace(sequence=5, positions=(0.3, 0.4, 0.781, 0.2)),
        )
    )
    client = SimpleNamespace(_state=None)

    def spin_once(node, timeout_sec):
        del timeout_sec
        node._state = next(states)

    monkeypatch.setattr(adapter.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(adapter.rclpy, 'spin_once', spin_once)
    observed = adapter.Stage9CClient.wait_for_final_state(
        client,
        sequence=3,
        target=target,
        timeout_seconds=1.0,
    )
    assert observed.sequence == 5


def test_final_state_observation_returns_latest_nonconforming_sample(
    monkeypatch,
) -> None:
    adapter = _load('stage9c_execution')
    clock = iter((0.0, 0.0, 0.5, 1.1))
    states = iter(
        (
            SimpleNamespace(sequence=4, positions=(0.1, 0.1, 0.3, 0.1)),
            SimpleNamespace(sequence=5, positions=(0.2, 0.2, 0.4, 0.1)),
        )
    )
    client = SimpleNamespace(_state=None)

    def spin_once(node, timeout_sec):
        del timeout_sec
        node._state = next(states)

    monkeypatch.setattr(adapter.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(adapter.rclpy, 'spin_once', spin_once)
    monkeypatch.setattr(adapter.time, 'monotonic', lambda: next(clock))
    observed = adapter.Stage9CClient.wait_for_final_state(
        client,
        sequence=3,
        target=(0.3, 0.4, 0.8, 0.2),
        timeout_seconds=1.0,
    )
    assert observed.sequence == 5


def test_reviewed_fixture_binds_observed_stage9a_proof() -> None:
    fixture = _load('stage9c_reviewed_fixture')
    description = Path(get_package_share_directory('ayyo_description'))
    planning = Path(get_package_share_directory('ayyo_manipulation_planning'))
    xacro = description / 'urdf/ayyo.urdf.xacro'
    srdf_path = planning / 'config/ayyo_left_arm.srdf'
    urdf = subprocess.run(
        ['xacro', str(xacro), 'use_meshes:=false', 'simulation_mode:=false'],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    planning_request = fixture.reviewed_planning_request(
        urdf,
        srdf_path.read_text(encoding='utf-8'),
    )
    executable = (
        Path(get_package_prefix('ayyo_manipulation_planning'))
        / 'lib/ayyo_manipulation_planning/moveit_planning_scene_proof'
    )
    report = subprocess.run(
        [str(executable), str(srdf_path)],
        input=urdf,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout
    proof = moveit_collision_proof_from_canonical_json(planning_request, report)
    request = fixture.reviewed_execution_request(planning_request, proof)
    assert request.authority is SimulationAuthority.DEVELOPMENT_SIMULATION_ONLY
    assert request.stage9b_handoff.status.value == (
        'eligible_for_future_simulation_handoff_review'
    )
    assert request.trajectory.points[0].positions[2].position == 0.2
    assert tuple(
        item.position for item in request.trajectory.points[-1].positions
    ) == (0.3, 0.4, 0.8, 0.2)
