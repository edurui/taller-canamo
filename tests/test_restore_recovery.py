"""Restore fault injection only touches per-test temporary data directories."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest

from taller.app import App
from taller.backups import GUARD, JOURNAL, MAGIC, recover_pending_restore
from taller.db import SCHEMA, SCHEMA_VERSION
from taller.errors import AppError
from taller.validation import today


def issue(app, customer_id, description="Trabajo sintético"):
    draft = app.documents.save({"customer_id":customer_id,"lines":[{"description":description,"unit_price":"10"}]})
    return app.documents.publish(draft["id"])


@pytest.fixture
def restore_case(app, customer):
    first = issue(app,customer["id"])
    (app.db.root/'assets'/'imagen.png').write_bytes(b'original-image-fixture')
    (app.db.root/'pdfs'/'original.pdf').write_bytes(b'%PDF-synthetic-original')
    backup = app.backups.create()
    second = issue(app,customer["id"],"Trabajo posterior")
    later = app.contacts.save_customer({"name":"Alta posterior a la copia"})
    (app.db.root/'assets'/'imagen.png').write_bytes(b'new-image-fixture')
    (app.db.root/'assets'/'posterior.png').write_bytes(b'later-image-fixture')
    (app.db.root/'pdfs'/'original.pdf').write_bytes(b'%PDF-new-version')
    (app.db.root/'pdfs'/'posterior.pdf').write_bytes(b'%PDF-later-document')
    (app.db.root/'secure'/'certificate.dpapi').write_bytes(b'encrypted-placeholder-no-private-key')
    app.settings.internal_update('fiscal','certificate_info',{'subject':'Certificado sintético, sin clave'})
    return {'backup':backup,'first':first,'second':second,'later':later}


def assert_current_resources(app):
    assert (app.db.root/'assets'/'imagen.png').read_bytes()==b'new-image-fixture'
    assert (app.db.root/'assets'/'posterior.png').read_bytes()==b'later-image-fixture'
    assert (app.db.root/'pdfs'/'original.pdf').read_bytes()==b'%PDF-new-version'
    assert (app.db.root/'pdfs'/'posterior.pdf').exists()
    assert (app.db.root/'secure'/'certificate.dpapi').read_bytes()==b'encrypted-placeholder-no-private-key'
    assert app.settings.get()['fiscal']['certificate_info']['subject'].startswith('Certificado sintético')


@pytest.mark.parametrize('stage',[
    'prepared','saved:taller.sqlite3','installed:taller.sqlite3','saved:assets','installed:assets',
    'saved:pdfs','installed:pdfs','saved:secure/certificate.dpapi','installed:secure/certificate.dpapi',
    'installed:'+GUARD,
])
def test_restore_failure_rolls_back_the_whole_set(app,restore_case,monkeypatch,stage):
    preview = app.backups.preview(restore_case['backup']['content'])
    checkpoint = app.backups._checkpoint

    def fail(completed):
        checkpoint(completed)
        if completed==stage:
            raise OSError('Injected storage failure')

    monkeypatch.setattr(app.backups,'_checkpoint',fail)
    with pytest.raises(AppError,match='conjunto anterior'):
        app.backups.restore(preview['token'],'RESTAURAR')
    assert_current_resources(app)
    assert app.documents.get(restore_case['second']['id'])['full_number']==restore_case['second']['full_number']
    assert app.contacts.customer(restore_case['later']['id'])['name']=='Alta posterior a la copia'
    assert app.db.check_audit()['ok'] and app.fiscal.verify_chain()['ok']
    assert not (app.db.root/JOURNAL).exists()
    assert not list(app.db.root.glob('.restore-work-*'))
    assert len(app.backups.list())==2


def test_successful_restore_replaces_resources_and_blocks_old_history(app,restore_case):
    preview = app.backups.preview(restore_case['backup']['content'])
    restored = app.backups.restore(preview['token'],'RESTAURAR')
    assert restored['restored'] is True and restored['recovery']['reason']=='older_history'
    assert (app.db.root/'assets'/'imagen.png').read_bytes()==b'original-image-fixture'
    assert (app.db.root/'pdfs'/'original.pdf').read_bytes()==b'%PDF-synthetic-original'
    assert not (app.db.root/'assets'/'posterior.png').exists()
    assert not (app.db.root/'pdfs'/'posterior.pdf').exists()
    assert not (app.db.root/'secure'/'certificate.dpapi').exists()
    assert app.settings.get()['fiscal']['certificate_info'] is None
    assert app.documents.list()['total']==1
    assert app.db.check_audit()['ok'] and app.fiscal.verify_chain()['ok']
    with pytest.raises(AppError,match='historial'):
        issue(app,restore_case['first']['customer_id'])
    assert len(app.fiscal.records())==1
    # A subsequent restart and another old copy cannot erase the high-water mark.
    reopened = App(app.db.root)
    assert reopened.backups.recovery_status()['blocked'] is True
    same = reopened.backups.preview(restore_case['backup']['content'])
    reopened.backups.restore(same['token'],'RESTAURAR')
    with pytest.raises(AppError,match='historial'):
        issue(reopened,restore_case['first']['customer_id'])


def test_restoring_safety_copy_recovers_known_history_and_numbering(app,restore_case):
    preview = app.backups.preview(restore_case['backup']['content'])
    restored = app.backups.restore(preview['token'],'RESTAURAR')
    safety = base64.b64encode((app.db.root/'backups'/restored['safety_copy']).read_bytes()).decode()
    complete = app.backups.preview(safety)
    result = app.backups.restore(complete['token'],'RESTAURAR')
    assert not result['recovery']['blocked']
    next_invoice = issue(app,restore_case['first']['customer_id'])
    assert next_invoice['sequence']==3
    assert app.fiscal.verify_chain()['checked']==3


@pytest.mark.parametrize('stage,committed', [('saved:taller.sqlite3',False),('installed:assets',False),('committed',True)])
def test_process_crash_is_recovered_before_database_initialization(app,restore_case,tmp_path,stage,committed):
    package = tmp_path/'restore-input.txt'
    package.write_text(restore_case['backup']['content'])
    script = '''
import os,sys
from pathlib import Path
from taller.app import App
app=App(sys.argv[1])
preview=app.backups.preview(Path(sys.argv[2]).read_text())
original=app.backups._checkpoint
def crash(stage):
    original(stage)
    if stage==sys.argv[3]: os._exit(73)
app.backups._checkpoint=crash
app.backups.restore(preview['token'],'RESTAURAR')
'''
    environment = {**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'backend')}
    process = subprocess.run([sys.executable,'-c',script,str(app.db.root),str(package),stage],env=environment,capture_output=True,text=True,timeout=30)
    assert process.returncode==73,process.stderr
    assert (app.db.root/JOURNAL).exists()
    reopened = App(app.db.root)
    assert not (app.db.root/JOURNAL).exists()
    assert reopened.documents.list()['total']==(1 if committed else 2)
    if committed:
        assert (app.db.root/'assets'/'imagen.png').read_bytes()==b'original-image-fixture'
        assert not (app.db.root/'secure'/'certificate.dpapi').exists()
        assert reopened.backups.recovery_status()['blocked']
    else:
        assert_current_resources(reopened)
    assert reopened.db.check_audit()['ok']
    assert recover_pending_restore(app.db.root)=={'recovered':False,'action':'none'}


def rewrite_archive(content,extra=None,change_manifest=None):
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(content))) as archive:
        files = {name:archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files.pop('manifest.json'))
    files.update(extra or {})
    manifest['files'] = {name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    if change_manifest:
        change_manifest(manifest)
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in files.items(): archive.writestr(name,data)
        archive.writestr('manifest.json',json.dumps(manifest))
    return base64.b64encode(buffer.getvalue()).decode()


@pytest.mark.parametrize('name',['../outside','assets/../../outside','assets//a.png','assets/CON.txt','pdfs/a.pdf:stream','assets/a.','assets/a\\b.png'])
def test_zip_rejects_windows_aliases_and_path_escapes(app,name):
    package = rewrite_archive(app.backups.create()['content'],{name:b'synthetic'})
    with pytest.raises(AppError): app.backups.preview(package)
    assert not app.backups.previews


def test_zip_rejects_case_collisions_corruption_and_size_limit(app,monkeypatch):
    package = app.backups.create()['content']
    with pytest.raises(AppError,match='duplicadas'):
        app.backups.preview(rewrite_archive(package,{'assets/A.png':b'A','assets/a.png':b'a'}))
    def wrong_digest(manifest): manifest['files']['taller.sqlite3']='0'*64
    with pytest.raises(AppError,match='alterada'):
        app.backups.preview(rewrite_archive(package,change_manifest=wrong_digest))
    monkeypatch.setattr('taller.backups.MAX_BYTES',128)
    with pytest.raises(AppError,match='grande'):
        app.backups.preview(package)


def test_encrypted_restore_keeps_safety_copy_encrypted(app,customer):
    password = 'synthetic-backup-password'
    backup = app.backups.create(password)
    app.contacts.save_customer({'name':'Dato posterior'})
    preview = app.backups.preview(backup['content'],password)
    result = app.backups.restore(preview['token'],'RESTAURAR')
    assert (app.db.root/'backups'/result['safety_copy']).read_bytes().startswith(MAGIC)
    assert app.contacts.list_customers()['total']==1


def test_second_location_error_reports_local_success_without_partial_file(app,tmp_path):
    unavailable = tmp_path/'unavailable'
    unavailable.write_text('A file cannot be an export directory')
    app.settings.save('backup',{'external_directory':str(unavailable)})
    result = app.backups.create()
    assert result['warning']
    assert (app.db.root/'backups'/result['name']).is_file()
    assert not list(app.db.root.rglob('*.partial'))


def test_transfer_requires_retiring_source_and_preserves_chain(app,customer,tmp_path):
    original = issue(app,customer['id'])
    common = app.backups.create()
    target = App(tmp_path/'Nuevo PC con espacios y tildes')
    preview = target.backups.preview(common['content'])
    result = target.backups.restore(preview['token'],'RESTAURAR')
    assert result['recovery']['reason']=='transfer_required'
    with pytest.raises(AppError): target.backups.activate_transfer('ACTIVAR SOLO ESTE EQUIPO')
    transfer = app.backups.prepare_transfer()
    repeated = app.backups.prepare_transfer()
    assert repeated['content']==transfer['content'] and repeated['name']==transfer['name']
    assert repeated['transfer_id']==transfer['transfer_id'] and repeated['repeated']
    with pytest.raises(AppError): issue(app,customer['id'])
    prepared = target.backups.preview(transfer['content'])
    restored = target.backups.restore(prepared['token'],'RESTAURAR')
    assert restored['recovery']['reason']=='transfer_ready'
    target.backups.activate_transfer('ACTIVAR SOLO ESTE EQUIPO')
    following = issue(target,customer['id'])
    assert following['sequence']==2
    assert following['payload']['fiscal']['hash']!=original['payload']['fiscal']['hash']
    assert target.fiscal.verify_chain()['ok']
    assert app.backups.recovery_status()['reason']=='transfer_source'
    # Moving back later is another explicit transfer from the now-active PC.
    back=target.backups.prepare_transfer()
    returning=app.backups.preview(back['content'])
    assert app.backups.restore(returning['token'],'RESTAURAR')['recovery']['reason']=='transfer_ready'
    app.backups.activate_transfer('ACTIVAR SOLO ESTE EQUIPO')
    assert issue(app,customer['id'])['sequence']==3
    assert target.backups.recovery_status()['blocked']


def test_restore_cannot_forget_a_known_fiscal_acknowledgment(app,customer):
    issued = issue(app,customer['id'])
    backup = app.backups.create()
    with app.db.transaction() as conn:
        conn.execute("UPDATE fiscal_outbox SET status='accepted',attempts=1,csv='SYNTHETIC-LOCAL-ACK',response='test-fixture' WHERE record_id=?",(issued['payload']['fiscal']['record_id'],))
    preview = app.backups.preview(backup['content'])
    result = app.backups.restore(preview['token'],'RESTAURAR')
    assert result['recovery']['reason']=='older_history'
    with pytest.raises(AppError,match='acuses'):
        issue(app,customer['id'])


def test_failed_rollback_leaves_journal_for_next_start(app,restore_case,monkeypatch):
    preview = app.backups.preview(restore_case['backup']['content'])
    checkpoint = app.backups._checkpoint
    replace = os.replace
    fault = {'restore':False,'rollback':False}

    def fail_stage(stage):
        checkpoint(stage)
        if stage=='installed:assets':
            fault['restore']=True
            raise OSError('Injected installation fault')

    def fail_rollback(source,target):
        if fault['restore'] and not fault['rollback'] and Path(source).parts[-2:]==('old','taller.sqlite3'):
            fault['rollback']=True
            raise OSError('Injected rollback fault')
        return replace(source,target)

    monkeypatch.setattr(app.backups,'_checkpoint',fail_stage)
    monkeypatch.setattr('taller.backups.os.replace',fail_rollback)
    with pytest.raises(AppError,match='interrumpida'):
        app.backups.restore(preview['token'],'RESTAURAR')
    assert app.backups.recovery_status()['pending_journal']
    with pytest.raises(AppError):
        app.dispatch('customers.save',{'data':{'name':'No se debe escribir durante recuperación'}})
    reopened = App(app.db.root)
    assert_current_resources(reopened)
    assert reopened.documents.list()['total']==2
    assert reopened.db.check_audit()['ok']
    assert not (app.db.root/JOURNAL).exists()


@pytest.mark.parametrize("tamper", ["hash", "xml"])
def test_preview_rejects_a_broken_fiscal_chain_even_with_matching_zip_hashes(app,customer,tmp_path,tamper):
    issue(app,customer['id'])
    backup = app.backups.create()['content']
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(backup))) as archive:
        path = tmp_path/'synthetic-corrupt.sqlite3'
        path.write_bytes(archive.read('taller.sqlite3'))
    with closing(sqlite3.connect(path)) as conn,conn:
        conn.execute('DROP TRIGGER fiscal_no_update')
        if tamper == 'hash':
            conn.execute("UPDATE fiscal_records SET hash=?",('A'*64,))
        else:
            conn.execute("UPDATE fiscal_records SET xml=replace(xml,'Trabajo sintético','Concepto alterado')")
    package = rewrite_archive(backup,{'taller.sqlite3':path.read_bytes()})
    with pytest.raises(AppError,match='cadena fiscal' if tamper=='hash' else 'XML fiscal no coincide'):
        app.backups.preview(package)


def test_source_stays_inactive_if_transfer_export_fails_after_writing(app,customer,monkeypatch):
    issue(app,customer['id'])
    def fail(*_args,**_kwargs):
        raise OSError('Injected post-export settings failure')
    monkeypatch.setattr(app.settings,'internal_update',fail)
    with pytest.raises(OSError):
        app.backups.prepare_transfer()
    assert app.backups.recovery_status()['reason']=='transfer_source'
    recovered = app.backups.prepare_transfer()
    assert recovered['repeated'] and recovered['source_blocked']
    assert (app.db.root/'backups'/recovered['name']).exists()


def test_configured_retention_only_removes_automatic_copies(app):
    directory=app.db.root/'backups'
    for name in ('auto-20260101-000000.canamo','auto-20260102-000000.canamo','copia-previa.canamo','traslado-protegido.canamo'):
        (directory/name).write_bytes(b'synthetic-retention-fixture')
    app.backups.configure_retention(daily=1,weekly=0,monthly=0)
    app.backups._retention()
    assert sorted(path.name for path in directory.glob('*.canamo'))==['auto-20260102-000000.canamo','copia-previa.canamo','traslado-protegido.canamo']
    with pytest.raises(AppError): app.backups.configure_retention(0,0,0)


def test_legacy_backup_migrates_only_staging_and_preserves_fiscal_records(app,customer,tmp_path):
    original = issue(app,customer['id'])
    old_path = tmp_path/'old-schema-1.sqlite3'
    with closing(sqlite3.connect(old_path)) as old, app.db.read() as source:
        old.executescript(SCHEMA)
        tables=[row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            columns=[row[1] for row in old.execute('PRAGMA table_info('+table+')')]
            rows=source.execute('SELECT '+','.join(columns)+' FROM '+table).fetchall()
            old.executemany('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[tuple(row) for row in rows])
        old.execute('PRAGMA user_version=1')
        old.commit()
    raw=old_path.read_bytes()
    manifest={'schema':1,'created_at':'2026-01-01T00:00:00+00:00','certificate_included':False,
              'files':{'taller.sqlite3':hashlib.sha256(raw).hexdigest()}}
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        archive.writestr('manifest.json',json.dumps(manifest))
        archive.writestr('taller.sqlite3',raw)
    preview=app.backups.preview(base64.b64encode(buffer.getvalue()).decode())
    assert preview['migration']['from_version']==1 and preview['migration']['to_version']==SCHEMA_VERSION
    assert old_path.read_bytes()==raw
    result=app.backups.restore(preview['token'],'RESTAURAR')
    assert not result['recovery']['blocked']
    assert app.documents.get(original['id'])['payload']['fiscal']['hash']==original['payload']['fiscal']['hash']
    assert issue(app,customer['id'])['sequence']==2
    assert app.fiscal.verify_chain()['ok']


def test_preview_expiry_and_tampering_never_replace_live_data(app,customer):
    backup=app.backups.create()
    preview=app.backups.preview(backup['content'])
    folder=app.backups.previews[preview['token']]['folder']
    (folder/'taller.sqlite3').write_bytes(b'changed-after-preview')
    with pytest.raises(AppError,match='vista previa ha cambiado'):
        app.backups.restore(preview['token'],'RESTAURAR')
    assert app.contacts.customer(customer['id'])['name']==customer['name']
    assert not folder.exists()
    assert len(app.backups.list())==1
    expired=app.backups.preview(backup['content'])
    stale=app.backups.previews[expired['token']]
    stale['expires']=datetime.now(timezone.utc)-timedelta(seconds=1)
    with pytest.raises(AppError,match='caducado'):
        app.backups.restore(expired['token'],'RESTAURAR')
    assert not stale['folder'].exists()
    assert app.contacts.customer(customer['id'])['name']==customer['name']


def test_second_location_receives_the_completed_encrypted_archive(app,tmp_path):
    external=tmp_path/'Copias con espacios y tildes'
    app.settings.save('backup',{'external_directory':str(external)})
    result=app.backups.create('synthetic-test-password')
    local=(app.db.root/'backups'/result['name']).read_bytes()
    assert local.startswith(MAGIC)
    assert (external/result['name']).read_bytes()==local
    assert result['warning']=='' and not list(external.glob('*.partial'))


@pytest.mark.parametrize('failure', [False, True])
def test_import_originals_staging_and_metadata_are_restored_as_one_set(app, tmp_path, monkeypatch, failure):
    imported = app.imports.preview('legacy_code,name\nBK1,Cliente sintético para copia\n')
    identifier = imported['batch_id']
    folder = app.db.root/'imports'/identifier
    original = {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob('*') if path.is_file()}
    assert {'source.bin','upload.json','diagnostic.json','staging.sqlite'} <= set(original)
    backup = app.backups.create()['content']
    extra = folder/'extracted'/'independiente.jsonl'
    extra.parent.mkdir(exist_ok=True)
    extra.write_text('{"campo_no_mapeado":"conservar"}\n', encoding='utf-8')
    preview = app.backups.preview(backup)
    if failure:
        checkpoint = app.backups._checkpoint
        def fail(stage):
            checkpoint(stage)
            if stage=='installed:imports':
                raise OSError('Fallo inyectado tras instalar importaciones')
        monkeypatch.setattr(app.backups,'_checkpoint',fail)
        with pytest.raises(AppError, match='conjunto anterior'):
            app.backups.restore(preview['token'],'RESTAURAR')
        assert extra.read_text(encoding='utf-8') == '{"campo_no_mapeado":"conservar"}\n'
    else:
        app.backups.restore(preview['token'],'RESTAURAR')
        assert not extra.exists()
    assert {name:(folder/name).read_bytes() for name in original} == original
    reopened = App(app.db.root)
    assert reopened.imports.review(identifier)['batch_id'] == identifier


def test_copy_rejects_missing_or_changed_original_import_source(app):
    imported = app.imports.preview('legacy_code,name\nBK2,Cliente sintético de origen\n')
    path = app.db.root/'imports'/imported['batch_id']/'source.bin'
    original = path.read_bytes()
    path.write_bytes(original+b'alterado')
    with pytest.raises(AppError, match='original.*huella'):
        app.backups.create()
    path.unlink()
    with pytest.raises(AppError, match='originales'):
        app.backups.create()
