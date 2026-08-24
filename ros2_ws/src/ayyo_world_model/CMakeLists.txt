cmake_minimum_required(VERSION 3.8)
project(ayyo_world_model)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

ament_python_install_package(
  ayyo_world_model
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../world_model/src/ayyo_world_model"
)
ament_python_install_package(
  ayyo_working_memory
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../working_memory/src/ayyo_working_memory"
)

install(
  PROGRAMS
    scripts/body_state_query.py
    scripts/world_model_node.py
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
      scripts/body_state_query.py
      scripts/world_model_node.py
      test/test_ros_adapter.py
  )
  ament_add_pytest_test(
    world_model_ros_contract
    test/test_ros_adapter.py
    TIMEOUT 60
  )
endif()

ament_package()
