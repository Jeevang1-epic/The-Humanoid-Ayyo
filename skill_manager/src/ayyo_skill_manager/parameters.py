"""Deterministic validation for the bounded Skill Manager v1 schema."""

from __future__ import annotations

from .canonical import JSONValue, canonicalize_json, copy_json
from .errors import InvalidSkillParametersError
from .schema import ValueSchema, ValueType, validate_schema_graph


def _type_matches(value: JSONValue, value_type: ValueType) -> bool:
    if value_type is ValueType.STRING:
        return type(value) is str
    if value_type is ValueType.INTEGER:
        return type(value) is int
    if value_type is ValueType.NUMBER:
        return type(value) in {int, float}
    if value_type is ValueType.BOOLEAN:
        return type(value) is bool
    if value_type is ValueType.NULL:
        return value is None
    if value_type is ValueType.ARRAY:
        return type(value) is list
    return type(value) is dict


def _validate_node(schema: ValueSchema, value: JSONValue, path: str) -> None:
    if value is None and schema.nullable:
        return
    if not _type_matches(value, schema.value_type):
        raise InvalidSkillParametersError(
            f"{path} must be {schema.value_type.value}"
        )
    if schema.allowed_values:
        actual = canonicalize_json(
            value,
            field_name=path,
            error_type=InvalidSkillParametersError,
        )
        allowed = {
            canonicalize_json(
                item,
                field_name=f"{path} allowed value",
                error_type=InvalidSkillParametersError,
            )
            for item in schema.allowed_values
        }
        if actual not in allowed:
            raise InvalidSkillParametersError(f"{path} is not an allowed value")
    if type(value) is str:
        if schema.min_length is not None and len(value) < schema.min_length:
            raise InvalidSkillParametersError(f"{path} is shorter than min_length")
        if schema.max_length is not None and len(value) > schema.max_length:
            raise InvalidSkillParametersError(f"{path} exceeds max_length")
    elif type(value) in {int, float}:
        if schema.minimum is not None and value < schema.minimum:
            raise InvalidSkillParametersError(f"{path} is below minimum")
        if schema.maximum is not None and value > schema.maximum:
            raise InvalidSkillParametersError(f"{path} exceeds maximum")
    elif type(value) is list:
        if schema.min_items is not None and len(value) < schema.min_items:
            raise InvalidSkillParametersError(f"{path} has fewer than min_items")
        if schema.max_items is not None and len(value) > schema.max_items:
            raise InvalidSkillParametersError(f"{path} exceeds max_items")


def validate_parameters(
    schema: ValueSchema,
    parameters: object,
) -> dict[str, JSONValue]:
    """Validate and defensively copy one proposed parameter object."""

    validate_schema_graph(schema)
    if schema.value_type is not ValueType.OBJECT or schema.nullable:
        raise InvalidSkillParametersError(
            "parameter validation requires a non-null object schema"
        )
    copied = copy_json(
        parameters,
        field_name="skill parameters",
        error_type=InvalidSkillParametersError,
    )
    if type(copied) is not dict:
        raise InvalidSkillParametersError("skill parameters must be a plain object")

    stack: list[tuple[ValueSchema, JSONValue, str]] = [
        (schema, copied, "parameters")
    ]
    while stack:
        current_schema, current_value, path = stack.pop()
        _validate_node(current_schema, current_value, path)
        if current_value is None:
            continue
        if current_schema.value_type is ValueType.OBJECT:
            assert isinstance(current_value, dict)
            properties = {
                item.name: item for item in current_schema.properties
            }
            missing = sorted(
                item.name
                for item in current_schema.properties
                if item.required and item.name not in current_value
            )
            if missing:
                raise InvalidSkillParametersError(
                    f"{path} is missing required fields: {missing}"
                )
            unexpected = sorted(set(current_value) - set(properties))
            if unexpected and not current_schema.allow_additional_properties:
                raise InvalidSkillParametersError(
                    f"{path} contains unexpected fields: {unexpected}"
                )
            for name in sorted(set(current_value) & set(properties), reverse=True):
                stack.append(
                    (
                        properties[name].schema,
                        current_value[name],
                        f"{path}.{name}",
                    )
                )
        elif current_schema.value_type is ValueType.ARRAY:
            assert isinstance(current_value, list)
            assert current_schema.item_schema is not None
            for index in range(len(current_value) - 1, -1, -1):
                stack.append(
                    (
                        current_schema.item_schema,
                        current_value[index],
                        f"{path}[{index}]",
                    )
                )
    return copied
