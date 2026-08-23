# Executive Cognition v1

## Status

Executive Cognition v1 is implemented as the standalone Python 3.12
`ayyo-executive` package. It consumes an owner-bound Personal Context Twin
(PCT) service and an explicit capability registry, then returns deterministic,
immutable proposal data.

It is not a natural-language system, model runtime, Safety Kernel, Skill
Manager, ROS bridge, or execution engine. It cannot actuate the robot.

## Responsibility and architecture position

```text
Memory Validation / Consolidation
        ↓
Memory OS
        ↓
Personal Context Twin
        ↓
Executive Cognition v1
        ↓ proposals only
Immutable Safety Kernel v1
        ↓ review decisions only
Future identity / approval authority and Skill Manager
        ↓
Future task / skill execution and ROS bridge
```

Executive Cognition owns structured-request validation, explicit context
dependency assessment, deterministic declarative planning, decision reasons,
and stale-decision checks. Memory OS remains the durable source of truth;
Memory Validation owns evidence admission and correction policy; PCT owns the
read-oriented owner projection and conflict state.

The Executive does not mutate any lower layer, infer new personal facts, resolve
conflicts, grant approval, determine physical safety, or execute plan steps.

## Structured request model

`ExecutiveRequest` is an immutable structured input containing:

- an externally supplied request ID, objective, and typed request category;
- one to 64 typed `CapabilityInvocation` records;
- invocation parameters and dependency step IDs;
- required and optional PCT context keys;
- constraints, approval requirements, and explicit assumptions;
- a missing-context policy (`REQUEST_INFORMATION` or `DEFER`); and
- JSON-compatible metadata.

Natural-language interpretation is deliberately absent. Nested JSON-compatible
input is validated iteratively, copied on ingress, and copied again on public
read. Cycles, non-string object keys, non-finite numbers, invalid Unicode,
oversized integers, and non-JSON objects are rejected. Depth, node count, text,
collection size, and aggregate context limits prevent unbounded request shapes.

## Capability contract

`CapabilityRegistry` is an immutable caller-supplied registry. It has no built-in
capabilities. A lookup is one of:

- `UNKNOWN`: no definition exists;
- `UNAVAILABLE`: a definition exists but is explicitly unavailable; or
- `AVAILABLE_FOR_PROPOSAL`: the integrating caller declares that a proposal may
  be formed.

`AVAILABLE_FOR_PROPOSAL` is not authorization, proof of runtime readiness, or a
safety result. There is no Skill Manager integration in v1, so the package
cannot independently attest that an implementation exists.

A `CapabilityDefinition` records the canonical ID, description, typed parameter
contract, required context, approvals, assumptions, preconditions, constraints,
expected-result category, failure policy, and declared availability. Extra,
missing, or type-incompatible parameters fail with a typed error. Booleans are
not accepted as integers or numbers.

Unknown capabilities produce `REJECT`; unavailable capabilities produce
`DEFER`. Neither produces a plan. The package ships no fake robot operations.

## Context consumption

`ExecutiveService` accepts the public `PersonalContextService`, which already
binds reads to one exact owner. Each evaluation builds one PCT snapshot and
queries that immutable snapshot through its public API. Executive runtime code
does not import Memory OS, SQLite, or persistence implementations.

For context used by the request or capability contract:

- required `RESOLVED` context may be referenced by a plan;
- required `UNKNOWN` context is never guessed and causes
  `REQUEST_INFORMATION` or `DEFER` according to the request policy;
- required `CONFLICTED` context causes `DEFER`; competing values and conflict
  evidence remain explicit and no winner is selected; and
- optional context may remain unknown and does not affect the plan in v1. If a
  capability truly depends on an optional key, its contract must declare that
  key as required.

Context references retain the state, SHA-256 value digests, evidence memory IDs,
and unresolved conflict IDs. The exact whole-owner PCT snapshot version is also
stored on every decision. PCT remains responsible for excluding other owners,
historical superseded records, and retracted records.

## Decision model

`ExecutiveDecision` supports exactly five outcomes:

- `PROPOSE`
- `REQUEST_INFORMATION`
- `REQUEST_APPROVAL`
- `DEFER`
- `REJECT`

There is no `EXECUTE` or `SAFE` result. Every decision records a deterministic
decision ID, request ID, owner subject, type, ordered reason codes, explanation,
exact PCT snapshot version, source fingerprints, context references,
missing/conflicted context, assumptions, required capabilities, approval
requirements, constraints, and an optional plan.

Construction rejects impossible combinations. For example, `PROPOSE` requires a
valid plan and resolved required context; `REQUEST_INFORMATION` cannot carry a
plan; `REQUEST_APPROVAL` requires both a plan and approval metadata; and
`DEFER`/`REJECT` cannot contain a plan.

## Declarative plan model

A `Plan` is only an ordered tuple of immutable `PlanStep` data. Each step records
its capability, copied JSON parameters, dependencies, preconditions, required
context, approvals, constraints, expected-result category, and failure policy.

Step IDs are unique. Dependencies must exist, cannot reference the same step,
and cannot form cycles. Kahn topological ordering with lexical step-ID
tie-breaking gives deterministic order. Parameters are checked against the
capability definition before planning. Callables, commands, publishers, and
other executable payloads are not JSON-compatible and are rejected.

## Approval and safety boundaries

Approval requirements are immutable metadata. Executive Cognition does not
attach an `approved` value, equate requester and approver, authenticate either
party, or grant authority. A separately authenticated future subsystem must
provide authorization.

Plans expose the inputs consumed by the Safety Kernel—operations,
parameters, context dependencies, constraints, approvals, assumptions,
preconditions, ordering, expected-result categories, and failure policy. The
Executive does not perform hazard scoring, collision checking, motor limiting,
emergency-stop handling, or any other physical-safety function.

## Determinism and fingerprints

All logical fingerprints use canonical JSON and SHA-256. Canonical ordering is
applied to mappings, unordered input collections, capability definitions,
context dependencies, reason codes, and plan steps. Logical identities use no
wall-clock time, randomness, process hashes, or generated UUIDs.

The versioned fingerprints are:

- request fingerprint: every normalized request field;
- capability-contract fingerprint: only capabilities requested by the prior
  decision, including an explicit marker for unknown capabilities;
- relevant-context fingerprint: only required context references, including
  state, canonical-value digests, evidence IDs, and conflict IDs; and
- decision fingerprint: the normalized decision and plan plus the three logical
  source fingerprints.

The decision fingerprint deliberately excludes the whole-owner PCT version and
optional context. Therefore unrelated owner data can change the PCT snapshot
without changing logical decision identity. A change to evidence IDs for a
required value is treated conservatively as a relevant-context change even if
the canonical value remains the same.

## Explicit stale-decision semantics

`ExecutiveService.revalidate(decision, request)` takes a new PCT snapshot but
does not modify, refresh, approve, or replace the prior decision. It returns
`CURRENT` only when all of the following still match:

- the complete request fingerprint;
- the owner subject;
- the relevant capability-contract fingerprint; and
- the relevant required-context fingerprint.

Otherwise it returns `STALE` with ordered reasons for request, owner, capability
contract, and/or relevant-context changes. Both prior and current fingerprints,
owner subjects, and whole PCT snapshot versions remain visible in the result.
Unrelated capability definitions, unrelated PCT entries, and optional-context
changes do not invalidate a proposal.

Revalidation proves equality only at the moments the two snapshots were built.
It does not lock Memory OS or authorize later reuse. Safety Kernel v1 binds its
review to the complete proposal and policy fingerprints; a future authenticated
approval or execution transaction must re-check the binding at its own
boundary.

## Public API

The package exports the service, request/decision/plan/context models,
capability models and registry, enums, fingerprints, limits, and typed errors
from `ayyo_executive`.

The main flow is intentionally small:

```python
registry = CapabilityRegistry((explicit_capability_definition,))
executive = ExecutiveService(personal_context_service, registry)

decision = executive.evaluate(structured_request)
validation = executive.revalidate(decision, structured_request)
```

The PCT service determines the owner; callers do not supply an unverified owner
ID to individual evaluations.

## Failure behavior

Malformed requests and capability contracts raise typed validation errors.
Invalid parameter sets raise `InvalidCapabilityParametersError`. Invalid plan or
decision combinations raise `PlanInvariantError` or
`DecisionInvariantError`. Unknown and explicitly unavailable capabilities are
normal typed decision outcomes, not fabricated fallbacks.

The service does not broadly catch exceptions. Public lower-layer failures,
including a closed Memory OS store beneath PCT, propagate with their existing
typed error. Unexpected dependency and programming failures remain visible.

## Dependency boundary

The sole direct runtime dependency is `ayyo-personal-context==0.1.0` through its
public package API. Executive runtime sources contain no Memory OS, persistence,
SQLite, ROS, network client, model, embedding, subprocess, or cloud dependency.

## Deliberate limitations and future integration

Implemented v1 is limited to deterministic structured requests and explicitly
registered contracts. It has no natural-language understanding, probabilistic
reasoning, model/LLM integration, live capability discovery, identity proof,
authorization, persistence, network access, perception, learning, physical
safety, execution, ROS behavior, navigation, manipulation, or motion control.

Safety Kernel v1 now consumes the unchanged Executive proposal and independently
revalidates its graph and cross-field relationships. Future work may translate
authenticated user intent into the structured request, attest capability
availability through a Skill Manager, and attach trusted authorization outside
both Executive and Safety packages. Those layers must not weaken the fail-closed
behavior described here.
