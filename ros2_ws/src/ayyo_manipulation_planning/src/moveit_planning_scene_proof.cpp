#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <geometry_msgs/msg/pose.hpp>
#include <moveit/collision_detection/collision_common.hpp>
#include <moveit/planning_scene/planning_scene.hpp>
#include <moveit/robot_model/robot_model.hpp>
#include <moveit/robot_state/robot_state.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <openssl/evp.h>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <srdfdom/model.h>
#include <urdf_parser/urdf_parser.h>

namespace
{
constexpr std::size_t kMaxDescriptionBytes = 1024U * 1024U;
constexpr std::size_t kMaxSemanticBytes = 64U * 1024U;
constexpr std::size_t kPathSegments = 13U;
constexpr double kInterpolationStep = 0.05;
constexpr std::size_t kMaxWaypoints = 129U;
constexpr int kDeterministicSeed = 0;
constexpr char kUrdfFingerprint[] =
  "ayyo-expanded-urdf-content-sha256-"
  "cc736dfa37535399b739d4e51550f5f76fe63102e037e29aabbb1c2e303ce93f";
constexpr char kSrdfFingerprint[] =
  "ayyo-left-arm-srdf-content-sha256-"
  "43b8163ee53c3694ee79890340611c822b79ddd1cee209a35d5d887163e0e385";

const std::array<std::string, 4> kJointNames = {
  "left_shoulder_yaw_joint",
  "left_shoulder_pitch_joint",
  "left_elbow_flex_joint",
  "left_wrist_yaw_joint",
};
const std::array<double, 4> kStart = {0.0, 0.0, 0.2, 0.0};
const std::array<double, 4> kGoal = {0.3, 0.0, 0.8, 0.2};
const std::array<double, 4> kLower = {-1.2, -1.8, 0.0, -1.5};
const std::array<double, 4> kUpper = {1.2, 1.8, 2.2, 1.5};
const std::array<double, 4> kEffort = {20.0, 20.0, 15.0, 5.0};
const std::array<double, 4> kVelocity = {1.2, 1.2, 1.5, 1.5};
const std::array<std::array<std::string, 2>, 10> kDisabledCollisionPairs = {{
  {"chest_link", "left_shoulder_mount_link"},
  {"left_elbow_link", "left_forearm_link"},
  {"left_elbow_link", "left_upper_arm_link"},
  {"left_forearm_link", "left_hand_link"},
  {"left_forearm_link", "left_upper_arm_link"},
  {"left_forearm_link", "left_wrist_link"},
  {"left_hand_link", "left_wrist_link"},
  {"left_shoulder_mount_link", "left_shoulder_yaw_link"},
  {"left_shoulder_mount_link", "left_upper_arm_link"},
  {"left_shoulder_yaw_link", "left_upper_arm_link"},
}};

std::string read_bounded(std::istream & stream, const std::size_t maximum)
{
  std::string value;
  std::array<char, 4096> buffer{};
  value.reserve(std::min(maximum, buffer.size()));
  while (stream) {
    const std::size_t remaining = maximum - value.size();
    const std::size_t requested = std::min(buffer.size(), remaining + 1U);
    stream.read(buffer.data(), static_cast<std::streamsize>(requested));
    const std::streamsize count = stream.gcount();
    if (count > 0) {
      value.append(buffer.data(), static_cast<std::size_t>(count));
    }
    if (value.size() > maximum) {
      throw std::runtime_error("input violates its planning-proof byte bound");
    }
  }
  if (stream.bad()) {
    throw std::runtime_error("input stream failed during bounded read");
  }
  if (value.empty()) {
    throw std::runtime_error("input violates its planning-proof byte bound");
  }
  return value;
}

std::string without_xml_comments(const std::string & document)
{
  std::string result;
  result.reserve(document.size());
  std::size_t position = 0U;
  while (true) {
    const std::size_t start = document.find("<!--", position);
    if (start == std::string::npos) {
      result.append(document, position, std::string::npos);
      break;
    }
    result.append(document, position, start - position);
    const std::size_t end = document.find("-->", start + 4U);
    if (end == std::string::npos) {
      throw std::runtime_error("description contains an unterminated XML comment");
    }
    position = end + 3U;
  }
  return result;
}

std::string sha256_hex(const std::string & value)
{
  std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> context(
    EVP_MD_CTX_new(), &EVP_MD_CTX_free);
  if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1 ||
    EVP_DigestUpdate(context.get(), value.data(), value.size()) != 1)
  {
    throw std::runtime_error("could not initialize collision-model digest");
  }
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int digest_size = 0U;
  if (EVP_DigestFinal_ex(context.get(), digest.data(), &digest_size) != 1 ||
    digest_size != 32U)
  {
    throw std::runtime_error("could not finalize collision-model digest");
  }
  constexpr char kHex[] = "0123456789abcdef";
  std::string result;
  result.reserve(digest_size * 2U);
  for (unsigned int index = 0U; index < digest_size; ++index) {
    result.push_back(kHex[digest[index] >> 4U]);
    result.push_back(kHex[digest[index] & 0x0fU]);
  }
  return result;
}

std::string content_fingerprint(const std::string & prefix, const std::string & document)
{
  return prefix + "-sha256-" + sha256_hex(without_xml_comments(document));
}

bool exact_double(const double left, const double right)
{
  return std::abs(left - right) < 1e-12;
}

void verify_srdf(const srdf::Model & model)
{
  if (model.getName() != "ayyo") {
    throw std::runtime_error("SRDF robot identity differs from reviewed semantics");
  }
  const std::vector<srdf::Model::Group> & groups = model.getGroups();
  if (groups.size() != 1U || groups[0].name_ != "left_arm" ||
    !groups[0].joints_.empty() || !groups[0].links_.empty() ||
    groups[0].chains_ != std::vector<std::pair<std::string, std::string>>{
      {"left_shoulder_mount_link", "left_hand_link"}} ||
    !groups[0].subgroups_.empty())
  {
    throw std::runtime_error("SRDF group differs from reviewed left-arm semantics");
  }
  if (!model.getVirtualJoints().empty() || !model.getEndEffectors().empty() ||
    !model.getGroupStates().empty() || !model.getPassiveJoints().empty() ||
    !model.getNoDefaultCollisionLinks().empty() ||
    !model.getEnabledCollisionPairs().empty() ||
    !model.getLinkSphereApproximations().empty() || !model.getJointProperties().empty())
  {
    throw std::runtime_error("SRDF contains unreviewed semantic authority");
  }

  std::vector<std::array<std::string, 2>> pairs;
  for (const srdf::Model::CollisionPair & raw : model.getDisabledCollisionPairs()) {
    if (raw.reason_ != "Adjacent" || raw.link1_ == raw.link2_) {
      throw std::runtime_error("SRDF collision exclusion differs from reviewed semantics");
    }
    std::array<std::string, 2> pair = {raw.link1_, raw.link2_};
    if (pair[1] < pair[0]) {
      std::swap(pair[0], pair[1]);
    }
    pairs.push_back(pair);
  }
  std::sort(pairs.begin(), pairs.end());
  if (pairs != std::vector<std::array<std::string, 2>>(
      kDisabledCollisionPairs.begin(), kDisabledCollisionPairs.end()))
  {
    throw std::runtime_error("SRDF allowed-collision matrix was substituted");
  }
}

bool reviewed_limits_match(
  const urdf::ModelInterface & urdf_model,
  const moveit::core::RobotModel & robot_model)
{
  for (std::size_t index = 0U; index < kJointNames.size(); ++index) {
    const urdf::JointConstSharedPtr source = urdf_model.getJoint(kJointNames[index]);
    if (!source || source->type != urdf::Joint::REVOLUTE || !source->limits ||
      !exact_double(source->limits->lower, kLower[index]) ||
      !exact_double(source->limits->upper, kUpper[index]) ||
      !exact_double(source->limits->effort, kEffort[index]) ||
      !exact_double(source->limits->velocity, kVelocity[index]))
    {
      return false;
    }
    const moveit::core::VariableBounds & bounds =
      robot_model.getVariableBounds(kJointNames[index]);
    if (!bounds.position_bounded_ || !bounds.velocity_bounded_ ||
      !exact_double(bounds.min_position_, kLower[index]) ||
      !exact_double(bounds.max_position_, kUpper[index]) ||
      !exact_double(bounds.min_velocity_, -kVelocity[index]) ||
      !exact_double(bounds.max_velocity_, kVelocity[index]))
    {
      return false;
    }
  }
  return true;
}

void add_box(
  planning_scene::PlanningScene & scene,
  const std::string & object_id,
  const std::array<double, 3> & dimensions,
  const std::array<double, 3> & position)
{
  moveit_msgs::msg::CollisionObject object;
  object.header.frame_id = "base_link";
  object.id = object_id;
  object.operation = moveit_msgs::msg::CollisionObject::ADD;
  shape_msgs::msg::SolidPrimitive box;
  box.type = shape_msgs::msg::SolidPrimitive::BOX;
  box.dimensions.assign(dimensions.begin(), dimensions.end());
  geometry_msgs::msg::Pose pose;
  pose.position.x = position[0];
  pose.position.y = position[1];
  pose.position.z = position[2];
  pose.orientation.w = 1.0;
  object.primitives.push_back(box);
  object.primitive_poses.push_back(pose);
  if (!scene.processCollisionObjectMsg(object)) {
    throw std::runtime_error("PlanningScene rejected a reviewed collision object");
  }
}

void set_group_positions(
  moveit::core::RobotState & state,
  const moveit::core::JointModelGroup * group,
  const std::array<double, 4> & values)
{
  state.setJointGroupPositions(group, std::vector<double>(values.begin(), values.end()));
  state.update();
}

bool self_collision_free(
  const planning_scene::PlanningScene & scene,
  const moveit::core::RobotState & state)
{
  collision_detection::CollisionRequest request;
  request.group_name = "left_arm";
  request.contacts = false;
  collision_detection::CollisionResult result;
  scene.checkSelfCollision(request, result, state, scene.getAllowedCollisionMatrix());
  return !result.collision;
}

bool environment_collision_free(
  const planning_scene::PlanningScene & scene,
  const moveit::core::RobotState & state)
{
  collision_detection::CollisionRequest request;
  request.group_name = "left_arm";
  request.contacts = false;
  collision_detection::CollisionResult result;
  scene.getCollisionEnv()->checkRobotCollision(
    request, result, state, scene.getAllowedCollisionMatrix());
  return !result.collision;
}

std::array<double, 4> waypoint(const std::size_t index)
{
  const double fraction = static_cast<double>(index) / static_cast<double>(kPathSegments);
  std::array<double, 4> result{};
  for (std::size_t joint = 0U; joint < result.size(); ++joint) {
    result[joint] = kStart[joint] + ((kGoal[joint] - kStart[joint]) * fraction);
  }
  return result;
}

std::string json_double(const double value)
{
  std::array<char, 32> buffer{};
  const auto conversion = std::to_chars(
    buffer.data(), buffer.data() + buffer.size(), value, std::chars_format::general);
  if (conversion.ec != std::errc{}) {
    throw std::runtime_error("could not serialize collision-proof number");
  }
  std::string result(buffer.data(), conversion.ptr);
  if (result.find_first_of(".eE") == std::string::npos) {
    result += ".0";
  }
  return result;
}

void write_bool_array(const std::vector<bool> & values)
{
  std::cout << '[';
  for (std::size_t index = 0U; index < values.size(); ++index) {
    if (index != 0U) {
      std::cout << ',';
    }
    std::cout << (values[index] ? "true" : "false");
  }
  std::cout << ']';
}

void write_waypoints(const std::vector<std::array<double, 4>> & waypoints)
{
  std::cout << '[';
  for (std::size_t index = 0U; index < waypoints.size(); ++index) {
    if (index != 0U) {
      std::cout << ',';
    }
    std::cout << '[';
    for (std::size_t joint = 0U; joint < waypoints[index].size(); ++joint) {
      if (joint != 0U) {
        std::cout << ',';
      }
      std::cout << json_double(waypoints[index][joint]);
    }
    std::cout << ']';
  }
  std::cout << ']';
}

void write_disabled_pairs()
{
  std::cout << '[';
  for (std::size_t index = 0U; index < kDisabledCollisionPairs.size(); ++index) {
    if (index != 0U) {
      std::cout << ',';
    }
    std::cout << "[\"" << kDisabledCollisionPairs[index][0] << "\",\""
              << kDisabledCollisionPairs[index][1] << "\"]";
  }
  std::cout << ']';
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
    const std::string urdf_fingerprint = content_fingerprint(
      "ayyo-expanded-urdf-content", urdf_xml);
    const std::string srdf_fingerprint = content_fingerprint(
      "ayyo-left-arm-srdf-content", srdf_xml);
    if (urdf_fingerprint != kUrdfFingerprint || srdf_fingerprint != kSrdfFingerprint) {
      throw std::runtime_error("collision-model description fingerprint is not reviewed");
    }

    const urdf::ModelInterfaceSharedPtr urdf_model = urdf::parseURDF(urdf_xml);
    if (!urdf_model || urdf_model->getName() != "ayyo") {
      throw std::runtime_error("invalid Ayyo URDF");
    }
    auto srdf_model = std::make_shared<srdf::Model>();
    if (!srdf_model->initString(*urdf_model, srdf_xml)) {
      throw std::runtime_error("invalid Ayyo SRDF");
    }
    verify_srdf(*srdf_model);
    auto robot_model = std::make_shared<moveit::core::RobotModel>(urdf_model, srdf_model);
    const moveit::core::JointModelGroup * group = robot_model->getJointModelGroup("left_arm");
    if (robot_model->getModelFrame() != "base_link" || group == nullptr ||
      group->getVariableNames() != std::vector<std::string>(kJointNames.begin(), kJointNames.end()))
    {
      throw std::runtime_error("MoveIt model differs from the reviewed left-arm chain");
    }
    const bool limits_match_reviewed = reviewed_limits_match(*urdf_model, *robot_model);

    planning_scene::PlanningScene scene(robot_model);
    add_box(scene, "review-box", {0.1, 0.1, 0.1}, {1.0, 0.0, 0.5});
    moveit::core::RobotState state(robot_model);
    state.setToDefaultValues();
    std::vector<std::array<double, 4>> waypoints;
    std::vector<bool> self_results;
    std::vector<bool> environment_results;
    for (std::size_t index = 0U; index <= kPathSegments; ++index) {
      waypoints.push_back(waypoint(index));
      set_group_positions(state, group, waypoints.back());
      self_results.push_back(state.satisfiesBounds(group) && self_collision_free(scene, state));
      environment_results.push_back(
        state.satisfiesBounds(group) && environment_collision_free(scene, state));
    }

    set_group_positions(state, group, kGoal);
    const Eigen::Vector3d hand_position =
      state.getGlobalLinkTransform("left_hand_link").translation();
    add_box(
      scene,
      "goal-hand-blocker",
      {0.12, 0.12, 0.12},
      {hand_position.x(), hand_position.y(), hand_position.z()});
    const bool goal_obstacle_collision_reported = !environment_collision_free(scene, state);
    const bool passed = limits_match_reviewed &&
      std::all_of(self_results.begin(), self_results.end(), [](const bool value) {return value;}) &&
      std::all_of(
      environment_results.begin(), environment_results.end(), [](const bool value) {return value;}) &&
      goal_obstacle_collision_reported;

    std::cout << "{\"backend_id\":\"moveit.planning-scene.v1\","
              << "\"backend_version\":\"moveit-2.12.4\","
              << "\"collision_objects\":[{\"dimensions_xyz\":[0.1,0.1,0.1],"
              << "\"frame_id\":\"base_link\",\"object_id\":\"review-box\","
              << "\"orientation_xyzw\":[0.0,0.0,0.0,1.0],"
              << "\"position_xyz\":[1.0,0.0,0.5]}],"
              << "\"deterministic_seed\":" << kDeterministicSeed
              << ",\"disabled_collision_pairs\":";
    write_disabled_pairs();
    std::cout << ",\"environment_collision_free\":";
    write_bool_array(environment_results);
    std::cout << ",\"execution_disposition\":\"not_executed\","
              << "\"goal_obstacle_collision_reported\":"
              << (goal_obstacle_collision_reported ? "true" : "false") << ','
              << "\"group_name\":\"left_arm\",\"interpolation_step\":"
              << json_double(kInterpolationStep)
              << ",\"joint_names\":[\"left_shoulder_yaw_joint\","
              << "\"left_shoulder_pitch_joint\",\"left_elbow_flex_joint\","
              << "\"left_wrist_yaw_joint\"],\"limits_match_reviewed\":"
              << (limits_match_reviewed ? "true" : "false") << ','
              << "\"max_waypoints\":" << kMaxWaypoints
              << ",\"model_frame\":\"base_link\","
              << "\"no_execution_api_used\":true,\"physical_validation\":\"absent\","
              << "\"planner_id\":\"ayyo.bounded-linear-joint-space.v1\","
              << "\"result\":\""
              << (passed ? "plan_available_for_review" : "rejected") << "\","
              << "\"robot_description_content_fingerprint\":\"" << urdf_fingerprint << "\","
              << "\"samples_checked\":" << waypoints.size() << ','
              << "\"schema\":{\"id\":\"ayyo.moveit-planning-scene-proof.v1\","
              << "\"version\":\"1.0.0\"},\"self_collision_free\":";
    write_bool_array(self_results);
    std::cout << ",\"srdf_content_fingerprint\":\"" << srdf_fingerprint
              << "\",\"waypoints\":";
    write_waypoints(waypoints);
    std::cout << '}';
    return passed ? 0 : 1;
  } catch (const std::exception & error) {
    std::cerr << "planning-scene proof rejected input: " << error.what() << '\n';
    return 2;
  }
}
