# Architecture

## System flow

```text
Human / Environment
→ Physical Perception
→ Perception Processing
→ Perception Trust Boundary
→ World Model
→ Working Memory
→ Memory Validation / Consolidation
→ Memory OS
→ Personal Context Twin
→ Executive Cognition
→ Immutable Safety Kernel
→ Skill Manager
→ ROS Runtime Bridge
→ Typed Simulation / Hardware Adapter
→ Motion / Control
→ Robot Body
→ Outcome
→ Memory / Learning Update
→ Digital Sleep / Consolidation
```

These are architectural boundaries, not claims of implemented functionality.

The standalone [Memory OS core](MEMORY_OS.md) implements the persistence and
domain boundary for provenance-aware owner memory. The deterministic
[Perception Trust Boundary and Proprioception Foundation](PERCEPTION_TRUST_PROPRIOCEPTION.md)
now admits exact provenance-bound joint and IMU evidence through a standalone
transport-neutral core before it can affect temporary world state. Its live ROS
adapter now also admits exact timestamped `odom` to `base_link` localization
and two allowlisted standard diagnostic components. The dedicated
[Body Localization and Sensor Diagnostics Foundation](BODY_LOCALIZATION_SENSOR_DIAGNOSTICS.md)
defines the fixed APIs, bounded TF2 behavior, simulation/physical provenance,
health mapping, and opt-in Harmonic source. The deterministic
[Head RGB Camera and Visual Observation Foundation](VISUAL_CAMERA_FOUNDATION.md)
adds a fixed standard Image/CameraInfo boundary, an exact optical frame,
deterministic calibration identity, and bounded pixel-free source state. It
does not infer scene semantics or retain video. The
[Visual Perception Processing Foundation](VISUAL_PERCEPTION_PROCESSING.md)
adds bounded typed interpretations tied to an exact admitted frame, an exact
producer allowlist, temporary projection, and a synthetic default-off proof.
It implements no production model and grants no execution authority. Compact
anonymous person/object observations now reuse that Perception trust boundary:
admission requires an exact fresh retained RGB frame, an admitted visual
interpretation, and one exact `PERSON` or `OBJECT` detection. A compact typed
source reference carries the interpretation and detection identities; those
content-addressed identities commit to producer/evaluation provenance, label,
region, time, and optional confidence without copying the full interpretation.
`TEST_PATTERN` cannot become person/object evidence. These observations are not
detectors, identity claims, temporary World Model state, commands, or authority.
The
transport-neutral
[Recorded Visual Producer Evaluation and Perception Quality Gate](VISUAL_PRODUCER_EVALUATION.md)
adds verified model/dataset/policy identity, bounded deterministic metrics,
sealed evaluator evidence, and a default-off live fixture while preserving the
same Perception boundary. Mechanical pass is not production approval. The
driver-neutral
[Physical Head Camera, Calibration, and Diagnostics Foundation](PHYSICAL_HEAD_CAMERA_CALIBRATION_DIAGNOSTICS.md)
adds an exact physical source manifest, bounded calibration validation,
lifecycle-scoped sessions, acquisition diagnostics, and sealed frame/health
admission. Its only executable source is a default-off TEST fixture; simulation
and recorded evidence cannot inherit physical trust from shared topics. The
transport-neutral
[Head Depth / RGB-D Sensor Foundation](HEAD_DEPTH_RGBD_FOUNDATION.md) adds a
distinct depth sensor/optical frame, exact Image/CameraInfo and source-session
validation, explicit `16UC1`/`32FC1` metric semantics, sealed admission, and
bounded compact depth projection. The
[Head RGB-D Synchronization and Fused Observation Foundation](HEAD_RGBD_FUSION_FOUNDATION.md)
then binds separately admitted compact RGB and depth observations by exact
source acquisition time, sealed source/session identity, and deterministic
pair identity through bounded memory and immutable projection. It explicitly
does not validate spatial registration, retain raw data, or grant authority.
The driver-neutral
[Head Audio Perception Foundation](HEAD_AUDIO_PERCEPTION_FOUNDATION.md) adds an
exact TEST microphone source/format manifest, lifecycle-scoped sessions,
immediate raw-PCM reduction, typed diagnostics, sealed frame/health admission,
bounded temporary retention, and compact immutable projection. It performs no
audio interpretation, retains no samples downstream, and grants no authority.
The deterministic
[World Model and Working Memory Foundation](WORLD_MODEL_WORKING_MEMORY.md)
implements immutable current embodied/environment evidence, deterministic
snapshots, freshness, and bounded temporary retention ahead of durable memory.
Its live fixed ROS composition now projects standard joint-state, simulated
body-IMU, localization, explicit health, and default-off compact TEST audio
evidence; it does not fabricate missing state or persist telemetry. The
deterministic
[Memory Validation policy](MEMORY_VALIDATION.md) now evaluates candidate evidence
before explicitly approved mutations reach Memory OS. The read-only
[Personal Context Twin](PERSONAL_CONTEXT_TWIN.md) projects deterministic,
owner-isolated state from Memory OS. The proposal-only
[Executive Cognition layer](EXECUTIVE_COGNITION.md) consumes PCT through its
public API, validates explicit capability contracts, and produces deterministic
declarative plans. The [Immutable Safety Kernel](SAFETY_KERNEL.md) independently
validates those proposals and emits deterministic fail-closed review decisions.
The declarative [Skill Manager](SKILL_MANAGER.md) now registers immutable skill
contracts and binds unchanged Safety-reviewed proposal steps without executing
them. The controlled [ROS Runtime Bridge](ROS_RUNTIME_BRIDGE.md) validates those
binding results against an explicit ROS service endpoint allowlist and models
dispatch eligibility and transport acceptance without providing a concrete ROS
client. The downstream [Simulation Control Foundation](SIMULATION_CONTROL.md)
now provides a typed, URDF-bounded controller adapter and one explicitly
enabled development injection path. Production movement remains closed because
Safety v1 defers physical movement and no production runtime motion service is
implemented. Identity/approval authority, runtime skill implementations,
physical-safety subsystems, and physical control remain separate future layers.

The [Robot Description & Simulation Foundation](ROBOT_DESCRIPTION_SIMULATION.md)
now provides an independent authoritative Xacro/TF model, RViz display path,
static default Gazebo Harmonic spawn, and an opt-in one-joint ros2_control
configuration. It imports no cognitive or authorization layer. Movement is
available only through the separate typed development adapter when both
control flags are explicit. The
[final mesh workflow](AYYO_MESH_IMPORT.md) defines how reviewed Ayyo assets will
replace proxy geometry without duplicating or bypassing frame semantics.

## Invariants

- General foundations may be pretrained.
- Owner-specific autobiographical memory starts empty.
- Perception is evidence, not authority.
- Memory stores provenance and uncertainty.
- The Personal Context Twin models owner context but is not the owner and is not
  an authority.
- Foundation models never directly command raw motors.
- Cognition produces bounded structured actions.
- Safety remains independent from learned behavior.
- Learned policies are versioned and evaluated before promotion.
- Embodiment remains replaceable.
- Cloud services are never required for basic safety.
- The architecture supports simulation-to-hardware migration.

## Boundary responsibilities

- Perception processing decodes only fixed standard sensor interfaces. The
  standalone trust boundary owns exact robot/source/sensor/frame/provenance,
  clock, timestamp, numeric, covariance, freshness, duplicate/order, identity,
  and resource admission before evidence can affect world or memory state. It
  cannot grant identity, authority, permission, safety, or execution.
- The localization adapter owns one fixed `odom` to `base_link` exact-time TF2
  lookup with bounded wait/cache and typed failure health. It never requests
  latest TF, publishes duplicate public TF, aliases frames, or fabricates a
  pose. The diagnostics adapter owns an exact two-component name/hardware
  allowlist and treats bounded message/key/value text as inert evidence only.
- The visual adapter owns fixed head Image and CameraInfo topics, exact optical
  frame and acquisition-time pairing, bounded standard calibration validation,
  image-shape validation, and immediate reduction to compact pixel-free
  metadata. Frame receipt establishes availability, not camera health or scene
  understanding. Pixel buffers cannot enter snapshots or durable memory.
- The physical-camera adapter additionally owns an explicit source allowlist,
  exact calibration record, active session, bounded metadata pairing, and
  acquisition-health evidence. Only a sealed frame/health pair may enter the
  Perception boundary; inactive, old-session, simulation, recorded, wrong-frame,
  or wrong-calibration evidence fails closed. It owns no driver, control, skill,
  or movement authority.
- The depth adapter owns an independent source/producer manifest, calibration
  record, optical frame, active session, exact-time bounded pairing, strict
  metric encoding/payload validation, compact statistics, and acquisition
  health. Only its sealed frame/health pair may enter Perception; raw depth,
  point clouds, geometry, and authority are not represented.
- The RGB-D synchronizer owns exact source-time pairing of separately admitted
  RGB and depth evidence, typed source/producer/frame/calibration/session
  relationships, bounded pending queues, deterministic pair identity, and a
  sealed one-use Perception admission. Temporal synchronization does not imply
  spatial registration. Fused evidence contains no raw buffers and cannot
  command, authorize, execute, persist, or learn.
- The head-audio adapter owns one exact microphone source, producer, mount
  frame, format, payload bound, lifecycle session, acquisition/result time,
  and compact payload summary. Only its sealed one-use frame/health pair may
  enter Perception; raw PCM cannot enter Working Memory or the World Model, and
  audio evidence cannot command, authorize, execute, persist, or learn.
- Visual interpretation producers operate only after frame admission. The
  existing trust boundary owns exact source-frame, camera, optical-frame,
  acquisition/result-time, producer, provenance, ordering, fingerprint, and
  resource admission. Working Memory keeps one current result per
  camera/producer plus bounded recent evidence; interpretation is never a
  command, permission, identity claim, or durable-memory write.
- Person/object admission reuses the retained visual-frame boundary and accepts
  only content-identity-valid anonymous evidence matching one exact fresh RGB
  source, one retained admitted interpretation, and one exact detection.
  Interpretation and semantic registers are TTL/reset scoped and capped at 64;
  deterministic oldest-result eviction invalidates dependent semantics. The
  path retains no pixels, does not project Person/Object evidence into Working
  Memory or World Model, and grants no identity, permission, safety, skill,
  Executive, movement, or execution authority.
- Evaluated producers additionally require one exact registered manifest,
  verified model artifact, immutable dataset and policy, successful semantic
  report identity, and a sealed one-use authorization. A bare result or
  self-asserted pass reference cannot establish Perception trust.
- World Model owns transport-neutral provenance-bound current robot/environment
  observations, authoritative body-value validation, IMU/pose/covariance/
  availability contracts, discrete freshness, and canonical immutable
  snapshots without importing ROS or Gazebo.
- Working Memory owns bounded temporary current/recent evidence, TTL, duplicate
  suppression, temporal ordering, and deterministic eviction. It cannot write
  Memory OS; future durable candidates must still pass Memory Validation.
- Memory validation owns deterministic admission, conservative identity
  normalization, duplicate decisions, correction authority, and contradiction
  review without selecting probabilistic truth.
- The Memory OS preserves evidence, revisions, retractions, and unresolved
  conflicts without depending on ROS 2 or future cognitive components.
- The Personal Context Twin owns deterministic read projection, explicit
  resolved/conflicted/unknown state, owner isolation, evidence references, and
  snapshot versioning. It does not own persistence, truth selection,
  permissions, cognition, or safety.
- Executive Cognition owns structured request validation, context dependency
  checks, deterministic declarative planning, explicit proposal blockers, and
  stale-decision evidence. It cannot grant approval, claim safety, execute a
  plan, or mutate PCT or Memory OS.
- Any future model gateway may translate input into a structured request but
  cannot bypass Executive invariants or supply authority.
- The immutable Safety Kernel owns deterministic proposal validation, explicit
  hazard classification, conservative plan aggregation, approval/prerequisite
  retention, and proposal/policy binding. Eligibility means only downstream
  consideration; it cannot grant approval, certify physical safety, or execute.
- The Skill Manager owns explicit immutable skill/backend/resource contracts,
  bounded parameter compatibility, deterministic registry selection, and
  proposal/Safety/skill/registry traceability. It cannot grant approval,
  schedule resources, call a backend, use ROS, or execute an invocation.
- The ROS Runtime Bridge owns deterministic validation, exact Skill-to-service
  endpoint compatibility, stale-request detection, and transport-boundary
  results. It cannot grant approval, weaken upstream restrictions, discover or
  dynamically load endpoints, schedule resources, claim task completion, or
  control simulation or hardware.
- The simulation-control adapter owns exact joint allowlisting, authoritative
  URDF-limit validation, controller/hardware lifecycle evidence, dispatch-time
  time/authority revalidation, and feedback-backed results. Its development
  service is not production runtime authority.
- Future physical controls remain isolated from higher-level contracts and
  constrained by the Runtime Bridge plus dedicated lower safety systems.
- Robot description single-owns kinematic and fixed sensor-frame semantics.
  RViz and Gazebo
  consume that same source; simulation does not maintain a duplicate Ayyo
  model, import cognition, or create an authorization bypass. Control mode has
  one command interface, while the body IMU is observation-only in both static
  and controlled simulation. Opt-in Harmonic localization and head RGB camera
  are replaceable simulation observation sources with distinct provenance, not
  motion authority or physical localization/calibration claims.
- Learning updates remain candidates until evaluation and controlled promotion;
  consolidation does not bypass safety or permissions.
