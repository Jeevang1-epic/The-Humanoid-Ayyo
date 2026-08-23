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
→ Personal Cognitive Twin
→ Executive Cognition
→ Model Gateway
→ Task Planner
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
before explicitly approved mutations reach Memory OS. The Personal Cognitive
Twin, cognition, and ROS adaptation remain separate future layers.

## Invariants

- General foundations may be pretrained.
- Owner-specific autobiographical memory starts empty.
- Perception is evidence, not authority.
- Memory stores provenance and uncertainty.
- The Personal Cognitive Twin models the owner but is not the owner.
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
- Executive cognition and the model gateway can propose only structured actions;
  the task planner and safety kernel constrain what can proceed.
- The immutable safety kernel is independent of cognition and learned policy.
- The ROS 2 embodiment bridge isolates higher-level contracts from simulation and
  physical hardware details.
- Learning updates remain candidates until evaluation and controlled promotion;
  consolidation does not bypass safety or permissions.
