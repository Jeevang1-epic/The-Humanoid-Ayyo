#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Typed ROS projection for bounded anonymous World Model semantic state."""

from __future__ import annotations

from ayyo_interfaces.msg import AnonymousSemanticItem, AnonymousSemanticState
from ayyo_interfaces.srv import GetAnonymousSemanticState
from ayyo_world_model import (
    FreshnessState,
    MAX_SEMANTIC_EVIDENCE_ITEMS,
    MAX_SEMANTIC_EVIDENCE_STATES,
    SemanticEvidenceKind,
    SensorAvailability,
    WorldSnapshot,
)


def _assign_time(target, nanoseconds: int) -> None:
    target.sec = nanoseconds // 1_000_000_000
    target.nanosec = nanoseconds % 1_000_000_000


def _nanoseconds(value) -> int:
    return value.sec * 1_000_000_000 + value.nanosec


def _availability_code(availability: SensorAvailability) -> int:
    return {
        SensorAvailability.UNAVAILABLE: AnonymousSemanticState.SENSOR_UNAVAILABLE,
        SensorAvailability.AVAILABLE: AnonymousSemanticState.SENSOR_AVAILABLE,
        SensorAvailability.DEGRADED: AnonymousSemanticState.SENSOR_DEGRADED,
        SensorAvailability.ERROR: AnonymousSemanticState.SENSOR_ERROR,
        SensorAvailability.STALE: AnonymousSemanticState.SENSOR_STALE,
    }[availability]


def populate_semantic_response(
    response: GetAnonymousSemanticState.Response,
    snapshot: WorldSnapshot,
    *,
    queried_at_ns: int,
) -> GetAnonymousSemanticState.Response:
    """Serialize one immutable snapshot without reading or mutating any source."""
    if type(snapshot) is not WorldSnapshot:
        raise TypeError('semantic transport requires one WorldSnapshot')
    if len(snapshot.semantic_states) > MAX_SEMANTIC_EVIDENCE_STATES:
        raise ValueError('semantic snapshot exceeds its transport bound')
    response.status = GetAnonymousSemanticState.Response.READY
    response.detail = (
        'no currently retained anonymous semantic evidence; '
        'physical-scene occupancy remains unknown'
        if not snapshot.semantic_states
        else 'current anonymous semantic evidence projected from one WorldSnapshot'
    )
    response.robot_id = snapshot.robot.robot_id
    response.snapshot_id = snapshot.snapshot_id
    response.snapshot_fingerprint = str(snapshot.version)
    _assign_time(response.queried_at, queried_at_ns)
    response.semantic_state_count = len(snapshot.semantic_states)
    for semantic in snapshot.semantic_states:
        observation = semantic.observation
        if len(observation.items) > MAX_SEMANTIC_EVIDENCE_ITEMS:
            raise ValueError('semantic evidence batch exceeds its transport bound')
        state_message = AnonymousSemanticState()
        state_message.observation_id = observation.observation_id
        state_message.observation_fingerprint = str(observation.fingerprint)
        state_message.sensor_id = observation.sensor.sensor_id
        state_message.reference_frame_id = observation.reference_frame_id
        state_message.source_visual_observation_id = (
            observation.source_visual_observation_id
        )
        state_message.source_visual_fingerprint = str(
            observation.source_visual_fingerprint
        )
        state_message.source_interpretation_observation_id = (
            observation.source_interpretation_observation_id
        )
        state_message.source_interpretation_fingerprint = str(
            observation.source_interpretation_fingerprint
        )
        state_message.producer_id = observation.producer.producer_id
        state_message.producer_kind = observation.producer.kind.value
        state_message.producer_model_id = observation.producer.model_id
        state_message.producer_adapter_id = observation.producer.adapter_id
        state_message.producer_interface = observation.producer.interface
        state_message.has_evaluation_reference = (
            observation.evaluation_reference_sha256 is not None
        )
        state_message.evaluation_reference_sha256 = (
            ''
            if observation.evaluation_reference_sha256 is None
            else observation.evaluation_reference_sha256
        )
        _assign_time(state_message.source_observed_at, observation.observed_at_ns)
        _assign_time(state_message.result_at, observation.result_at_ns)
        state_message.source_kind = observation.provenance.source_kind.value
        state_message.source_id = observation.provenance.source_id
        state_message.source_clock = observation.provenance.clock.value
        state_message.source_transport = observation.provenance.transport.value
        state_message.source_interface = observation.provenance.interface
        state_message.freshness = (
            AnonymousSemanticState.FRESH
            if semantic.freshness is FreshnessState.FRESH
            else AnonymousSemanticState.STALE
        )
        state_message.availability = _availability_code(semantic.availability)
        for item in observation.items:
            item_message = AnonymousSemanticItem()
            item_message.kind = (
                AnonymousSemanticItem.PERSON
                if item.kind is SemanticEvidenceKind.PERSON
                else AnonymousSemanticItem.OBJECT
            )
            item_message.source_semantic_observation_id = (
                item.source_semantic_observation_id
            )
            item_message.source_detection_id = item.source_detection_id
            item_message.coordinate_space = item.region.coordinate_space.value
            item_message.x_min = item.region.x_min
            item_message.y_min = item.region.y_min
            item_message.x_max = item.region.x_max
            item_message.y_max = item.region.y_max
            item_message.has_object_category = (
                item.kind is SemanticEvidenceKind.OBJECT
            )
            item_message.object_category = (
                '' if item.category is None else item.category
            )
            item_message.has_confidence = item.confidence is not None
            item_message.confidence = (
                0.0 if item.confidence is None else item.confidence
            )
            state_message.items.append(item_message)
        response.semantic_states.append(state_message)
    return response


def semantic_response_document(response) -> dict[str, object]:
    """Return deterministic JSON-ready data with explicit optional semantics."""
    kind_names = {
        AnonymousSemanticItem.PERSON: 'person',
        AnonymousSemanticItem.OBJECT: 'object',
    }
    freshness_names = {
        AnonymousSemanticState.FRESH: 'fresh',
        AnonymousSemanticState.STALE: 'stale',
    }
    availability_names = {
        AnonymousSemanticState.SENSOR_UNAVAILABLE: 'unavailable',
        AnonymousSemanticState.SENSOR_AVAILABLE: 'available',
        AnonymousSemanticState.SENSOR_DEGRADED: 'degraded',
        AnonymousSemanticState.SENSOR_ERROR: 'error',
        AnonymousSemanticState.SENSOR_STALE: 'stale',
    }
    states = []
    for state in response.semantic_states:
        items = []
        for item in state.items:
            if item.kind not in kind_names:
                raise ValueError('semantic response contains an unknown item kind')
            items.append(
                {
                    'category': (
                        item.object_category
                        if item.has_object_category
                        else None
                    ),
                    'confidence': item.confidence if item.has_confidence else None,
                    'coordinate_space': item.coordinate_space,
                    'kind': kind_names[item.kind],
                    'region': {
                        'x_max': item.x_max,
                        'x_min': item.x_min,
                        'y_max': item.y_max,
                        'y_min': item.y_min,
                    },
                    'source_detection_id': item.source_detection_id,
                    'source_semantic_observation_id': (
                        item.source_semantic_observation_id
                    ),
                }
            )
        if state.freshness not in freshness_names:
            raise ValueError('semantic response contains unknown freshness')
        if state.availability not in availability_names:
            raise ValueError('semantic response contains unknown availability')
        states.append(
            {
                'availability': availability_names[state.availability],
                'evaluation_reference_sha256': (
                    state.evaluation_reference_sha256
                    if state.has_evaluation_reference
                    else None
                ),
                'freshness': freshness_names[state.freshness],
                'items': items,
                'observation_fingerprint': state.observation_fingerprint,
                'observation_id': state.observation_id,
                'producer': {
                    'adapter_id': state.producer_adapter_id,
                    'id': state.producer_id,
                    'interface': state.producer_interface,
                    'kind': state.producer_kind,
                    'model_id': state.producer_model_id,
                },
                'reference_frame_id': state.reference_frame_id,
                'result_at_ns': _nanoseconds(state.result_at),
                'sensor_id': state.sensor_id,
                'source_interpretation_fingerprint': (
                    state.source_interpretation_fingerprint
                ),
                'source_interpretation_observation_id': (
                    state.source_interpretation_observation_id
                ),
                'source_observed_at_ns': _nanoseconds(
                    state.source_observed_at
                ),
                'source_provenance': {
                    'clock': state.source_clock,
                    'id': state.source_id,
                    'interface': state.source_interface,
                    'kind': state.source_kind,
                    'transport': state.source_transport,
                },
                'source_visual_fingerprint': state.source_visual_fingerprint,
                'source_visual_observation_id': (
                    state.source_visual_observation_id
                ),
            }
        )
    if response.semantic_state_count != len(states):
        raise ValueError('semantic response count does not match its bounded states')
    return {
        'detail': response.detail,
        'queried_at_ns': _nanoseconds(response.queried_at),
        'robot_id': response.robot_id,
        'semantic_state_count': response.semantic_state_count,
        'semantic_states': states,
        'snapshot_fingerprint': response.snapshot_fingerprint,
        'snapshot_id': response.snapshot_id,
        'status': response.status,
    }
