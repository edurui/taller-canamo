"""Reproducible local capacity probe. All resources live in one TemporaryDirectory.

Run: PYTHONPATH=backend .venv/bin/python reports/backup-capacity-check-2026-09-23.py
The binary is synthetic, sparse and compressible. This does not test MDB parsing.
"""
import base64
import hashlib
import json
import os
import platform
from pathlib import Path
import tempfile
import time
import tracemalloc
import zipfile

from taller.app import App
from taller.backups import CHUNK_BYTES, INLINE_BYTES, _file_hash
from taller.db import uid
from taller.reporting import Reporting


start = time.monotonic()
with tempfile.TemporaryDirectory(prefix='canamo-capacity-synthetic-') as temporary:
    root = Path(temporary)
    app = App(root/'data')
    external = root/'second-location'
    app.settings.save('backup', {'external_directory':str(external)})
    original = app.db.root/'imports'/uid()
    original.mkdir()
    source = original/'source.bin'
    with source.open('wb') as output:
        output.write(b'SYNTHETIC CAPACITY PROBE - NOT AN ACCESS DATABASE\n')
        output.truncate(2*1024**3)
        marker = b'SYNTHETIC-END!!!!'
        output.seek(-len(marker), os.SEEK_END)
        output.write(marker)
    (original/'upload.json').write_text(json.dumps({'name':'synthetic-capacity.mdb','size':source.stat().st_size}), encoding='utf-8')
    with (app.db.root/'pdfs'/'synthetic-random.pdf').open('wb') as output:
        for _ in range(4):
            output.write(os.urandom(CHUNK_BYTES))
    expected = _file_hash(source)
    tracemalloc.start()
    password = 'Synthetic capacity password'
    result = app.backups.create(password)
    created = time.monotonic()
    assert result['bytes']>INLINE_BYTES and 'content' not in result
    assert _file_hash(external/result['name'])==result['sha256']
    loaded = app.backups.upload_start(result['name'], result['bytes'])
    offset, download_hash = 0, hashlib.sha256()
    while offset<result['bytes']:
        part = app.backups.download_chunk(result['capability'], offset)
        data = base64.b64decode(part['content'])
        assert len(data)<=CHUNK_BYTES and hashlib.sha256(data).hexdigest()==part['sha256']
        download_hash.update(data)
        offset = app.backups.upload_chunk(loaded['upload_id'], offset, part['content'])['offset']
    assert download_hash.hexdigest()==result['sha256']
    prepared = app.backups.upload_finish(loaded['upload_id'], password)
    checked = time.monotonic()
    source.write_bytes(b'posterior state')
    restored = app.backups.restore(prepared['token'], 'RESTAURAR')
    assert restored['restored'] and source.stat().st_size==2*1024**3
    assert _file_hash(source)==expected
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak<96*1024**2, f'Unexpected Python peak allocation: {peak}'
    restored_at = time.monotonic()
    tracemalloc.start()
    portable = Reporting(app.db, app.settings, app.backups).portable()
    portable_path = root/'downloaded-portable.zip'
    offset, portable_hash = 0, hashlib.sha256()
    with portable_path.open('wb') as output:
        while offset<portable['bytes']:
            part = app.backups.download_chunk(portable['capability'], offset)
            chunk = base64.b64decode(part['content'])
            output.write(chunk)
            portable_hash.update(chunk)
            offset += len(chunk)
    assert portable_hash.hexdigest()==portable['sha256']
    with zipfile.ZipFile(portable_path) as archive:
        member = 'resources/imports/'+original.name+'/source.bin'
        with archive.open(member) as incoming:
            assert hashlib.file_digest(incoming, 'sha256').hexdigest()==expected
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['files'][member]['bytes']==2*1024**3
    portable_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert portable_peak<96*1024**2
    app.backups.release_download(portable['capability'])
    assert not list(app.backups.export_root.iterdir())
    output = {'python':platform.python_version(), 'platform':platform.platform(),
              'source_bytes':source.stat().st_size, 'additional_random_pdf_bytes':4*CHUNK_BYTES,
              'archive_bytes':result['bytes'], 'archive_encrypted':result['encrypted'],
              'archive_sha256':result['sha256'], 'original_sha256':expected,
              'create_seconds':round(created-start, 3), 'upload_and_preview_seconds':round(checked-created, 3),
              'restore_and_hash_seconds':round(restored_at-checked, 3),
              'python_peak_allocated_bytes':peak, 'second_location_verified':True,
              'restored_original_hash_verified':True,
              'portable_archive_bytes':portable['bytes'], 'portable_peak_allocated_bytes':portable_peak,
              'portable_create_download_verify_seconds':round(time.monotonic()-restored_at, 3),
              'portable_original_hash_verified':True, 'portable_temporary_deleted':True,
              'limitation':'Synthetic compressible binary, not MDB parsing, Windows, physical disk failure or a throughput guarantee.'}
print(json.dumps(output, ensure_ascii=False, indent=2))
