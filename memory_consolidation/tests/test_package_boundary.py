from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import ayyo_memory_consolidation


class PackageBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_root = Path(__file__).resolve().parents[2]
        self.package_root = self.repository_root / "memory_consolidation"
        self.source_root = self.package_root / "src"

    @staticmethod
    def imports_under(source_root: Path) -> set[str]:
        imports: set[str] = set()
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        return imports

    def test_dependency_direction_of_existing_layers_remains_unchanged(self) -> None:
        forbidden_by_root = {
            "working_memory": {
                "ayyo_memory",
                "ayyo_memory_consolidation",
                "ayyo_memory_validation",
            },
            "world_model": {
                "ayyo_memory",
                "ayyo_memory_consolidation",
                "ayyo_memory_validation",
            },
            "perception": {
                "ayyo_memory",
                "ayyo_memory_consolidation",
                "ayyo_memory_validation",
            },
            "memory": {"ayyo_memory_consolidation"},
        }
        for package, forbidden in forbidden_by_root.items():
            with self.subTest(package=package):
                imports = self.imports_under(
                    self.repository_root / package / "src"
                )
                self.assertEqual(set(), imports & forbidden)
        self.assertEqual(
            {"ayyo_memory"},
            self.imports_under(self.repository_root / "memory_validation" / "src")
            & {
                "ayyo_memory",
                "ayyo_working_memory",
                "ayyo_world_model",
                "ayyo_memory_consolidation",
            },
        )
        self.assertNotIn(
            "ayyo_memory_consolidation",
            self.imports_under(self.repository_root / "memory_validation" / "src"),
        )

    def test_bridge_has_only_reviewed_public_standalone_dependencies(self) -> None:
        with (self.package_root / "pyproject.toml").open("rb") as stream:
            dependencies = tomllib.load(stream)["project"]["dependencies"]
        self.assertEqual(
            [
                "ayyo-memory==0.1.0",
                "ayyo-memory-validation==0.1.0",
                "ayyo-working-memory==0.1.0",
                "ayyo-world-model==0.1.0",
            ],
            dependencies,
        )
        imports = self.imports_under(self.source_root)
        self.assertEqual(
            set(),
            imports
            & {
                "builtin_interfaces",
                "queue",
                "gazebo",
                "launch",
                "rclpy",
                "sensor_msgs",
                "sqlite3",
                "socket",
                "subprocess",
                "threading",
            },
        )

    def test_bridge_source_has_no_memory_service_or_persistence_operation(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in self.source_root.rglob("*.py")
        )
        for forbidden in (
            "MemoryService",
            "SQLiteMemoryStore",
            ".apply(",
            ".create_memory(",
            ".correct_memory(",
            "datetime.now(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_selection_policy_is_stateless_and_has_no_runtime_or_storage_edge(self) -> None:
        selection_source = "\n".join(
            (
                self.source_root / "ayyo_memory_consolidation" / name
            ).read_text(encoding="utf-8")
            for name in ("selection_models.py", "selection_policy.py")
        )
        for forbidden in (
            "WorkingMemory",
            "MemoryValidationService",
            "MemoryService",
            "SQLiteMemoryStore",
            ".evaluate(",
            ".apply(",
            ".persist(",
            "threading",
            "Timer(",
            "rclpy",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, selection_source)

    def test_discovery_is_explicit_and_has_no_downstream_or_runtime_edge(self) -> None:
        discovery_source = "\n".join(
            (
                self.source_root / "ayyo_memory_consolidation" / name
            ).read_text(encoding="utf-8")
            for name in ("discovery_models.py", "discovery_policy.py")
        )
        for forbidden in (
            "CandidateEvidence",
            "MemoryValidationService",
            "MemoryService",
            "SQLiteMemoryStore",
            ".stage(",
            ".select(",
            ".evaluate(",
            ".apply(",
            ".persist(",
            "datetime.now(",
            "threading",
            "Timer(",
            "rclpy",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, discovery_source)

    def test_public_exports_are_importable(self) -> None:
        self.assertTrue(ayyo_memory_consolidation.__all__)
        for name in ayyo_memory_consolidation.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(ayyo_memory_consolidation, name))

    def test_wheel_contains_only_bridge_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied = root / "memory_consolidation"
            wheels = root / "wheels"
            shutil.copytree(
                self.package_root,
                copied,
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
                    str(copied),
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
                    name.startswith("ayyo_memory_consolidation/")
                    for name in names
                    if name.endswith(".py")
                )
            )


if __name__ == "__main__":
    unittest.main()
