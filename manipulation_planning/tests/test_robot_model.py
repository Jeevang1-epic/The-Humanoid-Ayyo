from __future__ import annotations

from dataclasses import replace
import math

import pytest

from ayyo_manipulation_planning import (
    LEFT_ARM_JOINT_NAMES,
    JointPosition,
    PlanningFailureCode,
    PlanningValidationError,
    RobotJointKind,
    build_left_arm_planning_model,
    make_joint_state,
)


EXPECTED_CHAIN = (
    ("left_shoulder_yaw_joint", RobotJointKind.REVOLUTE, -1.2, 1.2),
    ("left_shoulder_pitch_joint", RobotJointKind.REVOLUTE, -1.8, 1.8),
    ("left_upper_arm_to_elbow_joint", RobotJointKind.FIXED, None, None),
    ("left_elbow_flex_joint", RobotJointKind.REVOLUTE, 0.0, 2.2),
    ("left_wrist_yaw_joint", RobotJointKind.REVOLUTE, -1.5, 1.5),
    ("left_wrist_to_hand_joint", RobotJointKind.FIXED, None, None),
)


def test_exact_authoritative_left_arm_chain_and_limits(expanded_urdf):
    model, catalog, group = build_left_arm_planning_model(expanded_urdf)

    assert model.robot_name == "ayyo"
    assert model.root_link == "base_link"
    assert catalog.base_link == "left_shoulder_mount_link"
    assert catalog.tip_link == "left_hand_link"
    assert catalog.planning_joint_names == LEFT_ARM_JOINT_NAMES
    assert tuple((j.joint_name, j.kind, j.lower, j.upper) for j in catalog.chain_joints) == EXPECTED_CHAIN
    assert group.fixed_joint_names == (
        "left_upper_arm_to_elbow_joint",
        "left_wrist_to_hand_joint",
    )


def test_model_derivation_is_deterministic(expanded_urdf):
    assert build_left_arm_planning_model(expanded_urdf) == build_left_arm_planning_model(expanded_urdf)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('name="ayyo"', 'name="other"'),
        ('name="left_hand_link"', 'name="removed_hand_link"'),
        ('name="left_elbow_flex_joint"', 'name="removed_elbow_joint"'),
        ('<limit effort="20.0" lower="-1.2"', '<limit effort="20.0" lower="nan"'),
        ('<limit effort="20.0" lower="-1.2"', '<limit effort="20.0" lower="-1.1"'),
        ('<joint name="left_shoulder_yaw_joint" type="revolute">', '<joint name="left_shoulder_yaw_joint" type="continuous">'),
    ],
)
def test_malformed_or_substituted_robot_models_fail_closed(expanded_urdf, old, new):
    with pytest.raises(PlanningValidationError):
        build_left_arm_planning_model(expanded_urdf.replace(old, new, 1))


def test_xml_entity_declarations_are_rejected(expanded_urdf):
    malicious = '<!DOCTYPE robot [<!ENTITY x "ayyo">]>' + expanded_urdf
    with pytest.raises(PlanningValidationError) as captured:
        build_left_arm_planning_model(malicious)
    assert captured.value.code is PlanningFailureCode.MALFORMED_MODEL


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_joint_positions_fail_closed(planning_bundle, value):
    _, catalog, group, *_ = planning_bundle
    with pytest.raises(PlanningValidationError) as captured:
        make_joint_state(group, catalog, (value, 0.0, 0.2, 0.0))
    assert captured.value.code is PlanningFailureCode.NONFINITE_POSITION


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ((-1.200001, 0.0, 0.2, 0.0), PlanningFailureCode.BELOW_JOINT_LIMIT),
        ((1.200001, 0.0, 0.2, 0.0), PlanningFailureCode.ABOVE_JOINT_LIMIT),
        ((0.0, -1.800001, 0.2, 0.0), PlanningFailureCode.BELOW_JOINT_LIMIT),
        ((0.0, 1.800001, 0.2, 0.0), PlanningFailureCode.ABOVE_JOINT_LIMIT),
        ((0.0, 0.0, -0.000001, 0.0), PlanningFailureCode.BELOW_JOINT_LIMIT),
        ((0.0, 0.0, 2.200001, 0.0), PlanningFailureCode.ABOVE_JOINT_LIMIT),
        ((0.0, 0.0, 0.2, -1.500001), PlanningFailureCode.BELOW_JOINT_LIMIT),
        ((0.0, 0.0, 0.2, 1.500001), PlanningFailureCode.ABOVE_JOINT_LIMIT),
    ],
)
def test_each_authoritative_joint_limit_is_fail_closed(planning_bundle, values, code):
    _, catalog, group, *_ = planning_bundle
    with pytest.raises(PlanningValidationError) as captured:
        make_joint_state(group, catalog, values)
    assert captured.value.code is code


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("left_upper_arm_to_elbow_joint", PlanningFailureCode.FIXED_JOINT),
        ("right_shoulder_yaw_joint", PlanningFailureCode.WRONG_ARM_JOINT),
        ("invented_joint", PlanningFailureCode.UNKNOWN_JOINT),
    ],
)
def test_non_planning_joint_injection_is_classified(planning_bundle, name, code):
    _, catalog, _, start, *_ = planning_bundle
    positions = (replace(start.positions[0], joint_name=name), *start.positions[1:])
    with pytest.raises(PlanningValidationError) as captured:
        catalog.validate_positions(positions)
    assert captured.value.code is code


def test_duplicate_missing_and_reordered_joint_lists_fail_closed(planning_bundle):
    _, catalog, _, start, *_ = planning_bundle
    cases = (
        ((start.positions[0], start.positions[0], *start.positions[2:]), PlanningFailureCode.DUPLICATE_JOINT),
        (start.positions[:-1], PlanningFailureCode.MISSING_JOINT),
        ((start.positions[1], start.positions[0], *start.positions[2:]), PlanningFailureCode.JOINT_ORDER_MISMATCH),
    )
    for positions, code in cases:
        with pytest.raises(PlanningValidationError) as captured:
            catalog.validate_positions(tuple(positions))
        assert captured.value.code is code


def test_joint_position_rejects_implicit_integer(planning_bundle):
    with pytest.raises(PlanningValidationError):
        JointPosition(LEFT_ARM_JOINT_NAMES[0], 0)
