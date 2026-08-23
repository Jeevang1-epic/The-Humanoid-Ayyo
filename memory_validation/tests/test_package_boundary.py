import ast
from pathlib import Path
import subprocess
import tomllib
import unittest

import ayyo_memory_validation


class PackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.source_root = self.repository_root / "memory_validation" / "src"

    def test_runtime_imports_have_no_sqlite_ros_network_or_model_coupling(self) -> None:
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

    def test_public_api_exports_are_importable(self) -> None:
        self.assertTrue(ayyo_memory_validation.__all__)
        for public_name in ayyo_memory_validation.__all__:
            with self.subTest(public_name=public_name):
                self.assertTrue(hasattr(ayyo_memory_validation, public_name))

    def test_runtime_does_not_import_memory_os_persistence_modules(self) -> None:
        source = "\n".join(
            source_file.read_text(encoding="utf-8")
            for source_file in self.source_root.rglob("*.py")
        )
        self.assertNotIn("ayyo_memory.sqlite_store", source)
        self.assertNotIn("ayyo_memory.sqlite_schema", source)
        self.assertNotIn("SQLiteMemoryStore", source)

    def test_pyproject_has_only_the_public_memory_runtime_dependency(self) -> None:
        pyproject_path = self.repository_root / "memory_validation" / "pyproject.toml"
        with pyproject_path.open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file)["project"]
        self.assertEqual(["ayyo-memory==0.1.0"], project["dependencies"])
        self.assertEqual(">=3.12", project["requires-python"])

    def test_temporary_runtime_artifacts_are_untracked(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "--", "memory_validation/**"],
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

    def test_python_package_build_artifacts_are_ignored(self) -> None:
        artifact_paths = (
            "memory_validation/build/lib/package.py",
            "memory_validation/dist/package.whl",
            "memory_validation/src/ayyo_memory_validation.egg-info/PKG-INFO",
        )
        for artifact_path in artifact_paths:
            with self.subTest(artifact_path=artifact_path):
                ignored = subprocess.run(
                    ["git", "check-ignore", "--quiet", artifact_path],
                    cwd=self.repository_root,
                    check=False,
                )
                self.assertEqual(0, ignored.returncode)


if __name__ == "__main__":
    unittest.main()
