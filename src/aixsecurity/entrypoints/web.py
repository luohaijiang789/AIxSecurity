"""Loopback-only single-user UI/API. No directory listing or arbitrary file access."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from ..application.reporting import render_markdown
from ..composition import build_platform, build_worker

STATIC = Path(__file__).parent/'static'


def make_server(database, *, port=8765):
    with_service = build_platform(database)
    with_service.platform.close()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *args): pass

        def send(self,status,body,content_type='application/json; charset=utf-8'):
            data=json.dumps(body,ensure_ascii=False).encode() if isinstance(body,(dict,list)) else body
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(data)

        def permitted(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.permitted(): return self.send(403,{'error':'Invalid local host'})
            path=urlsplit(self.path).path
            if path=='/favicon.ico':return self.send(204,b'','image/x-icon')
            if path in ('/','/static/app.js','/static/style.css'):
                name={'/':'index.html','/static/app.js':'app.js','/static/style.css':'style.css'}[path]
                content_type={'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]
                return self.send(200,(STATIC/name).read_bytes(),content_type)
            service=build_platform(database)
            try:
                if path=='/api/profiles': result={'profiles':service.profiles()}
                elif path=='/api/projects': result={'projects':service.platform.list_projects()}
                elif path.startswith('/api/projects/'): result=service.platform.get_project(path.rsplit('/',1)[-1])
                elif path=='/api/scans': result={'scans':service.platform.list_scans()}
                elif path.startswith('/api/scans/') and path.endswith('/report.md'):
                    scan=service.platform.get_scan(path.split('/')[3])
                    if scan['report'] is None:return self.send(404,{'error':'Report is not ready'})
                    return self.send(200,render_markdown(scan['report']).encode(),'text/markdown; charset=utf-8')
                elif path.startswith('/api/scans/'): result=service.platform.get_scan(path.rsplit('/',1)[-1])
                else:return self.send(404,{'error':'Not found'})
                self.send(200,result)
            except ValueError: self.send(404,{'error':'Resource not found'})
            except Exception: self.send(500,{'error':'Local storage operation failed'})
            finally:service.platform.close()

        def do_POST(self):
            if not self.permitted() or self.headers.get('X-AIxSecurity-Request')!='1':
                return self.send(403,{'error':'Same-origin request header required'})
            origin=self.headers.get('Origin')
            if origin is not None and origin != 'http://'+self.headers.get('Host',''):
                return self.send(403,{'error':'Cross-origin mutation refused'})
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                return self.send(415,{'error':'JSON required'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=65536:raise ValueError()
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict):raise ValueError()
            except (ValueError,UnicodeError,RecursionError):return self.send(400,{'error':'Invalid JSON request'})
            service=build_platform(database)
            try:
                path=urlsplit(self.path).path
                if path=='/api/projects': result=service.register(body)
                elif path=='/api/scans': result=service.create_scan(body)
                elif path.startswith('/api/projects/') and path.endswith('/prepare'):
                    result=service.platform.retry_preparation(path.split('/')[3],body['idempotency_key'],refresh=True)
                elif path.startswith('/api/projects/') and path.endswith('/retry'):
                    result=service.platform.retry_preparation(path.split('/')[3],body['idempotency_key'])
                else:return self.send(404,{'error':'Not found'})
                self.send(201,result)
            except (ValueError,KeyError,TypeError) as exc:
                self.send(400,{'error':str(exc)[:200] if isinstance(exc,ValueError) else 'Missing or invalid fields'})
            except Exception:self.send(500,{'error':'Local storage operation failed'})
            finally:service.platform.close()

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(database,workdir,semgrep_path,env_file,*,port=8765,max_cases=3):
    server=make_server(database,port=port)
    try:
        worker=build_worker(database,workdir,semgrep_path,env_file,max_cases)
    except Exception:
        server.server_close();raise
    thread=threading.Thread(target=worker.run,name='aixsecurity-worker',daemon=True)
    thread.start()
    print(f'AIxSecurity UI: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        worker.stop_event.set();server.server_close();thread.join(timeout=2)
