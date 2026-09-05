# Memory Validation and Consolidation Policy

## Responsibility and boundary

The deterministic Memory Validation and Consolidation Policy is the admission
layer for candidate long-term evidence. It normalizes conservative identity
fields, compares candidates with active Memory OS records, explains a typed policy
decision, and applies only decisions that explicitly permit persistence.

The Memory OS remains the authoritative persistence boundary. This package calls
only the public `ayyo_memory` domain and `MemoryService` API. It does not import
SQLite implementation modules, own a database transaction, or reproduce conflict
and revision persistence.

## Data flow

```text
Candidate evidence selected for review by an explicit upstream caller/policy
→ immutable candidate snapshot
→ conservative normalization
→ active Memory OS state read through MemoryService
→ deterministic policy decision
→ caller review
→ optional explicit apply
→ MemoryService create_memory or correct_memory
→ authoritative Memory OS transaction
```

Evaluation is read-only. Persistence occurs only through
`MemoryValidationService.apply(decision)`.

The separate
[Bounded Memory Candidate Discovery Policy](MEMORY_CANDIDATE_DISCOVERY.md) can
explicitly return bounded exact `ConsolidationRequest` proposals from currently
retained anonymous visual evidence without constructing `CandidateEvidence`.
The separate
[Working Memory Candidate Bridge](WORKING_MEMORY_CONSOLIDATION.md) can produce
one `CandidateEvidence` from an explicit proposition and exact fresh retained
evidence. The separate
[Reviewed Memory Candidate Selection Policy](REVIEWED_MEMORY_CANDIDATE_SELECTION.md)
can decide whether unchanged candidates are suitable to present here. The
separate [Controlled Memory Review Pipeline](CONTROLLED_MEMORY_REVIEW_PIPELINE.md)
can explicitly coordinate discovery, caller-approved restaging, one batch
selection, and selected-only calls to `evaluate` through a narrow protocol. It
cannot call `apply` or write Memory OS. None changes this package's dependency
direction, and selection for review remains distinct from a Memory Validation
acceptance decision.

## Public records and API

`CandidateEvidence` contains a memory category, original subject and predicate,
JSON-compatible value, provenance, confidence, UTC observation timestamp, optional
metadata, and optional correction intent. Mutable input is snapshotted. Accessors
for values, metadata, and provenance return independent copies.

`MemoryValidationService` exposes three operations:

- `normalize(candidate)` returns a `NormalizedCandidate` and
  `NormalizedIdentity`;
- `evaluate(candidate)` returns an auditable `ValidationDecision` without writing;
- `apply(decision)` re-evaluates current state and returns an `ApplicationResult`.

Every decision contains a typed decision and reason code, normalized identity,
the candidate snapshot with provenance and confidence, deterministically ordered
memory and conflict IDs, a persistence-permission flag, and scalar explanatory
metadata.

Decision construction enforces the policy's structural invariants: decision types
must use compatible reason codes and persistence permissions, the normalized
identity must derive from the candidate, correction decisions must retain their
target and authority, and explanatory metadata must match policy version 1. Facts
that require persistent state, such as whether a referenced record is still active,
are checked again by `apply` rather than trusted from the decision object.

## Normalization version 1

Subject and predicate identity fields use Unicode NFC normalization, removal of
leading and trailing whitespace, and collapse of internal Unicode whitespace runs
to one ASCII space. Case is preserved. Source identifiers and JSON string values
are not normalized.

JSON values are validated without recursive traversal failure and serialized with
sorted object keys, stable separators, UTF-8 text preservation, and non-finite
numbers disabled. Object order therefore does not affect equality. Array order,
number representation, string case, whitespace inside string values, and all
other value semantics remain significant.

The original subject and predicate remain present on the candidate and decision.
Applied records include original and normalized identity fields, policy version,
decision, and reason code under the reserved `ayyo_memory_validation` metadata
key.

## Decisions

- `ACCEPT_NEW`: no active memory has the canonical identity; persistence is allowed
  only through explicit apply.
- `EXACT_DUPLICATE`: an equivalent canonical value is already active; application
  is a no-op.
- `CONFLICT_REVIEW`: a different active value exists; explicit apply may preserve
  it as an unresolved conflict.
- `APPLY_CORRECTION`: an authorized explicit correction targets an active memory;
  persistence is allowed only through explicit apply.
- `REJECT`: correction target or authority policy failed; persistence is prohibited.

A canonical identity variant that cannot be represented by the Memory OS exact
storage identity is returned as `CONFLICT_REVIEW` with persistence prohibited.
This prevents the validation layer from creating a contradiction that the current
Memory OS schema could not link as a conflict.

## Duplicate and consolidation behavior

Against a stable current state, repeated equivalent evidence produces
`EXACT_DUPLICATE` and does not add another long-term record. Applying a duplicate
decision is idempotent. Reapplying a previously successful new, conflict, or
correction decision also detects the resulting equivalent active record and
performs no second mutation.

The candidate's new provenance remains inspectable in the decision. It is not
merged into the existing memory because Memory OS version 1 stores one provenance
object per record. Provenance aggregation would require a separately reviewed
schema and policy extension; v1 does not discard or overwrite stored provenance to
simulate consolidation.

## Contradictions and correction authority

A different value for the same canonical identity produces `CONFLICT_REVIEW`.
Evaluation never selects a winner, regardless of confidence. When the storage
identity is exact and a caller explicitly applies the decision, the candidate is
created through `MemoryService`; Memory OS keeps both records active and creates
the unresolved conflict.

Only explicit owner statements and trusted manual imports may request destructive
correction. Direct observations, derived inferences, and system events receive a
typed rejection when submitted as corrections. They may instead be evaluated and
explicitly persisted as non-destructive contradictory evidence.

Corrections use `MemoryService.correct_memory`, retaining the Memory OS atomic
supersession, replacement, history, provenance, and conflict behavior. Missing,
inactive, or logically mismatched correction targets are rejected.

## Evaluation, application, and stale state

Apply re-evaluates the candidate immediately against current active memory and
unresolved conflicts. Changes to relevant memory IDs, conflict IDs, counts,
correction-target state, reason, or permission raise `StaleDecisionError`. If an
equivalent active value appeared, apply explicitly reclassifies the outcome as an
`EXACT_DUPLICATE` no-op. It does not turn one mutating decision into another.

The read/evaluate and write operations are not one cross-package transaction.
Concurrent writers can change state after the final re-evaluation and before the
Memory OS call. Corrections remain protected by Memory OS's transactional active-
target check, and creates use Memory OS's actual transaction-time conflict state.
That preserves persistence integrity, but it is not a serializable compare-and-
write guarantee for the pre-write decision classification. Deployments requiring
that stronger guarantee must coordinate writers outside policy version 1. In
particular, two equivalent creates that both pass their final read before either
writes can both be stored; they remain intact evidence records, but policy version
1 cannot consolidate that race without a Memory OS compare-and-write API.

## Intentionally not implemented

- Semantic or entity understanding beyond conservative text normalization
- Global case folding, fuzzy matching, embeddings, or vector retrieval
- Probabilistic truth selection, confidence-based winner selection, or trust scores
- Provenance aggregation or destructive duplicate consolidation
- Automatic application of review decisions
- Automatic Working Memory scanning or candidate-discovery/selection-policy
  invocation, staging evaluation, or durable-memory promotion (explicit bounded
  discovery is implemented in the separate `memory_consolidation/` package)
- Models, network services, cloud storage, or external databases
- Personal Context Twin projection or owner-model behavior (the deterministic
  projection is implemented in the separate `personal_context/` package)
- ROS 2 memory bridge or other ROS 2 integration
- Perception or execution of Executive Cognition proposals (proposal planning is
  implemented in the separate `executive/` package)
- Immutable proposal safety review (implemented in the separate
  `safety_kernel/` package), physical safety, or skills
- Learning pipeline
- Simulation robot behavior or physical robot control
