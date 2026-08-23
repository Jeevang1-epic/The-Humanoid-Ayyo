from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from ayyo_runtime_bridge import (
    InvalidRuntimeContractError,
    RuntimeFingerprint,
    RuntimeFingerprintKind,
)
from ayyo_runtime_bridge.models import fingerprint_document


class RuntimeContractTest(unittest.TestCase):
    def test_fingerprint_is_deterministic_for_mapping_order(self) -> None:
        first = fingerprint_document(
            RuntimeFingerprintKind.REQUEST,
            {"nested": {"b": 2, "a": 1}, "name": "request"},
        )
        second = fingerprint_document(
            RuntimeFingerprintKind.REQUEST,
            {"name": "request", "nested": {"a": 1, "b": 2}},
        )
        self.assertEqual(first, second)
        self.assertEqual(f"request:sha256:{first.digest}", str(first))

    def test_fingerprint_rejects_forged_formats(self) -> None:
        with self.assertRaises(InvalidRuntimeContractError):
            RuntimeFingerprint(RuntimeFingerprintKind.REQUEST, "A" * 64)
        with self.assertRaises(InvalidRuntimeContractError):
            RuntimeFingerprint(
                RuntimeFingerprintKind.REQUEST,
                "0" * 64,
                algorithm="md5",
            )

    def test_fingerprint_is_immutable(self) -> None:
        fingerprint = RuntimeFingerprint(
            RuntimeFingerprintKind.REQUEST,
            "0" * 64,
        )
        with self.assertRaises(FrozenInstanceError):
            fingerprint.digest = "1" * 64

    def test_canonicalization_rejects_unsafe_values(self) -> None:
        cyclic: list[object] = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(InvalidRuntimeContractError, "reference cycles"):
            fingerprint_document(RuntimeFingerprintKind.REQUEST, cyclic)
        with self.assertRaisesRegex(InvalidRuntimeContractError, "non-finite"):
            fingerprint_document(RuntimeFingerprintKind.REQUEST, {"value": float("nan")})
        with self.assertRaisesRegex(InvalidRuntimeContractError, "object keys"):
            fingerprint_document(RuntimeFingerprintKind.REQUEST, {1: "invalid"})

    def test_json_scalar_types_remain_distinct(self) -> None:
        integer = fingerprint_document(RuntimeFingerprintKind.REQUEST, {"value": 1})
        boolean = fingerprint_document(RuntimeFingerprintKind.REQUEST, {"value": True})
        floating = fingerprint_document(RuntimeFingerprintKind.REQUEST, {"value": 1.0})
        self.assertEqual(3, len({integer, boolean, floating}))


if __name__ == "__main__":
    unittest.main()
