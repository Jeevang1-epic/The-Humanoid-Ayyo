# ROS Runtime Bridge v1

## Status and responsibility

ROS Runtime Bridge v1 is implemented as the standalone Python 3.12
`ayyo-runtime-bridge` package and is installed into the ROS 2 Jazzy workspace by
the `ayyo_runtime_bridge` package. It is the controlled compatibility boundary
between inert Skill Manager output and downstream typed ROS adapters.

The bridge performs five bounded operations:

```text
validate → bind → translate → decide dispatch eligibility → model the result
```

It does not plan, classify safety, select a skill, authenticate approval,
schedule resources, discover ROS endpoints, dynamically load interfaces, or
control a robot. Simulation Control v1 now exists downstream, but its production
translator remains non-dispatchable because Safety v1 defers physical movement.
Its live ROS service is explicitly development-only and does not consume a
Runtime request. The Runtime Bridge itself still has no concrete ROS client,
skill backend, controller, simulation behavior, or physical actuation.

## Architecture and authority

```text
Executive Cognition
    ↓ declarative proposal
Immutable Safety Kernel
    ↓ immutable review decision
Skill Manager
    ↓ binding result and inert invocation
ROS Runtime Bridge v1
    ↓ eligible declarative service request or explicit non-eligible result
Simulation Control typed boundary / future production ROS service adapter
    ↓
ros2_control simulation / future hardware safety layers
```

Safety remains authoritative for safety disposition. Skill Manager remains
authoritative for the skill contract and its binding to the reviewed proposal.
Runtime Bridge is authoritative only for compatibility with its explicit
runtime endpoint allowlist. It may add restrictions but cannot weaken an
upstream result.

The evaluator consumes the complete public `SkillBindingResult`, not a loose
capability string or caller-assembled command. This preserves the upstream
outcomes:

- Safety `BLOCKED` maps to runtime `BLOCKED`;
- Safety `DEFERRED` maps to runtime `DEFERRED`;
- stale upstream binding maps to runtime `STALE`;
- unavailable skill maps to runtime `UNAVAILABLE`; and
- `EXTERNAL_APPROVAL_REQUIRED` maps to `APPROVAL_REQUIRED` without creating a
  runtime request.

Only a valid `ELIGIBLE_FOR_RUNTIME_HANDOFF` invocation can produce an eligible
runtime request. Eligibility is compatibility evidence, not authorization,
transport acceptance, task completion, or physical-safety certification.

## Dependency direction

The standalone package has one direct runtime dependency:
`ayyo-skill-manager==0.1.0`. Runtime source imports only the public
`ayyo_skill_manager` package. It does not directly import Executive Cognition,
Safety Kernel, Personal Context Twin, Memory OS, persistence, `rclpy`, network,
model-provider, filesystem-execution, shell, or subprocess modules.

ROS-specific installation is isolated in
`ros2_ws/src/ayyo_runtime_bridge`. The ROS package installs the same
single-owned Python core into the colcon overlay with `ament_cmake_python`; it
does not duplicate the source tree. Business logic and unit tests require no
live ROS graph.

The colcon wrapper predates ROS packages for the standalone Skill Manager and
its upstream Python distributions. It therefore installs only the
Runtime-Bridge-owned source: importing `ayyo_runtime_bridge` from a bare colcon
overlay requires the standalone dependency chain to be installed or present on
`PYTHONPATH`. This packaging limitation does not change eligibility semantics
and is not silently replaced with a mock. The development ROS adapter imports
only the simulation-control top-level core, so it does not rely on that optional
upstream import path.

## ROS endpoint contract

V1 supports exactly one endpoint kind: `SERVICE_REQUEST`. Topic publication and
action goals are absent because the repository has no concrete skill runtime
that justifies them.

`RosServiceEndpoint` is frozen and contains:

- a canonical endpoint ID and backend ID;
- ROS package and service-interface names;
- a bounded absolute namespace and service name;
- exact non-null object request and response schemas;
- a positive bounded timeout; and
- explicit `AVAILABLE`, `UNAVAILABLE`, or `DISABLED` state.

The model computes a canonical SHA-256 endpoint fingerprint. It accepts no
source code, executable path, shell command, Python callable, dynamic import,
publisher, action goal, or arbitrary ROS handle. Service endpoints do not carry
QoS or lifecycle fields because v1 has no behavior for which those declarations
would be meaningful.

Simulation Control v1 adds `SetDevelopmentJointPosition.srv` for its concrete,
statically implemented test owner. That interface is not a Runtime Bridge
endpoint and cannot carry a `RuntimeRequest`. No production Runtime Bridge
`msg`, `srv`, or `action` is implemented.

## Runtime allowlist

`RuntimeEndpointBinding` pins one complete `SkillDefinition`, skill semantic
version and fingerprint, capability ID, backend ID, and `RosServiceEndpoint`.
Construction requires exact backend, input-schema, and output-schema agreement.
The endpoint timeout may be equal to or more restrictive than the Skill
timeout. Only an exactly `AVAILABLE` skill can be registered.

`RuntimeEndpointRegistry` is a closed immutable allowlist with a semantic
version and canonical fingerprint. It has no mutation, discovery, filesystem
scan, entry point, dynamic import, or ROS graph lookup. Ambiguous
skill/version/capability/backend mappings, duplicate endpoint IDs, and duplicate
ROS endpoint identities are rejected.

## Runtime request and translation

`RuntimeRequest` exists only after the Skill invocation and endpoint allowlist
have passed integrity reconstruction. It retains the complete immutable
`SkillInvocation` and endpoint binding, plus the runtime registry version and
fingerprint. Through the invocation it retains:

- Executive request and decision identities;
- Safety decision, reviewed proposal, policy version, and policy identities;
- Skill registry version and identity;
- skill ID, version, definition identity, capability, selected step, backend,
  and invocation identity;
- exact parameters and required context evidence;
- retained approval requirements;
- resource, concurrency, timeout, idempotency, failure, and lifecycle metadata;
  and
- input and expected output contracts.

Translation is deliberately structural: the final service request fields are
an exact defensive copy of the Skill Manager-validated parameter object. V1
does not rename fields, coerce values, or infer missing data. The endpoint
request schema must exactly equal the Skill input schema, and the endpoint
response schema must exactly equal the Skill output schema.

The runtime-request SHA-256 fingerprint binds the complete relevant upstream
identity chain, final request fields, context, approvals, resources, endpoint
binding, and runtime registry. Caller-supplied derived IDs are recomputed.

## Eligibility

`RuntimeBridge.evaluate(binding_result)` is pure and performs no transport or
ROS side effect. It returns a frozen `RuntimeDecision` with one of:

- `ELIGIBLE` — one current request exists and no runtime blocker remains;
- `APPROVAL_REQUIRED` — upstream approval remains unverified;
- `DEFERRED` — upstream Safety deferral is retained;
- `BLOCKED` — upstream Safety blocking is retained;
- `REJECTED` — no exact allowlisted runtime interpretation exists;
- `UNAVAILABLE` — the selected skill or endpoint is unavailable; or
- `STALE` — a relevant upstream or runtime identity changed.

Only `ELIGIBLE` carries a `RuntimeRequest`. Every other outcome has typed,
canonically ordered reasons and no request.

## Staleness and dispatch-time revalidation

All public Skill, selection, invocation, schema, endpoint, binding, semantic
version, registry, request, decision, and receipt data used at a trust boundary
is reconstructed through its public constructor. Changed parameters, context,
Executive/Safety/policy identity, Skill definition/version, selected step,
backend, endpoint, or registry therefore fails integrity or changes a
fingerprint.

`RuntimeBridge.revalidate(prior_decision, current_binding)` returns the same
decision only when it is exactly current; otherwise it returns a non-dispatchable
`STALE` decision. `assert_current()` raises `StaleRuntimeDecisionError` instead.

`RuntimeDispatcher.dispatch()` requires the prior eligible decision and a
current `SkillBindingResult`. Immediately before the adapter boundary it:

1. reconstructs and compares the final runtime request, including the defensive
   parameter copy;
2. evaluates the current upstream binding against the current runtime registry;
3. requires the new decision to equal the prior decision;
4. checks the explicitly supplied transport's availability; and
5. verifies that any receipt matches the exact runtime request and transport.

This closes detectable substitution between evaluation and transport. The
bridge has no independent oracle for Executive, Safety, Skill Registry, ROS
graph, hardware, or environment state. The integrating runtime must supply a
fresh Skill Manager result and the currently deployed runtime registry at
dispatch. Reusing the same old upstream object as both prior and “current”
cannot prove that external authoritative state is unchanged.

## Transport and result boundary

`RuntimeTransport` is a narrow protocol for an explicitly configured adapter.
The production package provides only `UnavailableRosServiceTransport`, which
reports unavailable and never falls back to an in-memory implementation. The
deterministic fake transport exists only in tests.

`RuntimeDispatchResult` distinguishes:

- `NOT_ELIGIBLE`;
- `NOT_DISPATCHED`;
- `TRANSPORT_UNAVAILABLE`;
- `REJECTED_BEFORE_DISPATCH`;
- `TRANSPORT_REJECTED`;
- `ACCEPTED_BY_TRANSPORT`; and
- `TRANSPORT_FAILURE`.

Expected transport failures become typed results. Unknown programming defects
remain visible because runtime source contains no broad exception catch.
`TransportReceipt.ACCEPTED` means only that the adapter accepted the immutable
request. It does not mean that a task ran, an outcome occurred, or physical
motion completed.

## Resource and concurrency boundary

Runtime requests retain Skill Manager resource requirements and concurrency
policy. Runtime Bridge v1 does not acquire locks, schedule work, arbitrate
resources, retry, enforce the declared timeout, or implement lifecycle
management. Contradictory declarations are rejected while reconstructing the
Skill contract. A later trusted runtime scheduler must enforce these constraints
without weakening them.

## Public API

The principal flow is:

```python
endpoint_binding = RuntimeEndpointBinding(
    skill_definition=reviewed_skill,
    capability_id="context.inspect",
    endpoint=reviewed_service_endpoint,
)
runtime_registry = RuntimeEndpointRegistry(
    version=SemanticVersion("1.0.0"),
    bindings=(endpoint_binding,),
)

bridge = RuntimeBridge(runtime_registry)
decision = bridge.evaluate(skill_binding_result)

dispatcher = RuntimeDispatcher(bridge)
result = dispatcher.dispatch(
    decision,
    current_skill_binding_result,
    explicitly_configured_transport,
)
```

The package exports the endpoint, endpoint binding/registry, request,
fingerprint, eligibility decision/reason, transport protocol/receipt, dispatch
result/failure, unavailable ROS transport, and typed error contracts. It
exports no planner, approval authority, dynamic endpoint loader, shell command,
or physical-control API.

## Deliberate limitations and next step

V1 does not authenticate approvals or identities; attest backend or ROS graph
state; implement a concrete production `rclpy` client; generate or dynamically
load ROS types; implement topic/action transports; enforce timeouts; schedule
resources; persist audit records; retry failures; interpret service responses;
certify motion/contact safety; or itself control simulation or hardware.

The downstream Simulation Control package proves exact endpoint translation,
URDF limits, controller lifecycle, and state feedback for one separately
authorized development command. Its future production identity is pinned to
`/ayyo/simulation_control/apply_runtime_joint_position`, but no such service is
implemented because physical movement is `DEFERRED`. A production integration
must add authenticated authorization, a current runtime scheduler/transport,
dedicated motion/collision/force/workspace safety, and emergency-stop layers
before implementing and registering that exact typed endpoint. See
[SIMULATION_CONTROL.md](SIMULATION_CONTROL.md).
