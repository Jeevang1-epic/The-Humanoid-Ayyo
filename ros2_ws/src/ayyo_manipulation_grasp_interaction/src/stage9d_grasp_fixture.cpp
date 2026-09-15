// Copyright 2026 P. Jeevan Kumar

#include <gz/msgs/contacts.pb.h>
#include <gz/msgs/empty.pb.h>
#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/stringmsg.pb.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <mutex>
#include <string>

#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/DetachableJoint.hh>
#include <gz/sim/components/ExternalWorldWrenchCmd.hh>
#include <gz/sim/components/Link.hh>
#include <gz/sim/components/Model.hh>
#include <gz/transport/Node.hh>

namespace ayyo::stage9d
{
namespace
{
constexpr char kRobotModel[] = "ayyo";
constexpr char kPhysicalHandLink[] = "left_wrist_link";
constexpr char kObjectModel[] = "stage9d_grasp_object";
constexpr char kObjectLink[] = "stage9d_grasp_object_link";
constexpr char kHandCollision[] =
  "ayyo::left_wrist_link::"
  "left_wrist_link_fixed_joint_lump__left_hand_link_collision_1";
constexpr char kObjectCollision[] =
  "stage9d_grasp_object::stage9d_grasp_object_link::stage9d_grasp_object_collision";
constexpr char kContactTopic[] = "/ayyo/stage9d/grasp_object/contacts";
constexpr char kAttachTopic[] = "/ayyo/stage9d/grasp_fixture/attach";
constexpr char kDetachTopic[] = "/ayyo/stage9d/grasp_fixture/detach";
constexpr char kStateTopic[] = "/ayyo/stage9d/grasp_fixture/state";
constexpr char kPoseTopic[] = "/ayyo/stage9d/grasp_fixture/entity_poses";
constexpr char kEndEffectorEntity[] = "ayyo::left_hand_link";
constexpr std::size_t kMaximumContactEntries = 16U;
constexpr double kExpectedRelativeX = 0.02;
constexpr double kExpectedRelativeY = 0.0;
constexpr double kExpectedRelativeZ = -0.17;
constexpr double kEndEffectorOffsetZ = -0.08;
constexpr double kTranslationTolerance = 0.012;
constexpr double kRotationTolerance = 0.10;
// A fixed, open-loop simulation staging preload keeps the gravity-enabled
// primitive against the reviewed terminal surface until the first attach.
// It is removed permanently before Stage 9C motion and is not force evidence.
constexpr double kPregraspPreloadForceZ = 0.55;
constexpr std::chrono::nanoseconds kContactFreshness{250000000};
constexpr std::chrono::nanoseconds kPublishPeriod{50000000};

bool reviewed_pair(const std::string & first, const std::string & second)
{
  return (first == kHandCollision && second == kObjectCollision) ||
         (first == kObjectCollision && second == kHandCollision);
}

void set_header(
  gz::msgs::Header * header,
  const std::chrono::steady_clock::duration & observed_at,
  const std::string & child_frame)
{
  const auto nanoseconds =
    std::chrono::duration_cast<std::chrono::nanoseconds>(observed_at).count();
  header->mutable_stamp()->set_sec(nanoseconds / 1000000000LL);
  header->mutable_stamp()->set_nsec(nanoseconds % 1000000000LL);
  auto * frame = header->add_data();
  frame->set_key("frame_id");
  frame->add_value("world");
  auto * child = header->add_data();
  child->set_key("child_frame_id");
  child->add_value(child_frame);
}

void set_pose(
  gz::msgs::Pose * message,
  const std::string & name,
  const gz::math::Pose3d & pose,
  const std::chrono::steady_clock::duration & observed_at)
{
  message->set_name(name);
  set_header(message->mutable_header(), observed_at, name);
  message->mutable_position()->set_x(pose.Pos().X());
  message->mutable_position()->set_y(pose.Pos().Y());
  message->mutable_position()->set_z(pose.Pos().Z());
  message->mutable_orientation()->set_x(pose.Rot().X());
  message->mutable_orientation()->set_y(pose.Rot().Y());
  message->mutable_orientation()->set_z(pose.Rot().Z());
  message->mutable_orientation()->set_w(pose.Rot().W());
}
}  // namespace

class GraspFixture final
  : public gz::sim::System,
  public gz::sim::ISystemConfigure,
  public gz::sim::ISystemPreUpdate
{
public:
  void Configure(
    const gz::sim::Entity & entity,
    const std::shared_ptr<const sdf::Element> &,
    gz::sim::EntityComponentManager & ecm,
    gz::sim::EventManager &) override
  {
    gz::sim::Model object_model(entity);
    if (!object_model.Valid(ecm) || object_model.Name(ecm) != kObjectModel) {
      gzerr << "Stage 9D fixture rejected a non-reviewed object model\n";
      return;
    }
    this->object_model_entity_ = entity;
    this->object_link_entity_ = object_model.LinkByName(ecm, kObjectLink);
    if (this->object_link_entity_ == gz::sim::kNullEntity) {
      gzerr << "Stage 9D fixture could not resolve the reviewed object link\n";
      return;
    }
    const bool contacts = this->node_.Subscribe(
      kContactTopic, &GraspFixture::OnContacts, this);
    const bool attach = this->node_.Subscribe(
      kAttachTopic, &GraspFixture::OnAttach, this);
    const bool detach = this->node_.Subscribe(
      kDetachTopic, &GraspFixture::OnDetach, this);
    this->state_publisher_ = this->node_.Advertise<gz::msgs::StringMsg>(kStateTopic);
    this->pose_publisher_ = this->node_.Advertise<gz::msgs::Pose_V>(kPoseTopic);
    this->configured_ =
      contacts && attach && detach && this->state_publisher_ && this->pose_publisher_;
    if (!this->configured_) {
      gzerr << "Stage 9D fixture could not create its fixed transport seams\n";
    }
  }

  void PreUpdate(
    const gz::sim::UpdateInfo & info,
    gz::sim::EntityComponentManager & ecm) override
  {
    if (!this->configured_ || info.paused) {
      return;
    }
    this->ResolveHand(ecm);
    if (this->pregrasp_preload_active_ && !this->attached_) {
      gz::msgs::Wrench preload;
      preload.mutable_force()->set_z(kPregraspPreloadForceZ);
      ecm.SetComponentData<gz::sim::components::ExternalWorldWrenchCmd>(
        this->object_link_entity_, preload);
    }

    bool attach_requested = false;
    bool detach_requested = false;
    bool latest_contact_valid = false;
    std::uint64_t contact_sequence = 0U;
    {
      std::lock_guard<std::mutex> lock(this->mutex_);
      attach_requested = this->attach_requested_;
      detach_requested = this->detach_requested_;
      latest_contact_valid = this->latest_contact_valid_;
      contact_sequence = this->contact_sequence_;
      this->attach_requested_ = false;
      this->detach_requested_ = false;
    }
    if (contact_sequence != this->observed_contact_sequence_) {
      this->observed_contact_sequence_ = contact_sequence;
      this->contact_valid_ = latest_contact_valid;
      this->contact_observed_at_ = info.simTime;
    }

    if (detach_requested && this->attached_) {
      ecm.RequestRemoveEntity(this->joint_entity_);
      this->joint_entity_ = gz::sim::kNullEntity;
      this->attached_ = false;
      this->PublishState("detached");
    }

    if (attach_requested && !this->attached_) {
      const bool fresh_contact =
        this->contact_valid_ && info.simTime >= this->contact_observed_at_ &&
        info.simTime - this->contact_observed_at_ <= kContactFreshness;
      if (fresh_contact && this->Aligned(ecm)) {
        ecm.RemoveComponent<gz::sim::components::ExternalWorldWrenchCmd>(
          this->object_link_entity_);
        this->pregrasp_preload_active_ = false;
        this->joint_entity_ = ecm.CreateEntity();
        ecm.CreateComponent(
          this->joint_entity_,
          gz::sim::components::DetachableJoint({
            this->physical_hand_link_entity_, this->object_link_entity_, "fixed"}));
        this->attached_ = true;
        this->PublishState("attached");
      } else {
        this->PublishState("detached");
      }
    }

    if (info.simTime >= this->next_publish_at_) {
      this->PublishState(this->attached_ ? "attached" : "detached");
      this->PublishPoses(info.simTime, ecm);
      this->next_publish_at_ = info.simTime + kPublishPeriod;
    }
  }

private:
  void ResolveHand(const gz::sim::EntityComponentManager & ecm)
  {
    if (this->physical_hand_link_entity_ != gz::sim::kNullEntity) {
      return;
    }
    const auto matches = gz::sim::entitiesFromScopedName(
      std::string(kRobotModel) + "::" + kPhysicalHandLink, ecm);
    if (matches.size() != 1U) {
      return;
    }
    const auto candidate = *matches.begin();
    if (ecm.Component<gz::sim::components::Link>(candidate) != nullptr) {
      this->physical_hand_link_entity_ = candidate;
    }
  }

  gz::math::Pose3d EndEffectorPose(
    const gz::sim::EntityComponentManager & ecm) const
  {
    return gz::sim::worldPose(this->physical_hand_link_entity_, ecm) *
           gz::math::Pose3d(0.0, 0.0, kEndEffectorOffsetZ, 0.0, 0.0, 0.0);
  }

  bool Aligned(const gz::sim::EntityComponentManager & ecm) const
  {
    if (this->physical_hand_link_entity_ == gz::sim::kNullEntity ||
      this->object_link_entity_ == gz::sim::kNullEntity)
    {
      return false;
    }
    const auto relative = this->EndEffectorPose(ecm).Inverse() *
      gz::sim::worldPose(this->object_link_entity_, ecm);
    const double dx = relative.Pos().X() - kExpectedRelativeX;
    const double dy = relative.Pos().Y() - kExpectedRelativeY;
    const double dz = relative.Pos().Z() - kExpectedRelativeZ;
    const double translation = std::sqrt(dx * dx + dy * dy + dz * dz);
    const double quaternion_w = std::abs(relative.Rot().W());
    const double rotation = 2.0 * std::acos(std::clamp(quaternion_w, 0.0, 1.0));
    return translation <= kTranslationTolerance && rotation <= kRotationTolerance;
  }

  void OnContacts(const gz::msgs::Contacts & message)
  {
    bool valid = message.contact_size() > 0 &&
      static_cast<std::size_t>(message.contact_size()) <= kMaximumContactEntries;
    for (const auto & contact : message.contact()) {
      valid = valid && reviewed_pair(
        contact.collision1().name(), contact.collision2().name());
    }
    std::lock_guard<std::mutex> lock(this->mutex_);
    this->latest_contact_valid_ = valid;
    ++this->contact_sequence_;
  }

  void OnAttach(const gz::msgs::Empty &)
  {
    std::lock_guard<std::mutex> lock(this->mutex_);
    this->attach_requested_ = true;
  }

  void OnDetach(const gz::msgs::Empty &)
  {
    std::lock_guard<std::mutex> lock(this->mutex_);
    this->detach_requested_ = true;
  }

  void PublishState(const std::string & state)
  {
    gz::msgs::StringMsg message;
    message.set_data(state);
    this->state_publisher_.Publish(message);
  }

  void PublishPoses(
    const std::chrono::steady_clock::duration & observed_at,
    const gz::sim::EntityComponentManager & ecm)
  {
    if (this->physical_hand_link_entity_ == gz::sim::kNullEntity) {
      return;
    }
    gz::msgs::Pose_V message;
    set_header(message.mutable_header(), observed_at, "stage9d-exact-entity-pair");
    set_pose(
      message.add_pose(), kEndEffectorEntity,
      this->EndEffectorPose(ecm), observed_at);
    set_pose(
      message.add_pose(), kObjectModel,
      gz::sim::worldPose(this->object_link_entity_, ecm), observed_at);
    this->pose_publisher_.Publish(message);
  }

  gz::transport::Node node_;
  gz::transport::Node::Publisher state_publisher_;
  gz::transport::Node::Publisher pose_publisher_;
  gz::sim::Entity object_model_entity_{gz::sim::kNullEntity};
  gz::sim::Entity object_link_entity_{gz::sim::kNullEntity};
  gz::sim::Entity physical_hand_link_entity_{gz::sim::kNullEntity};
  gz::sim::Entity joint_entity_{gz::sim::kNullEntity};
  bool configured_{false};
  bool attached_{false};
  bool pregrasp_preload_active_{true};
  bool contact_valid_{false};
  std::uint64_t observed_contact_sequence_{0U};
  std::chrono::steady_clock::duration contact_observed_at_{0};
  std::chrono::steady_clock::duration next_publish_at_{0};
  std::mutex mutex_;
  bool attach_requested_{false};
  bool detach_requested_{false};
  bool latest_contact_valid_{false};
  std::uint64_t contact_sequence_{0U};
};
}  // namespace ayyo::stage9d

GZ_ADD_PLUGIN(
  ayyo::stage9d::GraspFixture,
  gz::sim::System,
  gz::sim::ISystemConfigure,
  gz::sim::ISystemPreUpdate)

GZ_ADD_PLUGIN_ALIAS(
  ayyo::stage9d::GraspFixture,
  "ayyo::stage9d::GraspFixture")
