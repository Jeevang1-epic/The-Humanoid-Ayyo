# Reviewed Memory Candidate Selection Policy Foundation v1

## Responsibility

`ReviewedMemoryCandidateSelectionPolicy` is the explicit, transport-neutral
review-triage step between an already-constructed `CandidateEvidence` and
`MemoryValidationService.evaluate`. It answers only: “Is this unchanged
candidate suitable to present to the next review/validation stage under policy
version 1?”

Selection is not acceptance as truth. It is not owner approval, learning,
durability, identity evidence, physical-action authority, or permission to
apply a Memory Validation decision.

```text
temporary typed evidence
→ optional explicit bounded discovery returns an exact ConsolidationRequest
→ caller chooses the request
→ explicit ConsolidationRequest
→ WorkingMemoryCandidateBridge.stage
→ CandidateEvidence
→ ReviewedMemoryCandidateSelectionPolicy.select
→ selected / deferred / rejected for review
→ separate caller invokes MemoryValidationService.evaluate
→ separate caller review
→ optional separate caller invokes MemoryValidationService.apply
→ Memory OS
```

The selector is stateless. It retains no Working Memory reference, database,
clock, service, queue, or scheduler, and exposes only `select`.
The earlier
[Bounded Memory Candidate Discovery Policy](MEMORY_CANDIDATE_DISCOVERY.md) may
provide the exact request, but never calls this selector or changes selection
semantics.
The optional
[Controlled Memory Review Pipeline](CONTROLLED_MEMORY_REVIEW_PIPELINE.md) calls
this selector exactly once over all successfully restaged caller-allowlisted
candidates, then evaluates only `SELECT_FOR_REVIEW` items. That orchestration
does not change this policy or give it validation/application authority.

## Public API

- `CandidateReviewItem` snapshots the selection input relationship: one
  immutable `CandidateEvidence` and an optional exact eligible
  `CandidateStagingResult`. `from_staging(...)` is the normal path for direct
  observations.
- `ReviewedMemoryCandidateSelectionPolicy.select(items)` accepts only a list or
  tuple, capped at 32 occurrences, and returns one immutable
  `CandidateSelectionDecision`.
- `CandidateSelectionItemDecision` retains the bounded candidate, deterministic
  candidate ID, typed outcome/reasons, and exact duplicate occurrence count.
- `CandidateSelectionDecision` retains the policy identity/version/fingerprint,
  deterministic selection ID, aggregate outcome/reasons, canonical item order,
  input count, and computed unique/selected/deferred/rejected counts.

`selected_candidates` returns only the original unchanged candidates whose item
outcome is `SELECT_FOR_REVIEW`. The policy cannot construct a new proposition or
change memory type, subject, predicate, value, provenance, confidence,
observation time, metadata, or correction intent.

## Outcomes

- `SELECT_FOR_REVIEW` means only that the candidate clears this bounded
  presentation policy.
- `DEFER` means that confirmation or review is required before the candidate
  can be presented downstream.
- `REJECT_SELECTION` means that the candidate or batch fails this selection
  boundary.

The batch outcome is the most conservative item outcome: reject, then defer,
then select. Unrelated selected items remain available through
`selected_candidates`; consumers must use item outcomes and selected IDs rather
than treating a batch outcome as truth acceptance.

Typed reasons are:

- `eligible_for_review`
- `duplicate_candidate`
- `duplicate_proposition`
- `conflicting_candidate`
- `unsupported_memory_type`
- `source_eligibility_required`
- `low_confidence_for_policy`
- `direct_observation_requires_confirmation`
- `owner_confirmation_required`
- `provenance_requires_confirmation`
- `provenance_not_allowed_for_memory_type`
- `unsupported_provenance`
- `missing_required_confidence`
- `semantic_claim_exceeds_evidence`
- `correction_not_allowed`
- `insufficient_evidence`
- `resource_limit_exceeded`

Reasons are deduplicated and emitted in policy-defined enum order, never set or
input order. A selected item has only `eligible_for_review`; a deferred item has
only deferral reasons; and a rejected item retains at least one rejection
reason.

## Provenance and memory-type policy

Version 1 supports episodic, semantic, preference, social, spatial, and failure
candidates. Procedural candidates are rejected. After the special conservative
handling of derived inference, these provenance combinations are eligible to
continue through the remaining policy checks:

| Memory type | Provenance combinations |
| --- | --- |
| Episodic | direct observation, explicit owner statement, system event, trusted manual import |
| Semantic | direct observation, explicit owner statement, trusted manual import |
| Preference | explicit owner statement, trusted manual import |
| Social | explicit owner statement, trusted manual import |
| Spatial | direct observation, trusted manual import |
| Failure | direct observation, system event, trusted manual import |

All direct observations require the exact eligible staging result for the same
candidate. That reuses the bridge's existing source identity, freshness, clock,
confidence, and semantic-chain checks instead of reading mutable Working Memory
or reimplementing its source-chain validation. A direct episodic observation
can be selected when its subject remains the source robot. Broader direct
semantic/spatial/failure claims or a different subject are deferred for
confirmation. Direct evidence never becomes an owner statement.

Derived inference is never selected in v1. Preference and social inference are
deferred with `owner_confirmation_required`; other inferred memory types use
`provenance_requires_confirmation`. The policy does not infer an owner,
preference, or social relationship while deferring the supplied proposition.

Explicit owner statements and trusted manual imports are inputs supplied under
their existing Memory OS provenance contracts; this policy does not authenticate
an owner or import channel. Authentication remains a separate future boundary.
Corrections are rejected because selection v1 cannot grant destructive
authority.

## Confidence and observation time

The exact review-triage threshold is `MIN_REVIEW_CONFIDENCE = 0.5`. This is a
presentation threshold, not a probability-of-truth claim. A supplied finite
confidence at or above 0.5 can continue; a lower value is deferred. `0.0`
remains exactly zero. `None` cannot pass the existing `CandidateEvidence`
contract, and defensive selection checks reject a malformed missing confidence
rather than synthesizing one.

For bridge-produced direct evidence, the exact eligible staging result already
binds freshness and the reviewed UTC conversion. Other candidates retain the
timezone-aware UTC observation time required by `CandidateEvidence`. The
selector has no current-time input and does not invent a second freshness
window. Observation time remains part of the deterministic candidate identity,
so otherwise equal evidence observed at different instants has different IDs.

## Duplicates and conflicts

Candidate identity is SHA-256 over canonical candidate content: memory type,
original subject/predicate/value, provenance type/source/details, exact
confidence, UTC observation time, metadata, and correction fields.

- Exact candidate-ID duplicates collapse to one item with an occurrence count.
  A base-eligible group is deferred as `duplicate_candidate`; if any occurrence
  already fails closed, the collapsed item conservatively remains rejected.
- Distinct evidence records with the same normalized memory identity and
  canonical value receive `duplicate_proposition`; non-rejected items defer.
- Distinct canonical values for the same normalized memory identity are all
  marked `conflicting_candidate`; non-rejected items defer.

No winner is selected for a duplicate proposition or conflict. Confidence does
not break ties. Candidate IDs and item decisions are explicitly sorted, so
candidate input order does not alter the semantic decision. Existing Memory
Validation remains authoritative for comparison with durable records and its
own duplicate/conflict behavior.

## Anonymous semantic guarantee

An anonymous semantic bridge candidate remains eligible only when its exact
value is the already-staged anonymous episodic observation: robot subject,
`observed_anonymous_person` or `observed_anonymous_object`, `anonymous: true`,
kind, normalized region, and object category when applicable. Source evidence
IDs stay in provenance.

Selection cannot add a person, owner, object, tracking, relationship,
preference, permanence, or scene-absence identity. Object category is not
object identity. The selected candidate is the same immutable
`CandidateEvidence` object that entered the policy.

## Determinism, identity, and bounds

The policy identity is
`ayyo.reviewed-memory-candidate-selection.v1`, its integer version is `1`, and
its fingerprint commits to the provenance matrix, direct/derived/duplicate/
conflict/anonymous/correction behavior, confidence threshold, and bounds.
Selection IDs commit to that fingerprint plus canonical item outcomes, reasons,
candidate IDs, occurrence counts, and input count.

Version 1 hard-bounds:

- 32 candidate occurrences per invocation;
- 16 reasons per item or decision;
- 16 candidate metadata fields;
- 256-character subject, predicate, and provenance-source identities;
- JSON depth 16, 2,048 nodes, 256 items per collection, 4,096 characters per
  text value, and 1,024-bit integers;
- 65,536 measured aggregate content characters across a batch.

The JSON, identity, metadata, and aggregate limits reuse the existing World
Model and consolidation bounds. Cycles, non-JSON data, non-finite numbers,
oversized values, oversized metadata, aggregate overflow, and candidate-count
overflow fail closed. Resource-overflow decisions omit item payloads when
retaining them would violate the batch bound.

## Persistence prohibition and dependency direction

Selection source imports public Memory, Memory Validation model, World Model
bound, and local consolidation contracts. It imports no `MemoryService`,
`SQLiteMemoryStore`, `WorkingMemory`, ROS type, transport, runtime, Personal
Context, Executive, Safety, or action API. Lower packages do not depend back on
selection.

The selector has no `evaluate`, `apply`, create, correct, supersede, retract,
or persistence operation. Focused integration tests prove that typed Perception
evidence can pass through Working Memory, optional explicit discovery, explicit
staging, selection, and read-only Memory Validation evaluation while Memory OS
remains empty. Only the test caller's later explicit
`MemoryValidationService.apply` creates a durable record.

## Deliberate non-goals

- candidate discovery or Working Memory scanning inside the selector, proposition
  generation, LLM extraction, automatic invocation, or scheduled/background
  consolidation;
- truth resolution, confidence synthesis, provenance aggregation, or automatic
  duplicate/conflict winner selection;
- identity, recognition, tracking, preference, social, scene-absence, or object
  permanence inference;
- automatic validation, application, correction, supersession, Personal
  Context mutation, or learning promotion;
- ROS/network services, threads, timers, polling, queues, filesystem watchers,
  navigation, manipulation, motion, or execution authority.

## Validation

```bash
PYTHONPATH=memory/src:memory_validation/src:world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src:memory_consolidation/src \
python3 -m pytest -q memory_consolidation/tests
```

The focused suite covers all outcomes and typed reasons; exact duplicates,
equivalent propositions, conflicts, and order independence; policy/candidate/
selection identities; exact threshold, zero, and missing confidence; anonymous
person/object preservation; no owner/preference/social or correction authority;
input immutability; structural and aggregate resource failures; package
direction; and the explicit evidence-to-evaluate integration seam.
