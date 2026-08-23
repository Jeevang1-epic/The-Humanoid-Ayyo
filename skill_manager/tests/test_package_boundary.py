from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_skill_manager


class PackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "skill_manager"
        self.source_root = self.package_root / "src"

    def runtime_sources(self) -> tuple[Path, ...]:
        return tuple(sorted(self.source_root.rglob("*.py")))

    def runtime_trees(self) -> tuple[tuple[Path, ast.AST], ...]:
        return tuple(
            (path, ast.parse(path.read_text(encoding="utf-8")))
            for path in self.runtime_sources()
        )

    def test_runtime_has_no_persistence_ros_network_model_or_process_imports(self) -> None:
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
        for _, tree in self.runtime_trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        self.assertEqual(set(), imports & forbidden_roots)

    def test_runtime_uses_only_public_safety_and_executive_contracts(self) -> None:
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
        self.assertEqual({"ayyo_executive", "ayyo_safety"}, ayyo_imports)

    def test_runtime_exposes_no_execution_or_dynamic_loading_surface(self) -> None:
        forbidden_calls = {
            "__import__",
            "actuate",
            "compile",
            "eval",
            "exec",
            "execute",
            "import_module",
            "open",
            "popen",
            "publish",
            "run",
            "send",
            "spawn",
            "system",
            "write_bytes",
            "write_text",
        }
        forbidden_definitions = {
            "actuate",
            "authorize",
            "command",
            "execute",
            "load_plugin",
            "publish",
            "run",
            "send",
        }
        found_calls: set[str] = set()
        found_definitions: set[str] = set()
        for _, tree in self.runtime_trees():
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in forbidden_definitions:
                        found_definitions.add(node.name)
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
                        found_calls.add(name)
        self.assertEqual(set(), found_calls)
        self.assertEqual(set(), found_definitions)

    def test_public_models_have_no_executable_payload_fields(self) -> None:
        forbidden_fragments = {
            "arbitrary_code",
            "callback",
            "callable",
            "command",
            "executable",
            "python_code",
            "ros_action",
            "shell",
        }
        public_models = (
            ayyo_skill_manager.SkillDefinition,
            ayyo_skill_manager.SkillSelection,
            ayyo_skill_manager.SkillInvocation,
            ayyo_skill_manager.SkillBindingResult,
        )
        for model in public_models:
            annotations = set(model.__annotations__)
            with self.subTest(model=model.__name__):
                self.assertEqual(set(), annotations & forbidden_fragments)
        for public_name in ayyo_skill_manager.__all__:
            normalized = public_name.lower()
            self.assertNotIn("execute", normalized)
            self.assertNotIn("actuate", normalized)

    def test_runtime_does_not_hide_defects_with_broad_catches(self) -> None:
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

    def test_public_api_is_importable_and_unique(self) -> None:
        self.assertTrue(ayyo_skill_manager.__all__)
        self.assertEqual(
            len(ayyo_skill_manager.__all__),
            len(set(ayyo_skill_manager.__all__)),
        )
        for public_name in ayyo_skill_manager.__all__:
            with self.subTest(public_name=public_name):
                self.assertTrue(hasattr(ayyo_skill_manager, public_name))

    def test_pyproject_has_only_minimum_public_runtime_dependencies(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]
        self.assertEqual(
            ["ayyo-executive==0.1.0", "ayyo-safety==0.1.0"],
            project["dependencies"],
        )
        self.assertEqual(">=3.12", project["requires-python"])
        self.assertNotIn("scripts", project)
        self.assertNotIn("gui-scripts", project)
        self.assertNotIn("entry-points", project)

    def test_wheel_contains_only_skill_manager_runtime_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            package_copy = temporary_path / "skill_manager"
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
                all(name.startswith("ayyo_skill_manager/") for name in sources)
            )
            self.assertFalse(any(name.startswith("ayyo_safety/") for name in names))
            self.assertFalse(any(name.startswith("ayyo_executive/") for name in names))
            self.assertIn("Name: ayyo-skill-manager\n", metadata)
            self.assertIn("Version: 0.1.0\n", metadata)
            requirements = sorted(
                line.split(":", 1)[1].strip().replace(" ", "")
                for line in metadata.splitlines()
                if line.startswith("Requires-Dist:")
            )
            self.assertEqual(
                ["ayyo-executive==0.1.0", "ayyo-safety==0.1.0"],
                requirements,
            )

    def test_build_artifacts_are_ignored_and_untracked(self) -> None:
        artifacts = (
            "skill_manager/build/lib/package.py",
            "skill_manager/dist/package.whl",
            "skill_manager/src/ayyo_skill_manager.egg-info/PKG-INFO",
        )
        for artifact in artifacts:
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", artifact],
                cwd=self.repository_root,
                check=False,
            )
            self.assertEqual(0, ignored.returncode)
        tracked = subprocess.run(
            ["git", "ls-files", "--", "skill_manager/**"],
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
