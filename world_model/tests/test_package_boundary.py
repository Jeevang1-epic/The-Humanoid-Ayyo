from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_world_model


class PackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "world_model"
        self.source_root = self.package_root / "src"

    def test_core_has_no_ros_gazebo_memory_network_or_process_dependency(self) -> None:
        forbidden = {
            "ayyo_memory",
            "builtin_interfaces",
            "gz",
            "gazebo",
            "launch",
            "rclpy",
            "requests",
            "sensor_msgs",
            "socket",
            "sqlite3",
            "subprocess",
        }
        imports = set()
        for path in self.source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        self.assertEqual(set(), imports & forbidden)

    def test_no_runtime_dependency_is_declared(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        self.assertEqual([], project["dependencies"])
        self.assertEqual(">=3.12", project["requires-python"])

    def test_public_exports_are_importable(self) -> None:
        self.assertTrue(ayyo_world_model.__all__)
        for name in ayyo_world_model.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(ayyo_world_model, name))

    def test_wheel_contains_only_world_model_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy = root / "world_model"
            wheels = root / "wheels"
            shutil.copytree(self.package_root, copy, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            wheels.mkdir()
            result = subprocess.run(
                ["python3", "-m", "pip", "wheel", "--no-build-isolation", "--no-deps", "--wheel-dir", str(wheels), str(copy)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            wheel = next(wheels.glob("*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = archive.namelist()
            self.assertTrue(all(name.startswith("ayyo_world_model/") for name in names if name.endswith(".py")))


if __name__ == "__main__":
    unittest.main()
