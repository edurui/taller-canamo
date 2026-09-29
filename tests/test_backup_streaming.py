"""Bounded file transport with synthetic resources; no user directory is opened."""
import base64
import hashlib
import io
import os
import struct
import zipfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from taller.app import App
from taller.backups import CHUNK_BYTES, INLINE_BYTES, MAGIC, _atomic_copy, decrypt, encrypt
from taller.errors import AppError


def resource(app, size=6*CHUNK_BYTES):
    path = app.db.root/'pdfs'/'synthetic-large.pdf'
    digest = hashlib.sha256()
    with path.open('wb') as output:
        for _ in range(size//CHUNK_BYTES):
            block = os.urandom(CHUNK_BYTES)
            digest.update(block)
            output.write(block)
    return path, digest.hexdigest()


def upload(backups, result):
    task = backups.upload_start(result['name'], result['bytes'])
    offset, digest = 0, hashlib.sha256()
    while offset<result['bytes']:
        part = backups.download_chunk(result['capability'], offset)
        chunk = base64.b64decode(part['content'])
        assert hashlib.sha256(chunk).hexdigest()==part['sha256']
        assert part['offset']==offset and 0<len(chunk)<=CHUNK_BYTES
        assert part['bytes']==len(chunk) and part['total_bytes']==result['bytes']
        digest.update(chunk)
        status = backups.upload_chunk(task['upload_id'], offset, part['content'])
        repeated = backups.upload_chunk(task['upload_id'], offset, part['content'])
        assert repeated['offset']==status['offset']
        offset = status['offset']
        assert part['eof']==(offset==result['bytes'])
    assert digest.hexdigest()==result['sha256']
    return task['upload_id']


def test_streaming_encrypted_copy_download_upload_restore_without_whole_file_reads(app, monkeypatch):
    path, original_hash = resource(app)
    password = 'Synthetic streaming password'
    old_read = Path.read_bytes
    def bounded_read(file):
        assert file.stat().st_size<=INLINE_BYTES, 'Whole-file read of a large resource'
        return old_read(file)
    monkeypatch.setattr(Path, 'read_bytes', bounded_read)
    result = app.backups.create(password)
    assert result['bytes']>INLINE_BYTES and 'content' not in result
    assert result['mime']=='application/octet-stream' and result['chunk_bytes']==CHUNK_BYTES
    identifier = upload(app.backups, result)
    prepared = app.backups.upload_finish(identifier, password)
    assert not (app.backups.upload_root/identifier).exists()
    path.unlink()
    restored = app.backups.restore(prepared['token'], 'RESTAURAR')
    assert restored['restored']
    with path.open('rb') as incoming:
        assert hashlib.file_digest(incoming, 'sha256').hexdigest()==original_hash
    assert not list(app.db.root.glob('.backup-work-*'))
    assert not list(app.db.root.glob('.restore-preview-*'))
    assert app.backups.release_download(result['capability'])=={'released':True}
    with pytest.raises(AppError, match='caducado'):
        app.backups.download_chunk(result['capability'], 0)


def test_download_capability_is_bounded_revocable_expiring_and_rejects_changed_file(app):
    result = app.backups.create()
    for changes in ({'offset':True}, {'offset':-1}, {'length':True}, {'length':CHUNK_BYTES+1}, {'offset':result['bytes']+1}):
        with pytest.raises(AppError):
            app.backups.download_chunk(result['capability'], **{'offset':0, **changes})
    with pytest.raises(AppError):
        app.backups.download_chunk('../../secure/certificate.dpapi', 0)
    eof = app.backups.download_chunk(result['capability'], result['bytes'])
    assert eof['eof'] and eof['content']=='' and eof['bytes']==0
    path = app.db.root/'backups'/result['name']
    with path.open('ab') as output:
        output.write(b'changed')
    with pytest.raises(AppError, match='cambió'):
        app.backups.download_chunk(result['capability'], 0)
    second = app.backups.create()
    app.backups.downloads[second['capability']]['expires'] = datetime.now(timezone.utc)-timedelta(seconds=1)
    with pytest.raises(AppError, match='caducado'):
        app.backups.download_chunk(second['capability'], 0)
    app.backups.release_download(result['capability'])
    app.backups.release_download(result['capability'])
    assert path.exists()


def test_upload_survives_restart_rejects_gaps_and_conflicts_and_truncates_unacknowledged_tail(app):
    task = app.backups.upload_start('Copia sintética.canamo', 12)
    identifier = task['upload_id']
    part = base64.b64encode(b'abcdefgh').decode()
    with pytest.raises(AppError):
        app.backups.upload_finish(identifier)
    with pytest.raises(AppError, match='Posición'):
        app.backups.upload_chunk(identifier, 1, part)
    assert app.backups.upload_chunk(identifier, 0, part)['offset']==8
    with pytest.raises(AppError, match='no coincide'):
        app.backups.upload_chunk(identifier, 0, base64.b64encode(b'changed!').decode())
    with (app.backups.upload_root/identifier/'source.canamo').open('ab') as output:
        output.write(b'partial-after-process-crash')
    reopened = App(app.db.root)
    assert reopened.backups.upload_status(identifier)['offset']==8
    assert reopened.backups.upload_list()[0]['upload_id']==identifier
    assert (app.backups.upload_root/identifier/'source.canamo').stat().st_size==8
    assert reopened.backups.upload_chunk(identifier, 0, part)['offset']==8
    assert reopened.backups.upload_chunk(identifier, 8, base64.b64encode(b'ijkl').decode())['offset']==12
    assert reopened.backups.upload_cancel(identifier)=={'cancelled':True}
    assert reopened.backups.upload_cancel(identifier)=={'cancelled':True}
    assert reopened.backups.upload_list()==[]
    with pytest.raises(AppError):
        reopened.backups.upload_status(identifier)
    with pytest.raises(AppError):
        reopened.backups.upload_start('../copy.canamo', 20)
    with pytest.raises(AppError):
        reopened.backups.upload_start('copy.canamo', True)
    with pytest.raises(AppError):
        reopened.backups.upload_start('copy.canamo', 9*1024**3+1)


@pytest.mark.parametrize('damage', ['password', 'tag', 'ciphertext'])
def test_gcm_authenticates_before_zip_parser_and_cleans_unauthenticated_plaintext(app, monkeypatch, damage):
    password = 'Synthetic cipher password'
    result = app.backups.create(password)
    encrypted = bytearray(base64.b64decode(result['content']))
    if damage=='tag':
        encrypted[-1] ^= 1
    elif damage=='ciphertext':
        encrypted[40] ^= 1
    task = app.backups.upload_start(result['name'], len(encrypted))
    app.backups.upload_chunk(task['upload_id'], 0, base64.b64encode(encrypted).decode())
    def never_parse(*_args, **_kwargs):
        raise AssertionError('ZIP parser reached unauthenticated plaintext')
    monkeypatch.setattr('taller.backups.zipfile.ZipFile', never_parse)
    with pytest.raises(AppError, match='incorrecta|dañada'):
        app.backups.upload_finish(task['upload_id'], 'Wrong password' if damage=='password' else password)
    assert app.backups.upload_status(task['upload_id'])['offset']==len(encrypted)
    assert not list(app.db.root.glob('.backup-check-*'))
    assert not list(app.db.root.glob('.restore-preview-*'))
    assert not app.backups.recovery_status()['blocked']


def test_streaming_cipher_is_byte_format_compatible_with_v1_aesgcm(app):
    plain = app.backups.create()
    original = base64.b64decode(plain['content'])
    password = 'Synthetic legacy password'
    legacy = encrypt(original, password)
    assert app.backups.preview(base64.b64encode(legacy).decode(), password)['migration']['applied']==[]
    new = app.backups.create(password)
    decoded = decrypt(base64.b64decode(new['content']), password)
    assert decoded.startswith(b'PK') and base64.b64decode(new['content']).startswith(MAGIC)


def test_large_transfer_reexport_is_exact_after_cancelled_download(app):
    resource(app)
    first = app.backups.prepare_transfer('Synthetic transfer password')
    app.backups.release_download(first['capability'])
    second = app.backups.prepare_transfer('Different password ignored')
    assert first['sha256']==second['sha256'] and first['bytes']==second['bytes']
    assert first['transfer_id']==second['transfer_id']
    assert first['name']==second['name'] and first['capability']!=second['capability']
    assert 'content' not in first and 'content' not in second
    assert second['repeated'] and app.backups.recovery_status()['reason']=='transfer_source'
    identifier = upload(app.backups, second)
    assert app.backups.upload_finish(identifier, 'Synthetic transfer password')['counts']['documents']==0


def test_simulation_copy_is_disposable_but_import_original_and_staging_are_preserved(app):
    batch = app.imports.preview('legacy_code,name,unmapped\nSTREAM,Cliente sintético,valor original\n')
    folder = app.db.root/'imports'/batch['batch_id']
    with (folder/'simulation.sqlite').open('wb') as output:
        output.truncate(9*1024**3)  # Sparse sentinel larger than the complete limit.
    result = app.backups.create()
    prepared = app.backups.preview(result['content'])
    staged = app.backups.previews[prepared['token']]['folder']/'imports'/batch['batch_id']
    assert (staged/'source.bin').read_bytes()==(folder/'source.bin').read_bytes()
    assert (staged/'staging.sqlite').exists() and not (staged/'simulation.sqlite').exists()


def test_second_copy_preserves_previous_file_when_stream_read_fails(tmp_path, monkeypatch):
    source, target = tmp_path/'source', tmp_path/'target'
    source.write_bytes(b'x'*(CHUNK_BYTES*2))
    target.write_bytes(b'previous-complete-copy')
    original_open = Path.open
    class Interrupted(io.BytesIO):
        def read(self, size=-1):
            assert 0<size<=CHUNK_BYTES
            if self.tell():
                raise OSError('Injected read failure')
            return super().read(size)
    def failing_open(path, *args, **kwargs):
        if path==source:
            return Interrupted(b'x'*(CHUNK_BYTES*2))
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', failing_open)
    with pytest.raises(OSError, match='Injected'):
        _atomic_copy(source, target)
    assert target.read_bytes()==b'previous-complete-copy'
    assert not list(tmp_path.glob('*.partial'))


@pytest.mark.parametrize('damage', ['directory_size', 'false_count', 'actual_count', 'control_name'])
def test_central_directory_limits_are_checked_before_zipfile_allocation(app, monkeypatch, damage):
    (app.db.root/'pdfs'/'counted.pdf').write_bytes(b'synthetic')
    package = bytearray(base64.b64decode(app.backups.create()['content']))
    end = package.rfind(b'PK\x05\x06')
    if damage=='directory_size':
        struct.pack_into('<I', package, end+12, 500*1024**2)
    elif damage=='control_name':
        directory = struct.unpack_from('<I', package, end+16)[0]
        package[directory+46] = 0
    else:
        struct.pack_into('<H', package, end+8, 1)
        struct.pack_into('<H', package, end+10, 1)
        if damage=='actual_count':
            monkeypatch.setattr('taller.backups.MAX_FILES', 2)
    def never_allocate(*_args, **_kwargs):
        raise AssertionError('ZipFile allocated untrusted central directory')
    monkeypatch.setattr('taller.backups.zipfile.ZipFile', never_allocate)
    with pytest.raises(AppError, match='directorio|entradas|control'):
        app.backups.preview(base64.b64encode(package).decode())
    assert not app.backups.previews


def test_zip64_central_directory_and_legacy_comment_are_accepted(app, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(zipfile, 'ZIP64_LIMIT', 128)
        result = app.backups.create()
    raw = base64.b64decode(result['content'])
    assert b'PK\x06\x06' in raw and b'PK\x06\x07' in raw
    preview = app.backups.preview(result['content'])
    assert preview['counts']['customers']==0
    legacy = io.BytesIO(base64.b64decode(app.backups.create()['content']))
    with zipfile.ZipFile(legacy, 'a') as archive:
        archive.comment = 'Comentario sintético de una copia anterior'.encode('utf-8')
    assert app.backups.preview(base64.b64encode(legacy.getvalue()).decode())['counts']['customers']==0
