"""Authoritative URDF joint catalog and exact v1 command allowlist."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
import math
import xml.etree.ElementTree as ET

from .canonical import JSONValue
from .errors import ControlFailureCode, ControlValidationError
from .models import (
    ControlFailure,
    ControlFingerprint,
    ControlFingerprintKind,
    SimulationControlCommand,
    fingerprint_document,
    rebuild_command,
)


CONTROLLED_JOINT_ALLOWLIST = ("neck_yaw_joint",)


@dataclass(frozen=True, slots=True)
class UrdfJointContract:
    joint_name: str
    joint_type: str
    lower: float | None
    upper: float | None


@dataclass(frozen=True, slots=True, init=False)
class UrdfJointLimitCatalog:
    allowlist: tuple[str, ...]
    fingerprint: ControlFingerprint
    _joints: Mapping[str, UrdfJointContract]

    def __init__(self, robot_description: str) -> None:
        if type(robot_description) is not str or not robot_description.strip():
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "robot_description must be non-empty URDF XML",
            )
        try:
            root = ET.fromstring(robot_description)
        except ET.ParseError as error:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                f"robot_description is invalid XML: {error}",
            ) from error
        if root.tag != "robot" or not root.get("name"):
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "robot_description root must be a named robot",
            )
        joints: dict[str, UrdfJointContract] = {}
        for element in root.findall("joint"):
            name = element.get("name")
            joint_type = element.get("type")
            if not name or name in joints:
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_COMMAND,
                    "URDF joint names must be non-empty and unique",
                )
            if joint_type == "fixed":
                contract = UrdfJointContract(name, joint_type, None, None)
            elif joint_type == "revolute":
                limit = element.find("limit")
                try:
                    lower = float("nan" if limit is None else limit.get("lower", "nan"))
                    upper = float("nan" if limit is None else limit.get("upper", "nan"))
                except ValueError as error:
                    raise ControlValidationError(
                        ControlFailureCode.MALFORMED_COMMAND,
                        f"URDF limits for {name} must be numeric",
                    ) from error
                if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
                    raise ControlValidationError(
                        ControlFailureCode.MALFORMED_COMMAND,
                        f"URDF limits for {name} are invalid",
                    )
                contract = UrdfJointContract(name, joint_type, lower, upper)
            else:
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_COMMAND,
                    f"URDF joint {name} has unsupported type {joint_type!r}",
                )
            joints[name] = contract
        if not joints:
            raise ControlValidationError(
                ControlFailureCode.MALFORMED_COMMAND,
                "robot_description contains no joints",
            )
        for allowed_name in CONTROLLED_JOINT_ALLOWLIST:
            allowed = joints.get(allowed_name)
            if allowed is None or allowed.joint_type != "revolute":
                raise ControlValidationError(
                    ControlFailureCode.MALFORMED_COMMAND,
                    "the reviewed command allowlist is absent from the URDF",
                )
        document: dict[str, JSONValue] = {
            "allowlist": list(CONTROLLED_JOINT_ALLOWLIST),
            "joints": [
                {
                    "joint_name": joint.joint_name,
                    "joint_type": joint.joint_type,
                    "lower": joint.lower,
                    "upper": joint.upper,
                }
                for joint in sorted(joints.values(), key=lambda item: item.joint_name)
            ],
            "schema": "ayyo.simulation-control.urdf-limit-catalog.v1",
        }
        object.__setattr__(self, "allowlist", CONTROLLED_JOINT_ALLOWLIST)
        object.__setattr__(self, "_joints", MappingProxyType(joints))
        object.__setattr__(
            self,
            "fingerprint",
            fingerprint_document(ControlFingerprintKind.LIMIT_CATALOG, document),
        )

    @property
    def joints(self) -> tuple[UrdfJointContract, ...]:
        return tuple(sorted(self._joints.values(), key=lambda item: item.joint_name))

    def contract_for(self, joint_name: str) -> UrdfJointContract | None:
        return self._joints.get(joint_name)

    def validate(self, command: SimulationControlCommand) -> ControlFailure | None:
        command = rebuild_command(command)
        if len(command.targets) != 1:
            return ControlFailure(
                code=ControlFailureCode.JOINT_NOT_ALLOWLISTED,
                detail="Control v1 accepts exactly one reviewed joint target.",
                command=command,
            )
        target = command.targets[0]
        joint = self._joints.get(target.joint_name)
        if joint is None:
            return ControlFailure(
                code=ControlFailureCode.UNKNOWN_JOINT,
                detail=f"Joint {target.joint_name!r} is absent from the authoritative URDF.",
                command=command,
            )
        if joint.joint_type == "fixed":
            return ControlFailure(
                code=ControlFailureCode.FIXED_JOINT,
                detail=f"Joint {target.joint_name!r} is fixed and cannot be commanded.",
                command=command,
            )
        if target.joint_name not in self.allowlist:
            return ControlFailure(
                code=ControlFailureCode.JOINT_NOT_ALLOWLISTED,
                detail=f"Joint {target.joint_name!r} is not in the reviewed control allowlist.",
                command=command,
            )
        assert joint.lower is not None and joint.upper is not None
        if target.position < joint.lower:
            return ControlFailure(
                code=ControlFailureCode.BELOW_MINIMUM,
                detail=(
                    f"Target {target.position} is below the authoritative minimum "
                    f"{joint.lower} for {target.joint_name}."
                ),
                command=command,
            )
        if target.position > joint.upper:
            return ControlFailure(
                code=ControlFailureCode.ABOVE_MAXIMUM,
                detail=(
                    f"Target {target.position} is above the authoritative maximum "
                    f"{joint.upper} for {target.joint_name}."
                ),
                command=command,
            )
        return None
