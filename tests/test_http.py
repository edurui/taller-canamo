"""Loopback HTTP contract tests; not browser/visual end-to-end tests."""
import json
import os
import selectors
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
import pytest

@pytest.fixture
def server(tmp_path):
    root=Path(__file__).resolve().parents[1]
    web=tmp_path/"web";web.mkdir();(web/"index.html").write_text("<!doctype html><title>fixture</title>")
    process=subprocess.Popen([sys.executable,"-u","-m","taller.server","--port","0","--data",str(tmp_path/"data"),"--web",str(web)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,"PYTHONPATH":str(root/"backend")})
    try:
        # This bounded startup poll is portable to Windows (select does not support Windows pipes).
        import threading,queue
        lines=queue.Queue()
        threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True).start()
        url=lines.get(timeout=15).strip()
        assert url.startswith("http://127.0.0.1:")
        with urllib.request.urlopen(url+"/runtime.js",timeout=5) as response:
            runtime=response.read().decode()
        token=json.loads(runtime.split("=",1)[1].rstrip(";"))
        yield url,token
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def request(url,token=None,origin=None,body=None):
    headers={"Content-Type":"application/json"}
    if token is not None:headers["X-Canamo-Token"]=token
    if origin is not None:headers["Origin"]=origin
    return urllib.request.Request(url+"/api",data=json.dumps(body or {"action":"bootstrap"}).encode(),headers=headers)

def test_authenticated_api(server):
    url,token=server
    with urllib.request.urlopen(request(url,token),timeout=5) as r:
        result=json.load(r)
        assert result["ok"] and not result["result"]["production_released"]

@pytest.mark.parametrize("token",[None,"wrong"])
def test_missing_or_wrong_token_denied(server,token):
    with pytest.raises(urllib.error.HTTPError) as exc:urllib.request.urlopen(request(server[0],token),timeout=5)
    assert exc.value.code==403

def test_cross_origin_denied(server):
    with pytest.raises(urllib.error.HTTPError) as exc:urllib.request.urlopen(request(server[0],server[1],"https://attacker.invalid"),timeout=5)
    assert exc.value.code==403

def test_static_headers_and_path_boundary(server):
    url,_=server
    with urllib.request.urlopen(url,timeout=5) as r:
        assert r.headers["X-Content-Type-Options"]=="nosniff"
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    with pytest.raises(urllib.error.HTTPError) as exc:urllib.request.urlopen(url+"/%2e%2e/secret",timeout=5)
    assert exc.value.code==404
