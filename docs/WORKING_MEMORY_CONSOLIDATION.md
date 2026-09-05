# Working Memory Candidate Discovery, Bridge, and Selection Foundations v1

## Responsibility

`ayyo-memory-consolidation` owns three explicit transport-neutral steps between
temporary Working Memory evidence and Memory Validation: bounded discovery,
candidate staging, and reviewed selection. Each remains a separate caller
decision.

```text
Perception admission
→ bounded Working Memory
→ caller invokes BoundedMemoryCandidateDiscoveryPolicy.discover
→ immutable CandidateDiscoveryProposal + ConsolidationRequest
→ caller chooses that request (or constructs an exact request directly)
→ explicit ConsolidationRequest + exact EvidenceReference
→ WorkingMemoryCandidateBridge.stage(request, now_ns=...)
→ CandidateStagingResult
→ CandidateReviewItem.from_staging(...)
→ ReviewedMemoryCandidateSelectionPolicy.select(...)
→ caller passes selected CandidateEvidence to MemoryValidationService.evaluate
→ separate caller review
→ optional separate MemoryValidationService.apply
→ Memory OS
```

The stateless discovery policy exposes only `discover`; the bridge exposes only
`stage`; and the separate stateless selector exposes only `select`. Discovery
does not call either later operation. None has an automatic `evaluate`, `apply`,
persistence, timer, worker, thread, scheduler, ROS, Personal Context, Executive,
Safety, Skill, Runtime, or action API. See the focused
[Bounded Memory Candidate Discovery Policy](MEMORY_CANDIDATE_DISCOVERY.md) and
[Reviewed Memory Candidate Selection Policy](REVIEWED_MEMORY_CANDIDATE_SELECTION.md)
for their exact semantics.

## Dependency direction

Before this milestone:

```text
Working Memory → World Model
Memory Validation → Memory OS
```

After this milestone:

```text
Memory Consolidation
├──→ Working Memory → World Model
├──→ World Model public evidence contracts
├──→ Memory Validation → Memory OS
└──→ Memory OS public MemoryType/Provenance contracts
```

Working Memory, World Model, Perception, Memory Validation, and Memory OS do not
depend back on the bridge. The direct Memory OS dependency is model-only; bridge
source imports no `MemoryService`, SQLite implementation, or persistence API.

## Public API

- `BoundedMemoryCandidateDiscoveryPolicy.discover(working_memory, *, now_ns)`
  explicitly returns one immutable, versioned `CandidateDiscoveryResult` with
  canonical proposals and typed diagnostics. It retains no Working Memory
  reference or discovery history.
- `CandidateDiscoveryProposal` contains the exact existing
  `ConsolidationRequest` that a caller may separately choose to stage, plus
  policy identity/version/fingerprint and a deterministic proposal ID.
- `EvidenceReference` contains the exact retained observation ID, canonical
  fingerprint string, expected provenance source ID, and an optional exact
  semantic-item ID.
- `ConsolidationRequest` contains robot ID, `MemoryType`, subject, predicate,
  proposed JSON value, one evidence reference, and optional bounded metadata.
  Construction snapshots mutable values, metadata, and reference sequences.
- `WorkingMemoryCandidateBridge.stage(request, *, now_ns)` returns a typed
  `CandidateStagingResult` with either an immutable `CandidateEvidence` or an
  ineligibility reason and no candidate.
- `CandidateReviewItem.from_staging(result)` binds that exact eligible staging
  result to its unchanged candidate for direct-observation review selection.
- `ReviewedMemoryCandidateSelectionPolicy.select(items)` returns immutable,
  versioned `SELECT_FOR_REVIEW`, `DEFER`, or `REJECT_SELECTION` item decisions
  with typed reasons and canonical candidate IDs/order.

There are deliberately no caller fields for confidence, observation UTC time,
provenance, provenance authority, correction target, or correction reason.

## Eligibility policy

Version 1 requires all of the following:

- the request robot matches the exact Working Memory configuration;
- the selected observation is still in the bounded recent-evidence window;
- reconstructing every retained observation preserves its canonical identity;
- the selected observation ID, fingerprint, provenance source, allowed
  provenance profile, robot, and configured source clock all match;
- the selected evidence is not future-dated and is currently `FRESH` under the
  Working Memory freshness threshold;
- the configured and observed clock is exactly `ROS_SYSTEM_TIME`;
- source nanoseconds divide evenly by 1,000, so conversion to Python UTC
  `datetime` loses no precision;
- the selected observation or semantic item supplies an actual float
  confidence; `None` is ineligible while `0.0` remains exactly zero;
- observational memory type is episodic, semantic, spatial, or failure—not
  preference, social, or procedural;
- semantic evidence additionally selects one exact item and retains its exact
  frame → interpretation → detection source chain.

Expired, reset-epoch, evicted, and never-known IDs are intentionally
indistinguishable at this stateless public read boundary: none is currently
retained, so all fail closed as `evidence_not_found`. Stale-but-retained evidence
fails as `evidence_stale`. Simulation, recorded, and test clocks are never
relabeled UTC. The bridge never uses wall-clock now or evaluation time as the
observation time.

## Provenance mapping

Eligible candidates always use Memory OS `DIRECT_OBSERVATION`. Generic
observation provenance includes the exact observation ID/fingerprint, robot,
source nanoseconds, and complete compact World Model provenance document, plus
sensor/frame fields when present. Anonymous semantic provenance also includes
the exact semantic item, detection, frame, interpretation, producer, result
time, and compact evaluation-reference identities.

The selected semantic-item ID becomes the candidate provenance `source_id`;
otherwise the selected observation ID does. Caller metadata cannot replace
derived provenance. Raw pixels, audio samples, depth arrays, model reports, and
unbounded payloads are never copied.

## Anonymous semantic guarantee

Anonymous visual evidence can discover or stage only an explicit episodic proposition with
the Working Memory robot as subject, predicate
`observed_anonymous_person`/`observed_anonymous_object`, and a value containing
only `anonymous: true`, kind, normalized region, and object category when
applicable. Discovery can construct exactly that proposition; a caller bypassing
discovery must supply it exactly. The bridge independently validates either path.

Evidence IDs remain provenance, never value identity. Category is not object
identity. The bridge cannot generate a person ID, object ID, recognized owner,
owner-owned object, social relation, preference, scene-absence fact, object
permanence, or persistent World Model entity.

## Immutability and bounds

Discovery version 1 inspects at most 64 retained evidence envelopes and returns
at most 32 proposals, 64 diagnostics, and 16 unique reasons under a 65,536
character aggregate output bound. Bridge version 1 supports exactly one evidence
reference per staged candidate. Selection version 1 accepts a separately bounded
batch of at most 32 candidate occurrences. Metadata has at most 16 top-level
fields. Identity/detail text and JSON reuse the public bounded World Model
limits: depth 16, 2,048 nodes, 256 items per collection, 4,096 characters per
text value, 65,536 aggregate/serialized JSON characters, and 1,024-bit integers.
Cycles and non-finite numbers fail closed. Discovery, bridge, and selector are
stateless and retain no history or seen-ID set.

## Deliberate non-goals

- automatic discovery invocation, staging, selection, evaluation, apply, or
  persistence
- autonomous learning, memory extraction, truth scoring, or winner selection
- confidence synthesis or provenance aggregation
- destructive correction or authority upgrade
- fuzzy matching, embeddings, recognition, tracking, identity, preference, or
  social inference
- owner recognition, Personal Context updates, ROS memory services, action
  authority, navigation, manipulation, or motion

## Validation

```bash
PYTHONPATH=memory/src:memory_validation/src:world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src:memory_consolidation/src \
python3 -m pytest -q memory_consolidation/tests
```

The suite covers bounded deterministic discovery, immutable staging, source
identity/tampering, freshness,
expiry/reset, UTC clock conversion, honest confidence including `0.0`/`None`,
anonymous person/object boundaries, correction impossibility, existing Memory
Validation duplicate/conflict/apply behavior, selection duplicate/conflict/
confidence/resource behavior, dependency direction, and one transport-neutral
Perception → Working Memory → discovery → caller-selected staging → selection →
evaluation proof, with no durable record before explicit apply.
