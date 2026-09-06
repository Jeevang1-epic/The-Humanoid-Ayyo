cmake_minimum_required(VERSION 3.8)
project(ayyo_scenarios)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(
  ayyo_developmental_scenarios
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../developmental_scenarios/src/ayyo_developmental_scenarios"
)

install(
  DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS
    scripts/production_motion_probe.py
    scripts/scenario_report.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  set(AMENT_LINT_AUTO_EXCLUDE ament_cmake_copyright)
  ament_lint_auto_find_test_dependencies()
  find_package(ament_cmake_copyright REQUIRED)
  ament_copyright(
    EXCLUDE
      launch/developmental_scenarios.launch.py
      scripts/production_motion_probe.py
      scripts/scenario_report.py
      test/test_scenario_ros_package.py
  )
  ament_add_pytest_test(
    developmental_scenario_ros_contract
    test/test_scenario_ros_package.py
    TIMEOUT 60
  )
endif()

ament_package()
