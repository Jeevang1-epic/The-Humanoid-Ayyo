# Copyright 2026 Ayyo Project Authors

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
INTERFACES_ROOT = REPOSITORY_ROOT / 'ros2_ws' / 'src' / 'ayyo_interfaces'


def interface_source(relative_path: str) -> str:
    return (INTERFACES_ROOT / relative_path).read_text(encoding='utf-8')


def test_semantic_interfaces_are_dedicated_typed_and_hard_bounded() -> None:
    item = interface_source('msg/AnonymousSemanticItem.msg')
    state = interface_source('msg/AnonymousSemanticState.msg')
    service = interface_source('srv/GetAnonymousSemanticState.srv')
    assert 'uint8 PERSON=1' in item
    assert 'uint8 OBJECT=2' in item
    assert 'ayyo_interfaces/AnonymousSemanticItem[<=32] items' in state
    assert 'ayyo_interfaces/AnonymousSemanticState[<=64] semantic_states' in service
    assert 'string<=256 robot_id' in service
    assert 'builtin_interfaces/Time queried_at' in service
    for source in (item, state, service):
        for line in source.splitlines():
            declaration = line.strip()
            if declaration.startswith('string'):
                assert declaration.startswith('string<=')
            if '[]' in declaration:
                raise AssertionError(f'unbounded array in semantic interface: {declaration}')


def test_semantic_item_preserves_region_category_and_optional_confidence() -> None:
    item = interface_source('msg/AnonymousSemanticItem.msg')
    for field in (
        'string<=96 source_semantic_observation_id',
        'string<=96 source_detection_id',
        'string<=32 coordinate_space',
        'float64 x_min',
        'float64 y_min',
        'float64 x_max',
        'float64 y_max',
        'bool has_object_category',
        'string<=64 object_category',
        'bool has_confidence',
        'float64 confidence',
    ):
        assert field in item
    assert item.index('bool has_confidence') < item.index('float64 confidence')


def test_semantic_state_preserves_exact_source_and_producer_provenance() -> None:
    state = interface_source('msg/AnonymousSemanticState.msg')
    for field in (
        'string<=96 observation_id',
        'string<=96 observation_fingerprint',
        'string<=96 source_visual_observation_id',
        'string<=96 source_visual_fingerprint',
        'string<=96 source_interpretation_observation_id',
        'string<=96 source_interpretation_fingerprint',
        'string<=128 producer_id',
        'string<=32 producer_kind',
        'string<=128 producer_model_id',
        'string<=128 producer_adapter_id',
        'string<=128 producer_interface',
        'string<=32 source_kind',
        'string<=256 source_id',
        'string<=32 source_clock',
        'string<=32 source_transport',
        'string<=256 source_interface',
        'builtin_interfaces/Time source_observed_at',
        'builtin_interfaces/Time result_at',
        'uint8 freshness',
        'uint8 availability',
    ):
        assert field in state


def test_semantic_interfaces_cannot_represent_pixels_identity_or_authority() -> None:
    source = '\n'.join(
        interface_source(path)
        for path in (
            'msg/AnonymousSemanticItem.msg',
            'msg/AnonymousSemanticState.msg',
            'srv/GetAnonymousSemanticState.srv',
        )
    ).lower()
    for forbidden in (
        'person_id',
        'object_id',
        'track_id',
        'owner_id',
        'face_id',
        'identity_id',
        'entity_id',
        'pixel',
        'image_data',
        'command',
        'authority',
        'execute',
        'motor',
    ):
        assert forbidden not in source
    assert 'observation_id' in source
    assert 'source_detection_id' in source


def test_interface_generator_owns_only_the_explicit_new_contracts() -> None:
    cmake = interface_source('CMakeLists.txt')
    for contract in (
        'msg/AnonymousSemanticItem.msg',
        'msg/AnonymousSemanticState.msg',
        'srv/GetAnonymousSemanticState.srv',
    ):
        assert f'"{contract}"' in cmake
    assert cmake.count('srv/GetAnonymousSemanticState.srv') == 1
