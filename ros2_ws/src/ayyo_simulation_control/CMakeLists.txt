cmake_minimum_required(VERSION 3.8)
project(ayyo_simulation_control)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(
  ayyo_simulation_control
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../simulation_control/src/ayyo_simulation_control"
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
