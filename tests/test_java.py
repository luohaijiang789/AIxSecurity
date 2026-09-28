import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aixsecurity.adapters.java import JavaPreparer, PreparationError, _MAVEN_RETRY_SCRIPT


class JavaTests(unittest.TestCase):
    def test_maven_retry_keeps_same_cache_and_stops_after_success(self):
        self._exercise_maven_retry(failures=1, expected_calls=2, expected_code=0)

    def test_maven_retry_is_bounded_and_preserves_failure(self):
        self._exercise_maven_retry(failures=9, expected_calls=2, expected_code=7)

    def test_maven_success_does_not_retry(self):
        self._exercise_maven_retry(failures=0, expected_calls=1, expected_code=0)

    def _exercise_maven_retry(self, failures, expected_calls, expected_code):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / 'mvn'
            executable.write_text("#!/bin/sh\nn=0; [ ! -f count ] || n=$(cat count)\n"
                                  "n=$((n+1)); echo $n > count\n"
                                  "echo \"$*\" >> arguments\n"
                                  "[ $n -gt \"$FAILURES\" ] || exit 7\nexit 0\n")
            executable.chmod(0o700)
            (root/'sleep').write_text('#!/bin/sh\necho "$*" >> sleeps\nexit 0\n')
            (root/'sleep').chmod(0o700)
            result = subprocess.run(['sh', '-c', _MAVEN_RETRY_SCRIPT], cwd=root,
                                    env=dict(os.environ, PATH=f'{root}:/usr/bin:/bin',
                                             FAILURES=str(failures)),
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, expected_code)
            self.assertEqual(int((root/'count').read_text()), expected_calls)
            sleeps = (root/'sleeps').read_text().splitlines() if (root/'sleeps').exists() else []
            self.assertEqual(sleeps, ['2'] if expected_calls == 2 else [])
            self.assertIn(f'AIX_MAVEN_COMPILE_ATTEMPT={expected_calls}/2', result.stdout)
            arguments = (root/'arguments').read_text()
            self.assertIn('-Daether.transport.http.retryHandler.count=2', arguments)
            self.assertNotIn('insecure', arguments)
            self.assertNotIn('allowall', arguments)

    def test_dependency_cache_is_stable_and_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            first = JavaPreparer('semgrep', cache_scope=Path(temp)/'workspace-a')
            name = first._cache_volume('https://github.com/org/repo', 'a'*40)
            self.assertEqual(name, first._cache_volume('https://github.com/org/repo', 'a'*40))
            self.assertNotEqual(name, first._cache_volume('https://github.com/org/other', 'a'*40))
            self.assertNotEqual(name, first._cache_volume('https://github.com/org/repo', 'b'*40))
            other = JavaPreparer('semgrep', cache_scope=Path(temp)/'workspace-b')
            self.assertNotEqual(name, other._cache_volume('https://github.com/org/repo', 'a'*40))
            other_image = JavaPreparer('semgrep', image='maven:other',
                                      cache_scope=Path(temp)/'workspace-a')
            self.assertNotEqual(name, other_image._cache_volume('https://github.com/org/repo', 'a'*40))
            self.assertRegex(name, r'^aixsecurity-m2-[0-9a-f]{40}$')

    def test_rejects_nonpublic_github_without_subprocess(self):
        for url in ['file:///tmp/repo','https://localhost/a/b','https://github.com@evil.test/a/b',
                    'https://github.com/a/b?token=x','https://github.com/a/b#x','https://github.com/a/b/../x']:
            with self.subTest(url=url), patch('aixsecurity.adapters.java.subprocess.run') as run:
                with self.assertRaises(PreparationError):
                    JavaPreparer('semgrep').prepare(url, '/tmp/aix-rejected')
                run.assert_not_called()

    def test_taint_result_and_assets_keep_exact_location_not_fabricated_trace(self):
        with tempfile.TemporaryDirectory() as temp:
            repo=Path(temp)
            (repo/'Test.java').write_text('class Test {\nvoid bad() {}\n}\n')
            base={'path':str(repo/'Test.java'),'start':{'line':2},'end':{'line':2},'extra':{}}
            report={'results':[dict(base,check_id='aix.java.sqli.taint'),
                               dict(base,check_id='aix.java.asset.source')]}
            assets,candidates=JavaPreparer._extract(report,repo,'https://github.com/org/repo','a'*40)
            self.assertEqual(assets[0]['kind'],'source')
            self.assertEqual(candidates[0]['path'],'Test.java')
            self.assertEqual(candidates[0]['start_line'],2)
            self.assertIsNone(candidates[0]['dataflow_trace'])
            self.assertIsNone(candidates[0]['source'])
            self.assertEqual(candidates[0]['evidence']['mode'],'taint')

    def test_outside_repository_result_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            result={'path':'/etc/passwd','start':{'line':1},'end':{'line':1},'check_id':'aix.java.sqli.taint'}
            with self.assertRaises(PreparationError):
                JavaPreparer._extract({'results':[result]},Path(temp),'https://github.com/org/repo','a'*40)

    def test_coverage_rejects_zero_java_and_zero_java_scanned(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            with self.assertRaisesRegex(PreparationError, 'no Java source'):
                JavaPreparer._coverage({'errors': [], 'paths': {'scanned': []}}, repo, {})
            for scanned in ([], ['README.md']):
                with self.subTest(scanned=scanned), self.assertRaisesRegex(PreparationError, 'scanned no Java'):
                    JavaPreparer._coverage({'errors': [], 'paths': {'scanned': scanned}}, repo,
                                          {'Test.java': 'digest'})

    def test_coverage_reports_unscanned_java_and_large_files(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            for name, size in [('Test.java', 20), ('Ignored.java', 20), ('Large.java', 1000001)]:
                (repo/name).write_text('a'*size)
            manifest = {name: 'digest' for name in ['Test.java','Ignored.java','Large.java']}
            metrics = JavaPreparer._coverage({'paths': {'scanned': [str(repo/'Test.java'),
                                                                 str(repo/'Test.java')]}}, repo, manifest)
            self.assertEqual(metrics['scanned_java_files'], 1)
            self.assertEqual(metrics['source_files'], 3)
            self.assertEqual(metrics['unscanned_java_files'], 2)
            self.assertEqual(metrics['unscanned_java_paths'], ['Ignored.java','Large.java'])
            self.assertEqual(metrics['unscanned_large_java_paths'], ['Large.java'])

    def test_candidate_identity_is_repository_and_revision_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo/'Test.java').write_text('class Test {}')
            report = {'results': [{'path': str(repo/'Test.java'), 'start': {'line': 1},
                                  'end': {'line': 1}, 'check_id': 'aix.java.sqli.taint'}]}
            results = [JavaPreparer._extract(report, repo, url, commit)[1][0]
                       for url, commit in [('https://github.com/org/a','a'*40),
                                           ('https://github.com/org/b','a'*40),
                                           ('https://github.com/org/a','b'*40)]]
            self.assertEqual(len({r['id'] for r in results}), 3)
            self.assertEqual(results[0]['repository_url'], 'https://github.com/org/a')
            self.assertEqual(results[0]['commit'], 'a'*40)

    def test_rules_are_real_java_taint_and_assets(self):
        rules=json.loads((Path(__file__).parents[1]/'src/aixsecurity/rules/java.json').read_text())['rules']
        taint=next(r for r in rules if r['id']=='aix.java.sqli.taint')
        self.assertEqual(taint['mode'],'taint')
        self.assertTrue(taint['pattern-sources'])
        self.assertTrue(taint['pattern-sinks'])
        self.assertNotIn('pattern-regex',json.dumps(rules))

    def test_all_supported_categories_are_extracted_and_unknown_rules_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo/'Test.java').write_text('class Test {}')
            base = {'path': str(repo/'Test.java'), 'start': {'line': 1}, 'end': {'line': 1}}
            categories = ('sqli', 'command-injection', 'path-traversal')
            report = {'results': [dict(base, check_id=f'prefix.aix.java.{category}.taint')
                                  for category in (*categories, 'unknown')]}
            assets, candidates = JavaPreparer._extract(report, repo, 'https://github.com/org/repo', 'a'*40)
            self.assertEqual(assets, [])
            self.assertEqual([c['category'] for c in candidates], list(categories))
            self.assertEqual(len({c['id'] for c in candidates}), 3)
            self.assertTrue(all(c['evidence']['mode'] == 'taint' for c in candidates))
            self.assertTrue(all(c['source'] is None for c in candidates))

    def test_new_rules_focus_commands_and_file_paths(self):
        rules = json.loads((Path(__file__).parents[1]/'src/aixsecurity/rules/java.json').read_text())['rules']
        for category, focus in [('command-injection', '$COMMAND'), ('path-traversal', '$PATH')]:
            rule = next(r for r in rules if r['id'] == f'aix.java.{category}.taint')
            self.assertEqual(rule['mode'], 'taint')
            self.assertTrue(rule['pattern-sources'])
            self.assertEqual(rule['pattern-sinks'][0]['patterns'][-1]['focus-metavariable'], focus)
            self.assertNotIn('pattern-regex', json.dumps(rule))
            self.assertNotIn('pattern-sanitizers', rule)

    def test_failed_build_never_runs_analyzer(self):
        with tempfile.TemporaryDirectory() as temp:
            calls=[]
            def fake_run(args,**kwargs):
                calls.append(args)
                stage=Path(kwargs['log']).stem
                if stage=='clone':
                    repo=Path(temp)/'repository';repo.mkdir();(repo/'pom.xml').write_text('<project/>')
                if stage=='commit':return 'a'*40
                if stage=='build':raise PreparationError('build failed')
                return ''
            p=JavaPreparer('semgrep')
            with patch.object(p,'_run',side_effect=fake_run),patch('aixsecurity.adapters.java.subprocess.run'):
                with self.assertRaisesRegex(PreparationError,'build failed'):
                    p.prepare('https://github.com/org/repo',temp)
            self.assertEqual(len(calls),3)
            docker=calls[-1]
            self.assertIn('--read-only',docker)
            self.assertIn('--cap-drop=ALL',docker)
            self.assertIn('--pids-limit=256',docker)
            self.assertNotIn('/var/run/docker.sock',' '.join(docker))
            self.assertTrue(any(arg.startswith('type=volume,src=aixsecurity-m2-')
                                and arg.endswith('dst=/root/.m2/repository') for arg in docker))
            self.assertNotIn(str(Path.home()/'.m2'), ' '.join(docker))


if __name__=='__main__':
    unittest.main()
