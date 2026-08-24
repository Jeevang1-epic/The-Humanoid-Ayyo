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
[World Model and Working Memory Foundation](WORLD_MODEL_WORKING_MEMORY.md)
implements immutable current embodied/environment evidence, deterministic
snapshots, freshness, and bounded temporary retention ahead of durable memory.
Its live fixed ROS composition now projects standard joint-state, simulated
body-IMU, localization, and explicit health evidence; it does not fabricate
missing state or persist telemetry. The deterministic
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
  and controlled simulation. Opt-in Harmonic localization is a replaceable
  simulation observation source with distinct provenance, not motion authority
  or a physical localization claim.
- Learning updates remain candidates until evaluation and controlled promotion;
  consolidation does not bypass safety or permissions.
