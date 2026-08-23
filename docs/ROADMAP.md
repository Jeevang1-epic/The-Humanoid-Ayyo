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
eligibility, and an unavailable-by-default transport boundary. Authenticated identity,
permissions, approval verification, live backend attestation, a concrete typed
ROS service client, audit persistence, timeout/resource enforcement, runtime
skill implementations, simulation behavior, and physical-safety integration
remain future work. Executive proposals, Safety eligibility, Skill Manager
runtime-handoff eligibility, Runtime Bridge eligibility, and transport
acceptance do not count as authorization, task completion, execution, or
physical-safety certification.
