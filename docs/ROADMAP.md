# Roadmap

The implementation progresses through the following stages without fixed dates.
Each stage must preserve the architecture and safety contracts established by the
foundation.

1. **Foundation** — Repository standards, architecture contracts, ROS 2 package
   foundations, and local validation.
2. **Memory OS + Personal Context Twin** — Provenance-aware memory boundaries,
   owner modeling, and contradiction handling.
3. **Executive Cognition** — Structured reasoning interfaces, uncertainty
   handling, and bounded action proposals.
4. **Identity / Permissions / Safety** — Explicit authority, permission checks,
   immutable runtime safety boundaries, declarative skill contracts, and
   auditability.
5. **ROS 2 simulated embodiment** — Replaceable simulation interfaces and a first
   justified robot description.
6. **Developmental simulation scenarios** — Repeatable environments for testing
   perception, planning, interaction, and safe outcomes.
7. **Teach Mode / Learning Pipeline** — Demonstration capture, bounded
   candidate-policy evaluation, promotion/rollback eligibility, and immutable
   version registration foundations are implemented, followed by inert exact
   authority-approval evidence and future-activation eligibility. Training,
   execution, production authentication/approval enforcement, activation, and
   live state changes remain separately reviewed.
8. **Software Showcase** — An integrated, truthful demonstration of implemented
   software capabilities. Foundation v1 is implemented as a deterministic
   public-contract catalog and canonical report with explicit TEST, simulation,
   DEVELOPMENT-only, inert, unavailable, and physical-validation labels.
9. **Physical Manipulator** — Safety-bounded manipulation on limited hardware.
10. **Mobile / Upper-Body Prototype** — Integrated mobility and upper-body
    research platform.
11. **Full Humanoid Research** — Long-term whole-body embodiment research after
    earlier safety and validation gates are mature.

Stages 1 through 3 now have bounded v1 implementations. The immutable
proposal-review portion of stage 4 is implemented as Safety Kernel v1, and the
declarative Safety-to-runtime contract boundary is implemented as Skill Manager
v1. A preparatory controlled runtime boundary ahead of stage 5 is implemented
as ROS Runtime Bridge v1 with a service-only endpoint allowlist, pure
eligibility, and an unavailable-by-default transport boundary. Stage 5 now has
Robot Description & Simulation Foundation v1: a canonical mesh-ready
frame/joint model, deterministic validation, separate RViz and Gazebo Harmonic
launch paths, a static development spawn, and a fixed clock/sensor ros_gz
allowlist.
Stage 5 now also has Simulation Control & Actuation Foundation v1: opt-in
Jazzy/Harmonic `gz_ros2_control`, one URDF-bounded neck position interface,
controller-derived state, deterministic typed control contracts, and a
separately flagged development command service. This is infrastructure proof,
not integrated production execution. Physical-movement Safety remains
`DEFERRED`, and no production Runtime Bridge motion endpoint is implemented.
The cross-stage World Model and Working Memory Foundation v1 is also implemented:
transport-neutral embodied/environment observations, deterministic snapshots,
bounded temporary evidence, and an opt-in lifecycle ROS joint-state adapter now
provide current observed body state without coupling semantics to Gazebo or
writing telemetry to durable memory. This is proprioceptive infrastructure, not
general perception or a developmental simulation scenario framework.
Perception Trust Boundary and Proprioceptive Observation Foundation v1 now adds
exact transport-neutral sensor admission, immutable IMU/pose/covariance/health
contracts, deterministic disappearance, one authoritative body-IMU mount, and
a live simulated standard-IMU proof through the same World Model. Body
Localization and Sensor Diagnostics Foundation v1 now activates the narrow
pose/health seams: exact timestamped `odom` to `base_link` lookup, an opt-in
standard simulated odometry source, explicit typed failure health, and a
bounded two-component standard ROS diagnostics allowlist. These are
observation foundations, not SLAM, fusion, navigation, or authority.
Head RGB Camera and Visual Observation Foundation v1 now adds an exact optical
frame, a default-off standard `Image`/`CameraInfo` simulation source, fixed
calibration-aware admission, and bounded pixel-free visual state. It does not
implement detection, recognition, tracking, scene understanding, visual
localization, or a physical camera driver.
Visual Perception Processing Foundation v1 now adds bounded typed normalized
image-region observations tied to an exact admitted source frame, exact
producer/model/adapter identity, provenance and source/result time checks,
bounded Working Memory/World Model projection, and a deterministic synthetic
reference proof. It does not implement or claim production machine perception.
Person/Object Semantic Producer Binding Foundation v1 now adds compact
anonymous person/object evidence and fail-closed binding to one exact fresh
retained RGB source frame, admitted visual interpretation, and typed detection
through the existing Perception boundary. It preserves optional confidence
without fabrication and adds deterministic identity, duplicate/reset/expiry
behavior, and hard interpretation/semantic bounds, but no detector, tracking,
face or persistent identity, physical validation, authority, or motion.
Anonymous Person/Object Semantic Scene State Foundation v1 now adds the narrow
next step: Perception can project actually retained admissions into an
interpretation-scoped transport-neutral evidence batch, Working Memory retains
bounded recent batches under source-time freshness/TTL and dependency expiry,
and immutable World Snapshots expose canonically ordered anonymous semantic
state. Because upstream admission does not promise complete negative results,
this is deliberately a conservative recent-evidence model: newer partial
evidence does not claim that omitted people or objects are absent. It creates
no tracker, stable entity, persistent identity, environment entity, Memory OS
write, authority, or motion path.
Anonymous Semantic ROS Query Foundation v1 now adds exactly one read-only ROS
transport for that already-projected state. A lifecycle-owned fixed service
uses hard-bounded typed item/state arrays, preserves evidence provenance and
explicit optional confidence, and a deterministic client renders canonical
JSON. A default-off TEST producer and owned visual smoke validate the full
frame-to-query path. Empty retained evidence remains unknown physical-scene
occupancy; the query creates no perception, entity, persistence, authority, or
motion side effect.
Working Memory → Memory Validation Candidate Bridge Foundation v1 now adds an
explicit standalone staging layer. A caller must propose the memory
type/subject/predicate/value and select one exact currently retained evidence
identity. The bridge reconstructs fingerprints and semantic source chains,
requires fresh evidence, permits only exact microsecond-representable
`ROS_SYSTEM_TIME` conversion to UTC, preserves genuine confidence including
`0.0`, rejects missing confidence, and derives `DIRECT_OBSERVATION` provenance.
Anonymous person/object evidence can support only its exact anonymous episodic
observation. Candidate evaluation and application remain separate caller
actions; there is no automatic selection, durable write, identity or preference
inference, correction, Personal Context update, ROS service, or learning loop.
Reviewed Memory Candidate Selection Policy Foundation v1 now adds the next
explicit transport-neutral step over immutable candidate snapshots. A bounded
caller-supplied batch receives versioned selected/deferred/rejected-for-review
decisions with canonical candidate identities and typed reasons. Direct
observations require exact staging eligibility; confidence is never synthesized;
anonymous semantics remain anonymous; and all supplied duplicate propositions
or conflicts are deferred without choosing a winner. The policy is stateless
and cannot generate candidates, evaluate/apply Memory Validation, persist,
correct, learn, infer identity/preferences/relationships, or run automatically.
Bounded Memory Candidate Discovery Foundation v1 now adds an explicit stateless
operation over currently retained Working Memory evidence. It inspects at most
64 retained envelopes and deterministically returns at most 32 immutable exact
`ConsolidationRequest` proposals plus at most 64 typed diagnostics. Version 1
supports only fresh, exact-source-chain anonymous visual person/object evidence
under reviewed microsecond-compatible `ROS_SYSTEM_TIME`, with honest confidence
including `0.0`. It does not invoke staging, selection, validation, apply,
persistence, consolidation, learning, identity, preference, social, ownership,
absence, permanence, correction, ROS, or action behavior.
Controlled Memory Candidate Invocation and Review Pipeline Foundation v1 now
coordinates those reviewed seams only after explicit caller actions. `prepare`
invokes discovery once and returns an immutable verifiable plan;
`execute_review` requires that exact plan plus a canonical proposal-ID allowlist,
restages against current Working Memory, invokes selection once over the full
successful batch, and evaluates only selected candidates through a narrow
read-only interface. Immutable entries and batches retain deterministic full
lineage and typed partial failures. There is no application, durable write,
automatic learning, background invocation, ROS, or action authority.
Recorded Visual Producer Evaluation and Perception Quality Gate v1 now adds
explicit producer registration, verified model artifact identity, immutable
recorded dataset/policy/report contracts, deterministic bounded evaluation,
sealed Perception admission, and a default-off ROS fixture. It remains a TEST
foundation, not model approval or physical-camera validation.
Physical Head Camera Adapter, Calibration, and Camera Diagnostics Foundation v1
now adds a driver-neutral reviewed-source contract, deterministic calibration
identity, bounded Image/CameraInfo pairing, lifecycle sessions, acquisition
health, sealed Perception admission, and a default-off hardware-free TEST
composition. It validates the future integration boundary, not any real camera,
driver, clock, lens calibration, image quality, or edge-device performance.
Head Depth / RGB-D Sensor Foundation v1 now adds a distinct depth optical frame,
typed source/calibration/session identity, strict `16UC1`/`32FC1` semantics,
bounded exact-time Image/CameraInfo admission, compact pixel-free Working
Memory/World Model state, and default-off TEST/Gazebo seams. It does not add a
physical depth device, RGB-D fusion, point clouds, geometry, SLAM, navigation,
manipulation, or authority.
Head RGB-D Synchronization and Fused Observation Foundation v1 now adds a
bounded exact-source-time synchronizer for separately admitted compact RGB and
depth evidence, deterministic pair/source/session identity, sealed Perception
admission, bounded current/recent Working Memory references, immutable World
Model projection, and a default-off owned TEST composition. It establishes
temporal synchronization only; physical hardware, clock behavior, extrinsics,
pixel registration, point clouds, geometry, inference, SLAM, navigation,
manipulation, and authority remain unvalidated or out of scope.
Head Audio Perception Foundation v1 now adds one reviewed TEST microphone
manifest, an exact bounded mono 16 kHz PCM transport, lifecycle/session
isolation, immediate compacting, typed diagnostics, sealed Perception
admission, bounded Working Memory, immutable World Model/query projection, and
a default-off owned TEST composition. It retains no raw samples downstream and
adds no speech, sound interpretation, identity, skill, movement, or control
authority. Real microphones, drivers, hardware, calibration, acoustics,
beamforming, echo cancellation, speech/wake-word models, production timing,
and real-world noise remain unvalidated.

Stage 6 now has Developmental Simulation Scenario Harness Foundation v1. A
dedicated development/test package defines six immutable bounded scenarios and
three fixed launch profiles over the existing Gazebo, ROS, World Model,
Executive, Safety, Skill Manager, Runtime Bridge, and simulation-control
contracts. Headless validation proves embodied and anonymous TEST observation,
production physical-request deferral with zero dispatch or motion, separate
development-only neck actuation/reset, out-of-range rejection, optional-source
absence, deterministic reports, and owned-process teardown. This is scenario
orchestration against proxy geometry, not production motion or physical
validation.

Stage 7 now has Teach Mode Demonstration Capture Foundation v1. The standalone
transport-neutral package records only explicit caller-supplied typed events or
adapts an already-completed immutable Stage-6 report. Episodes are bounded,
immutable, canonically serialized, content-addressed, clock-explicit, and
outcome-explicit. The three first integration examples retain DEVELOPMENT-only
motion/reset evidence, production Safety `DEFERRED` with zero movement, and
invalid-command `REJECTED` evidence. This is historical evidence capture, not
learning, policy generation/evaluation, promotion, rollback, executable replay,
memory persistence, teacher authentication, or physical demonstration capture.

Stage 7 now also has Demonstration Candidate Policy and Offline Evaluation
Foundation v1. An explicit bounded corpus separates candidate evidence from
holdout evaluation with distinct content identities. Inert versioned candidate
manifests bind only candidate evidence; a pure evaluator verifies explicit
caller-supplied holdout trials and emits immutable complete, incomplete, or
does-not-meet reports. This adds no candidate execution, model runner, training,
promotion, rollback, persistence, Safety authority, runtime path, or motion.

Stage 7 now also has Candidate Policy Promotion & Rollback Control Plane
Foundation v1. Explicit caller-owned criteria and requests bind exact candidate,
offline-report, holdout, target-stage, known-good, provenance, reason-evidence,
and policy-contract lineage identities. Pure evaluators emit only immutable
promotion or rollback eligibility evidence. They do not install, load, execute,
activate, dispatch, promote, or roll back a policy and own no registry,
persistence, ROS/Gazebo, simulation, or hardware authority.

Stage 7 now also has Candidate Policy Registry and Immutable Version Lineage
Foundation v1. An explicit registration request binds the exact verified
candidate/report/criteria/request/eligible-decision chain. Pure registration
produces immutable exact-version records and bounded canonical snapshots;
lineage exists only when a candidate explicitly identifies an already-
registered compatible parent. Exact duplicate registration is explicit and
idempotent. Semantic-version ordering does not imply ancestry or preference.
The registry has no latest/active pointer, persistence, activation, model
loading/execution, automatic promotion/rollback, Runtime, ROS/Gazebo,
simulation, hardware, or Safety authority.

Stage 7 now also has Human / Authority Approval Evidence and Activation
Eligibility Boundary Foundation v1. Immutable authority references distinguish
`UNVERIFIED`, `EXTERNALLY_VERIFIED`, and `REVOKED` assertions without claiming
to authenticate anyone. Exact approval requests and evidence bind the complete
registered candidate/version/registration/promotion chain, approval scope, and
authority identity. A pure evaluator fails closed for unverified, revoked,
rejected, or revoked-approval evidence and can otherwise return only
`ELIGIBLE_FOR_FUTURE_ACTIVATION`. It provides no activation gate, active state,
persistence, model loading/execution, background work, network authentication,
Runtime, ROS/Gazebo, simulation, hardware, or Safety authority.

Stage 8 now has Software Showcase Foundation v1. A standalone top-level package
imports reviewed public contract identities into one closed 15-capability,
19-evidence catalog. Immutable manifests and reports preserve exact provenance,
truthful classifications, explicit non-claims, deterministic identities,
canonical serialization, and hard bounds. A local CLI can list, inspect,
report, or verify the catalog without invoking the represented packages. Two
catalog entries make production policy activation and physical hardware
validation explicitly unavailable. The showcase adds no cognition, Safety,
Skill, Runtime, ROS/Gazebo, persistence, learning, authentication, policy-state,
execution, or hardware authority; lower layers have no reverse dependency.

Final Ayyo assets, graphical controlled-design validation, additional joints,
trajectory/whole-body controllers, validated dynamics/contact behavior,
production authenticated identity, permissions, external approval enforcement,
live backend attestation, production typed ROS services, audit persistence,
timeout/resource enforcement, runtime skill implementations, and
physical-safety integration remain future work. Production visual producer
promotion and live physical audio/depth/force/touch perception, physical
camera/IMU/localization validation, production diagnostic producers, spatial
RGB-D registration, physical sensor fusion, SLAM, environment entity
production, background/scheduled review invocation, automatic durable
consolidation, additional Teach Mode sources, authenticated teacher/owner
identity, physical or recorded-source adapters, raw-recording management,
candidate generation, model runners, training, executable replay, automatic
rollback, automatic learning promotion, production approval workflow, policy
activation, and installed/active policy state also remain future work. Executive
proposals, Safety eligibility,
Skill Manager runtime-handoff eligibility, Runtime Bridge
eligibility, transport acceptance, development injection, and simulated motion
do not count as production authorization or physical-safety certification.
