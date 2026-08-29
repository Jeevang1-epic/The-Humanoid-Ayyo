from __future__ import annotations

import ast
from pathlib import Path
import unittest


SOURCE_ROOT = Path(__file__).parents[1] / "src" / "ayyo_physical_camera"


class PhysicalCameraPackageBoundaryTest(unittest.TestCase):
    def test_core_has_no_ros_cloud_control_or_dynamic_execution_dependency(self) -> None:
        forbidden_roots = {
            "ayyo_memory",
            "ayyo_runtime_bridge",
            "ayyo_safety",
            "ayyo_simulation_control",
            "diagnostic_msgs",
            "gazebo",
            "importlib",
            "nav_msgs",
            "requests",
            "rclpy",
            "sensor_msgs",
            "subprocess",
            "urllib",
        }
        for path in SOURCE_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
                self.assertFalse(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"eval", "exec", "__import__"},
                    f"dynamic execution in {path}",
                )
            self.assertFalse(imported & forbidden_roots, f"forbidden imports in {path}")


if __name__ == "__main__":
    unittest.main()
