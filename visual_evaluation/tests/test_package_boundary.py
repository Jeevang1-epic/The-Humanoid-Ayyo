from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_visual_evaluation


class VisualEvaluationPackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "visual_evaluation"
        self.source_root = self.package_root / "src"

    def test_core_has_no_ros_memory_control_network_shell_or_dynamic_import(self) -> None:
        forbidden = {
            "ayyo_executive",
            "ayyo_memory",
            "ayyo_perception",
            "ayyo_runtime_bridge",
            "ayyo_safety_kernel",
            "ayyo_simulation_control",
            "ayyo_working_memory",
            "builtin_interfaces",
            "gazebo",
            "gz",
            "importlib",
            "launch",
            "rclpy",
            "requests",
            "sensor_msgs",
            "socket",
            "sqlite3",
            "subprocess",
        }
        imports = set()
        forbidden_calls = []
        for path in self.source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in {"eval", "exec", "__import__"}:
                        forbidden_calls.append(node.func.id)
        self.assertEqual(set(), imports & forbidden)
        self.assertEqual([], forbidden_calls)

    def test_only_world_model_runtime_dependency_is_declared(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        self.assertEqual(["ayyo-world-model==0.1.0"], project["dependencies"])

    def test_public_exports_are_importable(self) -> None:
        self.assertTrue(ayyo_visual_evaluation.__all__)
        for name in ayyo_visual_evaluation.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(ayyo_visual_evaluation, name))

    def test_wheel_contains_only_visual_evaluation_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_copy = root / "visual_evaluation"
            wheels = root / "wheels"
            shutil.copytree(
                self.package_root,
                package_copy,
                ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
            )
            wheels.mkdir()
            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    "pip",
                    "wheel",
                    "--no-build-isolation",
                    "--no-deps",
                    "--wheel-dir",
                    str(wheels),
                    str(package_copy),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            wheel = next(wheels.glob("*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = archive.namelist()
            self.assertTrue(
                all(
                    name.startswith("ayyo_visual_evaluation/")
                    for name in names
                    if name.endswith(".py")
                )
            )


if __name__ == "__main__":
    unittest.main()
