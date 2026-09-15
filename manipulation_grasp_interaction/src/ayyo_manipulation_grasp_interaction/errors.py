"""Typed fail-closed errors for Stage 9D grasp interaction."""

from __future__ import annotations

from enum import StrEnum


class GraspInteractionFailureCode(StrEnum):
    INVALID_STAGE9C_LINEAGE = "invalid_stage9c_lineage"
    WRONG_ROBOT = "wrong_robot"
    WRONG_END_EFFECTOR = "wrong_end_effector"
    WRONG_OBJECT = "wrong_object"
    MISSING_OBJECT = "missing_object"
    DUPLICATE_OBJECT = "duplicate_object"
    MALFORMED_OBJECT_CONTRACT = "malformed_object_contract"
    FIXTURE_UNAVAILABLE = "fixture_unavailable"
    FIXTURE_UNEXPECTEDLY_ATTACHED = "fixture_unexpectedly_attached"
    NO_CONTACT = "no_contact"
    WRONG_CONTACT_PARTICIPANTS = "wrong_contact_participants"
    STALE_CONTACT = "stale_contact"
    CONTACT_REPLAY = "contact_replay"
    INVALID_ALIGNMENT = "invalid_alignment"
    ATTACHMENT_REJECTED = "attachment_rejected"
    ATTACHMENT_STATE_MISMATCH = "attachment_state_mismatch"
    INTERACTION_COLLISION = "interaction_collision"
    STAGE9C_EXECUTION_FAILURE = "stage9c_execution_failure"
    CONTROLLER_UNAVAILABLE = "controller_unavailable"
    UNSTABLE_WHOLE_BODY = "unstable_whole_body"
    STALE_OBJECT_OBSERVATION = "stale_object_observation"
    OBJECT_DISAPPEARED = "object_disappeared"
    OBJECT_SUBSTITUTION = "object_substitution"
    EXCESSIVE_RELATIVE_TRANSLATION = "excessive_relative_translation"
    EXCESSIVE_RELATIVE_ROTATION = "excessive_relative_rotation"
    SLIP_HOLD_FAILURE = "slip_hold_failure"
    RELEASE_WITHOUT_ESTABLISHED_HOLD = "release_without_established_hold"
    RELEASE_REJECTED = "release_rejected"
    STILL_ATTACHED_AFTER_RELEASE = "still_attached_after_release"
    STALE_POST_RELEASE_EVIDENCE = "stale_post_release_evidence"
    CROSS_RUN_COMPOSITION = "cross_run_composition"
    MALFORMED_ARTIFACT = "malformed_artifact"
    NONFINITE_VALUE = "nonfinite_value"
    RESOURCE_LIMIT = "resource_limit"
    SERIALIZATION_FAILURE = "serialization_failure"


class ManipulationGraspInteractionError(Exception):
    """Base exception for the Stage 9D package."""


class GraspInteractionValidationError(ManipulationGraspInteractionError, ValueError):
    """Raised when Stage 9D evidence violates a typed invariant."""

    def __init__(self, code: GraspInteractionFailureCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


class GraspInteractionSerializationError(
    ManipulationGraspInteractionError,
    ValueError,
):
    """Raised when canonical Stage 9D reconstruction fails closed."""
