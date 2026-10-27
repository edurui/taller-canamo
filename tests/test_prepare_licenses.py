"""License collection must preserve UTF-8 metadata on a Windows CP1252 host."""
import hashlib
import importlib.util
import json
from pathlib import Path


def test_license_inventory_preserves_nonwestern_metadata_with_cp1252_default(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'scripts/prepare_licenses.py'
    spec = importlib.util.spec_from_file_location('canamo_test_prepare_licenses', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / 'backend/taller/legal'
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'TARGET', target)
    monkeypatch.setattr(module.importlib.metadata, 'distributions', lambda: [])
    monkeypatch.setattr(module.shutil, 'which', lambda command: '/synthetic/cargo')
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *args, **kwargs: b'{"packages":[]}')

    def put(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
        return path

    put('tools/legal/supplemental-lock.json', '{}')
    put('tools/legal/SOURCES.md', 'Synthetic license sources')
    for folder in ('tools/assistant/licenses', 'tools/access/licenses'):
        (tmp_path / folder).mkdir(parents=True)
    put('package-lock.json', json.dumps({'packages': {'node_modules/synthetic-license': {}}}))
    put('node_modules/synthetic-license/package.json', json.dumps({
        'name': 'synthetic-license', 'version': '1.0.0',
        'license': 'MIT', 'description': 'Licencia sintética 中文 Ελληνικά',
        'author': 'Autor sintético ā',  # UTF-8 contains 0x81, undefined in CP1252.
    }, ensure_ascii=False))
    notice = put('node_modules/synthetic-license/LICENSE', 'Synthetic notice © 中文')
    font_notice = put('backend/taller/fonts/LICENSE.txt', 'Synthetic font notice Ω')
    put('backend/taller/fonts/manifest.json', json.dumps({
        'family': 'Fuente sintética Ω', 'version': '1.0', 'source': 'https://example.invalid',
        'files_sha256': {'LICENSE.txt': hashlib.sha256(font_notice.read_bytes()).hexdigest()},
    }, ensure_ascii=False))

    real_read = Path.read_text

    def cp1252_default(path, encoding=None, errors=None, newline=None):
        return real_read(path, encoding=encoding or 'cp1252', errors=errors, newline=newline)

    monkeypatch.setattr(Path, 'read_text', cp1252_default)
    module.main()
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    package = next(item for item in manifest['inventory'] if item['ecosystem'] == 'npm')
    assert package['name'] == 'synthetic-license'
    assert (target / package['notices'][0]).read_bytes() == notice.read_bytes()
    font = next(item for item in manifest['inventory'] if item['ecosystem'] == 'font')
    assert font['name'] == 'Fuente sintética Ω'
    assert manifest['missing_notices'] == []
    assert json.loads((tmp_path / 'reports/third-party-inventory.json').read_text(encoding='utf-8')) == manifest
