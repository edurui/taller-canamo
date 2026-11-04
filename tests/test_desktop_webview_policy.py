"""Policy lifetime tests only; native WebView2 acceptance still requires Windows."""

from contextlib import nullcontext
import ctypes
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def desktop():
    path = Path(__file__).resolve().parents[1] / "src-tauri/tests/desktop_smoke.py"
    spec = importlib.util.spec_from_file_location("desktop_policy_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("original", [None, ("previous options", 1)])
@pytest.mark.parametrize("fail", [False, True])
def test_ci_policy_is_app_specific_and_restored(desktop, tmp_path, monkeypatch, original, fail):
    name = "taller-canamo.exe"
    values = {"other.exe": ("untouched", 1)}
    if original is not None:
        values[name] = original
    before = values.copy()
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: 1)),
        raising=False,
    )

    def create(root, path, reserved, access):
        assert root == "HKLM" and path.endswith(r"WebView2\AdditionalBrowserArguments")
        assert access == 7
        return nullcontext(values)

    def query(key, name):
        if name not in key:
            raise FileNotFoundError(name)
        return key[name]

    registry = SimpleNamespace(
        HKEY_LOCAL_MACHINE="HKLM",
        KEY_QUERY_VALUE=1,
        KEY_SET_VALUE=2,
        KEY_WOW64_64KEY=4,
        REG_SZ=1,
        CreateKeyEx=create,
        QueryValueEx=query,
        SetValueEx=lambda key, name, reserved, kind, data: key.update({name: (data, kind)}),
        DeleteValue=lambda key, name: key.pop(name),
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)

    def run():
        with desktop.ci_webview_debugging(Path(name), 12345, tmp_path):
            assert values[name] == ("--remote-debugging-port=12345", 1)
            assert values["other.exe"] == before["other.exe"]
            if fail:
                raise RuntimeError("synthetic WebView2 failure")

    if fail:
        with pytest.raises(RuntimeError, match="synthetic"):
            run()
    else:
        run()
    assert values == before
    proof = json.loads((tmp_path / "webview-debug-policy.json").read_text())
    assert proof["restored"] and proof["elevated"]
    assert proof["application"] == name and proof["port"] == 12345


@pytest.mark.parametrize("platform,actions", [("linux", "true"), ("win32", "false")])
def test_policy_refuses_non_ci_or_non_windows(desktop, tmp_path, monkeypatch, platform, actions):
    monkeypatch.setattr(desktop.sys, "platform", platform)
    monkeypatch.setenv("GITHUB_ACTIONS", actions)
    with pytest.raises(ValueError, match="GitHub Windows"):
        with desktop.ci_webview_debugging(Path("taller-canamo.exe"), 12345, tmp_path):
            pytest.fail("Must reject before touching registry")
    assert not list(tmp_path.iterdir())
