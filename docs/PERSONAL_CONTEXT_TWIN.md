# Personal Context Twin v1

## Purpose

The Personal Context Twin (PCT) is Ayyo's deterministic, owner-centric read
model over Memory OS. It turns active owner memories and unresolved conflicts
into an immutable, evidence-backed snapshot that later executive systems can
inspect without learning Memory OS persistence details.

Memory OS remains authoritative. The PCT has no database, cache, mutation API,
ROS 2 dependency, model call, or network path. It does not infer new facts,
normalize identities, rank competing evidence, or decide what is true.

## Layer boundary

The implemented flow is:

```text
candidate evidence
→ Memory Validation
→ Memory OS
→ Personal Context Twin
→ Executive Cognition proposals
→ Immutable Safety Kernel decisions
→ future identity / approval and Skill Manager
```

The PCT package imports only the public `ayyo_memory` API. Its runtime does not
import the SQLite store or schema and never calls Memory OS create, correct, or
retract operations. Memory Validation continues to own candidate admission and
correction authority. Memory OS continues to own identity, active state,
revision history, retraction, and conflict truth.

## Owner and identity boundary

`PersonalContextService` is constructed with one explicit `owner_subject`. That
text is passed as the exact Memory OS subject filter for both source reads. Every
projected entry repeats that owner subject, making the boundary auditable.

Identity is exactly `(memory_type, subject, predicate)`, matching Memory OS.
The PCT does not lowercase, trim, collapse internal whitespace, apply Unicode
normalization, fuzzy-match, or reuse Memory Validation's candidate-normalization
rules. For example, `owner`, `Owner`, and `owner profile` are different
subjects; `preferred_drink` and `preferred  drink` are different predicates.
Surrounding whitespace is rejected because Memory OS rejects it.

Other-person context is never projected as an independent twin. A social memory
is included only when its Memory OS subject is the configured owner. The value
may explicitly identify another party when the owner-context relationship needs
to represent one.

## Context domains

PCT v1 maps these Memory OS types directly:

| Memory OS type | PCT domain | Intended representation |
| --- | --- | --- |
| `semantic` | `semantic` | Factual, persona, and temporal owner state |
| `preference` | `preference` | Owner preferences |
| `social` | `social` | Owner-centric relationships and social context |
| `spatial` | `spatial` | Owner-centric spatial context |
| `procedural` | `procedural` | Owner procedures and routines |

`episodic` is excluded from v1. Selecting, bounding, or summarizing episodes
would require temporal projection policy that has not yet been specified.
`failure` is also excluded because it records system/task failure evidence, not
personal owner context. Changes confined to either excluded category do not
change a PCT snapshot version.

## State semantics

Each present exact identity becomes one `ContextEntry`:

- `RESOLVED`: one distinct canonical JSON value is active. Multiple equivalent
  active records collapse into that one value while retaining every evidence
  reference.
- `CONFLICTED`: two or more distinct canonical JSON values are active and Memory
  OS reports the corresponding unresolved conflicts. Every competing value and
  conflict identifier remains visible.
- `UNKNOWN`: no active record exists for a query. Unknown is returned as a typed
  query result with no fabricated entry or placeholder value.

Canonical JSON comparison preserves type distinctions such as `false` versus
`0` and `1` versus `1.0`; only object key order is irrelevant. Conflict state is
never resolved by confidence, recency, insertion position, UUID ordering, or
provenance rank. Missing or inconsistent conflict information raises
`InconsistentSourceStateError` instead of choosing a winner.

Corrections, retractions, and conflict resolutions appear through Memory OS
active state. Only active revisions are projected. Each active evidence
reference includes its stable Memory OS `memory_id`; corrections also carry the
direct `supersedes` reference and revision reason, so callers can request the
complete history from Memory OS without the PCT copying database rows.

## Immutable public models

The public model consists of:

- `PersonalContextSnapshot`
- `ContextEntry`, `ContextIdentity`, and `ContextValue`
- `EvidenceReference`
- `ContextState` and `ContextDomain`
- `ContextQueryResult`
- `ContextSnapshotVersion`

Models are frozen and use tuples for collections. JSON values, provenance
details, and record metadata are copied on input and copied again when returned,
including deeply nested list/dictionary structures. A consumer mutating a
returned value cannot change the snapshot or Memory OS.

## Snapshot versions

Every snapshot has a `sha256` version under schema version 1. The digest covers
a canonical JSON document containing:

- the exact configured owner subject;
- sorted context identities and explicit states;
- sorted canonical values;
- sorted Memory OS evidence identifiers and their exposed provenance, metadata,
  and revision fields; and
- sorted unresolved conflict identifiers.

Ordering is defined explicitly. No wall clock, random value, construction time,
or iteration order enters the digest. Rebuilding from identical relevant source
state therefore returns an equal snapshot and version. A relevant owner-context
change changes the version; changes to another owner or an excluded memory type
do not. The digest is a deterministic change token, not proof of authenticity,
authorization, trust, or safety.

## Read consistency

A snapshot uses the minimum public Memory OS reads that expose the required
state:

1. one active-memory query filtered by the exact owner subject;
2. one unresolved-conflict query filtered by the same subject.

Memory OS does not currently expose an atomic transaction spanning those two
public reads. The projector detects many torn-read states: inactive records in
the active set, conflicts referencing absent or mismatched records, equivalent
values marked conflicted, missing conflict pairs, duplicate IDs, and
cross-identity conflicts all fail visibly.

Some concurrent transitions cannot be detected through the existing API. For
example, a single non-conflicting record can be added, corrected, or retracted
between the reads while the earlier active-memory result remains internally
coherent. In that case the PCT can return a coherent snapshot of the earlier
read, not an atomic point-in-time view. Consumers should build close to use and
compare versions when coordinating longer work. A future atomic Memory OS read
contract could remove this limitation without changing projection policy.

The PCT is not a hidden long-lived cache. Every service operation builds from
fresh public Memory OS reads; a `PersonalContextSnapshot` is an explicit,
immutable value that a caller may retain deliberately.

## Public usage

```python
from ayyo_personal_context import ContextDomain, PersonalContextService

context = PersonalContextService(memory_service, owner_subject="owner")
snapshot = context.build_snapshot()
drink = snapshot.get_context(ContextDomain.PREFERENCE, "preferred_drink")

print(snapshot.owner_subject)
print(snapshot.version)
print(drink.state)
```

`PersonalContextService.get_context(...)` is a convenience that builds a fresh
snapshot before querying. `snapshot_version()` similarly returns the version of
a freshly built snapshot. Known query results expose the complete entry, values,
evidence references, and conflict IDs needed to explain the projection.

## Failure behavior

Invalid owners and queries raise typed PCT validation errors. Impossible model
states raise `ContextInvariantError`. Incoherent Memory OS read pairs raise
`InconsistentSourceStateError`. Memory OS operational failures, including a
closed or unavailable store, propagate unchanged; the PCT does not broadly
catch, suppress, or convert them into empty/unknown context.

## Deliberately out of scope

PCT v1 does not provide:

- inferred personality, beliefs, intent, emotion, or psychological claims;
- vector search, embeddings, probabilistic scoring, model-generated summaries,
  or automatic conflict resolution;
- permissions, identity authentication, action authorization, executive
  reasoning, planning, or safety decisions;
- autonomous refresh, event subscriptions, persistence, caching, or historical
  snapshot storage;
- ROS messages, robot commands, or hardware integration.

These omissions are intentional boundaries, not implicit capabilities.

PCT v1 reads the complete active owner set for supported domains because the
public Memory OS API does not provide a cross-query snapshot cursor or a
projection budget. Episodic history is excluded, but a very large active
non-episodic set still increases memory use, fingerprint cost, and the pairwise
conflict-consistency check. Pagination or bounded partial context would require
an explicit completeness contract before it could be added safely.

## Validation

Run the standalone package tests with:

```bash
PYTHONPATH=memory/src:personal_context/src \
python3 -m unittest discover -s personal_context/tests -v
```

The suite covers empty and unknown state, every included category, explicit
exclusions, equivalent evidence, unresolved contradictions, corrections,
retractions, conflict resolution, owner isolation, exact identity boundaries,
deterministic ordering and versions, source inconsistency, mutation resistance,
deep JSON, dependency failure, repeat reads, public imports, and wheel contents.
