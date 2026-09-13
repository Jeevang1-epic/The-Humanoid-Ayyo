cmake_minimum_required(VERSION 3.16)
project(ayyo_manipulation_simulation_execution)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

find_package(ament_cmake REQUIRED)
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

install(TARGETS stage9c_moveit_preflight DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(
    test_stage9c_moveit_preflight
    test/test_stage9c_moveit_preflight.py
    TIMEOUT 90
  )
endif()

ament_package()
