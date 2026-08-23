# Copyright 2026 Ayyo Project Authors

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

import ayyo_simulation_control


class SimulationControlPackageBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "simulation_control"
        self.source_root = self.package_root / "src"
        self.ros_package_root = (
            self.repository_root / "ros2_ws" / "src" / "ayyo_simulation_control"
        )

    def production_sources(self) -> tuple[Path, ...]:
        return tuple(sorted(self.source_root.rglob("*.py")))

    def production_trees(self) -> tuple[tuple[Path, ast.AST], ...]:
        return tuple(
            (path, ast.parse(path.read_text(encoding="utf-8")))
            for path in self.production_sources()
        )

    def test_core_depends_only_on_public_runtime_bridge_contract(self) -> None:
        ayyo_imports: set[str] = set()
        for _, tree in self.production_trees():
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
        self.assertEqual({"ayyo_runtime_bridge"}, ayyo_imports)

    def test_core_has_no_ros_process_network_or_filesystem_surface(self) -> None:
        forbidden_roots = {
            "aiohttp",
            "httpx",
            "importlib",
            "openai",
            "os",
            "pathlib",
            "rclpy",
            "requests",
            "shutil",
            "socket",
            "subprocess",
            "urllib",
        }
        imports: set[str] = set()
        for _, tree in self.production_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        self.assertEqual(set(), imports & forbidden_roots)

    def test_core_has_no_dynamic_loading_or_arbitrary_execution(self) -> None:
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
        for path, tree in self.production_trees():
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

    def test_core_does_not_hide_programming_defects(self) -> None:
        broad_handlers: list[tuple[str, int]] = []
        for path, tree in self.production_trees():
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if node.type is None or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in {"BaseException", "Exception"}
                ):
                    broad_handlers.append((path.name, node.lineno))
        self.assertEqual([], broad_handlers)

    def test_public_api_is_importable_and_unique(self) -> None:
        self.assertTrue(ayyo_simulation_control.__all__)
        self.assertEqual(
            len(ayyo_simulation_control.__all__),
            len(set(ayyo_simulation_control.__all__)),
        )
        for public_name in ayyo_simulation_control.__all__:
            with self.subTest(public_name=public_name):
                self.assertTrue(hasattr(ayyo_simulation_control, public_name))

    def test_pyproject_has_only_runtime_bridge_dependency(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]
        self.assertEqual(
            ["ayyo-runtime-bridge==0.1.0"],
            project["dependencies"],
        )
        self.assertEqual(">=3.12", project["requires-python"])
        self.assertNotIn("scripts", project)
        self.assertNotIn("gui-scripts", project)
        self.assertNotIn("entry-points", project)

    def test_wheel_contains_only_control_core_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            package_copy = temporary_path / "simulation_control"
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
                all(name.startswith("ayyo_simulation_control/") for name in sources)
            )
            self.assertFalse(
                any(name.startswith("ayyo_runtime_bridge/") for name in names)
            )
            self.assertIn("Name: ayyo-simulation-control\n", metadata)
            self.assertIn("Version: 0.1.0\n", metadata)
            requirements = [
                line.split(":", 1)[1].strip().replace(" ", "")
                for line in metadata.splitlines()
                if line.startswith("Requires-Dist:")
            ]
            self.assertEqual(["ayyo-runtime-bridge==0.1.0"], requirements)

    def test_ros_metadata_installs_owned_core_without_upstream_layers(self) -> None:
        package = ET.parse(self.ros_package_root / "package.xml").getroot()
        self.assertEqual("ayyo_simulation_control", package.findtext("name"))
        dependencies = {
            item.text
            for item in package
            if item.tag.endswith("depend") and item.text
        }
        self.assertFalse(
            dependencies
            & {
                "ayyo_executive",
                "ayyo_memory",
                "ayyo_memory_validation",
                "ayyo_personal_context",
                "ayyo_safety",
                "ayyo_skill_manager",
            }
        )
        cmake = (self.ros_package_root / "CMakeLists.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("ament_python_install_package", cmake)
        self.assertIn("simulation_control/src/ayyo_simulation_control", cmake)

    def test_build_artifacts_are_ignored_and_untracked(self) -> None:
        artifacts = (
            "simulation_control/build/lib/package.py",
            "simulation_control/dist/package.whl",
            "simulation_control/src/ayyo_simulation_control.egg-info/PKG-INFO",
            "ros2_ws/build/ayyo_simulation_control/CMakeCache.txt",
        )
        for artifact in artifacts:
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", artifact],
                cwd=self.repository_root,
                check=False,
            )
            self.assertEqual(0, ignored.returncode)
        tracked = subprocess.run(
            ["git", "ls-files", "--", "simulation_control/**", "ros2_ws/**"],
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
                if path.endswith((".pyc", ".whl"))
                or "/build/" in path
                or "/install/" in path
                or "/log/" in path
            ],
        )


if __name__ == "__main__":
    unittest.main()
