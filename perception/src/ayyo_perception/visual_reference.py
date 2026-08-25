"""Deterministic test-only visual interpretation adapter."""

from __future__ import annotations

from ayyo_world_model import (
    ImageRegion2D,
    SensorAvailability,
    VisualDetection,
    VisualFrameObservation,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
    VisualProducerKind,
    VisualSemanticCategory,
    rebuild_observation,
)

from .errors import PerceptionConfigurationError
from .models import validate_time


REFERENCE_VISUAL_PRODUCER = VisualInterpretationProducer(
    producer_id="ayyo.visual.reference.synthetic.v1",
    kind=VisualProducerKind.TEST_FIXTURE,
    model_id="none",
    adapter_id="ayyo.visual.reference.adapter.v1",
    interface="ayyo.visual-interpretation.v1",
)


class DeterministicVisualReferenceAdapter:
    """Create one explicit synthetic marker result from admitted frame metadata.

    This adapter contains no model, pixels, randomness, network access, or
    confidence estimate. It exists only to exercise the interpretation path.
    """

    __slots__ = ()

    @property
    def producer(self) -> VisualInterpretationProducer:
        return REFERENCE_VISUAL_PRODUCER

    def interpret(
        self,
        frame: VisualFrameObservation,
        *,
        result_at_ns: int,
    ) -> VisualInterpretationObservation:
        rebuilt = rebuild_observation(frame)
        if type(rebuilt) is not VisualFrameObservation:
            raise PerceptionConfigurationError(
                "reference visual adapter requires admitted visual-frame metadata"
            )
        result_time = validate_time(result_at_ns, "visual result time")
        if result_time < rebuilt.observed_at_ns:
            raise PerceptionConfigurationError(
                "visual result cannot precede source acquisition"
            )
        if rebuilt.availability not in {
            SensorAvailability.AVAILABLE,
            SensorAvailability.DEGRADED,
        }:
            raise PerceptionConfigurationError(
                "unavailable visual frames cannot be interpreted"
            )
        detection = VisualDetection(
            source_visual_observation_id=rebuilt.observation_id,
            category=VisualSemanticCategory.TEST_PATTERN,
            label="synthetic.test-pattern.v1",
            region=ImageRegion2D(
                x_min=0.25,
                y_min=0.25,
                x_max=0.75,
                y_max=0.75,
            ),
            confidence=None,
        )
        return VisualInterpretationObservation(
            robot_id=rebuilt.robot_id,
            sensor=rebuilt.sensor,
            reference_frame_id=rebuilt.sensor.frame_id,
            source_visual_observation_id=rebuilt.observation_id,
            source_visual_fingerprint=rebuilt.fingerprint,
            observed_at_ns=rebuilt.observed_at_ns,
            result_at_ns=result_time,
            producer=self.producer,
            detections=(detection,),
            provenance=rebuilt.provenance,
            availability=rebuilt.availability,
        )
