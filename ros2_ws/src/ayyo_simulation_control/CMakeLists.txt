cmake_minimum_required(VERSION 3.8)
project(ayyo_simulation_control)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(
  ayyo_simulation_control
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../simulation_control/src/ayyo_simulation_control"
)

install(
  PROGRAMS
    scripts/development_command.py
    scripts/simulation_control_node.py
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
      scripts/development_command.py
      scripts/simulation_control_node.py
      test/test_ros_adapter.py
  )

  ament_add_pytest_test(
    simulation_control_ros_contract
    test/test_ros_adapter.py
    TIMEOUT 60
  )
endif()

ament_package()
