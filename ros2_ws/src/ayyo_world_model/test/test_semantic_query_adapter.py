# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ayyo_interfaces.msg import AnonymousSemanticItem, AnonymousSemanticState
from ayyo_interfaces.srv import GetAnonymousSemanticState
from ayyo_perception import semantic_observation_from_detection
from ayyo_working_memory import WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    FreshnessState,
    JointContract,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    ObservedSemanticEvidenceState,
    RobotAvailability,
    RobotBodyState,
    RobotJointCatalog,
    SemanticEvidenceItem,
    SemanticEvidenceKind,
    SemanticEvidenceObservation,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualFrameObservation,
    WorldSnapshot,
)

from test_ros_adapter import adapter_module


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CAMERA = SensorIdentity(
    'ayyo.camera.head.rgb.v1',
    SensorKind.RGB_CAMERA,
    'head_camera_optical_frame',
)
PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    'test.semantic-ros-query.v1',
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    'direct.semantic-ros-query.v1',
)


def catalog() -> RobotJointCatalog:
    return RobotJointCatalog(
        robot_id=AYYO_ROBOT_ID,
        joints=(
            JointContract(
                'neck_yaw_joint',
                'revolute',
                -1.2,
                1.2,
                1.5,
                8.0,
            ),
        ),
    )


def semantic_chain(*, observed_at_ns: int = 100):
    adapter = adapter_module()
    frame = VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=CAMERA,
        width=32,
        height=24,
        encoding='rgb8',
        step=96,
        data_size_bytes=2_304,
        is_bigendian=False,
        calibration_id='camera-calibration-sha256-' + '1' * 64,
        observed_at_ns=observed_at_ns,
        provenance=PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )
    interpretation = adapter.semantic_query_fixture_interpretation(
        frame,
        result_at_ns=observed_at_ns,
    )
    semantic_observations = tuple(
        semantic_observation_from_detection(
            interpretation,
            detection_id=detection.detection_id,
        )
        for detection in interpretation.detections
    )
    items = tuple(
        SemanticEvidenceItem(
            kind=SemanticEvidenceKind(semantic.kind.value),
            source_semantic_observation_id=semantic.observation_id,
            source_detection_id=semantic.source_detection.visual_detection_id,
            region=semantic.region,
            confidence=semantic.confidence,
            category=getattr(semantic, 'category', None),
        )
        for semantic in semantic_observations
    )
    evidence = SemanticEvidenceObservation(
        robot_id=interpretation.robot_id,
        sensor=interpretation.sensor,
        reference_frame_id=interpretation.reference_frame_id,
        source_visual_observation_id=interpretation.source_visual_observation_id,
        source_visual_fingerprint=interpretation.source_visual_fingerprint,
        source_interpretation_observation_id=interpretation.observation_id,
        source_interpretation_fingerprint=interpretation.fingerprint,
        observed_at_ns=interpretation.observed_at_ns,
        result_at_ns=interpretation.result_at_ns,
        producer=interpretation.producer,
        evaluation_reference_sha256=None,
        items=items,
        provenance=interpretation.provenance,
        availability=interpretation.availability,
    )
    return frame, interpretation, evidence


def snapshot_with(
    evidence: SemanticEvidenceObservation | None,
    *,
    now_ns: int = 100,
    freshness: FreshnessState = FreshnessState.FRESH,
) -> WorldSnapshot:
    robot = RobotBodyState(
        robot_id=AYYO_ROBOT_ID,
        known_joint_names=('neck_yaw_joint',),
        joints=(),
        base_pose=None,
        availability=RobotAvailability.UNAVAILABLE,
    )
    return WorldSnapshot(
        captured_at_ns=now_ns,
        robot=robot,
        entities=(),
        semantic_states=(
            ()
            if evidence is None
            else (
                ObservedSemanticEvidenceState(
                    observation=evidence,
                    freshness=freshness,
                    availability=(
                        SensorAvailability.STALE
                        if freshness is FreshnessState.STALE
                        else evidence.availability
                    ),
                ),
            )
        ),
    )


class FixedClock:
    def __init__(self, now_ns: int) -> None:
        self.now_ns = now_ns

    def now(self):
        return SimpleNamespace(nanoseconds=self.now_ns)


class QueryHarness:
    def __init__(self, module, memory, *, now_ns=100, active=True) -> None:
        self.module = module
        self._memory = memory
        self._active = active
        self.clock = FixedClock(now_ns)
        self.reset_count = 0

    def get_clock(self):
        return self.clock

    def _semantic_not_ready(self, response, detail):
        return self.module.AyyoWorldModelNode._semantic_not_ready(response, detail)

    def _reset_evidence_epoch(self):
        self.reset_count += 1
        if self._memory is not None:
            self._memory.reset()


class SnapshotMemory:
    def __init__(self, snapshot: WorldSnapshot) -> None:
        self.snapshot = snapshot
        self.query_times = []
        self.mutation_count = 0

    def current_snapshot(self, *, now_ns: int) -> WorldSnapshot:
        self.query_times.append(now_ns)
        return self.snapshot

    def ingest(self, *args, **kwargs):
        del args, kwargs
        self.mutation_count += 1
        raise AssertionError('read-only query attempted ingestion')

    def reset(self) -> None:
        self.mutation_count += 1


def invoke(harness: QueryHarness, *, robot_id: str = AYYO_ROBOT_ID):
    request = GetAnonymousSemanticState.Request()
    request.robot_id = robot_id
    response = GetAnonymousSemanticState.Response()
    return harness.module.AyyoWorldModelNode._handle_semantic_query(
        harness,
        request,
        response,
    )


def test_empty_retained_state_is_ready_without_negative_scene_knowledge() -> None:
    module = adapter_module()
    memory = SnapshotMemory(snapshot_with(None))
    response = invoke(QueryHarness(module, memory))
    assert response.status == GetAnonymousSemanticState.Response.READY
    assert response.semantic_state_count == 0
    assert list(response.semantic_states) == []
    assert 'no currently retained anonymous semantic evidence' in response.detail
    assert 'physical-scene occupancy remains unknown' in response.detail
    assert 'no people present' not in response.detail
    assert 'no objects present' not in response.detail
    assert 'scene is empty' not in response.detail


def test_person_and_object_transport_preserves_exact_anonymous_sources() -> None:
    module = adapter_module()
    _, _, evidence = semantic_chain()
    snapshot = snapshot_with(evidence)
    response = invoke(QueryHarness(module, SnapshotMemory(snapshot)))
    assert response.snapshot_id == snapshot.snapshot_id
    assert response.snapshot_fingerprint == str(snapshot.version)
    assert response.semantic_state_count == 1
    state = response.semantic_states[0]
    assert state.observation_id == evidence.observation_id
    assert state.observation_fingerprint == str(evidence.fingerprint)
    assert state.source_visual_observation_id == evidence.source_visual_observation_id
    assert state.source_visual_fingerprint == str(evidence.source_visual_fingerprint)
    assert state.source_interpretation_observation_id == (
        evidence.source_interpretation_observation_id
    )
    assert state.source_interpretation_fingerprint == str(
        evidence.source_interpretation_fingerprint
    )
    assert state.producer_id == evidence.producer.producer_id
    assert state.source_id == evidence.provenance.source_id
    assert state.freshness == AnonymousSemanticState.FRESH
    by_kind = {item.kind: item for item in state.items}
    person = by_kind[AnonymousSemanticItem.PERSON]
    object_evidence = by_kind[AnonymousSemanticItem.OBJECT]
    assert not person.has_object_category
    assert person.object_category == ''
    assert not person.has_confidence
    assert person.confidence == 0.0
    assert object_evidence.has_object_category
    assert object_evidence.object_category == 'synthetic.demo-object.v1'
    assert object_evidence.has_confidence
    assert object_evidence.confidence == 0.0
    assert person.source_semantic_observation_id.startswith(
        'person-observation-sha256-'
    )
    assert object_evidence.source_semantic_observation_id.startswith(
        'object-observation-sha256-'
    )


def test_each_request_uses_one_snapshot_and_repeated_query_is_state_neutral() -> None:
    module = adapter_module()
    _, _, evidence = semantic_chain()
    memory = SnapshotMemory(snapshot_with(evidence))
    harness = QueryHarness(module, memory, now_ns=123)
    first = invoke(harness)
    second = invoke(harness)
    assert memory.query_times == [123, 123]
    assert memory.mutation_count == 0
    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_fingerprint == second.snapshot_fingerprint
    assert first.semantic_states == second.semantic_states


def test_wrong_robot_and_inactive_lifecycle_fail_without_reading_state() -> None:
    module = adapter_module()
    memory = SnapshotMemory(snapshot_with(None))
    wrong = invoke(QueryHarness(module, memory), robot_id='other.robot.v1')
    inactive = invoke(QueryHarness(module, memory, active=False))
    assert wrong.status == GetAnonymousSemanticState.Response.NOT_READY
    assert inactive.status == GetAnonymousSemanticState.Response.NOT_READY
    assert memory.query_times == []
    assert wrong.snapshot_id == ''
    assert inactive.semantic_state_count == 0


def test_fresh_stale_ttl_and_reset_transitions_use_working_memory_semantics() -> None:
    module = adapter_module()
    frame, interpretation, evidence = semantic_chain()
    store = WorkingMemory(
        catalog(),
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            allowed_provenance=(PROVENANCE,),
            sensors=(CAMERA,),
            freshness_ns=50,
            retention_ttl_ns=100,
            permitted_future_skew_ns=5,
            recent_evidence_capacity=8,
            environment_entity_capacity=1,
            semantic_evidence_capacity=8,
            visual_interpretation_producers=(interpretation.producer,),
        ),
    )
    for receipt, observation in enumerate((frame, interpretation, evidence), start=1):
        assert store.ingest(
            observation,
            now_ns=100,
            received_at_monotonic_ns=receipt,
        ).status.value == 'accepted'
    recent_before = store.recent_evidence(now_ns=100)
    harness = QueryHarness(module, store, now_ns=100)
    fresh = invoke(harness)
    repeated = invoke(harness)
    assert len(store.recent_evidence(now_ns=100)) == len(recent_before)
    assert fresh.snapshot_id == repeated.snapshot_id
    assert fresh.semantic_states[0].freshness == AnonymousSemanticState.FRESH
    harness.clock.now_ns = 151
    stale = invoke(harness)
    assert stale.semantic_states[0].freshness == AnonymousSemanticState.STALE
    assert stale.snapshot_id != fresh.snapshot_id
    harness.clock.now_ns = 201
    expired = invoke(harness)
    assert expired.semantic_state_count == 0
    assert expired.snapshot_id != stale.snapshot_id
    store.reset()
    harness.clock.now_ns = 10
    reset = invoke(harness)
    assert reset.semantic_state_count == 0


def test_semantic_query_never_creates_persistent_entities() -> None:
    module = adapter_module()
    _, _, evidence = semantic_chain()
    snapshot = snapshot_with(evidence)
    response = invoke(QueryHarness(module, SnapshotMemory(snapshot)))
    assert snapshot.entities == ()
    assert not hasattr(response, 'entities')
    assert not hasattr(response.semantic_states[0], 'entity_id')
    assert not hasattr(response.semantic_states[0].items[0], 'person_id')
    assert not hasattr(response.semantic_states[0].items[0], 'track_id')


def test_query_callback_contains_no_perception_or_memory_write_path() -> None:
    source = (PACKAGE_ROOT / 'scripts' / 'world_model_node.py').read_text(
        encoding='utf-8'
    )
    start = source.index('    def _handle_semantic_query(')
    end = source.index('    @staticmethod\n    def _availability_code', start)
    callback = source[start:end]
    assert callback.count('current_snapshot(') == 1
    for forbidden in (
        '.admit(',
        '.ingest(',
        'project_semantic_evidence',
        'semantic_observation_from_detection',
        'PersonObservation',
        'ObjectObservation',
        'create_publisher',
        'ayyo_memory',
    ):
        assert forbidden not in callback


def test_service_and_semantic_fixture_are_lifecycle_owned_and_default_off() -> None:
    node = (PACKAGE_ROOT / 'scripts' / 'world_model_node.py').read_text(
        encoding='utf-8'
    )
    launch = (
        PACKAGE_ROOT.parent
        / 'ayyo_simulation'
        / 'launch'
        / 'simulation.launch.py'
    ).read_text(encoding='utf-8')
    assert "SEMANTIC_QUERY_SERVICE = '/ayyo/world_model/get_anonymous_semantic_state'" in node
    assert "declare_parameter('enable_anonymous_semantic_test_fixture', False)" in node
    assert 'self.create_service(\n                GetAnonymousSemanticState' in node
    assert 'self.destroy_service(self._semantic_query_service)' in node
    assert 'if not self._active or self._memory is None:' in node
    default_off = (
        "'enable_anonymous_semantic_test_fixture',\n"
        "                default_value='false'"
    )
    assert default_off in launch
    interpretation = semantic_chain()[1]
    categories = {detection.category.value for detection in interpretation.detections}
    assert categories == {'person', 'object'}
    confidences = {
        detection.category.value: detection.confidence
        for detection in interpretation.detections
    }
    assert confidences == {'person': None, 'object': 0.0}
