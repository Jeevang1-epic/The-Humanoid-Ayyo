# Teach Mode Demonstration Capture Foundation v1

## Status and purpose

This first Stage-7 foundation answers only: **what exactly was demonstrated?**
It captures bounded historical evidence. It does not decide what Ayyo should
learn, change, remember durably, or perform autonomously.

The standalone distribution is `ayyo-teach-mode`; its public module is
`ayyo_teach_mode`. The episode schema identity is
`ayyo.teach-mode.demonstration-episode.v1`, schema version `1.0.0`. The one
reviewed capture policy is `ayyo.teach-mode.explicit-capture-policy.v1`, policy
version `1.0.0`.

## Ownership and dependency direction

Teach Mode owns only immutable demonstration episodes, explicit capture-session
semantics, canonical in-memory serialization, integrity verification, and
adapting an already-completed Stage-6 report.

```text
caller
  → explicit DemonstrationRecorder.begin(...)
  → explicit session.append(typed immutable event)
  → explicit session.finish(typed outcome)
  → immutable DemonstrationCaptureResult / DemonstrationEpisode

ayyo_teach_mode
  → ayyo_developmental_scenarios public immutable contracts

developmental_scenarios and every lower production package
  ✕ no reverse dependency on ayyo_teach_mode
```

The core has no ROS, Gazebo, rosbag2, filesystem, database, network, subprocess,
dynamic-loading, Runtime Bridge dispatch, Safety mutation, Skill mutation,
Executive invocation, Working Memory mutation, or Memory OS write dependency.
No lower production package depends on Teach Mode.

## Immutable episode model

`DemonstrationEpisode` contains:

- exact schema identity and semantic version;
- exact capture-policy identity, version, and fingerprint;
- deterministic episode ID and integrity fingerprint;
- one closed `DemonstrationSourceKind`;
- canonical robot identity where the source requires it;
- one explicit `DemonstrationSourceTimeRange`;
- bounded `DemonstrationProvenance`;
- a non-empty, caller-ordered tuple of typed events; and
- one explicit typed outcome.

Completed episodes, events, references, annotations, outcomes, capture policy,
and results are frozen and slot-backed. Mutable caller sequences are copied to
tuples. Mutating a caller-owned list after construction cannot change episode
meaning, ordering, provenance, identity, or fingerprint.

Identity is derived only from canonical semantic content. Construction never
reads or includes a random UUID, current wall-clock time, PID, hostname,
username, absolute filesystem path, or Python object identity.

## Closed sources, events, and references

Version 1 source kinds are exactly:

- `DEVELOPMENT_SCENARIO`;
- `TEST_FIXTURE`; and
- `RECORDED_SOURCE_REFERENCE`.

`RECORDED_SOURCE_REFERENCE` means only a bounded reference with verified
content identity. It does not claim that Teach Mode recorded the material or
that it came from a physical human demonstration. Raw recording remains
external.

Event types are a fixed vocabulary: observation, intent, Executive proposal,
Safety decision, Skill binding, Runtime result, development action, outcome,
and annotation. Each event has a unique bounded ID and an explicit contiguous
zero-based sequence index. Event order is semantic and is never sorted away.

Observation references are typed identities for World Snapshot, Working
Memory evidence, anonymous semantic evidence, robot body state, Stage-6 report
or assertion, sensor evidence, external recording, or another public evidence
contract. They cannot contain raw RGB frames, depth arrays, PCM audio, ROS
message histories, or arbitrary metadata.

Action references are historical evidence only. They retain a typed action
kind, exact evidence reference, disposition, reason, target semantics when
applicable, and either `NONE` or `DEVELOPMENT_ONLY` authority. The package
exposes no `execute`, action application, Runtime dispatch, or executable replay
operation. A requested action remains distinct from a completed action.

## Outcome truthfulness

`DemonstrationOutcomeStatus` distinguishes `SUCCESS`, `FAILURE`, `DEFERRED`,
`REJECTED`, `INCOMPLETE`, and `UNKNOWN`. An outcome always has bounded typed
reason codes and an explicit detail. Recording a request never implies success.

Safety and downstream dispositions are preserved without reinterpretation.
`DEFERRED` is not approval, safety certification, or successful execution.
Rejected, incomplete, unknown, and failed evidence remain useful historical
examples without being repaired into positive demonstrations.

## Provenance and teacher-source semantics

Provenance contains one source reference, one content fingerprint, and an
optional `teacher_source_ref`. That optional label is inert caller-supplied
provenance. Ayyo does not yet authenticate an owner, teacher, known human, or
authorized instructor; the label grants no identity, permission, truth, Safety,
learning, memory, or action authority.

Annotations use a closed kind enum and normalized NFC text. They are caller
evidence, not trusted instructions. Annotation content is never evaluated or
executed.

## Source clocks and ordering

Clock kinds are explicit: simulation time, test time, recorded-source time,
monotonic time, or unavailable. Available ranges require bounded ordered start
and end nanoseconds, every event carries a timestamp inside that range, and
event timestamps cannot move backwards. Unavailable time requires both range
values and every event timestamp to remain absent. The package never converts
simulation, test, recorded, or monotonic time to UTC and never fabricates a
timestamp.

Current Stage-6 reports intentionally exclude runtime timing from semantic
identity. Their adapter therefore records `UNAVAILABLE` rather than inventing
start/end times, while retaining the exact simulation/test source provenance
already present in report references.

## Hard resource bounds

| Resource | v1 maximum |
| --- | ---: |
| events per episode | 64 |
| combined observation/action references per event | 16 |
| annotations per event | 8 |
| annotations per episode | 32 |
| annotation or outcome-detail text | 512 characters |
| identity string | 256 characters |
| outcome reasons | 16 |
| canonical serialized episode | 65,536 UTF-8 bytes |

No batch API exists in version 1, so no unbounded episode collection is
accepted. Large sensor histories and arbitrary JSON payloads have no field in
the episode model.

## Deterministic serialization and integrity

`canonical_episode_json` returns sorted-key, compact, UTF-8 JSON with non-finite
numbers forbidden. Equal semantic episodes produce byte-identical JSON, the
same content fingerprint, and the same episode ID.

`episode_from_canonical_json` accepts only bounded UTF-8, rejects duplicate
keys, non-canonical representation, unknown or missing fields, incompatible
schema/policy identity, invalid enums and bounds, and mismatched stored
identities. It reconstructs an immutable episode but performs no action and no
file I/O.

`verify_episode` is a pure local fail-closed verifier. It recomputes schema,
policy, enum, ordering, uniqueness, clock, robot/source, resource, fingerprint,
episode-ID, and canonical-content invariants. Tampering produces typed integrity
reasons.

## Explicit capture sessions

`DemonstrationRecorder.begin` creates one inert caller-controlled session.
`session.append` accepts exactly one immutable typed event at the next sequence
index. `session.finish` accepts one explicit outcome, seals the session, and
returns an immutable result. Empty capture, duplicate IDs, sequence gaps,
overflow, append-after-finish, and a second finish fail closed.

There is no background recording, timer, ROS subscription, source discovery,
filesystem watcher, or automatic persistence.

## Stage-6 integration and examples

`capture_development_scenario_report` first reconstructs and verifies one exact
public immutable `DevelopmentScenarioReport`; it never changes the report or
scenario definition. The report ID, scenario fingerprint, report outcome,
robot, sources, policy reasons, assertions, and authority facts remain explicit
references in the episode.

The three required examples are:

1. `development-only-neck-actuation` becomes a `SUCCESS` episode containing
   initial robot/source evidence, the historical requested `0.1` rad
   `neck_yaw_joint` target, observed target/result evidence, and the observed
   `0.0` rad reset. Every action remains `DEVELOPMENT_ONLY`; no production
   authority is created.
2. `production-physical-request-deferred` becomes a `DEFERRED` episode. It
   preserves the Executive request/proposal, Safety `DEFERRED` with
   `physical-movement-information-unavailable`, ineligible Skill binding,
   Runtime deferral/non-dispatch, stationary observed state, and exactly zero
   production dispatch. This demonstrates refusal behavior, not movement.
3. `invalid-development-command-rejected` becomes a `REJECTED` episode. It
   preserves the requested `1.3` rad target, typed above-maximum rejection, no
   invalid target movement, no fabricated World Model state, and subsequent
   controller/query health. It is negative evidence, not a corrected success.

The adapter also accepts the other three published Stage-6 reports as bounded
generic scenario evidence. It does not launch ROS, Gazebo, scenarios,
controllers, or development control.

## Explicitly not implemented

- automatic learning, training, fine-tuning, gradients, embeddings, behavior
  cloning, imitation learning, or reward models;
- candidate or learned policies, model/policy updates, evaluation, promotion,
  rollback, skill synthesis, or skill mutation;
- executable replay, autonomous behavior, Runtime Bridge dispatch, simulation
  control, or production motion;
- Memory OS persistence, Working Memory mutation, automatic consolidation,
  Personal Context update, database storage, or hidden file writes;
- owner/teacher authentication, authority inference, physical-human
  demonstration capture, raw-sensor recording, rosbag management, or physical
  hardware validation.

Canonical JSON may be handed to a caller, but saving it is outside the core and
must be an explicit separately reviewed action. Deserialization means inspect
and verify only; it never means repeat robot actions.

## Focused validation

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src \
python3 -m pytest -q teach_mode/tests
```

The focused suite covers deterministic identity and bytes, immutability,
caller-input isolation, enum/order/time/resource failures, outcome truthfulness,
tampering, raw-payload exclusion, explicit session lifecycle, all six Stage-6
adapters, the three required positive/deferred/rejected examples, absence of
launch/write side effects, one-way package dependencies, and wheel contents.
