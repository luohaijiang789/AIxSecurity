import json
import subprocess
import unittest
from types import SimpleNamespace
from aixsecurity.doctor import inspect_environment


class DoctorTests(unittest.TestCase):
    def test_missing_tools_and_model_do_not_pass_gate(self):
        result = inspect_environment(which=lambda _: None, environ={})
        self.assertIn('codeql', result['blockers'])
        self.assertEqual(result['g0_status'], 'not_passed')

    def test_secrets_and_command_output_are_not_returned(self):
        env = {key: 'SECRET-VALUE' for key in
               ('AIXSECURITY_MODEL_BASE_URL', 'AIXSECURITY_MODEL_NAME', 'AIXSECURITY_MODEL_API_KEY')}
        result = inspect_environment(which=lambda n: '/bin/'+n,
            runner=lambda *a, **kw: SimpleNamespace(returncode=0, stdout='SECRET-VALUE'), environ=env)
        self.assertNotIn('SECRET-VALUE', json.dumps(result))
        self.assertEqual(result['blockers'], [])
        self.assertEqual(result['checks']['model']['connectivity'], 'not_tested')
        self.assertEqual(result['g0_status'], 'not_passed')

    def test_timeout_is_bounded_and_recorded(self):
        def timeout(*args, **kwargs):
            self.assertEqual(kwargs['timeout'], 15)
            raise subprocess.TimeoutExpired(args[0], 15)
        result = inspect_environment(which=lambda n: n, runner=timeout, environ={})
        self.assertEqual(result['checks']['docker']['status'], 'timeout')

    def test_daemon_failure_is_not_available(self):
        result = inspect_environment(which=lambda n: n,
            runner=lambda *a, **kw: SimpleNamespace(returncode=1), environ={})
        self.assertEqual(result['checks']['docker']['status'], 'unavailable')

    def test_explicit_model_deferral_is_not_a_missing_config_blocker(self):
        result = inspect_environment(which=lambda _: None, environ={}, defer_model=True)
        self.assertNotIn('model_configuration', result['blockers'])
        self.assertEqual(result['checks']['model']['status'], 'deferred_by_user')
        self.assertEqual(result['deferred_gates'], ['model_connectivity'])
        self.assertEqual(result['g0_status'], 'not_passed')
