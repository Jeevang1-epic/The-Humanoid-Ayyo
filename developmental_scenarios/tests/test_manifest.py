from dataclasses import FrozenInstanceError
import unittest
from unittest import mock

from ayyo_developmental_scenarios import (
    build_scenario_manifest,
    canonical_manifest_json,
    DevelopmentScenarioDefinition,
    DevelopmentScenarioManifestEntry,
    MANIFEST_SCHEMA_ID,
    MANIFEST_SCHEMA_VERSION,
    MAX_SCENARIOS_PER_INVOCATION,
    scenario_by_id,
    SCENARIO_CATALOG,
    ScenarioManifestIntegrityReason,
    verify_scenario_catalog,
)


def copied_definition(source, **overrides):
    arguments = {
        'scenario_id': source.scenario_id,
        'version': source.version,
        'category': source.category,
        'description': source.description,
        'launch_profile': source.launch_profile,
        'expected_safe_outcome': source.expected_safe_outcome,
        'authority': source.authority,
        'steps': source.steps,
        'assertions': source.assertions,
    }
    arguments.update(overrides)
    return DevelopmentScenarioDefinition(**arguments)


def catalog_replacing_first(replacement):
    return (replacement,) + SCENARIO_CATALOG[1:]


class ScenarioManifestModelTest(unittest.TestCase):
    def test_manifest_and_entries_are_immutable(self):
        manifest = build_scenario_manifest()
        with self.assertRaises(FrozenInstanceError):
            manifest.manifest_schema_version = '2.0.0'
        with self.assertRaises(FrozenInstanceError):
            manifest.entries[0].scenario_id = 'changed'

    def test_manifest_schema_and_framework_are_explicit(self):
        document = build_scenario_manifest().as_dict()
        self.assertEqual(
            'ayyo.developmental-scenarios.v1',
            document['framework_id'],
        )
        self.assertEqual('1.0.0', document['framework_version'])
        self.assertEqual(MANIFEST_SCHEMA_ID, document['manifest_schema_id'])
        self.assertEqual(
            MANIFEST_SCHEMA_VERSION,
            document['manifest_schema_version'],
        )
        self.assertEqual(6, document['scenario_count'])

    def test_manifest_order_matches_declared_catalog_order(self):
        manifest = build_scenario_manifest()
        self.assertEqual(
            tuple(item.scenario_id for item in SCENARIO_CATALOG),
            tuple(item.scenario_id for item in manifest.entries),
        )

    def test_entry_contains_exact_bounded_public_metadata(self):
        definition = scenario_by_id('development-only-neck-actuation')
        entry = DevelopmentScenarioManifestEntry(definition)
        self.assertEqual(
            {
                'authority',
                'category',
                'expected_safe_outcome',
                'launch_profile',
                'scenario_fingerprint',
                'scenario_id',
                'scenario_version',
            },
            set(entry.as_dict()),
        )
        self.assertEqual(definition.fingerprint, entry.scenario_fingerprint)

    def test_manifest_fingerprint_is_deterministic(self):
        self.assertEqual(
            build_scenario_manifest().manifest_fingerprint,
            build_scenario_manifest().manifest_fingerprint,
        )

    def test_identical_catalogs_produce_byte_identical_canonical_json(self):
        first = canonical_manifest_json(build_scenario_manifest()).encode('utf-8')
        second = canonical_manifest_json(build_scenario_manifest()).encode('utf-8')
        self.assertEqual(first, second)

    def test_semantic_catalog_change_changes_manifest_fingerprint(self):
        source = SCENARIO_CATALOG[0]
        changed = copied_definition(
            source,
            expected_safe_outcome='A deliberately changed semantic expectation.',
        )
        self.assertNotEqual(
            build_scenario_manifest().manifest_fingerprint,
            build_scenario_manifest(
                catalog_replacing_first(changed)
            ).manifest_fingerprint,
        )

    def test_pid_does_not_affect_manifest_identity(self):
        with mock.patch('os.getpid', return_value=11):
            first = build_scenario_manifest().manifest_fingerprint
        with mock.patch('os.getpid', return_value=99_999):
            second = build_scenario_manifest().manifest_fingerprint
        self.assertEqual(first, second)

    def test_hostname_does_not_affect_manifest_identity(self):
        with mock.patch('socket.gethostname', return_value='first-host'):
            first = build_scenario_manifest().manifest_fingerprint
        with mock.patch('socket.gethostname', return_value='second-host'):
            second = build_scenario_manifest().manifest_fingerprint
        self.assertEqual(first, second)

    def test_wall_clock_does_not_affect_manifest_identity(self):
        with mock.patch('time.time', return_value=1.0):
            first = build_scenario_manifest().manifest_fingerprint
        with mock.patch('time.time', return_value=9_999_999.0):
            second = build_scenario_manifest().manifest_fingerprint
        self.assertEqual(first, second)


class ScenarioManifestVerificationTest(unittest.TestCase):
    def test_published_catalog_verifies_successfully(self):
        result = verify_scenario_catalog()
        self.assertTrue(result.valid)
        self.assertEqual(6, result.scenario_count)
        self.assertEqual((), result.reasons)

    def test_scenario_ids_are_unique(self):
        scenario_ids = tuple(item.scenario_id for item in SCENARIO_CATALOG)
        self.assertEqual(len(scenario_ids), len(set(scenario_ids)))
        self.assertNotIn(
            ScenarioManifestIntegrityReason.DUPLICATE_SCENARIO_ID,
            verify_scenario_catalog().reasons,
        )

    def test_duplicate_scenario_id_fails_verification(self):
        catalog = (SCENARIO_CATALOG[0], SCENARIO_CATALOG[0]) + SCENARIO_CATALOG[2:]
        result = verify_scenario_catalog(catalog)
        self.assertFalse(result.valid)
        self.assertIn(
            ScenarioManifestIntegrityReason.DUPLICATE_SCENARIO_ID,
            result.reasons,
        )

    def test_reordered_catalog_fails_verification(self):
        catalog = (SCENARIO_CATALOG[1], SCENARIO_CATALOG[0]) + SCENARIO_CATALOG[2:]
        result = verify_scenario_catalog(catalog)
        self.assertIn(
            ScenarioManifestIntegrityReason.CATALOG_ORDER_INVALID,
            result.reasons,
        )

    def test_duplicate_step_id_fails_verification(self):
        changed = copied_definition(SCENARIO_CATALOG[0])
        object.__setattr__(changed, 'steps', (changed.steps[0], changed.steps[0]))
        result = verify_scenario_catalog(catalog_replacing_first(changed))
        self.assertIn(
            ScenarioManifestIntegrityReason.DUPLICATE_STEP_ID,
            result.reasons,
        )

    def test_duplicate_assertion_id_fails_verification(self):
        changed = copied_definition(SCENARIO_CATALOG[0])
        object.__setattr__(
            changed,
            'assertions',
            (changed.assertions[0], changed.assertions[0]),
        )
        result = verify_scenario_catalog(catalog_replacing_first(changed))
        self.assertIn(
            ScenarioManifestIntegrityReason.DUPLICATE_ASSERTION_ID,
            result.reasons,
        )

    def test_broken_scenario_fingerprint_fails_verification(self):
        changed = copied_definition(SCENARIO_CATALOG[0])
        object.__setattr__(changed, 'fingerprint', 'development-scenario-sha256-broken')
        result = verify_scenario_catalog(catalog_replacing_first(changed))
        self.assertIn(
            ScenarioManifestIntegrityReason.SCENARIO_FINGERPRINT_MISMATCH,
            result.reasons,
        )

    def test_catalog_overflow_fails_verification(self):
        catalog = tuple(
            SCENARIO_CATALOG[index % len(SCENARIO_CATALOG)]
            for index in range(MAX_SCENARIOS_PER_INVOCATION + 1)
        )
        result = verify_scenario_catalog(catalog)
        self.assertIn(
            ScenarioManifestIntegrityReason.CATALOG_SIZE_OUT_OF_BOUNDS,
            result.reasons,
        )

    def test_invalid_manifest_fingerprint_fails_verification(self):
        manifest = build_scenario_manifest()
        object.__setattr__(
            manifest,
            'manifest_fingerprint',
            'development-scenario-manifest-sha256-broken',
        )
        result = verify_scenario_catalog(manifest=manifest)
        self.assertIn(
            ScenarioManifestIntegrityReason.MANIFEST_FINGERPRINT_MISMATCH,
            result.reasons,
        )

    def test_all_scenario_versions_and_resources_verify(self):
        result = verify_scenario_catalog()
        self.assertNotIn(
            ScenarioManifestIntegrityReason.SCENARIO_VERSION_INVALID,
            result.reasons,
        )
        self.assertNotIn(
            ScenarioManifestIntegrityReason.RESOURCE_BOUND_EXCEEDED,
            result.reasons,
        )


if __name__ == '__main__':
    unittest.main()
