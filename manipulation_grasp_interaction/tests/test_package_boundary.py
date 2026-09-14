from __future__ import annotations

import ast
from pathlib import Path
import tomllib

import ayyo_manipulation_grasp_interaction as public_api


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "manipulation_grasp_interaction"
SOURCE_ROOT = PACKAGE_ROOT / "src/ayyo_manipulation_grasp_interaction"


def _trees():
    return tuple(
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in sorted(SOURCE_ROOT.glob("*.py"))
    )


def test_distribution_depends_only_on_public_stage9c_core() -> None:
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == [
        "ayyo-manipulation-simulation-execution==0.1.0"
    ]
    assert "scripts" not in project
    assert "gui-scripts" not in project


def test_transport_neutral_core_has_no_transport_or_execution_imports() -> None:
    forbidden = {
        "action_msgs",
        "asyncio",
        "control_msgs",
        "controller_manager_msgs",
        "gz",
        "nav_msgs",
        "os",
        "pathlib",
        "rclpy",
        "requests",
        "ros_gz_interfaces",
        "sensor_msgs",
        "socket",
        "subprocess",
        "threading",
        "tf2_ros",
        "trajectory_msgs",
    }
    imports = set()
    broad_handlers = []
    for tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.ExceptHandler) and (
                node.type is None
                or isinstance(node.type, ast.Name)
                and node.type.id in {"Exception", "BaseException"}
            ):
                broad_handlers.append(node.lineno)
    assert imports.isdisjoint(forbidden)
    assert broad_handlers == []


def test_lower_stage_packages_do_not_import_stage9d() -> None:
    roots = (
        "manipulation_planning/src",
        "manipulation_trajectory/src",
        "manipulation_simulation_execution/src",
        "executive/src",
        "safety_kernel/src",
        "skill_manager/src",
        "runtime_bridge/src",
    )
    for root in roots:
        for path in (REPOSITORY_ROOT / root).rglob("*.py"):
            assert "ayyo_manipulation_grasp_interaction" not in path.read_text(
                encoding="utf-8"
            )


def test_public_surface_is_evidence_only() -> None:
    required = {
        "EndEffectorContract",
        "GraspableObjectContract",
        "GraspInteractionRequest",
        "ContactEvidence",
        "HoldEvidence",
        "ReleaseEvidence",
        "GraspInteractionResult",
        "canonical_grasp_interaction_artifact_json",
    }
    assert required <= set(public_api.__all__)
    assert not ({"dispatch", "execute", "publish", "attach", "detach"} & set(public_api.__all__))
