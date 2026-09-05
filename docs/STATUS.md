# Project Status

## Verified development environment

- Ubuntu 24.04 under WSL2
- ROS 2 Jazzy installed
- Gazebo Harmonic installed
- RViz2 installed
- MoveIt 2 installed
- Nav2 installed
- ros2_control installed
- gz_ros2_control installed
- ros_gz installed
- ROS publisher/subscriber smoke test passed
- Generic Gazebo GUI environment smoke test passed
- Generic RViz GUI environment smoke test passed
- Ayyo-specific controlled Gazebo graphical review not executed in this milestone

## Implemented

- Architecture, roadmap, and safety contracts
- ROS 2 workspace with `ament_cmake` foundations for `ayyo_interfaces` and
  `ayyo_bringup`, plus installable `ayyo_runtime_bridge` and
  `ayyo_simulation_control`, authoritative `ayyo_description`, and dedicated
  `ayyo_simulation` packages
- Local environment verification, build, and test scripts
- Standalone Memory OS core with typed records and mandatory provenance
- SQLite persistence with schema versioning, foreign keys, WAL journaling,
  transactional corrections, retractions, and conflict records
- Deterministic memory queries and revision/conflict inspection
- Standalone deterministic candidate validation with conservative identity and
  JSON normalization
- Typed duplicate, contradiction, correction, rejection, and review decisions
- Explicit evaluation/application separation using only the public Memory OS API
- Standalone `ayyo-memory-consolidation` bridge above public Working Memory,
  World Model, Memory Validation, and Memory contracts, without changing their
  dependency direction
- Explicit immutable `ConsolidationRequest`, exact one-evidence reference,
  typed staging status/reasons, and deterministic `CandidateEvidence` output
- Fresh-only retained-evidence eligibility, full immutable reconstruction,
  exact fingerprint/source/robot checks, fail-closed reset/expiry behavior,
  reviewed `ROS_SYSTEM_TIME`-only UTC conversion, and no fabricated confidence
- Bounded `DIRECT_OBSERVATION` provenance retaining source observation,
  fingerprint, source profile, and applicable frame/sensor/producer/semantic
  chain identities; bridge requests cannot supply timestamps, provenance,
  confidence, correction intent, or persistence authority
- Anonymous person/object staging limited to exact robot-subject episodic
  propositions with anonymous region/category values and evidence IDs confined
  to provenance, never persistent entity, owner, preference, or social identity
- Stateless caller-triggered bounded candidate discovery over at most 64
  currently retained evidence envelopes, with policy identity
  `ayyo.memory-candidate-discovery.v1`, canonical result/proposal identities,
  at most 32 immutable stage-compatible `ConsolidationRequest` proposals, and
  at most 64 typed diagnostics
- Discovery limited to exact fresh anonymous visual person/object episodic
  propositions with full retained source chains, reviewed microsecond-compatible
  `ROS_SYSTEM_TIME`, allowlisted provenance, and real confidence; `None` is
  diagnosed while genuine `0.0` remains eligible for proposal construction
- Discovery is an explicit read only: it retains no history, does not refresh
  TTL, and has no staging, selection, validation, apply, persistence, identity,
  preference/social inference, correction, ROS, runtime, learning, or action API
- Stateless reviewed candidate-selection policy over immutable
  `CandidateEvidence` plus optional exact staging eligibility, with a 32-item
  batch cap, versioned policy fingerprint, canonical candidate/selection IDs,
  and typed selected/deferred/rejected-for-review outcomes and reasons
- Exact duplicate collapse plus equivalent-proposition and conflict deferral
  without winner selection; deterministic input-order independence, explicit
  0.5 review threshold, genuine `0.0`, missing-confidence rejection, and bounded
  metadata/JSON/aggregate content
- Direct observations require their exact eligible staging result and cannot
  gain owner authority; broader direct claims and all derived inferences defer
  for confirmation, anonymous person/object candidates remain exact and
  anonymous, and the selector has no evaluate/apply/persistence/runtime surface
- Explicit controlled memory-review pipeline with immutable two-phase plan and
  invocation contracts, deterministic pipeline/plan/request/entry/batch IDs,
  exact proposal-ID allowlisting, and fail-closed plan reconstruction
- Authoritative per-proposal restaging against current Working Memory, one
  complete-batch selector invocation, typed partial ineligibility, and
  sequential evaluation of `SELECT_FOR_REVIEW` candidates only through a narrow
  read-only evaluator protocol
- Bounded immutable review batches with complete discovery → proposal → request
  → staging → candidate → selection → validation lineage and explicit counts;
  no validation application, Memory OS write, correction, Personal Context
  mutation, background invocation, ROS, runtime, or action surface
- Standalone Personal Context Twin v1 using only public, read-only Memory OS
  operations
- Exact owner isolation with deterministic resolved, conflicted, and unknown
  context states
- Immutable evidence-backed snapshots and canonical SHA-256 change versions
- Standalone Executive Cognition v1 with immutable structured requests,
  capability contracts, explicit proposal outcomes, and declarative plans
- Deterministic request, relevant-capability, relevant-context, and decision
  fingerprints with explicit stale-decision revalidation
- Fail-closed handling of unknown/unavailable capabilities and
  unknown/conflicted required owner context
- Standalone Immutable Safety Kernel v1 using only the public Executive
  Cognition contract
- Explicit immutable hazard policy for informational, internal, external
  digital, physical movement/contact, privileged, emergency, and unclassified
  capabilities
- Conservative plan-level dispositions for downstream eligibility, external
  approval, deferral, and blocking, with no execution or physical-safety claim
- Independent plan graph/relationship validation, defensive bounded JSON, and
  deterministic proposal, policy, and decision fingerprints
- Explicit stale Safety decision revalidation and typed approval/prerequisite
  evidence that cannot manufacture authorization
- Standalone Skill Manager v1 using only the public Safety Kernel contract and
  the minimum public Executive proposal types required for binding
- Immutable versioned skill definitions with explicit capability, backend,
  bounded input/output, context, resource, approval, hazard, timeout,
  concurrency, idempotency, failure, availability, and lifecycle contracts
- Explicit immutable Skill Registry construction with exact and
  capability-based resolution, no dynamic discovery, and canonical registry
  fingerprints independent of construction order
- Bounded deterministic parameter validation for nested scalar, array, and
  object contracts with fail-closed depth, size, cycle, numeric, key, and type
  handling
- Fail-closed binding of unchanged Safety-reviewed proposal steps to inert
  invocation contracts, including current Safety re-evaluation, registry/skill
  selection pins, step-scoped approval retention, and complete upstream
  fingerprint traceability
- Explicit binding outcomes for runtime-handoff eligibility, external approval
  requirement, and typed ineligibility; no skill or backend execution
- Standalone ROS Runtime Bridge v1 depending only on the public Skill Manager
  contract, with package-owned bounded canonical JSON and immutable fingerprints
- Service-only declarative ROS endpoint contracts and an exact immutable
  Skill/version/capability/backend/endpoint allowlist
- Runtime requests retaining the complete Executive, Safety, policy, Skill,
  registry, parameter, context, approval, resource, and endpoint identity chain
- Deterministic runtime eligibility that preserves approval, deferral, blocking,
  staleness, rejection, and unavailability without a transport side effect
- Dispatch-time request and current-binding reconstruction, typed result/failure
  semantics, correlated receipts, and no silent mock fallback
- Narrow transport protocol with an unavailable-by-default ROS service sentinel;
  the deterministic in-memory implementation exists only in tests
- Authoritative modular `ayyo_description` Xacro with a canonical `base_link`
  root, 39 links, 38 joints, 18 provisional movable joints, explicit RGB and
  depth camera mounts/ROS optical frames, and one fixed pelvis body-IMU datum
- Development proxy visual/collision primitives isolated from a normalized,
  machine-readable 33-part contract for absent final visual and collision
  meshes
- Deterministic description validation covering expansion, URDF XML/URDFDOM,
  topology, uniqueness, parentage, cycles, axes, limits, expected frames,
  symmetry, paths, mesh bindings, inactive control structure, and package
  resources
- RViz-only robot-state launch with tracked configuration and selectable CLI or
  GUI development joint-state source
- Dedicated `ayyo_simulation` package with an SDF 1.10 Gazebo Harmonic world,
  static non-actuating default spawn from the authoritative Xacro, opt-in
  controlled dynamic spawn, and no duplicate robot model
- Explicit one-way Gazebo-to-ROS allowlist for `/clock`, observation-only IMU,
  opt-in camera info and localization, plus an opt-in `ros_gz_image` image
  bridge, with no commands, services, actions, or wildcard bridging
- Opt-in Jazzy/Harmonic `gz_ros2_control` system with position/velocity/effort
  state for all 18 movable joints and exactly one claimed position command
  interface for `neck_yaw_joint`
- Controller Manager configuration with enforced URDF limits, authoritative
  `joint_state_broadcaster`, one standard forward position controller, and
  ordered spawn/activation lifecycle
- Standalone simulation-control models with exact allowlist, URDF-derived
  limits, simulation-time validity, dispatch-time authority/time revalidation,
  deterministic identities, explicit lifecycle failures, and strict
  feedback-backed completion
- Typed development-only `SetDevelopmentJointPosition` adapter behind two
  default-off launch flags, with fixed reviewed ROS names and no arbitrary
  topic/service/action/shell dispatch
- Runtime simulation-control translator pinned to one future exact service and
  complete Runtime Bridge identity evidence; physical movement remains
  non-dispatchable because Safety v1 returns `DEFERRED`
- Reproducible non-control and controlled headless smoke validations covering
  installed packages, nodes, TF/clock, entity spawn, controllers, hardware
  interfaces, sole joint-state publisher, valid motion, invalid rejection, and
  bounded clean shutdown
- Standalone transport-neutral `ayyo-world-model` with immutable robot and
  environment observations, explicit simulation/physical/recorded/test
  provenance, source-clock semantics, optional spatial pose, bounded generic
  entity evidence, and deterministic observation identities
- Immutable URDF-derived robot joint catalog with wrong-robot, unknown/fixed
  joint, finite numeric, and bounded position/velocity/effort validation plus a
  narrow numerical feedback tolerance that does not change command limits
- Pure deterministic World Model projection with unavailable/partial/available
  body coverage, per-joint provenance/confidence/freshness, optional base pose,
  evidence-backed environment entities, and canonical snapshot identities
- Standalone `ayyo-working-memory` with explicit source-clock TTL/freshness,
  bounded recent evidence and current entities, duplicate suppression,
  old/future/conflicting observation rejection, partial joint replacement,
  deterministic eviction, clock-regression reset semantics, and no persistence
- Configurable defaults of 500 ms freshness, 2 second TTL, 50 ms permitted
  future skew, 256 recent observations, and 128 environment entities, with
  hard resource maxima and measured regression tests
- Standalone `ayyo-perception` trust boundary depending only on public World
  Model contracts, with exact robot/source/sensor/frame/provenance/clock policy,
  immutable reconstruction, duplicate/order/future/stale rejection, typed
  lookup failure evidence, and constant-space source tracking
- Immutable IMU, body-pose, 3x3/6x6 covariance, optional quality, and sensor
  availability/health contracts with canonical quaternion normalization/sign,
  positive-semidefinite covariance validation, and no fabricated missing state
- Working Memory and World Model projection of bounded IMU/pose/health evidence,
  query-time fresh/stale/unavailable disappearance, and semantic snapshot
  changes only at evidence or discrete freshness transitions
- Lifecycle-managed `ayyo_world_model` ROS adapter with fixed `/joint_states`
  and `/ayyo/imu/data` sensor-data subscriptions, exact reviewed simulation/
  physical source profiles, authoritative `robot_description`, no Gazebo core
  dependency, and bounded configure/activate/deactivate/cleanup/shutdown
- Typed fixed read-only `/ayyo/world_model/get_robot_body_state` service with
  body coverage, source profile, per-joint values/timestamps/confidence/
  freshness/evidence identities, snapshot identity, and retained-evidence counts
- Headless embodied feedback smoke proving an 18-joint simulation-sourced
  snapshot, observed neck state change after the existing bounded development
  motion, command/observation separation, and clean lifecycle shutdown
- Authoritative 100 Hz Harmonic body IMU on `imu_link` and a headless smoke
  proving actual Gazebo → ROS → trust boundary → Working Memory → World Model
  evidence, unknown covariance/quality preservation, unavailable pose,
  lifecycle deactivate/reactivate, and clean shutdown
- Fixed `/ayyo/localization/odometry` `nav_msgs/Odometry` ingestion with exact
  nonzero timestamped `odom` to `base_link` TF2 lookup, a 20 ms default/100 ms
  maximum wait, bounded cache, explicit failure health, and no latest/zero-pose
  fallback
- Opt-in 50 Hz Harmonic ground-truth odometry plus one fixed Gazebo-to-ROS
  observation bridge, labeled with simulation-only localization provenance and
  disabled by default
- Fixed `/diagnostics` `DiagnosticArray` ingestion with exact reviewed
  joint-state/body-IMU component and hardware identities, conservative
  OK/WARN/ERROR/STALE mapping, bounded inert detail, deterministic conflicts,
  and no inferred health
- Additive body-state query fields for pose covariance/quality/provenance and
  independent explicit sensor health presence, freshness, identity,
  provenance, evidence detail, and disappearance
- A test-only non-installed fixed diagnostics fixture and headless smoke proving
  actual localization, all four diagnostic levels, unknown/wrong-frame
  rejection, expiry, existing 0.1 rad development motion independence, and
  bounded clean shutdown
- Fixed `head_camera_optical_frame` with ROS optical-axis semantics under the
  existing head camera mount, preserving the mount as a mechanical datum
- Default-off 10 Hz 320x240 `rgb8` Harmonic camera with standard
  `sensor_msgs/Image` and `sensor_msgs/CameraInfo` transport and bounded bridge
  queues
- Immutable calibration and pixel-free visual-observation contracts, exact
  simulation/physical provenance profiles, fixed paired-message admission, and
  bounded Working Memory/World Model visibility without durable telemetry
- Headless visual smoke proving the real Gazebo image path, optical frame,
  source timestamp, calibration, simulation provenance, rejection/recovery,
  bounds, lifecycle, motion independence, and clean shutdown
- Immutable bounded visual interpretation producer, normalized 2D region,
  detection, source/result time, optional confidence, and canonical identity
  contracts with no generic metadata or pixel retention
- Exact interpreted-evidence admission against one retained trusted frame and
  one reviewed producer, including simulation/physical provenance separation,
  result ordering, typed rejection, and a 64-reference hard bound
- Immutable compact anonymous person/object observation contracts with exact
  robot, RGB camera, optical frame, source-frame identity, a typed
  interpretation/detection reference, source/result time, normalized region,
  honest optional confidence, typed provenance, and deterministic content
  identity
- Fail-closed person/object admission through the existing Perception boundary,
  requiring one exact fresh retained visual source, admitted interpretation,
  and exact typed detection while preserving deterministic duplicate, reset,
  expiry, substitution rejection, and 64-item interpretation/semantic bounds
- Perception-owned projection from the actually retained semantic-admission
  register into one immutable, non-empty, interpretation-scoped anonymous
  `SemanticEvidenceObservation`; unadmitted, mixed-interpretation, expired, or
  reset sources cannot use the seam
- Conservative Working Memory retention of bounded semantic evidence batches
  with exact frame/interpretation/detection/producer/evaluation revalidation,
  source-time freshness/TTL, duplicate and temporal rejection, dependency
  expiry, bounded watermarks, and no fabricated negative scene knowledge
- Canonically ordered immutable `WorldSnapshot.semantic_states` with optional
  confidence preserved as `float | None`, semantic meaning included in snapshot
  identity, and no conversion into persistent `WorldEntity` records
- Dedicated lifecycle-owned
  `/ayyo/world_model/get_anonymous_semantic_state` query with bounded typed
  `AnonymousSemanticItem`, `AnonymousSemanticState`, and
  `GetAnonymousSemanticState` contracts; one response serializes one public
  immutable snapshot and preserves exact evidence/source/provenance, freshness,
  object category, and explicit confidence presence
- Fixed bounded-wait deterministic JSON query client plus a default-off TEST
  producer and owned visual smoke proving person/object evidence through the
  reviewed Perception → Working Memory → World Model → ROS read path, lifecycle
  fail-closed behavior, motion neutrality, and empty process teardown
- Working Memory replacement per camera/producer and immutable World Model
  visual-interpretation projection with additive fixed read-only query fields
- Default-off deterministic synthetic reference adapter with no model,
  randomness, network, fake confidence, command authority, or Memory OS path
- Dedicated interpreted-visual headless smoke proving the full real-frame to
  synthetic-result read path, adversarial recovery, 1,000-frame bounds,
  lifecycle reactivation, no movement, and zero owned processes after shutdown
- Immutable visual producer manifests, verified model artifacts, recorded
  dataset manifests/sources, typed evaluation policies, bounded metrics,
  deterministic semantic reports, and explicit mechanical decisions
- Sealed evaluated admissions bound exactly to producer/model/dataset/policy/
  report identity, consumed only by the existing Perception Trust Boundary and
  rechecked by bounded Working Memory
- Default-off evaluated live fixture plus two consecutive owned headless smoke
  runs, each proving 5,000-cycle bounds, adversarial recovery, compact query
  provenance, repeat-query identity, lifecycle reactivation, and empty teardown
- Standalone driver-neutral physical-camera package with immutable source
  manifests, explicit unknown device fields, deterministic calibration records,
  bounded exact-time pairing, lifecycle sessions, acquisition diagnostics, and
  no ROS, vendor, persistence, network, control, or pixel-storage dependency
- Sealed one-use physical frame and health admission through the existing
  Perception Trust Boundary, with exact adapter/manifest/calibration/provenance
  binding and rejection of bare, replayed, simulation, and recorded evidence
- Default-off hardware-free physical-camera TEST composition and two consecutive
  owned smoke passes proving 5,000-cycle bounds, calibration/frame rejection,
  recovery, lifecycle epoch isolation, compact query state, and empty teardown
- Distinct `ayyo.camera.head.depth.v1` identity, mechanical mount, ROS optical
  frame, standard fixed depth Image/CameraInfo topics, and default-off 320×240
  Harmonic `32FC1` source without changing the RGB frame contract
- Immutable depth source/calibration manifests, lifecycle sessions, strict
  `16UC1` millimetre and `32FC1` metre validation, compact validity/range/
  payload fingerprints, and bounded exact-time pairing with no retained pixels
- Sealed one-use depth frame and acquisition-health admission through
  Perception into one bounded Working Memory current state and immutable World
  Model/read-only query state, with TEST/simulation/recorded/physical separation
- Dedicated twice-run head-depth smoke covering 5,000 cycles, malformed and
  spoofed evidence, lifecycle recovery, default-off behavior, standard ROS
  types, no authority, and empty owned-process/ROS-graph teardown
- Exact smoke process ownership using a per-run inherited marker and dedicated
  process session, graceful bounded SIGINT-first cleanup, scoped escalation,
  survivor failure, early-exit coverage, and no name-based global killing
- Direct shell-free Gazebo launch ownership fixing the previously orphaned
  simulator child; the interrupted joint-state-publisher traceback is not
  suppressed and was not reproduced under graceful teardown

## Planned, but not implemented

- Final Ayyo CAD-derived visual and collision meshes
- Reviewed final dimensions, joint topology/axes/limits, masses, centres of
  mass, and inertia tensors
- Ayyo-specific RViz and Gazebo graphical review of orientation, scale, pivots,
  symmetry, clipping, collision alignment, and joint direction
- Physical joint, real camera/driver/calibration, IMU, localization, and
  diagnostic-source validation; the implemented camera source is TEST-only
- Force/torque, touch, physical depth hardware, audio, production object/person
  perception,
  navigation, manipulation, and non-synthetic visual producer adapters
- Person/object tracking, face recognition, biometric or persistent person
  identity, complete-scene/negative-detection claims, and persistent
  environment-entity projection of semantic evidence
- Production diagnostic producers, SLAM, visual localization, sensor fusion,
  calibration/bias estimation, trust scoring, clock
  synchronization, and environment-state ROS query transport
- Background/scheduled review invocation, automatic durable consolidation, and
  learning promotion
- Provenance aggregation and advanced consolidation policy
- ROS 2 memory bridge
- Natural-language/model cognition integration
- Live backend discovery and runtime capability attestation
- Authenticated identity, permissions, and approval verification
- Motion/contact safety evaluation and physical emergency-stop integration
- Runtime robot skill implementations
- Production-authorized statically typed ROS services and backend handlers
- Runtime timeout enforcement, resource scheduling, and lock arbitration
- ROS packaging wrappers for the standalone Skill Manager and its upstream
  Python dependency chain; the Runtime Bridge colcon wrapper alone is not a
  self-contained bare-overlay import
- Additional controlled joints, trajectory/whole-body control, friction/contact
  tuning, and validated dynamics
- Manipulation integration
- Navigation integration
- Teach Mode
- Learning pipeline
- Physical hardware

The repository contains the engineering foundation, Memory OS core,
deterministic memory validation policy, a bounded owner-context read model, a
stateless bounded memory candidate-discovery policy, a stateless reviewed memory
candidate-selection policy, an explicit controlled read-only review pipeline,
a deterministic proposal-only Executive layer, an immutable fail-closed Safety
proposal-review boundary, an inert declarative Skill Manager boundary, and a
controlled ROS Runtime Bridge compatibility boundary. The downstream
Simulation Control Foundation can actuate one bounded simulated neck joint only
through explicit development injection and can prove the result from
controller-derived feedback. The independent perception boundary admits
standard joint/IMU, exact body-localization, allowlisted diagnostic, and
compact calibrated visual-frame and bounded interpreted evidence but grants no
authority. The project
does not
provide inferred personality, natural-language understanding, model reasoning,
general perception, physical sensor validation, authenticated
authorization, live backend attestation, physical-safety certification,
production runtime motion, task execution, walking, manipulation, or physical
execution.
