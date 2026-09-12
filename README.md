# Ayyo

Ayyo is a developmental personal humanoid companion project created by
P. Jeevan Kumar and Amrutha Sai Reddy. The project follows a software-first,
simulation-first approach so that cognition, safety, learning, and embodiment
can mature behind stable boundaries before physical hardware is introduced.

## Current status

Ayyo has completed the local Stage 9B Manipulation Trajectory & Execution
Eligibility Foundation v1 above the reviewed Stage 9A planning boundary. One
exact positive Stage 9A decision can be converted into a bounded deterministic
joint trajectory, immutable review evidence, independently evaluated Safety
eligibility, and an explicit inert Skill handoff reference. The final positive
state is only eligible for a future separately reviewed simulation handoff:
the Runtime endpoint remains unregistered and every result is `NOT_EXECUTED`
with `PHYSICAL_VALIDATION_ABSENT`.

Implemented:

- Repository structure, engineering conventions, and architecture documentation
- A ROS 2 workspace with interface/bringup foundations, installable Runtime
  Bridge and simulation-control packages, an authoritative robot-description
  package, and a dedicated Gazebo Harmonic simulation package
- Local environment verification, build, and test scripts
- A dedicated development/test `ayyo_scenarios` ROS package and
  `ayyo.developmental-scenarios.v1` transport-neutral core with immutable
  scenario/step/assertion/result/report contracts, fixed typed operations,
  deterministic fingerprints, hard resource bounds, and no arbitrary command
  runner
- Three fixed headless launch profiles and six mandatory scenario proofs for
  embodied observation, anonymous visual TEST semantics, production physical
  request deferral with zero dispatch/movement, DEVELOPMENT-only neck motion
  and reset, invalid-command rejection, optional visual absence, and exact
  owned-process teardown
- A standalone `ayyo.teach-mode.demonstration-episode.v1` core with an explicit
  caller-controlled capture session, immutable typed ordered events and
  references, truthful source-clock/outcome semantics, canonical JSON, pure
  integrity verification, and hard resource bounds
- A one-way Stage-6 report adapter that preserves scenario/report identity,
  source provenance, DEVELOPMENT-only neck evidence, production Safety
  deferral with zero movement, and invalid-command rejection without launching
  ROS/Gazebo or creating action, learning, or persistence authority
- A standalone `ayyo-learning-evaluation` Stage-7 layer with explicitly assigned
  candidate-evidence and holdout partitions, separate content identities, an
  inert versioned candidate manifest, caller-supplied trial contracts, and pure
  deterministic offline reports that retain bounded canonical corpus/trial
  evidence and derive every summary from it, with no execution or promotion
  authority
- A standalone `ayyo-promotion-control` Stage-7 layer with caller-owned
  promotion/rollback criteria, exact candidate/report/known-good lineage,
  canonical immutable eligibility decisions, typed reason evidence, and no
  policy execution, installation, automatic state change, or runtime authority
- A standalone `ayyo-policy-registry` Stage-7 layer with exact upstream
  evidence-chain binding, immutable candidate-version records, explicit parent
  lineage, bounded canonical snapshots, deterministic read-only resolution,
  and no active-policy state, persistence, execution, or deployment authority
- A standalone `ayyo-approval-eligibility` Stage-7 layer with bounded immutable
  authority references, exact registry/request/approval evidence binding,
  explicit unverified/externally-verified/revoked authority states, strict
  canonical artifacts, and pure future-activation eligibility decisions;
  `UNVERIFIED` always fails closed and external verification is asserted by an
  upstream seam rather than performed or fabricated here
- A standalone `ayyo-software-showcase` Stage-8 inspection layer with a closed
  15-capability catalog, 19 imported public-contract evidence references,
  immutable canonical manifests/reports, exact provenance, explicit truthful
  classifications/non-claims, and a deterministic four-command CLI; production
  activation and physical validation remain explicitly unavailable
- A standalone `ayyo-manipulation-planning` Stage-9A planning-only layer with
  an exact URDF-derived left-arm chain, immutable content-addressed requests,
  fixed-box `base_link` collision scenes, exact evidence-chain binding,
  deterministic bounded joint interpolation, and decisions that remain
  `NOT_EXECUTED`
- A headless `ayyo_manipulation_planning` MoveIt 2 PlanningScene proof covering
  exact limits, self/environment collision checking, a collision-free bounded
  path, and positive rejection evidence for a fixed goal obstacle without any
  MoveGroup, action, controller, Runtime, ROS command, or hardware surface
- A standalone `ayyo-manipulation-trajectory` Stage-9B pre-execution layer that
  recursively binds one complete positive Stage 9A decision, derives finite
  strictly increasing timestamps from reviewed velocity limits and a bounded
  explicit configuration, and emits immutable canonical trajectory evidence
- Explicit Safety and Skill evidence seams for an information-only trajectory
  review capability; the caller supplies both decisions, Stage 9B revalidates
  their exact lineage, reconstructs every derived Skill invocation identity,
  and requires the authoritative contexts again when reconstructing positive
  canonical decisions; it creates no Runtime request or endpoint and stops at
  future simulation-handoff review eligibility
- A verified local ROS 2, Gazebo, and RViz development setup
- A standalone, provenance-aware Memory OS core with SQLite persistence
- A standalone deterministic validation and consolidation policy for candidate
  memory evidence
- A standalone stateless candidate-discovery policy that inspects a bounded
  retained-evidence set only when called, emits canonical immutable
  `ConsolidationRequest` proposals for exact anonymous person/object observations,
  and never stages, selects, evaluates, applies, or persists them
- A standalone explicit Working Memory candidate-staging bridge that accepts
  one exact retained evidence reference, reconstructs its immutable identity,
  enforces fresh-only and reviewed UTC-clock eligibility, derives bounded
  direct-observation provenance, and emits `CandidateEvidence` without applying
  or persisting it
- A standalone stateless reviewed candidate-selection policy that consumes
  unchanged `CandidateEvidence`, requires exact staging eligibility for direct
  observations, emits versioned selected/deferred/rejected-for-review decisions,
  defers duplicates and conflicts without choosing a winner, and never
  evaluates, applies, or persists memory
- A standalone explicit two-phase controlled review pipeline that snapshots and
  verifies bounded discovery plans, requires a caller proposal-ID allowlist,
  authoritatively restages current evidence, selects one complete batch, and
  evaluates only selected candidates through a narrow read-only interface; it
  exposes no apply or persistence operation
- A standalone, read-only Personal Context Twin that projects deterministic,
  owner-isolated, evidence-backed snapshots from Memory OS
- A standalone Executive Cognition layer that consumes PCT snapshots and emits
  deterministic declarative proposals, explicit blockers, and stale-decision
  evidence without execution or safety authority
- A standalone Immutable Safety Kernel that independently validates Executive
  proposal graphs, applies explicit fail-closed hazard policy, retains approval
  and safety prerequisites, and binds immutable decisions to proposal and
  policy fingerprints without executing actions
- A standalone Skill Manager that explicitly registers immutable skill and
  backend declarations, validates bounded parameter contracts, and binds
  unchanged Safety-reviewed proposal steps to inert, fingerprinted invocation
  contracts without executing skills or calling ROS
- A standalone ROS Runtime Bridge that reconstructs Skill Manager binding data,
  validates an exact service-only endpoint allowlist, emits deterministic
  dispatch-eligibility decisions, and models an unavailable-by-default
  transport boundary without a concrete ROS client or robot execution
- A modular 39-link, 38-joint canonical Ayyo humanoid frame tree with 18
  provisional movable joints, fixed body-IMU and head-camera optical frames,
  deterministic
  Xacro/URDF validation, isolated proxy geometry, and a machine-readable
  33-part final-mesh contract
- Separate RViz-only and Gazebo Harmonic launch paths using the same
  authoritative Xacro, plus a static non-actuating simulation spawn and an
  explicit Gazebo-to-ROS clock/body-IMU bridge allowlist
- An opt-in Jazzy/Harmonic `gz_ros2_control` path with `AyyoSystem`, an
  authoritative `joint_state_broadcaster`, and one position command interface
  for the URDF-bounded `neck_yaw_joint`; non-control simulation remains static
- A standalone deterministic simulation-control core with canonical command,
  failure, result, Runtime Bridge evidence, URDF-limit, lifecycle, stale-time,
  and feedback contracts
- A separately flagged typed development ROS service that proves bounded motion
  from controller-derived state without arbitrary endpoint dispatch, plus
  non-control and controlled headless lifecycle smoke tests
- A standalone transport-neutral World Model with immutable provenance-bound
  robot/environment observations, authoritative URDF joint validation,
  deterministic freshness, and canonical current-state snapshots
- A standalone deterministic Working Memory with explicit TTL, bounded current
  entities, bounded recent evidence, duplicate suppression, out-of-order and
  future-time rejection, deterministic eviction, and no durable persistence
- A standalone deterministic Perception Trust Boundary with exact source,
  sensor, frame, provenance, clock, time-order, fingerprint, and bounded
  resource admission policy and no ROS/Gazebo/vendor dependency
- Bounded typed visual-interpretation contracts tied to one exact admitted
  frame and producer, with normalized regions, optional honest confidence,
  source/result time, deterministic identity, and no generic metadata
- Compact immutable anonymous person and object observation contracts with an
  exact content-addressed interpretation/detection source, normalized regions,
  honest optional confidence, deterministic identity, typed provenance, no raw
  pixels, and no biometric or persistent identity
- Fail-closed person/object admission bound to one exact fresh retained RGB
  frame, one admitted interpretation, and one exact typed detection, including
  producer/evaluation provenance through the interpretation identity,
  deterministic replay/reset/expiry behavior, and 64-item interpretation and
  semantic caps
- A transport-neutral `SemanticEvidenceObservation` that projects a non-empty
  anonymous subset from one exact admitted interpretation while preserving
  source frame, interpretation, detection, producer/evaluation, region,
  category, provenance, and optional-confidence identities
- Conservative bounded Working Memory retention of recent semantic evidence
  batches, with source-chain revalidation, 500 ms default freshness, 2 second
  TTL, reset/clock-epoch isolation, deterministic eviction, and no negative
  scene knowledge from omitted detections
- Immutable canonically ordered semantic states in `WorldSnapshot`, included
  in snapshot identity without creating `WorldEntity` records or stable
  person/object identities
- A dedicated lifecycle-owned
  `/ayyo/world_model/get_anonymous_semantic_state` service with minimal bounded
  typed messages and a fixed deterministic JSON client, preserving exact
  evidence/source/provenance, freshness, object category, and explicit absent
  versus `0.0` confidence semantics from one immutable `WorldSnapshot`
- A default-off anonymous semantic TEST fixture and extended owned visual smoke
  proving real frame admission through Perception, Working Memory, World Model,
  and the ROS query without motion, persistent entities, or orphan processes
- Immutable IMU, body-pose, covariance, quality, health/availability,
  freshness, and disappearance contracts integrated into Working Memory and
  World Model without fabricating missing state
- A lifecycle-managed fixed `/joint_states`, `/ayyo/imu/data`,
  `/ayyo/localization/odometry`, and `/diagnostics` ROS adapter plus an additive
  typed read-only body-state query
- Exact timestamped `odom` to `base_link` localization through a bounded TF2
  lookup, with no latest/identity fallback, explicit typed failure health,
  unknown covariance preservation, and distinct simulation/physical provenance
- An opt-in 50 Hz Harmonic ground-truth odometry source and fixed one-way
  standard `nav_msgs/Odometry` bridge, truthfully labeled as simulation
- An exact two-component standard ROS diagnostics allowlist for joint-state and
  body-IMU sources, conservative OK/WARN/ERROR/STALE mapping, bounded inert
  detail, explicit expiry, and no health inferred from measurement arrival
- A headless end-to-end smoke proving localization, diagnostics, adversarial
  rejection, existing bounded development motion, and clean shutdown
- A default-off 10 Hz 320×240 Harmonic head RGB camera with standard
  `sensor_msgs/Image` and `sensor_msgs/CameraInfo`, image-transport-based
  bridging, one exact optical frame, and no camera-control channel
- Immutable calibration identity and pixel-free visual-frame metadata admitted
  through the existing trust boundary into one bounded current visual source
  state, with explicit disappearance and absent health semantics
- A headless visual smoke proving real nonempty pixels at transport ingress,
  matching CameraInfo, simulation provenance, adversarial rejection, bounded
  retention, lifecycle behavior, independent neck motion, and clean shutdown
- A disabled-by-default deterministic synthetic reference adapter and headless
  proof of trusted frame → interpretation → trust → Working Memory → immutable
  World Model → fixed query, without a model, fake confidence, or authority
- Immutable producer/model/dataset/policy contracts, verified artifact and
  dataset digests, bounded evaluation metrics/reports, and sealed one-use
  Perception admission for evaluated visual evidence
- A default-off evaluated ROS fixture and twice-run owned smoke proving exact
  compact provenance, 5,000-cycle bounded state, adversarial recovery,
  repeat-query identity, lifecycle reactivation, and empty teardown
- A driver-neutral physical-camera source, calibration, pairing, lifecycle,
  diagnostics, and sealed Perception-admission boundary with distinct physical,
  simulation, and recorded provenance and no raw-pixel retention
- A default-off TEST-only physical-camera ROS composition and twice-run smoke
  proving 5,000-cycle bounds, malformed-calibration/wrong-frame rejection,
  recovery, source-session renewal, and an empty graph without camera hardware
- A transport-neutral head-depth package with exact source, producer, sensor,
  frame, calibration, encoding, metric-range, session, and provenance contracts
- Compact depth validity/range/fingerprint state admitted through Perception
  into bounded Working Memory and immutable World Model without raw-depth
  retention, geometry, or authority; temporal fusion is a separate layer
- Distinct default-off TEST and Gazebo depth paths plus an owned 5,000-cycle
  adversarial smoke proving standard Image/CameraInfo transport, lifecycle
  isolation, recovery, resource bounds, and clean teardown
- An immutable compact RGB-D pair contract that binds already-admitted RGB and
  depth evidence by exact source acquisition time, component producer/source,
  frame, calibration, lifecycle session, provenance, policy, and fingerprints
- A sealed fusion admission path through Perception, one bounded current fused
  Working Memory state, immutable World Model projection, and additive compact
  query fields with spatial registration explicitly unvalidated
- A default-off four-topic TEST fixture and owned smoke proving exact temporal
  pairing, 5,000-cycle bounds, adversarial/lifecycle isolation, no execution
  authority, and empty teardown
- A driver-neutral head-microphone source manifest, exact mono 16 kHz
  `pcm_s16le` contract, lifecycle/session adapter, compact payload summaries,
  typed diagnostics, and sealed one-use Perception admission
- Bounded audio evidence in Working Memory and immutable World Model/query
  projection without raw sample retention, plus a default-off deterministic
  TEST publisher and owned adversarial/resource/lifecycle smoke
- Exact per-smoke process ownership and bounded graceful/scoped teardown,
  including direct shell-free Gazebo ownership and survivor regression tests

Planned, but not implemented:

- Final Ayyo CAD-derived visual/collision meshes and reviewed physical data
- Graphical Ayyo mesh/frame/collision validation
- Additional commandable joints, trajectory/whole-body control, and validated
  dynamics/contact behavior
- Physical localization/camera/sensor validation, real diagnostic producers,
  spatial registration/SLAM/physical calibration, and production visual
  producer promotion
- Production person/object detectors, tracking, face recognition, persistent
  identity, complete-scene/negative-detection claims, and semantic projection
  into persistent environment entities
- Background/scheduled review invocation, automatic durable consolidation,
  autonomous durable memory formation, confidence synthesis, and provenance
  aggregation
- Natural-language/model integration and a production authority-authentication
  provider, permissions, and external verification enforcement
- Runtime skill implementations, manipulation execution, and navigation
- Production-authorized typed ROS services, runtime scheduling, and resource
  enforcement; Safety v1 still defers all physical movement
- Additional Teach Mode sources, authenticated teacher identity, physical
  demonstration capture, and executable learning/training integration
- Production approval workflow, an actual activation gate, sandbox/model
  runner, and installed or active policy state
- Physical hardware

## Architecture

The planned system separates perception, world and memory state, owner modeling,
executive cognition, model access, planning, immutable safety enforcement, skill
management, and replaceable ROS 2 embodiment. Safety-critical controls remain
independent of cognition and learned policies. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/MEMORY_VALIDATION.md](docs/MEMORY_VALIDATION.md),
[docs/PERSONAL_CONTEXT_TWIN.md](docs/PERSONAL_CONTEXT_TWIN.md),
[docs/EXECUTIVE_COGNITION.md](docs/EXECUTIVE_COGNITION.md),
[docs/SAFETY_KERNEL.md](docs/SAFETY_KERNEL.md),
[docs/SKILL_MANAGER.md](docs/SKILL_MANAGER.md),
[docs/ROS_RUNTIME_BRIDGE.md](docs/ROS_RUNTIME_BRIDGE.md),
[docs/ROBOT_DESCRIPTION_SIMULATION.md](docs/ROBOT_DESCRIPTION_SIMULATION.md),
[docs/SIMULATION_CONTROL.md](docs/SIMULATION_CONTROL.md),
[docs/WORLD_MODEL_WORKING_MEMORY.md](docs/WORLD_MODEL_WORKING_MEMORY.md),
[docs/MEMORY_CANDIDATE_DISCOVERY.md](docs/MEMORY_CANDIDATE_DISCOVERY.md),
[docs/WORKING_MEMORY_CONSOLIDATION.md](docs/WORKING_MEMORY_CONSOLIDATION.md),
[docs/REVIEWED_MEMORY_CANDIDATE_SELECTION.md](docs/REVIEWED_MEMORY_CANDIDATE_SELECTION.md),
[docs/PERCEPTION_TRUST_PROPRIOCEPTION.md](docs/PERCEPTION_TRUST_PROPRIOCEPTION.md),
[docs/BODY_LOCALIZATION_SENSOR_DIAGNOSTICS.md](docs/BODY_LOCALIZATION_SENSOR_DIAGNOSTICS.md),
[docs/VISUAL_CAMERA_FOUNDATION.md](docs/VISUAL_CAMERA_FOUNDATION.md),
[docs/VISUAL_PERCEPTION_PROCESSING.md](docs/VISUAL_PERCEPTION_PROCESSING.md),
[docs/VISUAL_PRODUCER_EVALUATION.md](docs/VISUAL_PRODUCER_EVALUATION.md),
[docs/PHYSICAL_HEAD_CAMERA_CALIBRATION_DIAGNOSTICS.md](docs/PHYSICAL_HEAD_CAMERA_CALIBRATION_DIAGNOSTICS.md),
[docs/HEAD_DEPTH_RGBD_FOUNDATION.md](docs/HEAD_DEPTH_RGBD_FOUNDATION.md),
[docs/HEAD_RGBD_FUSION_FOUNDATION.md](docs/HEAD_RGBD_FUSION_FOUNDATION.md),
[docs/HEAD_AUDIO_PERCEPTION_FOUNDATION.md](docs/HEAD_AUDIO_PERCEPTION_FOUNDATION.md),
[docs/TEACH_MODE_DEMONSTRATION_CAPTURE.md](docs/TEACH_MODE_DEMONSTRATION_CAPTURE.md),
[docs/DEMONSTRATION_POLICY_OFFLINE_EVALUATION.md](docs/DEMONSTRATION_POLICY_OFFLINE_EVALUATION.md),
[docs/CANDIDATE_POLICY_PROMOTION_ROLLBACK_CONTROL.md](docs/CANDIDATE_POLICY_PROMOTION_ROLLBACK_CONTROL.md),
[docs/CANDIDATE_POLICY_REGISTRY_LINEAGE.md](docs/CANDIDATE_POLICY_REGISTRY_LINEAGE.md),
[docs/HUMAN_AUTHORITY_APPROVAL_ACTIVATION_ELIGIBILITY.md](docs/HUMAN_AUTHORITY_APPROVAL_ACTIVATION_ELIGIBILITY.md),
[docs/SOFTWARE_SHOWCASE.md](docs/SOFTWARE_SHOWCASE.md),
[docs/AYYO_MESH_IMPORT.md](docs/AYYO_MESH_IMPORT.md), and
[docs/SAFETY.md](docs/SAFETY.md).

## Supported environment

- Ubuntu 24.04 under WSL2
- ROS 2 Jazzy
- Gazebo Harmonic
- RViz2
- MoveIt 2, Nav2, ros2_control, and ros_gz
- Python 3.12, CMake, and colcon

Verify the environment from a shell with ROS 2 sourced:

```bash
source /opt/ros/jazzy/setup.bash
./scripts/verify_environment.sh
```

Build the workspace:

```bash
./scripts/build_workspace.sh
```

Run package tests:

```bash
./scripts/test_workspace.sh
```

Validate the authoritative robot description:

```bash
python3 ros2_ws/src/ayyo_description/scripts/validate_description.py
```

Run the opt-in headless simulation lifecycle after building:

```bash
./scripts/smoke_simulation.sh
```

Run the explicitly controlled one-joint headless lifecycle:

```bash
./scripts/smoke_simulation_control.sh
```

Run the integrated Stage-6 developmental scenario harness:

```bash
./scripts/smoke_developmental_scenarios.sh
```

Run the transport-neutral Teach Mode demonstration-capture tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src \
python3 -m pytest -q teach_mode/tests
```

Run the transport-neutral demonstration policy evaluation tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src \
python3 -m pytest -q learning_evaluation/tests
```

Run the inert candidate promotion and rollback control-plane tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src:promotion_control/src \
python3 -m pytest -q promotion_control/tests
```

Run the immutable candidate policy registry and version-lineage tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src:promotion_control/src:policy_registry/src \
python3 -m pytest -q policy_registry/tests
```

Run the inert authority-approval and future-activation eligibility tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src:promotion_control/src:policy_registry/src:approval_eligibility/src \
python3 -m pytest -q approval_eligibility/tests
```

Inspect and test the deterministic Stage-8 software showcase:

```bash
PYTHONPATH=memory/src:memory_validation/src:memory_consolidation/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:simulation_control/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src:promotion_control/src:policy_registry/src:approval_eligibility/src:world_model/src:working_memory/src:perception/src:visual_evaluation/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:head_audio/src:software_showcase/src \
python3 -m ayyo_software_showcase.cli verify
PYTHONPATH=memory/src:memory_validation/src:memory_consolidation/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:simulation_control/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src:promotion_control/src:policy_registry/src:approval_eligibility/src:world_model/src:working_memory/src:perception/src:visual_evaluation/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:head_audio/src:software_showcase/src \
python3 -m pytest -q software_showcase/tests
```

Run the planning-only Stage-9A contract and package-boundary tests:

```bash
source /opt/ros/jazzy/setup.bash
PYTHONPATH=manipulation_planning/src${PYTHONPATH:+:$PYTHONPATH} \
  python3 -m pytest -q manipulation_planning/tests
```

The MoveIt proof is built and tested through the ROS workspace as package
`ayyo_manipulation_planning`; it consumes expanded URDF and the reviewed SRDF,
pins their exact collision semantics, checks the exact 14-waypoint Python
candidate path and request scene, and never exposes an execution endpoint.

Run the transport-neutral Stage-9B trajectory, eligibility, serialization, and
negative authority-boundary tests while preserving the sourced ROS Python path:

```bash
source /opt/ros/jazzy/setup.bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:manipulation_planning/src:manipulation_trajectory/src${PYTHONPATH:+:$PYTHONPATH} \
  python3 -m pytest -q manipulation_trajectory/tests
```

Run Memory OS tests:

```bash
PYTHONPATH=memory/src python3 -m unittest discover -s memory/tests -v
```

Run Memory Validation tests:

```bash
PYTHONPATH=memory/src:memory_validation/src \
python3 -m unittest discover -s memory_validation/tests -v
```

Run candidate-discovery, staging, and reviewed-selection tests:

```bash
PYTHONPATH=memory/src:memory_validation/src:world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src:memory_consolidation/src \
python3 -m pytest -q memory_consolidation/tests
```

Run Personal Context Twin tests:

```bash
PYTHONPATH=memory/src:personal_context/src \
python3 -m unittest discover -s personal_context/tests -v
```

Run Executive Cognition tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src \
python3 -m unittest discover -s executive/tests -v
```

Run Immutable Safety Kernel tests:

```bash
PYTHONPATH=memory/src:memory_validation/src:personal_context/src:executive/src:safety_kernel/src \
python3 -m unittest discover -s safety_kernel/tests -v
```

Run Skill Manager tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src \
python3 -m unittest discover -s skill_manager/tests -v
```

Run ROS Runtime Bridge tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src \
python3 -m unittest discover -s runtime_bridge/tests -v
```

Run Simulation Control tests:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:simulation_control/src \
python3 -m unittest discover -s simulation_control/tests -v
```

Run World Model and Working Memory tests:

```bash
PYTHONPATH=world_model/src \
python3 -m unittest discover -s world_model/tests -v

PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m unittest discover -s working_memory/tests -v
```

Run Perception Trust Boundary tests:

```bash
export PYTHONPATH="world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src"
python3 -m pytest -q perception/tests/test_person_object_observations.py
python3 -m pytest -q perception/tests/test_semantic_admission_boundary.py
python3 -m pytest -q perception/tests/test_semantic_producer_binding.py
python3 -m pytest -q perception/tests/test_semantic_world_projection.py
python3 -m pytest -q perception/tests/test_semantic_scene_state_integration.py
python3 -m pytest -q perception/tests
```

Run physical head-camera foundation tests:

```bash
PYTHONPATH=world_model/src:physical_camera/src \
python3 -m unittest discover -s physical_camera/tests -v
```

Run head-depth foundation tests:

```bash
PYTHONPATH=world_model/src:depth_camera/src:physical_camera/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q depth_camera/tests perception/tests/test_depth_boundary.py \
  working_memory/tests/test_depth_resources.py world_model/tests/test_depth_camera.py
```

Run head RGB-D synchronization foundation tests:

```bash
PYTHONPATH=world_model/src:depth_camera/src:physical_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q rgbd_fusion/tests
PYTHONPATH=world_model/src:depth_camera/src:physical_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src \
python3 -m pytest -q perception/tests/test_rgbd_fusion_boundary.py
PYTHONPATH=world_model/src:depth_camera/src:working_memory/src \
python3 -m pytest -q working_memory/tests/test_rgbd_fusion_resources.py
PYTHONPATH=world_model/src \
python3 -m pytest -q world_model/tests/test_rgbd_fusion.py
```

Run Head Audio Perception Foundation tests:

```bash
PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q head_audio/tests
PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q perception/tests
PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q working_memory/tests
PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q world_model/tests
```

Run visual producer evaluation tests:

```bash
PYTHONPATH=world_model/src:visual_evaluation/src \
python3 -m unittest discover -s visual_evaluation/tests -v
```

Run the embodied feedback integration smoke after building:

```bash
./scripts/smoke_world_model.sh
```

Run the trusted proprioception integration smoke after building:

```bash
./scripts/smoke_perception.sh
```

Run the body localization and sensor diagnostics integration smoke:

```bash
./scripts/smoke_localization_diagnostics.sh
```

Run the head RGB camera and visual-observation integration smoke:

```bash
./scripts/smoke_visual_camera.sh
```

Run the visual-perception processing and teardown proof:

```bash
./scripts/smoke_visual_perception.sh
```

Run the recorded/evaluated producer gate twice:

```bash
./scripts/smoke_visual_producer_evaluation.sh
./scripts/smoke_visual_producer_evaluation.sh
```

Run the hardware-free physical-camera foundation smoke twice:

```bash
./scripts/smoke_physical_camera_foundation.sh
./scripts/smoke_physical_camera_foundation.sh
```

Run the hardware-free Head Depth / RGB-D foundation smoke twice:

```bash
./scripts/smoke_head_depth_rgbd.sh
./scripts/smoke_head_depth_rgbd.sh
```

Run the hardware-free exact-time Head RGB-D fusion smoke twice:

```bash
./scripts/smoke_head_rgbd_fusion.sh
./scripts/smoke_head_rgbd_fusion.sh
```

Run the hardware-free Head Audio Perception smoke twice:

```bash
./scripts/smoke_head_audio.sh
./scripts/smoke_head_audio.sh
```

## Repository layout

```text
docs/          Architecture, roadmap, safety, and status
memory/        Standalone Memory OS core and its tests
memory_validation/  Deterministic evidence policy layer and its tests
memory_consolidation/  Bounded discovery, staging, selection, and review orchestration
personal_context/  Deterministic owner-context projection and its tests
executive/     Deterministic Executive proposal planning and its tests
safety_kernel/  Immutable deterministic proposal safety review and its tests
skill_manager/  Immutable declarative skill contracts and Safety binding
runtime_bridge/  Deterministic Skill-to-ROS compatibility and transport boundary
simulation_control/  Bounded deterministic simulation-control policy and feedback
developmental_scenarios/  Bounded Stage-6 definitions, runner, reports, and tests
teach_mode/     Bounded immutable Stage-7 demonstration evidence and Stage-6 adapter
learning_evaluation/  Inert candidate identity and pure offline evaluation evidence
promotion_control/  Pure candidate promotion and rollback eligibility evidence
policy_registry/  Immutable candidate registration, snapshots, and exact lineage
approval_eligibility/  Inert authority evidence and future-activation eligibility
software_showcase/  Deterministic Stage-8 public-contract catalog and inspector
manipulation_planning/  Immutable Stage-9A planning-only evidence contracts
manipulation_trajectory/  Immutable Stage-9B trajectory and handoff eligibility
world_model/  Transport-neutral embodied/environment observations and snapshots
perception/  Deterministic sensor/provenance/time admission trust boundary
physical_camera/  Driver-neutral physical source, calibration, lifecycle, and diagnostics
head_audio/  Driver-neutral microphone source, lifecycle, compacting, and diagnostics
rgbd_fusion/  Exact-time bounded compact RGB-D synchronization and admission
visual_evaluation/  Deterministic producer/model/dataset evaluation quality gate
working_memory/  Bounded temporary current-state and recent-evidence retention
ros2_ws/src/   ROS 2 interfaces, description, simulation, scenarios, Runtime Bridge, and bringup
scripts/       Local environment, build, and test commands
tests/         Repository-level tests when justified
```

The roadmap defines the intended progression. Memory persistence, deterministic
candidate validation, Personal Context Twin v1, Executive Cognition v1,
Immutable Safety Kernel v1, Skill Manager v1, controlled ROS Runtime Bridge v1,
Robot Description & Simulation Foundation v1, and the one-joint Simulation
Control & Actuation Foundation v1, Embodied World Model and Working Memory
Foundation v1, and Perception Trust Boundary and Proprioceptive Observation
Foundation v1, plus Body Localization and Sensor Diagnostics Foundation v1,
Head RGB Camera and Visual Observation Foundation v1, and Visual Perception
Processing Foundation v1, Recorded Visual Producer Evaluation and Perception
Quality Gate v1, and Physical Head Camera Adapter, Calibration, and Camera
Diagnostics Foundation v1, plus Head Depth / RGB-D Sensor Foundation v1 are
implemented. Head RGB-D Synchronization and Fused Observation Foundation v1 is
also implemented as exact-time TEST evidence. Head Audio Perception Foundation
v1 adds TEST-only compact microphone evidence with no raw-sample retention or
authority. The physical-camera, depth, fusion, and audio milestones do not
validate real RGB-D/audio hardware, hardware clocks, physical calibration,
extrinsics, spatial registration, acoustics, or production device timing.
Anonymous Person/Object Semantic Scene State Foundation v1 now projects
already-admitted compact evidence into conservative bounded Working Memory and
immutable World Snapshot semantic state. It preserves exact source identity
and expiry without claiming scene completeness, tracking, persistent entities,
face/owner identity, physical validation, authority, or motion.
Anonymous Semantic ROS Query Foundation v1 now serializes that state through
one dedicated, lifecycle-aware, hard-bounded typed service and deterministic
read-only client. The ROS seam consumes one public immutable snapshot and does
not run perception, refresh evidence, create entities, or infer absence.
Working Memory → Memory Validation Candidate Bridge Foundation v1 now adds a
transport-neutral, caller-driven seam from one exact fresh retained observation
to immutable `CandidateEvidence`. It preserves evidence identity, direct
observation authority, honest confidence, and only exactly representable
`ROS_SYSTEM_TIME` UTC. Anonymous person/object evidence remains an explicit
episodic anonymous observation. The bridge has no evaluation, apply,
persistence, scanning, timer, worker, ROS, Personal Context, or action API.
Reviewed Memory Candidate Selection Policy Foundation v1 now adds an explicit
stateless review-triage step over unchanged candidate snapshots. Direct
observations retain exact bridge eligibility; policy version/fingerprint,
candidate/selection identities, confidence threshold, typed reasons, canonical
ordering, and resource bounds are deterministic. Exact duplicates, equivalent
propositions, and conflicts are deferred without a winner. Anonymous evidence
remains anonymous, and selection grants no truth, owner approval, validation,
apply, persistence, correction, learning, or physical-action authority.
Bounded Memory Candidate Discovery Foundation v1 now adds an earlier explicit,
stateless scan over at most 64 retained evidence envelopes. Versioned canonical
output contains at most 32 exact stage-compatible anonymous visual person/object
`ConsolidationRequest` proposals and 64 typed diagnostics. It reuses staging's
freshness, exact-source-chain, provenance, confidence, and microsecond-compatible
`ROS_SYSTEM_TIME` eligibility without invoking staging or any later step.
Exact proposal identities alone are deduplicated; category remains observation
content, evidence IDs remain provenance, and no identity, preference, social,
ownership, absence, permanence, correction, persistence, or learning claim is
created.
Controlled Memory Candidate Invocation and Review Pipeline Foundation v1 adds
an explicit two-phase `prepare`/`execute_review` orchestration over those
existing seams. The immutable plan is reconstructable, the caller must
allowlist exact proposal IDs, current evidence is authoritatively restaged, one
selector invocation sees the complete staged batch, and only
`SELECT_FOR_REVIEW` candidates reach sequential read-only validation. See
[Controlled Memory Review Pipeline](docs/CONTROLLED_MEMORY_REVIEW_PIPELINE.md).
The pipeline has no application, persistence, background, ROS, or action API.
Production motion remains
closed because Safety v1 defers physical movement; only explicit development
injection can exercise the simulated neck joint. The perception path adds
evidence only and grants no execution authority. Final Ayyo assets, production
identity authentication and approval enforcement, production runtime services,
additional controllers, physical-safety subsystems, and physical robot
execution remain planned.

Developmental Simulation Scenario Harness Foundation v1 now integrates those
truths as six fixed, headless, deterministic stories. See
[Developmental Simulation Scenarios](docs/DEVELOPMENTAL_SIMULATION_SCENARIOS.md).
It uses the development proxy model and cannot establish production motion,
physical safety, final mechanics, real-sensor performance, navigation,
manipulation, balance, or walking.
Teach Mode Demonstration Capture Foundation v1 consumes only those public
immutable Stage-6 reports and converts them into bounded, canonical historical
evidence. See
[Teach Mode Demonstration Capture](docs/TEACH_MODE_DEMONSTRATION_CAPTURE.md).
It has no ROS/Gazebo dependency, learning, policy mutation, executable replay,
memory persistence, authenticated teacher identity, or production authority.
Demonstration Candidate Policy and Offline Evaluation Foundation v1 consumes
only verified Teach Mode evidence through an explicit bounded corpus. See
[Demonstration Candidate Policy and Offline Evaluation](docs/DEMONSTRATION_POLICY_OFFLINE_EVALUATION.md).
Its candidate manifests are inert, holdout evidence cannot affect candidate
identity, and offline criteria grant no execution, promotion, or Safety rights.
Candidate Policy Promotion and Rollback Control Plane Foundation v1 turns that
verified report chain into immutable eligibility evidence without performing a
promotion or rollback. See
[Candidate Policy Promotion and Rollback Control Plane](docs/CANDIDATE_POLICY_PROMOTION_ROLLBACK_CONTROL.md).
Candidate Policy Registry and Immutable Version Lineage Foundation v1 consumes
only that verified promotion chain and records exact inert versions in bounded
canonical snapshots. See
[Candidate Policy Registry and Immutable Version Lineage](docs/CANDIDATE_POLICY_REGISTRY_LINEAGE.md).
Registry presence is not approval, activation, deployment, execution, or a
physical-safety claim.
Human / Authority Approval Evidence and Activation Eligibility Boundary
Foundation v1 consumes only an exact verified registry record and binds it to
one immutable approval request, one exact authority reference, and one explicit
approval disposition. See
[Human / Authority Approval Evidence and Activation Eligibility](docs/HUMAN_AUTHORITY_APPROVAL_ACTIVATION_ELIGIBILITY.md).
An `EXTERNALLY_VERIFIED` status carries caller-supplied provider and evidence
identities but is not authentication performed by this package. `UNVERIFIED`
always yields `INELIGIBLE`; an eligible result means only structurally eligible
to proceed to a separately reviewed future activation stage.
Software Showcase Foundation v1 now presents these and the other reviewed
software boundaries through a closed public-contract catalog and canonical
report. See [Software Showcase Foundation](docs/SOFTWARE_SHOWCASE.md). Its
`SUPPORTED_BY_PUBLIC_CONTRACT` result proves only that the exact reviewed
contract backs the classified claim; it performs no action and grants no new
authority.
Manipulation Planning & Collision Safety Foundation v1 begins Stage 9 as a
strictly downstream planning-only seam. See
[Manipulation Planning & Collision Safety](docs/MANIPULATION_PLANNING_COLLISION_SAFETY.md).
It binds exact robot, URDF, SRDF/allowed-collision semantics, chain, state, goal,
scene, planner, candidate-path, and per-waypoint collision-evidence identities.
`PLAN_AVAILABLE_FOR_REVIEW` never means activated,
dispatched, executed, physically safe, or hardware validated; every result is
explicitly `NOT_EXECUTED`.
Manipulation Trajectory & Execution Eligibility Foundation v1 adds only the
next pre-execution seam. See
[Manipulation Trajectory & Execution Eligibility](docs/MANIPULATION_TRAJECTORY_EXECUTION_ELIGIBILITY.md).
It binds the complete Stage 9A decision and exact waypoint/collision lineage,
derives deterministic conservative timestamps, and records exact external
Safety and Skill evidence. Positive decision reconstruction requires the exact
source Safety and Skill validation contexts rather than trusting rehashed
references. `TRAJECTORY_ELIGIBLE_FOR_SIMULATION_REVIEW` and the
final future-handoff-review status create no Runtime request or movement
authority; the endpoint is `NOT_REGISTERED`, execution is `NOT_EXECUTED`, and
physical validation is `ABSENT`.
