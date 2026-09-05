from __future__ import annotations

from ayyo_memory import MemoryType
from ayyo_memory_consolidation import (
    ConsolidationRequest,
    EvidenceReference,
)
from ayyo_perception import semantic_observation_from_detection
from ayyo_working_memory import WorkingMemory, WorkingMemoryConfig
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    JointContract,
    JointObservation,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    RobotJointCatalog,
    RobotStateObservation,
    SemanticEvidenceItem,
    SemanticEvidenceKind,
    SemanticEvidenceObservation,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualDetection,
    VisualFrameObservation,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
    VisualProducerKind,
    VisualSemanticCategory,
)


SYSTEM_TIME_NS = 1_767_225_600_000_000_000
SYSTEM_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    "ayyo.joint-state.physical.v1",
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    "sensor_msgs.msg.joint_state",
)
OTHER_SYSTEM_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    "ayyo.joint-state.physical.other.v1",
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    "sensor_msgs.msg.joint_state",
)
SIMULATION_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.SIMULATION,
    "ayyo.joint-state.simulation.v1",
    ObservationClock.ROS_SIMULATION_TIME,
    ObservationTransport.ROS2,
    "sensor_msgs.msg.joint_state",
)
TEST_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.memory-consolidation.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.robot-state.v1",
)
JOINT_SENSOR = SensorIdentity(
    "ayyo.joint-state.v1",
    SensorKind.JOINT_STATE,
    "base_link",
)
CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
VISUAL_PROVENANCE = ObservationProvenance(
    ObservationSourceKind.PHYSICAL_SENSOR,
    "ayyo.camera.head.rgb.physical.v1",
    ObservationClock.ROS_SYSTEM_TIME,
    ObservationTransport.ROS2,
    "sensor_msgs.msg.image",
)
PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.memory-candidate.v1",
    VisualProducerKind.PHYSICAL_PROCESSOR,
    "ayyo.visual.detector.v1",
    "ayyo.visual.memory-candidate.adapter.v1",
    "ayyo.visual-interpretation.v1",
)


def catalog() -> RobotJointCatalog:
    return RobotJointCatalog(
        robot_id=AYYO_ROBOT_ID,
        joints=(
            JointContract(
                "neck_yaw_joint",
                "revolute",
                -1.2,
                1.2,
                1.5,
                8.0,
            ),
        ),
    )


def working_memory(
    *,
    provenance: ObservationProvenance = SYSTEM_PROVENANCE,
    clock: ObservationClock = ObservationClock.ROS_SYSTEM_TIME,
    freshness_ns: int = 1_000_000_000,
    ttl_ns: int = 2_000_000_000,
    visual: bool = False,
) -> WorkingMemory:
    return WorkingMemory(
        catalog(),
        WorkingMemoryConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=clock,
            allowed_provenance=(provenance,),
            sensors=(CAMERA,) if visual else (),
            freshness_ns=freshness_ns,
            retention_ttl_ns=ttl_ns,
            permitted_future_skew_ns=10_000,
            recent_evidence_capacity=16,
            environment_entity_capacity=4,
            semantic_evidence_capacity=8,
            visual_interpretation_producers=(PRODUCER,) if visual else (),
        ),
    )


def robot_observation(
    *,
    observed_at_ns: int = SYSTEM_TIME_NS,
    confidence: float = 0.625,
    provenance: ObservationProvenance = SYSTEM_PROVENANCE,
) -> RobotStateObservation:
    return RobotStateObservation(
        robot_id=AYYO_ROBOT_ID,
        joints=(JointObservation("neck_yaw_joint", 0.25),),
        observed_at_ns=observed_at_ns,
        provenance=provenance,
        confidence=confidence,
    )


def retain_robot(
    *,
    observation: RobotStateObservation | None = None,
    store: WorkingMemory | None = None,
    now_ns: int = SYSTEM_TIME_NS,
) -> tuple[WorkingMemory, RobotStateObservation]:
    retained = observation or robot_observation()
    memory = store or working_memory(provenance=retained.provenance)
    result = memory.ingest(
        retained,
        now_ns=now_ns,
        received_at_monotonic_ns=1,
    )
    assert result.status.value == "accepted"
    return memory, retained


def reference(
    observation,
    *,
    semantic_item_id: str | None = None,
    source_id: str | None = None,
) -> EvidenceReference:
    return EvidenceReference(
        observation_id=observation.observation_id,
        observation_fingerprint=str(observation.fingerprint),
        source_id=observation.provenance.source_id if source_id is None else source_id,
        semantic_item_id=semantic_item_id,
    )


def request(
    observation,
    *,
    memory_type: MemoryType = MemoryType.EPISODIC,
    subject: str = AYYO_ROBOT_ID,
    predicate: str = "observed_neck_position",
    value=None,
    supporting_evidence=None,
    metadata=None,
) -> ConsolidationRequest:
    return ConsolidationRequest(
        robot_id=AYYO_ROBOT_ID,
        memory_type=memory_type,
        subject=subject,
        predicate=predicate,
        value={"position_rad": 0.25} if value is None else value,
        supporting_evidence=(
            [reference(observation)]
            if supporting_evidence is None
            else supporting_evidence
        ),
        metadata={} if metadata is None else metadata,
    )


def semantic_chain(
    *,
    kind: SemanticEvidenceKind,
    confidence: float | None,
    category: str = "cup",
    observed_at_ns: int = SYSTEM_TIME_NS,
):
    frame = VisualFrameObservation(
        robot_id=AYYO_ROBOT_ID,
        sensor=CAMERA,
        width=32,
        height=24,
        encoding="rgb8",
        step=96,
        data_size_bytes=2_304,
        is_bigendian=False,
        calibration_id="camera-calibration-sha256-" + "1" * 64,
        observed_at_ns=observed_at_ns,
        provenance=VISUAL_PROVENANCE,
        availability=SensorAvailability.AVAILABLE,
    )
    detection = VisualDetection(
        source_visual_observation_id=frame.observation_id,
        category=(
            VisualSemanticCategory.PERSON
            if kind is SemanticEvidenceKind.PERSON
            else VisualSemanticCategory.OBJECT
        ),
        label="person" if kind is SemanticEvidenceKind.PERSON else category,
        region=ImageRegion2D(
            x_min=0.1,
            y_min=0.2,
            x_max=0.6,
            y_max=0.9,
        ),
        confidence=confidence,
    )
    interpretation = VisualInterpretationObservation(
        robot_id=frame.robot_id,
        sensor=frame.sensor,
        reference_frame_id=frame.sensor.frame_id,
        source_visual_observation_id=frame.observation_id,
        source_visual_fingerprint=frame.fingerprint,
        observed_at_ns=frame.observed_at_ns,
        result_at_ns=frame.observed_at_ns,
        producer=PRODUCER,
        detections=(detection,),
        provenance=frame.provenance,
        availability=frame.availability,
    )
    admitted_semantic = semantic_observation_from_detection(
        interpretation,
        detection_id=detection.detection_id,
    )
    item = SemanticEvidenceItem(
        kind=kind,
        source_semantic_observation_id=admitted_semantic.observation_id,
        source_detection_id=detection.detection_id,
        region=detection.region,
        confidence=detection.confidence,
        category=None if kind is SemanticEvidenceKind.PERSON else category,
    )
    semantic = SemanticEvidenceObservation(
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
        items=(item,),
        provenance=interpretation.provenance,
        availability=interpretation.availability,
    )
    store = working_memory(provenance=VISUAL_PROVENANCE, visual=True)
    for receipt, observation in enumerate(
        (frame, interpretation, semantic),
        start=1,
    ):
        result = store.ingest(
            observation,
            now_ns=observed_at_ns,
            received_at_monotonic_ns=receipt,
        )
        assert result.status.value == "accepted"
    return store, frame, interpretation, semantic, item


def semantic_request(
    semantic: SemanticEvidenceObservation,
    item: SemanticEvidenceItem,
    *,
    memory_type: MemoryType = MemoryType.EPISODIC,
    subject: str = AYYO_ROBOT_ID,
    predicate: str | None = None,
    value=None,
) -> ConsolidationRequest:
    expected_value = {
        "anonymous": True,
        "kind": item.kind.value,
        "region": item.region.document(),
    }
    if item.kind is SemanticEvidenceKind.OBJECT:
        expected_value["category"] = item.category
    return ConsolidationRequest(
        robot_id=AYYO_ROBOT_ID,
        memory_type=memory_type,
        subject=subject,
        predicate=(
            f"observed_anonymous_{item.kind.value}"
            if predicate is None
            else predicate
        ),
        value=expected_value if value is None else value,
        supporting_evidence=[
            reference(
                semantic,
                semantic_item_id=item.source_semantic_observation_id,
            )
        ],
    )
