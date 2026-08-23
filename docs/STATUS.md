# Project Status

## Verified development environment

- Ubuntu 24.04 under WSL2
- ROS 2 Jazzy installed
- Gazebo Harmonic installed
- RViz2 installed
- MoveIt 2 installed
- Nav2 installed
- ros2_control installed
- ros_gz installed
- ROS publisher/subscriber smoke test passed
- Generic Gazebo GUI environment smoke test passed
- Generic RViz GUI environment smoke test passed
- Ayyo-specific RViz/Gazebo graphical review not executed in this milestone

## Implemented

- Architecture, roadmap, and safety contracts
- ROS 2 workspace with `ament_cmake` foundations for `ayyo_interfaces` and
  `ayyo_bringup`, plus installable `ayyo_runtime_bridge`, authoritative
  `ayyo_description`, and dedicated `ayyo_simulation` packages
- Local environment verification, build, and test scripts
- Standalone Memory OS core with typed records and mandatory provenance
- SQLite persistence with schema versioning, foreign keys, WAL journaling,
  transactional corrections, retractions, and conflict records
- Deterministic memory queries and revision/conflict inspection
- Standalone deterministic candidate validation with conservative identity and
  JSON normalization
- Typed duplicate, contradiction, correction, rejection, and review decisions
- Explicit evaluation/application separation using only the public Memory OS API
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
  root, 35 links, 34 joints, 18 provisional movable joints, and an explicit
  head camera mounting frame without a sensor implementation
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
  static non-actuating spawn from the authoritative Xacro, and no duplicate
  robot model
- Explicit one-way Gazebo `/clock` to ROS `/clock` bridge with no commands,
  sensors, services, actions, or wildcard bridging
- Dormant ros2_control joint-interface macro with no plugin, transmission,
  controller manager, controller configuration, or actuation
- Reproducible headless installed-package, node, TF, bridge, spawn, and bounded
  shutdown smoke validation

## Planned, but not implemented

- Final Ayyo CAD-derived visual and collision meshes
- Reviewed final dimensions, joint topology/axes/limits, masses, centres of
  mass, and inertia tensors
- Ayyo-specific RViz and Gazebo graphical review of orientation, scale, pivots,
  symmetry, clipping, collision alignment, and joint direction
- Perception
- Provenance aggregation and advanced consolidation policy
- ROS 2 memory bridge
- Natural-language/model cognition integration
- Live backend discovery and runtime capability attestation
- Authenticated identity, permissions, and approval verification
- Motion/contact safety evaluation and physical emergency-stop integration
- Runtime robot skill implementations
- Concrete statically typed ROS service transport adapters and backend handlers
- Runtime timeout enforcement, resource scheduling, and lock arbitration
- Dynamic Gazebo simulation, gz_ros2_control, transmissions, joint-state
  broadcaster, controllers, friction/contact tuning, and dynamics validation
- Manipulation integration
- Navigation integration
- Teach Mode
- Learning pipeline
- Physical hardware

The repository contains the engineering foundation, Memory OS core,
deterministic memory validation policy, a bounded owner-context read model, a
deterministic proposal-only Executive layer, an immutable fail-closed Safety
proposal-review boundary, an inert declarative Skill Manager boundary, and a
controlled ROS Runtime Bridge compatibility boundary. It does not provide
inferred personality, natural-language understanding, model
reasoning, perception, authenticated authorization, live backend attestation,
physical-safety certification, a concrete ROS service client, task execution,
physical execution, or simulated robot behavior.
The simulation foundation can render and statically spawn development geometry,
but it still provides no simulated task behavior or actuation.
