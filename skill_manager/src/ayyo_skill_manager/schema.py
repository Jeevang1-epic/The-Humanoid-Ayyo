"""Immutable, deliberately bounded v1 value-schema vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math

from .canonical import JSONScalar, JSONValue, canonicalize_json
from .errors import InvalidSchemaError


MAX_SCHEMA_DEPTH = 16
MAX_SCHEMA_NODES = 512
MAX_SCHEMA_PROPERTIES = 128
MAX_SCHEMA_STRING_LENGTH = 65_536
MAX_SCHEMA_ARRAY_ITEMS = 256


class ValueType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    NULL = "null"
    ARRAY = "array"
    OBJECT = "object"


def _matches_scalar(value: JSONScalar, value_type: ValueType, nullable: bool) -> bool:
    if value is None:
        return nullable or value_type is ValueType.NULL
    if value_type is ValueType.STRING:
        return type(value) is str
    if value_type is ValueType.INTEGER:
        return type(value) is int
    if value_type is ValueType.NUMBER:
        return type(value) in {int, float}
    if value_type is ValueType.BOOLEAN:
        return type(value) is bool
    return False


@dataclass(frozen=True, slots=True)
class SchemaProperty:
    name: str
    schema: ValueSchema
    required: bool = True

    def __post_init__(self) -> None:
        from .models import validate_identifier

        validate_identifier(
            self.name,
            field_name="schema property name",
            error_type=InvalidSchemaError,
        )
        if not isinstance(self.schema, ValueSchema):
            raise InvalidSchemaError("schema property requires a ValueSchema")
        if type(self.required) is not bool:
            raise InvalidSchemaError("schema property required flag must be boolean")


@dataclass(frozen=True, slots=True, init=False)
class ValueSchema:
    value_type: ValueType
    nullable: bool
    properties: tuple[SchemaProperty, ...]
    item_schema: ValueSchema | None
    allow_additional_properties: bool
    allowed_values: tuple[JSONScalar, ...]
    minimum: int | float | None
    maximum: int | float | None
    min_length: int | None
    max_length: int | None
    min_items: int | None
    max_items: int | None

    def __init__(
        self,
        value_type: ValueType,
        *,
        nullable: bool = False,
        properties: tuple[SchemaProperty, ...] = (),
        item_schema: ValueSchema | None = None,
        allow_additional_properties: bool = False,
        allowed_values: tuple[JSONScalar, ...] = (),
        minimum: int | float | None = None,
        maximum: int | float | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        min_items: int | None = None,
        max_items: int | None = None,
    ) -> None:
        if not isinstance(value_type, ValueType):
            raise InvalidSchemaError("value_type must be a ValueType")
        if type(nullable) is not bool or type(allow_additional_properties) is not bool:
            raise InvalidSchemaError("schema flags must be boolean")
        if not isinstance(properties, tuple) or not all(
            isinstance(item, SchemaProperty) for item in properties
        ):
            raise InvalidSchemaError("schema properties must be typed objects")
        if len(properties) > MAX_SCHEMA_PROPERTIES:
            raise InvalidSchemaError("schema properties exceed the v1 limit")
        properties = tuple(sorted(properties, key=lambda item: item.name))
        property_names = tuple(item.name for item in properties)
        if len(property_names) != len(set(property_names)):
            raise InvalidSchemaError("schema property names must be unique")
        if item_schema is not None and not isinstance(item_schema, ValueSchema):
            raise InvalidSchemaError("item_schema must be a ValueSchema")
        if not isinstance(allowed_values, tuple) or not all(
            value is None or type(value) in {str, bool, int, float}
            for value in allowed_values
        ):
            raise InvalidSchemaError("allowed_values must be a tuple of JSON scalars")
        for value in allowed_values:
            if type(value) is float and not math.isfinite(value):
                raise InvalidSchemaError("allowed_values cannot contain non-finite values")
            if not _matches_scalar(value, value_type, nullable):
                raise InvalidSchemaError("allowed_values conflict with the schema type")
        allowed_keys = tuple(
            canonicalize_json(
                value,
                field_name="allowed value",
                error_type=InvalidSchemaError,
            )
            for value in allowed_values
        )
        if len(allowed_keys) != len(set(allowed_keys)):
            raise InvalidSchemaError("allowed_values must be logically unique")
        allowed_values = tuple(
            value for _, value in sorted(zip(allowed_keys, allowed_values), key=lambda item: item[0])
        )
        numeric_bounds = (minimum, maximum)
        if any(
            value is not None
            and (type(value) not in {int, float} or (type(value) is float and not math.isfinite(value)))
            for value in numeric_bounds
        ):
            raise InvalidSchemaError("numeric bounds must be finite numbers")
        for value, field_name in (
            (min_length, "min_length"),
            (max_length, "max_length"),
            (min_items, "min_items"),
            (max_items, "max_items"),
        ):
            if value is not None and (type(value) is not int or value < 0):
                raise InvalidSchemaError(f"{field_name} must be a non-negative integer")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise InvalidSchemaError("minimum cannot exceed maximum")
        if min_length is not None and max_length is not None and min_length > max_length:
            raise InvalidSchemaError("min_length cannot exceed max_length")
        if min_items is not None and max_items is not None and min_items > max_items:
            raise InvalidSchemaError("min_items cannot exceed max_items")
        if max_length is not None and max_length > MAX_SCHEMA_STRING_LENGTH:
            raise InvalidSchemaError("max_length exceeds the v1 string limit")
        if max_items is not None and max_items > MAX_SCHEMA_ARRAY_ITEMS:
            raise InvalidSchemaError("max_items exceeds the v1 array limit")
        if value_type is ValueType.OBJECT:
            if item_schema is not None or any(
                value is not None
                for value in (minimum, maximum, min_length, max_length, min_items, max_items)
            ) or allowed_values:
                raise InvalidSchemaError("object schema has contradictory fields")
        elif value_type is ValueType.ARRAY:
            if item_schema is None:
                raise InvalidSchemaError("array schema requires item_schema")
            if properties or allow_additional_properties or any(
                value is not None for value in (minimum, maximum, min_length, max_length)
            ) or allowed_values:
                raise InvalidSchemaError("array schema has contradictory fields")
        else:
            if properties or item_schema is not None or allow_additional_properties:
                raise InvalidSchemaError("scalar schema cannot declare object or array fields")
            if value_type is ValueType.STRING:
                if any(value is not None for value in (minimum, maximum, min_items, max_items)):
                    raise InvalidSchemaError("string schema has contradictory bounds")
            elif value_type in {ValueType.INTEGER, ValueType.NUMBER}:
                if any(value is not None for value in (min_length, max_length, min_items, max_items)):
                    raise InvalidSchemaError("numeric schema has contradictory bounds")
            elif any(
                value is not None
                for value in (minimum, maximum, min_length, max_length, min_items, max_items)
            ):
                raise InvalidSchemaError("boolean/null schema cannot declare bounds")
        if value_type is ValueType.NULL and nullable:
            raise InvalidSchemaError("null schema cannot also be nullable")
        object.__setattr__(self, "value_type", value_type)
        object.__setattr__(self, "nullable", nullable)
        object.__setattr__(self, "properties", properties)
        object.__setattr__(self, "item_schema", item_schema)
        object.__setattr__(self, "allow_additional_properties", allow_additional_properties)
        object.__setattr__(self, "allowed_values", allowed_values)
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "min_length", min_length)
        object.__setattr__(self, "max_length", max_length)
        object.__setattr__(self, "min_items", min_items)
        object.__setattr__(self, "max_items", max_items)


def validate_schema_graph(schema: ValueSchema) -> None:
    if not isinstance(schema, ValueSchema):
        raise InvalidSchemaError("contract schema must be a ValueSchema")
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
            raise InvalidSchemaError("schema exceeds the v1 node limit")
        if depth > MAX_SCHEMA_DEPTH:
            raise InvalidSchemaError("schema exceeds the v1 depth limit")
        identity = id(current)
        if identity in active:
            raise InvalidSchemaError("schema cannot contain reference cycles")
        active.add(identity)
        stack.append((current, depth, True))
        children = [item.schema for item in current.properties]
        if current.item_schema is not None:
            children.append(current.item_schema)
        stack.extend((child, depth + 1, False) for child in reversed(children))


def schema_document(schema: ValueSchema) -> dict[str, JSONValue]:
    validate_schema_graph(schema)
    return {
        "allow_additional_properties": schema.allow_additional_properties,
        "allowed_values": list(schema.allowed_values),
        "item_schema": None if schema.item_schema is None else schema_document(schema.item_schema),
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
