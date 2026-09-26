"""Bounded local prerequisite checks; never reads or prints secret values."""
import os
import shutil
import subprocess

COMMANDS = {
    'git': ['--version'], 'java': ['-version'], 'javac': ['-version'],
    'mvn': ['-version'], 'codeql': ['version', '--format=json'],
    'docker': ['info', '--format', '{{.ServerVersion}}'],
}


def inspect_environment(*, which=shutil.which, runner=subprocess.run, environ=None, defer_model=False):
    environ = os.environ if environ is None else environ
    checks = {}
    for name, args in COMMANDS.items():
        executable = which(name)
        if not executable:
            checks[name] = {'status': 'missing'}
            continue
        try:
            # Output can contain local configuration or credentials; do not echo it.
            result = runner([executable, *args], capture_output=True, timeout=15,
                            check=False)
            checks[name] = {'status': 'available' if result.returncode == 0 else 'unavailable',
                            'exit_code': result.returncode}
        except subprocess.TimeoutExpired:
            checks[name] = {'status': 'timeout'}
        except OSError:
            checks[name] = {'status': 'unavailable'}
    expected = ('AIXSECURITY_MODEL_BASE_URL', 'AIXSECURITY_MODEL_NAME', 'AIXSECURITY_MODEL_API_KEY')
    checks['model'] = {'status': 'configured_unverified' if all(environ.get(k) for k in expected)
                       else 'not_configured_in_environment',
                       'connectivity': 'not_tested'}
    blockers = [name for name in COMMANDS if checks[name]['status'] != 'available']
    if defer_model:
        checks['model'] = {'status': 'deferred_by_user', 'connectivity': 'not_tested'}
    if not defer_model and checks['model']['status'] != 'configured_unverified':
        blockers.append('model_configuration')
    return {'schema_version': 1, 'checks': checks, 'blockers': blockers,
            'g0_status': 'not_passed',
            'deferred_gates': ['model_connectivity'] if defer_model else [],
            'remaining_gates': ['fixed_target_commit', 'isolated_build_test',
                                'real_program_query', 'model_connectivity'],
            'note': 'Tool presence is not isolation, framework coverage, or audit validation.'}
