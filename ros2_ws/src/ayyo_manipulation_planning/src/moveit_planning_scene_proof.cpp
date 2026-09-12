#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include <geometry_msgs/msg/pose.hpp>
#include <moveit/collision_detection/collision_common.hpp>
#include <moveit/planning_scene/planning_scene.hpp>
#include <moveit/robot_model/robot_model.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <srdfdom/model.h>
#include <urdf_parser/urdf_parser.h>

namespace
{
constexpr std::size_t kMaxDescriptionBytes = 1024U * 1024U;
constexpr std::size_t kMaxSemanticBytes = 64U * 1024U;
constexpr std::size_t kPathSegments = 20U;
const std::array<std::string, 4> kJointNames = {
  "left_shoulder_yaw_joint",
  "left_shoulder_pitch_joint",
  "left_elbow_flex_joint",
  "left_wrist_yaw_joint",
};
const std::array<double, 4> kStart = {0.0, 0.0, 0.2, 0.0};
const std::array<double, 4> kGoal = {0.3, 0.4, 0.8, 0.2};

std::string read_bounded(std::istream & stream, const std::size_t maximum)
{
  std::string value{
    std::istreambuf_iterator<char>(stream),
    std::istreambuf_iterator<char>()};
  if (value.empty() || value.size() > maximum) {
    throw std::runtime_error("input violates its planning-proof byte bound");
  }
  return value;
}

bool collision_free(
  const planning_scene::PlanningScene & scene,
  const moveit::core::RobotState & state)
{
  collision_detection::CollisionRequest request;
  request.group_name = "left_arm";
  request.contacts = false;
  collision_detection::CollisionResult result;
  scene.checkCollision(request, result, state);
  return !result.collision;
}

void set_group_positions(
  moveit::core::RobotState & state,
  const moveit::core::JointModelGroup * group,
  const std::array<double, 4> & values)
{
  state.setJointGroupPositions(group, std::vector<double>(values.begin(), values.end()));
  state.update();
}
}  // namespace

int main(int argc, char ** argv)
{
  try {
    if (argc != 2) {
      throw std::runtime_error("expected one reviewed SRDF path argument");
    }
    const std::string urdf_xml = read_bounded(std::cin, kMaxDescriptionBytes);
    std::ifstream semantic_stream(argv[1]);
    if (!semantic_stream) {
      throw std::runtime_error("could not read reviewed semantic description");
    }
    const std::string srdf_xml = read_bounded(semantic_stream, kMaxSemanticBytes);

    const urdf::ModelInterfaceSharedPtr urdf_model = urdf::parseURDF(urdf_xml);
    if (!urdf_model || urdf_model->getName() != "ayyo") {
      throw std::runtime_error("invalid Ayyo URDF");
    }
    auto srdf_model = std::make_shared<srdf::Model>();
    if (!srdf_model->initString(*urdf_model, srdf_xml)) {
      throw std::runtime_error("invalid Ayyo SRDF");
    }
    auto robot_model = std::make_shared<moveit::core::RobotModel>(urdf_model, srdf_model);
    const moveit::core::JointModelGroup * group = robot_model->getJointModelGroup("left_arm");
    if (group == nullptr || group->getVariableNames() != std::vector<std::string>(kJointNames.begin(), kJointNames.end())) {
      throw std::runtime_error("MoveIt group differs from the reviewed left-arm chain");
    }

    bool exact_limits = true;
    for (std::size_t index = 0; index < kJointNames.size(); ++index) {
      const moveit::core::VariableBounds & bounds = robot_model->getVariableBounds(kJointNames[index]);
      const urdf::JointConstSharedPtr source_joint = urdf_model->getJoint(kJointNames[index]);
      exact_limits = exact_limits && source_joint && source_joint->limits && bounds.position_bounded_ &&
        std::abs(bounds.min_position_ - source_joint->limits->lower) < 1e-12 &&
        std::abs(bounds.max_position_ - source_joint->limits->upper) < 1e-12;
    }

    planning_scene::PlanningScene scene(robot_model);
    moveit::core::RobotState state(robot_model);
    state.setToDefaultValues();
    set_group_positions(state, group, kStart);
    const bool start_in_bounds = state.satisfiesBounds(group);
    const bool start_collision_free = collision_free(scene, state);

    set_group_positions(state, group, kGoal);
    const bool goal_in_bounds = state.satisfiesBounds(group);
    const bool goal_collision_free = collision_free(scene, state);

    bool path_collision_free = start_collision_free && goal_collision_free;
    for (std::size_t segment = 0; segment <= kPathSegments; ++segment) {
      const double fraction = static_cast<double>(segment) / static_cast<double>(kPathSegments);
      std::array<double, 4> sample{};
      for (std::size_t joint = 0; joint < sample.size(); ++joint) {
        sample[joint] = kStart[joint] + ((kGoal[joint] - kStart[joint]) * fraction);
      }
      set_group_positions(state, group, sample);
      path_collision_free = path_collision_free && state.satisfiesBounds(group) && collision_free(scene, state);
    }

    set_group_positions(state, group, kGoal);
    const Eigen::Vector3d hand_position = state.getGlobalLinkTransform("left_hand_link").translation();
    moveit_msgs::msg::CollisionObject obstacle;
    obstacle.header.frame_id = "base_link";
    obstacle.id = "goal-hand-blocker";
    obstacle.operation = moveit_msgs::msg::CollisionObject::ADD;
    shape_msgs::msg::SolidPrimitive box;
    box.type = shape_msgs::msg::SolidPrimitive::BOX;
    box.dimensions = {0.12, 0.12, 0.12};
    geometry_msgs::msg::Pose pose;
    pose.position.x = hand_position.x();
    pose.position.y = hand_position.y();
    pose.position.z = hand_position.z();
    pose.orientation.w = 1.0;
    obstacle.primitives.push_back(box);
    obstacle.primitive_poses.push_back(pose);
    const bool object_accepted = scene.processCollisionObjectMsg(obstacle);
    const bool goal_obstacle_collision_reported = object_accepted && !collision_free(scene, state);

    const bool passed = exact_limits && start_in_bounds && goal_in_bounds &&
      start_collision_free && goal_collision_free && path_collision_free &&
      goal_obstacle_collision_reported;
    std::cout << std::boolalpha << std::setprecision(17)
              << "{\"backend\":\"moveit-planning-scene\","
              << "\"group\":\"left_arm\","
              << "\"goal_collision_free_without_object\":" << goal_collision_free << ','
              << "\"goal_obstacle_collision_reported\":" << goal_obstacle_collision_reported << ','
              << "\"joint_count\":" << kJointNames.size() << ','
              << "\"limits_exact\":" << exact_limits << ','
              << "\"model_frame\":\"" << robot_model->getModelFrame() << "\","
              << "\"no_execution_api_used\":true,"
              << "\"passed\":" << passed << ','
              << "\"path_collision_free\":" << path_collision_free << ','
              << "\"samples_checked\":" << (kPathSegments + 1U) << ','
              << "\"start_collision_free\":" << start_collision_free
              << "}\n";
    return passed ? 0 : 1;
  } catch (const std::exception & error) {
    std::cerr << "planning-scene proof rejected input: " << error.what() << '\n';
    return 2;
  }
}
