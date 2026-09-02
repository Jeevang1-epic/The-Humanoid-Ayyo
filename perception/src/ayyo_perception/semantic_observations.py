"""Compact person and object observation contracts without authority."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import NoReturn, TypeAlias

from ayyo_world_model import (
    ImageRegion2D,
    MAX_OBSERVATION_TIME_NS,
    MAX_VISUAL_LABEL_LENGTH,
    ObservationIdentityError,
    ObservationProvenance,
    SensorIdentity,
    SensorKind,
    VisualDetection,
    VisualInterpretationObservation,
    VisualSemanticCategory,
    WorldModelValidationError,
    rebuild_observation,
)

from .errors import (
    PerceptionObservationIdentityError,
    PerceptionObservationValidationError,
)


_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SOURCE_VISUAL_OBSERVATION_ID = re.compile(r"^world-observation-[0-9a-f]{64}$")
_VISUAL_DETECTION_ID = re.compile(
    r"^visual-detection-sha256-[0-9a-f]{64}$"
)


class SemanticObservationKind(StrEnum):
    """The only semantic facts represented by this contract slice."""

    PERSON = "person"
    OBJECT = "object"


def _fail(detail: str) -> NoReturn:
    raise PerceptionObservationValidationError(detail)


def _identifier(value: object, field_name: str, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _IDENTIFIER.fullmatch(value) is None
    ):
        _fail(f"{field_name} must be a bounded lowercase ASCII identifier")
    return value


def _confidence(value: object) -> float | None:
    if value is None:
        return None
    if type(value) not in {int, float} or not math.isfinite(value):
        _fail("semantic observation confidence must be finite")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        _fail("semantic observation confidence must be between 0.0 and 1.0")
    return 0.0 if result == 0.0 else result


def _canonical_sha256(document: dict[str, object]) -> str:
    encoded = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticDetectionSource:
    """Compact content-addressed link to one interpreted visual detection."""

    visual_interpretation_observation_id: str
    visual_detection_id: str

    def __post_init__(self) -> None:
        if (
            type(self.visual_interpretation_observation_id) is not str
            or _SOURCE_VISUAL_OBSERVATION_ID.fullmatch(
                self.visual_interpretation_observation_id
            )
            is None
        ):
            _fail("semantic source interpretation identity is malformed")
        if (
            type(self.visual_detection_id) is not str
            or _VISUAL_DETECTION_ID.fullmatch(self.visual_detection_id) is None
        ):
            _fail("semantic source detection identity is malformed")

    def document(self) -> dict[str, str]:
        return {
            "visual_detection_id": self.visual_detection_id,
            "visual_interpretation_observation_id": (
                self.visual_interpretation_observation_id
            ),
        }


def _validate_common(
    *,
    kind: SemanticObservationKind,
    robot_id: str,
    sensor: SensorIdentity,
    reference_frame_id: str,
    source_visual_observation_id: str,
    source_detection: SemanticDetectionSource,
    observed_at_ns: int,
    result_at_ns: int,
    confidence: float | None,
    region: ImageRegion2D,
    provenance: ObservationProvenance,
    specific: dict[str, object],
    observation_id: str | None,
) -> tuple[float | None, str]:
    _identifier(robot_id, "semantic observation robot_id")
    if (
        type(sensor) is not SensorIdentity
        or sensor.kind is not SensorKind.RGB_CAMERA
    ):
        _fail("semantic observation requires one typed RGB camera")
    if (
        type(reference_frame_id) is not str
        or reference_frame_id != sensor.frame_id
    ):
        _fail("semantic observation frame must match its camera optical frame")
    if (
        type(source_visual_observation_id) is not str
        or _SOURCE_VISUAL_OBSERVATION_ID.fullmatch(
            source_visual_observation_id
        )
        is None
    ):
        _fail("semantic observation source-frame identity is malformed")
    if type(source_detection) is not SemanticDetectionSource:
        _fail("semantic observation requires one typed detection source")
    if (
        type(observed_at_ns) is not int
        or type(result_at_ns) is not int
        or not 0 <= observed_at_ns <= result_at_ns <= MAX_OBSERVATION_TIME_NS
    ):
        _fail("semantic observation timestamps are malformed or reversed")
    confidence_value = _confidence(confidence)
    if type(region) is not ImageRegion2D:
        _fail("semantic observation region must be a normalized ImageRegion2D")
    if type(provenance) is not ObservationProvenance:
        _fail("semantic observation provenance must be typed")
    document: dict[str, object] = {
        "confidence": confidence_value,
        "kind": kind.value,
        "observed_at_ns": observed_at_ns,
        "provenance": provenance.document(),
        "reference_frame_id": reference_frame_id,
        "region": region.document(),
        "result_at_ns": result_at_ns,
        "robot_id": robot_id,
        "schema": f"ayyo.{kind.value}-observation.v1",
        "sensor": sensor.document(),
        "source_detection": source_detection.document(),
        "source_visual_observation_id": source_visual_observation_id,
        **specific,
    }
    semantic_digest = _canonical_sha256(document)
    derived_id = f"{kind.value}-observation-sha256-{semantic_digest}"
    if observation_id is not None and observation_id != derived_id:
        raise PerceptionObservationIdentityError(
            "semantic observation identity does not match its content"
        )
    return confidence_value, derived_id


def _common_document(observation) -> dict[str, object]:
    return {
        "confidence": observation.confidence,
        "kind": observation.kind.value,
        "observation_id": observation.observation_id,
        "observed_at_ns": observation.observed_at_ns,
        "provenance": observation.provenance.document(),
        "reference_frame_id": observation.reference_frame_id,
        "region": observation.region.document(),
        "result_at_ns": observation.result_at_ns,
        "robot_id": observation.robot_id,
        "sensor": observation.sensor.document(),
        "source_detection": observation.source_detection.document(),
        "source_visual_observation_id": (
            observation.source_visual_observation_id
        ),
    }


@dataclass(frozen=True, slots=True, init=False)
class PersonObservation:
    """One person region without biometric or persistent identity."""

    kind: SemanticObservationKind
    robot_id: str
    sensor: SensorIdentity
    reference_frame_id: str
    source_visual_observation_id: str
    source_detection: SemanticDetectionSource
    observed_at_ns: int
    result_at_ns: int
    confidence: float | None
    region: ImageRegion2D
    provenance: ObservationProvenance
    observation_id: str

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        reference_frame_id: str,
        source_visual_observation_id: str,
        source_detection: SemanticDetectionSource,
        observed_at_ns: int,
        result_at_ns: int,
        confidence: float | None,
        region: ImageRegion2D,
        provenance: ObservationProvenance,
        observation_id: str | None = None,
    ) -> None:
        kind = SemanticObservationKind.PERSON
        confidence_value, derived_id = _validate_common(
            kind=kind,
            robot_id=robot_id,
            sensor=sensor,
            reference_frame_id=reference_frame_id,
            source_visual_observation_id=source_visual_observation_id,
            source_detection=source_detection,
            observed_at_ns=observed_at_ns,
            result_at_ns=result_at_ns,
            confidence=confidence,
            region=region,
            provenance=provenance,
            specific={},
            observation_id=observation_id,
        )
        for field_name, value in (
            ("kind", kind),
            ("robot_id", robot_id),
            ("sensor", sensor),
            ("reference_frame_id", reference_frame_id),
            ("source_visual_observation_id", source_visual_observation_id),
            ("source_detection", source_detection),
            ("observed_at_ns", observed_at_ns),
            ("result_at_ns", result_at_ns),
            ("confidence", confidence_value),
            ("region", region),
            ("provenance", provenance),
            ("observation_id", derived_id),
        ):
            object.__setattr__(self, field_name, value)

    def document(self) -> dict[str, object]:
        return _common_document(self)


@dataclass(frozen=True, slots=True, init=False)
class ObjectObservation:
    """One bounded object-category region; it is evidence, never a command."""

    kind: SemanticObservationKind
    robot_id: str
    sensor: SensorIdentity
    reference_frame_id: str
    source_visual_observation_id: str
    source_detection: SemanticDetectionSource
    observed_at_ns: int
    result_at_ns: int
    category: str
    confidence: float | None
    region: ImageRegion2D
    provenance: ObservationProvenance
    observation_id: str

    def __init__(
        self,
        *,
        robot_id: str,
        sensor: SensorIdentity,
        reference_frame_id: str,
        source_visual_observation_id: str,
        source_detection: SemanticDetectionSource,
        observed_at_ns: int,
        result_at_ns: int,
        category: str,
        confidence: float | None,
        region: ImageRegion2D,
        provenance: ObservationProvenance,
        observation_id: str | None = None,
    ) -> None:
        kind = SemanticObservationKind.OBJECT
        category_value = _identifier(
            category,
            "object observation category",
            maximum=MAX_VISUAL_LABEL_LENGTH,
        )
        if category_value == SemanticObservationKind.PERSON.value:
            _fail("object observation category cannot substitute for a person")
        confidence_value, derived_id = _validate_common(
            kind=kind,
            robot_id=robot_id,
            sensor=sensor,
            reference_frame_id=reference_frame_id,
            source_visual_observation_id=source_visual_observation_id,
            source_detection=source_detection,
            observed_at_ns=observed_at_ns,
            result_at_ns=result_at_ns,
            confidence=confidence,
            region=region,
            provenance=provenance,
            specific={"category": category_value},
            observation_id=observation_id,
        )
        for field_name, value in (
            ("kind", kind),
            ("robot_id", robot_id),
            ("sensor", sensor),
            ("reference_frame_id", reference_frame_id),
            ("source_visual_observation_id", source_visual_observation_id),
            ("source_detection", source_detection),
            ("observed_at_ns", observed_at_ns),
            ("result_at_ns", result_at_ns),
            ("category", category_value),
            ("confidence", confidence_value),
            ("region", region),
            ("provenance", provenance),
            ("observation_id", derived_id),
        ):
            object.__setattr__(self, field_name, value)

    def document(self) -> dict[str, object]:
        return {**_common_document(self), "category": self.category}


SemanticObservation: TypeAlias = PersonObservation | ObjectObservation


def semantic_observation_from_detection(
    interpretation: VisualInterpretationObservation,
    *,
    detection_id: str,
) -> SemanticObservation:
    """Map one exact typed detection without guessing or fabricating facts."""
    if type(interpretation) is not VisualInterpretationObservation:
        _fail("semantic source must be one visual interpretation")
    try:
        rebuilt = rebuild_observation(interpretation)
    except (ObservationIdentityError, WorldModelValidationError) as error:
        detail = getattr(error, "detail", str(error))
        _fail(f"semantic source interpretation is invalid: {detail}")
    if type(rebuilt) is not VisualInterpretationObservation:
        _fail("semantic source must be one visual interpretation")
    source = SemanticDetectionSource(
        visual_interpretation_observation_id=rebuilt.observation_id,
        visual_detection_id=detection_id,
    )
    matches = tuple(
        detection
        for detection in rebuilt.detections
        if detection.detection_id == source.visual_detection_id
    )
    if len(matches) != 1:
        _fail("semantic source detection is not present in the interpretation")
    detection: VisualDetection = matches[0]
    common = {
        "robot_id": rebuilt.robot_id,
        "sensor": rebuilt.sensor,
        "reference_frame_id": rebuilt.reference_frame_id,
        "source_visual_observation_id": rebuilt.source_visual_observation_id,
        "source_detection": source,
        "observed_at_ns": rebuilt.observed_at_ns,
        "result_at_ns": rebuilt.result_at_ns,
        "confidence": detection.confidence,
        "region": detection.region,
        "provenance": rebuilt.provenance,
    }
    if detection.category is VisualSemanticCategory.PERSON:
        return PersonObservation(**common)
    if detection.category is VisualSemanticCategory.OBJECT:
        return ObjectObservation(category=detection.label, **common)
    _fail("visual detection category cannot produce person or object evidence")


def rebuild_semantic_observation(
    observation: SemanticObservation,
) -> SemanticObservation:
    """Reconstruct one semantic observation and recheck its content identity."""
    if type(observation) is PersonObservation:
        return PersonObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            reference_frame_id=observation.reference_frame_id,
            source_visual_observation_id=(
                observation.source_visual_observation_id
            ),
            source_detection=observation.source_detection,
            observed_at_ns=observation.observed_at_ns,
            result_at_ns=observation.result_at_ns,
            confidence=observation.confidence,
            region=observation.region,
            provenance=observation.provenance,
            observation_id=observation.observation_id,
        )
    if type(observation) is ObjectObservation:
        return ObjectObservation(
            robot_id=observation.robot_id,
            sensor=observation.sensor,
            reference_frame_id=observation.reference_frame_id,
            source_visual_observation_id=(
                observation.source_visual_observation_id
            ),
            source_detection=observation.source_detection,
            observed_at_ns=observation.observed_at_ns,
            result_at_ns=observation.result_at_ns,
            category=observation.category,
            confidence=observation.confidence,
            region=observation.region,
            provenance=observation.provenance,
            observation_id=observation.observation_id,
        )
    _fail("semantic observation has an unsupported concrete type")
