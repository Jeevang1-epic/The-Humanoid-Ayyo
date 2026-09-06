"""Real public-contract proof that production physical movement stays deferred."""

from __future__ import annotations

from dataclasses import dataclass

from ayyo_executive import (
    CapabilityAvailability,
    CapabilityDefinition,
    CapabilityInvocation,
    CapabilityRegistry,
    ExecutiveRequest,
    ExecutiveService,
    ExpectedResultCategory,
    FailurePolicy,
    ParameterDefinition,
    ParameterType,
    RequestType,
)
from ayyo_memory import MemoryService
from ayyo_personal_context import PersonalContextService
from ayyo_runtime_bridge import (
    RuntimeBridge,
    RuntimeDispatcher,
    RuntimeEndpointRegistry,
)
from ayyo_safety import (
    CapabilitySafetyRule,
    HazardClass,
    SafetyKernel,
    SafetyPolicy,
)
from ayyo_skill_manager import (
    ConcurrencyPolicy,
    FailureSemantics,
    IdempotencyClass,
    SchemaProperty,
    SemanticVersion,
    SkillAvailability,
    SkillDefinition,
    SkillLifecycle,
    SkillManagerService,
    SkillRegistry,
    ValueSchema,
    ValueType,
)


CAPABILITY_ID = 'robot.neck.set-position'
SKILL_ID = 'robot.neck.production-motion-unavailable'


class _EmptyMemoryStore:
    """Read-empty store that rejects every mutation for this policy scenario."""

    write_count = 0

    def add_memory(self, record):
        raise AssertionError('the production policy scenario cannot create memory')

    def get_memory(self, memory_id):
        return None

    def query_memories(self, query):
        return []

    def correct_memory(self, target_id, replacement):
        raise AssertionError('the production policy scenario cannot correct memory')

    def retract_memory(self, memory_id, reason, retracted_at):
        raise AssertionError('the production policy scenario cannot retract memory')

    def get_revision_history(self, memory_id):
        return []

    def list_conflicts(self, **kwargs):
        return []

    def close(self):
        return None


@dataclass(frozen=True, slots=True)
class ProductionMotionBoundaryResult:
    executive_decision: str
    safety_disposition: str
    safety_reason: str
    skill_binding_status: str
    skill_binding_reason: str
    runtime_eligibility: str
    runtime_reason: str
    dispatch_status: str
    production_dispatch_count: int
    development_service_call_count: int
    durable_memory_write_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            'development_service_call_count': self.development_service_call_count,
            'dispatch_status': self.dispatch_status,
            'durable_memory_write_count': self.durable_memory_write_count,
            'executive_decision': self.executive_decision,
            'production_dispatch_count': self.production_dispatch_count,
            'runtime_eligibility': self.runtime_eligibility,
            'runtime_reason': self.runtime_reason,
            'safety_disposition': self.safety_disposition,
            'safety_reason': self.safety_reason,
            'skill_binding_reason': self.skill_binding_reason,
            'skill_binding_status': self.skill_binding_status,
        }


def evaluate_production_motion_boundary() -> ProductionMotionBoundaryResult:
    """Evaluate one structured physical request without any transport dispatch."""
    store = _EmptyMemoryStore()
    memory = MemoryService(store)
    context = PersonalContextService(memory, owner_subject='owner')
    capability = CapabilityDefinition(
        capability_id=CAPABILITY_ID,
        description='Propose one neck position change for immutable Safety review.',
        availability=CapabilityAvailability.AVAILABLE_FOR_PROPOSAL,
        parameters=(ParameterDefinition('position', ParameterType.NUMBER),),
        expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
        failure_policy=FailurePolicy.STOP_PLAN,
    )
    executive = ExecutiveService(context, CapabilityRegistry((capability,)))
    request = ExecutiveRequest(
        request_id='development-scenario-production-motion-request-v1',
        objective='Request one bounded neck position change',
        request_type=RequestType.TASK,
        invocations=(
            CapabilityInvocation(
                step_id='request-neck-position',
                capability_id=CAPABILITY_ID,
                parameters={'position': 0.1},
                dependencies=(),
            ),
        ),
    )
    proposal = executive.evaluate(request)
    safety = SafetyKernel(
        SafetyPolicy(
            capability_rules=(
                CapabilitySafetyRule(
                    capability_id=CAPABILITY_ID,
                    hazard_class=HazardClass.PHYSICAL_MOVEMENT,
                ),
            )
        )
    )
    safety_decision = safety.evaluate(proposal)
    input_schema = ValueSchema(
        ValueType.OBJECT,
        properties=(
            SchemaProperty(
                'position',
                ValueSchema(ValueType.NUMBER, minimum=-1.0, maximum=1.0),
            ),
        ),
    )
    skill = SkillDefinition(
        skill_id=SKILL_ID,
        version=SemanticVersion('1.0.0'),
        name='Unavailable production neck movement',
        description='Declarative compatibility contract with no production backend.',
        capability_ids=(CAPABILITY_ID,),
        backend_id='production.motion.unavailable',
        input_schema=input_schema,
        output_schema=ValueSchema(ValueType.OBJECT),
        safety_classification=HazardClass.PHYSICAL_MOVEMENT,
        expected_result=ExpectedResultCategory.PROPOSED_PHYSICAL_EFFECT,
        timeout_ms=1_000,
        concurrency_policy=ConcurrencyPolicy.PARALLEL,
        idempotency=IdempotencyClass.CONDITIONALLY_IDEMPOTENT,
        failure_semantics=FailureSemantics.REQUIRES_OPERATOR,
        availability=SkillAvailability.AVAILABLE,
        lifecycle=SkillLifecycle.VALIDATED,
    )
    registry = SkillRegistry(
        version=SemanticVersion('1.0.0'),
        skills=(skill,),
    )
    manager = SkillManagerService(registry, safety)
    selection = registry.selection(
        skill_id=SKILL_ID,
        capability_id=CAPABILITY_ID,
        source_step_id='request-neck-position',
    )
    binding = manager.bind(proposal, safety_decision, selection)
    bridge = RuntimeBridge(
        RuntimeEndpointRegistry(version=SemanticVersion('1.0.0'), bindings=())
    )
    runtime_decision = bridge.evaluate(binding)
    dispatch_result = RuntimeDispatcher(bridge).not_dispatched(runtime_decision)
    return ProductionMotionBoundaryResult(
        executive_decision=proposal.decision_type.value,
        safety_disposition=safety_decision.disposition.value,
        safety_reason=safety_decision.reason_codes[0].value,
        skill_binding_status=binding.status.value,
        skill_binding_reason=binding.reasons[0].value,
        runtime_eligibility=runtime_decision.status.value,
        runtime_reason=runtime_decision.reasons[0].value,
        dispatch_status=dispatch_result.status.value,
        production_dispatch_count=0,
        development_service_call_count=0,
        durable_memory_write_count=store.write_count,
    )
