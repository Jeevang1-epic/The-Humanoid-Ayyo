#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Run one explicit fixed-fixture Stage 9D simulation interaction."""

from __future__ import annotations

import importlib.util
import json
from math import isfinite
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from ament_index_python.packages import get_package_prefix
from ayyo_manipulation_grasp_interaction import (
    ContactEvidence,
    EntityPoseEvidence,
    FixtureAttachmentState,
    FixtureStateEvidence,
    GraspInteractionValidationError,
    ObservedEntityKind,
    STAGE9D_CONTACT_TOPIC,
    STAGE9D_END_EFFECTOR_COLLISION,
    STAGE9D_END_EFFECTOR_ENTITY,
    STAGE9D_FIXTURE_ATTACH_TOPIC,
    STAGE9D_FIXTURE_DETACH_TOPIC,
    STAGE9D_FIXTURE_ID,
    STAGE9D_FIXTURE_STATE_TOPIC,
    STAGE9D_OBJECT_COLLISION,
    STAGE9D_OBJECT_ID,
    STAGE9D_OBJECT_MODEL,
    STAGE9D_OBJECT_ODOMETRY_TOPIC,
    canonical_grasp_interaction_artifact_json,
    create_grasp_interaction_request,
    create_grasp_interaction_result,
    establish_grasp,
    evaluate_hold,
    evaluate_pregrasp,
    evaluate_release,
    interaction_preflight_input_document,
    moveit_interaction_proof_from_canonical_json,
    relative_pose,
)
from ayyo_manipulation_simulation_execution import (
    PreflightStatus,
    SimulatedJointState,
    SimulationExecutionOutcome,
    create_simulation_execution_goal,
    create_simulation_execution_result,
    evaluate_simulation_preflight,
    evaluate_whole_body_stability,
)
from nav_msgs.msg import Odometry
import rclpy
from rclpy.parameter import Parameter
from ros_gz_interfaces.msg import Contacts
from std_msgs.msg import Empty, String
from tf2_ros import Buffer, TransformException, TransformListener


MAX_WAIT_SECONDS = 10.0
MAX_CONTACT_ENTRIES = 16
MINIMUM_RELEASE_CHANGE = 0.005


def _load_stage9c_adapter():
    """Load only the installed, fixed Stage 9C executable implementation."""
    path = (
        Path(get_package_prefix('ayyo_manipulation_simulation_execution'))
        / 'lib/ayyo_manipulation_simulation_execution/stage9c_execution.py'
    )
    spec = importlib.util.spec_from_file_location('ayyo_stage9c_execution', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('installed Stage 9C execution seam is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _interaction_report(grasp, urdf: str, srdf_path: Path) -> str:
    payload = json.dumps(
        interaction_preflight_input_document(
            grasp.request,
            grasp.grasp_evidence_id,
            grasp.grasp_evidence_fingerprint,
        ),
        allow_nan=False,
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True,
    )
    executable = (
        Path(get_package_prefix('ayyo_manipulation_grasp_interaction'))
        / 'lib/ayyo_manipulation_grasp_interaction/stage9d_moveit_preflight'
    )
    input_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            prefix='ayyo-stage9d-preflight-',
            suffix='.json',
            delete=False,
        ) as stream:
            stream.write(payload)
            input_path = Path(stream.name)
        return subprocess.run(
            [str(executable), str(srdf_path), str(input_path)],
            input=urdf,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
    finally:
        if input_path is not None:
            input_path.unlink(missing_ok=True)


class Stage9DClient:
    """Mixin adding only fixed Stage 9D observations to Stage 9C's client."""

    def _initialize_stage9d(self) -> None:
        self._stage9d_object = None
        self._stage9d_object_sequence = 0
        self._stage9d_fixture = None
        self._stage9d_fixture_sequence = 0
        self._stage9d_contact = None
        self._stage9d_contact_sequence = 0
        self._stage9d_tf_sequence = 0
        self._stage9d_request = None
        self._stage9d_tf_buffer = Buffer(node=self)
        self._stage9d_tf_listener = TransformListener(
            self._stage9d_tf_buffer,
            self,
            spin_thread=False,
        )
        self.create_subscription(
            Odometry,
            STAGE9D_OBJECT_ODOMETRY_TOPIC,
            self._on_stage9d_object,
            10,
        )
        self.create_subscription(
            Contacts,
            STAGE9D_CONTACT_TOPIC,
            self._on_stage9d_contact,
            10,
        )
        self.create_subscription(
            String,
            STAGE9D_FIXTURE_STATE_TOPIC,
            self._on_stage9d_fixture,
            10,
        )
        self._stage9d_attach = self.create_publisher(
            Empty,
            STAGE9D_FIXTURE_ATTACH_TOPIC,
            1,
        )
        self._stage9d_detach = self.create_publisher(
            Empty,
            STAGE9D_FIXTURE_DETACH_TOPIC,
            1,
        )

    def _simulation_now(self) -> int:
        return max(0, self.get_clock().now().nanoseconds)

    def _on_stage9d_object(self, message: Odometry) -> None:
        try:
            pose = message.pose.pose
            values = (
                float(pose.position.x),
                float(pose.position.y),
                float(pose.position.z),
                float(pose.orientation.x),
                float(pose.orientation.y),
                float(pose.orientation.z),
                float(pose.orientation.w),
            )
            if not all(isfinite(value) for value in values):
                return
            stamp = message.header.stamp.sec * 1_000_000_000 + (
                message.header.stamp.nanosec
            )
            if stamp < 0:
                return
            self._stage9d_object_sequence += 1
            self._stage9d_object = (values, stamp, self._stage9d_object_sequence)
        except (AttributeError, ArithmeticError, TypeError, ValueError):
            return

    def _on_stage9d_fixture(self, message: String) -> None:
        if message.data not in {'attached', 'detached'}:
            return
        self._stage9d_fixture_sequence += 1
        self._stage9d_fixture = (
            message.data,
            self._simulation_now(),
            self._stage9d_fixture_sequence,
        )

    def _on_stage9d_contact(self, message: Contacts) -> None:
        try:
            if not 1 <= len(message.contacts) <= MAX_CONTACT_ENTRIES:
                return
            pairs = tuple(
                sorted((contact.collision1.name, contact.collision2.name))
                for contact in message.contacts
            )
            depths = tuple(
                float(depth)
                for contact in message.contacts
                for depth in contact.depths
            )
            if depths and (
                not all(isfinite(depth) and 0.0 <= depth <= 0.01 for depth in depths)
            ):
                return
            self._stage9d_contact_sequence += 1
            self._stage9d_contact = (
                tuple(sorted(set(pairs))),
                len(message.contacts),
                max(depths) if depths else None,
                self._simulation_now(),
                self._stage9d_contact_sequence,
            )
        except (AttributeError, ArithmeticError, TypeError, ValueError):
            return

    def _pose_evidence(self, kind: ObservedEntityKind):
        request = self._stage9d_request
        if request is None:
            return None
        if kind is ObservedEntityKind.GRASP_OBJECT:
            if self._stage9d_object is None:
                return None
            values, stamp, sequence = self._stage9d_object
            return EntityPoseEvidence(
                interaction_request_id=request.interaction_request_id,
                interaction_request_fingerprint=(
                    request.interaction_request_fingerprint
                ),
                run_session_id=request.run_session_id,
                kind=kind,
                entity_name=STAGE9D_OBJECT_MODEL,
                frame_id='world',
                position_xyz=values[:3],
                orientation_xyzw=values[3:],
                observed_at_ns=stamp,
                sequence=sequence,
                entity_count=1,
                source='stage9d.gazebo-object-odometry.v1',
            )
        try:
            transform = self._stage9d_tf_buffer.lookup_transform(
                'world',
                'left_hand_link',
                rclpy.time.Time(),
            )
        except TransformException:
            return None
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        stamp = (
            transform.header.stamp.sec * 1_000_000_000
            + transform.header.stamp.nanosec
        )
        self._stage9d_tf_sequence += 1
        return EntityPoseEvidence(
            interaction_request_id=request.interaction_request_id,
            interaction_request_fingerprint=request.interaction_request_fingerprint,
            run_session_id=request.run_session_id,
            kind=kind,
            entity_name=STAGE9D_END_EFFECTOR_ENTITY,
            frame_id='world',
            position_xyz=(translation.x, translation.y, translation.z),
            orientation_xyzw=(rotation.x, rotation.y, rotation.z, rotation.w),
            observed_at_ns=stamp,
            sequence=self._stage9d_tf_sequence,
            entity_count=1,
            source='stage9d.tf2-gazebo-base.v1',
        )

    def _fixture_evidence(self):
        request = self._stage9d_request
        if request is None or self._stage9d_fixture is None:
            return None
        state, stamp, sequence = self._stage9d_fixture
        return FixtureStateEvidence(
            interaction_request_id=request.interaction_request_id,
            interaction_request_fingerprint=request.interaction_request_fingerprint,
            run_session_id=request.run_session_id,
            fixture_id=STAGE9D_FIXTURE_ID,
            object_id=STAGE9D_OBJECT_ID,
            state=FixtureAttachmentState(state),
            available=True,
            observed_at_ns=stamp,
            sequence=sequence,
        )

    def _contact_evidence(self):
        request = self._stage9d_request
        if request is None or self._stage9d_contact is None:
            return None
        pairs, count, depth, stamp, sequence = self._stage9d_contact
        return ContactEvidence(
            interaction_request_id=request.interaction_request_id,
            interaction_request_fingerprint=request.interaction_request_fingerprint,
            run_session_id=request.run_session_id,
            object_id=STAGE9D_OBJECT_ID,
            collision_pairs=pairs,
            observed_at_ns=stamp,
            sequence=sequence,
            contact_count=count,
            maximum_penetration_depth=depth,
        )

    def wait_for_stage9d_snapshot(
        self,
        *,
        fixture_state: FixtureAttachmentState,
        after_fixture_sequence: int = 0,
        after_object_sequence: int = 0,
    ):
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            now = self._simulation_now()
            try:
                hand = self._pose_evidence(ObservedEntityKind.END_EFFECTOR)
                obj = self._pose_evidence(ObservedEntityKind.GRASP_OBJECT)
                fixture = self._fixture_evidence()
            except GraspInteractionValidationError:
                continue
            if hand is None or obj is None or fixture is None:
                continue
            if (
                fixture.state is fixture_state
                and fixture.sequence > after_fixture_sequence
                and obj.sequence > after_object_sequence
                and all(
                    0 <= now - timestamp <= 500_000_000
                    for timestamp in (
                        hand.observed_at_ns,
                        obj.observed_at_ns,
                        fixture.observed_at_ns,
                    )
                )
            ):
                return hand, obj, fixture
        return None

    def wait_for_contact(self, after_sequence: int):
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            try:
                contact = self._contact_evidence()
            except GraspInteractionValidationError:
                return None
            if contact is not None and contact.sequence > after_sequence:
                now = self._simulation_now()
                if 0 <= now - contact.observed_at_ns <= 500_000_000:
                    return contact
        return None

    def command_attach_once(self) -> None:
        self._stage9d_attach.publish(Empty())

    def command_detach_once(self) -> None:
        self._stage9d_detach.publish(Empty())


def _client_type(stage9c):
    return type(
        'ReviewedStage9DClient',
        (Stage9DClient, stage9c.Stage9CClient),
        {
            '__init__': lambda self: (
                stage9c.Stage9CClient.__init__(self),
                self._initialize_stage9d(),
            )[-1],
        },
    )


def main() -> int:
    try:
        stage9c = _load_stage9c_adapter()
        profile = stage9c._profile_fingerprints()
        if profile != (
            stage9c.STAGE9C_REVIEWED_SIMULATION_DESCRIPTION_FINGERPRINT,
            stage9c.STAGE9C_REVIEWED_CONTROLLER_CONFIGURATION_FINGERPRINT,
        ):
            print('FAIL: installed Stage 9C profile is not reviewed', file=sys.stderr)
            return 2
        urdf, srdf, srdf_path = stage9c._reviewed_descriptions()
        planning_request = stage9c.reviewed_planning_request(urdf, srdf)
        stage9c_request, stage9c_collision = stage9c._moveit_reports(
            urdf,
            srdf_path,
            planning_request,
        )
        rclpy.init()
        node = _client_type(stage9c)()
        try:
            requested_at = node._simulation_now()
            request = create_grasp_interaction_request(
                stage9c_request,
                run_session_id=f'stage9d-run-{time.monotonic_ns()}',
                requested_at_ns=requested_at,
            )
            node._stage9d_request = request
            initial = node.wait_for_stage9d_snapshot(
                fixture_state=FixtureAttachmentState.DETACHED
            )
            if initial is None:
                print('FAIL: exact detached Stage 9D snapshot is unavailable', file=sys.stderr)
                return 2
            initial_hand, initial_object, detached = initial
            pregrasp_at = node._simulation_now()
            pregrasp = evaluate_pregrasp(
                request,
                initial_hand,
                initial_object,
                detached,
                evaluated_at_ns=pregrasp_at,
            )
            contact = node.wait_for_contact(node._stage9d_contact_sequence)
            if contact is None:
                print('FAIL: fresh exact hand/object contact is unavailable', file=sys.stderr)
                return 2
            node.command_attach_once()
            attached_snapshot = node.wait_for_stage9d_snapshot(
                fixture_state=FixtureAttachmentState.ATTACHED,
                after_fixture_sequence=detached.sequence,
                after_object_sequence=initial_object.sequence,
            )
            if attached_snapshot is None:
                print('FAIL: contact-gated Stage 9D attachment was rejected', file=sys.stderr)
                return 2
            _, _, attached = attached_snapshot
            grasp = establish_grasp(
                pregrasp,
                contact,
                attached,
                established_at_ns=node._simulation_now(),
            )
            interaction_report = _interaction_report(grasp, urdf, srdf_path)
            interaction_collision = moveit_interaction_proof_from_canonical_json(
                grasp,
                interaction_report,
            )
            if not interaction_collision.collision_free:
                print('FAIL: Stage 9D interaction collision preflight failed', file=sys.stderr)
                return 2

            if node.wait_for_whole_body_state() is None or not node.wait_for_support_fixture():
                print('FAIL: Stage 9C support evidence is unavailable', file=sys.stderr)
                return 2
            controller = node.controller_state(stage9c_request.controller_contract)
            initial_whole = node.wait_for_whole_body_state()
            if initial_whole is None:
                print('FAIL: fresh Stage 9C initial whole-body state expired', file=sys.stderr)
                return 2
            start = SimulatedJointState(
                joint_names=node._expected_names,
                positions=initial_whole.positions_for(node._expected_names),
                observed_at_ns=initial_whole.observed_at_ns,
                sequence=initial_whole.sequence,
            )
            preflight = evaluate_simulation_preflight(
                stage9c_collision,
                start,
                controller,
                evaluated_at_ns=node._simulation_now(),
            )
            if preflight.status is not PreflightStatus.READY_FOR_SIMULATION_EXECUTION:
                print('FAIL: exact Stage 9C preflight rejected execution', file=sys.stderr)
                return 2
            goal = create_simulation_execution_goal(preflight)
            observation = node.execute(goal, initial_whole)
            stage9c_result = create_simulation_execution_result(goal, observation)
            if observation.outcome is not (
                SimulationExecutionOutcome.SIMULATION_EXECUTION_COMPLETED
            ):
                print('FAIL: exact Stage 9C execution did not complete', file=sys.stderr)
                return 2

            final_snapshot = node.wait_for_stage9d_snapshot(
                fixture_state=FixtureAttachmentState.ATTACHED,
                after_fixture_sequence=attached.sequence,
                after_object_sequence=initial_object.sequence,
            )
            if final_snapshot is None:
                print('FAIL: fresh attached object evidence is unavailable', file=sys.stderr)
                return 2
            final_hand, final_object, hold_attached = final_snapshot
            hold = evaluate_hold(
                grasp,
                interaction_collision,
                stage9c_result,
                final_hand,
                final_object,
                hold_attached,
                evaluated_at_ns=node._simulation_now(),
            )

            release_requested_at = node._simulation_now()
            release_joint_sequence = observation.stability_observation.final_state.sequence
            release_base_sequence = (
                observation.stability_observation.final_state.base_pose.sequence
            )
            node.command_detach_once()
            post_snapshot = None
            deadline = time.monotonic() + MAX_WAIT_SECONDS
            while rclpy.ok() and time.monotonic() < deadline:
                candidate = node.wait_for_stage9d_snapshot(
                    fixture_state=FixtureAttachmentState.DETACHED,
                    after_fixture_sequence=hold_attached.sequence,
                    after_object_sequence=final_object.sequence,
                )
                if candidate is None:
                    break
                candidate_relative = relative_pose(candidate[0], candidate[1])
                held_relative = relative_pose(final_hand, final_object)
                change = sum(
                    (left - right) ** 2
                    for left, right in zip(
                        candidate_relative[0], held_relative[0], strict=True
                    )
                ) ** 0.5
                if change >= MINIMUM_RELEASE_CHANGE:
                    post_snapshot = candidate
                    break
            if post_snapshot is None:
                print('FAIL: explicit non-rigid release was not observed', file=sys.stderr)
                return 2
            post_hand, post_object, release_detached = post_snapshot
            post_whole = node.wait_for_whole_body_state(
                after_joint_sequence=release_joint_sequence,
                after_base_sequence=release_base_sequence,
            )
            if post_whole is None:
                print('FAIL: fresh post-release whole-body state is unavailable', file=sys.stderr)
                return 2
            post_controller = node.controller_state(stage9c_request.controller_contract)
            evaluated_at = node._simulation_now()
            post_stability = evaluate_whole_body_stability(
                initial_whole,
                post_whole,
                post_controller,
                evaluated_at_ns=evaluated_at,
            )
            release = evaluate_release(
                hold,
                release_requested_at_ns=release_requested_at,
                detached_fixture=release_detached,
                post_release_end_effector_pose=post_hand,
                post_release_object_pose=post_object,
                post_release_stability=post_stability,
                evaluated_at_ns=evaluated_at,
            )
            result = create_grasp_interaction_result(request, release)
            print(canonical_grasp_interaction_artifact_json(result))
            return 0
        finally:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
    except (
        AttributeError,
        GraspInteractionValidationError,
        ImportError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        TransformException,
        TypeError,
        ValueError,
    ) as error:
        print(f'FAIL: Stage 9D interaction rejected: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
