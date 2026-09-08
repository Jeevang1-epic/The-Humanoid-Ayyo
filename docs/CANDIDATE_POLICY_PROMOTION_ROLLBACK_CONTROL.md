# Candidate Policy Promotion and Rollback Control Plane

## Scope and authority boundary

Candidate Policy Promotion & Rollback Control Plane Foundation v1 is the
standalone `ayyo-promotion-control` distribution in `promotion_control/`. It
consumes immutable candidate manifests and offline evaluation reports from
`ayyo-learning-evaluation==0.1.0`. The dependency direction is strictly:

```text
promotion_control → learning_evaluation → teach_mode
```

No lower layer imports this package. The package is transport-neutral, pure,
and inert. It has no policy loader, model runner, installer, registry, mutable
active-policy pointer, runtime adapter, persistence, network, ROS, Gazebo,
thread, timer, or background worker.

An `ELIGIBLE` promotion decision means only that the supplied immutable
evidence satisfies the supplied caller-owned criteria. It does not mean that a
candidate was promoted, approved by a person, installed, loaded, trained,
executed, dispatched, or made active. Likewise, `ROLLBACK_ELIGIBLE` means only
that an explicit request and evidence chain satisfy rollback criteria. It does
not mutate current state or perform a rollback.

The target stages `reviewed_candidate` and `future_deployment_review` are
control-plane evidence labels. Neither is an execution environment.

## Promotion contracts

`PromotionCriteria` is explicit and content-addressed. It binds:

- one exact candidate ID and fingerprint;
- one required offline-report schema ID and semantic version;
- one exact holdout evidence-set ID and fingerprint;
- a non-empty closed set of accepted offline dispositions;
- a minimum number of evaluated trials and maximum number of failed trials;
- whether complete holdout coverage is required; and
- a non-empty allowlist of target stages.

`CandidatePromotionRequest` binds one exact candidate, evaluation report,
criteria artifact, target stage, and provenance identity. Its optional bounded
note is committed to the request identity, but is never interpreted as
authority or used to satisfy a criterion.

`evaluate_promotion()` first verifies every supplied artifact and fails closed
with a typed error if any in-memory identity is malformed or altered. For
structurally valid evidence, it emits exactly one immutable
`PromotionDecision` with `ELIGIBLE` or `NOT_ELIGIBLE`. It checks request
bindings, candidate/report lineage, criteria candidate identity, target
allowlisting, report schema/version, disposition, complete coverage, evaluated
trial minimum, failed-trial maximum, and holdout identity. All rejections carry
closed typed reasons. The evaluator performs no I/O or state mutation.

## Known-good and rollback contracts

`KnownGoodPolicyReference` is an immutable, content-addressed reference to one
exact target candidate and one exact eligible promotion decision. It retains
the target's semantic version, candidate-evidence identity, policy family,
input/output contracts, target stage, and caller-supplied provenance. Creating
one requires a verified eligible promotion decision for that same candidate.
The reference is not a registry entry and does not claim the target is or ever
was deployed.

`RollbackCriteria` binds one exact current candidate, one exact known-good
reference, an allowlist of rollback reasons, and a minimum evidence-reference
count. `RollbackRequest` binds those criteria and identities, one closed reason,
one to eight immutable typed evidence references, provenance, and an optional
non-authoritative note.

Each reason requires evidence of the corresponding kind:

| rollback reason | required evidence kind |
|---|---|
| `evaluation_regression` | `evaluation_report` |
| `safety_regression` | `safety_review` |
| `runtime_regression` | `runtime_observation` |
| `operator_request` | `operator_instruction` |
| `integrity_failure` | `integrity_report` |

`evaluate_rollback()` verifies criteria, request, current candidate, target
candidate, known-good reference, and source promotion decision. It rejects an
unknown or substituted known-good identity, a substituted target or promotion
decision, self-rollback, incompatible policy-family or input/output contract
lineage, a disallowed reason, insufficient evidence, and a mismatched evidence
kind. It returns only `ROLLBACK_ELIGIBLE` or `ROLLBACK_REJECTED` evidence. It
does not locate, load, install, activate, or execute either policy.

## Canonical identity and transport

All eight public artifacts are immutable and receive separate deterministic
SHA-256 content fingerprints and IDs:

| artifact | schema ID |
|---|---|
| promotion criteria | `ayyo.promotion-control.promotion-criteria.v1` |
| promotion request | `ayyo.promotion-control.promotion-request.v1` |
| promotion decision | `ayyo.promotion-control.promotion-decision.v1` |
| rollback evidence reference | `ayyo.promotion-control.rollback-evidence-reference.v1` |
| known-good policy reference | `ayyo.promotion-control.known-good-policy.v1` |
| rollback criteria | `ayyo.promotion-control.rollback-criteria.v1` |
| rollback request | `ayyo.promotion-control.rollback-request.v1` |
| rollback decision | `ayyo.promotion-control.rollback-decision.v1` |

Every schema version is `1.0.0`. `canonical_control_artifact_json()` accepts
only a verified public artifact. `control_artifact_from_canonical_json()`
accepts canonical UTF-8 text or bytes, dispatches by the exact closed schema
identity, reconstructs the typed value, and requires the reconstructed document
to equal the input exactly. It rejects malformed JSON/UTF-8, non-canonical
encoding, duplicate keys, unknown or missing fields, unknown schemas, wrong
versions, unsupported enums, malformed SHA-256 identities, non-finite JSON,
invalid types, resource violations, and content/identity tampering.

## V1 resource bounds

| resource | bound |
|---|---:|
| identifier | 256 characters |
| optional note | 512 Unicode characters |
| general closed sequence | 16 items |
| rollback evidence references | 8 items |
| canonical serialized artifact | 32,768 UTF-8 bytes |
| evaluated/failed trial criteria | upstream evaluation maximum of 16 |

Booleans are not accepted as integer thresholds. Lists with duplicate enum
values or evidence identities are rejected. Caller sequences are snapshotted
and deterministically sorted, so later caller mutation and input ordering cannot
change an artifact.

## Implemented and not implemented

Implemented: immutable promotion/rollback criteria, explicit requests,
content-addressed known-good and reason-evidence references, pure deterministic
eligibility evaluators, strict canonical round trips, typed fail-closed errors,
closed statuses/reasons/stages, exact evidence and lineage checks, hard bounds,
and package-boundary tests.

Not implemented: candidate generation, training, inference, policy execution,
installation/loading, active-policy state, automatic promotion, automatic
rollback, runtime dispatch, policy registry, persistence, scheduling,
authentication/authorization, human approval workflow, ROS/Gazebo, simulation
control, robot/hardware commands, or physical validation.

## Focused validation

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src:promotion_control/src \
python3 -m pytest -q promotion_control/tests
```
