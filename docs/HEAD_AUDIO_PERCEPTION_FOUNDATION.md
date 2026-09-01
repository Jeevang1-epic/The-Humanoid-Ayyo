# Head Audio Perception Foundation v1

## Purpose and scope

This milestone establishes a driver-neutral trust boundary for one head
microphone source. It reduces one bounded PCM transport frame immediately to
immutable compact metadata, admits the frame and its lifecycle health through
Perception, retains bounded temporary evidence in Working Memory, and exposes
an immutable read-only World Model projection.

It does not interpret speech or sound and cannot command, move, navigate,
manipulate, select a skill, override Safety, identify a speaker, or write
durable memory. Audio is evidence only.

## Trust flow

```text
bounded ayyo_interfaces/AudioFrame
  -> ROS-only transport validation and immediate PCM reduction
  -> immutable AudioFrameObservation (no samples)
  -> reviewed source manifest + lifecycle/session adapter
  -> sealed one-use frame/health admission
  -> Perception Trust Boundary
  -> bounded Working Memory
  -> immutable World Model projection
  -> compact read-only GetRobotBodyState fields
```

Raw audio bytes exist only at the ROS transport/normalization edge. Working
Memory, the World Model, fingerprints, diagnostics, and the query response do
not contain a byte or sample buffer.

## Exact source and format contracts

The deterministic executable source is TEST-only:

- sensor: `ayyo.microphone.head.v1`;
- mount frame: `head_microphone_frame`;
- source: `ros.audio.head.test-fixture.v1`;
- producer: `ayyo.audio.test-adapter.v1`, version `1.0.0`;
- classification: `test_fixture`;
- clock: `test_time`;
- transport: `ros2`;
- interface: `ayyo-interfaces.audio-frame.v1`; and
- topic: `/ayyo/audio/head/microphone/raw`.

The immutable source manifest binds the robot, microphone, producer
implementation digest, provenance, topic, frame, format, and resource bounds
to one content-derived `audio-source-sha256-*` identity. TEST, simulation,
recorded, and project-reviewed physical classifications cannot substitute for
one another. A non-physical source cannot claim a device serial or hardware
fingerprint.

v1 accepts only mono `pcm_s16le` at 16,000 Hz. The TEST fixture publishes 160
frames (160 samples), representing 10 ms and 320 bytes. The domain hard limits
are 16,000 frames and 32,000 bytes; the TEST manifest deliberately narrows
those limits to 160 frames and 320 bytes. Frame count, byte count, duration,
payload SHA-256, finite RMS, and peak amplitude must agree with the payload and
format. Odd, empty, oversized, malformed, mismatched, or unsupported payloads
fail closed.

## Time, lifecycle, and health

Configuration resolves one explicitly registered source. Activation creates a
content-derived `audio-session-sha256-*` identity for a new epoch. Submission
requires that exact active session and checks positive acquisition/result
time, result-time ordering, configured freshness/future-skew bounds, and
strict source-time ordering. Stale, future, regressed, duplicate, inactive,
and old-session evidence cannot become current.

Deactivation closes admission and clears the active session. Reactivation
creates a distinct session; callbacks or evidence carrying an earlier session
remain invalid. Cleanup returns the adapter to unconfigured state, and shutdown
finalizes it. Typed diagnostics report lifecycle/event, format, availability,
accepted/rejected/duplicate/dropped/error counters, the last evidence time,
and `retained_payload_bytes`, which remains zero.

The admitted health observation means that the reviewed TEST capture adapter
is active. It is not a claim about microphone hardware or acoustic quality.

## Perception Trust Boundary

Every configured microphone source requires one exact `AudioTrustRequirement`
that binds its source, robot, microphone, producer implementation, provenance,
manifest, format, and bounds. The lifecycle adapter issues a private sealed
admission containing an immutable frame/health pair. Perception reconstructs
and compares both values, requires the configured requirement, and consumes
each authorization once. A hand-built observation, forged admission, reused
authorization, mismatched frame/health pair, or alternate source cannot gain
trust.

Perception continues to enforce identity, provenance, source/result time,
freshness, ordering, duplicate, fingerprint, and bounded-resource policies.
Admission carries no execution or authorization semantics.

## Working Memory and World Model

Working Memory uses the typed `ROBOT_AUDIO` state key. It keeps at most one
current compact frame per configured microphone and references it through the
existing bounded recent-evidence capacity (default 256, hard maximum 4,096).
Duplicate evidence does not grow state, rejection does not replace current
trusted state, TTL expiry removes readiness, and reset clears the epoch.
Queries are read-only and do not extend lifetime or mutate evidence.

The World Model projects immutable `ObservedAudioState` values with explicit
availability and freshness. The observation contains identities, provenance,
session, acquisition/result times, format, counts, duration, byte count,
peak/RMS summaries, and payload/observation fingerprints. It has no raw-data
field and does not import ROS, device drivers, Perception, or control layers.

## ROS 2 interfaces and default-off composition

`ayyo_interfaces/msg/AudioFrame` contains a standard header and result stamp,
bounded source/producer/microphone strings, rate/channel/encoding/frame count,
the claimed payload digest, and `uint8[<=32000] data`. The ROS adapter checks
the exact type, positive times, source identity, microphone frame, format,
shape, digest, and manifest bounds before compacting the payload.

`head_audio_fixture.launch.py` is default off. Enabling the hardware-free proof
requires both:

```text
enable_head_audio_fixture:=true
head_audio_profile:=test_fixture_v1
```

The TEST publisher emits deterministic 10 ms PCM frames. Disabled composition
has no audio publisher or current audio state. The existing
`GetRobotBodyState` response is extended additively with compact audio frame
and diagnostic fields. It exposes no samples and no control endpoint.

## Failure and adversarial behavior

Tests and the owned smoke exercise wrong robot/source/sensor/frame/provenance,
source classification substitution, forged manifest and session identities,
wrong rate/channel/encoding/count/duration/digest, malformed payloads,
stale/future/regressed/out-of-order/result times, duplicate evidence,
inactive submission, old-session replay, forged and reused admission seals,
resource overflow, reset/expiry, rejection recovery, and stable read-only
projection. Failures are bounded diagnostic evidence and never establish
readiness.

The resource proof admits 5,000 deterministic frames. It requires 5,000
acceptances, zero retained payload bytes, no raw `data` member downstream,
traced current memory below 4 MiB, and traced peak memory below 16 MiB. The
smoke owns every process, requires an empty isolated ROS graph after shutdown,
and performs a delayed second teardown check.

## Physical-device migration

A physical adapter must register a separate `project_reviewed_device` manifest
with a reviewed device serial and device fingerprint, producer implementation,
clock, transport, format, lifecycle, and measured timing/resource behavior.
It must preserve the same raw-data containment, sealed admission, default-off
activation, provenance separation, and fail-closed session semantics. Sharing
the ROS topic or message type does not grant physical trust.

## Validation status and limitations

Implemented and validated behavior is limited to deterministic TEST data,
transport-neutral unit/resource tests, the ROS message/adapter/query path, and
the default-off hardware-free lifecycle smoke.

This milestone did **not** validate:

- real microphones;
- vendor microphone drivers;
- USB/I2S/audio hardware;
- acoustic quality;
- physical microphone calibration;
- beamforming;
- echo cancellation;
- speech recognition;
- speaker identification;
- wake-word models;
- production latency;
- production audio-device timing; or
- real-world noise robustness.

It makes no physical-hardware claim.

## Exact manual verification

From the repository root:

```bash
PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q head_audio/tests
PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q perception/tests
PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q working_memory/tests
PYTHONPATH=world_model/src:head_audio/src:physical_camera/src:depth_camera/src:rgbd_fusion/src:visual_evaluation/src:perception/src:working_memory/src \
python3 -m pytest -q world_model/tests

rm -rf ros2_ws/build ros2_ws/install ros2_ws/log
./scripts/build_workspace.sh
./scripts/test_workspace.sh

./scripts/smoke_head_audio.sh
./scripts/smoke_head_audio.sh

git diff --check
git status --short --branch
```

The two smoke runs must execute consecutively against unchanged code. They
must both finish with `PASS: Head Audio Perception Foundation v1 smoke
completed` and report an empty delayed owned-process set and isolated ROS
graph. These commands validate only the TEST foundation described above.
