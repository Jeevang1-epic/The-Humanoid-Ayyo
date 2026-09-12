cmake_minimum_required(VERSION 3.16)
project(ayyo_manipulation_planning)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_core REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(shape_msgs REQUIRED)
find_package(srdfdom REQUIRED)
find_package(urdf REQUIRED)

add_executable(moveit_planning_scene_proof src/moveit_planning_scene_proof.cpp)
target_compile_features(moveit_planning_scene_proof PUBLIC cxx_std_17)
target_link_libraries(moveit_planning_scene_proof OpenSSL::Crypto)
ament_target_dependencies(
  moveit_planning_scene_proof
  geometry_msgs
  moveit_core
  moveit_msgs
  shape_msgs
  srdfdom
  urdf
)

install(TARGETS moveit_planning_scene_proof DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY config DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(
    test_moveit_planning_scene_proof
    test/test_moveit_planning_scene_proof.py
    TIMEOUT 60
  )
endif()

ament_package()
