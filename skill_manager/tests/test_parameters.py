from __future__ import annotations

import math
import unittest

from ayyo_skill_manager import (
    InvalidSkillParametersError,
    SchemaProperty,
    ValueSchema,
    ValueType,
    validate_parameters,
)
from ayyo_skill_manager.canonical import (
    MAX_JSON_COLLECTION_SIZE,
    MAX_JSON_DEPTH,
)


def schema() -> ValueSchema:
    return ValueSchema(
        ValueType.OBJECT,
        properties=(
            SchemaProperty(
                "enabled",
                ValueSchema(ValueType.BOOLEAN),
            ),
            SchemaProperty(
                "mode",
                ValueSchema(
                    ValueType.STRING,
                    allowed_values=("brief", "full"),
                ),
            ),
            SchemaProperty(
                "options",
                ValueSchema(
                    ValueType.OBJECT,
                    properties=(
                        SchemaProperty(
                            "label",
                            ValueSchema(
                                ValueType.STRING,
                                min_length=1,
                                max_length=8,
                            ),
                        ),
                        SchemaProperty(
                            "limit",
                            ValueSchema(
                                ValueType.INTEGER,
                                minimum=1,
                                maximum=10,
                            ),
                        ),
                    ),
                ),
            ),
            SchemaProperty(
                "scores",
                ValueSchema(
                    ValueType.ARRAY,
                    item_schema=ValueSchema(
                        ValueType.NUMBER,
                        minimum=0,
                        maximum=1,
                    ),
                    min_items=1,
                    max_items=3,
                ),
            ),
            SchemaProperty(
                "note",
                ValueSchema(ValueType.STRING, nullable=True),
                required=False,
            ),
        ),
    )


def valid_parameters() -> dict:
    return {
        "enabled": True,
        "mode": "brief",
        "options": {"label": "owner", "limit": 3},
        "scores": [0, 0.5, 1],
        "note": None,
    }


class ParameterValidationTest(unittest.TestCase):
    def test_valid_nested_parameters_are_defensively_copied(self) -> None:
        source = valid_parameters()
        validated = validate_parameters(schema(), source)
        source["options"]["limit"] = 9
        source["scores"].append(0.25)
        self.assertEqual(3, validated["options"]["limit"])
        self.assertEqual([0, 0.5, 1], validated["scores"])

    def test_missing_and_unexpected_parameters_are_rejected(self) -> None:
        missing = valid_parameters()
        del missing["mode"]
        with self.assertRaisesRegex(InvalidSkillParametersError, "missing required"):
            validate_parameters(schema(), missing)
        unexpected = valid_parameters()
        unexpected["command"] = "never"
        with self.assertRaisesRegex(InvalidSkillParametersError, "unexpected"):
            validate_parameters(schema(), unexpected)

    def test_nested_unexpected_fields_are_rejected(self) -> None:
        parameters = valid_parameters()
        parameters["options"]["extra"] = True
        with self.assertRaisesRegex(InvalidSkillParametersError, "unexpected"):
            validate_parameters(schema(), parameters)

    def test_type_mismatches_preserve_boolean_integer_distinction(self) -> None:
        for value in (True, 1.0, "3"):
            parameters = valid_parameters()
            parameters["options"]["limit"] = value
            with self.subTest(value=value), self.assertRaisesRegex(
                InvalidSkillParametersError,
                "must be integer",
            ):
                validate_parameters(schema(), parameters)

    def test_numeric_string_and_array_bounds_are_enforced(self) -> None:
        mutations = (
            ("limit", 0, "below minimum"),
            ("limit", 11, "exceeds maximum"),
            ("label", "", "shorter"),
            ("label", "too-long-label", "max_length"),
        )
        for name, value, message in mutations:
            parameters = valid_parameters()
            parameters["options"][name] = value
            with self.subTest(name=name, value=value), self.assertRaisesRegex(
                InvalidSkillParametersError,
                message,
            ):
                validate_parameters(schema(), parameters)
        parameters = valid_parameters()
        parameters["scores"] = []
        with self.assertRaisesRegex(InvalidSkillParametersError, "min_items"):
            validate_parameters(schema(), parameters)
        parameters["scores"] = [0, 0.25, 0.5, 1]
        with self.assertRaisesRegex(InvalidSkillParametersError, "max_items"):
            validate_parameters(schema(), parameters)

    def test_allowed_values_are_exact(self) -> None:
        parameters = valid_parameters()
        parameters["mode"] = "unknown"
        with self.assertRaisesRegex(InvalidSkillParametersError, "allowed value"):
            validate_parameters(schema(), parameters)

    def test_non_finite_numbers_are_rejected(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            parameters = valid_parameters()
            parameters["scores"] = [value]
            with self.subTest(value=value), self.assertRaisesRegex(
                InvalidSkillParametersError,
                "non-finite",
            ):
                validate_parameters(schema(), parameters)

    def test_cycles_unsupported_values_and_invalid_keys_are_rejected(self) -> None:
        cyclic: list = []
        cyclic.append(cyclic)
        invalid = (
            {"value": cyclic},
            {"value": object()},
            {1: "invalid key"},
            {"value": lambda: None},
        )
        permissive = ValueSchema(ValueType.OBJECT, allow_additional_properties=True)
        for value in invalid:
            with self.subTest(value_type=type(value)), self.assertRaises(
                InvalidSkillParametersError
            ):
                validate_parameters(permissive, value)

    def test_depth_and_collection_size_are_bounded(self) -> None:
        deep: object = None
        for _ in range(MAX_JSON_DEPTH + 1):
            deep = [deep]
        permissive = ValueSchema(ValueType.OBJECT, allow_additional_properties=True)
        with self.assertRaisesRegex(InvalidSkillParametersError, "depth limit"):
            validate_parameters(permissive, {"value": deep})
        with self.assertRaisesRegex(InvalidSkillParametersError, "collection-size"):
            validate_parameters(
                permissive,
                {"value": [None] * (MAX_JSON_COLLECTION_SIZE + 1)},
            )

    def test_additional_properties_remain_bounded_json(self) -> None:
        permissive = ValueSchema(ValueType.OBJECT, allow_additional_properties=True)
        self.assertEqual(
            {"custom": {"items": [1, "two", False, None]}},
            validate_parameters(
                permissive,
                {"custom": {"items": [1, "two", False, None]}},
            ),
        )


if __name__ == "__main__":
    unittest.main()
