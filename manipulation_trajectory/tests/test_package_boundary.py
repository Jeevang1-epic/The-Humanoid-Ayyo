from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import tomllib

import ayyo_manipulation_trajectory as public_api
from ayyo_manipulation_planning import LEFT_ARM_JOINT_NAMES


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "manipulation_trajectory"
SOURCE_ROOT = PACKAGE_ROOT / "src/ayyo_manipulation_trajectory"
LOWER_PACKAGES = (
    "approval_eligibility",
    "policy_registry",
    "promotion_control",
    "learning_evaluation",
    "teach_mode",
    "developmental_scenarios",
    "memory",
    "memory_validation",
    "memory_consolidation",
    "personal_context",
    "working_memory",
    "world_model",
    "executive",
    "safety_kernel",
    "skill_manager",
    "runtime_bridge",
    "simulation_control",
    "perception",
    "visual_evaluation",
    "physical_camera",
    "depth_camera",
    "rgbd_fusion",
    "head_audio",
    "software_showcase",
    "manipulation_planning",
)
FORBIDDEN_DYNAMIC_CALLS = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "import_module",
    "open",
    "popen",
    "run",
    "spawn",
    "start",
    "system",
    "write",
}


def source_trees() -> tuple[tuple[Path, ast.AST], ...]:
    return tuple(
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in sorted(SOURCE_ROOT.glob("*.py"))
    )


def forbidden_dynamic_calls(tree: ast.AST) -> list[tuple[int, str]]:
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
            if (
                name == "compile"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "re"
            ):
                continue
        else:
            continue
        if name in FORBIDDEN_DYNAMIC_CALLS:
            calls.append((node.lineno, name))
    return calls


def test_distribution_has_only_reviewed_upstream_contract_dependencies() -> None:
    metadata = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())["project"]
    assert metadata["name"] == "ayyo-manipulation-trajectory"
    assert metadata["version"] == "0.1.0"
    assert metadata["requires-python"] == ">=3.12"
    assert metadata["dependencies"] == [
        "ayyo-executive==0.1.0",
        "ayyo-manipulation-planning==0.1.0",
        "ayyo-safety==0.1.0",
        "ayyo-skill-manager==0.1.0",
    ]
    assert "scripts" not in metadata
    assert "gui-scripts" not in metadata
    assert "entry-points" not in metadata


def test_production_imports_only_reviewed_pure_contract_modules() -> None:
    allowed = {
        "__future__",
        "ayyo_executive",
        "ayyo_manipulation_planning",
        "ayyo_safety",
        "ayyo_skill_manager",
        "dataclasses",
        "enum",
        "hashlib",
        "json",
        "math",
        "re",
        "typing",
        "unicodedata",
    }
    imports = set()
    for _, tree in source_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])
    assert imports <= allowed
    assert "ayyo_runtime_bridge" not in imports
    assert "ayyo_simulation_control" not in imports


def test_no_io_process_network_thread_ros_persistence_or_model_loader() -> None:
    forbidden_imports = {
        "aiohttp",
        "asyncio",
        "builtins",
        "concurrent",
        "controller_manager",
        "grpc",
        "hardware_interface",
        "httpx",
        "importlib",
        "moveit",
        "moveit_commander",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "rclpy",
        "requests",
        "shutil",
        "socket",
        "sqlite3",
        "subprocess",
        "tensorflow",
        "threading",
        "torch",
        "trajectory_msgs",
        "urllib",
    }
    imports = set()
    calls = []
    broad_handlers = []
    for path, tree in source_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.ExceptHandler) and (
                node.type is None
                or isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
            ):
                broad_handlers.append((path.name, node.lineno))
        calls.extend(
            (path.name, line, name)
            for line, name in forbidden_dynamic_calls(tree)
        )
    assert imports.isdisjoint(forbidden_imports)
    assert calls == []
    assert broad_handlers == []


def test_dynamic_code_guard_exempts_exact_re_compile_only() -> None:
    assert forbidden_dynamic_calls(ast.parse('re.compile(r"reviewed")')) == []
    probes = {
        "compile('pass', '<probe>', 'exec')": "compile",
        "builtins.compile('pass', '<probe>', 'exec')": "compile",
        "attacker.compile('payload')": "compile",
        "module.compile('payload')": "compile",
        "eval('payload')": "eval",
        "exec('payload')": "exec",
    }
    for source, expected in probes.items():
        assert expected in {
            name for _, name in forbidden_dynamic_calls(ast.parse(source))
        }


def test_public_surface_is_evidence_and_eligibility_only() -> None:
    required = {
        "TrajectoryConstructionRequest",
        "TrajectoryTimingConfiguration",
        "TrajectoryPoint",
        "DeterministicJointTrajectory",
        "TrajectoryEvidence",
        "TrajectorySafetyEligibilityResult",
        "ExecutionHandoffEligibilityDecision",
        "construct_deterministic_trajectory",
        "create_trajectory_evidence",
        "evaluate_trajectory_safety_eligibility",
        "evaluate_execution_handoff_eligibility",
        "canonical_manipulation_trajectory_artifact_json",
    }
    forbidden = {
        "activate",
        "command",
        "control",
        "deploy",
        "dispatch",
        "execute",
        "load_model",
        "move",
        "persist",
        "publish",
        "run",
        "send",
        "train",
    }
    assert required <= set(public_api.__all__)
    assert forbidden.isdisjoint(public_api.__all__)
    assert len(public_api.__all__) == len(set(public_api.__all__))


def test_no_runtime_request_endpoint_or_transport_contract_is_defined() -> None:
    class_names = {
        node.name
        for _, tree in source_trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    assert class_names.isdisjoint(
        {
            "RuntimeRequest",
            "RuntimeDecision",
            "RuntimeEndpointBinding",
            "RosServiceEndpoint",
            "FollowJointTrajectory",
            "MoveGroupInterface",
        }
    )
    for _, tree in source_trees():
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert calls.isdisjoint(
            {
                "bind",
                "call_async",
                "dispatch",
                "execute",
                "move",
                "publish",
                "send_goal_async",
            }
        )


def test_lower_architecture_layers_have_no_reverse_dependency() -> None:
    offenders = []
    stage9c_root = (
        REPOSITORY_ROOT
        / "ros2_ws/src/ayyo_manipulation_simulation_execution"
    )
    stage9d_root = (
        REPOSITORY_ROOT
        / "ros2_ws/src/ayyo_manipulation_grasp_interaction"
    )
    for package in LOWER_PACKAGES:
        for source in (REPOSITORY_ROOT / package / "src").rglob("*.py"):
            if "ayyo_manipulation_trajectory" in source.read_text(encoding="utf-8"):
                offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
    for source in (REPOSITORY_ROOT / "ros2_ws/src").rglob("*"):
        if (
            stage9c_root in source.parents
            or stage9d_root in source.parents
            or not source.is_file()
        ):
            continue
        if source.suffix in {".py", ".cpp", ".hpp", ".xml", ".txt", ".yaml"}:
            if "ayyo_manipulation_trajectory" in source.read_text(
                encoding="utf-8",
                errors="ignore",
            ):
                offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
    assert offenders == []


def test_arm_commands_remain_default_off_below_explicit_stage9c_profile() -> None:
    control = (
        REPOSITORY_ROOT
        / "ros2_ws/src/ayyo_description/urdf/ayyo_ros2_control.xacro"
    ).read_text(encoding="utf-8")
    for name in LEFT_ARM_JOINT_NAMES:
        assert re.search(
            rf'name="{name}"\s+command_position="\$\{{manipulation_control\}}"',
            control,
        )
    description = (
        REPOSITORY_ROOT / "ros2_ws/src/ayyo_description/urdf/ayyo.urdf.xacro"
    ).read_text(encoding="utf-8")
    assert (
        '<xacro:arg name="simulation_manipulation_control" default="false"/>'
        in description
    )
    assert (
        '<xacro:arg name="simulation_manipulation_support" default="false"/>'
        in description
    )
    controllers = (
        REPOSITORY_ROOT / "ros2_ws/src/ayyo_simulation/config/controllers.yaml"
    ).read_text(encoding="utf-8")
    assert controllers.count(
        "type: forward_command_controller/ForwardCommandController"
    ) == 1
    command_section = controllers.rsplit("ayyo_neck_position_controller:", 1)[1]
    assert "neck_yaw_joint" in command_section
    assert "left_shoulder" not in command_section
    assert "left_elbow" not in command_section
    assert "left_wrist" not in command_section


def test_only_stage9b_or_reviewed_downstream_surfaces_are_changed() -> None:
    changed = subprocess.run(
        ["git", "diff", "--name-only", "main", "--"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.splitlines()
    allowed = (
        "manipulation_trajectory/",
        "manipulation_planning/tests/test_package_boundary.py",
        "manipulation_simulation_execution/",
        "manipulation_grasp_interaction/",
        "ros2_ws/src/ayyo_description/",
        "ros2_ws/src/ayyo_manipulation_simulation_execution/",
        "ros2_ws/src/ayyo_manipulation_grasp_interaction/",
        "ros2_ws/src/ayyo_simulation/",
        "scripts/",
        "README.md",
        "docs/",
    )
    assert [path for path in changed if not path.startswith(allowed)] == []


def test_no_generated_artifact_is_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.splitlines()
    forbidden_parts = {"__pycache__", ".pytest_cache", "build", "install", "log"}
    assert [
        path
        for path in tracked
        if forbidden_parts.intersection(Path(path).parts)
        or path.endswith((".pyc", ".pyo"))
    ] == []
