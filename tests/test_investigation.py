"""Independent contexts and evidence failure gates with synthetic model replies."""
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from aixsecurity.adapters.investigation import Investigator
from aixsecurity.adapters.model import ModelError


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append(deepcopy(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {'content': json.dumps(reply), 'model': 'synthetic-model'}


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'repo'
        self.root.mkdir()
        (self.root/'Demo.java').write_text('class Demo {\n void run() {}\n}\n')
        self.candidate = {'id': 'synthetic-case', 'path': 'Demo.java', 'start_line': 2,
            'rule_id': 'aix.java.sqli.taint', 'message': 'Synthetic candidate, not a real finding',
            'code_excerpt': 'void run() {}', 'dataflow_trace': None}
        self.snapshot = {'limitations': ['Synthetic test only'], 'repositories': [{
            'url': 'https://github.com/example/synthetic.git', 'commit': 'a'*40,
            'repo_path': str(self.root), 'candidates': [self.candidate],
            'source_manifest': {'Demo.java': hashlib.sha256((self.root/'Demo.java').read_bytes()).hexdigest()},
            'build': {'success': True}, 'tool_versions': {'semgrep': 'synthetic'}}]}

    def replies(self, first='confirmed', second='confirmed'):
        return [{'read_requests': [{'path': 'Demo.java', 'line': 2}]},
                {'verdict': first, 'reason': 'UNIQUE_INITIAL_ASSESSMENT'},
                {'verdict': second, 'reason': 'Independent synthetic assessment'}]

    def test_review_context_does_not_include_initial_assessment(self):
        client = FakeClient(self.replies())
        result = Investigator(client).run(self.snapshot)
        self.assertEqual(len(client.calls), 3)
        self.assertNotIn('UNIQUE_INITIAL_ASSESSMENT', json.dumps(client.calls[2]))
        first_evidence = json.loads(client.calls[1][1]['content'])['evidence']
        review_evidence = json.loads(client.calls[2][1]['content'])['evidence']
        self.assertEqual(first_evidence, review_evidence)
        self.assertEqual(result['findings'][0]['verification_method'], 'static_review')

    def test_no_dataflow_trace_cannot_be_confirmed_by_model_agreement(self):
        result = Investigator(FakeClient(self.replies())).run(self.snapshot)
        self.assertEqual(result['findings'][0]['status'], 'suspicious')
        self.assertEqual(result['summary']['confirmed'], 0)

    def test_model_error_at_any_stage_marks_unreviewed(self):
        for index in range(3):
            replies = self.replies(); replies[index] = ModelError('Synthetic unavailable model')
            with self.subTest(index=index):
                result = Investigator(FakeClient(replies)).run(self.snapshot)
                finding = result['findings'][0]
                self.assertEqual(finding['verification_method'], 'unreviewed')
                self.assertEqual(finding['status'], 'suspicious')
                self.assertEqual(result['summary']['reviewed'], 0)
                self.assertEqual(result['coverage'], 'partial')

    def test_model_requested_out_of_scope_path_is_not_read(self):
        client = FakeClient([{'read_requests': [{'path': '../outside.java', 'line': 1}]}])
        finding = Investigator(client).run(self.snapshot)['findings'][0]
        self.assertEqual(finding['verification_method'], 'unreviewed')
        self.assertEqual(finding['trace'], [])
        self.assertEqual(len(client.calls), 1)

    def test_read_rejects_traversal_and_symlink_and_non_java(self):
        outside = Path(self.temp.name)/'outside.java'; outside.write_text('private synthetic')
        (self.root/'Link.java').symlink_to(outside)
        reader = Investigator(FakeClient([]))
        for path in ('../outside.java', 'Link.java', '/etc/passwd', 'build.xml'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                reader._read(str(self.root), path, 1, 'b' * 64)

    def test_changed_source_is_unreviewed_not_bound_to_old_commit(self):
        (self.root/'Demo.java').write_text('class Changed {}')
        client = FakeClient(self.replies())
        result = Investigator(client).run(self.snapshot)
        self.assertEqual(result['findings'][0]['verification_method'], 'unreviewed')
        self.assertEqual(result['findings'][0]['status'], 'suspicious')
        self.assertEqual(len(client.calls), 1)

    def test_unvalidated_trace_cannot_promote_to_confirmed(self):
        self.candidate['dataflow_trace'] = {'unvalidated': 'synthetic trace'}
        result = Investigator(FakeClient(self.replies())).run(self.snapshot)
        self.assertEqual(result['findings'][0]['status'], 'suspicious')
        self.assertEqual(result['summary']['confirmed'], 0)

    def test_disagreement_remains_suspicious(self):
        result = Investigator(FakeClient(self.replies('rejected', 'confirmed'))).run(self.snapshot)
        self.assertEqual(result['findings'][0]['status'], 'suspicious')

    def test_budget_exhaustion_does_not_clear_remaining_candidates(self):
        result = Investigator(FakeClient([]), max_cases=0).run(self.snapshot)
        self.assertEqual(result['coverage'], 'partial')
        self.assertEqual(result['summary']['candidate_count'], 1)
        self.assertEqual(result['summary']['attempted'], 0)
        self.assertTrue(any('remaining candidates' in x for x in result['limitations']))

    def test_profile_filters_candidates_and_uses_specific_review_focus(self):
        command = deepcopy(self.candidate)
        command.update(id='command-case', category='command-injection', rule_id='aix.java.command-injection.taint')
        self.snapshot['repositories'][0]['candidates'].append(command)
        client = FakeClient(self.replies())
        result = Investigator(client).run(self.snapshot, profile_id='command-injection-intraprocedural-v1')
        self.assertEqual(result['summary']['candidate_count'], 1)
        self.assertEqual(result['findings'][0]['id'], 'command-case')
        self.assertIn('Runtime.exec is not automatically a shell', client.calls[2][0]['content'])
        self.assertNotIn('SQL identifiers', client.calls[2][0]['content'])
        self.assertEqual(result['profile_title'], '命令注入')

    def test_mismatched_rule_and_category_are_not_assessed(self):
        self.candidate['category'] = 'path-traversal'
        result = Investigator(FakeClient([])).run(self.snapshot)
        self.assertEqual(result['summary']['attempted'], 0)
