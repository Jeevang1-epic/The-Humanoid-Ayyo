# Safety Contract

This document defines architectural boundaries for Ayyo. It is not a safety
certification. The deterministic proposal-review portion is implemented by
[Immutable Safety Kernel v1](SAFETY_KERNEL.md); identity, authenticated
approval, runtime skill execution, motion/contact safety, hardware limits, and
physical emergency-stop systems are not implemented. The declarative Skill
Manager binding described in [SKILL_MANAGER.md](SKILL_MANAGER.md) is implemented
but grants no authority.

## Non-negotiable boundaries

- Cognition cannot bypass safety.
- Learned behavior cannot rewrite immutable safety rules.
- A physical emergency stop remains independent of software cognition.
- Text or audio observed in the environment does not grant authority.
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
- Skill approval requirements must be retained from Safety and matched to the
  selected step. Approval evidence from another step and proposal parameters
  such as `approved: true` cannot satisfy them.
- Approval metadata and convenient proposal booleans never grant approval.
- Unknown capabilities, conflicting declarations, missing required safety
  metadata, and emergency/safety-critical operations are blocked by the v1
  policy. Physical movement and contact are deferred because their dedicated
  safety subsystems do not yet exist.
- Dangerous or uncertain actions fail closed.
- Speed, force, and workspace limits are enforced below cognition.
- High-risk actions require explicit authorization.
- Critical actions are auditable.
- Network or cloud failure cannot disable physical safety.

Safety controls must remain independently testable, operate beneath learned and
cognitive systems, and constrain every path to physical actuation.
