"""Build the exact reviewed Stage 9A collision-model identity."""

from __future__ import annotations

from hashlib import sha256
from xml.etree import ElementTree

from .errors import PlanningFailureCode, PlanningValidationError
from .models import (
    LEFT_ARM_BASE_LINK,
    LEFT_ARM_GROUP_NAME,
    LEFT_ARM_TIP_LINK,
    REVIEWED_DISABLED_COLLISION_PAIRS,
    CollisionModelIdentity,
    ManipulatorGroupIdentity,
    ManipulatorJointCatalog,
    RobotModelIdentity,
)
from .robot_model import build_left_arm_planning_model


MAX_SRDF_BYTES = 65_536


def _fail(detail: str) -> PlanningValidationError:
    return PlanningValidationError(PlanningFailureCode.MODEL_MISMATCH, detail)


def _comment_free_fingerprint(prefix: str, document: str, maximum: int) -> str:
    if type(document) is not str or not document.strip():
        raise _fail("collision-model description must be non-empty text")
    try:
        encoded = document.encode("utf-8")
    except UnicodeError as error:
        raise _fail("collision-model description must be valid UTF-8") from error
    if len(encoded) > maximum:
        raise PlanningValidationError(
            PlanningFailureCode.RESOURCE_LIMIT,
            "collision-model description exceeds its byte bound",
        )
    pieces = []
    position = 0
    while True:
        start = document.find("<!--", position)
        if start < 0:
            pieces.append(document[position:])
            break
        pieces.append(document[position:start])
        end = document.find("-->", start + 4)
        if end < 0:
            raise _fail("collision-model description contains an unterminated comment")
        position = end + 3
    normalized = "".join(pieces).encode("utf-8")
    return f"{prefix}-sha256-{sha256(normalized).hexdigest()}"


def build_reviewed_collision_model(
    robot_description: str,
    srdf_description: str,
    robot_model: RobotModelIdentity,
    joint_catalog: ManipulatorJointCatalog,
    group: ManipulatorGroupIdentity,
) -> CollisionModelIdentity:
    """Bind exact reviewed URDF, SRDF, ACM, catalog, and group semantics."""

    rebuilt_model, rebuilt_catalog, rebuilt_group = build_left_arm_planning_model(
        robot_description
    )
    if (
        rebuilt_model != robot_model
        or rebuilt_catalog != joint_catalog
        or rebuilt_group != group
    ):
        raise _fail("collision model differs from the exact planning-model identities")
    urdf_fingerprint = _comment_free_fingerprint(
        "ayyo-expanded-urdf-content",
        robot_description,
        1_048_576,
    )
    srdf_fingerprint = _comment_free_fingerprint(
        "ayyo-left-arm-srdf-content",
        srdf_description,
        MAX_SRDF_BYTES,
    )
    upper_description = srdf_description.upper()
    if "<!DOCTYPE" in upper_description or "<!ENTITY" in upper_description:
        raise _fail("SRDF document type and entity declarations are not accepted")
    try:
        root = ElementTree.fromstring(srdf_description)
    except (ElementTree.ParseError, RecursionError) as error:
        raise _fail("reviewed SRDF is malformed XML") from error
    if root.tag != "robot" or root.attrib != {"name": "ayyo"}:
        raise _fail("SRDF must describe only the reviewed Ayyo robot")
    children = list(root)
    groups = [item for item in children if item.tag == "group"]
    exclusions = [item for item in children if item.tag == "disable_collisions"]
    if len(groups) != 1 or len(children) != len(groups) + len(exclusions):
        raise _fail("SRDF contains unreviewed semantic elements")
    group_element = groups[0]
    if group_element.attrib != {"name": LEFT_ARM_GROUP_NAME}:
        raise _fail("SRDF group differs from the reviewed left arm")
    group_children = list(group_element)
    if (
        len(group_children) != 1
        or group_children[0].tag != "chain"
        or group_children[0].attrib
        != {"base_link": LEFT_ARM_BASE_LINK, "tip_link": LEFT_ARM_TIP_LINK}
    ):
        raise _fail("SRDF chain differs from the reviewed left arm")
    pairs = []
    for exclusion in exclusions:
        if set(exclusion.attrib) != {"link1", "link2", "reason"}:
            raise _fail("SRDF collision exclusion has unknown or missing fields")
        if exclusion.attrib["reason"] != "Adjacent" or list(exclusion):
            raise _fail("SRDF collision exclusion differs from reviewed semantics")
        pair = tuple(sorted((exclusion.attrib["link1"], exclusion.attrib["link2"])))
        if any(link not in robot_model.link_names for link in pair):
            raise _fail("SRDF collision exclusion names an unknown robot link")
        pairs.append(pair)
    normalized_pairs = tuple(sorted(pairs))
    if normalized_pairs != REVIEWED_DISABLED_COLLISION_PAIRS:
        raise _fail("SRDF allowed-collision semantics were substituted")
    return CollisionModelIdentity(
        robot_model_id=robot_model.robot_model_id,
        robot_model_fingerprint=robot_model.robot_model_fingerprint,
        group_id=group.group_id,
        group_fingerprint=group.group_fingerprint,
        robot_description_content_fingerprint=urdf_fingerprint,
        srdf_content_fingerprint=srdf_fingerprint,
        disabled_collision_pairs=normalized_pairs,
    )
