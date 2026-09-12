"""Derive the reviewed Stage 9A chain from an expanded Ayyo URDF."""

from __future__ import annotations

from xml.etree import ElementTree

from .canonical import MAX_DESCRIPTION_BYTES, semantic_sha256
from .errors import PlanningFailureCode, PlanningValidationError
from .models import (
    LEFT_ARM_BASE_LINK,
    LEFT_ARM_GROUP_NAME,
    LEFT_ARM_JOINT_NAMES,
    LEFT_ARM_TIP_LINK,
    ManipulatorGroupIdentity,
    ManipulatorJointCatalog,
    RobotJointKind,
    RobotJointReference,
    RobotModelIdentity,
)


DESCRIPTION_SOURCE = "ayyo-description.expanded-xacro.v1"


def _fail(detail: str) -> PlanningValidationError:
    return PlanningValidationError(PlanningFailureCode.MALFORMED_MODEL, detail)


def _vector(element: ElementTree.Element | None, attribute: str, length: int) -> tuple[float, ...]:
    raw = None if element is None else element.get(attribute)
    if raw is None:
        return tuple(0.0 for _ in range(length))
    parts = raw.split()
    if len(parts) != length:
        raise _fail(f"{attribute} must contain exactly {length} values")
    try:
        return tuple(float(item) for item in parts)
    except ValueError as error:
        raise _fail(f"{attribute} contains a non-numeric value") from error


def _required_child_attribute(
    joint: ElementTree.Element,
    child_name: str,
    attribute: str,
) -> str:
    child = joint.find(child_name)
    value = None if child is None else child.get(attribute)
    if not value:
        raise _fail(f"joint {joint.get('name')!r} has no {child_name}/{attribute}")
    return value


def _joint_reference(joint: ElementTree.Element) -> RobotJointReference:
    name = joint.get("name")
    kind_text = joint.get("type")
    if not name or kind_text not in {RobotJointKind.FIXED.value, RobotJointKind.REVOLUTE.value}:
        raise _fail("left-arm chain contains an unnamed or unsupported joint")
    kind = RobotJointKind(kind_text)
    origin = joint.find("origin")
    common = {
        "joint_name": name,
        "kind": kind,
        "parent_link": _required_child_attribute(joint, "parent", "link"),
        "child_link": _required_child_attribute(joint, "child", "link"),
        "origin_xyz": _vector(origin, "xyz", 3),
        "origin_rpy": _vector(origin, "rpy", 3),
    }
    if kind is RobotJointKind.FIXED:
        return RobotJointReference(
            **common,
            axis_xyz=None,
            lower=None,
            upper=None,
            effort=None,
            velocity=None,
        )
    limit = joint.find("limit")
    if limit is None:
        raise _fail(f"revolute joint {name!r} has no limits")
    try:
        lower = float(limit.attrib["lower"])
        upper = float(limit.attrib["upper"])
        effort = float(limit.attrib["effort"])
        velocity = float(limit.attrib["velocity"])
    except (KeyError, ValueError) as error:
        raise _fail(f"revolute joint {name!r} has malformed limits") from error
    return RobotJointReference(
        **common,
        axis_xyz=_vector(joint.find("axis"), "xyz", 3),
        lower=lower,
        upper=upper,
        effort=effort,
        velocity=velocity,
    )


def build_left_arm_planning_model(
    robot_description: str,
) -> tuple[RobotModelIdentity, ManipulatorJointCatalog, ManipulatorGroupIdentity]:
    """Build exact immutable planning identities from expanded URDF text.

    The core accepts already-expanded text. It performs no file, process, ROS,
    network, persistence, model-loading, or execution operation.
    """

    if type(robot_description) is not str or not robot_description.strip():
        raise _fail("robot description must be non-empty expanded URDF text")
    try:
        encoded = robot_description.encode("utf-8")
    except UnicodeError as error:
        raise _fail("robot description is not valid UTF-8") from error
    if len(encoded) > MAX_DESCRIPTION_BYTES:
        raise PlanningValidationError(
            PlanningFailureCode.RESOURCE_LIMIT,
            "robot description exceeds the Stage 9A byte bound",
        )
    upper_description = robot_description.upper()
    if "<!DOCTYPE" in upper_description or "<!ENTITY" in upper_description:
        raise _fail("document type and entity declarations are not accepted")
    try:
        root = ElementTree.fromstring(robot_description)
    except (ElementTree.ParseError, RecursionError) as error:
        raise _fail("robot description is malformed XML") from error
    if root.tag != "robot" or root.get("name") != "ayyo":
        raise _fail("expanded model must be the Ayyo robot")
    try:
        canonical_description = ElementTree.canonicalize(
            robot_description,
            with_comments=False,
            strip_text=True,
        )
    except (ElementTree.ParseError, TypeError, ValueError) as error:
        raise _fail("robot description cannot be canonicalized") from error

    links = root.findall("link")
    joints = root.findall("joint")
    link_names = [item.get("name") for item in links]
    joint_names = [item.get("name") for item in joints]
    if (
        not link_names
        or not joint_names
        or any(not item for item in (*link_names, *joint_names))
        or len(set(link_names)) != len(link_names)
        or len(set(joint_names)) != len(joint_names)
    ):
        raise _fail("robot link and joint names must be present and unique")

    children: dict[str, ElementTree.Element] = {}
    child_links: set[str] = set()
    for joint in joints:
        parent = _required_child_attribute(joint, "parent", "link")
        child = _required_child_attribute(joint, "child", "link")
        if parent not in link_names or child not in link_names or child in children:
            raise _fail("robot joint tree has an unknown or multiply-parented link")
        children[child] = joint
        child_links.add(child)
    roots = set(link_names) - child_links
    if roots != {"base_link"}:
        raise _fail("expanded model must have base_link as its single root")
    for candidate in link_names:
        link = candidate
        seen_ancestors = set()
        while link != "base_link":
            if link in seen_ancestors or link not in children:
                raise _fail("robot joint tree is disconnected or cyclic")
            seen_ancestors.add(link)
            link = _required_child_attribute(children[link], "parent", "link")

    chain_reversed: list[ElementTree.Element] = []
    seen = set()
    link = LEFT_ARM_TIP_LINK
    while link != LEFT_ARM_BASE_LINK:
        if link in seen or link not in children:
            raise _fail("reviewed left-arm chain is missing or cyclic")
        seen.add(link)
        joint = children[link]
        chain_reversed.append(joint)
        link = _required_child_attribute(joint, "parent", "link")
    chain = tuple(_joint_reference(item) for item in reversed(chain_reversed))

    model = RobotModelIdentity(
        robot_name="ayyo",
        root_link="base_link",
        description_source=DESCRIPTION_SOURCE,
        description_fingerprint=semantic_sha256(
            "ayyo-robot-description",
            {"canonical_expanded_urdf": canonical_description},
        ),
        link_names=tuple(link_names),
        joint_names=tuple(joint_names),
    )
    catalog = ManipulatorJointCatalog(
        robot_model=model,
        group_name=LEFT_ARM_GROUP_NAME,
        base_link=LEFT_ARM_BASE_LINK,
        tip_link=LEFT_ARM_TIP_LINK,
        chain_joints=chain,
        planning_joint_names=LEFT_ARM_JOINT_NAMES,
    )
    group = ManipulatorGroupIdentity(
        robot_model_id=model.robot_model_id,
        robot_model_fingerprint=model.robot_model_fingerprint,
        joint_catalog_id=catalog.joint_catalog_id,
        joint_catalog_fingerprint=catalog.joint_catalog_fingerprint,
        group_name=catalog.group_name,
        base_link=catalog.base_link,
        tip_link=catalog.tip_link,
        joint_names=catalog.planning_joint_names,
        fixed_joint_names=catalog.fixed_joint_names,
    )
    return model, catalog, group
