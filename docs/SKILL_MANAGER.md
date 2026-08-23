# Skill Manager v1

## Status and purpose

Skill Manager v1 is implemented as the standalone Python 3.12
`ayyo-skill-manager` package. It is the final declarative contract boundary
between the Immutable Safety Kernel and a future ROS/runtime bridge.

The package answers which explicitly registered skills exist, which capability
IDs they implement, what bounded inputs and outputs they declare, which future
backend and resources they require, and whether an unchanged Safety-reviewed
proposal step is compatible with that contract. It does not execute a skill.

## Architecture position

```text
Memory OS
    ↓
Memory Validation / Consolidation
    ↓
Personal Context Twin
    ↓
Executive Cognition
    ↓ declarative proposal
Immutable Safety Kernel
    ↓ immutable decision
Skill Manager v1
    ↓ inert, fingerprinted invocation contract only
Future ROS Runtime Bridge
    ↓
Future controllers / simulation / hardware
```

Skill Manager depends only on the public `ayyo_safety` contract and the minimum
public `ayyo_executive` types required to inspect the proposal being bound. It
does not import Memory OS, Memory Validation, Personal Context Twin, SQLite,
ROS, networking, model providers, subprocesses, shells, or backend code.

## Skill definition

`SkillDefinition` is a frozen contract containing:

- a canonical skill ID and Semantic Versioning value;
- a human-readable name and description;
- one or more canonical capability IDs;
- a declarative backend ID;
- bounded input and output schemas;
- required Executive context roles;
- typed shared or exclusive resource requirements;
- required Safety approval classes and an explicit Safety hazard class;
- the expected-result category;
- a deterministic positive timeout in milliseconds;
- concurrency, idempotency, failure, availability, and lifecycle states;
- defensively copied bounded JSON metadata; and
- a canonical SHA-256 skill fingerprint.

Availability is explicit: `UNAVAILABLE`, `AVAILABLE`, `DEGRADED`, or
`DISABLED`. Lifecycle is separately explicit: `EXPERIMENTAL`, `VALIDATED`, or
`DEPRECATED`. Deprecated skills cannot claim available or degraded state.
Only exactly `AVAILABLE` skills may produce an invocation; degraded is not an
implicit fallback. Availability never means authorized, physically safe, or
ready for actuation.

Concurrency declarations are descriptive. `PARALLEL` skills may claim only
shared resources, `RESOURCE_GOVERNED` skills must name at least one resource,
and `EXCLUSIVE` skills must name at least one exclusively held resource. V1
does not acquire locks or schedule work.

Failure semantics are one of `RETRYABLE`, `NON_RETRYABLE`,
`REQUIRES_REPLAN`, `REQUIRES_OPERATOR`, or `EMERGENCY_ABORT`. They describe a
future backend's reported failure contract; Skill Manager does not retry,
replan, contact an operator, or initiate an emergency action.

## Bounded parameter schema

The v1 schema deliberately supports only strings, integers, finite numbers,
booleans, explicit nullability, arrays, and objects. It supports required object
properties, optional rejection of additional properties, scalar allowed values,
numeric bounds, string-length bounds, array-size bounds, and nested schemas.
Booleans are not treated as integers or numbers.

Ingress JSON is limited to 32 levels, 4,096 nodes, 256 items per collection,
1,000,000 aggregate characters, and 1,024-bit integers. Schemas are limited to
16 levels, 512 nodes, and 128 properties per object. Cycles, arbitrary classes,
callables, non-string keys, invalid Unicode, NaN, infinity, oversized integers,
excessive nesting, and excessive collections fail with typed errors. Caller
data is copied before use and copied again on public read.

## Immutable registry

`SkillRegistry` is constructed explicitly from a registry semantic version and
a tuple of skill definitions. There is no mutation, filesystem scan, Python
entry-point discovery, dynamic import, or plugin loading.

Construction canonicalizes skill order and rejects duplicate skill IDs. The
registry supports exact skill resolution, deterministic enumeration,
availability queries, and capability resolution with an optional exact
`AVAILABLE` filter. Resolution results are ordered by skill identity. Its
SHA-256 fingerprint binds the registry version, every skill identity, version,
and complete skill fingerprint; input construction order is not semantic.

`SkillRegistry.selection()` creates a frozen `SkillSelection` that pins the
requested skill ID/version/fingerprint, capability, proposal step ID, registry
version/fingerprint, and its own selection fingerprint. Later registry or
skill changes therefore make the selection stale instead of silently selecting
a replacement.

## Safety binding

`SkillManagerService.bind(proposal, safety_decision, selection)` is a pure
contract operation. It accepts the public Executive proposal because the
Safety decision intentionally does not duplicate plan parameters or context.
It also requires the exact public Safety decision and a registry-pinned
selection.

Binding performs the following checks:

1. Revalidate the decision against the current proposal and Safety policy.
2. Re-evaluate the proposal with the current `SafetyKernel` and require the
   complete decision to match, detecting forged or inconsistent decision data.
3. Require the pinned registry, skill version, skill fingerprint, capability,
   and step selection to remain current.
4. Reject overall `BLOCKED` and `DEFERRED` Safety dispositions without creating
   an invocation.
5. Require the selected Executive step and Safety step to exist and agree on
   capability identity.
6. Require exact skill availability, context-role compatibility,
   expected-result compatibility, parameter compatibility, and Safety hazard
   classification compatibility.
7. Require every skill approval class to be present on the selected step's
   Safety approval evidence. An approval on another plan step cannot be
   laundered into the selected skill.
8. Preserve the complete plan-level Safety approval requirements and every
   relevant source fingerprint in the resulting invocation.

Normal incompatibility produces a frozen `SkillBindingResult` with
`INELIGIBLE`, typed reason codes, and no invocation. A Safety result requiring
external approval may produce an invocation only with
`EXTERNAL_APPROVAL_REQUIRED`; it preserves the unverified requirements and is
not eligible for runtime handoff. There is no approval input, `approved=True`
flag, authorization method, or inferred approval.

## Invocation contract and traceability

`SkillInvocation` is inert immutable data. It carries the pinned selection and
skill contract, backend declaration, copied parameters, expected-result/output
contract, required context evidence references, resources, approvals, Safety
classification, timeout, concurrency/idempotency/failure declarations, and
source Executive, Safety proposal, Safety decision, Safety policy, skill, and
registry fingerprints and versions.

The invocation SHA-256 fingerprint uses canonical JSON and includes the full
chain of relevant source fingerprints. Changing relevant proposal content,
Safety policy or decision, registry version/content, skill definition, selected
step, parameters, context evidence, or approval requirements changes invocation
identity. Timestamps, randomness, object IDs, memory addresses, process hashes,
and dictionary insertion order are excluded.

The model exposes no callable, command, shell string, Python source, ROS action,
publisher, callback, arbitrary executable payload, or backend implementation.
`ELIGIBLE_FOR_RUNTIME_HANDOFF` means only that the declarative binding is
compatible with an unchanged Safety result. It is not execution authority,
authenticated approval, physical-safety certification, or proof that a backend
exists.

## Public API

The principal public flow is:

```python
registry = SkillRegistry(
    version=SemanticVersion("1.0.0"),
    skills=(reviewed_skill_definition,),
)
manager = SkillManagerService(registry, safety_kernel)
selection = registry.selection(
    skill_id="context.inspect.primary",
    capability_id="context.inspect",
    source_step_id="step-1",
)

result = manager.bind(executive_proposal, safety_decision, selection)
```

The package exports its schema, definition, resource, registry, selection,
invocation, binding result, fingerprint, lifecycle, availability, concurrency,
idempotency, failure, and typed error contracts. It exports no executor.

## Deliberate limitations

Skill Manager v1 does not:

- execute skills or call a backend;
- call ROS, publish messages, invoke actions, or control the robot;
- issue motor, navigation, manipulation, simulation, or physical commands;
- perform collision, force, workspace, motion, or contact-safety evaluation;
- authenticate identity, permissions, or approvals;
- dynamically load plugins, scan filesystems, or discover Python entry points;
- schedule work, acquire resource locks, retry failures, or enforce timeouts;
- contain hardware drivers or attest that a declared backend exists;
- call models, LLMs, networks, clouds, subprocesses, shells, or arbitrary code;
  or
- persist registry, selection, binding, or invocation data.

A future runtime bridge must consume an unchanged eligible invocation, recheck
all relevant authority and state at its own boundary, implement resource and
timeout enforcement, and remain constrained by lower physical-safety systems.
It may add restrictions but must not reinterpret this declarative contract as
permission to actuate.
