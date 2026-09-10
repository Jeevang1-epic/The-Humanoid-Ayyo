# Candidate Policy Registry and Immutable Version Lineage Foundation v1

## Status and authority boundary

This Stage-7 foundation records which exact inert candidate versions and
promotion-evidence chains have been registered for later review. The standalone
distribution is `ayyo-policy-registry`; its public module is
`ayyo_policy_registry`.

**REGISTRATION IS NOT DEPLOYMENT OR ACTIVATION.** `REGISTERED` means only that
one exact candidate identity and its independently verified evidence chain are
present in an immutable snapshot. `ALREADY_REGISTERED` is an explicit
idempotency result for the same record. Neither status grants human approval,
physical safety, model loading, execution, Runtime dispatch, or production
authority. `ELIGIBLE` remains evidence, not authorization.

The dependency direction is strictly one way:

```text
policy_registry
  → promotion_control
    → learning_evaluation
      → teach_mode
```

The registry runtime imports only `ayyo_promotion_control`. Promotion control
owns the authoritative verification/evaluation route into its lower layers.
No lower package or ROS package imports the registry.

## Explicit flow

```text
verified Teach Mode evidence
  → bounded candidate/holdout corpus
  → inert candidate manifest
  → concrete offline trial evidence
  → verified offline evaluation report
  → caller-owned promotion criteria and request
  → authoritative ELIGIBLE promotion decision
  → explicit CandidateRegistrationRequest
  → pure register_candidate(...)
  → immutable RegisteredPolicyVersion
  → immutable PolicyRegistrySnapshot
  → stop
```

The package never runs candidate code. It has no active-policy pointer, model
runner, installer, persistence adapter, filesystem registry, network service,
ROS integration, timer, thread, worker, or module-global registry state.

## Public contracts

### `CandidateRegistrationRequest`

An immutable caller request binds the exact candidate, evaluation report,
promotion criteria, promotion request, promotion decision, target review stage,
and bounded provenance supplied to its constructor. It stores their exact IDs
and SHA-256 fingerprints instead of duplicating fields already derived from the
upstream immutable artifacts. An optional normalized note is committed to the
request identity but is never interpreted as authority.

The request may describe an attempt whose evidence will later be rejected.
Construction proves structural identity; `register_candidate()` independently
re-evaluates the complete chain before producing a record.

### `RegisteredPolicyVersion`

A registered version is an immutable content-addressed record of one exact:

- candidate ID/fingerprint, semantic version, policy family, and evidence set;
- input/output contract identity and semantic version;
- explicit candidate parent ID/fingerprint, or honest absence;
- evaluation report, evaluation contract, and holdout evidence-set identity;
- promotion criteria, request, decision, and target review stage;
- registration request and registration provenance.

It contains no candidate payload, model weights, path, URL, callback, command,
or executable. A record says only: “this exact inert candidate version and this
exact verified review evidence are registered.”

### `PolicyRegistrySnapshot`

The snapshot is an immutable canonical tuple of registered versions. Ordering
is deterministic by policy family and record identity. Caller sequences are
copied before validation. The snapshot rejects duplicate record identities,
duplicate candidate identities, conflicting `(policy family, semantic version)`
pairs, unresolved parent identities, incompatible parent families/contracts,
cycles, and resource overflow.

There is no mutable alias, `latest`, `current`, or active-policy field. Exact
family/version lookup does not rank versions or infer ancestry.

### `RegistrationResult`

The immutable result binds the registration request, registered version,
previous snapshot, updated snapshot, and closed status:

- `REGISTERED`: the updated snapshot adds exactly the bound record;
- `ALREADY_REGISTERED`: the exact record already exists and the snapshot is
  unchanged.

Any same-family semantic-version collision with different content fails with a
typed error. Registration never silently creates a second record.

## Registration verification

`register_candidate()` requires the previous snapshot, registration request,
candidate, evaluation report, promotion criteria, promotion request, and
promotion decision as explicit arguments. It:

1. verifies the snapshot and registration request;
2. invokes promotion control's authoritative evaluator, which independently
   verifies the candidate, concrete corpus/trial report, criteria, and request;
3. verifies the supplied decision and requires it to equal that authoritative
   recomputation exactly;
4. requires `ELIGIBLE` and exact candidate/report/criteria/request/decision and
   target-stage bindings;
5. derives the record only from the verified artifacts;
6. checks duplicate/version rules and explicit parent compatibility;
7. constructs a new immutable snapshot and self-verifying result.

Malformed identities, in-memory modification, substituted artifacts, rewritten
trial evidence, holdout mismatch, ineligible or forged decisions, criteria or
request substitution, target mismatch, version conflict, and invalid lineage
all fail closed. Registry code does not reimplement a weaker evaluation or
promotion algorithm.

## Explicit version lineage

Candidate lineage comes only from the existing candidate manifest's explicit
`parent_candidate_id` and `parent_candidate_fingerprint`. A parent must already
be present in the supplied snapshot with that exact identity and must share the
same policy family and input/output contract identities and versions.

Semantic-version comparison never establishes ancestry. `9.0.0` may be an
unrelated root and `1.0.0` may be registered later. Self-parenting, unresolved
or fingerprint-substituted parents, cross-family parentage, incompatible
contracts, and direct or longer cycles are rejected. V1 remains a bounded
immutable lineage set, not a graph database.

## Read-only resolution

`resolve_registered_policy()` requires an exact record ID/fingerprint pair.
`resolve_policy_version()` requires an explicit policy-family ID and semantic
version. Each returns the immutable matching record or `None`; malformed lookup
identities fail with `PolicyResolutionError`. Neither API selects a latest
version, mutates state, or grants authority.

## Canonical identity and serialization

The four artifact schemas are:

| artifact | schema ID |
|---|---|
| registration request | `ayyo.policy-registry.registration-request.v1` |
| registered version | `ayyo.policy-registry.registered-policy-version.v1` |
| registry snapshot | `ayyo.policy-registry.snapshot.v1` |
| registration result | `ayyo.policy-registry.registration-result.v1` |

Every schema version is `1.0.0`. IDs and content fingerprints are deterministic
SHA-256 identities over compact, sorted-key, UTF-8 canonical JSON. Identity
excludes wall time, host, PID, filesystem path, random UUID, and object identity.

`canonical_registry_artifact_json()` accepts only a verified public artifact.
`registry_artifact_from_canonical_json()` is inspect-only and requires exact
canonical text/bytes. It rejects malformed UTF-8/JSON, duplicate keys,
non-finite constants, non-object roots, unknown or missing fields, unsupported
schema IDs/versions/enums, unexpected types, malformed identities, resource
overflow, noncanonical encoding/order, nested tampering, and reconstructed
content or identity differences. Deserialization executes nothing.

## V1 resource bounds

| resource | maximum |
|---|---:|
| identifier | 256 characters |
| optional note | 512 Unicode characters |
| registered versions per snapshot | 64 |
| policy families per snapshot | 16 |
| canonical registration request | 16,384 UTF-8 bytes |
| canonical registered version | 16,384 UTF-8 bytes |
| canonical registry snapshot | 262,144 UTF-8 bytes |
| canonical registration result | 524,288 UTF-8 bytes |

The larger result bound covers two bounded snapshots for independently
verifiable before/after transition evidence. These remain finite in-memory
artifacts; the core saves neither representation.

## Implemented and not implemented

Implemented: explicit registration requests; immutable exact-version records;
bounded canonical snapshots; explicit idempotent results; authoritative
promotion-chain recomputation; exact parent lineage; deterministic read-only
resolution; strict canonical serialization; typed errors; adversarial and
cross-layer tests.

Not implemented: candidate generation, training, fine-tuning, inference, model
loading/execution, installation, deployment, activation, active-policy state,
automatic promotion, automatic rollback, human approval/authentication,
persistence, cache, registry service, background work, Runtime dispatch, Safety
bypass, Skill execution, ROS/Gazebo, simulation control, robot commands, or
hardware authority.

The separately reviewed approval-evidence and future-activation eligibility
boundary now consumes exact registry identity, but registry presence alone
cannot satisfy it. Production authority authentication/enforcement and any
actual activation boundary remain future work before a sandbox/model runner or
runtime path may exist.

## Focused validation

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src:promotion_control/src:policy_registry/src \
python3 -m pytest -q policy_registry/tests
```
