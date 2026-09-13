from __future__ import annotations

import ast
from pathlib import Path
import tomllib

import ayyo_manipulation_simulation_execution as public_api


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "manipulation_simulation_execution"
SOURCE_ROOT = PACKAGE_ROOT / "src/ayyo_manipulation_simulation_execution"


def _trees() -> tuple[ast.AST, ...]:
    return tuple(
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in sorted(SOURCE_ROOT.glob("*.py"))
    )


def test_distribution_has_only_stage9a_and_stage9b_dependencies() -> None:
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == [
        "ayyo-manipulation-planning==0.1.0",
        "ayyo-manipulation-trajectory==0.1.0",
    ]
    assert "scripts" not in project
    assert "gui-scripts" not in project


def test_transport_neutral_core_has_no_io_ros_or_execution_imports() -> None:
    forbidden = {
        "action_msgs",
        "asyncio",
        "control_msgs",
        "controller_manager_msgs",
        "moveit",
        "os",
        "pathlib",
        "rclpy",
        "requests",
        "sensor_msgs",
        "socket",
        "subprocess",
        "threading",
        "trajectory_msgs",
    }
    imports: set[str] = set()
    broad_handlers: list[int] = []
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


def test_core_does_not_depend_on_lower_execution_or_runtime_layers() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(SOURCE_ROOT.glob("*.py"))
    )
    assert "ayyo_runtime_bridge" not in text
    assert "ayyo_simulation_control" not in text
    assert "FollowJointTrajectory" not in text


def test_public_surface_is_contract_and_evidence_only() -> None:
    required = {
        "SimulationExecutionRequest",
        "SimulationPreflightEvidence",
        "SimulationExecutionGoal",
        "SimulationExecutionObservation",
        "SimulationExecutionResult",
        "canonical_simulation_execution_artifact_json",
    }
    assert required <= set(public_api.__all__)
    assert not ({"activate", "dispatch", "execute", "publish"} & set(public_api.__all__))
