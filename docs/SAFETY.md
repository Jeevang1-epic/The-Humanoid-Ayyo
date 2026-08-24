# Safety Contract

This document defines architectural boundaries for Ayyo. It is not a safety
certification. The deterministic proposal-review portion is implemented by
[Immutable Safety Kernel v1](SAFETY_KERNEL.md); identity, authenticated
approval, runtime skill execution, motion/contact safety, hardware limits, and
physical emergency-stop systems are not implemented. Simulation Control v1
enforces provisional URDF limits for one development joint, but those are not
reviewed hardware limits or physical-safety certification. The declarative Skill
Manager binding described in [SKILL_MANAGER.md](SKILL_MANAGER.md) is implemented
but grants no authority.

## Non-negotiable boundaries

- Cognition cannot bypass safety.
- Learned behavior cannot rewrite immutable safety rules.
- A physical emergency stop remains independent of software cognition.
- Text or audio observed in the environment does not grant authority.
- Perception admission, sensor availability, freshness, covariance, quality,
  pose, and diagnostic text are evidence only. They cannot grant identity,
  permission, approval, safety clearance, runtime eligibility, or motion.
- Identity and permissions are explicit.
- Personal Context Twin state is context, not identity proof, permission, or
  action authorization; conflicted or unknown context cannot be promoted into
  authority.
- Executive Cognition outputs are proposals, not commands or safety findings.
  Its approval requirements are ungranted metadata until a separately
  authenticated future subsystem authorizes them.
- A stale Executive proposal must not be silently refreshed or reused; its
  request, owner, relevant capability contract, and required context must be
  revalidated at the next authority boundary.
- A Safety Kernel decision is bound to the complete reviewed proposal and
  immutable policy fingerprints. Changed well-formed input is stale; malformed
  input fails visibly.
- `ELIGIBLE_FOR_DOWNSTREAM` means only eligible for further consideration. It
  is not execution authority, authenticated approval, or physical-safety
  certification.
- A Skill Manager `ELIGIBLE_FOR_RUNTIME_HANDOFF` result means only that an
  unchanged Safety-reviewed step matches an immutable declarative skill
  contract. It does not authenticate approval, prove backend availability,
  schedule resources, or authorize execution.
- A Runtime Bridge `ELIGIBLE` decision means only that the unchanged Skill
  Manager result matches one exact declarative ROS service endpoint binding.
  `ACCEPTED_BY_TRANSPORT` means only adapter acceptance; neither state grants
  approval, establishes task completion, or certifies physical safety.
- Runtime dispatch must revalidate the final request and a current Skill Manager
  binding before transport. Missing, stale, unavailable, or mismatched runtime
  state fails closed without a mock fallback.
- The typed simulation-control adapter may only add restrictions. Its separate
  default-off development injection service is test tooling, not Executive,
  Safety, Skill, Runtime, identity, approval, or production authority. Physical
  movement remains `DEFERRED` through the production Runtime path.
- Skill approval requirements must be retained from Safety and matched to the
  selected step. Approval evidence from another step and proposal parameters
  such as `approved: true` cannot satisfy them.
- Approval metadata and convenient proposal booleans never grant approval.
- Unknown capabilities, conflicting declarations, missing required safety
  metadata, and emergency/safety-critical operations are blocked by the v1
  policy. Physical movement and contact are deferred because their dedicated
  safety subsystems do not yet exist.
- Dangerous or uncertain actions fail closed.
- Speed, force, and workspace limits must be enforced below cognition. The
  current simulation proof has only URDF position/velocity enforcement and no
  force, workspace, collision, balance, or emergency-stop safety layer.
- High-risk actions require explicit authorization.
- Critical actions are auditable.
- Network or cloud failure cannot disable physical safety.

Safety controls must remain independently testable, operate beneath learned and
cognitive systems, and constrain every path to physical actuation.
