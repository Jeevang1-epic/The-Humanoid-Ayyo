cmake_minimum_required(VERSION 3.16)
project(ayyo_manipulation_simulation_execution)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_core REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(shape_msgs REQUIRED)
find_package(srdfdom REQUIRED)
find_package(urdf REQUIRED)

add_executable(stage9c_moveit_preflight src/stage9c_moveit_preflight.cpp)
target_compile_features(stage9c_moveit_preflight PUBLIC cxx_std_17)
target_link_libraries(
  stage9c_moveit_preflight
  nlohmann_json::nlohmann_json
  OpenSSL::Crypto
)
ament_target_dependencies(
  stage9c_moveit_preflight
  geometry_msgs
  moveit_core
  moveit_msgs
  shape_msgs
  srdfdom
  urdf
)

ament_python_install_package(
  ayyo_memory
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../memory/src/ayyo_memory"
)
ament_python_install_package(
  ayyo_personal_context
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../personal_context/src/ayyo_personal_context"
)
ament_python_install_package(
  ayyo_executive
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../executive/src/ayyo_executive"
)
ament_python_install_package(
  ayyo_safety
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../safety_kernel/src/ayyo_safety"
)
ament_python_install_package(
  ayyo_skill_manager
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../skill_manager/src/ayyo_skill_manager"
)
ament_python_install_package(
  ayyo_manipulation_planning
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../manipulation_planning/src/ayyo_manipulation_planning"
)
ament_python_install_package(
  ayyo_manipulation_trajectory
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../manipulation_trajectory/src/ayyo_manipulation_trajectory"
)
ament_python_install_package(
  ayyo_manipulation_simulation_execution
  PACKAGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../manipulation_simulation_execution/src/ayyo_manipulation_simulation_execution"
)

install(TARGETS stage9c_moveit_preflight DESTINATION lib/${PROJECT_NAME})
install(
  PROGRAMS
    scripts/stage9c_execution.py
    scripts/stage9c_reviewed_fixture.py
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  set(AMENT_LINT_AUTO_EXCLUDE ament_cmake_copyright)
  ament_lint_auto_find_test_dependencies()
  find_package(ament_cmake_copyright REQUIRED)
  ament_copyright(
    EXCLUDE
      launch/stage9c_simulation.launch.py
      scripts/stage9c_execution.py
      scripts/stage9c_reviewed_fixture.py
      src/stage9c_moveit_preflight.cpp
      test/test_stage9c_action_adapter.py
      test/test_stage9c_moveit_preflight.py
  )
  ament_add_pytest_test(
    test_stage9c_moveit_preflight
    test/test_stage9c_moveit_preflight.py
    TIMEOUT 90
  )
  ament_add_pytest_test(
    test_stage9c_action_adapter
    test/test_stage9c_action_adapter.py
    TIMEOUT 90
  )
endif()

ament_package()
