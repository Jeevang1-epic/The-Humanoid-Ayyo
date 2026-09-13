#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iostream>
#include <memory>
#include <set>
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
#include <nlohmann/json.hpp>
#include <openssl/evp.h>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <srdfdom/model.h>
#include <urdf_parser/urdf_parser.h>

namespace
{
using json = nlohmann::json;

constexpr std::size_t kMaxDescriptionBytes = 1024U * 1024U;
constexpr std::size_t kMaxSemanticBytes = 64U * 1024U;
constexpr std::size_t kMaxInputBytes = 16U * 1024U * 1024U;
constexpr std::size_t kMaxSamples = 4096U;
constexpr std::size_t kMaxCollisionObjects = 32U;
constexpr char kBackendId[] = "moveit.planning-scene.stage9c-preflight.v1";
constexpr char kBackendVersion[] = "moveit-2.12.4";

const std::array<std::string, 4> kJointNames = {
  "left_shoulder_yaw_joint",
  "left_shoulder_pitch_joint",
  "left_elbow_flex_joint",
  "left_wrist_yaw_joint",
};

std::string read_bounded(std::istream & stream, const std::size_t maximum)
{
  std::string value;
  std::array<char, 4096> buffer{};
  while (stream) {
    const std::size_t remaining = maximum - value.size();
    const std::size_t requested = std::min(buffer.size(), remaining + 1U);
    stream.read(buffer.data(), static_cast<std::streamsize>(requested));
    const std::streamsize count = stream.gcount();
    if (count > 0) {
      value.append(buffer.data(), static_cast<std::size_t>(count));
    }
    if (value.size() > maximum) {
      throw std::runtime_error("input violates its Stage 9C byte bound");
    }
  }
  if (stream.bad() || value.empty()) {
    throw std::runtime_error("input violates its Stage 9C byte bound");
  }
  return value;
}

std::string read_file(const std::string & path, const std::size_t maximum)
{
  std::ifstream stream(path);
  if (!stream) {
    throw std::runtime_error("could not read Stage 9C input file");
  }
  return read_bounded(stream, maximum);
}

std::string without_xml_comments(const std::string & document)
{
  std::string result;
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
    throw std::runtime_error("could not initialize Stage 9C digest");
  }
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int size = 0U;
  if (EVP_DigestFinal_ex(context.get(), digest.data(), &size) != 1 || size != 32U) {
    throw std::runtime_error("could not finalize Stage 9C digest");
  }
  constexpr char kHex[] = "0123456789abcdef";
  std::string result;
  result.reserve(64U);
  for (unsigned int index = 0U; index < size; ++index) {
    result.push_back(kHex[digest[index] >> 4U]);
    result.push_back(kHex[digest[index] & 0x0fU]);
  }
  return result;
}

std::string content_fingerprint(const std::string & prefix, const std::string & value)
{
  return prefix + "-sha256-" + sha256_hex(without_xml_comments(value));
}

void exact_keys(
  const json & value,
  const std::set<std::string> & expected,
  const std::string & name)
{
  if (!value.is_object()) {
    throw std::runtime_error(name + " must be an object");
  }
  std::set<std::string> actual;
  for (const auto & item : value.items()) {
    actual.insert(item.key());
  }
  if (actual != expected) {
    throw std::runtime_error(name + " fields differ from its closed schema");
  }
}

std::array<double, 4> positions(const json & raw)
{
  if (!raw.is_array() || raw.size() != kJointNames.size()) {
    throw std::runtime_error("sample must contain exactly four positions");
  }
  std::array<double, 4> result{};
  for (std::size_t index = 0U; index < result.size(); ++index) {
    if (!raw[index].is_number()) {
      throw std::runtime_error("sample positions must be numeric");
    }
    result[index] = raw[index].get<double>();
    if (!std::isfinite(result[index])) {
      throw std::runtime_error("sample positions must be finite");
    }
  }
  return result;
}

void verify_srdf(const srdf::Model & model, const json & input)
{
  if (model.getName() != "ayyo") {
    throw std::runtime_error("SRDF robot identity differs from reviewed semantics");
  }
  const auto & groups = model.getGroups();
  if (groups.size() != 1U || groups[0].name_ != "left_arm" ||
    groups[0].chains_ != std::vector<std::pair<std::string, std::string>>{
      {"left_shoulder_mount_link", "left_hand_link"}})
  {
    throw std::runtime_error("SRDF group differs from reviewed left-arm semantics");
  }
  std::vector<std::array<std::string, 2>> actual;
  for (const auto & raw : model.getDisabledCollisionPairs()) {
    if (raw.reason_ != "Adjacent" || raw.link1_ == raw.link2_) {
      throw std::runtime_error("SRDF allowed-collision entry is not reviewed");
    }
    std::array<std::string, 2> pair = {raw.link1_, raw.link2_};
    if (pair[1] < pair[0]) {
      std::swap(pair[0], pair[1]);
    }
    actual.push_back(pair);
  }
  std::sort(actual.begin(), actual.end());
  std::vector<std::array<std::string, 2>> expected;
  const json & raw_pairs = input.at("disabled_collision_pairs");
  if (!raw_pairs.is_array() || raw_pairs.size() > 64U) {
    throw std::runtime_error("allowed-collision matrix violates its bound");
  }
  for (const json & raw : raw_pairs) {
    if (!raw.is_array() || raw.size() != 2U || !raw[0].is_string() ||
      !raw[1].is_string())
    {
      throw std::runtime_error("allowed-collision matrix is malformed");
    }
    expected.push_back({raw[0].get<std::string>(), raw[1].get<std::string>()});
  }
  std::sort(expected.begin(), expected.end());
  if (actual != expected) {
    throw std::runtime_error("SRDF allowed-collision matrix was substituted");
  }
}

void add_collision_objects(planning_scene::PlanningScene & scene, const json & raw_objects)
{
  if (!raw_objects.is_array() || raw_objects.size() > kMaxCollisionObjects) {
    throw std::runtime_error("collision objects violate their Stage 9C bound");
  }
  for (const json & raw : raw_objects) {
    exact_keys(
      raw,
      {"dimensions_xyz", "frame_id", "object_fingerprint", "object_id",
        "orientation_xyzw", "position_xyz", "schema"},
      "collision object");
    const auto dimensions = raw.at("dimensions_xyz");
    const auto position = raw.at("position_xyz");
    const auto orientation = raw.at("orientation_xyzw");
    if (!dimensions.is_array() || dimensions.size() != 3U || !position.is_array() ||
      position.size() != 3U || !orientation.is_array() || orientation.size() != 4U)
    {
      throw std::runtime_error("collision box vectors are malformed");
    }
    moveit_msgs::msg::CollisionObject object;
    object.header.frame_id = raw.at("frame_id").get<std::string>();
    object.id = raw.at("object_id").get<std::string>();
    object.operation = moveit_msgs::msg::CollisionObject::ADD;
    shape_msgs::msg::SolidPrimitive box;
    box.type = shape_msgs::msg::SolidPrimitive::BOX;
    for (const auto & item : dimensions) {
      const double value = item.get<double>();
      if (!std::isfinite(value) || value <= 0.0 || value > 5.0) {
        throw std::runtime_error("collision box dimensions are invalid");
      }
      box.dimensions.push_back(value);
    }
    geometry_msgs::msg::Pose pose;
    pose.position.x = position[0].get<double>();
    pose.position.y = position[1].get<double>();
    pose.position.z = position[2].get<double>();
    pose.orientation.x = orientation[0].get<double>();
    pose.orientation.y = orientation[1].get<double>();
    pose.orientation.z = orientation[2].get<double>();
    pose.orientation.w = orientation[3].get<double>();
    object.primitives.push_back(box);
    object.primitive_poses.push_back(pose);
    if (!scene.processCollisionObjectMsg(object)) {
      throw std::runtime_error("PlanningScene rejected a collision object");
    }
  }
}

bool collision_free(
  const planning_scene::PlanningScene & scene,
  const moveit::core::RobotState & state,
  const bool self_only)
{
  collision_detection::CollisionRequest request;
  request.group_name = "left_arm";
  request.contacts = false;
  collision_detection::CollisionResult result;
  if (self_only) {
    scene.checkSelfCollision(request, result, state, scene.getAllowedCollisionMatrix());
  } else {
    scene.getCollisionEnv()->checkRobotCollision(
      request, result, state, scene.getAllowedCollisionMatrix());
  }
  return !result.collision;
}
}  // namespace

int main(int argc, char ** argv)
{
  try {
    if (argc != 3) {
      throw std::runtime_error("expected reviewed SRDF and canonical preflight paths");
    }
    const std::string urdf_xml = read_bounded(std::cin, kMaxDescriptionBytes);
    const std::string srdf_xml = read_file(argv[1], kMaxSemanticBytes);
    const std::string input_text = read_file(argv[2], kMaxInputBytes);
    const json input = json::parse(input_text);
    if (input.dump() != input_text) {
      throw std::runtime_error("preflight input is not canonical JSON");
    }
    exact_keys(
      input,
      {"collision_model_fingerprint", "collision_model_id", "collision_objects",
        "disabled_collision_pairs", "execution_request_fingerprint",
        "execution_request_id", "group_fingerprint", "group_id",
        "joint_catalog_fingerprint", "joint_catalog_id", "joint_names",
        "robot_description_content_fingerprint", "robot_model_fingerprint",
        "robot_model_id", "samples", "sampling_policy_fingerprint",
        "scene_fingerprint", "scene_id", "schema", "srdf_content_fingerprint",
        "trajectory_fingerprint", "trajectory_id"},
      "preflight input");
    if (input.at("schema") != json{
        {"id", "ayyo.stage9c.moveit-preflight-input.v1"}, {"version", "1.0.0"}} ||
      input.at("joint_names") != json(kJointNames))
    {
      throw std::runtime_error("preflight identity differs from Stage 9C");
    }
    if (content_fingerprint("ayyo-expanded-urdf-content", urdf_xml) !=
      input.at("robot_description_content_fingerprint").get<std::string>() ||
      content_fingerprint("ayyo-left-arm-srdf-content", srdf_xml) !=
      input.at("srdf_content_fingerprint").get<std::string>())
    {
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
    verify_srdf(*srdf_model, input);
    auto robot_model = std::make_shared<moveit::core::RobotModel>(urdf_model, srdf_model);
    const moveit::core::JointModelGroup * group =
      robot_model->getJointModelGroup("left_arm");
    if (robot_model->getModelFrame() != "base_link" || group == nullptr ||
      group->getVariableNames() != std::vector<std::string>(
        kJointNames.begin(), kJointNames.end()))
    {
      throw std::runtime_error("MoveIt model differs from reviewed Stage 9C chain");
    }
    planning_scene::PlanningScene scene(robot_model);
    add_collision_objects(scene, input.at("collision_objects"));
    moveit::core::RobotState state(robot_model);
    state.setToDefaultValues();

    const json & samples = input.at("samples");
    if (!samples.is_array() || samples.size() < 2U || samples.size() > kMaxSamples) {
      throw std::runtime_error("dense samples violate their Stage 9C bound");
    }
    json reports = json::array();
    for (std::size_t index = 0U; index < samples.size(); ++index) {
      const json & raw = samples[index];
      exact_keys(
        raw,
        {"positions", "sample_index", "segment_fraction", "segment_index",
          "segment_subdivisions", "subdivision_index"},
        "dense sample");
      if (raw.at("sample_index") != index) {
        throw std::runtime_error("dense sample ordering is not canonical");
      }
      const auto sample_positions = positions(raw.at("positions"));
      state.setJointGroupPositions(
        group, std::vector<double>(sample_positions.begin(), sample_positions.end()));
      state.update();
      const bool within_limits = state.satisfiesBounds(group);
      json report = raw;
      report["environment_collision_free"] =
        within_limits && collision_free(scene, state, false);
      report["self_collision_free"] =
        within_limits && collision_free(scene, state, true);
      report["within_joint_limits"] = within_limits;
      reports.push_back(report);
    }

    const std::string input_fingerprint =
      "stage9c-moveit-preflight-input-sha256-" + sha256_hex(input_text);
    const json output = {
      {"backend_id", kBackendId},
      {"backend_version", kBackendVersion},
      {"continuous_collision_certification", false},
      {"execution_disposition", "not_executed"},
      {"input_fingerprint", input_fingerprint},
      {"no_execution_api_used", true},
      {"physical_validation", "absent"},
      {"samples", reports},
      {"samples_checked", reports.size()},
      {"schema", {
        {"id", "ayyo.stage9c.moveit-preflight-report.v1"}, {"version", "1.0.0"}}},
    };
    std::cout << output.dump();
    return 0;
  } catch (const std::exception & error) {
    std::cerr << "Stage 9C MoveIt preflight rejected input: " << error.what() << '\n';
    return 2;
  }
}
