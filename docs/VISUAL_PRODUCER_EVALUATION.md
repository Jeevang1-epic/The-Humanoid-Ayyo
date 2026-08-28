# Recorded Visual Producer Evaluation and Perception Quality Gate v1

## Purpose and scope

This milestone adds the auditable boundary needed before Ayyo can integrate a
real visual model. It does not add a production detector, approve a model for
deployment, validate physical hardware, or grant any command authority.

The implemented path is:

```text
recorded/trusted RGB source
→ immutable evaluation sample
→ explicit registered producer
→ bounded producer invocation
→ typed producer result
→ mechanical policy evaluation
→ sealed evaluated admission
→ existing Perception Trust Boundary
→ bounded Working Memory
→ immutable World Model projection
→ fixed read-only query
```

Perception remains the only evidence-admission boundary. A mechanically
passing report is evidence about one exact evaluation configuration; it is not
human approval, physical validation, production certification, or permission
to act.

## Package and dependency boundary

`visual_evaluation/` is a standalone transport-neutral Python package. Its only
runtime dependency is the public `ayyo-world-model` contract package. It does
not import ROS, Gazebo, Working Memory, Memory OS, cognition, Safety, Runtime
Bridge, a model framework, networking, cloud APIs, persistence, or a dynamic
plugin loader.

The dependency direction is deliberately one way:

```text
ayyo-world-model
        ↑
ayyo-visual-evaluation
        ↑
ayyo-perception → ayyo-working-memory → World Model projection
```

ROS only composes these packages. Future model runtimes belong in narrow,
explicitly registered producer adapters; they do not gain direct access to
Working Memory or World Model mutation.

## Producer and model identity

`VisualProducerManifest` is immutable and pins:

- exact producer, semantic version, implementation SHA-256, kind, adapter,
  model, and result-interface identities;
- supported typed categories and confidence semantics;
- the fixed normalized evaluator input interface and exact `rgb8` encoding;
- exact dimensions, sensor identities, and source-provenance profiles;
- timeout, input-byte, result, detection, and label bounds;
- result schema version; and
- an honest manifest source classification.

Registration is explicit and bounded. An unknown producer fails. Re-registering
the same exact manifest is idempotent; the same producer ID with conflicting
content fails. Manifest fields cannot select a module, shell command, network
endpoint, or arbitrary executable.

`VisualModelProvenance` separately pins model ID/version, producer ID, artifact
SHA-256, format, capability, configuration SHA-256, label schema ID/version,
source classification, and optional build/export ID. A filesystem path is not
model identity. `verify_model_artifact_bytes` hashes supplied immutable bytes
and rejects a claimed digest that does not match them. The repository contains
only a tiny deterministic TEST fixture artifact; there is no downloaded or
production model.

Canonical serialization sorts unordered semantic collections, rejects
non-finite numbers, normalizes negative zero where float semantics allow it,
and derives SHA-256 identities from bounded documents. Semantically different
manifests change identity; execution paths, usernames, temporary directories,
and wall-clock values do not enter identity.

## Recorded dataset contract

`VisualEvaluationDatasetManifest` pins dataset ID/version/fingerprint, robot and
camera identity, optical frame, exact source provenance, collection provenance,
encoding, dimensions, calibration identity, annotation schema, and a bounded,
strictly ordered sample set.

Each `VisualEvaluationSample` binds one source-frame observation to an asset
reference, exact byte count and SHA-256, scenarios, and typed expected
detections. Raw bytes remain in the source/input layer and never enter a report,
Working Memory, World Model, Memory OS, or the query.

Two sources are implemented:

- `InMemoryVisualRecordedSource` copies a bounded immutable fixture mapping.
- `RootedRawRgb8VisualSource` reads only exact raw `rgb8` files below one
  configured root. It opens every path component by directory descriptor,
  uses `O_NOFOLLOW`, rejects traversal/absolute references/symlinks, requires a
  regular file, enforces size before reading, bounds each read, and verifies the
  digest. No decoder, archive, or decompressor is involved.

Duplicate/conflicting samples, missing data, changed content, source-profile,
camera, frame, dimension, encoding, calibration, annotation, ordering, or
manifest substitution fail closed.

## Invocation and result boundary

The evaluator consumes one immutable `VisualEvaluationInput`: a typed sample
plus immutable bytes whose size and digest match the sample. A registration
contains the fixed adapter object; producer metadata cannot create one.

`DeterministicFixtureInvoker` is synchronous and exists for deterministic
tests and the default-off ROS fixture. `OwnedProcessVisualProducerInvoker`
provides an evaluation-only Linux process boundary for timeout tests. It starts
one exact registered adapter in its own session, gives the run a random 128-bit
marker, enforces a fixed timeout, and cleans only the direct child and exact
marker-bearing descendants. It never kills by process name. Exceptions become
typed failures without serializing exception text into reports.

Every returned batch, producer result, source frame, detection, and region is
rebuilt after the invocation seam. Wrong producer/model/source/schema/time,
duplicate/oversized results, malformed geometry, NaN/infinity, category,
label, and confidence violations fail before admission.

## Metrics, report, and time semantics

`VisualEvaluationReport` contains one bounded record per source sample plus:

- attempted, admitted, rejected, valid, annotation-match, result, timeout,
  producer-failure, malformed, and duplicate counts;
- typed reason counts;
- minimum, maximum, mean, p50, p95, and p99 invocation latency;
- throughput sample count and monotonic elapsed time;
- optional explicitly labeled Python `tracemalloc` current/peak bytes;
- producer, model, dataset, policy, result-schema, and software identities;
- mechanical decision and typed reasons; and
- a deterministic semantic SHA-256.

Source acquisition time and producer result time remain in the typed evidence.
Monotonic invocation latency and report start/end times are separate. Receipt,
admission, query, and wall time do not replace source acquisition time.

The semantic report fingerprint excludes run ID, absolute monotonic start/end,
latency/throughput measurements, and Python allocation measurements. It keeps
stable quality counts, decisions, reasons, identities, and record semantics.
Two deterministic fixture evaluations therefore have the same semantic report
identity even when execution metadata differs.

## Mechanical quality gate and exact trust binding

`VisualEvaluationPolicy` pins the required producer manifest, model provenance,
dataset ID/version/manifest, result schema, categories, confidence semantics,
quality ratios, failure ceilings, p95 latency, and result/detection/label
bounds. A configuration mismatch fails before producer invocation.

A passing evaluator issues `EvaluatedVisualAdmission`; its constructor is
sealed inside the evaluator module. The admission binds one exact rebuilt
producer result and observation to:

- producer version, implementation SHA-256, and manifest SHA-256;
- complete model provenance and artifact SHA-256;
- dataset ID, version, and manifest SHA-256;
- policy ID, version, and SHA-256;
- semantic report SHA-256 and mechanical decision; and
- result schema version.

For a new live frame, the evaluator accepts only the same evaluator-issued
successful report object, exact registration/policy, an allowlisted source
profile, dimensions/encoding/sensor, bounded immutable bytes, and one valid
rebuilt result. The evidence kind is `qualified_live_frame`; it does not claim
that the live frame was a member of the recorded dataset.

`PerceptionTrustBoundary.authorize_evaluated_visual` accepts only the sealed
admission, not a bare observation or self-asserted “passed” reference. It
requires the exact configured evaluation requirement and a previously admitted
source frame with matching robot, camera, optical frame, acquisition time,
provenance, ID, and fingerprint. Authorization is consumed by one admission
attempt and is bounded by the existing 64 source-reference ceiling.

Working Memory then independently rechecks producer, compact evaluation
reference, and retained source-frame metadata. Only the compact accepted
`VisualInterpretationObservation` survives. No report object, manifest, raw
image, model bytes, dataset payload, producer log, or arbitrary dictionary is
retained.

## Bounds

| Resource | v1 bound |
| --- | ---: |
| Registered producers | 16 |
| Dataset samples | 8,192 |
| Aggregate fixture bytes | 128 MiB |
| Results per sample | 8 |
| Detections per result | 32 |
| Detection label characters | 64 |
| Producer timeout | 60 s maximum contract; fixture 20 ms |
| Evaluation reason categories | bounded typed enum |
| Software identities per report | 16 |
| Perception source/evaluation authorizations | 64 each |
| Current Working Memory interpretation per camera/producer | 1 |
| Default / maximum recent Working Memory evidence | 256 / 4,096 |
| Qualified reports retained by one evaluator | 16 |

The 5,000-cycle integration fixture admitted 5,000 source frames and 5,000
sealed interpretations, retained one current interpretation, one compact
evaluation reference, 16 recent/unique entries under the test capacity, and 64
source references. The measured run used Python `tracemalloc`; it is not a
total-process, ROS, Gazebo, GPU, Raspberry Pi, Jetson, or physical-device memory
measurement.

## ROS fixture behavior

The lifecycle World Model node exposes
`enable_visual_producer_evaluation_fixture`, default `false`. It is mutually
exclusive with the older synthetic reference interpreter. During configure it:

1. constructs one 320×240 recorded TEST fixture while keeping recorded and
   simulation source provenance distinct;
2. verifies/registers the fixture producer and model artifact;
3. runs one deterministic mechanical evaluation; and
4. configures Perception and Working Memory with the resulting exact
   requirement.

While active, the fixed sensor-data-QoS Image/CameraInfo path first normalizes
and admits the camera frame. At most one frame per lifecycle activation is
copied into a local immutable `bytes` value, invoked synchronously through the
deterministic TEST adapter, sealed, authorized by Perception, and retained as
compact semantic evidence. The local bytes are then released. Deactivation
destroys subscriptions and resets the per-activation flag; reactivation may
issue one new result. Cleanup/shutdown clears evaluator/report references and
all temporary evidence.

`world_model_retention_ttl_ms` is an explicit bounded launch argument with the
unchanged 2,000 ms default. The smoke uses 10,000 ms only so two separate CLI
query processes can inspect the same one-per-activation result before its
source-derived TTL expires.

The existing read-only service remains fixed. Its additive fields expose only
compact producer/model/dataset/policy/report identities, decision, source
identity, bounded detections, and status. It exposes no pixels or full report.

## Verification and adversarial findings

Automated coverage includes unknown/conflicting producer registration, changed
manifest/model artifact/dataset content, path traversal and symlink escape,
wrong camera/frame/source/model/schema/time, malformed/oversized collections,
NaN/infinity/reversed/zero-area/out-of-range regions, category/label/confidence
violations, timeout/exception mapping, exact process cleanup, forged reports,
bare evaluator and Perception bypass attempts, physical/simulation
substitution, corruption recovery, deterministic reruns, query immutability,
bounded duplicate/high-rate state, lifecycle reactivation, package isolation,
and absence of command surfaces.

The focused smoke ran twice consecutively. Each run used the owned process
marker/session utilities, ran the 5,000-cycle offline fixture, launched an
isolated ROS/Gazebo graph, admitted the evaluated result to the fixed query,
checked compact provenance and unchanged repeat-query identity, verified no
movement/skill/actuation service, deactivated/reactivated, and ended with an
empty owned-process set and empty isolated graph.

Run the focused validation with:

```bash
PYTHONPATH=world_model/src:visual_evaluation/src \
python3 -m unittest discover -s visual_evaluation/tests -v

PYTHONPATH=world_model/src:visual_evaluation/src:perception/src \
python3 -m unittest discover -s perception/tests -v

PYTHONPATH=world_model/src:working_memory/src \
python3 -m unittest discover -s working_memory/tests -v

./scripts/build_workspace.sh
./scripts/test_workspace.sh
./scripts/smoke_visual_producer_evaluation.sh
./scripts/smoke_visual_producer_evaluation.sh
```

## Optional recorded ROS camera path

`rosbag2` is not a standalone-core dependency. The following manual boundary
uses only the fixed camera topics and must run in an isolated domain. It was not
executed or claimed as validated in this milestone.

Record and inspect:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=131
ros2 bag record -o /tmp/ayyo_head_rgb_eval \
  /ayyo/camera/head/image_raw /ayyo/camera/head/camera_info
# Stop with Ctrl-C.
ros2 bag info /tmp/ayyo_head_rgb_eval
```

In a new isolated domain, launch the simulation clock/body observer without a
live camera publisher, then replay the two recorded camera topics. The replayed
header timestamps must be compatible with the new simulation clock; otherwise
the existing future/stale checks intentionally reject them.

```bash
export ROS_DOMAIN_ID=132
export GZ_PARTITION=ayyo_visual_bag_eval_132
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=true enable_control:=false enable_world_model:=true \
  enable_camera:=false enable_visual_reference_interpreter:=false \
  enable_visual_producer_evaluation_fixture:=true \
  world_model_retention_ttl_ms:=10000
```

Second terminal, same domain and overlay:

```bash
ros2 bag play /tmp/ayyo_head_rgb_eval
ros2 run ayyo_world_model body_state_query.py
```

This is an optional replay seam, not a dedicated validated rosbag evaluator.
A future adapter should explicitly bind bag metadata/storage ID, topic
allowlist, Image/CameraInfo synchronization, and recorded clock identity before
claiming repeatable bag evaluation.

## Physical camera and future real-model migration

The physical path keeps the architecture:

```text
physical standard camera driver
→ same Image + CameraInfo topics and optical frame
→ distinct reviewed physical source provenance
→ same immutable input and producer contracts
→ model/dataset/policy evaluation
→ same sealed Perception admission
→ same bounded Working Memory and immutable World Model
```

Model provenance is independent of simulation/physical camera provenance. A
model does not become approved merely because it passed this fixture, and a
physical camera must not reuse simulation or test provenance.

A future detector, person detector, tracker, pose estimator, OCR adapter, or
scene producer must be a narrow explicit registration: trusted immutable frame
input, verified artifact/configuration, typed bounded result, recorded-policy
evaluation, sealed Perception admission. It does not need and must not receive
Memory OS, World Model mutation, Safety, Runtime Bridge, navigation,
manipulation, or actuator access.

## Known limitations and non-claims

- Only deterministic TEST producers and tiny raw `rgb8` fixtures exist.
- No production model, accuracy benchmark, representative dataset, human model
  approval workflow, GPU runtime, edge-device benchmark, or physical camera was
  validated.
- Latency is fixture/invoker latency on this development environment, not a
  realtime or deployment guarantee.
- The ROS live path intentionally issues only one TEST result per activation;
  it is not a streaming production inference scheduler.
- No dedicated rosbag adapter or bag metadata identity is implemented.
- Reports are in-process immutable evidence; durable report storage/signing,
  approval records, promotion, rollback, and fleet attestation are future work.
- Perception output remains evidence only. It cannot command motion, navigation,
  manipulation, skill execution, Safety decisions, or durable memory writes.

The recommended next milestone is a real recorded-corpus adapter and
human-reviewed producer promotion registry with signed artifact/dataset/policy
identities, representative scenario coverage, rollback state, and deployment
resource budgets—still behind the same Perception Trust Boundary and with no
movement authority.
