"""Build the offline Access reader from locked official dependencies (no Office driver)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'backend/taller/access_runtime'


def download(item, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and hashlib.file_digest(destination.open('rb'), 'sha256').hexdigest() == item['sha256']:
        return
    request = urllib.request.Request(item['url'], headers={'User-Agent': 'Canamo-reproducible-build/1'})
    with urllib.request.urlopen(request, timeout=120) as response, tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            shutil.copyfileobj(response, output)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        with temporary.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != item['sha256']:
                raise RuntimeError('La descarga no coincide con el hash fijado: ' + item['url'])
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(with_jre=True):
    lock = json.loads((ROOT / 'tools/access/dependencies.lock.json').read_text())
    library = DESTINATION / 'lib' / ('jackcess-' + lock['jackcess']['version'] + '.jar')
    download(lock['jackcess'], library)
    javac = shutil.which('javac')
    if not javac:
        raise SystemExit('Para construir el lector se necesita un JDK 17 o posterior de Adoptium. El usuario final recibe el JRE incluido.')
    with tempfile.TemporaryDirectory(prefix='canamo-javac-') as temporary:
        classes = Path(temporary)
        subprocess.run([javac, '--release', '17', '-encoding', 'UTF-8', '-cp', str(library), '-d', str(classes), str(ROOT / 'tools/access/CanamoAccess.java')], check=True)
        # Stable zip metadata: same Java classes produce the same jar bytes.
        with zipfile.ZipFile(DESTINATION / 'canamo-access.jar', 'w', compression=zipfile.ZIP_DEFLATED) as jar:
            for file in sorted(classes.rglob('*.class')):
                item = zipfile.ZipInfo(file.relative_to(classes).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                jar.writestr(item, file.read_bytes())
    with zipfile.ZipFile(library) as jar:
        for name in jar.namelist():
            if name in {'META-INF/LICENSE.txt', 'META-INF/NOTICE.txt', 'META-INF/LICENSE', 'META-INF/NOTICE'}:
                (DESTINATION / ('JACKCESS-' + name.split('/')[-1])).write_bytes(jar.read(name))
    for file in (ROOT / 'tools/access/licenses').iterdir():
        shutil.copyfile(file, DESTINATION / file.name)
    platform = 'windows' if sys.platform == 'win32' else 'linux'
    if with_jre:
        item = lock['jre'][platform]
        archive = ROOT / 'build/access' / item['url'].split('/')[-1]
        download(item, archive)
        with tempfile.TemporaryDirectory(prefix='canamo-jre-', dir=DESTINATION) as directory:
            folder = Path(directory)
            if archive.suffix == '.zip':
                with zipfile.ZipFile(archive) as source:
                    for info in source.infolist():
                        target = (folder / info.filename).resolve()
                        if not target.is_relative_to(folder.resolve()):
                            raise RuntimeError('Ruta inválida en el JRE oficial.')
                    source.extractall(folder)
            else:
                with tarfile.open(archive) as source:
                    source.extractall(folder, filter='data')
            extracted = next(folder.iterdir())
            target = DESTINATION / 'jre'
            if target.exists():
                shutil.rmtree(target)
            shutil.move(extracted, target)
    manifest = {'engine': lock['jackcess'], 'jre': lock['jre'][platform] if with_jre else None,
                'source_sha256': hashlib.sha256((ROOT / 'tools/access/CanamoAccess.java').read_bytes()).hexdigest(),
                'files': {file.relative_to(DESTINATION).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest() for file in DESTINATION.rglob('*') if file.is_file() and file.name != 'manifest.json'}}
    (DESTINATION / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Lector Access preparado:', DESTINATION)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-java', action='store_true', help='Desarrollo: compilar lector sin descargar JRE. No usar para distribución.')
    prepare(not parser.parse_args().system_java)
