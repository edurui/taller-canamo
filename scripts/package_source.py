"""Package the project sources, without private references, runtime data or build caches."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ('backend', 'frontend', 'public', 'web', 'scripts', 'tests', 'e2e', 'tools', 'docs', '.github',
           'src-tauri/src', 'src-tauri/tests', 'src-tauri/icons', 'src-tauri/capabilities')
EXCLUDED_PARTS = {'__pycache__', '.pytest_cache', 'node_modules', '.venv', 'private-reference',
                  'assistant_models', 'access_runtime', 'legal', 'target', 'binaries'}
PRIVATE_SUFFIXES = {'.pfx', '.p12', '.pem', '.dpapi', '.mdb', '.accdb', '.db', '.canamo', '.pyc'}
ROOT_SUFFIXES = {'.md', '.json', '.toml', '.ts', '.txt', '.lock', '.cmd', '.html'}


def source_files():
    paths = {path for path in ROOT.iterdir() if path.is_file() and
             (path.suffix in ROOT_SUFFIXES or path.name in ('.gitignore', '.gitattributes', '.nvmrc'))}
    paths.update(path for path in (ROOT/'src-tauri').iterdir()
                 if path.is_file() and path.suffix in {'.rs', '.toml', '.json', '.lock'})
    for folder in FOLDERS:
        for path in (ROOT/folder).rglob('*'):
            relative = path.relative_to(ROOT/folder)
            # Generated backend resources are reconstructed by the locked build.
            excluded = EXCLUDED_PARTS if folder == 'backend' else EXCLUDED_PARTS - {'legal'}
            if path.is_file() and not excluded.intersection(relative.parts) and not any(part.endswith('.egg-info') for part in relative.parts):
                paths.add(path)
    for path in sorted(paths):
        if path.is_symlink():
            raise ValueError('No se empaquetan enlaces: '+str(path.relative_to(ROOT)))
        if path.suffix.lower() in PRIVATE_SUFFIXES or '.sqlite' in path.name.lower() or path.name.startswith('.env'):
            raise ValueError('Archivo de datos o secreto fuera del inventario admitido: '+str(path.relative_to(ROOT)))
        yield path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='build/entrega/taller-canamo-0.9.1-fuentes.zip')
    args=parser.parse_args()
    output=(ROOT/args.output).resolve()
    if not output.is_relative_to(ROOT/'build') or output.suffix!='.zip':
        parser.error('El ZIP debe guardarse dentro de build/.')
    output.parent.mkdir(parents=True,exist_ok=True)
    inventory={}
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in source_files():
            data=path.read_bytes(); name=path.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo(name,date_time=(2026,9,23,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(stat.S_IFREG | (path.stat().st_mode & 0o777)) << 16
            archive.writestr(info,data,compresslevel=9)
            inventory[name]=hashlib.sha256(data).hexdigest()
        info=zipfile.ZipInfo('SOURCE-SHA256.json',date_time=(2026,9,23,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=(stat.S_IFREG | 0o644) << 16
        archive.writestr(info,json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',compresslevel=9)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('CRC incorrecto en ZIP de fuentes.')
        for name,expected in inventory.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=expected:
                raise RuntimeError('Huella incorrecta: '+name)
    result={'path':output.relative_to(ROOT).as_posix(),'bytes':output.stat().st_size,
            'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'files':len(inventory),
            'verified':'CRC y SHA-256 de cada archivo',
            'excluded':'Datos privados, informes, dependencias instaladas, motores generados y artefactos; reconstruir mediante los locks/scripts incluidos.'}
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/source-artifact.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
