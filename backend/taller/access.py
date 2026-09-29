"""Bounded, local Access extraction and durable source storage."""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from .errors import AppError, require
from .files import atomic_write

MAX_FILE_BYTES = 2_147_483_648
CHUNK_BYTES = 2_000_000
MAX_RAW_ROW_BYTES = 2 * 1024 * 1024
RUNTIME = Path(__file__).with_name('access_runtime')


def digest_file(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def json_write(path, value):
    atomic_write(Path(path), json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def jsonl_rows(stream):
    """Read one bounded UTF-8 record, including from a compressed ZIP member."""
    count = 0
    while line := stream.readline(MAX_RAW_ROW_BYTES + 1):
        count += 1
        require(len(line) <= MAX_RAW_ROW_BYTES,
                f'La fila {count} supera 2 MiB de JSONL. El original se conserva íntegro; '
                'extrae los adjuntos o textos grandes por separado antes de importar.', 'access_row_size')
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise AppError(f'La fila intermedia {count} no contiene JSON válido.') from exc
        require(isinstance(value, dict), f'La fila intermedia {count} debe ser un objeto.')
        yield count, value


def java_command():
    manifest_path = RUNTIME / 'manifest.json'
    require(manifest_path.exists(), 'Falta el lector Access. Repara la instalación o usa CSV/paquete intermedio.', 'access_runtime')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    jar = RUNTIME / 'canamo-access.jar'
    library = RUNTIME / 'lib/jackcess-5.0.1.jar'
    for file in (jar, library):
        require(file.is_file() and digest_file(file) == manifest['files'].get(file.relative_to(RUNTIME).as_posix()),
                'El lector Access no coincide con su manifiesto. Repara la instalación.', 'access_runtime')
    java = RUNTIME / 'jre/bin' / ('java.exe' if os.name == 'nt' else 'java')
    if not java.is_file():
        # Frozen releases must ship a verified JRE. Development may use the installed JDK.
        require(not getattr(sys, 'frozen', False), 'Esta instalación no incluye el runtime de Access. Repara la instalación.', 'access_runtime')
        java = shutil.which('java')
        require(java, 'Falta Java 17 para el entorno de desarrollo. Ejecuta scripts/prepare_access_runtime.py.', 'access_runtime')
    return [str(java), '-Xmx512m', '-Dfile.encoding=UTF-8', '-cp', os.pathsep.join((str(jar), str(library))), 'CanamoAccess']


def extract_access(source, destination):
    source, destination = Path(source), Path(destination)
    require(source.is_file() and 0 < source.stat().st_size <= MAX_FILE_BYTES, 'Selecciona una copia Access de hasta 2 GiB.')
    before = digest_file(source)
    require(not destination.exists(), 'El directorio de extracción ya existe.', 'conflict')
    try:
        result = subprocess.run([*java_command(), 'extract', str(source), str(destination)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8',
                                timeout=120, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise AppError('La lectura Access superó 120 segundos. Conserva la copia y usa la herramienta de extracción por tablas.', 'access_timeout') from exc
    require(digest_file(source) == before, 'La copia ha cambiado durante la extracción. No se importará.', 'conflict')
    if result.returncode != 0:
        shutil.rmtree(destination, ignore_errors=True)
        try:
            failure_type = json.loads(result.stderr.strip().splitlines()[-1]).get('error', '')
        except (json.JSONDecodeError, IndexError, AttributeError):
            failure_type = ''
        encrypted = failure_type == 'UnsupportedCodecException'
        # Deliberately do not return raw library exceptions or connection strings.
        raise AppError('No se puede leer esta copia Access. Comprueba que está cerrada, no dañada y sin cifrado; para una base cifrada exporta tablas desde Access autorizado. No se ha abierto ningún vínculo.', 'access_unreadable',
                       {'engine': 'Jackcess 5.0.1', 'architecture': platform.machine(), 'drivers_required': False,
                        'encryption': 'unsupported_codec' if encrypted else 'not_determined', 'links_followed': 0})
    manifest = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
    manifest.update({'source_sha256': before, 'source_bytes': source.stat().st_size,
                     'architecture': platform.machine(), 'drivers_required': False, 'original_preserved': True})
    json_write(destination / 'manifest.json', manifest)
    return manifest


class Staging:
    """Rows and incidents remain on disk; pages are views, never a truncation of a lot."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'staging.sqlite'

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS raw_rows(table_name TEXT NOT NULL,row_number INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(table_name,row_number));
          CREATE TABLE IF NOT EXISTS records(position INTEGER PRIMARY KEY,entity TEXT NOT NULL,source_key TEXT NOT NULL,source_hash TEXT NOT NULL,payload TEXT NOT NULL,original TEXT NOT NULL,action TEXT NOT NULL DEFAULT 'insert',resolution TEXT NOT NULL DEFAULT '{}');
          CREATE INDEX IF NOT EXISTS record_key ON records(entity,source_key);
          CREATE INDEX IF NOT EXISTS record_legacy_code ON records(json_extract(payload,'$.legacy_code')) WHERE entity='customers';
          CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY,level TEXT NOT NULL,entity TEXT NOT NULL,source_key TEXT NOT NULL,message TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS line_rows(source_key TEXT NOT NULL,row_number INTEGER NOT NULL,data TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS line_key ON line_rows(source_key);
        ''')
        return conn

    def load_extracted(self, manifest, directory):
        with self.connect() as conn:
            conn.execute('DELETE FROM raw_rows')
            for table in manifest['tables']:
                if table.get('linked'):
                    continue
                filename = table.get('file', '')
                require(filename.startswith('table-') and Path(filename).name == filename, 'Nombre de tabla intermedia no válido.')
                count = 0
                with (Path(directory) / filename).open('rb') as source:
                    for count, value in jsonl_rows(source):
                        conn.execute('INSERT INTO raw_rows VALUES(?,?,?)', (table['name'], count, json.dumps(value, ensure_ascii=False)))
                require(count == table['rows'], 'La extracción no concilia el número de filas.')


def decode_chunk(data):
    require(isinstance(data, str) and len(data) <= (CHUNK_BYTES + 2) // 3 * 4, 'Fragmento de importación demasiado grande.')
    try:
        result = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AppError('El fragmento de archivo no es válido.') from exc
    require(0 < len(result) <= CHUNK_BYTES, 'Tamaño de fragmento no válido.')
    return result
