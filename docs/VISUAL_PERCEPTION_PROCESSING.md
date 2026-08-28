# Visual Perception Processing Foundation v1

## Scope

Ayyo now has a transport-neutral seam for bounded visual interpretation after
camera-frame admission. It proves how a future reviewed processor can attach
semantic evidence to one exact trusted RGB frame without putting a model,
pixels, ROS, Gazebo, network clients, persistence, or execution authority into
the core packages.

```text
standard Image + CameraInfo
→ exact camera normalization
→ admitted pixel-free VisualFrameObservation
→ explicitly enabled interpretation producer
→ typed VisualInterpretationObservation
→ existing Perception Trust Boundary
→ bounded Working Memory
→ immutable World Model projection
→ fixed read-only body-state query
```

No production machine-learning perception is implemented. The only executable
producer is an explicitly synthetic deterministic reference adapter for tests.
It is disabled by default and must not be represented as object detection AI.

## Core contracts

`VisualInterpretationProducer` pins an exact producer ID, producer kind, model
ID, adapter ID, and interface ID. A trust configuration admits only exact
producer records from its allowlist; matching only the text producer ID is not
enough.

`ImageRegion2D` uses one explicit coordinate system:
`normalized_image`. Coordinates are finite values in `[0, 1]`; left/top are
inclusive and right/bottom are exclusive. The rectangle must have positive
width and height and remain inside the image. Negative zero is canonicalized to
positive zero before identity derivation.

`VisualDetection` contains the exact source-frame ID, a typed semantic
category, one bounded canonical label, one normalized typed image region,
optional confidence, and a deterministic content-derived detection ID.
Confidence is absent unless a producer actually supplies it. When present it
must be finite and within `[0, 1]`. `None` is not serialized as an invented
zero confidence.

`VisualInterpretationObservation` contains the canonical robot and RGB camera,
exact optical/reference frame, source-frame ID and typed fingerprint, unchanged
source acquisition time, separate result time, exact producer, bounded
canonical detections, source provenance, availability, and a deterministic
typed fingerprint and observation ID.

There is no generic metadata dictionary or arbitrary JSON extension point.
Equivalent detection order and negative-zero geometry have the same semantic
identity. Receipt time is not part of the fingerprint. Processing does not
rewrite the source-frame identity or acquisition timestamp.

## Bounds

| Resource | Bound |
| --- | ---: |
| Detections in one interpretation | 32 |
| Detection label characters | 64 |
| Each producer/model/adapter/interface identifier | 128 |
| Configured interpretation producers | 16 |
| Trust-boundary admitted source-frame references | 64 |
| Per-camera/per-producer current Working Memory result | 1 |
| Default Working Memory recent evidence | 256 |
| Maximum configured recent evidence | 4,096 |
| Default source freshness | 500 ms |
| Default source retention TTL | 2 s |
| Default permitted future skew | 50 ms |

Source-frame references use deterministic oldest-acquisition-time then
observation-ID eviction. Working Memory uses replacement for the current
camera/producer key and its existing bounded recent-evidence capacity. Exact
duplicates do not append recent evidence or grow current state. No raw pixel
buffer, image archive, all-time ID set, durable telemetry, or background queue
is introduced.

The adversarial fixture admitted 1,000 sequential frame/result pairs and ended
with 64 retained trust references, 16 recent observations under its deliberately
small test capacity, one current frame, and one current interpretation. Valid
evidence remained usable after rejected traffic.

## Trust and failure semantics

Interpretations pass through the existing `PerceptionTrustBoundary`; there is
no competing visual trust system. The boundary reconstructs canonical identity
and then requires:

- canonical Ayyo robot identity;
- one exact reviewed RGB sensor and optical frame;
- exact source provenance and configured clock domain;
- one exact allowlisted producer record;
- a retained previously admitted source-frame ID;
- exact agreement with that source frame's robot, camera, frame, acquisition
  time, provenance, and fingerprint;
- result time no earlier than acquisition and no later than permitted future
  skew;
- source acquisition within retention policy;
- newer result-time ordering for each camera/producer key; and
- non-conflicting deterministic identity.

Typed admission reasons distinguish an unknown producer, absent source frame,
source-frame mismatch, invalid result time, wrong robot/sensor/frame,
provenance/clock rejection, duplicate, out-of-order result, temporal conflict,
future source, and stale source. Malformed bounds, labels, identifiers,
timestamps, confidence, fingerprints, and collections fail in immutable core
construction.

A rejected result never changes current accepted evidence or the retained
source-frame set. It increments bounded statistics only. It cannot remove the
last valid result, grant authority, or partially install detections.

## Working Memory and World Model

Working Memory accepts only configured producer identities and rechecks that a
result matches retained trusted frame metadata. Current interpretation state is
keyed by exact `(camera_id, producer_id)`. Ordering uses `result_at_ns`, while
freshness and TTL use the unchanged source acquisition time. Late processing
therefore cannot make old sensor evidence appear newly acquired.

The World Model projector rebuilds each selected result into an immutable
`ObservedVisualInterpretationState`. Fresh/stale availability is derived at
projection time. Camera measurement availability remains based on the actual
admitted frame, not on a downstream interpretation. Interpretation semantics
participate in snapshot identity; query/capture time and pixel data do not.
Repeated read-only queries do not mutate state.

Evaluated producers add an exact compact `VisualEvaluationReference` and must
arrive as a sealed evaluator-issued admission. Perception consumes that
authorization once after binding it to the admitted source frame; Working
Memory independently matches the configured producer/model/dataset/policy/
report requirement. The full gate is documented in
[VISUAL_PRODUCER_EVALUATION.md](VISUAL_PRODUCER_EVALUATION.md).

No interpretation enters Memory OS. A later durable consolidation milestone
would require an explicit separate candidate-selection decision and the
existing Memory Validation boundary.

## Deterministic reference adapter

`DeterministicVisualReferenceAdapter` receives only validated pixel-free
`VisualFrameObservation` metadata. It contains no model, model download,
randomness, network access, external API, GPU framework, or image decoder. It
emits exactly one test-fixture detection:

```text
producer:   ayyo.visual.reference.synthetic.v1
kind:       test_fixture
model:      none
label:      synthetic.test-pattern.v1
category:   test_pattern
region:     [0.25, 0.25] → [0.75, 0.75]
confidence: absent
```

The result preserves the frame's simulation or physical source provenance.
The distinct producer record describes who processed it. Synthetic producer
identity is never substituted for camera provenance.

The ROS composition parameter
`enable_visual_reference_interpreter` is `false` by default. The simulation
launch exposes the same default-off argument. It exists only to exercise the
full architecture in tests and manual development.

## Read-only ROS projection

`GetRobotBodyState` adds typed visual-interpretation fields for source and
result time, source-frame identity/fingerprint, producer identity, provenance,
availability/freshness, detection IDs/categories/labels/normalized regions,
and explicit confidence presence. The fixed JSON client renders absent
confidence as `null`.

The transport-neutral contracts do not import ROS. The v1 ROS response is
singular because only one reference producer is configured in this milestone;
the immutable core snapshot supports bounded current results for multiple
camera/producer keys.

## Deterministic smoke-process teardown

Every smoke now starts its launch graph through `smoke_session.py`, which
creates a dedicated process session, restores normal `SIGINT`/`SIGTERM`
handling, and adds a unique `AYYO_SMOKE_RUN_ID` environment marker inherited by
every descendant. `smoke_processes.sh` identifies ownership by that exact
marker in `/proc`; it does not use process names, `pkill`, or `killall`.

Shutdown requests `SIGINT` from the owned launch process first and waits for a
bounded interval. If owned descendants remain, the helper prints their exact
PID/PPID/session/process details and sends scoped `SIGTERM`. A final scoped
`SIGKILL` removes otherwise unkillable test-owned processes, but the smoke still
returns nonzero because graceful/bounded cleanup failed. Success and early
failure paths share the same `EXIT` cleanup and only report success after the
owned set is empty.

The Gazebo defect came from the generic `ros_gz_sim` launcher using a shell
wrapper: ROS launch signaled the shell while its Ruby `gz sim` child survived.
Ayyo now invokes the reviewed `gz sim` command directly with
`ExecuteProcess(shell=False, on_exit=Shutdown())`, so launch owns and reaps the
actual simulator process. Regression tests cover graceful exit, unrelated
process survival, scoped TERM/KILL escalation, early failure, and exact marker
ownership.

The previously reported `joint_state_publisher` argument-conversion traceback
was consistent with forced/interrupted teardown. Ayyo does not own that
publisher's implementation. It was not reproduced after direct Gazebo
ownership and graceful test shutdown, and smoke logs explicitly fail on that
traceback. No upstream exception was suppressed and no publisher code was
changed.

## Physical and production migration

```text
physical camera + standard driver
→ same exact Image/CameraInfo normalizer
→ physical VisualFrameObservation provenance
→ separately reviewed physical/recorded processor adapter
→ same typed interpretation, trust, Working Memory, World Model, and query
```

Hardware work must validate mounting, calibration, synchronization, bandwidth,
failure diagnostics, compute and latency budgets, model provenance/versioning,
dataset/evaluation policy, and physical source separation. It must not reuse
simulation or test-fixture provenance. A real producer must supply honest
confidence semantics or leave confidence absent.

## Validated and not validated

Automated tests cover numeric and geometry bounds, negative-zero and ordering
canonicalization, deterministic rebuild/fingerprints, source/result times,
unknown producers, missing/spoofed frames, wrong robot/camera/frame/profile,
simulation/physical substitution, future/stale/out-of-order/conflicting
evidence, duplicate suppression, projection/query immutability, package
dependencies, resource ceilings, lifecycle deactivate/reactivate, and exact
owned-process shutdown.

The headless smoke exercised a real simulated RGB frame through the synthetic
result, trust, Working Memory, World Model, and fixed query. It also proved
that no command was issued and that the observed neck position remained
unchanged.

Not validated or implemented:

- production object/person detection, tracking, segmentation, OCR, face or
  owner identity, gesture, pose, depth, SLAM, localization, or scene-language
  understanding;
- model accuracy, calibration, dataset quality, GPU/edge performance, physical
  camera behavior, or production latency;
- graphical camera review in this milestone;
- any perception-derived command, Safety decision, permission, or execution;
- durable visual telemetry or Memory OS consolidation.

Run the focused proof with:

```bash
./scripts/build_workspace.sh
./scripts/smoke_visual_perception.sh
./scripts/smoke_visual_perception.sh
```

The recorded-data evaluation harness is now implemented in
[Recorded Visual Producer Evaluation and Perception Quality Gate v1](VISUAL_PRODUCER_EVALUATION.md).
The next step is representative recorded-corpus integration and a human-reviewed
promotion/rollback registry, still without movement authority.
