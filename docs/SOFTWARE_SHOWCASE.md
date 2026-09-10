# Software Showcase Foundation v1

## Purpose and status

Stage 8 provides one deterministic, bounded way to inspect what Ayyo's
reviewed software currently exposes. The standalone distribution is
`ayyo-software-showcase`; its public module is `ayyo_software_showcase`, and its
developer command is `ayyo-showcase`.

The showcase is an evidence inventory, not a robot runtime. It derives the
reviewed catalog from imported public contract identities and versioned schema
constants where those packages expose them. It emits immutable content-addressed
manifests and reports. It neither invokes the represented operations nor treats
the existence of a contract as proof of runtime execution.

## Dependency and authority boundary

The showcase is a top-level read-only consumer:

```text
reviewed public Ayyo contracts
  → closed software-showcase catalog
  → immutable manifest
  → pure evidence checks
  → immutable report or developer inspection output
  → stop
```

It imports only reviewed public Python interfaces. Existing perception, memory,
cognition, Safety, Skill Manager, Runtime Bridge, simulation, scenario, and
Stage-7 learning packages do not import the showcase. ROS packages do not import
it either.

The package owns no cognition, Safety policy, skill selection, runtime binding,
transport, policy state, authentication, persistence, simulation, ROS, or
hardware authority. Its CLI has no operation that starts another subsystem.

## Public contracts

- `ShowcaseEvidenceReference` identifies one imported public contract, its
  module and public symbol, optional exact schema identity/version, and explicit
  provenance reference/fingerprint.
- `ShowcaseCapability` binds a stable ordered capability claim to one or more
  exact evidence identities, truthful classifications, and explicit
  `does_not_prove` values.
- `ShowcaseManifest` contains the complete closed v1 catalog and unique evidence
  inventory. Every evidence reference must be used; every claimed evidence ID
  must resolve exactly.
- `ShowcaseCheck` binds one capability fingerprint and its exact evidence set to
  either `SUPPORTED_BY_PUBLIC_CONTRACT` or `EXPLICITLY_UNAVAILABLE`.
- `ShowcaseReport` embeds the complete manifest and exactly one ordered check per
  capability. Verification regenerates the authoritative report from the live
  reviewed catalog.

All contracts are frozen, slot-backed, bounded, and content-addressed. Caller
sequences are copied before validation.

## Truthful classifications

Every capability has exactly one primary state: `IMPLEMENTED` or
`NOT_YET_IMPLEMENTED`. Additional labels preserve the evidence context:
`TEST`, `SIMULATION`, `DEVELOPMENT_ONLY`, `INERT_EVIDENCE_ONLY`, and
`NOT_PHYSICALLY_VALIDATED`.

`IMPLEMENTED` means the cited software contract exists in the reviewed public
catalog. It does not mean that every planned behavior exists or that the
showcase executed the contract. `SUPPORTED_BY_PUBLIC_CONTRACT` has the same
narrow meaning.

The reviewed catalog contains these areas:

| Capability | Truthful classification |
| --- | --- |
| Perception and sensor evidence foundations | implemented; TEST/simulation; not physically validated |
| World Model and Working Memory | implemented temporary software state |
| Bounded memory candidate and review flow | implemented; inert evidence-only |
| Personal Context, Executive, and Safety | implemented separate decision boundaries; inert here |
| Skill Manager and Runtime Bridge eligibility | implemented; inert evidence-only |
| ROS/Gazebo simulation foundations | implemented simulation and DEVELOPMENT-only contracts; not physical validation |
| Developmental scenario harness | implemented TEST/simulation/DEVELOPMENT-only manifest |
| Teach Mode demonstration evidence | implemented TEST evidence; inert |
| Offline candidate-policy evaluation | implemented TEST/offline evidence; inert |
| Promotion and rollback eligibility | implemented; inert eligibility only |
| Immutable policy registry/version lineage | implemented; inert records only |
| Human/authority approval evidence | implemented caller-supplied evidence; not authentication |
| Future-activation eligibility | implemented; inert eligibility only |
| Production policy activation | not yet implemented |
| Physical hardware validation | not yet implemented and not physically validated |

The last two entries are deliberately present. Unavailable capabilities are not
omitted or implied by future architecture arrows.

## Evidence integrity

The built-in catalog is assembled from actual imported public classes. Schema
IDs and versions are taken from the owning public modules where available.
Evidence reference fingerprints bind the public module, symbol, schema pair,
and provenance. Capability fingerprints bind exact evidence IDs,
classifications, non-claims, text, and declared sequence.

Generic structurally valid objects cannot replace the reviewed built-in catalog
for report generation or canonical publication. Unknown capability claims,
valid-but-unrelated evidence substitution, duplicate capabilities/evidence,
reordered evidence, modified provenance, altered classifications, and forged
report outcomes fail closed.

## Developer interface

After installing the package and its reviewed local dependencies:

```bash
ayyo-showcase list
ayyo-showcase inspect future-activation-eligibility
ayyo-showcase report
ayyo-showcase verify
```

`list` and `inspect` provide concise human-readable output. `inspect` shows the
public contract and provenance behind the claim plus explicit non-claims.
`report` emits compact canonical JSON. `verify` recomputes the manifest and
report identities from the current imported public interfaces.

Equal repository interfaces and inputs produce byte-identical manifest/report
JSON and identical CLI output. No wall time, host, process ID, path, random UUID,
network state, ROS graph state, or hardware state enters semantic identity.

## Resource and serialization boundary

Version 1 allows at most 32 capabilities, 64 evidence references, 16 evidence
references per capability, 8 classifications per capability, and 16 explicit
non-claims per capability. Evidence, capability, check, manifest, and report
artifacts each have independent canonical UTF-8 byte bounds; the largest report
bound is 524,288 bytes.

Canonical parsing rejects malformed UTF-8/JSON, duplicate keys, non-finite
constants, noncanonical representation, unknown or missing fields, unknown
schemas/versions/enums, invalid identities, duplicate or dangling evidence,
resource overflow, changed ordering, nested tampering, and reconstructed
identity differences. Pathological surrogate, integer, and nesting inputs are
normalized into typed fail-closed errors.

## What this proves

- the reviewed public contract catalog can be imported and identified;
- capability claims preserve exact evidence identity and provenance;
- TEST, simulation, DEVELOPMENT-only, inert, unavailable, and unvalidated states
  remain machine-readable and visible to a reviewer;
- the report is deterministic, bounded, canonical, and independently
  regenerable from the same catalog; and
- the showcase dependency direction remains one-way.

## What this does not prove

The showcase does not prove or perform:

- production perception, complete scene knowledge, or physical sensor quality;
- physical mechanics, dynamics, contacts, balance, motion safety, or hardware;
- human, owner, teacher, or authority authentication;
- memory persistence beyond the separately owned Memory OS;
- model loading, inference, training, or automatic learning;
- automatic promotion, rollback, installation, or activation;
- active/latest policy state or policy execution;
- Executive action, Safety certification, Skill execution, Runtime dispatch, or
  ROS/Gazebo command execution; or
- physical-safety certification or a Safety bypass.

In particular, future-activation eligibility is not activation, an eligible
policy is not installed, Runtime eligibility is not dispatch, simulated motion
is not physical validation, and DEVELOPMENT-only evidence is not production
authority.

## Focused validation

From the repository root with the reviewed source packages on `PYTHONPATH`:

```bash
python3 -m pytest -q software_showcase/tests
python3 -m ayyo_software_showcase.cli verify
```

The focused suite covers deterministic output, classifications, exact evidence
and provenance, duplicates, substitutions, unknown capabilities, canonical
round trips, resource failures, CLI behavior, wheel contents, dependency
direction, and the absence of execution/authority APIs. It does not start or
revalidate ROS/Gazebo.
