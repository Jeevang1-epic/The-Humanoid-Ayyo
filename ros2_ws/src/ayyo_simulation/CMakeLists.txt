cmake_minimum_required(VERSION 3.8)
project(ayyo_simulation)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY config launch worlds
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  # ament_copyright recognizes only predefined open-source license texts.
  # Keep the repository's declared Proprietary license and retain the test
  # while excluding the proprietary Python sources from that incompatible scan.
  set(AMENT_LINT_AUTO_EXCLUDE ament_cmake_copyright)
  ament_lint_auto_find_test_dependencies()
  find_package(ament_cmake_copyright REQUIRED)
  ament_copyright(
    EXCLUDE
      launch/head_depth_fixture.launch.py
      launch/physical_camera_fixture.launch.py
      launch/simulation.launch.py
      test/test_simulation.py
  )

  ament_add_pytest_test(
    simulation_contract
    test/test_simulation.py
    TIMEOUT 60
  )
endif()

ament_package()
