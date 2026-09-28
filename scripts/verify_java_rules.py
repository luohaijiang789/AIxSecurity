#!/usr/bin/env python3
"""Opt-in real Semgrep acceptance; no target code or network is executed."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--semgrep', required=True, help='Installed Semgrep executable')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fixtures = root/'tests/fixtures/java_scan_profiles'
    expected, forbidden = set(), set()
    for path in fixtures.glob('*.java'):
        lines = path.read_text().splitlines()
        for index, line in enumerate(lines):
            marker = re.search(r'// (ruleid|ok): (aix\.java\.[a-z-]+\.taint)', line)
            if marker:
                target = index + 1
                while target < len(lines) and not lines[target].strip():
                    target += 1
                key = (path.name, target + 1, marker[2])
                (expected if marker[1] == 'ruleid' else forbidden).add(key)
    if not expected or not forbidden:
        raise SystemExit('Rule fixture annotations missing')
    with tempfile.TemporaryDirectory(prefix='aix-java-rules-') as temp:
        # Default Semgrep exclusions include directories named tests. Stage the
        # exact fixture bytes under targets so acceptance actually analyzes them.
        targets = Path(temp) / 'targets'
        shutil.copytree(fixtures, targets)
        env = dict(os.environ, HOME=temp, SEMGREP_SEND_METRICS='off', SEMGREP_ENABLE_VERSION_CHECK='0')
        env.pop('SEMGREP_APP_TOKEN', None)
        if Path('/etc/ssl/cert.pem').is_file():
            env['SSL_CERT_FILE'] = '/etc/ssl/cert.pem'
        result = subprocess.run([args.semgrep, 'scan', '--config', str(root/'src/aixsecurity/rules/java.json'),
                                 '--json', '--metrics=off', '--disable-version-check', '--no-git-ignore',
                                 str(targets)], env=env, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise SystemExit(f'SEMGREP_FAILED exit={result.returncode}\n{result.stderr}')
        report = json.loads(result.stdout)
        if report.get('errors'):
            raise SystemExit('SEMGREP_ERRORS ' + json.dumps(report['errors']))
        actual = set()
        for finding in report['results']:
            rule = finding['check_id']
            if '.taint' not in rule:
                continue
            rule = rule[rule.rfind('aix.java.'):]
            actual.add((Path(finding['path']).name, finding['start']['line'], rule))
        missing, unexpected = expected-actual, actual-expected
        false_positives = actual & forbidden
        if missing or unexpected or false_positives:
            raise SystemExit(f'RULE_ACCEPTANCE_FAILED missing={sorted(missing)} '
                             f'unexpected={sorted(unexpected)} forbidden_hits={sorted(false_positives)}')
        print(f'JAVA_RULES_OK positive={len(expected)} negative={len(forbidden)} findings={len(actual)}')
        for category in ('sqli','command-injection','path-traversal'):
            count = sum(item[2] == f'aix.java.{category}.taint' for item in actual)
            print(f'{category}: expected positives matched={count}')


if __name__ == '__main__':
    main()
