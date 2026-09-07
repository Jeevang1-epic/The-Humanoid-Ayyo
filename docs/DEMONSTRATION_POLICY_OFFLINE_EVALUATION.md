# Demonstration Candidate Policy and Offline Evaluation Foundation v1

## Status and safety statement

This Stage-7 foundation turns explicitly selected, already-completed Teach Mode
episodes into reviewable evaluation evidence. It implements a bounded corpus,
an inert candidate-policy manifest, explicit caller-supplied trial results, and
a pure deterministic evaluation report.

**OFFLINE EVALUATION DOES NOT GRANT EXECUTION AUTHORITY.** Meeting offline
criteria grants zero promotion, Safety, Skill, Runtime, transport, simulation,
hardware, or production authority.

The distribution is `ayyo-learning-evaluation`; its public module is
`ayyo_learning_evaluation`. Its only direct runtime dependency is the exact
public Teach Mode distribution `ayyo-teach-mode==0.1.0`.

## Explicit flow and ownership

```text
explicit caller-supplied verified DemonstrationEpisode objects
  → explicit bounded DemonstrationEvaluationCorpus construction
  → explicit inert CandidatePolicyManifest construction from candidate evidence
  → explicit caller-supplied OfflineTrialResult objects for holdout references
  → explicit pure evaluate_offline(...) aggregation
  → immutable OfflineEvaluationReport
  → stop

ayyo_learning_evaluation
  → ayyo_teach_mode

Teach Mode, Stage 6, production layers, and ROS packages
  ✕ no reverse dependency on ayyo_learning_evaluation
```

The package never captures or launches demonstrations. It has no ROS, Gazebo,
filesystem, database, network, subprocess, watcher, timer, worker, dynamic
loading, model framework, Memory OS, Executive, Safety, Skill, Runtime Bridge,
or simulation-control dependency.

## Corpus and partitions

`DemonstrationEvaluationCorpus` uses schema
`ayyo.learning-evaluation.demonstration-corpus.v1`, version `1.0.0`. Every
supplied object must be an exact `DemonstrationEpisode` and must pass Teach
Mode's existing pure `verify_episode` check before inclusion. The manifest
retains references only: episode ID and content fingerprint, explicit
partition, robot/source compatibility, source kind, historical outcome, and
capture-policy identity/version/fingerprint. It never copies episode events,
annotations, sensor content, or raw payloads.

The closed partitions are exactly:

- `CANDIDATE_EVIDENCE`, the only evidence source that may bind a candidate;
- `HOLDOUT_EVALUATION`, visible only to corpus/evaluation reporting.

Both partitions are non-empty and caller assigned. Construction performs no
random, automatic, time-based, or order-dependent split. Order is not semantic
inside a partition, so references are canonically sorted by episode ID.
Duplicate identities and any cross-partition overlap fail closed. There is no
`TRAIN` partition because this milestone implements no training.

Each partition receives its own content-addressed evidence-set identity and
fingerprint. The full corpus identity covers both sets and compatibility data.

## Holdout isolation

The candidate manifest constructor accepts only a verified
`CANDIDATE_EVIDENCE` set. Its stored provenance is exactly that set's ID and
fingerprint. The artifact has no holdout field and stores no corpus ID,
holdout-set ID, holdout episode ID/fingerprint, outcome, annotation, event, or
evaluation result.

Consequently, changing only holdout evidence changes the holdout set and full
corpus identities but cannot change the candidate evidence-set identity or a
candidate-policy identity. Changing candidate evidence changes both the
candidate source identity and any candidate built from it. Evaluation rejects
unknown episodes and candidate-evidence identities masquerading as holdout.

## Inert candidate policy

`CandidatePolicyManifest` uses schema
`ayyo.learning-evaluation.candidate-policy.v1`, version `1.0.0`. It records an
explicit candidate semantic version, policy family, candidate-evidence source,
input/output contract identities and versions, bounded description, optional
structural parent identity, and an optional inert external artifact identity.

An `InertArtifactReference` contains only a bounded identifier, kind, and
SHA-256 content fingerprint. Paths, URLs, commands, source, bytecode, pickles,
weights, callbacks, and executable payloads have no field. Nothing loads the
reference. Candidate version ordering has no automatic meaning: a higher or
newer version is not approved, preferred, promoted, safe, or runtime eligible.
Multiple versions may coexist as inert evidence.

The candidate exposes no `predict`, `act`, `execute`, `step`, `run`,
`dispatch`, `apply`, `promote`, `rollback`, training, inference, or model-load
operation.

## Offline trial contract

`OfflineTrialResult` uses evaluation contract
`ayyo.learning-evaluation.offline-trial.v1`, version `1.0.0`. It binds exactly
one verified candidate ID/fingerprint to one explicitly referenced holdout
episode ID/fingerprint, the episode's unchanged historical outcome, a typed
observed outcome or honest absence, a closed status, bounded typed reasons,
required result-source provenance, and optional exact integer-rational metrics.

Statuses are `OUTCOME_MATCH`, `OUTCOME_MISMATCH`, and `INCOMPLETE`. Their
constructor invariants prevent a match from naming a different outcome, a
mismatch from naming the same outcome, or an incomplete result from fabricating
an observed outcome. Historical `SUCCESS`, `FAILURE`, `DEFERRED`, `REJECTED`,
`INCOMPLETE`, and `UNKNOWN` remain distinct; negative evidence is never repaired
into positive evidence.

Trial results are supplied by a caller. Version 1 contains no candidate runner.
A future separately reviewed runner may emit this contract, but it cannot alter
Teach Mode, corpus identity, holdout isolation, or report integrity.

## Pure evaluator and report

`evaluate_offline` verifies the corpus, candidate, every trial identity, exact
candidate lineage, exact holdout membership, episode fingerprints, expected
historical outcome, and evaluation-contract identity/version. It rejects
duplicate, unknown, candidate-partition, wrong-candidate, wrong-episode, and
tampered trials. It performs no I/O and never invokes candidate code.

The immutable report schema is
`ayyo.learning-evaluation.offline-report.v1`, version `1.0.0`. Its deterministic
content identity covers candidate and evidence-set lineage, exact trial and
evaluated/missing/incomplete episode IDs, typed status and historical-outcome
counts, exact coverage numerator/denominator, optional summed integer-rational
metrics, typed reasons, and disposition.

Disposition semantics are deliberately neutral:

- `MEETS_OFFLINE_CRITERIA`: every holdout has a complete trial and every
  observed outcome exactly matches its historical expected outcome;
- `DOES_NOT_MEET_OFFLINE_CRITERIA`: coverage is complete and at least one
  result differs;
- `INCOMPLETE`: at least one holdout result is missing or explicitly
  incomplete.

These criteria are evidence bookkeeping, not an ML score or an authority gate.
Missing or incomplete results remain visible and take precedence over a
positive disposition. Failed or mismatched trials remain in exact counts.

## Determinism and resource bounds

Canonical JSON uses sorted keys, compact separators, UTF-8, and forbidden
non-finite numbers. Identity is SHA-256 over semantic content only. It excludes
wall time, PID, host, user, path, random UUID, Python object identity, and input
mapping order. Inspect-only parsers reject duplicate keys, noncanonical JSON,
unknown/missing fields, unsupported versions/enums, overflow, and identity
tampering; deserialization never executes anything.

Version 1 limits are:

| Resource | Maximum |
| --- | ---: |
| episodes per corpus | 32 |
| episodes per partition | 16 |
| identity text | 256 characters |
| description/metadata text | 512 characters |
| canonical corpus JSON | 65,536 UTF-8 bytes |
| canonical candidate JSON | 16,384 UTF-8 bytes |
| trials per evaluation | 16 |
| typed reasons per trial | 8 |
| exact metrics per trial | 8 |
| one metric numerator or denominator | 1,000,000,000 |
| canonical report representation | 65,536 UTF-8 bytes |

The 32/16 limits permit two equally bounded review partitions without creating
a giant batch API. Text and corpus/report limits follow Teach Mode's existing
256/512/65,536 style. Candidate JSON is smaller because it contains only inert
identity/lineage metadata. Metrics are integers; floats, booleans, NaN, and
infinity are not accepted.

## Implemented and not implemented

Implemented: immutable bounded corpus/reference/evidence-set contracts; strict
canonical corpus and candidate serialization; separate candidate and holdout
identities; inert versioned candidate lineage; explicit immutable trials; pure
offline aggregation; deterministic immutable reports; Stage-6 success,
production-deferred/zero-dispatch, and invalid-command-rejected integration
proofs; package/dependency and abuse tests.

Not implemented: candidate generation, training, learning, fine-tuning,
gradients, model inference/loading/execution, behavior cloning, reinforcement
learning, automatic splitting, winner selection, promotion, rollback,
executable replay, persistence, authentication, background work, ROS/Gazebo,
simulation/physical control, or any runtime/hardware authority.

## Focused validation

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src \
python3 -m pytest -q learning_evaluation/tests
```
