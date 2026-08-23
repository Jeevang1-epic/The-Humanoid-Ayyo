"""Strict declarative ROS service endpoint contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from ayyo_skill_manager import (
    MAX_SCHEMA_DEPTH,
    MAX_SCHEMA_NODES,
    MAX_SKILL_TIMEOUT_MS,
    SchemaProperty,
    SkillManagerError,
    ValueSchema,
    ValueType,
)

from .canonical import JSONValue
from .errors import InvalidRosEndpointError
from .models import (
    RuntimeFingerprint,
    RuntimeFingerprintKind,
    fingerprint_document,
    validate_identifier,
)


MAX_ROS_NAME_LENGTH = 256
_ROS_PACKAGE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_ROS_INTERFACE_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_ROS_NAME_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class RosEndpointKind(StrEnum):
    """Endpoint kinds implemented by Runtime Bridge v1."""

    SERVICE_REQUEST = "service_request"


class RosEndpointAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


def _validate_schema_graph(schema: object, *, field_name: str) -> ValueSchema:
    if type(schema) is not ValueSchema:
        raise InvalidRosEndpointError(f"{field_name} must be a ValueSchema")
    stack: list[tuple[ValueSchema, int, bool]] = [(schema, 0, False)]
    active: set[int] = set()
    nodes = 0
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(current))
            continue
        nodes += 1
        if nodes > MAX_SCHEMA_NODES:
            raise InvalidRosEndpointError(f"{field_name} exceeds the schema node limit")
        if depth > MAX_SCHEMA_DEPTH:
            raise InvalidRosEndpointError(f"{field_name} exceeds the schema depth limit")
        identity = id(current)
        if identity in active:
            raise InvalidRosEndpointError(f"{field_name} cannot contain reference cycles")
        active.add(identity)
        stack.append((current, depth, True))
        if not isinstance(current.properties, tuple) or not all(
            type(item) is SchemaProperty for item in current.properties
        ):
            raise InvalidRosEndpointError(
                f"{field_name} contains invalid schema properties"
            )
        children = [item.schema for item in current.properties]
        if current.item_schema is not None:
            children.append(current.item_schema)
        if not all(type(child) is ValueSchema for child in children):
            raise InvalidRosEndpointError(f"{field_name} contains an invalid schema node")
        stack.extend((child, depth + 1, False) for child in reversed(children))
    return schema


def rebuild_schema_contract(schema: object, *, field_name: str) -> ValueSchema:
    source = _validate_schema_graph(schema, field_name=field_name)

    def rebuild(current: ValueSchema) -> ValueSchema:
        try:
            return ValueSchema(
                current.value_type,
                nullable=current.nullable,
                properties=tuple(
                    SchemaProperty(
                        item.name,
                        rebuild(item.schema),
                        required=item.required,
                    )
                    for item in current.properties
                ),
                item_schema=(
                    None if current.item_schema is None else rebuild(current.item_schema)
                ),
                allow_additional_properties=current.allow_additional_properties,
                allowed_values=current.allowed_values,
                minimum=current.minimum,
                maximum=current.maximum,
                min_length=current.min_length,
                max_length=current.max_length,
                min_items=current.min_items,
                max_items=current.max_items,
            )
        except SkillManagerError as error:
            raise InvalidRosEndpointError(
                f"{field_name} failed schema integrity reconstruction"
            ) from error

    rebuilt = rebuild(source)
    if rebuilt != source:
        raise InvalidRosEndpointError(f"{field_name} is not canonical")
    return rebuilt


def schema_document(schema: ValueSchema) -> dict[str, JSONValue]:
    """Build a canonical document from the public Skill Manager schema contract."""

    _validate_schema_graph(schema, field_name="endpoint schema")
    return {
        "allow_additional_properties": schema.allow_additional_properties,
        "allowed_values": list(schema.allowed_values),
        "item_schema": (
            None if schema.item_schema is None else schema_document(schema.item_schema)
        ),
        "max_items": schema.max_items,
        "max_length": schema.max_length,
        "maximum": schema.maximum,
        "min_items": schema.min_items,
        "min_length": schema.min_length,
        "minimum": schema.minimum,
        "nullable": schema.nullable,
        "properties": [
            {
                "name": item.name,
                "required": item.required,
                "schema": schema_document(item.schema),
            }
            for item in schema.properties
        ],
        "value_type": schema.value_type.value,
    }


def _validate_ros_name(value: object, *, field_name: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise InvalidRosEndpointError(f"{field_name} must be a non-empty trimmed string")
    if len(value) > MAX_ROS_NAME_LENGTH or pattern.fullmatch(value) is None:
        raise InvalidRosEndpointError(f"{field_name} is not a supported ROS name")
    return value


def _validate_namespace(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise InvalidRosEndpointError("namespace must be a non-empty trimmed string")
    if len(value) > MAX_ROS_NAME_LENGTH or not value.startswith("/"):
        raise InvalidRosEndpointError("namespace must be an absolute bounded ROS namespace")
    if value == "/":
        return value
    if value.endswith("/") or any(
        _ROS_NAME_TOKEN_PATTERN.fullmatch(token) is None
        for token in value[1:].split("/")
    ):
        raise InvalidRosEndpointError("namespace contains an unsupported ROS name token")
    return value


@dataclass(frozen=True, slots=True, init=False)
class RosServiceEndpoint:
    """An allowlistable ROS service identity with structural request/response contracts."""

    endpoint_id: str
    kind: RosEndpointKind
    backend_id: str
    package_name: str
    interface_name: str
    endpoint_name: str
    namespace: str
    request_schema: ValueSchema
    response_schema: ValueSchema
    timeout_ms: int
    availability: RosEndpointAvailability
    fingerprint: RuntimeFingerprint

    def __init__(
        self,
        *,
        endpoint_id: str,
        backend_id: str,
        package_name: str,
        interface_name: str,
        endpoint_name: str,
        namespace: str,
        request_schema: ValueSchema,
        response_schema: ValueSchema,
        timeout_ms: int,
        availability: RosEndpointAvailability,
    ) -> None:
        endpoint_id = validate_identifier(
            endpoint_id,
            field_name="endpoint_id",
            error_type=InvalidRosEndpointError,
        )
        backend_id = validate_identifier(
            backend_id,
            field_name="endpoint backend_id",
            error_type=InvalidRosEndpointError,
        )
        package_name = _validate_ros_name(
            package_name,
            field_name="package_name",
            pattern=_ROS_PACKAGE_PATTERN,
        )
        interface_name = _validate_ros_name(
            interface_name,
            field_name="interface_name",
            pattern=_ROS_INTERFACE_PATTERN,
        )
        endpoint_name = _validate_ros_name(
            endpoint_name,
            field_name="endpoint_name",
            pattern=_ROS_NAME_TOKEN_PATTERN,
        )
        namespace = _validate_namespace(namespace)
        request_schema = rebuild_schema_contract(
            request_schema,
            field_name="request_schema",
        )
        response_schema = rebuild_schema_contract(
            response_schema,
            field_name="response_schema",
        )
        if (
            request_schema.value_type is not ValueType.OBJECT
            or request_schema.nullable
            or response_schema.value_type is not ValueType.OBJECT
            or response_schema.nullable
        ):
            raise InvalidRosEndpointError(
                "service request and response schemas must be non-null objects"
            )
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= MAX_SKILL_TIMEOUT_MS:
            raise InvalidRosEndpointError("endpoint timeout_ms is outside v1 bounds")
        if not isinstance(availability, RosEndpointAvailability):
            raise InvalidRosEndpointError("endpoint availability is invalid")
        document: dict[str, JSONValue] = {
            "availability": availability.value,
            "backend_id": backend_id,
            "endpoint_id": endpoint_id,
            "endpoint_name": endpoint_name,
            "interface_name": interface_name,
            "kind": RosEndpointKind.SERVICE_REQUEST.value,
            "namespace": namespace,
            "package_name": package_name,
            "request_schema": schema_document(request_schema),
            "response_schema": schema_document(response_schema),
            "schema": "ayyo.runtime-bridge.ros-service-endpoint.v1",
            "timeout_ms": timeout_ms,
        }
        object.__setattr__(self, "endpoint_id", endpoint_id)
        object.__setattr__(self, "kind", RosEndpointKind.SERVICE_REQUEST)
        object.__setattr__(self, "backend_id", backend_id)
        object.__setattr__(self, "package_name", package_name)
        object.__setattr__(self, "interface_name", interface_name)
        object.__setattr__(self, "endpoint_name", endpoint_name)
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "request_schema", request_schema)
        object.__setattr__(self, "response_schema", response_schema)
        object.__setattr__(self, "timeout_ms", timeout_ms)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(
            self,
            "fingerprint",
            fingerprint_document(
                RuntimeFingerprintKind.ENDPOINT,
                document,
                error_type=InvalidRosEndpointError,
            ),
        )

    @property
    def fully_qualified_name(self) -> str:
        prefix = "" if self.namespace == "/" else self.namespace
        return f"{prefix}/{self.endpoint_name}"


def rebuild_ros_service_endpoint(endpoint: object) -> RosServiceEndpoint:
    """Reconstruct all endpoint fields before accepting a caller-owned object."""

    if type(endpoint) is not RosServiceEndpoint:
        raise InvalidRosEndpointError("endpoint must be a RosServiceEndpoint")
    rebuilt = RosServiceEndpoint(
        endpoint_id=endpoint.endpoint_id,
        backend_id=endpoint.backend_id,
        package_name=endpoint.package_name,
        interface_name=endpoint.interface_name,
        endpoint_name=endpoint.endpoint_name,
        namespace=endpoint.namespace,
        request_schema=endpoint.request_schema,
        response_schema=endpoint.response_schema,
        timeout_ms=endpoint.timeout_ms,
        availability=endpoint.availability,
    )
    if rebuilt != endpoint:
        raise InvalidRosEndpointError("ROS endpoint fingerprint is stale")
    return rebuilt
