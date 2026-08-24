"""Authoritative robot joint catalog independent of ROS and Gazebo."""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping
import xml.etree.ElementTree as ET

from .canonical import JSONValue, sha256_document
from .errors import WorldModelFailureCode, WorldModelValidationError
from .models import JointObservation, RobotStateObservation, canonical_identifier


JOINT_LIMIT_OBSERVATION_TOLERANCE = 1e-8


@dataclass(frozen=True, slots=True)
class JointContract:
    joint_name: str
    joint_type: str
    lower: float | None
    upper: float | None
    velocity_limit: float | None
    effort_limit: float | None

    def __post_init__(self) -> None:
        canonical_identifier(self.joint_name, "catalog joint_name")
        if self.joint_type not in {"fixed", "revolute", "continuous", "prismatic"}:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                f"unsupported joint type {self.joint_type!r}",
            )
        bounded = self.joint_type in {"revolute", "prismatic"}
        if bounded != (self.lower is not None and self.upper is not None):
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "bounded joint limits are incomplete",
            )
        for value in (self.lower, self.upper, self.velocity_limit, self.effort_limit):
            if value is not None and (type(value) not in {int, float} or not math.isfinite(value)):
                raise WorldModelValidationError(
                    WorldModelFailureCode.MALFORMED_CATALOG,
                    "joint limits must be finite numbers",
                )
        if bounded and self.lower >= self.upper:  # type: ignore[operator]
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "joint lower limit must be less than upper limit",
            )
        if self.velocity_limit is not None and self.velocity_limit <= 0:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "joint velocity limit must be positive",
            )
        if self.effort_limit is not None and self.effort_limit <= 0:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "joint effort limit must be positive",
            )


class RobotJointCatalog:
    """Immutable reviewed kinematic bounds used to validate body evidence."""

    __slots__ = ("robot_id", "fingerprint", "_joints")

    def __init__(self, *, robot_id: str, joints: tuple[JointContract, ...]) -> None:
        canonical_identifier(robot_id, "catalog robot_id")
        if type(joints) is not tuple or not joints or len(joints) > 256:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "joint catalog must be a non-empty bounded tuple",
            )
        if any(type(item) is not JointContract for item in joints):
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "joint catalog entries must be JointContract values",
            )
        ordered = tuple(sorted(joints, key=lambda item: item.joint_name))
        if len({item.joint_name for item in ordered}) != len(ordered):
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "joint catalog names must be unique",
            )
        document: dict[str, JSONValue] = {
            "joints": [
                {
                    "effort_limit": item.effort_limit,
                    "joint_name": item.joint_name,
                    "joint_type": item.joint_type,
                    "lower": item.lower,
                    "upper": item.upper,
                    "velocity_limit": item.velocity_limit,
                }
                for item in ordered
            ],
            "robot_id": robot_id,
            "schema": "ayyo.world-model.joint-catalog.v1",
        }
        self.robot_id = robot_id
        self._joints: Mapping[str, JointContract] = MappingProxyType(
            {item.joint_name: item for item in ordered}
        )
        self.fingerprint = f"joint_catalog:sha256:{sha256_document(document)}"

    @classmethod
    def from_urdf(cls, *, robot_id: str, robot_description: str) -> "RobotJointCatalog":
        if type(robot_description) is not str or not robot_description.strip():
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "robot_description must be non-empty URDF XML",
            )
        try:
            root = ET.fromstring(robot_description)
        except ET.ParseError as error:
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                f"robot_description is invalid XML: {error}",
            ) from error
        if root.tag != "robot" or not root.get("name"):
            raise WorldModelValidationError(
                WorldModelFailureCode.MALFORMED_CATALOG,
                "robot_description root must be a named robot",
            )
        joints: list[JointContract] = []
        for element in root.findall("joint"):
            name = element.get("name")
            joint_type = element.get("type")
            if not name or not joint_type:
                raise WorldModelValidationError(
                    WorldModelFailureCode.MALFORMED_CATALOG,
                    "URDF joints require names and types",
                )
            limit = element.find("limit")

            def number(attribute: str, *, required: bool = False) -> float | None:
                raw = None if limit is None else limit.get(attribute)
                if raw is None:
                    if required:
                        raise WorldModelValidationError(
                            WorldModelFailureCode.MALFORMED_CATALOG,
                            f"URDF joint {name} lacks {attribute}",
                        )
                    return None
                try:
                    parsed = float(raw)
                except ValueError as error:
                    raise WorldModelValidationError(
                        WorldModelFailureCode.MALFORMED_CATALOG,
                        f"URDF joint {name} has non-numeric {attribute}",
                    ) from error
                if not math.isfinite(parsed):
                    raise WorldModelValidationError(
                        WorldModelFailureCode.MALFORMED_CATALOG,
                        f"URDF joint {name} has non-finite {attribute}",
                    )
                return parsed

            bounded = joint_type in {"revolute", "prismatic"}
            movable = joint_type != "fixed"
            joints.append(
                JointContract(
                    joint_name=name,
                    joint_type=joint_type,
                    lower=number("lower", required=bounded),
                    upper=number("upper", required=bounded),
                    velocity_limit=number("velocity", required=movable),
                    effort_limit=number("effort", required=movable),
                )
            )
        return cls(robot_id=robot_id, joints=tuple(joints))

    @property
    def joints(self) -> tuple[JointContract, ...]:
        return tuple(self._joints.values())

    @property
    def observable_joint_names(self) -> tuple[str, ...]:
        return tuple(
            item.joint_name for item in self._joints.values() if item.joint_type != "fixed"
        )

    def contract_for(self, joint_name: str) -> JointContract | None:
        return self._joints.get(joint_name)

    def validate_observation(self, observation: RobotStateObservation) -> None:
        if observation.robot_id != self.robot_id:
            raise WorldModelValidationError(
                WorldModelFailureCode.WRONG_ROBOT_IDENTITY,
                "robot observation does not belong to this World Model",
            )
        for joint in observation.joints:
            self.validate_joint(joint)

    def validate_joint(self, joint: JointObservation) -> None:
        contract = self._joints.get(joint.joint_name)
        if contract is None:
            raise WorldModelValidationError(
                WorldModelFailureCode.UNKNOWN_JOINT,
                f"joint {joint.joint_name!r} is absent from the authoritative catalog",
            )
        if contract.joint_type == "fixed":
            raise WorldModelValidationError(
                WorldModelFailureCode.FIXED_JOINT,
                f"joint {joint.joint_name!r} is fixed",
            )
        if (
            contract.lower is not None
            and joint.position < contract.lower - JOINT_LIMIT_OBSERVATION_TOLERANCE
        ):
            raise WorldModelValidationError(
                WorldModelFailureCode.JOINT_BELOW_MINIMUM,
                f"joint {joint.joint_name!r} position is below its URDF minimum",
            )
        if (
            contract.upper is not None
            and joint.position > contract.upper + JOINT_LIMIT_OBSERVATION_TOLERANCE
        ):
            raise WorldModelValidationError(
                WorldModelFailureCode.JOINT_ABOVE_MAXIMUM,
                f"joint {joint.joint_name!r} position is above its URDF maximum",
            )
        if (
            joint.velocity is not None
            and contract.velocity_limit is not None
            and abs(joint.velocity)
            > contract.velocity_limit + JOINT_LIMIT_OBSERVATION_TOLERANCE
        ):
            raise WorldModelValidationError(
                WorldModelFailureCode.JOINT_VELOCITY_EXCEEDED,
                f"joint {joint.joint_name!r} velocity exceeds its URDF limit",
            )
        if (
            joint.effort is not None
            and contract.effort_limit is not None
            and abs(joint.effort)
            > contract.effort_limit + JOINT_LIMIT_OBSERVATION_TOLERANCE
        ):
            raise WorldModelValidationError(
                WorldModelFailureCode.JOINT_EFFORT_EXCEEDED,
                f"joint {joint.joint_name!r} effort exceeds its URDF limit",
            )
