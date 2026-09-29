"""Shutdown acknowledgement, backup failures, and process exit are real IPC gates."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from taller.errors import AppError
from taller.stdio import serve


def test_shutdown_ack_exits_and_runs_backup_once(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("taller.app.App.shutdown", lambda self: calls.append("backup") or {"ok": True})
    target = io.StringIO()
    serve(tmp_path, io.BytesIO(b'{"id":1,"action":"app.shutdown"}\n{"id":2,"action":"bootstrap"}\n'), target, background=False)
    rows = [json.loads(line) for line in target.getvalue().splitlines()]
    assert len(rows) == 1 and rows[0]["ok"] and rows[0]["id"] == 1
    assert calls == ["backup"]


def test_failed_backup_keeps_ipc_available_for_recovery(tmp_path, monkeypatch):
    calls = []

    def fail_then_recover(self):
        calls.append("backup")
        if len(calls) == 1:
            raise AppError("Disco de copias no disponible")
        return {"ok": True}

    monkeypatch.setattr("taller.app.App.shutdown", fail_then_recover)
    target = io.StringIO()
    serve(tmp_path, io.BytesIO(b'{"id":1,"action":"app.shutdown"}\n{"id":2,"action":"bootstrap"}\n{"id":3,"action":"app.shutdown"}\n'), target, background=False)
    rows = [json.loads(line) for line in target.getvalue().splitlines()]
    assert not rows[0]["ok"] and "Disco" in rows[0]["error"]["message"]
    assert rows[1]["ok"] and rows[2]["ok"]
    assert calls == ["backup", "backup"]


def test_shutdown_exits_without_waiting_for_stdin_eof(tmp_path):
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "taller.stdio", "--data", str(tmp_path), "--no-background"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "PYTHONPATH": str(root / "backend")},
    )
    try:
        process.stdin.write('{"id":1,"action":"app.shutdown"}\n')
        process.stdin.flush()
        # wait() while stdin is still open demonstrates the explicit shutdown path.
        assert process.wait(timeout=20) == 0
        response = json.loads(process.stdout.readline())
        assert response["id"] == 1 and response["ok"]
        assert process.stdout.read() == ""
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
