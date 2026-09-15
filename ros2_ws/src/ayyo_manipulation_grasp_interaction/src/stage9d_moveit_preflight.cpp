// Copyright 2026 P. Jeevan Kumar

#include <openssl/evp.h>
#include <srdfdom/model.h>
#include <urdf_parser/urdf_parser.h>

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
#include <moveit_msgs/msg/attached_collision_object.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <nlohmann/json.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>

namespace
{
using json = nlohmann::json;

constexpr std::size_t kMaxDescriptionBytes = 1024U * 1024U;
constexpr std::size_t kMaxSemanticBytes = 64U * 1024U;
constexpr std::size_t kMaxInputBytes = 16U * 1024U * 1024U;
constexpr std::size_t kMaxSamples = 4096U;
constexpr std::size_t kMaxCollisionObjects = 32U;
constexpr char kBackendId[] = "moveit.planning-scene.stage9d-attached-object.v1";
constexpr char kBackendVersion[] = "moveit-2.12.4";
constexpr char kHandLink[] = "left_hand_link";
constexpr char kObjectCollision[] =
  "stage9d_grasp_object::stage9d_grasp_object_link::stage9d_grasp_object_collision";

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
      throw std::runtime_error("input violates its Stage 9D byte bound");
    }
  }
  if (stream.bad() || value.empty()) {
    throw std::runtime_error("input violates its Stage 9D byte bound");
  }
  return value;
}

std::string read_file(const std::string & path, const std::size_t maximum)
{
  std::ifstream stream(path);
  if (!stream) {
    throw std::runtime_error("could not read Stage 9D input file");
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
      throw std::runtime_error("description has an unterminated XML comment");
    }
    position = end + 3U;
  }
  return result;
}

std::string sha256_hex(const std::string & value)
{
  std::unique_ptr<EVP_MD_CTX, decltype(& EVP_MD_CTX_free)> context(
    EVP_MD_CTX_new(), &EVP_MD_CTX_free);
  if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1 ||
    EVP_DigestUpdate(context.get(), value.data(), value.size()) != 1)
  {
    throw std::runtime_error("could not initialize Stage 9D digest");
  }
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int size = 0U;
  if (EVP_DigestFinal_ex(context.get(), digest.data(), &size) != 1 || size != 32U) {
    throw std::runtime_error("could not finalize Stage 9D digest");
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

double finite_number(const json & value, const std::string & name)
{
  if (!value.is_number()) {
    throw std::runtime_error(name + " must be numeric");
  }
  const double result = value.get<double>();
  if (!std::isfinite(result)) {
    throw std::runtime_error(name + " must be finite");
  }
  return result;
}

void verify_srdf(const srdf::Model & model, const json & input)
{
  if (model.getName() != "ayyo") {
    throw std::runtime_error("SRDF robot identity differs from Stage 9D");
  }
  const auto & groups = model.getGroups();
  if (groups.size() != 1U || groups[0].name_ != "left_arm" ||
    groups[0].chains_ != std::vector<std::pair<std::string, std::string>>{
      {"left_shoulder_mount_link", kHandLink}})
  {
    throw std::runtime_error("SRDF group differs from reviewed left arm");
  }
  std::vector<std::array<std::string, 2>> actual;
  for (const auto & raw : model.getDisabledCollisionPairs()) {
    if (raw.reason_ != "Adjacent" || raw.link1_ == raw.link2_) {
      throw std::runtime_error("SRDF collision exception is not reviewed");
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

geometry_msgs::msg::Pose box_pose(const json & position, const json & orientation)
{
  if (!position.is_array() || position.size() != 3U || !orientation.is_array() ||
    orientation.size() != 4U)
  {
    throw std::runtime_error("collision pose vectors are malformed");
  }
  geometry_msgs::msg::Pose pose;
  pose.position.x = finite_number(position[0], "pose position");
  pose.position.y = finite_number(position[1], "pose position");
  pose.position.z = finite_number(position[2], "pose position");
  pose.orientation.x = finite_number(orientation[0], "pose orientation");
  pose.orientation.y = finite_number(orientation[1], "pose orientation");
  pose.orientation.z = finite_number(orientation[2], "pose orientation");
  pose.orientation.w = finite_number(orientation[3], "pose orientation");
  const double norm = std::sqrt(
    pose.orientation.x * pose.orientation.x +
    pose.orientation.y * pose.orientation.y +
    pose.orientation.z * pose.orientation.z +
    pose.orientation.w * pose.orientation.w);
  if (std::abs(norm - 1.0) > 1e-6) {
    throw std::runtime_error("collision orientation is not normalized");
  }
  return pose;
}

shape_msgs::msg::SolidPrimitive box_shape(const json & dimensions)
{
  if (!dimensions.is_array() || dimensions.size() != 3U) {
    throw std::runtime_error("collision dimensions are malformed");
  }
  shape_msgs::msg::SolidPrimitive box;
  box.type = shape_msgs::msg::SolidPrimitive::BOX;
  for (const auto & item : dimensions) {
    const double value = finite_number(item, "collision dimension");
    if (value <= 0.0 || value > 5.0) {
      throw std::runtime_error("collision dimension is outside its bound");
    }
    box.dimensions.push_back(value);
  }
  return box;
}

void add_environment(planning_scene::PlanningScene & scene, const json & objects)
{
  if (!objects.is_array() || objects.size() > kMaxCollisionObjects) {
    throw std::runtime_error("collision objects violate their bound");
  }
  for (const json & raw : objects) {
    exact_keys(
      raw,
      {"dimensions_xyz", "frame_id", "object_fingerprint", "object_id",
        "orientation_xyzw", "position_xyz", "schema"},
      "collision object");
    moveit_msgs::msg::CollisionObject object;
    object.header.frame_id = raw.at("frame_id").get<std::string>();
    object.id = raw.at("object_id").get<std::string>();
    object.operation = moveit_msgs::msg::CollisionObject::ADD;
    object.primitives.push_back(box_shape(raw.at("dimensions_xyz")));
    object.primitive_poses.push_back(
      box_pose(raw.at("position_xyz"), raw.at("orientation_xyzw")));
    if (!scene.processCollisionObjectMsg(object)) {
      throw std::runtime_error("PlanningScene rejected an environment object");
    }
  }
}

void attach_reviewed_object(planning_scene::PlanningScene & scene, const json & raw)
{
  exact_keys(
    raw,
    {"collision_name", "dimensions_xyz", "object_id",
      "relative_orientation_xyzw", "relative_position_xyz", "touch_links"},
    "attached object");
  if (raw.at("collision_name") != kObjectCollision ||
    raw.at("touch_links") != json::array({kHandLink}) ||
    raw.at("dimensions_xyz") != json::array({0.03, 0.03, 0.02}))
  {
    throw std::runtime_error("attached object differs from the Stage 9D primitive");
  }
  moveit_msgs::msg::AttachedCollisionObject attached;
  attached.link_name = kHandLink;
  attached.touch_links = {kHandLink};
  attached.object.header.frame_id = kHandLink;
  attached.object.id = kObjectCollision;
  attached.object.operation = moveit_msgs::msg::CollisionObject::ADD;
  attached.object.primitives.push_back(box_shape(raw.at("dimensions_xyz")));
  attached.object.primitive_poses.push_back(box_pose(
      raw.at("relative_position_xyz"), raw.at("relative_orientation_xyzw")));
  if (!scene.processAttachedCollisionObjectMsg(attached) ||
    !scene.getCurrentState().hasAttachedBody(kObjectCollision))
  {
    throw std::runtime_error("PlanningScene rejected the reviewed attached object");
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
      throw std::runtime_error("expected reviewed SRDF and canonical input paths");
    }
    const std::string urdf_xml = read_bounded(std::cin, kMaxDescriptionBytes);
    const std::string srdf_xml = read_file(argv[1], kMaxSemanticBytes);
    const std::string input_text = read_file(argv[2], kMaxInputBytes);
    const json input = json::parse(input_text);
    if (input.dump() != input_text) {
      throw std::runtime_error("interaction input is not canonical JSON");
    }
    exact_keys(
      input,
      {"attached_object", "collision_objects", "disabled_collision_pairs",
        "execution_request_fingerprint", "execution_request_id",
        "grasp_evidence_fingerprint", "grasp_evidence_id",
        "interaction_request_fingerprint", "interaction_request_id", "joint_names",
        "robot_description_content_fingerprint", "robot_model_fingerprint",
        "robot_model_id", "samples", "schema", "srdf_content_fingerprint"},
      "interaction input");
    if (input.at("schema") != json{
      {"id", "ayyo.stage9d.moveit-interaction-preflight-input.v1"},
      {"version", "1.0.0"}} || input.at("joint_names") != json(kJointNames))
    {
      throw std::runtime_error("interaction identity differs from Stage 9D");
    }
    if (content_fingerprint("ayyo-expanded-urdf-content", urdf_xml) !=
      input.at("robot_description_content_fingerprint").get<std::string>() ||
      content_fingerprint("ayyo-left-arm-srdf-content", srdf_xml) !=
      input.at("srdf_content_fingerprint").get<std::string>())
    {
      throw std::runtime_error("interaction descriptions are not reviewed");
    }
    const auto urdf_model = urdf::parseURDF(urdf_xml);
    if (!urdf_model || urdf_model->getName() != "ayyo") {
      throw std::runtime_error("invalid Ayyo URDF");
    }
    auto srdf_model = std::make_shared<srdf::Model>();
    if (!srdf_model->initString(*urdf_model, srdf_xml)) {
      throw std::runtime_error("invalid Ayyo SRDF");
    }
    verify_srdf(*srdf_model, input);
    auto robot_model = std::make_shared<moveit::core::RobotModel>(urdf_model, srdf_model);
    const auto * group = robot_model->getJointModelGroup("left_arm");
    if (robot_model->getModelFrame() != "base_link" || group == nullptr ||
      group->getVariableNames() != std::vector<std::string>(
        kJointNames.begin(), kJointNames.end()))
    {
      throw std::runtime_error("MoveIt model differs from the Stage 9C chain");
    }
    planning_scene::PlanningScene scene(robot_model);
    add_environment(scene, input.at("collision_objects"));
    attach_reviewed_object(scene, input.at("attached_object"));
    moveit::core::RobotState & state = scene.getCurrentStateNonConst();
    state.setToDefaultValues();

    const json & samples = input.at("samples");
    if (!samples.is_array() || samples.size() < 2U || samples.size() > kMaxSamples) {
      throw std::runtime_error("dense samples violate their Stage 9D bound");
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
      reports.push_back({
        {"attached_object_checked", state.hasAttachedBody(kObjectCollision)},
        {"environment_collision_free", within_limits && collision_free(scene, state, false)},
        {"positions", raw.at("positions")},
        {"sample_index", index},
        {"self_collision_free", within_limits && collision_free(scene, state, true)},
        {"within_joint_limits", within_limits},
      });
    }
    const json output = {
      {"allowed_collision_pair", json::array({kHandLink, kObjectCollision})},
      {"allowed_touch_links", json::array({kHandLink})},
      {"backend_id", kBackendId},
      {"backend_version", kBackendVersion},
      {"continuous_collision_certification", false},
      {"global_acm_modified", false},
      {"grasp_interval_only", true},
      {"input_fingerprint", "stage9d-moveit-interaction-input-sha256-" +
        sha256_hex(input_text)},
      {"physical_collision_certification", false},
      {"samples", reports},
      {"samples_checked", reports.size()},
      {"schema", {
          {"id", "ayyo.stage9d.moveit-interaction-preflight-report.v1"},
          {"version", "1.0.0"}}},
      {"target_object_specific", true},
    };
    std::cout << output.dump();
    return 0;
  } catch (const std::exception & error) {
    std::cerr << "Stage 9D MoveIt preflight rejected input: " << error.what() << '\n';
    return 2;
  }
}
