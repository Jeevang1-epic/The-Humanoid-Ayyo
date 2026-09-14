"""Pure construction and evaluation operations for Stage 9D."""

from __future__ import annotations

from ayyo_manipulation_simulation_execution import SimulationExecutionRequest

from .errors import GraspInteractionFailureCode, GraspInteractionValidationError
from .models import (
    DEFAULT_ALIGNMENT_ROTATION_TOLERANCE,
    DEFAULT_ALIGNMENT_TRANSLATION_TOLERANCE,
    DEFAULT_HOLD_ROTATION_TOLERANCE,
    DEFAULT_HOLD_TRANSLATION_TOLERANCE,
    DEFAULT_MAXIMUM_OBJECT_TELEPORT,
    DEFAULT_MINIMUM_RELEASE_RELATIVE_CHANGE,
    STAGE9D_COLLISION_BACKEND_ID,
    STAGE9D_COLLISION_BACKEND_VERSION,
    STAGE9D_END_EFFECTOR_LINK,
    STAGE9D_EXPECTED_RELATIVE_ORIENTATION,
    STAGE9D_EXPECTED_RELATIVE_POSITION,
    STAGE9D_OBJECT_COLLISION,
    EndEffectorContract,
    EntityPoseEvidence,
    FixtureStateEvidence,
    GraspEstablishedEvidence,
    GraspInteractionRequest,
    GraspInteractionResult,
    GraspableObjectContract,
    HoldEvidence,
    InteractionCollisionProof,
    InteractionCollisionSample,
    PregraspEvidence,
    ReleaseEvidence,
    _rotation_distance,
    _translation_distance,
    relative_pose,
)


def reviewed_end_effector_contract(
    stage9c_request: SimulationExecutionRequest,
) -> EndEffectorContract:
    """Bind the Stage 9D semantic end effector to the exact Stage 9C robot."""

    try:
        model = stage9c_request.planning_request.robot_model
        return EndEffectorContract(
            robot_name=model.robot_name,
            robot_model_id=model.robot_model_id,
            robot_model_fingerprint=model.robot_model_fingerprint,
        )
    except GraspInteractionValidationError:
        raise
    except (AssertionError, AttributeError, KeyError, TypeError, ValueError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE,
            "cannot derive the Stage 9D end effector from malformed Stage 9C data",
        ) from error


def reviewed_graspable_object_contract() -> GraspableObjectContract:
    """Return the one exact primitive accepted by Stage 9D v1."""

    return GraspableObjectContract()


def create_grasp_interaction_request(
    stage9c_request: SimulationExecutionRequest,
    *,
    run_session_id: str,
    requested_at_ns: int,
) -> GraspInteractionRequest:
    """Create one run-specific request over the exact reviewed Stage 9C source."""

    try:
        return GraspInteractionRequest(
            stage9c_execution_request=stage9c_request,
            end_effector=reviewed_end_effector_contract(stage9c_request),
            grasp_object=reviewed_graspable_object_contract(),
            run_session_id=run_session_id,
            requested_at_ns=requested_at_ns,
        )
    except GraspInteractionValidationError:
        raise
    except (AssertionError, AttributeError, KeyError, TypeError, ValueError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.INVALID_STAGE9C_LINEAGE,
            "malformed Stage 9C source cannot become a Stage 9D request",
        ) from error


def evaluate_pregrasp(
    request: GraspInteractionRequest,
    end_effector_pose: EntityPoseEvidence,
    object_pose: EntityPoseEvidence,
    detached_fixture: FixtureStateEvidence,
    *,
    evaluated_at_ns: int,
) -> PregraspEvidence:
    """Validate exact detached-state, pose, identity, freshness, and alignment."""

    try:
        position, orientation = relative_pose(end_effector_pose, object_pose)
        return PregraspEvidence(
            request=request,
            end_effector_pose=end_effector_pose,
            object_pose=object_pose,
            detached_fixture=detached_fixture,
            evaluated_at_ns=evaluated_at_ns,
            translation_error=_translation_distance(
                position,
                STAGE9D_EXPECTED_RELATIVE_POSITION,
            ),
            rotation_error=_rotation_distance(
                orientation,
                STAGE9D_EXPECTED_RELATIVE_ORIENTATION,
            ),
            translation_tolerance=DEFAULT_ALIGNMENT_TRANSLATION_TOLERANCE,
            rotation_tolerance=DEFAULT_ALIGNMENT_ROTATION_TOLERANCE,
        )
    except GraspInteractionValidationError:
        raise
    except (AssertionError, AttributeError, ArithmeticError, KeyError, TypeError, ValueError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.INVALID_ALIGNMENT,
            "pregrasp evaluation received malformed evidence",
        ) from error


def establish_grasp(
    pregrasp: PregraspEvidence,
    contact,
    attached_fixture: FixtureStateEvidence,
    *,
    established_at_ns: int,
) -> GraspEstablishedEvidence:
    """Establish a simulated hold only after exact fresh contact."""

    try:
        return GraspEstablishedEvidence(
            pregrasp=pregrasp,
            contact=contact,
            attached_fixture=attached_fixture,
            established_at_ns=established_at_ns,
        )
    except GraspInteractionValidationError:
        raise
    except (AssertionError, AttributeError, ArithmeticError, KeyError, TypeError, ValueError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.ATTACHMENT_REJECTED,
            "grasp establishment received malformed evidence",
        ) from error


def create_interaction_collision_proof(
    grasp: GraspEstablishedEvidence,
    samples: tuple[InteractionCollisionSample, ...],
) -> InteractionCollisionProof:
    """Bind target-specific attached-body collision checks to one grasp interval."""

    try:
        return InteractionCollisionProof(
            request=grasp.request,
            grasp_evidence_id=grasp.grasp_evidence_id,
            grasp_evidence_fingerprint=grasp.grasp_evidence_fingerprint,
            backend_id=STAGE9D_COLLISION_BACKEND_ID,
            backend_version=STAGE9D_COLLISION_BACKEND_VERSION,
            samples=samples,
            allowed_touch_links=(STAGE9D_END_EFFECTOR_LINK,),
            allowed_collision_pair=(
                STAGE9D_END_EFFECTOR_LINK,
                STAGE9D_OBJECT_COLLISION,
            ),
            target_object_specific=True,
            grasp_interval_only=True,
            global_acm_modified=False,
            continuous_collision_certification=False,
            physical_collision_certification=False,
        )
    except GraspInteractionValidationError:
        raise
    except (AssertionError, AttributeError, ArithmeticError, KeyError, TypeError, ValueError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.INTERACTION_COLLISION,
            "interaction collision proof received malformed data",
        ) from error


def evaluate_hold(
    grasp: GraspEstablishedEvidence,
    collision_proof: InteractionCollisionProof,
    stage9c_result,
    final_end_effector_pose: EntityPoseEvidence,
    final_object_pose: EntityPoseEvidence | None,
    attached_fixture: FixtureStateEvidence,
    *,
    evaluated_at_ns: int,
) -> HoldEvidence:
    """Require Stage 9C success plus fresh relative object-pose evidence."""

    if final_object_pose is None:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.OBJECT_DISAPPEARED,
            "the reviewed object disappeared during Stage 9C movement",
        )
    try:
        initial_relative = relative_pose(
            grasp.pregrasp.end_effector_pose,
            grasp.pregrasp.object_pose,
        )
        final_relative = relative_pose(final_end_effector_pose, final_object_pose)
        return HoldEvidence(
            grasp=grasp,
            collision_proof=collision_proof,
            stage9c_result=stage9c_result,
            final_end_effector_pose=final_end_effector_pose,
            final_object_pose=final_object_pose,
            attached_fixture=attached_fixture,
            evaluated_at_ns=evaluated_at_ns,
            relative_translation_change=_translation_distance(
                initial_relative[0], final_relative[0]
            ),
            relative_rotation_change=_rotation_distance(
                initial_relative[1], final_relative[1]
            ),
            object_world_displacement=_translation_distance(
                grasp.pregrasp.object_pose.position_xyz,
                final_object_pose.position_xyz,
            ),
            translation_tolerance=DEFAULT_HOLD_TRANSLATION_TOLERANCE,
            rotation_tolerance=DEFAULT_HOLD_ROTATION_TOLERANCE,
            maximum_object_teleport=DEFAULT_MAXIMUM_OBJECT_TELEPORT,
        )
    except GraspInteractionValidationError:
        raise
    except (AssertionError, AttributeError, ArithmeticError, KeyError, TypeError, ValueError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.SLIP_HOLD_FAILURE,
            "hold evaluation received malformed evidence",
        ) from error


def evaluate_release(
    hold: HoldEvidence,
    *,
    release_requested_at_ns: int,
    detached_fixture: FixtureStateEvidence,
    post_release_end_effector_pose: EntityPoseEvidence,
    post_release_object_pose: EntityPoseEvidence | None,
    post_release_stability,
    evaluated_at_ns: int,
) -> ReleaseEvidence:
    """Prove explicit detachment and fresh non-rigid post-release movement."""

    if post_release_object_pose is None:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.OBJECT_DISAPPEARED,
            "the reviewed object disappeared after release",
        )
    try:
        before = relative_pose(hold.final_end_effector_pose, hold.final_object_pose)
        after = relative_pose(post_release_end_effector_pose, post_release_object_pose)
        return ReleaseEvidence(
            hold=hold,
            release_requested_at_ns=release_requested_at_ns,
            detached_fixture=detached_fixture,
            post_release_end_effector_pose=post_release_end_effector_pose,
            post_release_object_pose=post_release_object_pose,
            post_release_stability=post_release_stability,
            evaluated_at_ns=evaluated_at_ns,
            relative_pose_change=_translation_distance(before[0], after[0]),
            minimum_relative_change=DEFAULT_MINIMUM_RELEASE_RELATIVE_CHANGE,
        )
    except GraspInteractionValidationError:
        raise
    except (AssertionError, AttributeError, ArithmeticError, KeyError, TypeError, ValueError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.RELEASE_REJECTED,
            "release evaluation received malformed evidence",
        ) from error


def create_grasp_interaction_result(
    request: GraspInteractionRequest,
    release: ReleaseEvidence,
) -> GraspInteractionResult:
    """Create the final bounded simulation-only Stage 9D result."""

    try:
        return GraspInteractionResult(request=request, release=release)
    except GraspInteractionValidationError:
        raise
    except (AssertionError, AttributeError, ArithmeticError, KeyError, TypeError, ValueError) as error:
        raise GraspInteractionValidationError(
            GraspInteractionFailureCode.MALFORMED_ARTIFACT,
            "final Stage 9D result received malformed evidence",
        ) from error
