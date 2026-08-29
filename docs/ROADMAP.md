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
7. **Teach Mode / Learning Pipeline** — Demonstration capture, candidate policy
   versioning, evaluation, promotion, and rollback.
8. **Software Showcase** — An integrated, truthful demonstration of implemented
   software capabilities.
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

Final Ayyo assets, graphical controlled-design validation, additional joints,
trajectory/whole-body controllers, validated dynamics/contact behavior,
authenticated identity, permissions, approval verification, live backend
attestation, production typed ROS services, audit persistence,
timeout/resource enforcement, runtime skill implementations, and
physical-safety integration remain future work. Production visual producer
promotion and live audio/depth/force/touch perception, physical
camera/IMU/localization validation, production diagnostic producers, SLAM,
sensor fusion, environment entity production, and
reviewed Working-Memory-to-Memory-Validation consolidation also remain future
work. Executive proposals, Safety
eligibility, Skill Manager runtime-handoff eligibility, Runtime Bridge
eligibility, transport acceptance, development injection, and simulated motion
do not count as production authorization or physical-safety certification.
