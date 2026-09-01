from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import xml.etree.ElementTree as ET
import zipfile

import ayyo_runtime_bridge


class RuntimeBridgePackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "runtime_bridge"
        self.source_root = self.package_root / "src"
        self.ros_package_root = (
            self.repository_root / "ros2_ws" / "src" / "ayyo_runtime_bridge"
        )

    def runtime_sources(self) -> tuple[Path, ...]:
        return tuple(sorted(self.source_root.rglob("*.py")))

    def runtime_trees(self) -> tuple[tuple[Path, ast.AST], ...]:
        return tuple(
            (path, ast.parse(path.read_text(encoding="utf-8")))
            for path in self.runtime_sources()
        )

    def test_runtime_depends_only_on_public_skill_manager_contract(self) -> None:
        ayyo_imports: set[str] = set()
        for _, tree in self.runtime_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                else:
                    continue
                ayyo_imports.update(
                    module for module in modules if module.startswith("ayyo_")
                )
        self.assertEqual({"ayyo_skill_manager"}, ayyo_imports)

    def test_runtime_has_no_forbidden_system_or_provider_imports(self) -> None:
        forbidden_roots = {
            "aiohttp",
            "ayyo_executive",
            "ayyo_memory",
            "ayyo_memory_validation",
            "ayyo_personal_context",
            "ayyo_safety",
            "boto3",
            "grpc",
            "httpx",
            "importlib",
            "openai",
            "os",
            "pathlib",
            "rclpy",
            "requests",
            "shutil",
            "socket",
            "sqlite3",
            "subprocess",
            "urllib",
        }
        imports: set[str] = set()
        for _, tree in self.runtime_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        self.assertEqual(set(), imports & forbidden_roots)

    def test_runtime_has_no_dynamic_loading_or_process_execution(self) -> None:
        forbidden_calls = {
            "__import__",
            "compile",
            "eval",
            "exec",
            "import_module",
            "open",
            "popen",
            "run",
            "spawn",
            "system",
        }
        found: list[tuple[str, int, str]] = []
        for path, tree in self.runtime_trees():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                    if name == "compile":
                        continue
                else:
                    continue
                if name in forbidden_calls:
                    found.append((path.name, node.lineno, name))
        self.assertEqual([], found)

    def test_runtime_does_not_hide_programming_defects(self) -> None:
        broad_handlers: list[tuple[str, int]] = []
        for path, tree in self.runtime_trees():
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if node.type is None or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in {"BaseException", "Exception"}
                ):
                    broad_handlers.append((path.name, node.lineno))
        self.assertEqual([], broad_handlers)

    def test_production_package_contains_no_fake_transport(self) -> None:
        class_names = {
            node.name
            for _, tree in self.runtime_trees()
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
        }
        self.assertFalse(any("fake" in name.lower() for name in class_names))
        self.assertFalse(any("mock" in name.lower() for name in class_names))

    def test_public_models_have_no_executable_payload_fields(self) -> None:
        forbidden_fragments = {
            "arbitrary_code",
            "callback",
            "callable",
            "command",
            "executable",
            "executable_path",
            "python_code",
            "shell",
            "source_code",
        }
        public_models = (
            ayyo_runtime_bridge.RosServiceEndpoint,
            ayyo_runtime_bridge.RuntimeEndpointBinding,
            ayyo_runtime_bridge.RuntimeRequest,
            ayyo_runtime_bridge.RuntimeDecision,
            ayyo_runtime_bridge.RuntimeDispatchResult,
        )
        for model in public_models:
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    set(),
                    set(model.__annotations__) & forbidden_fragments,
                )

    def test_public_api_is_importable_and_unique(self) -> None:
        self.assertTrue(ayyo_runtime_bridge.__all__)
        self.assertEqual(
            len(ayyo_runtime_bridge.__all__),
            len(set(ayyo_runtime_bridge.__all__)),
        )
        for public_name in ayyo_runtime_bridge.__all__:
            with self.subTest(public_name=public_name):
                self.assertTrue(hasattr(ayyo_runtime_bridge, public_name))

    def test_pyproject_has_only_skill_manager_runtime_dependency(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]
        self.assertEqual(["ayyo-skill-manager==0.1.0"], project["dependencies"])
        self.assertEqual(">=3.12", project["requires-python"])
        self.assertNotIn("scripts", project)
        self.assertNotIn("gui-scripts", project)
        self.assertNotIn("entry-points", project)

    def test_wheel_contains_only_runtime_bridge_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            package_copy = temporary_path / "runtime_bridge"
            wheel_directory = temporary_path / "wheel"
            shutil.copytree(
                self.package_root,
                package_copy,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.egg-info",
                    "build",
                    "dist",
                ),
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
                cwd=self.repository_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            wheels = list(wheel_directory.glob("*.whl"))
            self.assertEqual(1, len(wheels))
            with zipfile.ZipFile(wheels[0]) as wheel:
                names = wheel.namelist()
                metadata_name = next(
                    name for name in names if name.endswith(".dist-info/METADATA")
                )
                metadata = wheel.read(metadata_name).decode("utf-8")
            sources = [name for name in names if name.endswith(".py")]
            self.assertTrue(sources)
            self.assertTrue(
                all(name.startswith("ayyo_runtime_bridge/") for name in sources)
            )
            self.assertFalse(any(name.startswith("ayyo_skill_manager/") for name in names))
            self.assertIn("Name: ayyo-runtime-bridge\n", metadata)
            self.assertIn("Version: 0.1.0\n", metadata)
            requirements = [
                line.split(":", 1)[1].strip().replace(" ", "")
                for line in metadata.splitlines()
                if line.startswith("Requires-Dist:")
            ]
            self.assertEqual(["ayyo-skill-manager==0.1.0"], requirements)

    def test_ros_package_metadata_installs_the_owned_core(self) -> None:
        package = ET.parse(self.ros_package_root / "package.xml").getroot()
        self.assertEqual("ayyo_runtime_bridge", package.findtext("name"))
        self.assertEqual("0.1.0", package.findtext("version"))
        build_tools = {item.text for item in package.findall("buildtool_depend")}
        self.assertEqual({"ament_cmake", "ament_cmake_python"}, build_tools)
        cmake = (self.ros_package_root / "CMakeLists.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("ament_python_install_package", cmake)
        self.assertIn("runtime_bridge/src/ayyo_runtime_bridge", cmake)

    def test_only_reviewed_non_runtime_ros_interfaces_are_present(self) -> None:
        interface_root = self.repository_root / "ros2_ws" / "src" / "ayyo_interfaces"
        generated = [
            path.relative_to(interface_root).as_posix()
            for suffix in ("*.msg", "*.srv", "*.action")
            for path in interface_root.rglob(suffix)
        ]
        self.assertEqual(
            {
                "msg/AudioFrame.msg",
                "srv/GetRobotBodyState.srv",
                "srv/SetDevelopmentJointPosition.srv",
            },
            set(generated),
        )
        development = (
            interface_root / "srv" / "SetDevelopmentJointPosition.srv"
        ).read_text(encoding="utf-8")
        body_query = (
            interface_root / "srv" / "GetRobotBodyState.srv"
        ).read_text(encoding="utf-8")
        audio_frame = (interface_root / "msg" / "AudioFrame.msg").read_text(
            encoding="utf-8"
        )
        self.assertIn("explicit development injection", development)
        self.assertIn("Read-only fixed query", body_query)
        self.assertIn("uint8[<=32000] data", audio_frame)
        self.assertNotIn(
            "ApplyRuntimeJointPosition",
            development + body_query + audio_frame,
        )

    def test_build_artifacts_are_ignored_and_untracked(self) -> None:
        artifacts = (
            "runtime_bridge/build/lib/package.py",
            "runtime_bridge/dist/package.whl",
            "runtime_bridge/src/ayyo_runtime_bridge.egg-info/PKG-INFO",
            "ros2_ws/build/ayyo_runtime_bridge/CMakeCache.txt",
        )
        for artifact in artifacts:
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", artifact],
                cwd=self.repository_root,
                check=False,
            )
            self.assertEqual(0, ignored.returncode)
        tracked = subprocess.run(
            ["git", "ls-files", "--", "runtime_bridge/**", "ros2_ws/**"],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(
            [],
            [
                path
                for path in tracked
                if path.endswith((".pyc", ".sqlite3", ".whl"))
                or "/build/" in path
                or "/install/" in path
                or "/log/" in path
            ],
        )


if __name__ == "__main__":
    unittest.main()
