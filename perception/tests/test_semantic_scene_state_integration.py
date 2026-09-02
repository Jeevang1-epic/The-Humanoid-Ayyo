from __future__ import annotations

from dataclasses import fields
import unittest

from ayyo_perception import (
    AdmissionStatus,
    PerceptionObservationValidationError,
    semantic_observation_from_detection,
)
from ayyo_working_memory import (
    IngestionStatus,
    WorkingMemory,
    WorkingMemoryConfig,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    JointContract,
    ObservationIdentityError,
    RobotJointCatalog,
    SemanticEvidenceItem,
    VisualDetection,
    VisualInterpretationObservation,
    VisualSemanticCategory,
)

from test_semantic_world_projection import (
    CAMERA,
    PRODUCER,
    PROVENANCE,
    admit,
    boundary,
    frame,
    interpretation,
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


class SemanticSceneStateIntegrationTest(unittest.TestCase):
    def test_trusted_person_and_object_chain_reaches_only_anonymous_snapshot_state(self) -> None:
        trust = boundary()
        source = frame()
        source_interpretation = interpretation(source)
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, source, 100, 1).status,
        )
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, source_interpretation, 101, 2).status,
        )
        semantic_admissions = []
        for receipt, detection in enumerate(
            source_interpretation.detections,
            start=3,
        ):
            semantic = semantic_observation_from_detection(
                source_interpretation,
                detection_id=detection.detection_id,
            )
            admission = admit(trust, semantic, 101, receipt)
            self.assertIs(AdmissionStatus.ACCEPTED, admission.status)
            semantic_admissions.append(admission.observation_id)
        projected = trust.project_semantic_evidence(
            tuple(semantic_admissions)
        )

        store = WorkingMemory(
            catalog(),
            WorkingMemoryConfig(
                robot_id=AYYO_ROBOT_ID,
                source_clock=PROVENANCE.clock,
                allowed_provenance=(PROVENANCE,),
                sensors=(CAMERA,),
                freshness_ns=500_000_000,
                retention_ttl_ns=2_000_000_000,
                permitted_future_skew_ns=50_000_000,
                recent_evidence_capacity=16,
                environment_entity_capacity=1,
                semantic_evidence_capacity=8,
                visual_interpretation_producers=(PRODUCER,),
            ),
        )
        for receipt, observation in enumerate(
            (source, source_interpretation, projected),
            start=1,
        ):
            self.assertIs(
                IngestionStatus.ACCEPTED,
                store.ingest(
                    observation,
                    now_ns=101,
                    received_at_monotonic_ns=receipt,
                ).status,
            )
        snapshot = store.current_snapshot(now_ns=101)
        self.assertEqual(1, len(snapshot.semantic_states))
        self.assertEqual(2, len(snapshot.semantic_states[0].observation.items))
        self.assertEqual((), snapshot.entities)

        test_pattern = VisualInterpretationObservation(
            robot_id=source.robot_id,
            sensor=source.sensor,
            reference_frame_id=source.sensor.frame_id,
            source_visual_observation_id=source.observation_id,
            source_visual_fingerprint=source.fingerprint,
            observed_at_ns=source.observed_at_ns,
            result_at_ns=102,
            producer=PRODUCER,
            detections=(
                VisualDetection(
                    source_visual_observation_id=source.observation_id,
                    category=VisualSemanticCategory.TEST_PATTERN,
                    label="test.marker.v1",
                    region=ImageRegion2D(
                        x_min=0.1,
                        y_min=0.1,
                        x_max=0.9,
                        y_max=0.9,
                    ),
                    confidence=None,
                ),
            ),
            provenance=source.provenance,
            availability=source.availability,
        )
        with self.assertRaises(PerceptionObservationValidationError):
            semantic_observation_from_detection(
                test_pattern,
                detection_id=test_pattern.detections[0].detection_id,
            )

        object.__setattr__(
            projected.items[0],
            "region",
            ImageRegion2D(
                x_min=0.2,
                y_min=0.2,
                x_max=0.8,
                y_max=0.8,
            ),
        )
        with self.assertRaises(ObservationIdentityError):
            store.ingest(
                projected,
                now_ns=101,
                received_at_monotonic_ns=4,
            )

        forbidden = {
            "actuator",
            "command",
            "data",
            "entity_id",
            "image",
            "person_id",
            "pixels",
            "raw_image",
            "safety",
            "skill",
            "track_id",
        }
        self.assertFalse(
            {item.name for item in fields(SemanticEvidenceItem)} & forbidden
        )


if __name__ == "__main__":
    unittest.main()
