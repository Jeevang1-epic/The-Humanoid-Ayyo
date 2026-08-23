import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_personal_context


class PackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "personal_context"
        self.source_root = self.package_root / "src"

    def test_runtime_imports_have_no_persistence_ros_network_or_model_coupling(self) -> None:
        forbidden_roots = {
            "aiohttp",
            "azure",
            "boto3",
            "chromadb",
            "grpc",
            "httpx",
            "numpy",
            "pinecone",
            "rclpy",
            "requests",
            "sentence_transformers",
            "socket",
            "sqlite3",
            "torch",
            "transformers",
            "urllib",
        }
        imports: set[str] = set()
        for source_file in self.source_root.rglob("*.py"):
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        self.assertEqual(set(), imports & forbidden_roots)

    def test_runtime_uses_only_public_memory_os_and_has_no_mutation_calls(self) -> None:
        source = "\n".join(
            source_file.read_text(encoding="utf-8")
            for source_file in self.source_root.rglob("*.py")
        )
        self.assertNotIn("ayyo_memory.sqlite_store", source)
        self.assertNotIn("ayyo_memory.store", source)
        self.assertNotIn("SQLiteMemoryStore", source)

        forbidden_calls = {"create_memory", "correct_memory", "retract_memory"}
        calls: set[str] = set()
        for source_file in self.source_root.rglob("*.py"):
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in forbidden_calls
                ):
                    calls.add(node.func.attr)
        self.assertEqual(set(), calls)

    def test_public_api_exports_are_importable(self) -> None:
        self.assertTrue(ayyo_personal_context.__all__)
        for public_name in ayyo_personal_context.__all__:
            with self.subTest(public_name=public_name):
                self.assertTrue(hasattr(ayyo_personal_context, public_name))

    def test_pyproject_has_only_memory_os_as_runtime_dependency(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]
        self.assertEqual(["ayyo-memory==0.1.0"], project["dependencies"])
        self.assertEqual(">=3.12", project["requires-python"])

    def test_wheel_contains_only_the_context_runtime_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            package_copy = temporary_path / "personal_context"
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
                all(name.startswith("ayyo_personal_context/") for name in source_names)
            )
            self.assertFalse(any(name.startswith("ayyo_memory/") for name in names))

    def test_build_artifacts_are_ignored_and_untracked(self) -> None:
        artifact_paths = (
            "personal_context/build/lib/package.py",
            "personal_context/dist/package.whl",
            "personal_context/src/ayyo_personal_context.egg-info/PKG-INFO",
        )
        for artifact_path in artifact_paths:
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", artifact_path],
                cwd=self.repository_root,
                check=False,
            )
            self.assertEqual(0, ignored.returncode)
        tracked = subprocess.run(
            ["git", "ls-files", "--", "personal_context/**"],
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
