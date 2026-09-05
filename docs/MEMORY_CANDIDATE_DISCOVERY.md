# Bounded Memory Candidate Discovery Foundation v1

## Responsibility

`BoundedMemoryCandidateDiscoveryPolicy` is a caller-triggered, stateless read of
currently retained Working Memory evidence. It answers only:

> Which exact retained evidence items can support one exact, deliberately narrow
> consolidation request under discovery policy version 1?

Discovery is not learning, truth acceptance, review selection, validation, or
persistence. It returns proposals; a caller decides whether any proposal should
be passed to the unchanged staging bridge.

The optional controlled review pipeline may invoke this exact operation once
during an explicit caller `prepare` call. It snapshots the result and still
requires a second caller action with an exact proposal-ID allowlist before any
staging or evaluation.

```text
typed Perception evidence
→ bounded Working Memory
→ caller invokes discover(working_memory, now_ns=...)
→ immutable CandidateDiscoveryResult
→ caller chooses one CandidateDiscoveryProposal.request
→ caller separately invokes WorkingMemoryCandidateBridge.stage
→ caller separately invokes reviewed selection
→ caller separately invokes Memory Validation evaluation
→ optional caller-explicit apply
→ Memory OS
```

## Public API and policy identity

- `BoundedMemoryCandidateDiscoveryPolicy` has no mutable state and exposes
  `discover(working_memory, *, now_ns)`.
- `CandidateDiscoveryProposal` retains the exact immutable
  `ConsolidationRequest`, deterministic proposal ID, and policy identity.
- `CandidateDiscoveryResult` retains canonical proposals, typed bounded
  diagnostics/reasons, inspected/retained counts, outcome, deterministic result
  ID, and policy identity.
- The policy ID is `ayyo.memory-candidate-discovery.v1`, version `1`, with a
  deterministic fingerprint of its reviewed rules and public bounds.

No proposal contains `CandidateEvidence`; staging remains the sole operation
that derives candidate time, confidence, and `DIRECT_OBSERVATION` provenance.

## Supported evidence and exact propositions

Version 1 supports only retained `SemanticEvidenceObservation` items whose full
frame → interpretation → detection source chain is still exact and available.
All other observation families receive `unsupported_evidence_kind` diagnostics.

An anonymous person item produces only:

```text
memory_type: episodic
subject: <Working Memory robot_id>
predicate: observed_anonymous_person
value: {anonymous: true, kind: person, region: <exact normalized region>}
```

An anonymous object item produces only:

```text
memory_type: episodic
subject: <Working Memory robot_id>
predicate: observed_anonymous_object
value: {anonymous: true, kind: object, region: <exact normalized region>,
        category: <exact evidence category>}
```

The exact semantic observation ID/fingerprint, provenance source ID, and
semantic-item ID become the request's one `EvidenceReference`. Metadata is empty.
Category is observation content, not an object identity. Evidence, detection,
frame, interpretation, and semantic-item IDs are provenance—not person, owner,
or object identities.

## Eligibility

Discovery only emits requests capable of satisfying the existing staging
eligibility contract:

- every retained envelope fits the per-call evidence bound and reconstructs to
  its canonical immutable identity;
- retained observation identities are unique;
- the robot and provenance exactly match Working Memory configuration;
- the configured and observed clock is exactly `ROS_SYSTEM_TIME`;
- evidence is not future-dated, remains fresh, and has not expired or crossed a
  reset epoch;
- source nanoseconds divide exactly by 1,000 and therefore convert to UTC without
  losing precision;
- the full semantic frame/interpretation/detection chain remains exact;
- the semantic item contains real confidence.

Confidence is never synthesized. `None` produces a
`missing_required_confidence` diagnostic and no proposal. A real `0.0` remains
eligible for proposal construction and later stages as exactly zero; discovery
does not apply the selection policy's separate review threshold.

Calling `discover` performs the normal public Working Memory source-time read,
including ordinary expiry purging. It does not ingest, rewrite, refresh TTL,
change counters, or retain a Working Memory reference. It never uses wall-clock
time or relabels simulation, test, recorded, or monotonic time as UTC.

## Determinism, duplicates, and bounds

Proposal identity hashes only the policy fingerprint, canonical proposition,
metadata, and exact evidence reference. Result identity hashes only canonical
output and counts. Storage iteration order, process state, filesystem, machine,
randomness, and wall-clock time do not affect either identity.

Only equal proposal identities are deduplicated; there is no fuzzy or semantic
deduplication and no provenance aggregation. A non-unique retained observation
identity fails closed because the unchanged staging bridge would also reject
that evidence selection as ambiguous.

Hard version-1 limits are:

- 64 retained evidence envelopes per call; an oversized retained set yields no
  scan and a resource-limited result;
- 32 returned proposals;
- 64 returned diagnostics;
- 16 unique aggregate reasons;
- 16 request metadata fields (discovery emits none);
- 256 characters per consolidation identity field;
- World Model JSON limits: depth 16, 2,048 nodes, 256 collection entries, 4,096
  characters per text value, 65,536 aggregate characters, and 1,024-bit integers.

Proposal and diagnostic overflow is resolved by canonical order, with an
explicit `resource_limit_reached` outcome/reason.

## Outcomes and reasons

Outcomes are `proposals_discovered`, `no_discoverable_proposals`,
`discovery_ineligible`, and `resource_limit_reached`.

Typed reasons are `discoverable`, `no_retained_evidence`,
`unsupported_evidence_kind`, `missing_required_confidence`, `unsupported_clock`,
`evidence_stale`, `evidence_time_in_future`, `wrong_robot`,
`provenance_not_allowed`, `invalid_source_chain`,
`timestamp_not_utc_convertible`, `proposition_not_safely_derivable`,
`resource_limit_reached`, `source_clock_regression`, `invalid_discovery_time`,
and `invalid_retained_evidence`. Reasons and diagnostics are deduplicated and
canonically ordered; internal exception strings are not part of policy output.

## Deliberate non-goals

- background/scheduled discovery, staging, selection, validation, apply,
  persistence, durable consolidation, learning, or promotion
- identity/owner recognition, tracking, facial/biometric processing, person or
  object identity, ownership, relationships, familiarity, habit, routine,
  intention, emotion, preference, or social inference
- scene-absence, negative-detection, complete-scene, or object-permanence claims
- corrections, provenance/authority upgrades, Personal Context updates,
  Executive/Safety/Skill integration, ROS memory services, motion, navigation,
  or manipulation
- language models, prompts, text generation, embeddings, semantic similarity,
  fuzzy matching, vector search, databases, caches, queues, workers, or timers

## Validation

```bash
PYTHONPATH=memory/src:memory_validation/src:world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src:memory_consolidation/src \
python3 -m pytest -q memory_consolidation/tests
```

Focused tests prove deterministic exact person/object proposals, immutable
request snapshots, source identity, clock/time/freshness/reset/expiry behavior,
confidence `None`/`0.0`, source-chain and corruption failure, canonical ordering,
deduplication and bounds, semantic non-inference, package direction, read-only
behavior, and explicit end-to-end compatibility through evaluation and apply.
