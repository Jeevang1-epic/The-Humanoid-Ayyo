from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import unittest
from uuid import UUID

from ayyo_memory import ProvenanceType
from ayyo_personal_context import (
    ContextDomain,
    ContextEntry,
    ContextIdentity,
    ContextInvariantError,
    ContextSnapshotVersion,
    ContextState,
    ContextValue,
    EvidenceReference,
    InvalidContextQueryError,
    PersonalContextSnapshot,
)
from ayyo_personal_context.models import compute_snapshot_version


NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def evidence(memory_id: int = 1, *, details=None) -> EvidenceReference:
    return EvidenceReference(
        memory_id=UUID(int=memory_id),
        provenance_type=ProvenanceType.EXPLICIT_OWNER_STATEMENT,
        provenance_source_id="owner.voice",
        provenance_details={"frame_ids": ["frame-1"]} if details is None else details,
        metadata={},
        confidence=0.9,
        observed_at=NOW,
        recorded_at=NOW,
    )


def resolved_entry(*, value="tea", reference=None) -> ContextEntry:
    identity = ContextIdentity(
        ContextDomain.PREFERENCE,
        "owner",
        "preferred_drink",
    )
    return ContextEntry(
        identity=identity,
        state=ContextState.RESOLVED,
        values=(
            ContextValue(
                value=value,
                evidence=(evidence() if reference is None else reference,),
            ),
        ),
    )


class PersonalContextModelTest(unittest.TestCase):
    def test_values_and_provenance_are_defensive_snapshots(self) -> None:
        raw_value = {"choices": ["tea"]}
        raw_details = {"frames": ["frame-1"]}
        reference = evidence(details=raw_details)
        value = ContextValue(value=raw_value, evidence=(reference,))

        raw_value["choices"].append("coffee")
        raw_details["frames"].append("frame-2")
        returned_value = value.value
        returned_details = reference.provenance_details
        returned_value["choices"].append("water")
        returned_details["frames"].append("frame-3")

        self.assertEqual({"choices": ["tea"]}, value.value)
        self.assertEqual({"frames": ["frame-1"]}, reference.provenance_details)

    def test_deep_json_values_copy_without_recursion_failure(self) -> None:
        value = "leaf"
        for _ in range(2_000):
            value = [value]

        context_value = ContextValue(value=value, evidence=(evidence(),))
        copied = context_value.value
        depth = 0
        while isinstance(copied, list):
            depth += 1
            copied = copied[0]

        self.assertEqual(2_000, depth)
        self.assertEqual("leaf", copied)

    def test_public_models_are_frozen(self) -> None:
        identity = ContextIdentity(
            ContextDomain.PREFERENCE,
            "owner",
            "preferred_drink",
        )
        with self.assertRaises(FrozenInstanceError):
            identity.predicate = "other"
        with self.assertRaises(FrozenInstanceError):
            evidence().confidence = 0.1

    def test_context_value_requires_sorted_unique_evidence(self) -> None:
        with self.assertRaises(ContextInvariantError):
            ContextValue(value="tea", evidence=())
        with self.assertRaises(ContextInvariantError):
            ContextValue(value="tea", evidence=(evidence(2), evidence(1)))
        with self.assertRaises(ContextInvariantError):
            ContextValue(value="tea", evidence=(evidence(1), evidence(1)))

    def test_context_entry_rejects_impossible_states(self) -> None:
        entry = resolved_entry()
        with self.assertRaises(ContextInvariantError):
            replace(entry, state=ContextState.UNKNOWN)
        with self.assertRaises(ContextInvariantError):
            replace(entry, state="resolved")
        with self.assertRaises(ContextInvariantError):
            replace(entry, conflict_ids=(UUID(int=3),))
        with self.assertRaises(ContextInvariantError):
            replace(entry, state=ContextState.CONFLICTED)

    def test_snapshot_rejects_forged_version_and_wrong_owner(self) -> None:
        entry = resolved_entry()
        version = compute_snapshot_version("owner", (entry,))
        snapshot = PersonalContextSnapshot("owner", (entry,), version)
        self.assertEqual(version, snapshot.version)

        with self.assertRaises(ContextInvariantError):
            replace(
                snapshot,
                version=ContextSnapshotVersion(digest="0" * 64),
            )
        with self.assertRaises(ContextInvariantError):
            PersonalContextSnapshot(
                "another-owner",
                (entry,),
                compute_snapshot_version("another-owner", (entry,)),
            )

    def test_snapshot_lookup_returns_typed_unknown_without_fabricated_entry(self) -> None:
        entry = resolved_entry()
        snapshot = PersonalContextSnapshot(
            "owner",
            (entry,),
            compute_snapshot_version("owner", (entry,)),
        )

        result = snapshot.get_context(ContextDomain.PREFERENCE, "favorite_color")

        self.assertEqual(ContextState.UNKNOWN, result.state)
        self.assertIsNone(result.entry)
        self.assertEqual(snapshot.version, result.snapshot_version)

    def test_lookup_preserves_exact_predicate_and_rejects_invalid_queries(self) -> None:
        entry = resolved_entry()
        snapshot = PersonalContextSnapshot(
            "owner",
            (entry,),
            compute_snapshot_version("owner", (entry,)),
        )

        self.assertEqual(
            ContextState.UNKNOWN,
            snapshot.get_context(ContextDomain.PREFERENCE, "Preferred_Drink").state,
        )
        with self.assertRaises(InvalidContextQueryError):
            snapshot.get_context(ContextDomain.PREFERENCE, " preferred_drink")
        with self.assertRaises(InvalidContextQueryError):
            snapshot.get_context("preference", "preferred_drink")


if __name__ == "__main__":
    unittest.main()
