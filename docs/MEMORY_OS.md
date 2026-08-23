# Memory OS Core

## Responsibility and boundary

The Memory OS is the authoritative local persistence boundary for developmental,
owner-specific knowledge. It stores evidence-backed memory records and their
history; it is not a chat log, a reasoning engine, or a source of motor commands.
A fresh database contains schema metadata but no owner autobiographical memory.

The core is a standalone Python package with no ROS 2, model, cloud, or external
database dependency. A future ROS memory bridge will adapt its public API without
moving ROS concerns into the domain or persistence layers.

## Domain records

Each memory has a UUID, category, subject, predicate, JSON-compatible value,
mandatory provenance, confidence from `0.0` through `1.0`, UTC observation and
creation timestamps, lifecycle status, and optional JSON-compatible metadata.
Supported categories are episodic, semantic, preference, social, spatial,
procedural, and failure. Categories are stored as text so future additions do not
require a persistence rewrite.

Provenance distinguishes explicit owner statements, direct observations, derived
inferences, system events, and trusted manual imports. It includes a stable source
identifier and optional structured source details. The core preserves this
information but does not implement a general trust-scoring system.

## Revisions and retractions

Memory content is never corrected in place. An explicit correction transaction:

1. marks the active target as superseded;
2. inserts a new active record linked through `supersedes`;
3. retains the reason for preferring the revision; and
4. updates conflict relationships.

Only an explicit owner statement or trusted manual import can be submitted as a
correction. Other evidence remains non-destructive. Any failure rolls back the
entire correction. Retraction similarly keeps the record and its reason while
excluding it from active retrieval. Ordinary operations never physically delete
memory history.

## Contradictions

Different active values for the same memory category, subject, and predicate are
stored as separate records with an explicit conflict relationship. Neither record
is silently chosen. Corrections resolve applicable historical conflicts; any
remaining contradictory active evidence is exposed as an unresolved conflict.
For this version, category, subject, and predicate are exact storage-layer identity
fields. The separate deterministic Memory Validation policy performs conservative
Unicode and whitespace normalization before new writes. Semantic entity resolution
remains unimplemented.

## Persistence and retrieval

SQLite provides local durability with foreign keys enabled, WAL journaling,
`FULL` synchronous writes, a five-second busy timeout, explicit transactions, and
a versioned schema. WAL allows readers to proceed while a writer commits; full
synchronization prioritizes durable local memory over write throughput. Database
paths are supplied by callers. Project-local runtime databases should be placed
under `memory/runtime/`, which is ignored together with WAL and SHM sidecars.
While a WAL-mode database is live, copying only its main `.sqlite3` file is not a
safe backup or export procedure because committed data may still be in the WAL
sidecar. This core does not provide a backup or export API.

Retrieval is exact and deterministic by memory ID, category, subject, predicate,
or subject/predicate pair. Queries return active records by default. Callers must
explicitly request historical records, revision chains, resolved conflicts, or
unresolved conflicts. Records retain confidence and provenance in every result.

## Intentionally not implemented

- Personal Cognitive Twin behavior
- Probabilistic truth selection, provenance aggregation, or destructive consolidation
- Semantic or vector search, embeddings, and model integrations
- ROS 2 messages, services, actions, or a memory bridge
- Perception, cognition, permissions, safety runtime, or robot behavior
- Hard deletion, retention policy, and privacy-deletion workflows
