cmake_minimum_required(VERSION 3.8)
project(ayyo_runtime_bridge)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(
  ayyo_runtime_bridge
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../runtime_bridge/src/ayyo_runtime_bridge"
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
