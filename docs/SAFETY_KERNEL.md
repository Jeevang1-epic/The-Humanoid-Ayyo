# Immutable Safety Kernel v1

## Status and purpose

Immutable Safety Kernel v1 is implemented as the standalone Python 3.12
`ayyo-safety` package. It is the deterministic, fail-closed review boundary
between declarative Executive Cognition proposals and any future authority or
execution subsystem.

The kernel classifies a proposal as one of:

- `ELIGIBLE_FOR_DOWNSTREAM`;
- `EXTERNAL_APPROVAL_REQUIRED`;
- `DEFERRED`; or
- `BLOCKED`.

`ELIGIBLE_FOR_DOWNSTREAM` means only that this policy found no current blocker
to further consideration. It does not mean executed, human-authorized,
collision-free, motion-safe, hardware-safe, or physically safe. The API has no
`EXECUTE` disposition and no `safe` or `allowed` boolean.

## Architecture position and trust boundary

```text
Memory OS
    ↓
Memory Validation / Consolidation
    ↓
Personal Context Twin
    ↓
Executive Cognition
    ↓ declarative proposal
Immutable Safety Kernel v1
    ↓ immutable decision only
Future identity / approval authority and Skill Manager
    ↓
Future ROS 2 bridge and physical controls
```

The kernel consumes only the public `ayyo_executive` contract. It does not read
Memory OS or Personal Context Twin directly. It has no persistence, ROS,
network, model, subprocess, shell, or filesystem-execution dependency.

Executive Cognition owns planning and context dependency declaration. The
Safety Kernel independently checks the plan structure and applies immutable
hazard policy. A future trusted approval authority must authenticate approvals.
A future Skill Manager must map an unchanged eligible proposal to an
implementation. Lower physical-control layers must enforce motion, collision,
force, workspace, and emergency-stop protections.

## Non-goals

Safety Kernel v1 is not an executor, planner replacement, Skill Manager, ROS
node, approval interface, identity provider, motion planner, collision detector,
perception system, motor controller, or hardware emergency stop. It does not
provide probabilistic risk scores or claim that model confidence establishes
safety.

## Immutable policy

`SafetyPolicy` is fixed at construction time. It contains a sorted tuple of
explicit `CapabilitySafetyRule` records and the complete built-in v1 hazard-rule
table. Its lookup indexes are read-only mappings. There are no rule mutation,
rule registration, or dynamic policy update methods.

The policy version is `ayyo.safety.policy.v1`. A canonical SHA-256 policy
fingerprint binds the version, every hazard rule, every prerequisite and
approval class, and every capability classification. Input rule order is not
semantic.

The v1 hazard behavior is:

| Hazard class | Minimum disposition | Additional result |
| --- | --- | --- |
| Informational/read-only | Eligible downstream | Expected result must be informational |
| Internal non-actuating | Eligible downstream | Expected result may be informational or a proposed internal state change |
| External digital effect | External approval required | Policy approval class is retained |
| Physical movement | Deferred | Motion-safety evaluation remains unresolved |
| Physical contact | Deferred | Contact-safety evaluation remains unresolved |
| Privileged/high-impact | External approval required | Privileged approval class is retained |
| Emergency/safety-critical | Blocked | No software fallback is fabricated |
| Unknown/unclassified | Blocked | No implicit default classification exists |

`CapabilitySafetyRule` can additionally require named Executive preconditions
and constraints. Their absence blocks the step as missing safety metadata. A
declared hazard class that conflicts with a step's expected-result category also
blocks the step.

Capability classification is explicit trusted deployment configuration in v1.
The package ships no built-in capability classifications and cannot discover or
attest implementations. Integrators must construct a policy from reviewed
configuration before evaluating proposals. An omitted capability is
unclassified and blocked.

## Plan and proposal validation

`SafetyKernel.evaluate()` accepts only an `ExecutiveDecision` containing a
`PROPOSE` or `REQUEST_APPROVAL` plan. The Safety-owned proposal boundary
independently verifies:

- one to 64 typed plan steps;
- bounded normalized identifiers and typed Executive fields;
- unique step IDs, existing dependencies, no self-dependency, and no cycles;
- deterministic lexical topological ordering;
- exact agreement between plan and decision capabilities;
- exact agreement between step and decision approval requirements;
- exact agreement between step and decision constraints;
- exact agreement between plan context dependencies and required context
  references;
- resolved required context for an executable proposal;
- no conflicting required/optional roles for one context identity;
- decision type, reason, approval, fingerprint, and ID shape;
- content agreement with a rebuilt public Executive decision fingerprint;
- typed preconditions, context requirements, approvals, constraints, expected
  results, and failure policies; and
- bounded JSON-compatible step and constraint parameters.

Malformed or inconsistent proposal structures raise typed errors. They never
become ordinary eligible outcomes. Independent steps are normalized by lexical
step ID, and restriction aggregation follows:

```text
eligible downstream < approval required < deferred < blocked
```

No later rule may weaken a hazard class or a prior step's restriction. One
blocked step blocks the plan. One deferred step prevents approval-only or
eligible plan status. One approval-gated step prevents unconditional
eligibility.

Executive assumptions have no verified truth source in this milestone. Their
presence therefore creates explicit unresolved assumption prerequisites and
defers the plan. Because Executive assumptions are plan-wide rather than
step-scoped, their decision records are anchored to the first canonical plan
step.

## Approval boundary

Executive approval requirements are copied into `SafetyDecision` as unverified
external requirements. Policy-mandated external and privileged approval classes
are added independently. There is no approval-evidence input and no method that
grants, verifies, consumes, or bypasses an approval.

Parameters such as `approved: true`, `authorized: true`, or `is_safe: true` are
ordinary proposal data. They never affect the approval or physical-safety
disposition. Requester identity and Personal Context Twin state are not treated
as authorization.

## Decision model

`SafetyDecision` and `SafetyStepDecision` are frozen, strongly typed records.
They expose:

- overall and per-step disposition;
- ordered `SafetyReason` values;
- affected step and capability IDs;
- hazard class and triggering policy-rule IDs;
- external approval class, source, requirement ID, description, and affected
  step;
- unresolved prerequisite kind, ID, description, and affected step;
- source Executive decision, request, owner, and decision fingerprint;
- policy version and policy fingerprint;
- Safety-owned proposal fingerprint; and
- deterministic decision ID and decision fingerprint.

Constructors reject impossible combinations, including an unclassified
eligible step, a disposition weaker than its hazard-class minimum, an eligible
step with unresolved blockers, or an approval/deferred/blocked result without
the corresponding typed evidence.

## Determinism, defensive data, and fingerprints

The Safety Kernel copies public Executive parameter mappings before review. It
uses a package-owned, bounded, iterative canonical JSON implementation because
Executive Cognition does not export its canonicalization utility. No private
Executive module is imported.

Ingress canonical data handling rejects cycles, unsupported objects, non-string
object keys, non-finite numbers, invalid Unicode, oversized integers, structures
deeper than 256 levels, more than 10,000 JSON nodes, or more than 4,000,000
aggregate characters. Strings, booleans, integers, and floats remain
type-distinct; Unicode normalization is not silently changed. Internally
generated policy and decision fingerprint documents use separate bounds of
250,000 nodes and 32,000,000 characters so that maximum valid Executive plans
and explicit blocker evidence remain representable without relaxing ingress
limits.

The Safety-owned proposal fingerprint binds the actual reviewed content,
including source IDs and fingerprints, context snapshot version and references,
source explanation and reasons, assumptions, full plan structure, capability
IDs, canonical parameters, dependencies, preconditions, context requirements,
approval requirements, constraints, expected results, and failure policies. It
does not rely on object identity, process hashing, time, or randomness. Initial
evaluation also rebuilds the decision through the public Executive constructor
and rejects content that no longer matches the declared Executive decision or
relevant-context fingerprints.

`SafetyKernel.revalidate(prior_decision, current_proposal)` rebuilds the proposal
snapshot and compares both proposal and current policy fingerprints. A
well-formed changed proposal returns `STALE` with `PROPOSAL_CHANGED`; policy
evolution returns `POLICY_CHANGED`. `assert_current()` raises
`StaleSafetyDecisionError` for a stale result. Revalidation never refreshes,
approves, or replaces a decision. A change that makes the proposal structurally
invalid raises a typed validation error instead, which also prevents reuse.

## Public API

The principal API is exported from `ayyo_safety`:

```python
from ayyo_safety import (
    CapabilitySafetyRule,
    HazardClass,
    SafetyKernel,
    SafetyPolicy,
)

policy = SafetyPolicy(
    capability_rules=(
        CapabilitySafetyRule(
            capability_id="context.inspect",
            hazard_class=HazardClass.INFORMATIONAL_READ_ONLY,
        ),
    )
)
kernel = SafetyKernel(policy)

decision = kernel.evaluate(executive_decision)
revalidation = kernel.revalidate(decision, current_executive_decision)
```

The package also exports the disposition, hazard, reason, approval,
prerequisite, fingerprint, and revalidation enums/models plus typed domain
errors. It intentionally exports no execution or actuation service.

## Failure behavior

Malformed policies raise `InvalidSafetyPolicyError`. Malformed Executive
proposal fields raise `InvalidSafetyProposalError`. Graph violations raise
`SafetyPlanInvariantError`. Impossible Safety decision models raise
`SafetyDecisionInvariantError`. Explicit stale assertion raises
`StaleSafetyDecisionError`.

Known malformed lower-contract access is converted to a typed proposal error.
The runtime contains no broad `Exception` or `BaseException` catch, so unexpected
programming defects remain visible. There is no service lifecycle or resource to
silently reopen.

## Package boundary and verification

`ayyo-safety==0.1.0` has one direct runtime dependency:
`ayyo-executive==0.1.0`. Runtime source imports only the public
`ayyo_executive` package. Structural tests prohibit direct lower-layer,
persistence, ROS, networking, model-provider, process, shell, and filesystem
execution dependencies. Wheel tests verify that only `ayyo_safety` runtime code
is packaged.

## Deliberate limitations and future integration

V1 has no authenticated identity, permission store, trusted approval evidence,
policy/decision signature or attestation mechanism, audit persistence, live
capability discovery, perception, robot-state input, environment-state input,
collision model, motion/contact safety evaluator, emergency-stop hardware,
Skill Manager, execution, ROS bridge, simulation behavior, or physical
actuation.

Consequently, physical movement and contact cannot become eligible in v1, and
an approval requirement cannot become satisfied inside this package. Emergency
behavior is blocked rather than fabricated. Future identity, approval, Skill
Manager, ROS, and physical-control integrations must consume the unchanged
proposal and decision bindings, revalidate at their own authority boundary, and
may only add restrictions. They must not reinterpret `ELIGIBLE_FOR_DOWNSTREAM`
as permission or a physical-safety guarantee.
