# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from ayyo_interfaces.msg import AnonymousSemanticItem, AnonymousSemanticState
from ayyo_interfaces.srv import GetAnonymousSemanticState


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    scripts = str(PACKAGE_ROOT / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    path = PACKAGE_ROOT / 'scripts' / name
    spec = importlib.util.spec_from_file_location(f'ayyo_{name}_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response_with(*items: AnonymousSemanticItem) -> GetAnonymousSemanticState.Response:
    response = GetAnonymousSemanticState.Response()
    response.status = GetAnonymousSemanticState.Response.READY
    response.detail = 'current anonymous semantic evidence'
    response.robot_id = 'ayyo.robot.v1'
    response.snapshot_id = 'world-snapshot-' + '1' * 64
    response.snapshot_fingerprint = 'world_snapshot:sha256:' + '1' * 64
    response.queried_at.sec = 2
    if items:
        state = AnonymousSemanticState()
        state.observation_id = 'world-observation-' + '2' * 64
        state.observation_fingerprint = 'semantic_evidence:sha256:' + '2' * 64
        state.sensor_id = 'ayyo.camera.head.rgb.v1'
        state.reference_frame_id = 'head_camera_optical_frame'
        state.source_visual_observation_id = 'world-observation-' + '3' * 64
        state.source_visual_fingerprint = 'visual_frame:sha256:' + '3' * 64
        state.source_interpretation_observation_id = (
            'world-observation-' + '4' * 64
        )
        state.source_interpretation_fingerprint = (
            'visual_interpretation:sha256:' + '4' * 64
        )
        state.producer_id = 'ayyo.visual.semantic-query.fixture.v1'
        state.producer_kind = 'test_fixture'
        state.producer_model_id = 'none'
        state.producer_adapter_id = 'ayyo.visual.semantic-query.fixture-adapter.v1'
        state.producer_interface = 'ayyo.visual-interpretation.v1'
        state.source_observed_at.sec = 1
        state.result_at.sec = 1
        state.result_at.nanosec = 10
        state.source_kind = 'simulation'
        state.source_id = 'ros.camera.head.simulation.gz-harmonic.v1'
        state.source_clock = 'ros_simulation_time'
        state.source_transport = 'ros2'
        state.source_interface = 'sensor-msgs.image-camera-info.v1'
        state.freshness = AnonymousSemanticState.FRESH
        state.availability = AnonymousSemanticState.SENSOR_AVAILABLE
        state.items = list(items)
        response.semantic_states = [state]
    response.semantic_state_count = len(response.semantic_states)
    return response


def person_item() -> AnonymousSemanticItem:
    item = AnonymousSemanticItem()
    item.kind = AnonymousSemanticItem.PERSON
    item.source_semantic_observation_id = 'person-observation-sha256-' + '5' * 64
    item.source_detection_id = 'visual-detection-sha256-' + '6' * 64
    item.coordinate_space = 'normalized_image'
    item.x_min = 0.1
    item.y_min = 0.2
    item.x_max = 0.4
    item.y_max = 0.8
    item.has_object_category = False
    item.object_category = ''
    item.has_confidence = False
    item.confidence = 0.0
    return item


def object_item() -> AnonymousSemanticItem:
    item = AnonymousSemanticItem()
    item.kind = AnonymousSemanticItem.OBJECT
    item.source_semantic_observation_id = 'object-observation-sha256-' + '7' * 64
    item.source_detection_id = 'visual-detection-sha256-' + '8' * 64
    item.coordinate_space = 'normalized_image'
    item.x_min = 0.55
    item.y_min = 0.25
    item.x_max = 0.9
    item.y_max = 0.75
    item.has_object_category = True
    item.object_category = 'synthetic.demo-object.v1'
    item.has_confidence = True
    item.confidence = 0.0
    return item


def test_query_client_has_one_fixed_read_only_endpoint_and_bounded_waits() -> None:
    source = (PACKAGE_ROOT / 'scripts' / 'semantic_state_query.py').read_text(
        encoding='utf-8'
    )
    assert "QUERY_SERVICE = '/ayyo/world_model/get_anonymous_semantic_state'" in source
    assert 'wait_for_service(timeout_sec=5.0)' in source
    assert 'spin_until_future_complete(node, future, timeout_sec=5.0)' in source
    for forbidden in ('--topic', '--service', '--action', 'create_publisher', 'write('):
        assert forbidden not in source


def test_empty_response_json_is_deterministic_without_scene_absence_claim() -> None:
    transport = load_script('semantic_state_transport.py')
    response = response_with()
    response.detail = (
        'no currently retained anonymous semantic evidence; '
        'physical-scene occupancy remains unknown'
    )
    document = transport.semantic_response_document(response)
    assert document['semantic_states'] == []
    assert document['semantic_state_count'] == 0
    encoded = json.dumps(document, allow_nan=False, separators=(',', ':'), sort_keys=True)
    assert encoded == json.dumps(
        transport.semantic_response_document(response),
        allow_nan=False,
        separators=(',', ':'),
        sort_keys=True,
    )
    assert 'no people present' not in encoded
    assert 'no objects present' not in encoded
    assert 'scene is empty' not in encoded


def test_person_json_preserves_anonymity_and_absent_optionals() -> None:
    transport = load_script('semantic_state_transport.py')
    document = transport.semantic_response_document(response_with(person_item()))
    item = document['semantic_states'][0]['items'][0]
    assert item['kind'] == 'person'
    assert item['category'] is None
    assert item['confidence'] is None
    assert item['region'] == {
        'x_max': 0.4,
        'x_min': 0.1,
        'y_max': 0.8,
        'y_min': 0.2,
    }
    assert 'person_id' not in repr(document)
    assert 'entity_id' not in repr(document)


def test_object_zero_confidence_remains_distinct_from_absent_confidence() -> None:
    transport = load_script('semantic_state_transport.py')
    response = response_with(person_item(), object_item())
    items = transport.semantic_response_document(response)['semantic_states'][0]['items']
    by_kind = {item['kind']: item for item in items}
    assert by_kind['person']['confidence'] is None
    assert by_kind['object']['confidence'] == 0.0
    assert by_kind['object']['category'] == 'synthetic.demo-object.v1'
    assert by_kind['person']['confidence'] != by_kind['object']['confidence']


def test_multiple_states_preserve_transport_order_and_exact_source_fields() -> None:
    transport = load_script('semantic_state_transport.py')
    response = response_with(person_item())
    second = AnonymousSemanticState()
    for field_name in second.get_fields_and_field_types():
        setattr(second, field_name, getattr(response.semantic_states[0], field_name))
    second.observation_id = 'world-observation-' + '9' * 64
    response.semantic_states.append(second)
    response.semantic_state_count = 2
    first = transport.semantic_response_document(response)
    second_document = transport.semantic_response_document(response)
    assert first == second_document
    assert [state['observation_id'] for state in first['semantic_states']] == [
        'world-observation-' + '2' * 64,
        'world-observation-' + '9' * 64,
    ]
    assert first['semantic_states'][0]['source_visual_observation_id'].endswith(
        '3' * 64
    )
    assert first['semantic_states'][0][
        'source_interpretation_observation_id'
    ].endswith('4' * 64)


def test_client_rejects_mismatched_count_or_unknown_semantic_kind() -> None:
    transport = load_script('semantic_state_transport.py')
    response = response_with(person_item())
    response.semantic_state_count = 0
    try:
        transport.semantic_response_document(response)
    except ValueError as error:
        assert 'count' in str(error)
    else:
        raise AssertionError('mismatched semantic response count was accepted')
    response.semantic_state_count = 1
    response.semantic_states[0].items[0].kind = 255
    try:
        transport.semantic_response_document(response)
    except ValueError as error:
        assert 'unknown item kind' in str(error)
    else:
        raise AssertionError('unknown semantic item kind was accepted')
