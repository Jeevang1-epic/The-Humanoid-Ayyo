# Architecture

## System flow

```text
Human / Environment
→ Physical Perception
→ Perception Processing
→ Perception Trust Boundary
→ World Model
→ Working Memory
→ Memory OS
→ Memory Validation / Consolidation
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
- Memory validation owns provenance, uncertainty, contradiction handling, and
  consolidation boundaries.
- Executive cognition and the model gateway can propose only structured actions;
  the task planner and safety kernel constrain what can proceed.
- The immutable safety kernel is independent of cognition and learned policy.
- The ROS 2 embodiment bridge isolates higher-level contracts from simulation and
  physical hardware details.
- Learning updates remain candidates until evaluation and controlled promotion;
  consolidation does not bypass safety or permissions.
