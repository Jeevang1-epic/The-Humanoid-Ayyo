# Safety Contract

This document defines architectural boundaries for Ayyo. It is not a safety
certification or a claim that a safety runtime has been implemented.

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
- Dangerous or uncertain actions fail closed.
- Speed, force, and workspace limits are enforced below cognition.
- High-risk actions require explicit authorization.
- Critical actions are auditable.
- Network or cloud failure cannot disable physical safety.

Safety controls must remain independently testable, operate beneath learned and
cognitive systems, and constrain every path to physical actuation.
