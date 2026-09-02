from __future__ import annotations

import unittest
from dataclasses import fields, replace

from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    MAX_SEMANTIC_SOURCE_INTERPRETATIONS,
    ObjectObservation,
    PerceptionObservationValidationError,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
    PersonObservation,
    SemanticDetectionSource,
    semantic_observation_from_detection,
)
from ayyo_visual_evaluation import (
    DeterministicFixtureInvoker,
    VisualProducerEvaluator,
    VisualProducerRegistry,
    fixture_bundle,
)
from ayyo_world_model import (
    AYYO_ROBOT_ID,
    ImageRegion2D,
    ObservationClock,
    ObservationProvenance,
    ObservationSourceKind,
    ObservationTransport,
    SensorAvailability,
    SensorIdentity,
    SensorKind,
    VisualDetection,
    VisualEvaluationReference,
    VisualFrameObservation,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
    VisualProducerKind,
    VisualSemanticCategory,
)


CAMERA = SensorIdentity(
    "ayyo.camera.head.rgb.v1",
    SensorKind.RGB_CAMERA,
    "head_camera_optical_frame",
)
PROVENANCE = ObservationProvenance(
    ObservationSourceKind.TEST_FIXTURE,
    "test.camera.semantic-binding.v1",
    ObservationClock.TEST_TIME,
    ObservationTransport.DIRECT,
    "direct.visual-frame.v1",
)
PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.semantic-binding.v1",
    VisualProducerKind.TEST_FIXTURE,
    "none",
    "ayyo.visual.semantic-binding.adapter.v1",
    "ayyo.visual-interpretation.v1",
)
OTHER_PRODUCER = VisualInterpretationProducer(
    "ayyo.visual.semantic-binding.other.v1",
    VisualProducerKind.TEST_FIXTURE,
    "none",
    "ayyo.visual.semantic-binding.other-adapter.v1",
    "ayyo.visual-interpretation.v1",
)
REGION = ImageRegion2D(x_min=0.1, y_min=0.2, x_max=0.7, y_max=0.9)
OTHER_REGION = ImageRegion2D(x_min=0.2, y_min=0.2, x_max=0.8, y_max=0.9)


def frame(time_ns: int = 100, **overrides) -> VisualFrameObservation:
    values = {
        "robot_id": AYYO_ROBOT_ID,
        "sensor": CAMERA,
        "width": 32,
        "height": 24,
        "encoding": "rgb8",
        "step": 96,
        "data_size_bytes": 2_304,
        "is_bigendian": False,
        "calibration_id": "camera-calibration-sha256-" + "1" * 64,
        "observed_at_ns": time_ns,
        "provenance": PROVENANCE,
        "availability": SensorAvailability.AVAILABLE,
    }
    values.update(overrides)
    return VisualFrameObservation(**values)


def detection(
    source: VisualFrameObservation,
    *,
    category: VisualSemanticCategory,
    label: str,
    confidence: float | None,
    region: ImageRegion2D = REGION,
) -> VisualDetection:
    return VisualDetection(
        source_visual_observation_id=source.observation_id,
        category=category,
        label=label,
        region=region,
        confidence=confidence,
    )


def interpretation(
    source: VisualFrameObservation,
    *,
    detections: tuple[VisualDetection, ...] | None = None,
    result_at_ns: int | None = None,
    producer: VisualInterpretationProducer = PRODUCER,
    evaluation_reference: VisualEvaluationReference | None = None,
    **overrides,
) -> VisualInterpretationObservation:
    if detections is None:
        detections = (
            detection(
                source,
                category=VisualSemanticCategory.PERSON,
                label="person",
                confidence=0.75,
            ),
            detection(
                source,
                category=VisualSemanticCategory.OBJECT,
                label="cup",
                confidence=0.625,
            ),
        )
    values = {
        "robot_id": source.robot_id,
        "sensor": source.sensor,
        "reference_frame_id": source.sensor.frame_id,
        "source_visual_observation_id": source.observation_id,
        "source_visual_fingerprint": source.fingerprint,
        "observed_at_ns": source.observed_at_ns,
        "result_at_ns": (
            source.observed_at_ns + 1
            if result_at_ns is None
            else result_at_ns
        ),
        "producer": producer,
        "detections": detections,
        "provenance": source.provenance,
        "availability": source.availability,
        "evaluation_reference": evaluation_reference,
    }
    values.update(overrides)
    return VisualInterpretationObservation(**values)


def semantic(
    source_interpretation: VisualInterpretationObservation,
    category: VisualSemanticCategory,
):
    source_detection = next(
        item
        for item in source_interpretation.detections
        if item.category is category
    )
    return semantic_observation_from_detection(
        source_interpretation,
        detection_id=source_detection.detection_id,
    )


def clone_semantic(observation, **overrides):
    values = {
        "robot_id": observation.robot_id,
        "sensor": observation.sensor,
        "reference_frame_id": observation.reference_frame_id,
        "source_visual_observation_id": observation.source_visual_observation_id,
        "source_detection": observation.source_detection,
        "observed_at_ns": observation.observed_at_ns,
        "result_at_ns": observation.result_at_ns,
        "confidence": observation.confidence,
        "region": observation.region,
        "provenance": observation.provenance,
    }
    if type(observation) is ObjectObservation:
        values["category"] = observation.category
        observation_type = ObjectObservation
    else:
        observation_type = PersonObservation
    values.update(overrides)
    return observation_type(**values)


def boundary(
    *,
    freshness_ns: int = 100,
    retention_ttl_ns: int = 1_000,
    producers: tuple[VisualInterpretationProducer, ...] = (PRODUCER,),
) -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            sources=(PerceptionSourceContract(CAMERA, PROVENANCE),),
            freshness_ns=freshness_ns,
            retention_ttl_ns=retention_ttl_ns,
            permitted_future_skew_ns=5,
            visual_interpretation_producers=producers,
        )
    )


def admit(trust, observation, *, now: int, receipt: int):
    return trust.admit(
        observation,
        now_ns=now,
        received_at_monotonic_ns=receipt,
    )


def admit_visual_chain(trust, source, source_interpretation) -> None:
    assert (
        admit(
            trust,
            source,
            now=source.observed_at_ns,
            receipt=1,
        ).status
        is AdmissionStatus.ACCEPTED
    )
    assert (
        admit(
            trust,
            source_interpretation,
            now=source_interpretation.result_at_ns,
            receipt=2,
        ).status
        is AdmissionStatus.ACCEPTED
    )


class SemanticProducerBindingTest(unittest.TestCase):
    def test_exact_person_and_object_detections_produce_admitted_semantics(self) -> None:
        trust = boundary()
        source = frame()
        source_interpretation = interpretation(source)
        admit_visual_chain(trust, source, source_interpretation)
        person = semantic(source_interpretation, VisualSemanticCategory.PERSON)
        object_result = semantic(
            source_interpretation,
            VisualSemanticCategory.OBJECT,
        )
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, person, now=101, receipt=3).status,
        )
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, object_result, now=101, receipt=4).status,
        )
        self.assertEqual("cup", object_result.category)
        self.assertEqual(
            source_interpretation.observation_id,
            person.source_detection.visual_interpretation_observation_id,
        )

    def test_test_pattern_cannot_be_promoted_to_person_or_object(self) -> None:
        trust = boundary()
        source = frame()
        pattern = interpretation(
            source,
            detections=(
                detection(
                    source,
                    category=VisualSemanticCategory.TEST_PATTERN,
                    label="synthetic.test-pattern.v1",
                    confidence=None,
                ),
            ),
        )
        admit_visual_chain(trust, source, pattern)
        with self.assertRaises(PerceptionObservationValidationError):
            semantic_observation_from_detection(
                pattern,
                detection_id=pattern.detections[0].detection_id,
            )
        forged = PersonObservation(
            robot_id=pattern.robot_id,
            sensor=pattern.sensor,
            reference_frame_id=pattern.reference_frame_id,
            source_visual_observation_id=pattern.source_visual_observation_id,
            source_detection=SemanticDetectionSource(
                pattern.observation_id,
                pattern.detections[0].detection_id,
            ),
            observed_at_ns=pattern.observed_at_ns,
            result_at_ns=pattern.result_at_ns,
            confidence=None,
            region=pattern.detections[0].region,
            provenance=pattern.provenance,
        )
        self.assertIs(
            AdmissionReason.SEMANTIC_MAPPING_MISMATCH,
            admit(trust, forged, now=101, receipt=3).reason,
        )

    def test_bare_and_unadmitted_interpretation_claims_fail_closed(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        bare = PersonObservation(
            robot_id=source.robot_id,
            sensor=source.sensor,
            reference_frame_id=source.sensor.frame_id,
            source_visual_observation_id=source.observation_id,
            source_detection=SemanticDetectionSource(
                "world-observation-" + "9" * 64,
                "visual-detection-sha256-" + "8" * 64,
            ),
            observed_at_ns=source.observed_at_ns,
            result_at_ns=101,
            confidence=0.5,
            region=REGION,
            provenance=source.provenance,
        )
        self.assertIs(
            AdmissionReason.SOURCE_INTERPRETATION_NOT_ADMITTED,
            admit(trust, bare, now=101, receipt=2).reason,
        )
        unadmitted = interpretation(source)
        derived = semantic(unadmitted, VisualSemanticCategory.PERSON)
        self.assertIs(
            AdmissionReason.SOURCE_INTERPRETATION_NOT_ADMITTED,
            admit(trust, derived, now=101, receipt=3).reason,
        )

    def test_unknown_and_forged_detection_id_fails(self) -> None:
        trust = boundary()
        source = frame()
        result = interpretation(source)
        admit_visual_chain(trust, source, result)
        valid = semantic(result, VisualSemanticCategory.PERSON)
        unknown = clone_semantic(
            valid,
            source_detection=SemanticDetectionSource(
                result.observation_id,
                "visual-detection-sha256-" + "0" * 64,
            ),
        )
        self.assertIs(
            AdmissionReason.SOURCE_DETECTION_NOT_ADMITTED,
            admit(trust, unknown, now=101, receipt=3).reason,
        )

    def test_source_frame_substitution_fails(self) -> None:
        trust = boundary()
        first = frame(100)
        result = interpretation(first)
        admit_visual_chain(trust, first, result)
        second = frame(102)
        admit(trust, second, now=102, receipt=3)
        changed = clone_semantic(
            semantic(result, VisualSemanticCategory.PERSON),
            source_visual_observation_id=second.observation_id,
        )
        self.assertIs(
            AdmissionReason.SOURCE_FRAME_MISMATCH,
            admit(trust, changed, now=102, receipt=4).reason,
        )

    def test_producer_substitution_is_not_an_admitted_interpretation(self) -> None:
        trust = boundary(producers=(PRODUCER, OTHER_PRODUCER))
        source = frame()
        exact = interpretation(source)
        admit_visual_chain(trust, source, exact)
        substituted = interpretation(source, producer=OTHER_PRODUCER)
        claim = semantic(substituted, VisualSemanticCategory.PERSON)
        self.assertIs(
            AdmissionReason.SOURCE_INTERPRETATION_NOT_ADMITTED,
            admit(trust, claim, now=101, receipt=3).reason,
        )
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(
                trust,
                semantic(exact, VisualSemanticCategory.PERSON),
                now=101,
                receipt=4,
            ).status,
        )

    def test_robot_camera_frame_and_provenance_substitution_are_rejected(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        other_camera = SensorIdentity(
            "ayyo.camera.other.rgb.v1",
            SensorKind.RGB_CAMERA,
            CAMERA.frame_id,
        )
        other_frame_camera = SensorIdentity(
            CAMERA.sensor_id,
            SensorKind.RGB_CAMERA,
            "other_camera_optical_frame",
        )
        other_provenance = ObservationProvenance(
            ObservationSourceKind.TEST_FIXTURE,
            "test.camera.semantic-binding.other.v1",
            ObservationClock.TEST_TIME,
            ObservationTransport.DIRECT,
            "direct.visual-frame.v1",
        )
        cases = (
            (
                interpretation(source, robot_id="other.robot.v1"),
                AdmissionReason.WRONG_ROBOT_IDENTITY,
            ),
            (
                interpretation(
                    source,
                    sensor=other_camera,
                    reference_frame_id=other_camera.frame_id,
                ),
                AdmissionReason.UNKNOWN_SENSOR,
            ),
            (
                interpretation(
                    source,
                    sensor=other_frame_camera,
                    reference_frame_id=other_frame_camera.frame_id,
                ),
                AdmissionReason.FRAME_MISMATCH,
            ),
            (
                interpretation(source, provenance=other_provenance),
                AdmissionReason.PROVENANCE_NOT_ALLOWED,
            ),
        )
        for receipt, (substituted, reason) in enumerate(cases, start=2):
            with self.subTest(reason=reason):
                self.assertIs(
                    reason,
                    admit(
                        trust,
                        substituted,
                        now=101,
                        receipt=receipt,
                    ).reason,
                )

    def test_evaluated_producer_reference_substitution_fails(self) -> None:
        bundle = fixture_bundle(sample_count=1)
        registry = VisualProducerRegistry()
        registry.register(bundle.registration)
        evaluated = VisualProducerEvaluator(
            registry,
            DeterministicFixtureInvoker(),
        ).evaluate(
            producer_id=bundle.manifest.producer.producer_id,
            dataset=bundle.dataset,
            source=bundle.source,
            policy=bundle.policy,
            run_id="semantic-binding.evaluation.v1",
        ).admissions[0]
        source = evaluated.producer_result.source_frame
        exact = evaluated.observation
        trust = PerceptionTrustBoundary(
            PerceptionTrustConfig(
                robot_id=source.robot_id,
                source_clock=source.provenance.clock,
                sources=(
                    PerceptionSourceContract(source.sensor, source.provenance),
                ),
                freshness_ns=50_000_000,
                retention_ttl_ns=1_000_000_000,
                permitted_future_skew_ns=5_000_000,
                visual_interpretation_producers=(exact.producer,),
                visual_evaluation_requirements=(evaluated.requirement,),
            )
        )
        admit(trust, source, now=source.observed_at_ns, receipt=1)
        self.assertTrue(trust.authorize_evaluated_visual(evaluated))
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, exact, now=exact.result_at_ns, receipt=2).status,
        )
        changed_reference = replace(
            evaluated.reference,
            dataset_id="ayyo.dataset.substituted.v1",
        )
        changed = interpretation(
            source,
            detections=exact.detections,
            result_at_ns=exact.result_at_ns,
            producer=exact.producer,
            evaluation_reference=changed_reference,
        )
        self.assertIs(
            AdmissionReason.EVALUATION_MISMATCH,
            admit(trust, changed, now=changed.result_at_ns, receipt=3).reason,
        )
        forged = PersonObservation(
            robot_id=changed.robot_id,
            sensor=changed.sensor,
            reference_frame_id=changed.reference_frame_id,
            source_visual_observation_id=changed.source_visual_observation_id,
            source_detection=SemanticDetectionSource(
                changed.observation_id,
                changed.detections[0].detection_id,
            ),
            observed_at_ns=changed.observed_at_ns,
            result_at_ns=changed.result_at_ns,
            confidence=changed.detections[0].confidence,
            region=changed.detections[0].region,
            provenance=changed.provenance,
        )
        self.assertIs(
            AdmissionReason.SOURCE_INTERPRETATION_NOT_ADMITTED,
            admit(trust, forged, now=changed.result_at_ns, receipt=4).reason,
        )

    def test_person_object_category_substitution_fails_both_directions(self) -> None:
        trust = boundary()
        source = frame()
        result = interpretation(source)
        admit_visual_chain(trust, source, result)
        person = semantic(result, VisualSemanticCategory.PERSON)
        object_result = semantic(result, VisualSemanticCategory.OBJECT)
        person_as_object = ObjectObservation(
            robot_id=person.robot_id,
            sensor=person.sensor,
            reference_frame_id=person.reference_frame_id,
            source_visual_observation_id=person.source_visual_observation_id,
            source_detection=person.source_detection,
            observed_at_ns=person.observed_at_ns,
            result_at_ns=person.result_at_ns,
            category="human",
            confidence=person.confidence,
            region=person.region,
            provenance=person.provenance,
        )
        object_as_person = PersonObservation(
            robot_id=object_result.robot_id,
            sensor=object_result.sensor,
            reference_frame_id=object_result.reference_frame_id,
            source_visual_observation_id=(
                object_result.source_visual_observation_id
            ),
            source_detection=object_result.source_detection,
            observed_at_ns=object_result.observed_at_ns,
            result_at_ns=object_result.result_at_ns,
            confidence=object_result.confidence,
            region=object_result.region,
            provenance=object_result.provenance,
        )
        for claim in (person_as_object, object_as_person):
            with self.subTest(kind=type(claim).__name__):
                self.assertIs(
                    AdmissionReason.SEMANTIC_MAPPING_MISMATCH,
                    admit(trust, claim, now=101, receipt=3).reason,
                )

    def test_label_region_confidence_and_time_substitution_fail(self) -> None:
        trust = boundary()
        source = frame()
        result = interpretation(source)
        admit_visual_chain(trust, source, result)
        object_result = semantic(result, VisualSemanticCategory.OBJECT)
        cases = (
            clone_semantic(object_result, category="mug"),
            clone_semantic(object_result, region=OTHER_REGION),
            clone_semantic(object_result, confidence=0.5),
            clone_semantic(object_result, result_at_ns=102),
        )
        for index, claim in enumerate(cases, start=3):
            with self.subTest(index=index):
                self.assertIs(
                    AdmissionReason.SEMANTIC_MAPPING_MISMATCH,
                    admit(trust, claim, now=102, receipt=index).reason,
                )
        changed_acquisition = clone_semantic(
            object_result,
            observed_at_ns=99,
        )
        self.assertIs(
            AdmissionReason.SOURCE_FRAME_MISMATCH,
            admit(trust, changed_acquisition, now=102, receipt=7).reason,
        )

    def test_absent_confidence_is_preserved_not_fabricated(self) -> None:
        trust = boundary()
        source = frame()
        result = interpretation(
            source,
            detections=(
                detection(
                    source,
                    category=VisualSemanticCategory.OBJECT,
                    label="cup",
                    confidence=None,
                ),
            ),
        )
        admit_visual_chain(trust, source, result)
        observation = semantic(result, VisualSemanticCategory.OBJECT)
        self.assertIsNone(observation.confidence)
        self.assertIsNone(observation.document()["confidence"])
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, observation, now=101, receipt=3).status,
        )
        changed = clone_semantic(observation, confidence=0.0)
        self.assertIs(
            AdmissionReason.SEMANTIC_MAPPING_MISMATCH,
            admit(trust, changed, now=101, receipt=4).reason,
        )

    def test_duplicate_derivation_and_admission_are_deterministic(self) -> None:
        trust = boundary()
        source = frame()
        result = interpretation(source)
        admit_visual_chain(trust, source, result)
        first = semantic(result, VisualSemanticCategory.PERSON)
        second = semantic(result, VisualSemanticCategory.PERSON)
        self.assertEqual(first, second)
        self.assertEqual(first.document(), second.document())
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, first, now=101, receipt=3).status,
        )
        replay = admit(trust, second, now=101, receipt=4)
        self.assertIs(AdmissionStatus.DUPLICATE, replay.status)
        self.assertIs(AdmissionReason.DUPLICATE, replay.reason)

    def test_source_expiry_and_reset_invalidate_binding(self) -> None:
        trust = boundary(freshness_ns=50, retention_ttl_ns=100)
        source = frame()
        result = interpretation(source)
        admit_visual_chain(trust, source, result)
        claim = semantic(result, VisualSemanticCategory.PERSON)
        admit(trust, frame(201), now=201, receipt=3)
        self.assertIs(
            AdmissionReason.STALE_OBSERVATION,
            admit(trust, claim, now=201, receipt=4).reason,
        )

        trust = boundary()
        admit_visual_chain(trust, source, result)
        trust.reset()
        self.assertIs(
            AdmissionReason.SOURCE_FRAME_NOT_ADMITTED,
            admit(trust, claim, now=101, receipt=1).reason,
        )

    def test_rejected_tampering_does_not_poison_valid_evidence(self) -> None:
        trust = boundary()
        source = frame()
        result = interpretation(source)
        admit_visual_chain(trust, source, result)
        valid = semantic(result, VisualSemanticCategory.PERSON)
        tampered = clone_semantic(valid, region=OTHER_REGION)
        self.assertIs(
            AdmissionReason.SEMANTIC_MAPPING_MISMATCH,
            admit(trust, tampered, now=101, receipt=3).reason,
        )
        self.assertEqual(
            1,
            trust.stats().tracked_semantic_source_interpretation_count,
        )
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, valid, now=101, receipt=4).status,
        )

    def test_interpretation_retention_is_bounded_and_evicts_deterministically(self) -> None:
        trust = boundary(freshness_ns=500, retention_ttl_ns=1_000)
        source = frame()
        admit(trust, source, now=100, receipt=1)
        interpretations = []
        for index in range(MAX_SEMANTIC_SOURCE_INTERPRETATIONS + 1):
            result = interpretation(source, result_at_ns=101 + index)
            interpretations.append(result)
            self.assertIs(
                AdmissionStatus.ACCEPTED,
                admit(
                    trust,
                    result,
                    now=result.result_at_ns,
                    receipt=index + 2,
                ).status,
            )
        self.assertEqual(
            MAX_SEMANTIC_SOURCE_INTERPRETATIONS,
            trust.stats().tracked_semantic_source_interpretation_count,
        )
        first = semantic(interpretations[0], VisualSemanticCategory.PERSON)
        self.assertIs(
            AdmissionReason.SOURCE_INTERPRETATION_NOT_ADMITTED,
            admit(trust, first, now=165, receipt=67).reason,
        )
        newest = semantic(interpretations[-1], VisualSemanticCategory.PERSON)
        self.assertIs(
            AdmissionStatus.ACCEPTED,
            admit(trust, newest, now=165, receipt=68).status,
        )

    def test_forged_interpretation_and_detection_objects_fail_identity_rebuild(self) -> None:
        trust = boundary()
        source = frame()
        admit(trust, source, now=100, receipt=1)
        forged_interpretation = interpretation(source)
        object.__setattr__(
            forged_interpretation,
            "observation_id",
            "world-observation-" + "0" * 64,
        )
        self.assertIs(
            AdmissionReason.IDENTITY_MISMATCH,
            admit(trust, forged_interpretation, now=101, receipt=2).reason,
        )

        forged_detection_interpretation = interpretation(source)
        object.__setattr__(
            forged_detection_interpretation.detections[0],
            "detection_id",
            "visual-detection-sha256-" + "0" * 64,
        )
        self.assertIs(
            AdmissionReason.IDENTITY_MISMATCH,
            admit(
                trust,
                forged_detection_interpretation,
                now=101,
                receipt=3,
            ).reason,
        )

    def test_semantics_remain_anonymous_pixel_free_and_without_authority(self) -> None:
        source = frame()
        result = interpretation(source)
        person = semantic(result, VisualSemanticCategory.PERSON)
        object_result = semantic(result, VisualSemanticCategory.OBJECT)
        forbidden = {
            "actuator",
            "approval",
            "command",
            "data",
            "demographics",
            "emotion",
            "executive",
            "face_identity",
            "image",
            "manipulation",
            "memory",
            "motion",
            "movement",
            "name",
            "navigation",
            "person_id",
            "permission",
            "pixels",
            "raw_image",
            "runtime",
            "safety",
            "skill",
            "tracking_id",
        }
        for observation in (person, object_result):
            with self.subTest(kind=type(observation).__name__):
                self.assertFalse(
                    {item.name for item in fields(type(observation))} & forbidden
                )
                self.assertFalse(set(observation.document()) & forbidden)
        self.assertFalse(
            {item.name for item in fields(VisualInterpretationObservation)}
            & {"data", "image", "pixels", "raw_image"}
        )
        self.assertNotIn("person_id", person.document())
        with self.assertRaises(PerceptionObservationValidationError):
            clone_semantic(object_result, category="person")


if __name__ == "__main__":
    unittest.main()
