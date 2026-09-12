from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import tomllib
from xml.etree import ElementTree

import ayyo_manipulation_planning as public_api


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "manipulation_planning"
SOURCE_ROOT = PACKAGE_ROOT / "src/ayyo_manipulation_planning"
ROS_ROOT = REPOSITORY_ROOT / "ros2_ws/src/ayyo_manipulation_planning"
LOWER_PACKAGES = (
    "approval_eligibility", "policy_registry", "promotion_control",
    "learning_evaluation", "teach_mode", "developmental_scenarios",
    "memory", "memory_validation", "memory_consolidation", "personal_context",
    "working_memory", "world_model", "executive", "safety_kernel",
    "skill_manager", "runtime_bridge", "simulation_control", "perception",
    "visual_evaluation", "physical_camera", "depth_camera", "rgbd_fusion",
    "head_audio", "software_showcase",
)


def source_trees():
    return tuple(
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in SOURCE_ROOT.glob("*.py")
    )


FORBIDDEN_DYNAMIC_CALLS = {
    "__import__", "compile", "eval", "exec", "import_module", "open", "popen",
    "start", "system", "write",
}


def forbidden_dynamic_calls(tree):
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


def test_distribution_has_no_dependency_or_runtime_entrypoint():
    metadata = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())["project"]
    assert metadata["name"] == "ayyo-manipulation-planning"
    assert metadata["version"] == "0.1.0"
    assert metadata["requires-python"] == ">=3.12"
    assert metadata["dependencies"] == []
    assert "scripts" not in metadata
    assert "entry-points" not in metadata


def test_core_runtime_imports_only_reviewed_standard_library_modules():
    allowed = {
        "__future__", "dataclasses", "enum", "hashlib", "json", "math", "re",
        "typing", "unicodedata", "xml",
    }
    imports = set()
    for _, tree in source_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])
    assert imports <= allowed


def test_core_has_no_io_process_network_thread_ros_dynamic_code_or_model_loader():
    forbidden_imports = {
        "asyncio", "builtins", "concurrent", "importlib", "multiprocessing", "os",
        "pathlib", "pickle", "requests", "rclpy", "shutil", "socket", "sqlite3",
        "subprocess", "tensorflow", "threading", "torch", "urllib",
    }
    imports = set()
    calls = []
    for path, tree in source_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        calls.extend(
            (path.name, line, name)
            for line, name in forbidden_dynamic_calls(tree)
        )
    assert imports.isdisjoint(forbidden_imports)
    assert calls == []


def test_dynamic_code_guard_allows_only_reviewed_regex_compile():
    assert forbidden_dynamic_calls(ast.parse("re.compile(r\"reviewed\")")) == []

    probes = {
        "compile('pass', '<probe>', 'exec')": "compile",
        "builtins.compile('pass', '<probe>', 'exec')": "compile",
        "attacker.compile('payload')": "compile",
        "module.compile('payload')": "compile",
        "eval('payload')": "eval",
        "exec('payload')": "exec",
        "builtins.eval('payload')": "eval",
        "builtins.exec('payload')": "exec",
    }
    for source, expected in probes.items():
        assert expected in {
            name for _, name in forbidden_dynamic_calls(ast.parse(source))
        }


def test_public_surface_is_planning_evidence_only():
    required = {
        "ManipulationPlanningRequest", "ManipulationPlanEvidence",
        "ManipulationPlanningDecision", "PlanningSceneEvidence",
        "build_left_arm_planning_model", "deterministic_joint_interpolation",
        "evaluate_manipulation_plan", "canonical_manipulation_planning_artifact_json",
    }
    forbidden = {
        "activate", "command", "control", "deploy", "dispatch", "execute",
        "load_model", "move", "persist", "publish", "run", "send", "train",
    }
    assert required <= set(public_api.__all__)
    assert forbidden.isdisjoint(public_api.__all__)


def test_lower_architecture_layers_have_no_reverse_dependency():
    offenders = []
    for package in LOWER_PACKAGES:
        for source in (REPOSITORY_ROOT / package / "src").rglob("*.py"):
            if "ayyo_manipulation_planning" in source.read_text(encoding="utf-8"):
                offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
    for source in (REPOSITORY_ROOT / "ros2_ws/src").rglob("*"):
        if ROS_ROOT in source.parents or not source.is_file():
            continue
        if source.suffix in {".py", ".cpp", ".hpp", ".xml", ".txt", ".yaml"}:
            if "ayyo_manipulation_planning" in source.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
    assert offenders == []


def test_moveit_package_has_no_execution_runtime_or_controller_api():
    package = ElementTree.parse(ROS_ROOT / "package.xml").getroot()
    dependencies = {item.text for item in package if item.tag in {"depend", "exec_depend"}}
    assert dependencies == {"geometry_msgs", "moveit_core", "moveit_msgs", "shape_msgs", "srdfdom", "urdf"}
    assert dependencies.isdisjoint({
        "controller_manager", "hardware_interface", "moveit_ros_move_group",
        "moveit_ros_planning_interface", "rclcpp", "rclpy", "ros2_control",
        "trajectory_msgs",
    })
    source = (ROS_ROOT / "src/moveit_planning_scene_proof.cpp").read_text()
    forbidden_patterns = (
        r"\bexecute\s*\(", r"asyncExecute", r"FollowJointTrajectory", r"MoveGroupInterface",
        r"create_(?:publisher|subscription|service|client)", r"rclcpp::Node",
        r"controller_manager", r"hardware_interface", r"trajectory_execution",
    )
    assert [pattern for pattern in forbidden_patterns if re.search(pattern, source)] == []


def test_srdf_contains_only_left_arm_group_and_bounded_adjacent_exclusions():
    root = ElementTree.parse(ROS_ROOT / "config/ayyo_left_arm.srdf").getroot()
    groups = root.findall("group")
    assert len(groups) == 1
    assert groups[0].attrib == {"name": "left_arm"}
    assert groups[0].find("chain").attrib == {
        "base_link": "left_shoulder_mount_link",
        "tip_link": "left_hand_link",
    }
    exclusions = root.findall("disable_collisions")
    assert 1 <= len(exclusions) <= 10
    assert all(item.attrib["reason"] == "Adjacent" for item in exclusions)
    assert all(item.attrib["link1"].startswith("left_") or item.attrib["link1"] == "chest_link" for item in exclusions)
    assert all(item.attrib["link2"].startswith("left_") for item in exclusions)


def test_arm_command_interfaces_remain_disabled_and_only_neck_controller_exists():
    control = (REPOSITORY_ROOT / "ros2_ws/src/ayyo_description/urdf/ayyo_ros2_control.xacro").read_text()
    for name in public_api.LEFT_ARM_JOINT_NAMES:
        assert re.search(rf'name="{name}"\s+command_position="false"', control)
    controllers = (REPOSITORY_ROOT / "ros2_ws/src/ayyo_simulation/config/controllers.yaml").read_text()
    assert "ayyo_neck_position_controller" in controllers
    assert controllers.count("type: forward_command_controller/ForwardCommandController") == 1
    neck_command_section = controllers.rsplit("ayyo_neck_position_controller:", 1)[1]
    assert "neck_yaw_joint" in neck_command_section
    assert "left_shoulder" not in neck_command_section
    assert "left_elbow" not in neck_command_section
    assert "left_wrist" not in neck_command_section


def test_no_existing_authority_or_runtime_implementation_was_modified():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "main", "--"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.splitlines()
    allowed_prefixes = (
        "manipulation_planning/", "ros2_ws/src/ayyo_manipulation_planning/",
        "README.md", "docs/",
    )
    assert [path for path in changed if not path.startswith(allowed_prefixes)] == []


def test_no_generated_artifact_is_tracked():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPOSITORY_ROOT, check=True,
        capture_output=True, text=True, timeout=10,
    ).stdout.splitlines()
    forbidden_parts = {"__pycache__", ".pytest_cache", "build", "install", "log"}
    offenders = [
        path for path in tracked
        if forbidden_parts.intersection(Path(path).parts) or path.endswith((".pyc", ".pyo"))
    ]
    assert offenders == []
