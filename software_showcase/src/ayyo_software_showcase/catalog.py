"""Closed Stage-8 catalog assembled only from reviewed public contracts."""

from __future__ import annotations

from ayyo_approval_eligibility import (
    ACTIVATION_ELIGIBILITY_DECISION_SCHEMA_ID,
    APPROVAL_ELIGIBILITY_SCHEMA_VERSION,
    AUTHORITY_APPROVAL_EVIDENCE_SCHEMA_ID,
    ActivationEligibilityDecision,
    AuthorityApprovalEvidence,
)
from ayyo_developmental_scenarios import (
    MANIFEST_SCHEMA_ID,
    MANIFEST_SCHEMA_VERSION,
    DevelopmentScenarioManifest,
)
from ayyo_executive import ExecutiveDecision
from ayyo_learning_evaluation import (
    EVALUATION_REPORT_SCHEMA_ID,
    EVALUATION_REPORT_SCHEMA_VERSION,
    OfflineEvaluationReport,
)
from ayyo_memory_consolidation import ControlledMemoryCandidateReviewPipeline
from ayyo_memory_validation import CandidateEvidence
from ayyo_perception import PerceptionSourceContract
from ayyo_personal_context import PersonalContextSnapshot
from ayyo_policy_registry import (
    POLICY_REGISTRY_SCHEMA_VERSION,
    REGISTERED_POLICY_VERSION_SCHEMA_ID,
    RegisteredPolicyVersion,
)
from ayyo_promotion_control import (
    PROMOTION_DECISION_SCHEMA_ID,
    PROMOTION_SCHEMA_VERSION,
    ROLLBACK_DECISION_SCHEMA_ID,
    ROLLBACK_SCHEMA_VERSION,
    PromotionDecision,
    RollbackDecision,
)
from ayyo_runtime_bridge import RuntimeDecision
from ayyo_safety import SafetyDecision
from ayyo_simulation_control import SimulationControlResult
from ayyo_skill_manager import SkillBindingResult
from ayyo_teach_mode import (
    TEACH_MODE_SCHEMA_ID,
    TEACH_MODE_SCHEMA_VERSION,
    DemonstrationEpisode,
)
from ayyo_working_memory import WorkingMemory
from ayyo_world_model import WorldSnapshot

from .canonical import identifier, semantic_sha256
from .errors import UnknownShowcaseCapabilityError
from .models import (
    ShowcaseCapability,
    ShowcaseClassification,
    ShowcaseEvidenceKind,
    ShowcaseEvidenceReference,
    ShowcaseManifest,
    ShowcaseNonClaim,
    verify_showcase_manifest,
)


def _public_contract(
    contract: type,
    *,
    schema_id: str | None = None,
    schema_version: str | None = None,
) -> ShowcaseEvidenceReference:
    module = contract.__module__
    symbol = contract.__qualname__
    provenance_ref = f"public-api.{module.split('.')[0]}.v1"
    provenance_fingerprint = semantic_sha256(
        "showcase-provenance",
        {
            "contract_module": module,
            "contract_symbol": symbol,
            "schema_id": schema_id,
            "schema_version": schema_version,
        },
    )
    return ShowcaseEvidenceReference(
        kind=(
            ShowcaseEvidenceKind.VERSIONED_SCHEMA
            if schema_id is not None
            else ShowcaseEvidenceKind.PUBLIC_CONTRACT
        ),
        contract_module=module,
        contract_symbol=symbol,
        schema_id=schema_id,
        schema_version=schema_version,
        provenance_ref=provenance_ref,
        provenance_fingerprint=provenance_fingerprint,
    )


def _capability(
    sequence_index: int,
    capability_id: str,
    title: str,
    summary: str,
    classifications: tuple[ShowcaseClassification, ...],
    evidence: tuple[ShowcaseEvidenceReference, ...],
    does_not_prove: tuple[ShowcaseNonClaim, ...],
) -> ShowcaseCapability:
    return ShowcaseCapability(
        sequence_index=sequence_index,
        capability_id=capability_id,
        title=title,
        summary=summary,
        classifications=classifications,
        evidence_ids=tuple(item.evidence_id for item in evidence),
        does_not_prove=does_not_prove,
    )


def build_showcase_manifest() -> ShowcaseManifest:
    """Build the reviewed catalog from imported public interface identities."""
    perception = _public_contract(PerceptionSourceContract)
    world = _public_contract(WorldSnapshot)
    working = _public_contract(WorkingMemory)
    candidate = _public_contract(CandidateEvidence)
    memory_review = _public_contract(ControlledMemoryCandidateReviewPipeline)
    context = _public_contract(PersonalContextSnapshot)
    executive = _public_contract(ExecutiveDecision)
    safety = _public_contract(SafetyDecision)
    skill = _public_contract(SkillBindingResult)
    runtime = _public_contract(RuntimeDecision)
    simulation = _public_contract(SimulationControlResult)
    scenarios = _public_contract(
        DevelopmentScenarioManifest,
        schema_id=MANIFEST_SCHEMA_ID,
        schema_version=MANIFEST_SCHEMA_VERSION,
    )
    teach = _public_contract(
        DemonstrationEpisode,
        schema_id=TEACH_MODE_SCHEMA_ID,
        schema_version=TEACH_MODE_SCHEMA_VERSION,
    )
    evaluation = _public_contract(
        OfflineEvaluationReport,
        schema_id=EVALUATION_REPORT_SCHEMA_ID,
        schema_version=EVALUATION_REPORT_SCHEMA_VERSION,
    )
    promotion = _public_contract(
        PromotionDecision,
        schema_id=PROMOTION_DECISION_SCHEMA_ID,
        schema_version=PROMOTION_SCHEMA_VERSION,
    )
    rollback = _public_contract(
        RollbackDecision,
        schema_id=ROLLBACK_DECISION_SCHEMA_ID,
        schema_version=ROLLBACK_SCHEMA_VERSION,
    )
    registry = _public_contract(
        RegisteredPolicyVersion,
        schema_id=REGISTERED_POLICY_VERSION_SCHEMA_ID,
        schema_version=POLICY_REGISTRY_SCHEMA_VERSION,
    )
    approval = _public_contract(
        AuthorityApprovalEvidence,
        schema_id=AUTHORITY_APPROVAL_EVIDENCE_SCHEMA_ID,
        schema_version=APPROVAL_ELIGIBILITY_SCHEMA_VERSION,
    )
    activation_eligibility = _public_contract(
        ActivationEligibilityDecision,
        schema_id=ACTIVATION_ELIGIBILITY_DECISION_SCHEMA_ID,
        schema_version=APPROVAL_ELIGIBILITY_SCHEMA_VERSION,
    )
    evidence = (
        perception,
        world,
        working,
        candidate,
        memory_review,
        context,
        executive,
        safety,
        skill,
        runtime,
        simulation,
        scenarios,
        teach,
        evaluation,
        promotion,
        rollback,
        registry,
        approval,
        activation_eligibility,
    )
    capabilities = (
        _capability(
            0,
            "perception-and-sensor-evidence",
            "Perception and sensor evidence foundations",
            "Bounded public source contracts exist for reviewed evidence admission; current producers are TEST, simulation, or driver-neutral foundations rather than physically validated production perception.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.TEST,
                ShowcaseClassification.SIMULATION,
                ShowcaseClassification.NOT_PHYSICALLY_VALIDATED,
            ),
            (perception,),
            (
                ShowcaseNonClaim.COMPLETE_SCENE_KNOWLEDGE,
                ShowcaseNonClaim.HARDWARE_AUTHORITY,
                ShowcaseNonClaim.PHYSICAL_VALIDATION,
            ),
        ),
        _capability(
            1,
            "world-model-and-working-memory",
            "World Model and Working Memory",
            "Transport-neutral immutable snapshots and bounded temporary working state expose current evidence without manufacturing durable truth.",
            (ShowcaseClassification.IMPLEMENTED,),
            (world, working),
            (
                ShowcaseNonClaim.COMPLETE_SCENE_KNOWLEDGE,
                ShowcaseNonClaim.DURABLE_PERSISTENCE,
                ShowcaseNonClaim.HARDWARE_AUTHORITY,
            ),
        ),
        _capability(
            2,
            "bounded-memory-review",
            "Bounded memory candidate and review flow",
            "Reviewed public contracts support explicit candidate validation and controlled review while remaining caller-invoked and evidence-only.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (candidate, memory_review),
            (
                ShowcaseNonClaim.AUTOMATIC_LEARNING,
                ShowcaseNonClaim.DURABLE_PERSISTENCE,
                ShowcaseNonClaim.SAFETY_BYPASS,
            ),
        ),
        _capability(
            3,
            "context-executive-and-safety",
            "Personal Context, Executive, and Safety boundaries",
            "Read-only context, declarative Executive decisions, and independent Safety decisions are implemented as separate public contracts with no action execution in this showcase.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (context, executive, safety),
            (
                ShowcaseNonClaim.EXECUTED_MOTION,
                ShowcaseNonClaim.PHYSICAL_SAFETY_CERTIFICATION,
                ShowcaseNonClaim.SAFETY_BYPASS,
            ),
        ),
        _capability(
            4,
            "skill-and-runtime-eligibility",
            "Skill Manager and Runtime Bridge eligibility",
            "Public skill-binding and runtime-decision contracts can establish bounded handoff eligibility without dispatching a request or executing a skill.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (skill, runtime),
            (
                ShowcaseNonClaim.EXECUTED_MOTION,
                ShowcaseNonClaim.PRODUCTION_ROS_COMMAND,
                ShowcaseNonClaim.RUNTIME_DISPATCH,
            ),
        ),
        _capability(
            5,
            "ros-gazebo-simulation-foundations",
            "ROS and Gazebo simulation foundations",
            "Reviewed simulation-control and scenario contracts describe bounded software integration; inspection does not launch ROS or Gazebo and simulation evidence is not physical validation.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.SIMULATION,
                ShowcaseClassification.DEVELOPMENT_ONLY,
                ShowcaseClassification.NOT_PHYSICALLY_VALIDATED,
            ),
            (simulation, scenarios),
            (
                ShowcaseNonClaim.HARDWARE_AUTHORITY,
                ShowcaseNonClaim.PHYSICAL_SAFETY_CERTIFICATION,
                ShowcaseNonClaim.PHYSICAL_VALIDATION,
                ShowcaseNonClaim.PRODUCTION_ROS_COMMAND,
            ),
        ),
        _capability(
            6,
            "developmental-scenario-harness",
            "Developmental scenario harness",
            "The versioned scenario manifest exposes fixed TEST and simulation stories, including explicitly DEVELOPMENT-only evidence, without starting them from the showcase.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.TEST,
                ShowcaseClassification.SIMULATION,
                ShowcaseClassification.DEVELOPMENT_ONLY,
            ),
            (scenarios,),
            (
                ShowcaseNonClaim.EXECUTED_MOTION,
                ShowcaseNonClaim.PHYSICAL_VALIDATION,
                ShowcaseNonClaim.RUNTIME_DISPATCH,
            ),
        ),
        _capability(
            7,
            "teach-mode-evidence",
            "Teach Mode demonstration evidence",
            "Versioned bounded demonstration episodes retain typed historical evidence; they do not authenticate a teacher, train a model, or replay actions.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.TEST,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (teach,),
            (
                ShowcaseNonClaim.AUTHENTICATED_AUTHORITY,
                ShowcaseNonClaim.AUTOMATIC_LEARNING,
                ShowcaseNonClaim.MODEL_EXECUTION,
                ShowcaseNonClaim.POLICY_ACTIVATION,
            ),
        ),
        _capability(
            8,
            "offline-candidate-evaluation",
            "Offline candidate-policy evaluation",
            "The versioned offline evaluation contract evaluates caller-supplied evidence and results without loading, training, or executing candidate policy code.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.TEST,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (evaluation,),
            (
                ShowcaseNonClaim.AUTOMATIC_LEARNING,
                ShowcaseNonClaim.MODEL_EXECUTION,
                ShowcaseNonClaim.POLICY_ACTIVATION,
            ),
        ),
        _capability(
            9,
            "promotion-and-rollback-eligibility",
            "Promotion and rollback eligibility",
            "Versioned promotion and rollback decisions preserve exact evidence and lineage while granting eligibility only, never an automatic state change.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (promotion, rollback),
            (
                ShowcaseNonClaim.ACTIVE_OR_INSTALLED_POLICY,
                ShowcaseNonClaim.AUTOMATIC_PROMOTION_OR_ROLLBACK,
                ShowcaseNonClaim.POLICY_ACTIVATION,
            ),
        ),
        _capability(
            10,
            "immutable-policy-registry",
            "Immutable policy registry and version lineage",
            "A versioned registered-policy record binds exact eligible evidence and explicit ancestry without an active/latest pointer, execution surface, or persistence service.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (registry,),
            (
                ShowcaseNonClaim.ACTIVE_OR_INSTALLED_POLICY,
                ShowcaseNonClaim.DURABLE_PERSISTENCE,
                ShowcaseNonClaim.MODEL_EXECUTION,
                ShowcaseNonClaim.POLICY_ACTIVATION,
            ),
        ),
        _capability(
            11,
            "human-authority-approval-evidence",
            "Human or authority approval evidence",
            "The approval-evidence schema binds caller-supplied authority provenance and disposition; Ayyo does not authenticate the referenced person or provider.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (approval,),
            (
                ShowcaseNonClaim.AUTHENTICATED_AUTHORITY,
                ShowcaseNonClaim.PHYSICAL_SAFETY_CERTIFICATION,
                ShowcaseNonClaim.POLICY_ACTIVATION,
            ),
        ),
        _capability(
            12,
            "future-activation-eligibility",
            "Future-activation eligibility",
            "The exact versioned decision can mean only ELIGIBLE_FOR_FUTURE_ACTIVATION; it is not installation, activation, deployment, execution, or physical authorization.",
            (
                ShowcaseClassification.IMPLEMENTED,
                ShowcaseClassification.INERT_EVIDENCE_ONLY,
            ),
            (activation_eligibility,),
            (
                ShowcaseNonClaim.ACTIVE_OR_INSTALLED_POLICY,
                ShowcaseNonClaim.EXECUTED_MOTION,
                ShowcaseNonClaim.POLICY_ACTIVATION,
                ShowcaseNonClaim.RUNTIME_DISPATCH,
                ShowcaseNonClaim.SAFETY_BYPASS,
            ),
        ),
        _capability(
            13,
            "production-policy-activation",
            "Production policy activation",
            "No production activation gate, installed-policy state, model runner, or policy execution path is implemented.",
            (ShowcaseClassification.NOT_YET_IMPLEMENTED,),
            (activation_eligibility,),
            (
                ShowcaseNonClaim.ACTIVE_OR_INSTALLED_POLICY,
                ShowcaseNonClaim.MODEL_EXECUTION,
                ShowcaseNonClaim.POLICY_ACTIVATION,
                ShowcaseNonClaim.RUNTIME_DISPATCH,
                ShowcaseNonClaim.SAFETY_BYPASS,
            ),
        ),
        _capability(
            14,
            "physical-hardware-validation",
            "Physical hardware validation",
            "Current scenario and simulation-control evidence does not validate final mechanics, real sensors, actuators, contacts, balance, or human-safe physical operation.",
            (
                ShowcaseClassification.NOT_YET_IMPLEMENTED,
                ShowcaseClassification.NOT_PHYSICALLY_VALIDATED,
            ),
            (simulation, scenarios),
            (
                ShowcaseNonClaim.EXECUTED_MOTION,
                ShowcaseNonClaim.HARDWARE_AUTHORITY,
                ShowcaseNonClaim.PHYSICAL_SAFETY_CERTIFICATION,
                ShowcaseNonClaim.PHYSICAL_VALIDATION,
            ),
        ),
    )
    return ShowcaseManifest(
        title="Ayyo Software Showcase Foundation v1",
        summary="A deterministic public-contract inventory of implemented software evidence, explicit test and simulation classifications, and bounded unavailable capabilities.",
        capabilities=capabilities,
        evidence=evidence,
    )


def verify_showcase_catalog(manifest: object) -> bool:
    """Verify structural integrity and exact equality to the reviewed live catalog."""
    return verify_showcase_manifest(manifest) and manifest == build_showcase_manifest()


def capability_by_id(
    manifest: ShowcaseManifest, capability_id: str
) -> ShowcaseCapability:
    if not verify_showcase_catalog(manifest):
        raise UnknownShowcaseCapabilityError(
            "capability lookup requires the reviewed v1 showcase catalog"
        )
    try:
        capability_id = identifier(capability_id, "capability_id")
    except ValueError as error:
        raise UnknownShowcaseCapabilityError(
            "unknown showcase capability"
        ) from error
    for capability in manifest.capabilities:
        if capability.capability_id == capability_id:
            return capability
    raise UnknownShowcaseCapabilityError(
        f"unknown showcase capability: {capability_id}"
    )
