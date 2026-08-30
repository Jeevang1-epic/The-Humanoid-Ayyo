from __future__ import annotations

from dataclasses import replace

from ayyo_depth_camera import (
    DepthLifecycleAdapter,
    DepthSourceRegistry,
    depth_simulation_bundle,
    depth_test_fixture_bundle,
    fixture_depth_camera_info_metadata,
    fixture_depth_image_metadata,
)
from ayyo_perception import (
    AdmissionReason,
    AdmissionStatus,
    PerceptionSourceContract,
    PerceptionTrustBoundary,
    PerceptionTrustConfig,
)
from ayyo_world_model import AYYO_ROBOT_ID, ObservationClock


def sealed(bundle, observed_at_ns: int = 1_000):
    registry = DepthSourceRegistry()
    registry.register(bundle.source)
    adapter = DepthLifecycleAdapter(registry)
    adapter.configure(bundle.source.source_id, bundle.calibration)
    session = adapter.activate()
    adapter.submit_camera_info(
        fixture_depth_camera_info_metadata(bundle, session, observed_at_ns),
        now_ns=observed_at_ns,
    )
    admission = adapter.submit_image(
        fixture_depth_image_metadata(
            bundle,
            session,
            observed_at_ns,
            encoding=bundle.source.encodings[0],
        ),
        now_ns=observed_at_ns,
    )
    assert admission is not None
    return admission


def trust(bundle) -> PerceptionTrustBoundary:
    return PerceptionTrustBoundary(
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=bundle.source.provenance.clock,
            sources=(
                PerceptionSourceContract(
                    bundle.source.sensor,
                    bundle.source.provenance,
                ),
            ),
            depth_camera_requirements=(bundle.source.requirement(),),
            freshness_ns=500,
            retention_ttl_ns=2_000,
            permitted_future_skew_ns=10,
        )
    )


def test_every_depth_source_requires_exact_adapter_requirement() -> None:
    bundle = depth_test_fixture_bundle()
    try:
        PerceptionTrustConfig(
            robot_id=AYYO_ROBOT_ID,
            source_clock=ObservationClock.TEST_TIME,
            sources=(PerceptionSourceContract(bundle.source.sensor, bundle.source.provenance),),
        )
    except ValueError as error:
        assert 'every depth source requires' in str(error)
    else:
        raise AssertionError('unsealed depth source was accepted by configuration')


def test_bare_depth_observation_cannot_bypass_sealed_authorization() -> None:
    bundle = depth_test_fixture_bundle()
    admission = sealed(bundle)
    result = trust(bundle).admit(
        admission.frame,
        now_ns=1_000,
        received_at_monotonic_ns=1,
    )
    assert result.status is AdmissionStatus.REJECTED
    assert result.reason is AdmissionReason.DEPTH_CAMERA_NOT_AUTHORIZED


def test_sealed_depth_and_health_are_each_consumed_once() -> None:
    bundle = depth_test_fixture_bundle()
    admission = sealed(bundle)
    boundary = trust(bundle)
    assert boundary.authorize_depth_camera(admission)
    frame = boundary.admit(
        admission.frame,
        now_ns=1_000,
        received_at_monotonic_ns=1,
    )
    health = boundary.admit(
        admission.health,
        now_ns=1_000,
        received_at_monotonic_ns=2,
    )
    assert frame.status is AdmissionStatus.ACCEPTED
    assert health.status is AdmissionStatus.ACCEPTED
    assert boundary.stats().tracked_depth_camera_count == 0


def test_reset_discards_unused_depth_authorization() -> None:
    bundle = depth_test_fixture_bundle()
    admission = sealed(bundle)
    boundary = trust(bundle)
    assert boundary.authorize_depth_camera(admission)
    boundary.reset()
    result = boundary.admit(
        admission.frame,
        now_ns=1_000,
        received_at_monotonic_ns=1,
    )
    assert result.reason is AdmissionReason.DEPTH_CAMERA_NOT_AUTHORIZED


def test_simulation_cannot_substitute_for_test_profile() -> None:
    test_bundle = depth_test_fixture_bundle()
    simulation_admission = sealed(depth_simulation_bundle(), 1_000)
    boundary = trust(test_bundle)
    assert not boundary.authorize_depth_camera(simulation_admission)
    result = boundary.admit(
        simulation_admission.frame,
        now_ns=1_000,
        received_at_monotonic_ns=1,
    )
    assert result.status is AdmissionStatus.REJECTED


def test_unknown_producer_requirement_is_not_authorized() -> None:
    bundle = depth_test_fixture_bundle()
    admission = sealed(bundle)
    forged_requirement = replace(
        admission.requirement,
        producer_id='unknown.depth.producer.v1',
    )
    object.__setattr__(admission, 'requirement', forged_requirement)
    assert not trust(bundle).authorize_depth_camera(admission)


def test_rejected_bypass_does_not_poison_later_valid_evidence() -> None:
    bundle = depth_test_fixture_bundle()
    admission = sealed(bundle)
    boundary = trust(bundle)
    rejected = boundary.admit(
        admission.frame,
        now_ns=1_000,
        received_at_monotonic_ns=1,
    )
    assert rejected.status is AdmissionStatus.REJECTED
    assert boundary.authorize_depth_camera(admission)
    accepted = boundary.admit(
        admission.frame,
        now_ns=1_000,
        received_at_monotonic_ns=2,
    )
    assert accepted.status is AdmissionStatus.ACCEPTED


def test_out_of_order_depth_is_rejected_after_newer_admission() -> None:
    bundle = depth_test_fixture_bundle()
    newer = sealed(bundle, 1_001)
    older = sealed(bundle, 1_000)
    boundary = trust(bundle)
    assert boundary.authorize_depth_camera(newer)
    assert boundary.admit(
        newer.frame,
        now_ns=1_001,
        received_at_monotonic_ns=1,
    ).status is AdmissionStatus.ACCEPTED
    assert boundary.authorize_depth_camera(older)
    result = boundary.admit(
        older.frame,
        now_ns=1_001,
        received_at_monotonic_ns=2,
    )
    assert result.reason is AdmissionReason.OUT_OF_ORDER
