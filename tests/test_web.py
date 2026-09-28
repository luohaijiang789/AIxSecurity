import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from aixsecurity.entrypoints.web import make_server


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        try:self.server=make_server(Path(self.tmp.name)/'platform.db',port=0)
        except PermissionError:self.skipTest('Loopback sockets require sandbox permission')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)

    def call(self,path,body=None,headers=None):
        request=urllib.request.Request(self.base+path, data=None if body is None else json.dumps(body).encode(),headers=headers or {})
        try:
            with self.opener.open(request,timeout=5) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:
            data=e.read();e.close();return e.code,data

    def test_static_and_no_filesystem_escape(self):
        code,data=self.call('/');self.assertEqual(code,200);self.assertIn('资产中心'.encode(),data)
        self.assertEqual(self.call('/../../.env')[0],404)
        self.assertEqual(self.call('/api/projects',headers={'Host':'evil.invalid'})[0],403)

    def test_register_and_ready_gate(self):
        headers={'Content-Type':'application/json','X-AIxSecurity-Request':'1'}
        body={'name':'Fixture','repositories':['https://github.com/example/fixture.git'],'idempotency_key':'x'}
        self.assertEqual(self.call('/api/projects',body)[0],403)
        self.assertEqual(self.call('/api/projects',body,dict(headers,Origin='https://evil.invalid'))[0],403)
        code,data=self.call('/api/projects',body,headers);self.assertEqual(code,201)
        project=json.loads(data)
        self.assertEqual(project['preparation_status'],'queued')
        code,_=self.call('/api/scans',{'project_id':project['id'],'idempotency_key':'scan'},headers)
        self.assertEqual(code,400)
        self.assertEqual(json.loads(self.call('/api/scans')[1])['scans'],[])
        self.assertEqual(json.loads(self.call('/api/projects',body,headers)[1])['id'],project['id'])

    def test_retry_missing_project_has_controlled_error(self):
        headers={'Content-Type':'application/json','X-AIxSecurity-Request':'1'}
        self.assertEqual(self.call('/api/projects/missing/retry',{'idempotency_key':'retry'},headers)[0],400)


    def test_profiles_are_real_catalog_and_unknown_profile_rejected(self):
        status, body = self.call('/api/profiles')
        self.assertEqual(status, 200)
        profiles = json.loads(body)['profiles']
        self.assertEqual(len(profiles), 3)
        self.assertEqual({p['category'] for p in profiles}, {'sqli','command-injection','path-traversal'})
        headers={'Content-Type':'application/json','X-AIxSecurity-Request':'1'}
        status,_ = self.call('/api/scans', {'project_id':'missing','idempotency_key':'x','profile_id':'fake'}, headers)
        self.assertEqual(status, 400)
        self.assertEqual(self.call('/api/projects/missing/prepare', {'idempotency_key':'refresh'}, headers)[0],400)
