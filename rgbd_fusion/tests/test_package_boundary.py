from pathlib import Path


def test_core_has_no_ros_or_authority_dependencies() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("rgbd_fusion/src/ayyo_rgbd_fusion").glob("*.py")
    )
    for forbidden in (
        "import rclpy",
        "sensor_msgs",
        "geometry_msgs",
        "cmd_vel",
        "trajectory",
        "ayyo_safety_kernel",
        "ayyo_skill_manager",
        "ayyo_executive",
        "ayyo_memory",
    ):
        assert forbidden not in source
