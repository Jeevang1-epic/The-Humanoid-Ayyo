import ast
from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parents[2]


class ScenarioRosPackageTest(unittest.TestCase):
    def _profiles(self):
        source = (
            PACKAGE_ROOT / 'launch' / 'developmental_scenarios.launch.py'
        ).read_text(encoding='utf-8')
        tree = ast.parse(source)
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == '_PROFILES'
                for target in node.targets
            )
        )
        return ast.literal_eval(assignment.value)

    def test_fixed_launch_profiles_compose_existing_simulation(self):
        source = (PACKAGE_ROOT / 'launch' / 'developmental_scenarios.launch.py').read_text(
            encoding='utf-8'
        )
        self.assertIn('ayyo_simulation', source)
        self.assertEqual(
            {'development_control', 'observation', 'sensor_absence'},
            set(self._profiles()),
        )
        self.assertIn('headless', source)

    def test_development_service_is_enabled_only_in_development_profile(self):
        profiles = self._profiles().values()
        values = [profile['enable_development_control'] for profile in profiles]
        self.assertEqual(1, values.count('true'))
        self.assertEqual(2, values.count('false'))

    def test_visual_fixture_is_explicit_and_default_off_outside_observation(self):
        profiles = self._profiles().values()
        values = [
            profile['enable_anonymous_semantic_test_fixture']
            for profile in profiles
        ]
        self.assertEqual(1, values.count('true'))
        self.assertEqual(2, values.count('false'))

    def test_manual_rviz_is_optional_and_not_in_profile_identity(self):
        source = (PACKAGE_ROOT / 'launch' / 'developmental_scenarios.launch.py').read_text(
            encoding='utf-8'
        )
        self.assertIn('start_rviz', source)
        self.assertIn('default_value=', source)
        self.assertIn('condition=IfCondition(start_rviz)', source)

    def test_scenario_package_depends_downstream_only(self):
        manifest = (PACKAGE_ROOT / 'package.xml').read_text(encoding='utf-8')
        self.assertIn('<exec_depend>ayyo_simulation</exec_depend>', manifest)
        for forbidden in (
            'ayyo_perception',
            'ayyo_world_model',
            'ayyo_working_memory',
            'ayyo_safety',
            'ayyo_skill_manager',
            'ayyo_runtime_bridge',
        ):
            self.assertNotIn(f'<exec_depend>{forbidden}</exec_depend>', manifest)

    def test_no_production_package_depends_on_scenarios(self):
        offenders = []
        for manifest in (REPOSITORY_ROOT / 'ros2_ws' / 'src').glob('*/package.xml'):
            if manifest.parent.name == 'ayyo_scenarios':
                continue
            if 'ayyo_scenarios' in manifest.read_text(encoding='utf-8'):
                offenders.append(manifest.parent.name)
        self.assertEqual([], offenders)

    def test_launch_and_scripts_have_no_shell_execution_surface(self):
        text = '\n'.join(
            path.read_text(encoding='utf-8')
            for directory in ('launch', 'scripts')
            for path in (PACKAGE_ROOT / directory).glob('*.py')
        )
        self.assertNotIn('subprocess', text)
        self.assertNotIn('shell=True', text)
        self.assertNotIn('eval(', text)
        self.assertNotIn('exec(', text)
        self.assertNotIn('--topic', text)
        self.assertNotIn('--service', text)


if __name__ == '__main__':
    unittest.main()
