"""Download small local engines' models from pinned public sources during build.

Never runs while invoicing and never uploads documents. The desktop app only reads
the resulting verified local assets; it does not download models automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT/'backend/taller/assistant_models'
LOCK = ROOT/'scripts/assistant-models.lock.json'


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    args = parser.parse_args()
    if args.verify:
        manifest = json.loads((TARGET/'manifest.json').read_text())
        for name, expected in manifest['assets'].items():
            if not (TARGET/name).is_file() or digest(TARGET/name)!=expected:
                raise SystemExit('Falta o ha cambiado un modelo local: '+name)
        print('Modelos locales verificados:',len(manifest['assets']))
        return
    lock = json.loads(LOCK.read_text())
    if not any(name.endswith('.zip') for name in lock['files']):
        raise SystemExit('El lock debe contener el modelo de voz con su hash revisado.')
    cache = ROOT/'build/assistant-downloads'
    cache.mkdir(parents=True,exist_ok=True)
    TARGET.mkdir(parents=True,exist_ok=True)
    for name, item in lock['files'].items():
        path = cache/name
        if not path.is_file() or digest(path)!=item['sha256']:
            temporary = cache/(name+'.part')
            print('Descargando modelo:',name,flush=True)
            try:
                with urllib.request.urlopen(item['url'],timeout=45) as response, temporary.open('wb') as handle:
                    while chunk := response.read(1024*1024):
                        handle.write(chunk)
                        if handle.tell()>80_000_000:
                            raise RuntimeError('El modelo supera el tamaño máximo revisado.')
                if digest(temporary)!=item['sha256']:
                    raise RuntimeError('Hash de modelo incorrecto: '+name)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        if path.suffix=='.zip':
            with tempfile.TemporaryDirectory(prefix='voice-',dir=cache) as temp, zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                if len(members)>2000 or sum(member.file_size for member in members)>250_000_000:
                    raise RuntimeError('Paquete de voz fuera de los límites revisados.')
                for member in members:
                    pieces=PurePosixPath(member.filename).parts
                    if not pieces or pieces[0]!='vosk-model-small-es-0.42' or '..' in pieces or '\\' in member.filename or member.filename.startswith('/') or ((member.external_attr>>16)&0o170000)==0o120000:
                        raise RuntimeError('Ruta no segura en paquete de voz.')
                    destination = Path(temp).joinpath(*pieces)
                    if member.is_dir():
                        destination.mkdir(parents=True,exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        with archive.open(member) as src, destination.open('wb') as dst:
                            shutil.copyfileobj(src,dst)
                target=TARGET/'vosk-model-small-es-0.42'
                if target.exists():shutil.rmtree(target)
                shutil.copytree(Path(temp)/target.name,target)
        else:
            shutil.copyfile(path,TARGET/name)
    shutil.copytree(ROOT/'tools/assistant/licenses', TARGET/'licenses', dirs_exist_ok=True)
    assets = {str(path.relative_to(TARGET)).replace('\\','/'):digest(path) for path in sorted(TARGET.rglob('*')) if path.is_file() and path.name!='manifest.json'}
    (TARGET/'manifest.json').write_text(json.dumps({'source_lock':lock,'assets':assets},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Modelos preparados:',len(assets),'archivos',flush=True)


if __name__=='__main__':main()
