"""Build orchestration only: every compiler/installer command below is simulated.

These tests do not compile, install, or execute a Windows binary.
"""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def windows_builder(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('canamo_build_orchestration', scripts / 'build_desktop.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    monkeypatch.setattr(module.sys, 'argv', ['build_desktop.py'])
    monkeypatch.setattr(module.shutil, 'which', lambda command: '/simulated/' + command)
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *args, **kwargs: 'host: x86_64-pc-windows-msvc\n')
    monkeypatch.setattr(module.importlib.metadata, 'distributions', lambda: [])
    monkeypatch.setattr(module, 'build_input_hashes', lambda include_desktop: {'simulated-input': 'unchanged'})
    for name in ('package-lock.json', 'requirements-dev.lock', 'src-tauri/Cargo.lock'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('simulated fixture', encoding='utf-8')
    (tmp_path / 'package.json').write_text('{"version":"0.9.1"}', encoding='utf-8')
    source_policy = tmp_path / 'backend/taller/release-policy.json'
    source_policy.parent.mkdir(parents=True)
    source_policy.write_text(json.dumps({'format_version': 1, 'application_version': '0.9.1', 'edition': 'development'}), encoding='utf-8')
    calls = []

    def simulated_sidecar(target, policy):
        assert target == 'x86_64-pc-windows-msvc'
        path = tmp_path / 'src-tauri/binaries/canamo-service-x86_64-pc-windows-msvc.exe'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'SIMULATED; NOT EXECUTABLE\n' + policy.read_bytes())
        return path

    def simulated_run(command, **kwargs):
        command = [str(part) for part in command]
        calls.append(command)
        if command[1:4] == ['run', 'tauri', '--']:
            for name in ('taller-canamo.exe', 'canamo-service.exe', 'bundle/nsis/simulated-setup.exe'):
                path = tmp_path / 'src-tauri/target/release' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'SIMULATED; NOT EXECUTABLE')
        elif '--diagnose-sidecar' in command:
            path = Path(command[command.index('--diagnose-sidecar') + 1])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'ok': True, 'fixture': 'simulated orchestration only'}), encoding='utf-8')

    monkeypatch.setattr(module, 'build_sidecar', simulated_sidecar)
    monkeypatch.setattr(module, 'run', simulated_run)
    return module, tmp_path, calls


def test_simulated_windows_orchestration_preserves_diagnostic_and_manifest(windows_builder):
    module, root, calls = windows_builder
    module.main()
    diagnostic = json.loads((root / 'reports/windows-staged-sidecar.json').read_text())
    artifacts = json.loads((root / 'reports/windows-artifacts.json').read_text())
    assert diagnostic == {'ok': True, 'fixture': 'simulated orchestration only'}
    assert len(artifacts['artifacts']) == 4
    assert artifacts['embedded_release_policy']['edition'] == 'development'
    assert all(len(item['sha256']) == 64 and item['bytes'] > 0 for item in artifacts['artifacts'])
    commands = [command[1:] for command in calls]
    assert commands.index(['run', 'typecheck:e2e']) < commands.index(['run', 'build']) < commands.index(['run', 'test:e2e'])


def test_simulated_windows_rejects_changed_inputs_and_removes_old_acceptance(windows_builder, monkeypatch):
    module, root, _ = windows_builder
    report = root / 'reports/windows-artifacts.json'
    report.parent.mkdir()
    report.write_text('{"old_acceptance":true}', encoding='utf-8')
    snapshots = iter([{'input': 'before'}, {'input': 'changed'}])
    monkeypatch.setattr(module, 'build_input_hashes', lambda include_desktop: next(snapshots))
    with pytest.raises(SystemExit, match='cambiaron'):
        module.main()
    assert not report.exists()
    assert json.loads((root / 'reports/windows-staged-sidecar.json').read_text())['fixture'].startswith('simulated')
