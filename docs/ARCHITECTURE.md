# Architecture

## System flow

```text
Human / Environment
→ Physical Perception
→ Perception Processing
→ Perception Trust Boundary
→ World Model
→ Working Memory
→ Explicit Bounded Memory Candidate Discovery
→ Explicit Memory Candidate Staging
→ Reviewed Memory Candidate Selection
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

Stage-7 demonstration evidence is a separate side path, not an execution or
memory-update shortcut:

```text
explicit caller events or immutable Stage-6 report
→ Teach Mode demonstration capture
→ immutable bounded demonstration episode
→ explicit candidate-evidence / holdout corpus
→ inert candidate-policy identity
→ explicit offline trial results
→ immutable offline evaluation report
→ explicit caller-owned promotion criteria and request
→ immutable promotion eligibility decision
├→ explicit candidate registration and immutable version lineage
│ → bounded policy registry snapshot
│ → exact approval request and externally supplied authority reference
│ → one immutable authority approval evidence object
│ → pure future-activation eligibility decision
│ → stop
└→ explicit known-good reference and rollback evidence
  → immutable rollback eligibility decision
→ stop
```

Stage-8 showcase inspection is a separate top-level read-only presentation
path, not part of either authority flow:

```text
reviewed public contract identities
→ closed truthful capability catalog
→ immutable canonical showcase manifest/report
→ developer inspection output
→ stop
```

The [Software Showcase Foundation](SOFTWARE_SHOWCASE.md) depends downward on
reviewed public interfaces across the implemented architecture. No represented
package depends back on it. `SUPPORTED_BY_PUBLIC_CONTRACT` means only that one
exact imported contract backs the displayed classification; it is not runtime
execution, live validation, authentication, activation, deployment, physical
safety, or hardware proof. The showcase calls none of the represented
subsystems and has no persistence, network, process, ROS, or hardware surface.

The standalone
[Teach Mode Demonstration Capture Foundation](TEACH_MODE_DEMONSTRATION_CAPTURE.md)
depends only on public immutable developmental-scenario contracts. It records
typed historical references, ordering, source-clock semantics, provenance, and
outcomes. No developmental or production layer depends back on Teach Mode. A
captured episode grants no truth, teacher identity, learning, persistence,
Safety, Skill, Runtime, replay-execution, or motion authority.

The standalone
[Demonstration Candidate Policy and Offline Evaluation Foundation](DEMONSTRATION_POLICY_OFFLINE_EVALUATION.md)
depends only on Teach Mode. Separate content-addressed candidate and holdout
sets enforce the leakage boundary: candidate artifacts store only the candidate
set identity. Pure evaluation retains the bounded canonical corpus snapshot and
complete caller-supplied trial evidence in its report, then derives every
partition, count, metric, reason, coverage value, and disposition from that
evidence. It grants no training, execution, promotion, Safety, Skill, Runtime,
simulation, or hardware authority. Teach Mode and every lower layer remain
unaware of it.

The standalone
[Candidate Policy Promotion and Rollback Control Plane](CANDIDATE_POLICY_PROMOTION_ROLLBACK_CONTROL.md)
depends only on the learning/evaluation layer. Pure evaluators bind exact
candidate, report, criteria, holdout, known-good, reason-evidence, and lineage
identities into immutable eligibility decisions. Eligibility is evidence for a
later review boundary, not an installation, activation, execution, automatic
promotion/rollback, Runtime, ROS/Gazebo, or hardware action. The package owns no
policy registry or active-policy state, and lower layers remain unaware of it.

The standalone
[Candidate Policy Registry and Immutable Version Lineage Foundation](CANDIDATE_POLICY_REGISTRY_LINEAGE.md)
depends only on promotion control. It reuses the authoritative promotion
evaluation route, requires an exact eligible candidate/report/criteria/request/
decision chain, and derives immutable exact-version records in bounded
content-addressed snapshots. Candidate parentage is accepted only when the
upstream manifest explicitly names an exact already-registered compatible
parent; semantic-version ordering never establishes ancestry. Registration is
not approval, activation, deployment, execution, or physical safety. The
registry has no mutable alias, active-policy pointer, persistence, model loader,
Runtime, ROS/Gazebo, or hardware authority, and every lower layer remains
unaware of it.

The standalone
[Human / Authority Approval Evidence and Activation Eligibility Boundary Foundation](HUMAN_AUTHORITY_APPROVAL_ACTIVATION_ELIGIBILITY.md)
depends only on Policy Registry. In the repository dependency-arrow convention,
the complete side path is `approval_eligibility → policy_registry →
promotion_control → learning_evaluation → teach_mode`: each package points to
the lower package it consumes. It binds one exact registered version, its
candidate/version/registration/promotion identities, one approval request, one
authority reference, and one approval evidence object before a pure evaluator
can return eligibility for a separately reviewed future activation stage.
`UNVERIFIED` authority evidence is always ineligible. `EXTERNALLY_VERIFIED`
means only that caller-supplied provider and evidence identities are present;
this package does not authenticate a human or validate those external systems.
It has no active state, persistence, model loader, execution path, background
worker, network, Runtime, ROS/Gazebo, hardware, or Safety authority, and no
lower layer depends on it.

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
detectors, identity claims, commands, or authority. The anonymous semantic-state
continuation projects only actually admitted observations into a compact
interpretation-scoped World Model contract. Working Memory retains bounded
recent evidence under source-time freshness/TTL; immutable snapshots expose it
without creating persistent entities, tracking identity, or negative scene
knowledge from omitted detections.
One dedicated ROS query now serializes that already-projected semantic state
from exactly one public immutable `WorldSnapshot`. Its item/state arrays and
strings are bounded, optional confidence uses explicit presence, and empty
evidence means only that nothing is currently retained. The lifecycle-owned
service and fixed JSON client do not admit evidence, run a producer, refresh
TTL, create entities, persist records, command motion, or grant authority.
The standalone
[Bounded Memory Candidate Discovery Policy](MEMORY_CANDIDATE_DISCOVERY.md)
performs an explicit caller-triggered bounded read of retained Working Memory
evidence. It emits only canonical immutable requests for exact anonymous visual
person/object observations that can satisfy the staging eligibility contract.
It does not stage, select, validate, apply, persist, infer identity/preferences,
or run automatically.
The standalone
[Working Memory Candidate Bridge](WORKING_MEMORY_CONSOLIDATION.md) now occupies
the explicit seam between temporary evidence and `CandidateEvidence`. It reads
only caller-selected retained evidence, reconstructs content identity and
semantic source chains, requires fresh reviewed UTC-compatible evidence and an
honest confidence, and derives bounded direct-observation provenance. It has no
automatic selection, evaluator, apply, persistence, correction, ROS, Personal
Context, or action surface.
The explicit
[Reviewed Memory Candidate Selection Policy](REVIEWED_MEMORY_CANDIDATE_SELECTION.md)
then receives immutable candidate snapshots rather than reaching back into
Working Memory. It emits deterministic selected/deferred/rejected-for-review
decisions with typed reasons, conflict/duplicate deferral, policy identity, and
hard resource bounds. Selection means only suitable to present for review; it
does not establish truth, owner approval, durable learning, identity, or action
authority, and it cannot evaluate or apply a Memory Validation decision.
The explicit
[Controlled Memory Review Pipeline](CONTROLLED_MEMORY_REVIEW_PIPELINE.md)
coordinates these existing seams without collapsing their authority boundaries.
Preparation snapshots one bounded discovery result; execution requires the
exact plan and a caller proposal-ID allowlist, restages current evidence, calls
selection once over all successful candidates, and evaluates selected
candidates sequentially through a narrow read-only protocol. It exposes no
application or persistence operation and makes no transactional batch claim.
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
implemented. Production identity authentication and approval enforcement,
runtime skill implementations,
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
- A demonstration is bounded historical evidence, not a learned policy,
  executable command, authenticated teacher statement, or persistence grant.
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
  projection seam reads only that actually admitted register and preserves
  exact frame, interpretation, detection, producer/evaluation, region,
  confidence, and provenance identities. Working Memory rechecks those sources,
  retains at most 64 conservative evidence batches plus its bounded recent
  window, and removes dependent state with source expiry/reset. World Snapshot
  state remains anonymous and separate from persistent entities. The path
  retains no pixels and grants no identity, permission, safety, skill,
  Executive, movement, or execution authority.
- The World Model ROS adapter owns the fixed typed read-only serialization from
  one public immutable snapshot to
  `/ayyo/world_model/get_anonymous_semantic_state`. It preserves exact evidence
  and source provenance, bounds responses to 64 states × 32 items, fails closed
  outside the active lifecycle, and performs no Perception or memory write.
- Evaluated producers additionally require one exact registered manifest,
  verified model artifact, immutable dataset and policy, successful semantic
  report identity, and a sealed one-use authorization. A bare result or
  self-asserted pass reference cannot establish Perception trust.
- World Model owns transport-neutral provenance-bound current robot/environment
  observations, authoritative body-value validation, IMU/pose/covariance/
  availability contracts, compact anonymous semantic evidence, discrete
  freshness, and canonical immutable snapshots without importing Perception,
  ROS, or Gazebo.
- Working Memory owns bounded temporary current/recent evidence, TTL, duplicate
  suppression, temporal ordering, source-dependent semantic expiry, and
  deterministic eviction through public World Model contracts only. It cannot
  import Perception, the candidate bridge, or Memory Validation and cannot
  write Memory OS.
- Memory candidate discovery owns one explicit bounded scan of retained Working
  Memory evidence and deterministic construction of stage-compatible immutable
  `ConsolidationRequest` proposals. Version 1 supports only exact anonymous
  visual person/object episodic observations. It cannot create
  `CandidateEvidence`, invoke staging/selection/validation/apply, persist, infer
  identity/preferences/relationships, retain history, or run in the background.
- Memory candidate staging owns explicit selection of one exact retained
  evidence reference and fail-closed conversion to immutable
  `CandidateEvidence`. It depends downward on public Working Memory/World Model
  evidence contracts and sideways on public Memory/Memory Validation models;
  neither lower package depends back on it. It cannot evaluate policy, apply a
  decision, persist, request correction, infer identity/preferences, scan
  Working Memory, or run in the background.
- Reviewed candidate selection owns explicit bounded review triage over
  unchanged `CandidateEvidence` snapshots. It requires exact staging
  eligibility for direct observations, preserves anonymous evidence and exact
  confidence, defers duplicates/conflicts without choosing a winner, and emits
  deterministic versioned decisions. It cannot generate propositions, read
  Working Memory, authenticate an owner, evaluate/apply validation, persist,
  correct, infer identity/preferences/relationships, or run in the background.
- Controlled memory review orchestration owns the explicit two-phase caller
  checkpoint, plan verification, current-evidence restaging, one-call batch
  selection, selected-only sequential evaluation, immutable full-lineage review
  output, and typed partial ineligibility. It depends on the existing public
  discovery/staging/selection contracts and only a narrow validation evaluator.
  It cannot apply a decision, write Memory OS, correct, promote learning, infer
  identity/preferences/relationships, schedule work, call ROS, or act.
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
- The dedicated development/test
  [Developmental Simulation Scenario Harness](DEVELOPMENTAL_SIMULATION_SCENARIOS.md)
  owns only fixed scenario definitions, orchestration profiles, bounded
  evidence/result reporting, and owned-process validation. It may consume
  public production contracts, but no production layer depends back on it. Its
  production-motion story requires the unchanged Safety `DEFERRED` outcome and
  zero dispatch; only explicitly declared development authority may use the
  existing neck service.
- Teach Mode owns explicit bounded capture sessions, immutable ordered event and
  reference contracts, truthful outcome/clock/provenance semantics, canonical
  serialization, pure verification, and the one-way adapter from an already
  completed Stage-6 report. It cannot launch a scenario, invoke Executive,
  mutate Safety or Skills, dispatch Runtime, command simulation, write Memory
  OS or Working Memory, train or promote a policy, or replay an action.
- Learning Evaluation owns explicit bounded corpus partitioning, inert
  candidate-policy identity, caller-supplied offline trial contracts, and pure
  immutable reports. It cannot capture or execute a demonstration, run a
  candidate, train, promote, roll back, persist, call ROS, or create authority.
- Promotion Control owns caller-supplied promotion/rollback criteria and pure
  evidence eligibility decisions. `ELIGIBLE` and `ROLLBACK_ELIGIBLE` are not
  state transitions or authorization.
- Policy Registry owns exact registration requests, immutable version records,
  explicit parent lineage, bounded canonical snapshots, and exact read-only
  resolution. It cannot choose a latest version, make a policy active, persist,
  load or execute a model, dispatch Runtime, call ROS, or bypass Safety.
- Approval Eligibility owns bounded authority references, exact approval
  requests/evidence, cross-object registry-lineage verification, and pure
  future-activation eligibility decisions. It accepts exactly one concrete
  approval evidence object, never authenticates the referenced authority, and
  cannot activate, install, load, execute, persist, deploy, dispatch Runtime,
  call ROS, control hardware, or bypass Safety.
- Software Showcase owns only the closed Stage-8 public-contract inventory,
  truthful classifications/non-claims, canonical manifest/report, and local
  inspection CLI. It may import reviewed public interfaces, but every lower
  package remains unaware of it. It cannot invoke cognition, decide Safety,
  bind or execute a Skill, dispatch Runtime, call ROS/Gazebo, authenticate,
  activate a policy, persist state, control hardware, or certify physical
  behavior.
- Learning updates remain candidates until evaluation and controlled promotion;
  consolidation does not bypass safety or permissions.
