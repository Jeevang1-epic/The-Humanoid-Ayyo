"""Fail-closed binding of Skill Manager invocations to runtime requests."""

from __future__ import annotations

from dataclasses import dataclass, field

from ayyo_skill_manager import (
    InvocationStatus,
    SemanticVersion,
    SkillDefinition,
    SkillInvocation,
    SkillManagerError,
    SkillSelection,
    validate_parameters,
)

from .canonical import JSONValue, copy_json
from .endpoints import RosServiceEndpoint, rebuild_ros_service_endpoint
from .errors import (
    InvalidRosEndpointError,
    InvalidRuntimeBindingError,
    InvalidRuntimeRegistryError,
)
from .models import RuntimeFingerprint, RuntimeFingerprintKind, fingerprint_document
from .registry import (
    RuntimeEndpointBinding,
    RuntimeEndpointRegistry,
    rebuild_semantic_version,
    rebuild_skill_definition,
)


def _context_document(reference: object) -> dict[str, JSONValue]:
    requirement = reference.requirement
    return {
        "conflict_ids": [str(item) for item in reference.conflict_ids],
        "domain": requirement.domain.value,
        "memory_ids": [str(item) for item in reference.memory_ids],
        "predicate": requirement.predicate,
        "required": reference.required,
        "state": reference.state.value,
        "value_digests": list(reference.value_digests),
    }


def _approval_document(approval: object) -> dict[str, JSONValue]:
    return {
        "affected_step_id": approval.affected_step_id,
        "approval_class": approval.approval_class.value,
        "description": approval.description,
        "requirement_id": approval.requirement_id,
        "source": approval.source.value,
    }


def _rebuild_skill(skill: SkillDefinition) -> SkillDefinition:
    try:
        rebuilt = rebuild_skill_definition(skill)
    except InvalidRuntimeRegistryError as error:
        raise InvalidRuntimeBindingError("skill definition failed integrity review") from error
    return rebuilt


def _rebuild_selection(
    selection: SkillSelection,
    skill: SkillDefinition,
) -> SkillSelection:
    try:
        rebuilt = SkillSelection(
            skill_id=selection.skill_id,
            skill_version=selection.skill_version,
            skill_fingerprint=skill.fingerprint,
            capability_id=selection.capability_id,
            source_step_id=selection.source_step_id,
            registry_version=rebuild_semantic_version(
                selection.registry_version,
                field_name="Skill registry version",
            ),
            registry_fingerprint=selection.registry_fingerprint,
        )
    except (SkillManagerError, InvalidRuntimeRegistryError) as error:
        raise InvalidRuntimeBindingError("skill selection failed integrity review") from error
    if rebuilt != selection:
        raise InvalidRuntimeBindingError("skill selection fingerprint is stale")
    return rebuilt


def rebuild_invocation(invocation: object) -> SkillInvocation:
    """Recompute every caller-supplied Skill invocation identity."""

    if type(invocation) is not SkillInvocation:
        raise InvalidRuntimeBindingError(
            "runtime binding requires a public SkillInvocation"
        )
    skill = _rebuild_skill(invocation.skill_definition)
    selection = _rebuild_selection(invocation.selection, skill)
    try:
        rebuilt = SkillInvocation(
            status=invocation.status,
            selection=selection,
            skill_definition=skill,
            parameters=invocation.parameters,
            context_references=invocation.context_references,
            required_approvals=invocation.required_approvals,
            source_request_id=invocation.source_request_id,
            source_executive_decision_id=invocation.source_executive_decision_id,
            source_executive_fingerprint=invocation.source_executive_fingerprint,
            source_safety_decision_id=invocation.source_safety_decision_id,
            source_safety_fingerprint=invocation.source_safety_fingerprint,
            source_proposal_fingerprint=invocation.source_proposal_fingerprint,
            source_policy_fingerprint=invocation.source_policy_fingerprint,
            source_policy_version=invocation.source_policy_version,
        )
    except SkillManagerError as error:
        raise InvalidRuntimeBindingError("skill invocation failed integrity review") from error
    if rebuilt != invocation or rebuilt.fingerprint != invocation.fingerprint:
        raise InvalidRuntimeBindingError("skill invocation fingerprint is stale")
    return rebuilt


def _rebuild_endpoint(endpoint: RosServiceEndpoint) -> RosServiceEndpoint:
    try:
        return rebuild_ros_service_endpoint(endpoint)
    except InvalidRosEndpointError as error:
        raise InvalidRuntimeBindingError(
            "ROS endpoint failed integrity review"
        ) from error


def rebuild_registry(registry: object) -> RuntimeEndpointRegistry:
    """Rebuild a complete endpoint allowlist before using its indexes."""

    if type(registry) is not RuntimeEndpointRegistry:
        raise InvalidRuntimeBindingError(
            "runtime binding requires a RuntimeEndpointRegistry"
        )
    bindings: list[RuntimeEndpointBinding] = []
    for binding in registry.bindings:
        skill = _rebuild_skill(binding.skill_definition)
        bindings.append(
            RuntimeEndpointBinding(
                skill_definition=skill,
                capability_id=binding.capability_id,
                endpoint=_rebuild_endpoint(binding.endpoint),
            )
        )
    rebuilt = RuntimeEndpointRegistry(version=registry.version, bindings=tuple(bindings))
    if rebuilt != registry:
        raise InvalidRuntimeBindingError("runtime registry fingerprint is stale")
    return rebuilt


@dataclass(frozen=True, slots=True, init=False)
class RuntimeRequest:
    """A fully pinned, immutable service request eligible for runtime review."""

    request_id: str
    invocation: SkillInvocation
    endpoint_binding: RuntimeEndpointBinding
    runtime_registry_version: SemanticVersion
    runtime_registry_fingerprint: RuntimeFingerprint
    fingerprint: RuntimeFingerprint
    _request_fields: JSONValue = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        invocation: SkillInvocation,
        endpoint_binding: RuntimeEndpointBinding,
        runtime_registry_version: SemanticVersion,
        runtime_registry_fingerprint: RuntimeFingerprint,
    ) -> None:
        invocation = rebuild_invocation(invocation)
        if type(endpoint_binding) is not RuntimeEndpointBinding:
            raise InvalidRuntimeBindingError("runtime endpoint binding is invalid")
        try:
            rebuilt_binding = RuntimeEndpointBinding(
                skill_definition=_rebuild_skill(endpoint_binding.skill_definition),
                capability_id=endpoint_binding.capability_id,
                endpoint=_rebuild_endpoint(endpoint_binding.endpoint),
            )
        except InvalidRuntimeRegistryError as error:
            raise InvalidRuntimeBindingError(
                "runtime endpoint binding failed integrity review"
            ) from error
        if rebuilt_binding != endpoint_binding:
            raise InvalidRuntimeBindingError(
                "runtime endpoint binding fingerprint is stale"
            )
        endpoint_binding = rebuilt_binding
        if invocation.status is not InvocationStatus.ELIGIBLE_FOR_RUNTIME_HANDOFF:
            raise InvalidRuntimeBindingError(
                "only an upstream runtime-handoff-eligible invocation can form a request"
            )
        try:
            runtime_registry_version = rebuild_semantic_version(
                runtime_registry_version,
                field_name="runtime registry version",
            )
        except InvalidRuntimeRegistryError as error:
            raise InvalidRuntimeBindingError(
                "runtime registry version is invalid"
            ) from error
        if (
            not isinstance(runtime_registry_fingerprint, RuntimeFingerprint)
            or runtime_registry_fingerprint.kind is not RuntimeFingerprintKind.REGISTRY
        ):
            raise InvalidRuntimeBindingError("runtime registry fingerprint is invalid")
        if (
            endpoint_binding.skill_id != invocation.selection.skill_id
            or endpoint_binding.skill_version != invocation.selection.skill_version
            or endpoint_binding.skill_fingerprint != invocation.selection.skill_fingerprint
            or endpoint_binding.capability_id != invocation.selection.capability_id
            or endpoint_binding.backend_id != invocation.backend_id
        ):
            raise InvalidRuntimeBindingError(
                "Skill invocation and runtime endpoint binding disagree"
            )
        try:
            request_fields = validate_parameters(
                endpoint_binding.endpoint.request_schema,
                invocation.parameters,
            )
        except SkillManagerError as error:
            raise InvalidRuntimeBindingError(
                "invocation parameters do not match the endpoint request contract"
            ) from error
        request_fields = copy_json(
            request_fields,
            field_name="runtime request fields",
            error_type=InvalidRuntimeBindingError,
        )
        document: dict[str, JSONValue] = {
            "backend_id": invocation.backend_id,
            "capability_id": invocation.selection.capability_id,
            "concurrency_policy": invocation.concurrency_policy.value,
            "context_references": [
                _context_document(item) for item in invocation.context_references
            ],
            "endpoint_binding_fingerprint": str(endpoint_binding.fingerprint),
            "endpoint_fingerprint": str(endpoint_binding.endpoint.fingerprint),
            "invocation_fingerprint": str(invocation.fingerprint),
            "invocation_id": invocation.invocation_id,
            "request_fields": request_fields,
            "required_approvals": [
                _approval_document(item) for item in invocation.required_approvals
            ],
            "required_resources": [
                {"access": item.access.value, "resource_id": item.resource_id}
                for item in invocation.required_resources
            ],
            "runtime_registry_fingerprint": str(runtime_registry_fingerprint),
            "runtime_registry_version": str(runtime_registry_version),
            "schema": "ayyo.runtime-bridge.request.v1",
            "skill_fingerprint": str(invocation.selection.skill_fingerprint),
            "skill_id": invocation.selection.skill_id,
            "skill_registry_fingerprint": str(
                invocation.selection.registry_fingerprint
            ),
            "skill_registry_version": str(invocation.selection.registry_version),
            "skill_version": str(invocation.selection.skill_version),
            "source_executive_decision_id": invocation.source_executive_decision_id,
            "source_executive_fingerprint": str(
                invocation.source_executive_fingerprint
            ),
            "source_policy_fingerprint": str(invocation.source_policy_fingerprint),
            "source_policy_version": invocation.source_policy_version,
            "source_proposal_fingerprint": str(invocation.source_proposal_fingerprint),
            "source_request_id": invocation.source_request_id,
            "source_safety_decision_id": invocation.source_safety_decision_id,
            "source_safety_fingerprint": str(invocation.source_safety_fingerprint),
            "source_step_id": invocation.selection.source_step_id,
        }
        fingerprint = fingerprint_document(
            RuntimeFingerprintKind.REQUEST,
            document,
            error_type=InvalidRuntimeBindingError,
        )
        object.__setattr__(self, "request_id", f"runtime-request-{fingerprint.digest}")
        object.__setattr__(self, "invocation", invocation)
        object.__setattr__(self, "endpoint_binding", endpoint_binding)
        object.__setattr__(self, "runtime_registry_version", runtime_registry_version)
        object.__setattr__(self, "runtime_registry_fingerprint", runtime_registry_fingerprint)
        object.__setattr__(self, "fingerprint", fingerprint)
        object.__setattr__(self, "_request_fields", request_fields)

    @property
    def request_fields(self) -> dict[str, JSONValue]:
        copied = copy_json(self._request_fields, field_name="runtime request fields")
        assert isinstance(copied, dict)
        return copied


def bind_runtime_request(
    invocation: SkillInvocation,
    registry: RuntimeEndpointRegistry,
) -> RuntimeRequest:
    """Bind one verified eligible invocation to the current endpoint allowlist."""

    current_invocation = rebuild_invocation(invocation)
    current_registry = rebuild_registry(registry)
    binding = current_registry.resolve(
        skill_id=current_invocation.selection.skill_id,
        skill_version=current_invocation.selection.skill_version,
        capability_id=current_invocation.selection.capability_id,
        backend_id=current_invocation.backend_id,
    )
    if binding is None:
        raise InvalidRuntimeBindingError(
            "invocation has no exact registered Skill/backend/endpoint binding"
        )
    if binding.skill_fingerprint != current_invocation.selection.skill_fingerprint:
        raise InvalidRuntimeBindingError(
            "registered runtime binding targets a different Skill fingerprint"
        )
    return RuntimeRequest(
        invocation=current_invocation,
        endpoint_binding=binding,
        runtime_registry_version=current_registry.version,
        runtime_registry_fingerprint=current_registry.fingerprint,
    )
