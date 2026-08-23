from datetime import datetime, timezone
import unittest
from uuid import UUID

from ayyo_memory import MemoryType, Provenance, ProvenanceType
from ayyo_memory_validation import (
    CandidateConfidenceError,
    CandidateEvidence,
    CandidateProvenanceError,
    CandidateTimestampError,
    CandidateValidationError,
    CyclicValueError,
    InvalidCorrectionRequestError,
    NormalizationError,
    NormalizedIdentity,
    PolicyInvariantError,
    UnsupportedValueError,
    canonicalize_json,
    copy_json,
    normalize_identity_text,
)


OBSERVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def owner_statement(details=None) -> Provenance:
    return Provenance(
        ProvenanceType.EXPLICIT_OWNER_STATEMENT,
        "owner.voice",
        {} if details is None else details,
    )


class NormalizationAndModelTest(unittest.TestCase):
    def candidate(self, **overrides) -> CandidateEvidence:
        arguments = {
            "memory_type": MemoryType.PREFERENCE,
            "subject": "owner",
            "predicate": "preferred_drink",
            "value": "tea",
            "provenance": owner_statement(),
            "confidence": 0.9,
            "observed_at": OBSERVED_AT,
        }
        arguments.update(overrides)
        return CandidateEvidence(**arguments)

    def test_unicode_normalization_uses_nfc(self) -> None:
        decomposed = "Cafe\u0301"
        self.assertEqual("Café", normalize_identity_text(decomposed))

    def test_whitespace_normalization_is_deterministic(self) -> None:
        raw = "  owner\t  primary\nprofile  "
        self.assertEqual("owner primary profile", normalize_identity_text(raw))
        self.assertEqual(
            normalize_identity_text(raw),
            normalize_identity_text(normalize_identity_text(raw)),
        )

    def test_unicode_whitespace_collapses_but_format_controls_are_preserved(self) -> None:
        self.assertEqual(
            "owner primary profile",
            normalize_identity_text("\u00a0owner\u2003primary\u202f\nprofile\u00a0"),
        )
        unusual = "owner\u200dprofile"
        self.assertEqual(unusual, normalize_identity_text(unusual))
        self.assertNotEqual(
            normalize_identity_text(unusual),
            normalize_identity_text("owner profile"),
        )

    def test_empty_after_normalization_identity_is_rejected(self) -> None:
        for value in ("", " \t\n", "\u00a0\u2003"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(NormalizationError):
                    normalize_identity_text(value)
                with self.assertRaises(NormalizationError):
                    self.candidate(subject=value)

    def test_normalized_identity_rejects_noncanonical_text(self) -> None:
        with self.assertRaises(PolicyInvariantError):
            NormalizedIdentity(
                memory_type=MemoryType.PREFERENCE,
                subject=" owner ",
                predicate="preferred_drink",
            )

    def test_case_is_preserved(self) -> None:
        self.assertEqual("Owner", normalize_identity_text(" Owner "))
        self.assertNotEqual(
            normalize_identity_text("Owner"),
            normalize_identity_text("owner"),
        )

    def test_canonical_json_ignores_dictionary_order(self) -> None:
        left = {"b": 2, "a": 1}
        right = {"a": 1, "b": 2}
        self.assertEqual(canonicalize_json(left), canonicalize_json(right))
        self.assertEqual('{"a":1,"b":2}', canonicalize_json(left))

    def test_nested_json_canonicalization_is_stable(self) -> None:
        value = {
            "outer": [{"z": False, "a": [3, 2, 1]}, None],
            "name": "unchanged text",
        }
        first = canonicalize_json(value)
        second = canonicalize_json(copy_json(value))
        self.assertEqual(first, second)

    def test_scalar_json_types_remain_distinct(self) -> None:
        values = (None, False, 0, 0.0, -0.0, True, 1, 1.0, "1")
        canonical_values = tuple(canonicalize_json(value) for value in values)

        self.assertEqual(
            ("null", "false", "0", "0.0", "-0.0", "true", "1", "1.0", '"1"'),
            canonical_values,
        )
        self.assertEqual(len(values), len(set(canonical_values)))

    def test_deep_json_structure_is_handled_without_recursive_validation(self) -> None:
        value = "leaf"
        for _ in range(2_000):
            value = [value]

        canonical = canonicalize_json(value)
        self.assertEqual(canonical, canonicalize_json(copy_json(value)))

    def test_unsupported_and_non_finite_values_are_rejected(self) -> None:
        for value in (
            {"invalid": object()},
            {"invalid": {1, 2}},
            {1: "non-string key"},
            {"invalid": float("nan")},
            {"invalid": float("inf")},
            {"invalid": -float("inf")},
        ):
            with self.subTest(value=repr(value)):
                with self.assertRaises(UnsupportedValueError):
                    canonicalize_json(value)

    def test_cyclic_values_are_rejected_without_recursion_failure(self) -> None:
        cyclic_list = []
        cyclic_list.append(cyclic_list)
        with self.assertRaises(CyclicValueError):
            canonicalize_json(cyclic_list)

        cyclic_dict = {}
        cyclic_dict["self"] = cyclic_dict
        with self.assertRaises(CyclicValueError):
            canonicalize_json(cyclic_dict)

    def test_shared_non_cyclic_structure_is_allowed(self) -> None:
        shared = ["evidence"]
        value = {"first": shared, "second": shared}
        self.assertEqual(
            '{"first":["evidence"],"second":["evidence"]}',
            canonicalize_json(value),
        )

    def test_candidate_rejects_missing_or_malformed_provenance(self) -> None:
        with self.assertRaises(CandidateProvenanceError):
            self.candidate(provenance=None)
        with self.assertRaises(CandidateProvenanceError):
            self.candidate(provenance={"source": "owner"})

        mutated = owner_statement()
        mutated.details["invalid"] = object()
        with self.assertRaises(CandidateProvenanceError):
            self.candidate(provenance=mutated)

    def test_candidate_confidence_validation(self) -> None:
        for confidence in (-0.1, 1.1, float("nan"), float("inf"), True, "high"):
            with self.subTest(confidence=confidence):
                with self.assertRaises(CandidateConfidenceError):
                    self.candidate(confidence=confidence)

    def test_candidate_timestamp_requires_utc(self) -> None:
        with self.assertRaises(CandidateTimestampError):
            self.candidate(observed_at=datetime(2026, 1, 1, 12, 0))
        with self.assertRaises(CandidateTimestampError):
            self.candidate(
                observed_at=datetime.fromisoformat("2026-01-01T12:00:00+05:30")
            )

    def test_candidate_rejects_malformed_correction_intent(self) -> None:
        with self.assertRaises(InvalidCorrectionRequestError):
            self.candidate(correction_reason="Missing target")
        with self.assertRaises(InvalidCorrectionRequestError):
            self.candidate(correction_target_id="not-a-uuid", correction_reason="Fix")
        with self.assertRaises(InvalidCorrectionRequestError):
            self.candidate(correction_target_id=UUID(int=1), correction_reason=" ")

    def test_reserved_trace_metadata_key_is_rejected(self) -> None:
        with self.assertRaises(CandidateValidationError):
            self.candidate(metadata={"ayyo_memory_validation": {"forged": True}})

    def test_candidate_snapshots_mutable_input_and_returns_copies(self) -> None:
        value = {"choices": ["tea"]}
        metadata = {"room": {"name": "kitchen"}}
        provenance = owner_statement({"frames": ["frame-1"]})
        candidate = self.candidate(
            value=value,
            metadata=metadata,
            provenance=provenance,
        )

        value["choices"].append("coffee")
        metadata["room"]["name"] = "workshop"
        provenance.details["frames"].append("frame-2")
        returned_value = candidate.value
        returned_value["choices"].append("water")

        self.assertEqual({"choices": ["tea"]}, candidate.value)
        self.assertEqual({"room": {"name": "kitchen"}}, candidate.metadata)
        self.assertEqual({"frames": ["frame-1"]}, candidate.provenance.details)

    def test_original_identity_is_preserved_on_candidate(self) -> None:
        candidate = self.candidate(
            subject="  Cafe\u0301   Owner ",
            predicate=" preferred\t drink ",
        )
        self.assertEqual("  Cafe\u0301   Owner ", candidate.subject)
        self.assertEqual(" preferred\t drink ", candidate.predicate)


if __name__ == "__main__":
    unittest.main()
