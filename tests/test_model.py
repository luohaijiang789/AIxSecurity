import io
import http.client
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from aixsecurity.adapters.model import LocalModelClient, ModelConfig, ModelError, load_config


class Stub:
    def __init__(self, responses): self.responses, self.requests = responses, []
    def open(self, request, **kwargs):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception): raise result
        return io.BytesIO(result if isinstance(result, bytes) else json.dumps(result).encode())


class ModelTests(unittest.TestCase):
    def config(self): return ModelConfig('http://localhost:3001/v1', 'auto', 'test-secret')

    def test_repr_has_no_key_and_url_is_local(self):
        self.assertNotIn('test-secret', repr(self.config()))
        for url in ['https://example.com/v1', 'http://localhost.evil/v1',
                    'http://user:pass@localhost/v1', 'http://localhost/v1?key=x']:
            with self.assertRaises(ModelError): ModelConfig(url, 'auto', 'test')

    def test_smoke_does_not_send_source_or_echo_extra_fields(self):
        stub = Stub([{'data': [{'id': 'auto'}]}, {'choices': [{'message': {'content': 'AIXSECURITY_OK'}}],
                    'usage': {'secret': 'test-secret'}, 'model': 'test-secret'}])
        result = LocalModelClient(self.config(), opener=stub).smoke_test()
        self.assertEqual(result['status'], 'ok')
        self.assertNotIn('test-secret', json.dumps(result))
        body = json.loads(stub.requests[1].data)
        self.assertEqual(body['messages'][0]['content'], 'Reply with exactly AIXSECURITY_OK.')
        self.assertEqual(body['max_tokens'], 32)
        self.assertFalse(body['stream'])

    def test_errors_are_redacted_and_never_retried(self):
        stub = Stub([urllib.error.HTTPError('test-secret', 401, 'test-secret', {}, io.BytesIO(b'test-secret'))])
        with self.assertRaises(ModelError) as ctx: LocalModelClient(self.config(), opener=stub).list_models()
        self.assertNotIn('test-secret', str(ctx.exception))
        self.assertEqual(len(stub.requests), 1)

    def test_protocol_size_and_missing_text(self):
        for result in [b'invalid', b'x'*1048577, {'error': 'test-secret'}, {'choices': []}]:
            with self.assertRaises(ModelError):
                LocalModelClient(self.config(), opener=Stub([result])).complete([{'role':'user','content':'hi'}])

    def test_unlisted_model_does_not_call_completion(self):
        stub = Stub([{'data': []}])
        with self.assertRaises(ModelError): LocalModelClient(self.config(), opener=stub).smoke_test()
        self.assertEqual(len(stub.requests), 1)

    def test_bad_reply_not_reported_as_success(self):
        stub = Stub([{'data':[{'id':'auto'}]}, {'choices':[{'message':{'content':'test-secret'}}]}])
        result = LocalModelClient(self.config(), opener=stub).smoke_test()
        self.assertEqual(result['status'], 'unexpected_reply')
        self.assertNotIn('test-secret', json.dumps(result))

    def test_config_permissions_and_environment_override(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'.env'
            p.write_text('AIXSECURITY_MODEL_BASE_URL=http://localhost:3001/v1\nAIXSECURITY_MODEL_NAME=auto\nAIXSECURITY_MODEL_API_KEY=test-secret\n')
            p.chmod(0o644)
            with self.assertRaises(ModelError): load_config(p, environ={})
            p.chmod(0o600)
            self.assertEqual(load_config(p, environ={'AIXSECURITY_MODEL_NAME':'chosen'}).model, 'chosen')

    def test_budget_and_messages_checked_before_request(self):
        client=LocalModelClient(self.config(), opener=Stub([]))
        for messages in [[], [{'role':'tool','content':'x'}], [{'role':'user','content':'x'*32769}]]:
            with self.assertRaises(ModelError): client.complete(messages)
        with self.assertRaises(ModelError): client.complete([{'role':'user','content':'x'}], max_tokens=0)

    def test_malformed_http_and_deep_json_are_sanitized(self):
        for reply in [http.client.BadStatusLine('test-secret'),
                      http.client.IncompleteRead(b'test-secret'), b'['*2000+b']'*2000]:
            with self.assertRaises(ModelError) as ctx:
                LocalModelClient(self.config(), opener=Stub([reply])).list_models()
            self.assertNotIn('test-secret', str(ctx.exception))

    def test_invalid_url_and_non_utf8_config_are_sanitized(self):
        with self.assertRaises(ModelError): ModelConfig('http://[test-secret/v1', 'auto', 'key')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'.env'; p.write_bytes(b'\xfftest-secret');p.chmod(0o600)
            with self.assertRaises(ModelError) as ctx: load_config(p,environ={})
            self.assertNotIn('test-secret',str(ctx.exception))
