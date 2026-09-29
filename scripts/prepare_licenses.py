"""Collect notices from the actual installed, locked dependencies for distribution.

Run in the build virtualenv after npm ci. No customer data or credentials are read.
The inventory includes development dependencies for reproducibility; their inclusion
in this inventory does not mean every package is shipped as executable code.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT/'backend/taller/legal'
TOKENS = ('LICENSE', 'LICENCE', 'COPYING', 'COPYRIGHT', 'NOTICE', 'AUTHORS')
SUPPLEMENT = {
    'antlr4-python3-runtime': ('BSD-3-Clause', ROOT/'tools/legal/antlr4-python3-runtime'),
    'flatbuffers': ('Apache-2.0', ROOT/'tools/legal/flatbuffers'),
    'saxonche': ('MPL-2.0', ROOT/'tools/legal/saxonche'),
    'rapidocr': ('Apache-2.0', ROOT/'tools/assistant/licenses/RapidOCR-LICENSE.txt'),
    'vosk': ('Apache-2.0', ROOT/'tools/assistant/licenses/Vosk-LICENSE.txt'),
}


def safe(value):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', value)


def copy_notice(source, destination):
    if source.is_file() and source.stat().st_size < 5_000_000:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return str(destination.relative_to(TARGET)).replace('\\', '/')


def main():
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    inventory = []
    supplements = json.loads((ROOT/'tools/legal/supplemental-lock.json').read_text())
    for dist in sorted(importlib.metadata.distributions(), key=lambda item: item.metadata['Name'].lower()):
        name = dist.metadata['Name']; key = name.lower().replace('_','-')
        files = []
        for entry in dist.files or []:
            source = Path(dist.locate_file(entry))
            if any(token in source.name.upper() for token in TOKENS) and source.suffix not in ('.py','.pyc','.so','.dll'):
                label = safe(str(entry))
                copied = copy_notice(source, TARGET/'python'/safe(name)/label)
                if copied: files.append(copied)
        license = dist.metadata.get('License-Expression') or dist.metadata.get('License','')
        if key in SUPPLEMENT:
            license, source = SUPPLEMENT[key]
            for file in [source] if source.is_file() else source.rglob('*'):
                if file.is_file():
                    copied = copy_notice(file,TARGET/'python'/safe(name)/safe(file.name))
                    if copied:files.append(copied)
        classifiers = [value for value in dist.metadata.get_all('Classifier',[]) if value.startswith('License ::')]
        inventory.append({'ecosystem':'python','name':name,'version':dist.version,'license':license[:500] if license else classifiers,
                          'homepage':dist.metadata.get('Home-page'),'project_urls':dist.metadata.get_all('Project-URL',[]),'notices':sorted(set(files))})
    lock = json.loads((ROOT/'package-lock.json').read_text())
    for package, metadata in sorted(lock.get('packages',{}).items()):
        if not package:continue
        directory = ROOT/package
        if not (directory/'package.json').is_file():continue  # Other-platform optional package; collected on that platform.
        installed = json.loads((directory/'package.json').read_text())
        files = []
        for source in directory.iterdir():
            if any(token in source.name.upper() for token in TOKENS):
                copied = copy_notice(source,TARGET/'npm'/safe(installed.get('name',package))/safe(source.name))
                if copied:files.append(copied)
        if not files:
            # Native npm artifacts inherit the notice of the matching publisher
            # package at exactly the same version, installed from this lockfile.
            name = installed.get('name','')
            parent = next((value for prefix,value in (
                ('@esbuild/', 'esbuild'), ('@napi-rs/lzma-', '@napi-rs/lzma'),
                ('@rollup/rollup-', 'rollup'), ('@tauri-apps/cli-', '@tauri-apps/cli')) if name.startswith(prefix)), None)
            owner = ROOT/'node_modules'/parent if parent else None
            if owner and (owner/'package.json').is_file() and json.loads((owner/'package.json').read_text())['version']==installed['version']:
                for source in owner.iterdir():
                    if any(token in source.name.upper() for token in TOKENS):
                        copied=copy_notice(source,TARGET/'npm'/safe(name)/safe(source.name))
                        if copied:files.append(copied)
        extra=supplements.get('npm:'+installed.get('name','')+'@'+installed['version'],[])
        for notice in extra:
            source=ROOT/notice['file']
            if hashlib.sha256(source.read_bytes()).hexdigest()!=notice['sha256']:
                raise ValueError('Ha cambiado un aviso de licencia: '+notice['file'])
            copied=copy_notice(source,TARGET/'npm'/safe(installed['name'])/safe(source.name))
            if copied:files.append(copied)
        inventory.append({'ecosystem':'npm','name':installed.get('name',package),'version':installed['version'],
                          'license':installed.get('license',metadata.get('license','')),'development':metadata.get('dev',False),'notices':files,
                          'supplement_sources':[notice['url'] for notice in extra]})
    cargo = shutil.which('cargo') or str(Path.home()/'.cargo/bin/cargo')
    graph = json.loads(subprocess.check_output([cargo,'metadata','--locked','--format-version','1'],cwd=ROOT/'src-tauri'))
    for package in sorted(graph['packages'],key=lambda item:(item['name'],item['version'])):
        if package.get('source') is None:continue
        folder=Path(package['manifest_path']).parent
        sources=list(folder.iterdir())
        if package.get('license_file'):sources.append(folder/package['license_file'])
        files=[]
        for source in sources:
            if any(token in source.name.upper() for token in TOKENS):
                copied=copy_notice(source,TARGET/'rust'/safe(package['name']+'-'+package['version'])/safe(source.name))
                if copied:files.append(copied)
        extra=supplements.get(package['name']+'@'+package['version'],[])
        for notice in extra:
            source=ROOT/notice['file']
            if hashlib.sha256(source.read_bytes()).hexdigest()!=notice['sha256']:
                raise ValueError('Ha cambiado un aviso de licencia: '+notice['file'])
            copied=copy_notice(source,TARGET/'rust'/safe(package['name']+'-'+package['version'])/safe(source.name))
            if copied:files.append(copied)
        inventory.append({'ecosystem':'rust','name':package['name'],'version':package['version'],'license':package.get('license'),
                          'repository':package.get('repository'),'notices':sorted(set(files)),
                          'supplement_sources':[notice['url'] for notice in extra]})
    for folder in (ROOT/'tools/assistant/licenses', ROOT/'tools/access/licenses'):
        for source in folder.iterdir():
            copy_notice(source,TARGET/'models-and-access'/safe(folder.parent.name)/source.name)
    font_manifest=json.loads((ROOT/'backend/taller/fonts/manifest.json').read_text(encoding='utf-8'))
    font_notices=[]
    for name,expected in font_manifest['files_sha256'].items():
        source=ROOT/'backend/taller/fonts'/name
        if hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
            raise ValueError('Ha cambiado un recurso tipográfico: '+name)
        if any(token in name.upper() for token in TOKENS):
            font_notices.append(copy_notice(source,TARGET/'fonts'/name))
    inventory.append({'ecosystem':'font','name':font_manifest['family'],'version':font_manifest['version'],
                      'license':'Bitstream-Vera / Arev / public-domain DejaVu changes',
                      'homepage':font_manifest['source'],'notices':font_notices})
    for source in (ROOT/'backend/taller/access_runtime/jre/legal').rglob('*'):
        if source.is_file():
            copy_notice(source,TARGET/'java'/source.relative_to(ROOT/'backend/taller/access_runtime/jre/legal'))
    for source in (ROOT/'backend/taller/schemas').rglob('*'):
        if source.is_file() and any(token in source.name.upper() for token in TOKENS):
            copy_notice(source,TARGET/'schemas'/source.relative_to(ROOT/'backend/taller/schemas'))
    missing=[item['ecosystem']+':'+item['name'] for item in inventory if not item['notices']]
    manifest={'format':'canamo-third-party-notices-v1','inventory':inventory,'missing_notices':missing,
              'notice':'Inventario del entorno de construcción. Incluye herramientas de desarrollo. No contiene datos del taller.',
              'source_information':'Consulte SOURCES.md y los repositorios/versiones indicados. Las bibliotecas se distribuyen sin modificar.'}
    copy_notice(ROOT/'tools/legal/SOURCES.md',TARGET/'SOURCES.md')
    manifest['files_sha256']={path.relative_to(TARGET).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in TARGET.rglob('*') if path.is_file()}
    (TARGET/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/third-party-inventory.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Dependencias inventariadas:',len(inventory),'Avisos copiados:',len(manifest['files_sha256']))
    if missing:print('Paquetes que solo declaran licencia en metadatos:',', '.join(missing))


if __name__=='__main__':main()
