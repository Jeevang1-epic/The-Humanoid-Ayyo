# Controlled Memory Candidate Invocation and Review Pipeline Foundation v1

## Responsibility

`ControlledMemoryCandidateReviewPipeline` is the explicit, transport-neutral
orchestrator for the already-reviewed discovery, staging, selection, and
read-only Memory Validation seams. It reduces caller coordination errors while
preserving a mandatory proposal-ID checkpoint and stopping before persistence.

```text
current Working Memory
→ caller invokes pipeline.prepare(working_memory, now_ns=...)
→ bounded discovery is invoked exactly once
→ immutable MemoryCandidateReviewPlan
→ caller explicitly allowlists proposal IDs
→ immutable MemoryCandidateReviewRequest
→ caller invokes pipeline.execute_review(request, working_memory, now_ns=...)
→ exact selected requests are authoritatively restaged
→ one selection call receives the complete successfully staged batch
→ SELECT_FOR_REVIEW candidates only are evaluated sequentially
→ immutable MemoryCandidateReviewBatch
→ stop
```

The pipeline has no application, persistence, promotion, learning, correction,
background, ROS, runtime, Personal Context, Executive, Safety, Skill, or action
mode. Even a validation decision with `persistence_permitted=True` is only a
reported read result. A separate caller must use the existing Memory Validation
application API if it later chooses to make a durable change.

## Public contracts

- `MemoryCandidateEvaluator` is the narrow dependency protocol. It exposes only
  `evaluate(CandidateEvidence) -> ValidationDecision`.
- `ControlledMemoryCandidateReviewPipeline.prepare(...)` invokes
  `BoundedMemoryCandidateDiscoveryPolicy.discover(...)` once and returns a
  plan. It does not stage, select, evaluate, or write.
- `MemoryCandidateReviewPlan` snapshots the complete bounded discovery result,
  source `now_ns`, pipeline identity, and deterministic plan ID. Convenience
  properties expose discovery policy identity, proposal IDs/count, and
  diagnostic count without duplicating evidence payloads.
- `MemoryCandidateReviewRequest` binds one exact plan to a canonical explicit
  proposal-ID allowlist and deterministic request ID.
- `ControlledMemoryCandidateReviewPipeline.execute_review(...)` verifies the
  plan and request before any downstream operation, stages each allowlisted
  proposal once with the same explicit `now_ns`, invokes selection once, and
  evaluates only selected candidates.
- `MemoryCandidateReviewEntry` retains one requested proposal's exact request,
  staging result, selection item when staged, validation decision when selected,
  evaluated status, and plan/discovery/proposal/candidate lineage.
- `MemoryCandidateReviewBatch` retains the pipeline/source/request identities,
  canonical entries, exact batch selection decision, typed outcome/reasons,
  deterministic batch ID, and discovered/requested/staged/ineligible/selected/
  deferred/rejected/evaluated/validation-decision counts.

All records are frozen and slot-backed. Mutable JSON supplied before discovery
is already snapshotted by `ConsolidationRequest`; preparation reconstructs the
complete discovery result into a separate immutable plan snapshot.

## Identity and plan integrity

The pipeline identity is
`ayyo.controlled-memory-review-pipeline.v1`, version `1`. Its SHA-256
fingerprint commits to:

- the discovery and selection policy fingerprints;
- the explicit two-phase caller gate;
- exact authoritative restaging with no retry or rediscovery;
- rejection of duplicate requested proposal IDs;
- per-entry staging ineligibility;
- one complete-batch selection call;
- selected-only sequential read-only evaluation; and
- all version-1 resource limits.

Plan identity commits to that fingerprint, the prepare source time, exact
discovery result ID and policy identity, canonical proposal IDs, discovery
outcome, diagnostics count, and evidence counts. Proposal IDs already commit to
their complete canonical `ConsolidationRequest`, including exact proposition
and evidence reference. The discovery result ID commits to its canonical
proposals, diagnostics, reasons, outcome, and counts.

Execution reconstructs and revalidates the nested request, proposal, discovery,
plan, and invocation identities and bounds. A changed proposition, evidence
reference, proposal ID, discovery ID, policy identity/fingerprint, plan ID,
allowlist, or request ID fails the whole invocation before staging. Unknown
proposal IDs cannot be injected. Caller ordering is normalized by sorting exact
IDs. Duplicate requested IDs are deliberately **rejected for the whole
invocation**, not silently deduplicated, because an explicit gate must not hide
ambiguous caller intent.

## Structural failure versus per-entry ineligibility

Structural failures perform no partial review work and return no entries or
selection decision. Typed outcomes/reasons cover invalid plan/request identity,
unknown or duplicate proposal IDs, and resource overflow.

A structurally valid plan is not a capability token. Working Memory may expire,
evict, reset, or otherwise lose evidence between prepare and execute. Execution
therefore passes each unchanged request back through
`WorkingMemoryCandidateBridge.stage(...)`. Its typed ineligibility is retained
in that proposal's entry. No request is rewritten, repaired, retried, or
rediscovered, and unrelated eligible proposals continue. If all requested
entries are ineligible the batch outcome is `plan_stale`; a mixed batch is
`review_completed_with_ineligible_entries`.

The selector is still invoked exactly once over the complete successful staging
set, including an empty set when proposals were requested but all became
ineligible. `DEFER` and `REJECT_SELECTION` entries are never evaluated.

## Read-only evaluation and time behavior

The pipeline stores only the evaluator's `evaluate` callable. It does not import
or retain `MemoryService`, a SQLite implementation, or a validation application
surface. Each selected candidate is evaluated once in canonical candidate-ID
order. The exact `ValidationDecision` is retained without reinterpretation:
`ACCEPT_NEW`, `EXACT_DUPLICATE`, `CONFLICT_REVIEW`, `APPLY_CORRECTION`, and
`REJECT` remain Memory Validation descriptions, not write commands.

Evaluation reads current Memory OS state sequentially. Version 1 does not claim
a transaction or serializable snapshot across multiple evaluations. With stable
Memory OS state, identical plan, allowlist, Working Memory state, execution
`now_ns`, and policy versions produce the same semantic batch and IDs.

One caller-provided source-clock `now_ns` is passed unchanged to every staging
attempt. The pipeline never reads wall time. Working Memory public reads may
perform their existing ordinary expiry purge; the pipeline does not ingest,
refresh TTL, extend expiry, or alter retained content.

## Bounds

Version 1 never expands the discovery boundary:

- at most 32 requested proposal IDs;
- at most 32 staging attempts and review entries;
- at most 32 validation evaluations;
- at most 16 review reasons;
- at most 65,536 aggregate discovery/validation lineage characters;
- existing 256-character consolidation identities and 512-character staging
  details; and
- existing World Model JSON depth, node, collection, text, integer, and
  aggregate limits.

Discovery remains capped at 64 inspected evidence envelopes, 32 proposals, and
64 diagnostics. Selection retains its 32-occurrence and aggregate bounds.
Malformed or oversized structures fail closed; overflow output does not retain
partial candidate payloads.

## Semantic, confidence, provenance, and correction guarantees

The orchestrator does not create a candidate. The existing staging bridge alone
derives the observation time, confidence, and provenance from exact retained
evidence. Missing confidence remains undiscoverable/unstageable, genuine `0.0`
remains zero, and the selector alone owns its `0.5` review threshold.

Anonymous visual proposals remain exact robot-subject episodic
`observed_anonymous_person` or `observed_anonymous_object` observations with
normalized region and evidence category where applicable. Evidence, detection,
interpretation, frame, and semantic-item IDs remain provenance identities. The
pipeline cannot create person, owner, object, tracking, preference, social,
relationship, familiarity, routine, emotion, intention, permanence, or scene
absence identity.

Staged provenance remains `DIRECT_OBSERVATION`; it cannot be upgraded to an
owner statement or manual import. Discovery requests contain no correction
target or reason, and the pipeline exposes no field that can add either.

## Deliberate non-goals

- automatic persistence, durable consolidation, learning promotion, autonomous
  learning, rollback, or conflict winner selection;
- automatic discovery schedules, timers, workers, queues, polling, watchers, or
  background invocation;
- confidence synthesis, truth scoring, provenance aggregation, LLM extraction,
  embeddings, fuzzy matching, or vector search;
- Personal Context projection or owner/preference/social updates;
- ROS/network memory service, Runtime, Executive, Safety, Skill, navigation,
  manipulation, or physical movement authority.

## Validation

```bash
PYTHONPATH=memory/src:memory_validation/src:world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src:memory_consolidation/src \
python3 -m pytest -q memory_consolidation/tests
```

Focused coverage proves plan immutability/integrity, explicit caller gating,
stale and partial staging, one-call batch selection, selected-only evaluation,
read-only durable state, deterministic identities, resource bounds, exact
anonymous lineage, and single-/multi-candidate end-to-end behavior.
