import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_executive


class PackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "executive"
        self.source_root = self.package_root / "src"

    def runtime_sources(self):
        return tuple(self.source_root.rglob("*.py"))

    def test_runtime_has_no_persistence_ros_network_model_or_execution_imports(self) -> None:
        forbidden_roots = {
            "aiohttp",
            "ayyo_memory",
            "azure",
            "boto3",
            "chromadb",
            "grpc",
            "httpx",
            "numpy",
            "openai",
            "requests",
            "rclpy",
            "sentence_transformers",
            "socket",
            "sqlite3",
            "subprocess",
            "torch",
            "transformers",
            "urllib",
        }
        imports: set[str] = set()
        for source_file in self.runtime_sources():
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        self.assertEqual(set(), imports & forbidden_roots)

    def test_runtime_has_no_memory_mutation_or_execution_calls(self) -> None:
        forbidden_calls = {
            "create_memory",
            "correct_memory",
            "retract_memory",
            "exec",
            "eval",
            "system",
            "popen",
            "publish",
            "send",
        }
        calls: set[str] = set()
        for source_file in self.runtime_sources():
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        name = node.func.attr
                    else:
                        continue
                    if name in forbidden_calls:
                        calls.add(name)
        self.assertEqual(set(), calls)

    def test_runtime_uses_only_the_public_personal_context_import(self) -> None:
        imports = []
        for source_file in self.runtime_sources():
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            imports.extend(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("ayyo_personal_context")
            )
        self.assertTrue(imports)
        self.assertEqual({"ayyo_personal_context"}, set(imports))

    def test_public_api_exports_are_importable_and_unique(self) -> None:
        self.assertTrue(ayyo_executive.__all__)
        self.assertEqual(len(ayyo_executive.__all__), len(set(ayyo_executive.__all__)))
        for public_name in ayyo_executive.__all__:
            with self.subTest(public_name=public_name):
                self.assertTrue(hasattr(ayyo_executive, public_name))

    def test_pyproject_has_only_personal_context_as_runtime_dependency(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]
        self.assertEqual(
            ["ayyo-personal-context==0.1.0"],
            project["dependencies"],
        )
        self.assertEqual(">=3.12", project["requires-python"])

    def test_wheel_contains_only_the_executive_runtime_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            package_copy = temporary_path / "executive"
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
            source_names = [name for name in names if name.endswith(".py")]
            self.assertTrue(source_names)
            self.assertTrue(
                all(name.startswith("ayyo_executive/") for name in source_names)
            )
            self.assertFalse(
                any(name.startswith("ayyo_personal_context/") for name in names)
            )

    def test_build_artifacts_are_ignored_and_untracked(self) -> None:
        artifact_paths = (
            "executive/build/lib/package.py",
            "executive/dist/package.whl",
            "executive/src/ayyo_executive.egg-info/PKG-INFO",
        )
        for artifact_path in artifact_paths:
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", artifact_path],
                cwd=self.repository_root,
                check=False,
            )
            self.assertEqual(0, ignored.returncode)
        tracked = subprocess.run(
            ["git", "ls-files", "--", "executive/**"],
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
            ],
        )


if __name__ == "__main__":
    unittest.main()
