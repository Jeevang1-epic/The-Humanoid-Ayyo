from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import zipfile

import ayyo_software_showcase as public_api


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "software_showcase"
SOURCE_ROOT = PACKAGE_ROOT / "src" / "ayyo_software_showcase"
DIRECT_DEPENDENCIES = [
    "ayyo-approval-eligibility==0.1.0",
    "ayyo-developmental-scenarios==0.1.0",
    "ayyo-executive==0.1.0",
    "ayyo-learning-evaluation==0.1.0",
    "ayyo-memory-consolidation==0.1.0",
    "ayyo-memory-validation==0.1.0",
    "ayyo-perception==0.1.0",
    "ayyo-personal-context==0.1.0",
    "ayyo-policy-registry==0.1.0",
    "ayyo-promotion-control==0.1.0",
    "ayyo-runtime-bridge==0.1.0",
    "ayyo-safety==0.1.0",
    "ayyo-simulation-control==0.1.0",
    "ayyo-skill-manager==0.1.0",
    "ayyo-teach-mode==0.1.0",
    "ayyo-working-memory==0.1.0",
    "ayyo-world-model==0.1.0",
]
LOWER_PACKAGE_DIRECTORIES = (
    "approval_eligibility",
    "depth_camera",
    "developmental_scenarios",
    "executive",
    "head_audio",
    "learning_evaluation",
    "memory",
    "memory_consolidation",
    "memory_validation",
    "perception",
    "personal_context",
    "physical_camera",
    "policy_registry",
    "promotion_control",
    "rgbd_fusion",
    "runtime_bridge",
    "safety_kernel",
    "simulation_control",
    "skill_manager",
    "teach_mode",
    "visual_evaluation",
    "working_memory",
    "world_model",
)


def source_trees():
    return tuple(
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in SOURCE_ROOT.glob("*.py")
    )


def test_distribution_has_exact_reviewed_dependencies_and_one_inspection_cli():
    metadata = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text())["project"]

    assert metadata["name"] == "ayyo-software-showcase"
    assert metadata["version"] == "0.1.0"
    assert metadata["requires-python"] == ">=3.12"
    assert metadata["dependencies"] == DIRECT_DEPENDENCIES
    assert metadata["scripts"] == {
        "ayyo-showcase": "ayyo_software_showcase.cli:main"
    }


def test_source_imports_only_stdlib_local_and_reviewed_public_packages():
    allowed_roots = {
        "__future__",
        "argparse",
        "dataclasses",
        "enum",
        "hashlib",
        "json",
        "re",
        "sys",
        "typing",
        "unicodedata",
        "ayyo_approval_eligibility",
        "ayyo_developmental_scenarios",
        "ayyo_executive",
        "ayyo_learning_evaluation",
        "ayyo_memory_consolidation",
        "ayyo_memory_validation",
        "ayyo_perception",
        "ayyo_personal_context",
        "ayyo_policy_registry",
        "ayyo_promotion_control",
        "ayyo_runtime_bridge",
        "ayyo_safety",
        "ayyo_simulation_control",
        "ayyo_skill_manager",
        "ayyo_teach_mode",
        "ayyo_working_memory",
        "ayyo_world_model",
    }
    imports = set()
    for _, tree in source_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])

    assert imports <= allowed_roots


def test_all_lower_layers_and_ros_have_no_reverse_showcase_dependency():
    offenders = []
    for package in LOWER_PACKAGE_DIRECTORIES:
        for source in (REPOSITORY_ROOT / package).rglob("*"):
            if (
                source.is_file()
                and source.suffix in {".py", ".toml", ".xml", ".txt"}
                and "ayyo_software_showcase" in source.read_text(
                    encoding="utf-8", errors="ignore"
                )
            ):
                offenders.append(str(source.relative_to(REPOSITORY_ROOT)))
    for source in (REPOSITORY_ROOT / "ros2_ws" / "src").rglob("*"):
        if (
            source.is_file()
            and source.suffix in {".py", ".xml", ".txt"}
            and "ayyo_software_showcase" in source.read_text(
                encoding="utf-8", errors="ignore"
            )
        ):
            offenders.append(str(source.relative_to(REPOSITORY_ROOT)))

    assert offenders == []


def test_runtime_has_no_io_network_process_worker_dynamic_model_or_ros_imports():
    forbidden_imports = {
        "asyncio",
        "concurrent",
        "importlib",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "requests",
        "rclpy",
        "shutil",
        "socket",
        "sqlite3",
        "subprocess",
        "tensorflow",
        "threading",
        "torch",
        "urllib",
    }
    forbidden_calls = {
        "__import__",
        "compile",
        "connect",
        "eval",
        "exec",
        "import_module",
        "open",
        "popen",
        "start",
        "system",
    }
    imports = set()
    calls = []
    for path, tree in source_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                    if name == "compile":
                        continue
                else:
                    continue
                if name in forbidden_calls:
                    calls.append((path.name, node.lineno, name))

    assert imports.isdisjoint(forbidden_imports)
    assert calls == []


def test_public_surface_has_inspection_but_no_authority_or_execution_api():
    required = {
        "ShowcaseManifest",
        "ShowcaseCapability",
        "ShowcaseEvidenceReference",
        "ShowcaseCheck",
        "ShowcaseReport",
        "build_showcase_manifest",
        "generate_showcase_report",
        "canonical_showcase_artifact_json",
        "verify_showcase_report",
    }
    forbidden = {
        "activate_policy",
        "authenticate_authority",
        "deploy_policy",
        "dispatch",
        "execute_policy",
        "install_policy",
        "load_model",
        "persist",
        "run_policy",
        "train",
    }

    assert required <= set(public_api.__all__)
    assert forbidden.isdisjoint(public_api.__all__)
    assert len(public_api.__all__) == len(set(public_api.__all__))


def test_models_have_no_payload_path_active_alias_or_runtime_authority_fields():
    forbidden = {
        "active_policy",
        "alias",
        "bytecode",
        "callback",
        "command",
        "current_policy",
        "executable",
        "latest",
        "model_weights",
        "path",
        "payload",
        "python_source",
        "ros_client",
        "runtime_handle",
        "shell",
        "url",
    }
    for model in (
        public_api.ShowcaseEvidenceReference,
        public_api.ShowcaseCapability,
        public_api.ShowcaseManifest,
        public_api.ShowcaseCheck,
        public_api.ShowcaseReport,
    ):
        assert forbidden.isdisjoint(model.__annotations__)


def test_live_catalog_evidence_points_only_to_expected_public_module_roots():
    expected = {
        "ayyo_approval_eligibility",
        "ayyo_developmental_scenarios",
        "ayyo_executive",
        "ayyo_learning_evaluation",
        "ayyo_memory_consolidation",
        "ayyo_memory_validation",
        "ayyo_perception",
        "ayyo_personal_context",
        "ayyo_policy_registry",
        "ayyo_promotion_control",
        "ayyo_runtime_bridge",
        "ayyo_safety",
        "ayyo_simulation_control",
        "ayyo_skill_manager",
        "ayyo_teach_mode",
        "ayyo_working_memory",
        "ayyo_world_model",
    }
    actual = {
        item.contract_module.split(".")[0]
        for item in public_api.build_showcase_manifest().evidence
    }

    assert actual == expected


def test_wheel_contains_only_showcase_runtime_sources_and_exact_metadata():
    expected_sources = {
        "ayyo_software_showcase/__init__.py",
        "ayyo_software_showcase/canonical.py",
        "ayyo_software_showcase/catalog.py",
        "ayyo_software_showcase/cli.py",
        "ayyo_software_showcase/errors.py",
        "ayyo_software_showcase/models.py",
        "ayyo_software_showcase/report.py",
        "ayyo_software_showcase/serialization.py",
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        package_copy = root / "software_showcase"
        wheel_directory = root / "wheel"
        shutil.copytree(
            PACKAGE_ROOT,
            package_copy,
            ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", "build", "dist"),
        )
        wheel_directory.mkdir()
        result = subprocess.run(
            [
                "python3",
                "-m",
                "pip",
                "wheel",
                "--no-build-isolation",
                "--no-deps",
                "--wheel-dir",
                str(wheel_directory),
                str(package_copy),
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        wheels = tuple(wheel_directory.glob("*.whl"))
        assert len(wheels) == 1
        with zipfile.ZipFile(wheels[0]) as archive:
            names = archive.namelist()
            sources = {name for name in names if name.endswith(".py")}
            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            metadata = archive.read(metadata_name).decode("utf-8")
            entry_points_name = next(
                name for name in names if name.endswith(".dist-info/entry_points.txt")
            )
            entry_points = archive.read(entry_points_name).decode("utf-8")
        assert sources == expected_sources
        requirements = [
            line.split(":", 1)[1].strip().replace(" ", "")
            for line in metadata.splitlines()
            if line.startswith("Requires-Dist:")
        ]
        assert requirements == DIRECT_DEPENDENCIES
        assert "ayyo-showcase = ayyo_software_showcase.cli:main" in entry_points


def test_generated_artifacts_are_ignored_and_not_tracked():
    artifacts = (
        "software_showcase/build/lib/package.py",
        "software_showcase/dist/package.whl",
        "software_showcase/src/ayyo_software_showcase.egg-info/PKG-INFO",
    )
    for artifact in artifacts:
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", artifact],
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        assert ignored.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--", "software_showcase/**"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert not any(
        "__pycache__" in item or ".egg-info" in item or "/build/" in item
        for item in tracked
    )
