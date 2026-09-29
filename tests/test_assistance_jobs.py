"""Memory-only assistance jobs, real local engines and injected slow-provider contracts."""
import base64
import json
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from time import monotonic

import pytest

from taller.app import App
from taller.assistance import MAX_JOBS
from taller.errors import AppError

FIXTURES=Path(__file__).parent/'fixtures/assistance'


def wait_job(app, identifier):
    deadline=monotonic()+30
    while monotonic()<deadline:
        value=app.dispatch('assistant.job_status',{'identifier':identifier})
        if value['status'] not in ('queued','running') and not value['worker_active']:
            return value
        Event().wait(.005)
    raise AssertionError('El trabajo de prueba no terminó dentro de 30 segundos')


def counts(app):
    with app.db.read() as conn:
        return {name:conn.execute('SELECT count(*) FROM '+name).fetchone()[0]
                for name in ('customers','documents','audit','fiscal_records','payments')}


@pytest.mark.parametrize('operation,filename',[
    ('rewrite',None),('extract','ficha-sintetica.png'),('transcribe','dictado-sintetico.wav'),
])
def test_jobs_run_real_local_engines_offline_and_do_not_persist_proposals(app, monkeypatch, operation, filename):
    app.settings.save('assistant',{'enabled':True,'model':''})
    def forbidden(*args,**kwargs):
        raise AssertionError('Un trabajo local no puede abrir conexiones de red')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    params={'text':'  revisar   ruido sintético '} if filename is None else {
        'content':base64.b64encode((FIXTURES/filename).read_bytes()).decode(),'name':filename}
    before=counts(app)
    job=app.dispatch('assistant.start',{'operation':operation,'params':params,'idempotency_key':'offline-'+operation})
    assert job['status'] in ('queued','running') and job['operation']==operation
    value=wait_job(app,job['id'])
    assert value['status']=='completed' and value['result']['requires_review']
    assert value['result']['network_called'] is False
    assert value['result']['text']
    assert counts(app)==before
    assert not list(app.db.root.rglob('*.wav')) and not list(app.db.root.rglob('*.png'))
    assert App(app.db.root).assistance._jobs=={}


def test_slow_rewrite_does_not_block_search_or_invoice_and_cancel_discards_late_result(app, draft, monkeypatch):
    app.settings.save('assistant',{'enabled':True,'model':'synthetic-local:1'})
    entered,release=Event(),Event()
    calls=[]
    def protocol(path,data=None,**kwargs):
        calls.append(path)
        if path=='/api/show':
            return {'details':{'format':'gguf'},'model_info':{'general.architecture':'llama'}}
        entered.set()
        assert release.wait(10)
        return {'response':'{"text":"Notas sintéticas"}'}
    monkeypatch.setattr('taller.assistance._local_model',protocol)
    params={'operation':'rewrite','params':{'text':'Notas sintéticas'},'idempotency_key':'slow-one'}
    job=app.dispatch('assistant.start',params)
    try:
        assert entered.wait(5)
        assert app.dispatch('assistant.start',params)['id']==job['id']
        with pytest.raises(AppError) as caught:
            app.dispatch('assistant.start',{**params,'params':{'text':'Otro texto'}})
        assert caught.value.code=='conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            found=pool.submit(app.dispatch,'customers.search',{'query':'Lucia'}).result(timeout=1)
            emitted=pool.submit(app.dispatch,'documents.publish',{'identifier':draft['id']}).result(timeout=1)
        assert found[0]['customer_id']==draft['customer_id'] and emitted['status']=='issued'
        cancelled=app.dispatch('assistant.cancel',{'identifier':job['id']})
        assert cancelled['status']=='cancelled' and cancelled['worker_active']
        assert 'result' not in cancelled
        with pytest.raises(AppError) as caught:
            app.dispatch('assistant.start',{**params,'idempotency_key':'new-while-cancelled'})
        assert caught.value.code=='assistant_busy'
    finally:
        release.set()
    finished=wait_job(app,job['id'])
    assert finished['status']=='cancelled' and 'result' not in finished
    assert 'Notas sintéticas' not in json.dumps(finished,ensure_ascii=False)
    assert calls==['/api/show','/api/generate']
    assert app.documents.get(draft['id'])['payload']['notes']==''


def test_cancel_releases_completed_proposal_and_is_idempotent(app):
    app.settings.save('assistant',{'enabled':True})
    params={'operation':'rewrite','params':{'text':'Texto de prueba'},'idempotency_key':'completed'}
    job=app.dispatch('assistant.start',params)
    assert wait_job(app,job['id'])['status']=='completed'
    cancelled=app.dispatch('assistant.cancel',{'identifier':job['id']})
    assert cancelled['status']=='cancelled' and 'result' not in cancelled
    assert app.dispatch('assistant.cancel',{'identifier':job['id']})==cancelled
    assert app.dispatch('assistant.start',params)==cancelled


def test_job_errors_hide_provider_internals_and_keep_domain_messages(app, monkeypatch, caplog):
    app.settings.save('assistant',{'enabled':True})
    def crash(text):
        raise RuntimeError('PRIVATE-CONTENT and C:/private/certificate.key')
    monkeypatch.setattr(app.assistance,'rewrite',crash)
    failed=app.dispatch('assistant.start',{'operation':'rewrite','params':{'text':'Texto sintético'},'idempotency_key':'crash'})
    result=wait_job(app,failed['id'])
    assert result['status']=='failed' and result['error']['code']=='assistant_failed'
    assert 'PRIVATE-CONTENT' not in json.dumps(result) and 'certificate.key' not in caplog.text
    invalid=app.dispatch('assistant.start',{'operation':'transcribe','params':{'content':'invalid-base64!'},'idempotency_key':'invalid'})
    result=wait_job(app,invalid['id'])
    assert result['status']=='failed' and result['error']['code']=='validation'
    assert 'codificado' in result['error']['message']


def test_jobs_expire_and_bounded_history_does_not_write_data(app, monkeypatch):
    app.settings.save('assistant',{'enabled':True})
    stamp=datetime(2026,9,23,tzinfo=timezone.utc)
    monkeypatch.setattr(app.assistance,'_job_clock',lambda:stamp)
    before=counts(app)
    identifiers=[]
    for index in range(MAX_JOBS+1):
        job=app.dispatch('assistant.start',{'operation':'rewrite','params':{'text':'Propuesta sintética'},'idempotency_key':str(index)})
        assert wait_job(app,job['id'])['status']=='completed'
        identifiers.append(job['id'])
    assert len(app.assistance._jobs)==MAX_JOBS
    with pytest.raises(AppError) as caught:
        app.dispatch('assistant.job_status',{'identifier':identifiers[0]})
    assert caught.value.code=='not_found'
    stamp+=timedelta(minutes=16)
    with pytest.raises(AppError) as caught:
        app.dispatch('assistant.job_status',{'identifier':identifiers[-1]})
    assert caught.value.code=='not_found' and not app.assistance._jobs
    assert counts(app)==before


@pytest.mark.parametrize('operation,params,key',[
    ('shutdown',{},'x'),('rewrite',{'text':'Texto','conn':'internal'},'x'),
    ('rewrite',{'text':True},'x'),('rewrite',{'text':'x'*4001},'x'),
    ('extract',{'content':'AA==','name':'x'*251},'x'),('transcribe',{'content':'AA=='},False),
])
def test_job_rpc_rejects_wrong_types_before_starting_engine(app, operation, params, key):
    app.settings.save('assistant',{'enabled':True})
    with pytest.raises(AppError):
        app.dispatch('assistant.start',{'operation':operation,'params':params,'idempotency_key':key})
    assert not app.assistance._jobs and app.assistance._active_job is None
