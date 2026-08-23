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
→ ROS 2 Embodiment Bridge
→ Motion / Control
→ Robot Body
→ Outcome
→ Memory / Learning Update
→ Digital Sleep / Consolidation
```

These are architectural boundaries, not claims of implemented functionality.

The standalone [Memory OS core](MEMORY_OS.md) implements the persistence and
domain boundary for provenance-aware owner memory. The deterministic
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
them. Identity/approval authority, runtime skill implementations,
physical-safety subsystems, and ROS adaptation remain separate future layers.

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

- Perception processing produces evidence that crosses an explicit trust boundary
  before it can affect world or memory state.
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
- The ROS 2 embodiment bridge isolates higher-level contracts from simulation and
  physical hardware details.
- Learning updates remain candidates until evaluation and controlled promotion;
  consolidation does not bypass safety or permissions.
