"""Loopback development runner. Desktop production uses stdio, not an HTTP port."""
import argparse
import hmac
import json
import logging
import secrets
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote
from .app import App
from .errors import AppError


def run(root,web_root,port=8765,open_browser=False):
    app=App(root);token=secrets.token_urlsafe(32)
    web_root=Path(web_root).resolve()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass  # Never log request bodies or private data.
        def common(self,status=200,mime='application/json'):
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Cross-Origin-Resource-Policy','same-origin')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-src blob:; object-src blob:; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.valid_host() or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.common(403);self.wfile.write(b'{}');return
            path=unquote(urlparse(self.path).path)
            if path=='/runtime.js':
                self.common(mime='text/javascript; charset=utf-8')
                self.wfile.write(('window.__CANAMO_DEV_TOKEN__='+json.dumps(token)+';').encode());return
            if path=='/':path='/index.html'
            target=(web_root/path.lstrip('/')).resolve()
            if not target.is_relative_to(web_root) or not target.is_file():
                self.common(404);self.wfile.write(b'{}');return
            mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}.get(target.suffix,'application/octet-stream')
            self.common(mime=mime);self.wfile.write(target.read_bytes())
        def do_POST(self):
            origin=self.headers.get('Origin','')
            good_origins=(f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
            if not self.valid_host() or (origin and origin not in good_origins) or not hmac.compare_digest(self.headers.get('X-Canamo-Token',''),token):
                self.common(403);self.wfile.write(b'{"ok":false,"error":{"message":"Acceso denegado"}}');return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if self.path!='/api' or not 0<length<=300_000_000:raise AppError('Solicitud no admitida.')
                payload=json.loads(self.rfile.read(length))
                value=app.dispatch(payload.get('action'),payload.get('params',{}))
                output={'ok':True,'result':value}
            except AppError as error:
                output={'ok':False,'error':{'message':str(error),'code':error.code,'details':error.details}}
            except Exception:
                logging.exception('Error interno del servicio local')
                output={'ok':False,'error':{'message':'No se ha podido completar la operacion. No vuelvas a emitir sin revisar el listado.','code':'internal'}}
            self.common();self.wfile.write(json.dumps(output,ensure_ascii=False).encode())
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    url=f'http://127.0.0.1:{server.server_port}'
    print(url,flush=True)
    stop=threading.Event()
    def background():
        while not stop.wait(30):
            try:app.tick()
            except Exception:logging.exception('Error del trabajo periodico')
    threading.Thread(target=background,daemon=True).start()
    if open_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        stop.set();server.server_close()
        try:app.shutdown()
        except Exception:logging.exception('Copia de cierre no completada')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',default=str(Path.home()/'.canamo-pruebas'))
    parser.add_argument('--web',default=str(Path(__file__).resolve().parents[2]/'web'))
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args();run(args.data,args.web,args.port,args.open)
