from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_safety


class PackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "safety_kernel"
        self.source_root = self.package_root / "src"

    def runtime_sources(self) -> tuple[Path, ...]:
        return tuple(sorted(self.source_root.rglob("*.py")))

    def test_runtime_has_no_persistence_ros_network_model_or_execution_imports(self) -> None:
        forbidden_roots = {
            "aiohttp",
            "ayyo_memory",
            "ayyo_memory_validation",
            "ayyo_personal_context",
            "azure",
            "boto3",
            "chromadb",
            "grpc",
            "httpx",
            "numpy",
            "openai",
            "os",
            "pathlib",
            "requests",
            "rclpy",
            "sentence_transformers",
            "shutil",
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

    def test_runtime_uses_only_public_executive_imports(self) -> None:
        executive_imports: list[str] = []
        ayyo_imports: list[str] = []
        for source_file in self.runtime_sources():
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                else:
                    continue
                ayyo_imports.extend(
                    module for module in modules if module.startswith("ayyo_")
                )
                executive_imports.extend(
                    module
                    for module in modules
                    if module.startswith("ayyo_executive")
                )
        self.assertTrue(executive_imports)
        self.assertEqual({"ayyo_executive"}, set(executive_imports))
        self.assertEqual({"ayyo_executive"}, set(ayyo_imports))

    def test_runtime_has_no_execution_or_mutation_surface(self) -> None:
        forbidden_calls = {
            "__import__",
            "actuate",
            "compile",
            "create_memory",
            "correct_memory",
            "eval",
            "exec",
            "execute",
            "import_module",
            "open",
            "popen",
            "publish",
            "retract_memory",
            "run",
            "send",
            "spawn",
            "system",
            "unlink",
            "write_bytes",
            "write_text",
        }
        forbidden_definitions = {
            "actuate",
            "authorize",
            "execute",
            "publish",
            "send",
        }
        calls: set[str] = set()
        definitions: set[str] = set()
        for source_file in self.runtime_sources():
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in forbidden_definitions:
                        definitions.add(node.name)
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        name = node.func.attr
                    else:
                        continue
                    if name in forbidden_calls:
                        calls.add(name)
        self.assertEqual(set(), calls)
        self.assertEqual(set(), definitions)

    def test_runtime_does_not_hide_programming_defects_with_broad_catches(self) -> None:
        broad_handlers: list[tuple[str, int]] = []
        for source_file in self.runtime_sources():
            tree = ast.parse(source_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if node.type is None or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in {"BaseException", "Exception"}
                ):
                    broad_handlers.append((source_file.name, node.lineno))
        self.assertEqual([], broad_handlers)

    def test_public_api_is_importable_unique_and_has_no_execute_result(self) -> None:
        self.assertTrue(ayyo_safety.__all__)
        self.assertEqual(len(ayyo_safety.__all__), len(set(ayyo_safety.__all__)))
        for public_name in ayyo_safety.__all__:
            with self.subTest(public_name=public_name):
                self.assertTrue(hasattr(ayyo_safety, public_name))
                self.assertNotIn("execute", public_name.lower())
                self.assertNotIn("actuate", public_name.lower())
        disposition_values = {
            disposition.value for disposition in ayyo_safety.SafetyDisposition
        }
        self.assertNotIn("execute", disposition_values)
        self.assertFalse(hasattr(ayyo_safety.SafetyDecision, "safe"))
        self.assertFalse(hasattr(ayyo_safety.SafetyDecision, "allowed"))

    def test_pyproject_has_only_executive_as_runtime_dependency(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]
        self.assertEqual(["ayyo-executive==0.1.0"], project["dependencies"])
        self.assertEqual(">=3.12", project["requires-python"])
        self.assertNotIn("scripts", project)
        self.assertNotIn("gui-scripts", project)
        self.assertNotIn("entry-points", project)

    def test_wheel_contains_only_safety_runtime_package_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            package_copy = temporary_path / "safety_kernel"
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
            source_names = [name for name in names if name.endswith(".py")]
            self.assertTrue(source_names)
            self.assertTrue(
                all(name.startswith("ayyo_safety/") for name in source_names)
            )
            self.assertFalse(
                any(name.startswith("ayyo_executive/") for name in names)
            )
            self.assertIn("Name: ayyo-safety\n", metadata)
            self.assertIn("Version: 0.1.0\n", metadata)
            requires_dist = next(
                line.split(":", 1)[1].strip()
                for line in metadata.splitlines()
                if line.startswith("Requires-Dist:")
            )
            self.assertEqual("ayyo-executive==0.1.0", requires_dist.replace(" ", ""))

    def test_build_artifacts_are_ignored_and_untracked(self) -> None:
        artifact_paths = (
            "safety_kernel/build/lib/package.py",
            "safety_kernel/dist/package.whl",
            "safety_kernel/src/ayyo_safety.egg-info/PKG-INFO",
        )
        for artifact_path in artifact_paths:
            with self.subTest(artifact_path=artifact_path):
                ignored = subprocess.run(
                    ["git", "check-ignore", "--quiet", artifact_path],
                    cwd=self.repository_root,
                    check=False,
                )
                self.assertEqual(0, ignored.returncode)
        tracked = subprocess.run(
            ["git", "ls-files", "--", "safety_kernel/**"],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        forbidden_suffixes = (
            ".pyc",
            ".sqlite3",
            ".sqlite3-wal",
            ".sqlite3-shm",
            ".whl",
        )
        self.assertEqual(
            [],
            [path for path in tracked if path.endswith(forbidden_suffixes)],
        )


if __name__ == "__main__":
    unittest.main()
